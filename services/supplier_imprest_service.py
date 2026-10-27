"""Supplier extensions reuse the existing master/payables; imprest retires cash once."""
from uuid import uuid4
from models import (Supplier, SupplierProfile, SupplierQuotation, SupplierBill, FinancePayable,
    PurchaseRequest, PurchaseFulfillment, RequestItem, ImprestFund, ImprestEntry, ImprestReplenishment, Attachment)
from packages.database import db
from services.business_core import *
from services.storage_service import save_attachment
from services.operational_policy import require_operational, can_operate

BUYERS=FINANCE|{"procurement"}


def supplier_profile(user,supplier,data=None):
    row=SupplierProfile.query.filter_by(organization_id=user.organization_id,supplier_id=supplier.id).first()
    if not row:
        row=SupplierProfile(id=str(uuid4()),**dimensions(user,data or {}),supplier_id=supplier.id);db.session.add(row);db.session.flush()
    return row


def create_supplier(app,user,data):
    require_operational(user,"supplier","supplier / vendor operations")
    from services.management_service import ensure_supplier
    supplier=ensure_supplier(user,text_value(data,'name',True,180));db.session.flush()
    row=supplier_profile(user,supplier,data)
    return supplier_action(app,user,row,'update',data)


def supplier_action(app,user,row,action,data,files=None):
    require_operational(user,"finance_ops" if action=="bill" else "supplier","supplier bill / payable" if action=="bill" else "supplier / vendor operations");files=files or {}
    supplier=tenant_row(Supplier,user,row.supplier_id)
    if action=='update':
        for key,limit in [('phone',80),('email',180),('address',255),('notes',4000)]:
            if key in data:setattr(supplier,key,text_value(data,key,limit=limit))
        if supplier.email and ('@' not in supplier.email or ' ' in supplier.email):raise ValueError('Enter a valid supplier email address.')
        for key,limit in [('contact_person',180),('bank_name',160),('bank_account',80),('account_name',180),('tin',80),('offerings',4000)]:
            if key in data:setattr(row,key,text_value(data,key,limit=limit))
        if data.get('rating'):
            row.rating=count(data['rating'])
            if not 1<=row.rating<=5:raise ValueError('Vendor rating must be between 1 and 5.')
    elif action=='quotation':
        quote=SupplierQuotation(id=str(uuid4()),**inherited(user,row),supplier_id=supplier.id,
            description=text_value(data,'description',True,300),quoted=money(data.get('quoted'),True),
            negotiated=money(data.get('negotiated'),True),quantity=money(data.get('quantity'),True,'0.001'),
            promised_date=day(data.get('promised_date'),False))
        if data.get('request_id'):quote.request_id=get_row(PurchaseRequest,user,data['request_id'],broad=BUYERS).id
        db.session.add(quote)
    elif action=='delivery':
        quote=get_row(SupplierQuotation,user,data.get('quotation_id'),True,broad=BUYERS)
        if quote.supplier_id!=supplier.id:raise ValueError('Quotation does not belong to this supplier.')
        delivered=money(data.get('delivered'),places='0.001')
        if delivered<quote.delivered or delivered>quote.quantity:raise ValueError('Delivery total must be between previous deliveries and ordered quantity.')
        quote.delivered=delivered;quote.delivered_at=instant()
    elif action=='bill':
        amount=money(data.get('amount'),True)
        bill=SupplierBill(id=str(uuid4()),**inherited(user,row),supplier_id=supplier.id)
        if data.get('fulfillment_id'):
            fulfillment=get_row(PurchaseFulfillment,user,data['fulfillment_id'],broad=BUYERS)
            if fulfillment.is_draft or not fulfillment.confirmed_at:raise ValueError('Select a finalized acquisition.')
            if (fulfillment.supplier_name or '').strip().casefold()!=supplier.name.strip().casefold():raise ValueError('Acquisition and supplier must match.')
            if amount!=fulfillment.actual_total:raise ValueError('The bill total must match the confirmed acquisition.')
            bill.fulfillment_id=fulfillment.id
        payable=FinancePayable(id=str(uuid4()),reference='AP-'+uuid4().hex[:20].upper(),organization_id=user.organization_id,
            department_id=row.department_id,created_by_id=user.id,vendor_name=supplier.name,
            bill_number=text_value(data,'bill_number',True,120),description=text_value(data,'description',True,300),
            total_amount=amount,amount_paid=0,currency=user.organization.currency,due_date=day(data.get('due_date')),status='open')
        if FinancePayable.query.filter_by(organization_id=user.organization_id,vendor_name=supplier.name,bill_number=payable.bill_number).first():raise ValueError('This supplier invoice is already recorded.')
        db.session.add(payable);bill.payable_id=payable.id;db.session.add(bill);db.session.flush()
        tag_branch(user,bill,payable)
        if not bill.fulfillment_id:post(user,bill,'supplier-bill:'+bill.id,amount,'expense','neutral',{},'expense',payable.description)
    elif action=='evidence':
        if not files.get('evidence'):raise ValueError('Choose a supplier document.')
        save_attachment(app,files['evidence'],user,'supplier',supplier.id,'supplier_document')
    else:raise ValueError('Unsupported supplier action.')
    activity(app,user,row,'supplier_'+action,'Supplier '+action.replace('_',' '),'supplier')
    return row


