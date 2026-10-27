"""Plans, controlled lifecycle, funding, retirement and measured campaign outcomes."""
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import func
from models import (EventPlan, EventBudget, EventCash, EventExpense, EventResource, EventReport,
                    InventoryItem, StockMovement, AssetItem, AssetMovement, Attachment, EventTransfer)
from packages.database import db
from core.datetime_utils import as_utc
from services.business_core import *
from services.storage_service import save_attachment

LIFECYCLE = ("draft", "submitted", "approved", "funded", "ongoing", "completed", "outcome_review", "closed")


def transferred_out(event):
    return db.session.query(func.coalesce(func.sum(EventTransfer.amount),0)).filter_by(organization_id=event.organization_id,campaign_id=event.id).scalar()


def transferred_in(event):
    return db.session.query(func.coalesce(func.sum(EventTransfer.amount),0)).filter_by(organization_id=event.organization_id,event_id=event.id).scalar()


def event_balance(event):return event.released-event.spent-event.returned-transferred_out(event)


def campaign_allocation_limit(user,row,amount):
    if not row.parent_id:return
    parent=get_row(EventPlan,user,row.parent_id,True)
    if parent.status not in {'approved','funded','ongoing'}:raise ValueError('Approve the campaign before approving an activity budget.')
    siblings=EventPlan.query.filter(EventPlan.organization_id==user.organization_id,EventPlan.parent_id==parent.id,EventPlan.id!=row.id).all()
    if parent.spent+sum((s.approved for s in siblings),Decimal(0))+amount>parent.approved:raise ValueError('Activity budgets and direct campaign spending cannot exceed the campaign budget.')
    parent.updated_at=instant()  # Concurrent child approvals share the campaign version lock.


def manageable(user, event):
    if user.role not in OWNER and user.id not in {event.manager_id, event.created_by_id} and user.role != "department_head":
        raise PermissionError("Only the responsible staff or an authorized manager can manage this activity.")


def create_event(app, user, payload):
    dims = dimensions(user, payload)
    kind = payload.get("kind", "event")
    if kind not in {"event", "campaign"}: raise ValueError("Choose Event or Campaign.")
    start, end = instant(payload.get("start_at")), instant(payload.get("end_at"))
    if not payload.get("start_at") or not payload.get("end_at") or end < start: raise ValueError("Set a start and an end after the start.")
    row = EventPlan(id=str(uuid4()), **dims, name=text_value(payload, "name", True, 180), kind=kind,
        category=text_value(payload, "category", True, 100), objective=text_value(payload, "objective", True),
        description=text_value(payload, "description"), venue=text_value(payload, "venue", limit=255),
        start_at=start, end_at=end, manager_id=user.id, requested=money(payload.get("requested")),
        expected_reach=count(payload.get("expected_reach")), expected_leads=count(payload.get("expected_leads")),
        expected_customers=count(payload.get("expected_customers")), expected_revenue=money(payload.get("expected_revenue")),
        staffing=text_value(payload, "staffing"), notes=text_value(payload, "notes"))
    manager = worker(user, payload.get("manager_id"))
    if user.role not in OWNER and manager.id != user.id: raise PermissionError("Only an owner can assign another event manager.")
    align_worker(user,row,manager,payload)
    row.manager_id = manager.id
    if payload.get("parent_id"):
        parent = get_row(EventPlan, user, payload["parent_id"], True)
        manageable(user, parent)
        if kind != "event" or parent.kind != "campaign" or parent.status in {"completed", "outcome_review", "closed"}: raise ValueError("Choose an active parent campaign for this event.")
        if as_utc(parent.start_at) > start or as_utc(parent.end_at) < end: raise ValueError("Activity dates must lie within the campaign period.")
        if parent.branch_id != row.branch_id and user.role not in OWNER: raise PermissionError("This campaign belongs to another branch.")
        row.parent_id = parent.id
    db.session.add(row); db.session.flush()
    activity(app, user, row, "event_created", "Event/campaign plan created", "event")
    return row


