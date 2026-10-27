"""CRM and accrual sales: recognize each sale once, collect it in any number of parts."""
from uuid import uuid4
from decimal import Decimal
from models import (Customer, CustomerActivity, SalesInvoice, SalesLine, InvoicePayment,
                    EventPlan, FinanceReceivable, InventoryItem, StockMovement)
from packages.database import db
from services.business_core import *

STAGES = ("lead", "prospect", "customer", "repeat_customer")


def create_customer(app, user, data):
    stage = data.get("stage") or "lead"
    if stage not in STAGES: raise ValueError("Choose a valid customer stage.")
    row = Customer(id=str(uuid4()), **dimensions(user, data), name=text_value(data, "name", True, 180), stage=stage,
        phone=text_value(data,"phone",limit=80),email=text_value(data,"email",limit=180),
        business=text_value(data,"business",limit=180),address=text_value(data,"address",limit=255),
        notes=text_value(data,"notes"),next_follow_up=day(data.get("next_follow_up"),False),assigned_to_id=user.id)
    if row.email and ("@" not in row.email or " " in row.email): raise ValueError("Enter a valid email address.")
    if data.get("event_id"):
        event = get_row(EventPlan,user,data["event_id"])
        if event.branch_id != row.branch_id and user.role not in OWNER: raise PermissionError("The event belongs to another branch.")
        row.event_id=event.id
    db.session.add(row);db.session.flush()
    activity(app,user,row,"customer_created","Customer / lead created","customer")
    return row


def customer_action(app,user,row,action,data):
    if action == "update":
        for field,limit in [("name",180),("phone",80),("email",180),("business",180),("address",255),("notes",4000)]:
            if field in data: setattr(row,field,text_value(data,field,field=="name",limit))
        if row.email and ("@" not in row.email or " " in row.email): raise ValueError("Enter a valid email address.")
        if data.get("stage"):
            if data["stage"] not in STAGES: raise ValueError("Choose a valid CRM stage.")
            row.stage=data["stage"]
        if "next_follow_up" in data: row.next_follow_up=day(data.get("next_follow_up"),False)
        note=text_value(data,"activity_notes") or "Contact details / stage updated"
    elif action == "note": note=text_value(data,"notes",True)
    else: raise ValueError("Unsupported customer action.")
    db.session.add(CustomerActivity(**inherited(user,row),customer_id=row.id,kind=action,notes=note,occurred_at=instant()))
    activity(app,user,row,"customer_"+action,"CRM contact updated","customer")
    return row