def pay_supplier_bill(app,user,bill,data):
    require_operational(user,"finance_ops","finance operations")
    payable=tenant_row(FinancePayable,user,bill.payable_id)
    if payable.status=='cancelled':raise ValueError('This bill is cancelled.')
    amount=money(data.get('amount'),True)
    if amount>payable.total_amount-payable.amount_paid:raise ValueError('Payment exceeds the supplier balance.')
    post(user,bill,'supplier-payment:'+str(uuid4()),amount,'cash_out','out',data,description='Supplier payment · '+(payable.bill_number or payable.reference))
    payable.amount_paid+=amount;payable.status='paid' if payable.amount_paid==payable.total_amount else 'partial'
    # The bill version also guards concurrent payments on SQLite.
    bill.updated_at=instant()
    activity(app,user,bill,'supplier_payment','Supplier payment recorded','supplier')
    return bill


def create_imprest(app,user,data):
    require_operational(user,"finance_ops","finance operations")
    row=ImprestFund(id=str(uuid4()),**dimensions(user,data),name=text_value(data,'name',True,180),
        ceiling=money(data.get('ceiling'),True),holder_id=user.id)
    holder=worker(user,data.get('holder_id'));align_worker(user,row,holder,data);row.holder_id=holder.id
    db.session.add(row);db.session.flush()
    activity(app,user,row,'imprest_created','Petty cash / imprest fund opened','imprest')
    return row


def imprest_action(app,user,row,action,data,files=None):
    files=files or {}
    if row.status!='active':raise ValueError('This fund is closed.')
    if not can_operate(user,"finance_ops") and user.id!=row.holder_id:raise PermissionError('Only the fund holder or Finance can manage this imprest.')
    balance=row.issued-row.spent-row.returned
    if action in {'issue','spend','return'}:
        amount=money(data.get('amount'),True)
        if action=='issue':
            require_operational(user,"finance_ops","finance operations")
            if row.issued:raise ValueError('Use an approved replenishment after the opening cash issue.')
            if amount>row.ceiling:raise ValueError('Cash issue exceeds the fund ceiling.')
        elif amount>balance:raise ValueError('Amount exceeds available petty cash.')
        if action=='spend' and not files.get('evidence'):raise ValueError('Attach the expenditure receipt.')
        entry=ImprestEntry(id=str(uuid4()),**inherited(user,row),fund_id=row.id,kind=action,
            description=text_value(data,'description',True,300),amount=amount,occurred_at=instant(data.get('occurred_at')))
        posting=post(user,row,'imprest-entry:'+entry.id,amount,'expense' if action=='spend' else 'cash_out' if action=='issue' else 'cash_in',
            'neutral' if action=='spend' else 'out' if action=='issue' else 'in',data,'expense' if action=='spend' else None,entry.description)
        entry.posting_id=posting.id;db.session.add(entry)
        if action=='issue':row.issued+=amount
        elif action=='spend':
            row.spent+=amount;save_attachment(app,files['evidence'],user,'imprest',row.id,'imprest_receipt',True)
        else:row.returned+=amount
    elif action=='request_replenishment':
        if ImprestReplenishment.query.filter_by(organization_id=user.organization_id,fund_id=row.id,status='submitted').first():raise ValueError('An existing replenishment request is still pending.')
        paid=sum((r.amount for r in ImprestReplenishment.query.filter_by(organization_id=user.organization_id,fund_id=row.id,status='paid')),Decimal(0))
        amount=money(data.get('amount'),True)
        if amount>row.spent-paid:raise ValueError('Replenishment cannot exceed expenditure not yet replenished.')
        req=PurchaseRequest(id=str(uuid4()),reference='IMP-'+uuid4().hex[:20].upper(),organization_id=user.organization_id,department_id=row.department_id,
            requester_id=user.id,title='Imprest replenishment · '+row.name,purpose=text_value(data,'description',True),
            estimated_total=amount,currency=user.organization.currency,status='approved' if individual(user) and user.role in OWNER else 'submitted',
            submitted_at=instant(),approved_at=instant() if individual(user) and user.role in OWNER else None,
            approved_by_id=user.id if individual(user) and user.role in OWNER else None)
        db.session.add(req);db.session.flush()
        db.session.add(ImprestReplenishment(**inherited(user,row),fund_id=row.id,request_id=req.id,amount=amount))
    elif action=='replenish':
        require_operational(user,"finance_ops","finance operations")
        replenishment=get_row(ImprestReplenishment,user,data.get('replenishment_id'),True)
        if replenishment.fund_id!=row.id or replenishment.status!='submitted':raise ValueError('This replenishment has already been paid or belongs to another fund.')
        req=tenant_row(PurchaseRequest,user,replenishment.request_id)
        if req.status!='approved':raise ValueError('Approve the replenishment in Requests first.')
        if balance+replenishment.amount>row.ceiling:raise ValueError('Replenishment exceeds the fund ceiling.')
        post(user,row,'imprest-replenishment:'+replenishment.id,replenishment.amount,'cash_out','out',data,description=req.title)
        row.issued+=replenishment.amount;replenishment.status='paid';replenishment.paid_at=instant()
        req.status='verified';req.money_sent_at=instant();req.money_sent_by_id=user.id
        from services.budget_control_service import sync_request_budget
        sync_request_budget(req,user,release=True)
    elif action=='close':
        require_role(user,OWNER)
        if balance!=0:raise ValueError('Retire or return the entire cash balance before closing.')
        if ImprestReplenishment.query.filter_by(organization_id=user.organization_id,fund_id=row.id,status='submitted').count():raise ValueError('Resolve pending replenishments first.')
        row.status='closed';row.closed_at=instant()
    else:raise ValueError('Unsupported imprest action.')
    activity(app,user,row,'imprest_'+action,'Imprest · '+action.replace('_',' '),'imprest')
    return row