def event_action(app, user, row, action, data, files=None):
    files = files or {}
    if action not in {"approve", "fund", "allocate", "close", "review"} and not (action=='return_funds' and user.role in FINANCE): manageable(user, row)
    if action == "budget":
        if row.status != "draft": raise ValueError("Budget lines can only change in Draft.")
        line = EventBudget(id=str(uuid4()), **inherited(user, row), event_id=row.id,
                           name=text_value(data, "name", True, 160), amount=money(data.get("amount"), True))
        db.session.add(line); db.session.flush()
        row.requested = db.session.query(func.sum(EventBudget.amount)).filter_by(organization_id=user.organization_id, event_id=row.id).scalar()
    elif action == "submit":
        if row.status != "draft": raise ValueError("Only a Draft can be submitted.")
        row.status, row.submitted_at = "submitted", instant()
        if individual(user) and user.role in OWNER:
            campaign_allocation_limit(user,row,row.requested)
            row.status, row.approved, row.approved_at, row.approved_by_id = "approved", row.requested, instant(), user.id
    elif action == "approve":
        require_role(user, OWNER)
        if row.status != "submitted": raise ValueError("Submit the plan before approval.")
        approved = money(data.get("amount"))
        if approved > row.requested: raise ValueError("Approval cannot exceed the requested budget.")
        campaign_allocation_limit(user,row,approved)
        row.approved, row.status, row.approved_at, row.approved_by_id = approved, "approved", instant(), user.id
    elif action in {"fund", "return_funds"}:
        if action == "fund":
            require_role(user, FINANCE)
            if row.status not in {"approved", "funded", "ongoing"}: raise ValueError("Approve the event before funding.")
        elif row.status not in {"funded", "ongoing", "completed", "outcome_review"}: raise ValueError("There is no open event funding to return.")
        amount = money(data.get("amount"), True)
        limit = row.approved - row.released if action == "fund" else event_balance(row)
        if amount > limit: raise ValueError("Amount exceeds the available funding or unretired balance.")
        if action=='fund':
            root=get_row(EventPlan,user,row.parent_id,True) if row.parent_id else row
            children=EventPlan.query.filter_by(organization_id=user.organization_id,parent_id=root.id).all()
            external=root.released+sum((child.released-transferred_in(child) for child in children),Decimal(0))
            if external+amount>root.approved:raise ValueError('Campaign funding would exceed the approved campaign envelope. Allocate existing campaign funds to the activity instead.')
            root.updated_at=instant()
        receiver = worker(user, data.get("receiver_id") or row.manager_id, row)
        cash = EventCash(id=str(uuid4()), **inherited(user, row), event_id=row.id, receiver_id=receiver.id,
                         kind=action, amount=amount, occurred_at=instant(data.get("occurred_at")))
        posting = post(user, row, "event-cash:"+cash.id, amount, "cash_out" if action == "fund" else "cash_in",
                       "out" if action == "fund" else "in", data, description=("Event funding · " if action == "fund" else "Event funds returned · ")+row.name)
        cash.posting_id = posting.id; db.session.add(cash)
        if action == "fund":
            row.released += amount; row.funded_at = row.funded_at or instant()
            if row.status == "approved": row.status = "funded"
            if row.parent_id and root.status=='approved':root.status='funded';root.funded_at=root.funded_at or instant()
        else: row.returned += amount
    elif action=='allocate':
        require_role(user,FINANCE)
        if row.kind!='campaign' or row.status not in {'funded','ongoing'}:raise ValueError('Only an open, funded campaign can allocate money to an activity.')
        child=get_row(EventPlan,user,data.get('event_id'),True)
        if child.parent_id!=row.id or child.status not in {'approved','funded','ongoing'}:raise ValueError('Choose an approved activity within this campaign.')
        amount=money(data.get('amount'),True)
        if amount>event_balance(row) or amount>child.approved-child.released:raise ValueError('Allocation exceeds available campaign funds or the activity budget.')
        db.session.add(EventTransfer(**inherited(user,row),campaign_id=row.id,event_id=child.id,amount=amount,notes=text_value(data,'notes',True)))
        child.released+=amount;child.funded_at=child.funded_at or instant()
        if child.status=='approved':child.status='funded'
        row.updated_at=instant()
    elif action == "start":
        if row.status != "funded" and not (row.status == "approved" and row.approved == 0): raise ValueError("Approve and fund this event before starting.")
        row.status, row.started_at = "ongoing", instant()
    elif action == "expense":
        if row.status not in {"funded", "ongoing", "completed", "outcome_review"}: raise ValueError("Record expenditure only against open, funded activities.")
        amount = money(data.get("amount"), True)
        if amount > event_balance(row): raise ValueError("Expenditure exceeds funds held for this activity.")
        if row.kind=='campaign':
            children=EventPlan.query.filter_by(organization_id=user.organization_id,parent_id=row.id).all()
            if row.spent+amount+sum((c.approved for c in children),Decimal(0))>row.approved:raise ValueError('This expenditure would consume budget already approved for campaign activities.')
        description = text_value(data, "description", True, 300)
        expense = EventExpense(id=str(uuid4()), **inherited(user, row), event_id=row.id, description=description,
                               amount=amount, occurred_at=instant(data.get("occurred_at")))
        if data.get("budget_id"):
            budget = tenant_row(EventBudget, user, data["budget_id"])
            if budget.event_id != row.id: raise ValueError("Choose a budget line for this event.")
            expense.budget_id = budget.id
        if not files.get("evidence"): raise ValueError("Attach a receipt for this expenditure.")
        posting = post(user, row, "event-expense:"+expense.id, amount, "expense", "neutral", data, "expense", row.name+" · "+description)
        expense.posting_id = posting.id; db.session.add(expense)
        save_attachment(app, files["evidence"], user, "event", row.id, "event_receipt", final=True)
        row.spent += amount
    elif action == "resource":
        if row.status not in {"approved", "funded", "ongoing"}: raise ValueError("Issue resources after approval and before completion.")
        quantity = money(data.get("quantity"), True, "0.001")
        inventory_id, asset_id = data.get("inventory_id"), data.get("asset_id")
        if bool(inventory_id) == bool(asset_id): raise ValueError("Choose one stock item or one asset.")
        resource = EventResource(id=str(uuid4()), **inherited(user, row), event_id=row.id, issued=quantity)
        if inventory_id:
            item = get_row(InventoryItem, user, inventory_id, True, broad=FINANCE | {"procurement"})
            if quantity > item.quantity: raise ValueError("Insufficient available stock.")
            from services.stock_service import take_stock
            take_stock(user,item,quantity,'event',resource.id)
            resource.inventory_id, resource.name = item.id, item.name
            db.session.add(StockMovement(organization_id=user.organization_id, inventory_item_id=item.id, user_id=user.id,
                movement_type="stock_out", quantity=quantity, reason="Event issue: "+row.name, reference=row.id))
        else:
            item = get_row(AssetItem, user, asset_id, True, broad=FINANCE | {"procurement"})
            if item.status not in {"active", "assigned"}: raise ValueError("This asset is unavailable.")
            held = db.session.query(func.coalesce(func.sum(EventResource.issued-EventResource.returned-EventResource.missing),0)).filter_by(organization_id=user.organization_id, asset_id=item.id, resolved_at=None).scalar()
            if quantity > item.quantity - held: raise ValueError("This asset quantity is already reserved or unavailable.")
            resource.asset_id, resource.name = item.id, item.name
            db.session.add(AssetMovement(organization_id=user.organization_id, asset_id=item.id, user_id=user.id,
                movement_type="assign", quantity=quantity, destination_location=row.venue, reason="Event issue: "+row.name, reference=row.id))
        db.session.add(resource)
    elif action == "resource_return":
        resource = get_row(EventResource, user, data.get("resource_id"), True)
        if resource.event_id != row.id or resource.resolved_at or row.status == "closed": raise ValueError("Choose an unresolved resource for this activity.")
        returned, distributed, missing = (money(data.get(key), places="0.001") for key in ("returned", "distributed", "missing"))
        if returned + distributed + missing != resource.issued: raise ValueError("Returned, distributed and missing quantities must equal the quantity issued.")
        if resource.asset_id and distributed: raise ValueError("Company assets cannot be distributed as consumables.")
        if missing:
            require_role(user, OWNER)
            resource.resolution = text_value(data, "resolution", True)
        if resource.inventory_id and returned:
            item = get_row(InventoryItem, user, resource.inventory_id, True, broad=FINANCE | {"procurement"})
            from services.stock_service import restore_stock
            restore_stock(user,item,returned,'event',resource.id)
            db.session.add(StockMovement(organization_id=user.organization_id, inventory_item_id=item.id, user_id=user.id,
                movement_type="return", quantity=returned, reason="Event return: "+row.name, reference=row.id))
        if resource.asset_id:
            item = get_row(AssetItem, user, resource.asset_id, True, broad=FINANCE | {"procurement"})
            if missing: item.quantity -= missing
            db.session.add(AssetMovement(organization_id=user.organization_id, asset_id=item.id, user_id=user.id,
                movement_type="return" if not missing else "write_off", quantity=returned or missing,
                reason="Event reconciliation: "+row.name, reference=row.id))
        resource.returned, resource.distributed, resource.missing, resource.resolved_at = returned, distributed, missing, instant()
    elif action == "complete":
        if row.status != "ongoing": raise ValueError("Only an Ongoing activity can be completed.")
        children = EventPlan.query.filter_by(organization_id=user.organization_id, parent_id=row.id).all()
        if any(child.status != "closed" for child in children): raise ValueError("Close all campaign activities first.")
        row.status, row.completed_at = "completed", instant()
    elif action == "report":
        if row.status not in {"completed", "outcome_review"}: raise ValueError("Complete the activity before submitting its outcome report.")
        report = EventReport.query.filter_by(organization_id=user.organization_id, event_id=row.id).first()
        if report and report.reviewed_by_id: raise ValueError("This report has already been reviewed.")
        if not report:
            report = EventReport(id=str(uuid4()), **inherited(user, row), event_id=row.id); db.session.add(report)
        for field in ("summary", "lessons", "follow_up"): setattr(report, field, text_value(data, field, True))
        for field in ("challenges", "comments"): setattr(report, field, text_value(data, field))
        for field in ("reach", "leads", "prospects", "customers", "sales"): setattr(report, field, count(data.get(field)))
        report.revenue = money(data.get("revenue"))
        report.successful = str(data.get("successful", "true")).lower() in {"true", "1", "yes"}
        report.objective_status = data.get("objective_status", "achieved")
        if report.objective_status not in {"achieved", "partial", "not_achieved"}: raise ValueError("Choose the objective outcome.")
        row.status = "outcome_review"
    elif action == "review":
        require_role(user, OWNER)
        if row.status != "outcome_review": raise ValueError("Submit the post-event report first.")
        report = EventReport.query.filter_by(organization_id=user.organization_id, event_id=row.id).one()
        report.management_review = text_value(data, "management_review", True)
        report.reviewed_by_id, row.reviewed_at = user.id, instant()
    elif action == "close":
        require_role(user, OWNER)
        report = EventReport.query.filter_by(organization_id=user.organization_id, event_id=row.id).first()
        if row.status != "outcome_review" or not report or not report.reviewed_by_id: raise ValueError("Complete management review before closing.")
        if event_balance(row) != 0: raise ValueError("Return or account for all unretired funds first.")
        if EventResource.query.filter_by(organization_id=user.organization_id, event_id=row.id, resolved_at=None).count(): raise ValueError("Reconcile all issued resources first.")
        row.status, row.closed_at = "closed", instant()
    elif action == "evidence":
        if row.status == "closed": raise ValueError("Closed event evidence is immutable.")
        if not files.get("evidence"): raise ValueError("Choose a supporting document or photo.")
        save_attachment(app, files["evidence"], user, "event", row.id, "event_evidence")
    else: raise ValueError("Unsupported event action.")
    activity(app, user, row, "event_"+action, row.name+" · "+action.replace("_", " "), "event")
    return row