def create_invoice(app,user,data):
    customer=get_row(Customer,user,data.get("customer_id"),True)
    dims=dimensions(user,data)
    if customer.branch_id != dims['branch_id'] and user.role not in OWNER: raise PermissionError("Customer and sale must belong to the same branch.")
    lines=data.get("lines")
    if not lines:
        lines=[dict(description=data.get("description"),inventory_id=data.get("inventory_id"),quantity=data.get("quantity") or 1,unit_price=data.get("unit_price"))]
    if not isinstance(lines,list) or not 1 <= len(lines) <= 100: raise ValueError("Provide between one and 100 sale lines.")
    row=SalesInvoice(id=str(uuid4()),**dims,customer_id=customer.id,number=text_value(data,"number",limit=80) or "INV-"+uuid4().hex[:12].upper(),
        description=text_value(data,"description",True,300),currency=user.organization.currency,
        subtotal=Decimal(0),discount=money(data.get("discount")),tax=money(data.get("tax")),total=Decimal(0),paid=Decimal(0),
        due_date=day(data.get("due_date"),False),issued_at=instant(data.get("issued_at") or data.get("occurred_at")),sales_person_id=user.id)
    if row.issued_at > instant(): raise ValueError("Issue date cannot be in the future.")
    person=worker(user,data.get("sales_person_id"))
    if user.role not in OWNER and person.id != user.id: raise PermissionError("Only an owner can attribute a sale to another staff member.")
    align_worker(user,row,person,data)
    row.sales_person_id=person.id
    event_id=data.get("event_id") or customer.event_id
    if event_id: row.event_id=get_row(EventPlan,user,event_id).id
    db.session.add(row)
    for line in lines:
        if not isinstance(line,dict): raise ValueError("Each sale line must be an object.")
        quantity=money(line.get("quantity"),True,"0.001");price=money(line.get("unit_price"),True)
        cost=Decimal(0);item=None
        if line.get("inventory_id"):
            item=get_row(InventoryItem,user,line["inventory_id"],True,broad=FINANCE|{"procurement"})
            if quantity > item.quantity: raise ValueError("Insufficient stock for "+item.name)
            from services.stock_service import take_stock
            cost=take_stock(user,item,quantity,'sale',row.id)
            db.session.add(StockMovement(organization_id=user.organization_id,inventory_item_id=item.id,user_id=user.id,
                movement_type="sale",quantity=quantity,reason="Invoice "+row.number,reference=row.id))
        total=money(quantity*price)
        description=str(line.get("description") or (item.name if item else row.description)).strip()
        if len(description)>180: raise ValueError("Sale line description is too long.")
        db.session.add(SalesLine(**inherited(user,row),invoice_id=row.id,inventory_id=item.id if item else None,
            description=description,quantity=quantity,unit_price=price,cost_price=cost,total=total))
        row.subtotal+=total
    if row.discount>row.subtotal: raise ValueError("Discount cannot exceed the subtotal.")
    row.total=money(row.subtotal-row.discount+row.tax,True)
    paid=money(data.get("amount_paid"))
    if paid>row.total: raise ValueError("Payment exceeds the invoice total.")
    if paid<row.total and not row.due_date: raise ValueError("A credit sale requires a due date.")
    receivable=FinanceReceivable(id=str(uuid4()),reference="AR-"+uuid4().hex[:20].upper(),organization_id=user.organization_id,
        department_id=row.department_id,created_by_id=user.id,customer_name=customer.name,invoice_number=row.number,
        description=row.description,total_amount=row.total,amount_received=0,currency=row.currency,due_date=row.due_date,status="open")
    db.session.add(receivable);row.receivable_id=receivable.id;db.session.flush()
    tag_branch(user,row,receivable)
    # Revenue is recognized here. Collections below only move cash.
    post(user,row,"invoice-revenue:"+row.id,row.subtotal-row.discount,"revenue","neutral",{},"revenue","Sale · "+row.number+" · "+customer.name)
    if row.tax: post(user,row,"invoice-tax:"+row.id,row.tax,"liability","neutral",{},description="Invoice tax · "+row.number)
    customer.stage="repeat_customer" if SalesInvoice.query.filter_by(organization_id=user.organization_id,customer_id=customer.id).count()>1 else "customer"
    if paid: collect_invoice(app,user,row,dict(data,amount=paid))
    activity(app,user,row,"sale_created","Sale / credit invoice recorded","sale")
    return row


def collect_invoice(app,user,row,data):
    if row.status not in {"issued","partial"}: raise ValueError("This invoice has no open balance.")
    amount=money(data.get("amount"),True)
    if amount>row.total-row.paid: raise ValueError("Payment cannot exceed the outstanding balance.")
    payment=InvoicePayment(id=str(uuid4()),**inherited(user,row),invoice_id=row.id,amount=amount,occurred_at=instant(data.get("occurred_at")))
    posting=post(user,row,"invoice-payment:"+payment.id,amount,"cash_in","in",data,description="Invoice collection · "+row.number)
    if as_utc_time(posting.occurred_at)<as_utc_time(row.issued_at): raise ValueError("Payment cannot precede the invoice issue date.")
    payment.posting_id=posting.id;db.session.add(payment)
    row.paid+=amount;row.status="paid" if row.paid==row.total else "partial"
    if row.status=="paid":row.closed_at=instant()
    receivable=tenant_row(FinanceReceivable,user,row.receivable_id)
    receivable.amount_received=row.paid;receivable.status=row.status
    activity(app,user,row,"sale_collection","Customer payment collected","sale")
    return row


def as_utc_time(value):
    from core.datetime_utils import as_utc
    return as_utc(value)