def event_outcome(user, event):
    from models import SalesInvoice,Customer
    events = [event] + scope(EventPlan.query, EventPlan, user).filter_by(parent_id=event.id).all()
    reports = EventReport.query.filter(EventReport.organization_id == user.organization_id, EventReport.event_id.in_([row.id for row in events])).all()
    invoices=scope(SalesInvoice.query,SalesInvoice,user).filter(SalesInvoice.event_id.in_([row.id for row in events])).all()
    contacts=scope(Customer.query,Customer,user).filter(Customer.event_id.in_([row.id for row in events])).all()
    reported_revenue=sum((row.revenue for row in reports),Decimal(0));invoice_revenue=sum((row.subtotal-row.discount for row in invoices),Decimal(0))
    cost = sum((row.spent for row in events), Decimal(0)); revenue = invoice_revenue if invoices else reported_revenue
    leads = sum(row.leads for row in reports) if reports else len(contacts)
    customers = sum(row.customers for row in reports) if reports else sum(c.stage in {'customer','repeat_customer'} for c in contacts)
    return dict(cost=cost, revenue=revenue, reach=sum(row.reach for row in reports), leads=leads, customers=customers,
        invoice_revenue=invoice_revenue,reported_revenue=reported_revenue,revenue_source='invoices' if invoices else 'outcome report',
        released=sum(row.released-transferred_in(row) for row in events), budget=event.approved,
        unretired=sum(event_balance(row) for row in events), profit=revenue-cost,
        roi=round(float((revenue-cost)/cost*100), 1) if cost else None,
        lead_achievement=round(leads/event.expected_leads*100,1) if event.expected_leads else None,
        customer_achievement=round(customers/event.expected_customers*100,1) if event.expected_customers else None,
        budget_utilization=round(float(cost/event.approved*100),1) if event.approved else None)
