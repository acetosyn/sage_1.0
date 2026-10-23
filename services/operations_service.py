# SERVICE: SAGE Core Operations Engine
# Implements request -> approval -> money-sent -> purchase/evidence -> inventory/finance posting with immutable final confirmation.

import re
from datetime import date, datetime, timedelta, timezone
from core.datetime_utils import as_utc, parse_client_datetime
from decimal import Decimal, InvalidOperation
from sqlalchemy import func
from models import ActivityEvent, AssetItem, AssetMovement, Attachment, CatalogItem, Department, FinanceLedgerEntry, FinancialRecord, FulfillmentLine, InventoryItem, PurchaseFulfillment, PurchaseRequest, RequestFunding, RequestBalanceTransaction, RequestItem, StockMovement, User
from packages.database import db
from services.notification_service import notify_user, record_activity
from services.storage_service import save_attachment
from services.management_service import can_actor_approve_request, ensure_supplier, record_revision

FINANCE_TYPES = {"income", "revenue", "expense", "expenditure", "profit", "loss", "cash_flow", "budget", "receivable", "payable", "asset", "liability", "inventory_value", "payroll", "procurement", "tax", "operating_cost", "forecast", "department_spend"}


def money(value, default="0"):
    try:
        parsed = Decimal(str(value if value not in (None, "") else default)).quantize(Decimal("0.01"))
        if not parsed.is_finite() or parsed < 0: raise ValueError("Enter a valid non-negative amount.")
        return parsed
    except (InvalidOperation, ValueError): raise ValueError("Enter a valid amount.")


def quantity(value, default="1"):
    try:
        result = Decimal(str(value if value not in (None, "") else default)).quantize(Decimal("0.001"))
        if not result.is_finite() or result < 0: raise ValueError("Enter a valid non-negative quantity.")
        return result
    except (InvalidOperation, ValueError): raise ValueError("Enter a valid quantity.")


def next_reference(prefix, model, organization_id, field="reference"):
    """Generate an organization-scoped human reference while keeping the database value globally unique."""
    today = datetime.now(timezone.utc).strftime("%y%m%d"); org_code = str(organization_id or "ORG").replace("-", "")[:6].upper(); pattern = f"{prefix}-{org_code}-{today}-%"
    count = model.query.filter(getattr(model, "organization_id") == organization_id, getattr(model, field).like(pattern)).count() + 1
    return f"{prefix}-{org_code}-{today}-{count:04d}"


# ==========================================================
# REQUEST FUNDING -> MONEY-OUT SYNCHRONIZATION
# The money transfer still occurs outside SAGE. SAGE records the release once in both finance ledgers so dashboards and Expenses show exactly what was sent, when, why and to which request/department.
# ==========================================================

REQUEST_RELEASE_CATEGORY = "Request funding / cash released"
REQUEST_RETURN_CATEGORY = "Request balance returned"


def request_balance_breakdown(request_row):
    """Return the complete accountable funding chain for one request. Internal allocations move existing cash between requests and never create a second organization expense."""
    funding, fulfillment = request_row.funding, request_row.fulfillment; sent = Decimal(funding.amount_sent or 0) if funding else Decimal("0"); actual = Decimal(fulfillment.actual_total or 0) if fulfillment and fulfillment.confirmed_at else Decimal("0")
    incoming = db.session.query(func.coalesce(func.sum(RequestBalanceTransaction.amount), 0)).filter(RequestBalanceTransaction.organization_id == request_row.organization_id, RequestBalanceTransaction.target_request_id == request_row.id, RequestBalanceTransaction.transaction_type == "allocation", RequestBalanceTransaction.status == "posted").scalar() or 0
    outgoing = db.session.query(func.coalesce(func.sum(RequestBalanceTransaction.amount), 0)).filter(RequestBalanceTransaction.organization_id == request_row.organization_id, RequestBalanceTransaction.source_request_id == request_row.id, RequestBalanceTransaction.transaction_type == "allocation", RequestBalanceTransaction.status == "posted").scalar() or 0
    returned = db.session.query(func.coalesce(func.sum(RequestBalanceTransaction.amount), 0)).filter(RequestBalanceTransaction.organization_id == request_row.organization_id, RequestBalanceTransaction.source_request_id == request_row.id, RequestBalanceTransaction.transaction_type == "return", RequestBalanceTransaction.status == "posted").scalar() or 0
    incoming, outgoing, returned = Decimal(incoming), Decimal(outgoing), Decimal(returned); available_before_purchase = sent + incoming; balance = available_before_purchase - actual - outgoing - returned; owner_needed = max(Decimal(request_row.estimated_total or 0) - incoming, Decimal("0"))
    return {"owner_sent":sent,"inherited":incoming,"available_before_purchase":available_before_purchase,"actual":actual,"allocated_out":outgoing,"returned":returned,"balance":balance,"owner_needed":owner_needed,"reusable":max(balance,Decimal("0")) if fulfillment and fulfillment.confirmed_at else Decimal("0")}


def request_balance(request_row):
    detail = request_balance_breakdown(request_row); return detail["owner_sent"], detail["actual"], detail["balance"]


def balance_sources_for_user(user, exclude_request_id=None):
    """Reusable balances belong to the staff member whose funded request produced them; only confirmed acquisitions can become reusable credit."""
    query = PurchaseRequest.query.filter_by(organization_id=user.organization_id, requester_id=user.id).filter(PurchaseRequest.status.in_(["fulfilled", "verified"]))
    if exclude_request_id: query = query.filter(PurchaseRequest.id != exclude_request_id)
    rows = []
    for request_row in query.order_by(PurchaseRequest.created_at.asc()).all():
        detail = request_balance_breakdown(request_row)
        if detail["reusable"] > 0: rows.append({"request":request_row,"available":detail["reusable"],"detail":detail})
    return rows


def reusable_balance_for_user(user, exclude_request_id=None): return sum((item["available"] for item in balance_sources_for_user(user, exclude_request_id)), Decimal("0"))


def allocate_request_balance(app, user, target_request, amount):
    """Apply the staff member's older confirmed request balances to a new request, oldest balance first. This is an internal transfer, not a new expense."""
    requested = money(amount, "0")
    if requested <= 0: return Decimal("0"), []
    cap = Decimal(target_request.estimated_total or 0); requested = min(requested, cap); available = reusable_balance_for_user(user, target_request.id)
    if requested > available: raise ValueError(f"You only have {user.organization.currency} {available:,.2f} reusable request balance available.")
    remaining, created = requested, []
    for source in balance_sources_for_user(user, target_request.id):
        if remaining <= 0: break
        applied = min(source["available"], remaining); tx = RequestBalanceTransaction(reference=next_reference("BAL", RequestBalanceTransaction, user.organization_id), organization_id=user.organization_id, department_id=target_request.department_id, holder_user_id=user.id, source_request_id=source["request"].id, target_request_id=target_request.id, created_by_id=user.id, transaction_type="allocation", amount=applied, currency=target_request.currency, note=f"Applied to {target_request.reference} · {target_request.title}", status="posted"); db.session.add(tx); created.append(tx); remaining -= applied
    applied_total = requested - remaining
    if applied_total > 0: record_activity(app, user, "request_balance_allocated", "Existing balance applied to request", f"{user.display_name} applied {user.organization.currency} {applied_total:,.2f} of prior request balance to {target_request.reference}. Owner funding required is now {user.organization.currency} {max(cap-applied_total,Decimal('0')):,.2f}.", "request", target_request.id, {"balance_applied":float(applied_total),"gross_request":float(cap),"owner_needed":float(max(cap-applied_total,Decimal('0'))),"source_count":len(created)}, notify_owner=True, email_owner=False, level="info")
    return applied_total, created


def post_balance_return_finance(actor, request_row, transaction):
    """A returned staff balance is an expense recovery: it reduces net expenditure without pretending it is sales/income."""
    description = f"{request_row.reference} · balance returned by {transaction.holder.display_name if transaction.holder else 'staff'} · {request_row.title}"[:255]; now = transaction.created_at or datetime.now(timezone.utc)
    ledger = FinanceLedgerEntry(reference=next_reference("LED", FinanceLedgerEntry, actor.organization_id), organization_id=actor.organization_id, department_id=request_row.department_id, created_by_id=actor.id, entry_type="adjustment", direction="in", category=REQUEST_RETURN_CATEGORY, counterparty=transaction.holder.display_name if transaction.holder else "Staff", description=description, amount=transaction.amount, currency=request_row.currency, payment_method=transaction.payment_method, external_reference=transaction.payment_reference, status="posted", occurred_at=now, posted_at=datetime.now(timezone.utc), source_entity_type="request_balance_return", source_entity_id=transaction.id, notes=transaction.note); db.session.add(ledger)
    db.session.add(FinancialRecord(reference=next_reference("FIN", FinancialRecord, actor.organization_id), organization_id=actor.organization_id, department_id=request_row.department_id, created_by_id=actor.id, record_type="expense_recovery", category=REQUEST_RETURN_CATEGORY, description=description, amount=transaction.amount, currency=request_row.currency, status="posted", source_entity_type="request_balance_return", source_entity_id=transaction.id, occurred_at=now)); return ledger


def return_request_balance(app, actor, request_row, amount, note=None, payment_method=None, payment_reference=None):
    """Record money physically returned to management from a completed request balance."""
    if actor.organization_id != request_row.organization_id: raise PermissionError("This request belongs to another organization.")
    if actor.role not in {"owner","admin","finance"} and actor.id != request_row.requester_id: raise PermissionError("Only the requesting staff member or management can return this request balance.")
    detail = request_balance_breakdown(request_row)
    if not request_row.fulfillment or not request_row.fulfillment.confirmed_at: raise ValueError("Complete the acquisition and submit evidence before returning a remaining balance.")
    value = money(amount, detail["reusable"]);
    if value <= 0: raise ValueError("Enter an amount to return.")
    if value > detail["reusable"]: raise ValueError(f"Return amount exceeds the available balance of {request_row.currency} {detail['reusable']:,.2f}.")
    tx = RequestBalanceTransaction(reference=next_reference("BAL", RequestBalanceTransaction, actor.organization_id), organization_id=actor.organization_id, department_id=request_row.department_id, holder_user_id=request_row.requester_id, source_request_id=request_row.id, target_request_id=None, created_by_id=actor.id, transaction_type="return", amount=value, currency=request_row.currency, payment_method=(str(payment_method or "").strip() or None), payment_reference=(str(payment_reference or "").strip() or None), note=(str(note or "").strip() or f"Balance returned from {request_row.reference}"), status="posted"); db.session.add(tx); db.session.flush(); post_balance_return_finance(actor, request_row, tx); updated = request_balance_breakdown(request_row)
    message = f"{request_row.currency} {value:,.2f} was returned from {request_row.reference}. Remaining reusable balance: {request_row.currency} {updated['reusable']:,.2f}."; record_activity(app, actor, "request_balance_returned", "Request balance returned", message, "request_balance", tx.id, {"request":request_row.reference,"returned":float(value),"remaining":float(updated["reusable"])}, notify_owner=True, email_owner=False, level="success")
    if request_row.requester and request_row.requester.id != actor.id: notify_user(app, request_row.requester, "Balance return recorded", message, "success", "request", request_row.id, email=False)
    db.session.commit(); return tx, updated


def notify_request_team(app, actor, request_row, title, message, level="info", entity_type="request", entity_id=None, requester_email=False, include_actor=False):
    """Push one tenant-safe request event to the requester and active staff in the same department. Management already receives audit alerts, so ordinary team members are the extra audience here."""
    delivered = set(); entity_id = entity_id or request_row.id
    if include_actor and actor and actor.status == "active": notify_user(app, actor, title, message, level, entity_type, entity_id, email=False); delivered.add(actor.id)
    requester = request_row.requester
    if requester and requester.status == "active" and requester.id not in delivered and (include_actor or not actor or requester.id != actor.id): notify_user(app, requester, title, message, level, entity_type, entity_id, email=bool(requester_email)); delivered.add(requester.id)
    if request_row.department_id:
        teammates = User.query.filter_by(organization_id=request_row.organization_id, department_id=request_row.department_id, status="active").all()
        for teammate in teammates:
            if teammate.id in delivered or (actor and teammate.id == actor.id) or teammate.role in {"owner", "admin"}: continue
            notify_user(app, teammate, title, message, level, entity_type, entity_id, email=False); delivered.add(teammate.id)
    return delivered


def sync_request_release_finance(actor, request_row):
    funding, fulfillment = request_row.funding, request_row.fulfillment; detail = request_balance_breakdown(request_row); sent, actual = detail["owner_sent"], detail["actual"]; cash_out = sent if sent > 0 else (actual if actual > 0 and not funding else Decimal("0")); occurred_at = (funding.funded_at if funding else None) or request_row.money_sent_at or (fulfillment.confirmed_at if fulfillment else None) or datetime.now(timezone.utc); department_name = request_row.department.name if request_row.department else "Organization"; requester_name = request_row.requester.display_name if request_row.requester else "Staff"
    parts = [f"Owner released {request_row.currency} {sent:,.2f}"]
    if detail["inherited"] > 0: parts.append(f"balance applied {request_row.currency} {detail['inherited']:,.2f}")
    if actual > 0: parts.append(f"actual purchase {request_row.currency} {actual:,.2f}")
    if detail["allocated_out"] > 0: parts.append(f"reallocated {request_row.currency} {detail['allocated_out']:,.2f}")
    if detail["returned"] > 0: parts.append(f"returned {request_row.currency} {detail['returned']:,.2f}")
    parts.append(f"{'balance' if detail['balance'] >= 0 else 'shortfall'} {request_row.currency} {abs(detail['balance']):,.2f}"); description = f"{request_row.reference} · {request_row.title} · {department_name} · {' · '.join(parts)}"[:300]
    ledger = FinanceLedgerEntry.query.filter_by(organization_id=actor.organization_id, source_entity_type="request", source_entity_id=request_row.id, category=REQUEST_RELEASE_CATEGORY).order_by(FinanceLedgerEntry.created_at.asc()).first(); summary = FinancialRecord.query.filter_by(organization_id=actor.organization_id, source_entity_type="request_or_fulfillment", source_entity_id=request_row.id, category=REQUEST_RELEASE_CATEGORY).order_by(FinancialRecord.created_at.asc()).first()
    if fulfillment:
        for legacy in FinancialRecord.query.filter_by(organization_id=actor.organization_id, source_entity_type="request_or_fulfillment", source_entity_id=fulfillment.id, category="Actual procurement expenditure", status="posted").all(): legacy.status = "void"
    if cash_out <= 0:
        if ledger: ledger.status = "void"
        if summary: summary.status = "void"
        return None
    if not ledger: ledger = FinanceLedgerEntry(reference=next_reference("LED", FinanceLedgerEntry, actor.organization_id), organization_id=actor.organization_id, department_id=request_row.department_id, created_by_id=actor.id, entry_type="expense", direction="out", category=REQUEST_RELEASE_CATEGORY, counterparty=requester_name, description=description, amount=cash_out, currency=request_row.currency, status="posted", occurred_at=occurred_at, posted_at=datetime.now(timezone.utc), source_entity_type="request", source_entity_id=request_row.id); db.session.add(ledger)
    else: ledger.department_id, ledger.entry_type, ledger.direction, ledger.counterparty, ledger.description, ledger.amount, ledger.currency, ledger.payment_method, ledger.external_reference, ledger.status, ledger.occurred_at, ledger.posted_at = request_row.department_id, "expense", "out", requester_name, description, cash_out, request_row.currency, (funding.payment_method if funding else None), (funding.payment_reference if funding else None), "posted", occurred_at, ledger.posted_at or datetime.now(timezone.utc)
    ledger.payment_method = funding.payment_method if funding else ledger.payment_method; ledger.external_reference = funding.payment_reference if funding else ledger.external_reference; ledger.notes = funding.note if funding else ledger.notes
    if not summary: summary = FinancialRecord(reference=next_reference("FIN", FinancialRecord, actor.organization_id), organization_id=actor.organization_id, department_id=request_row.department_id, created_by_id=actor.id, record_type="expense", category=REQUEST_RELEASE_CATEGORY, description=description, amount=cash_out, currency=request_row.currency, status="posted", source_entity_type="request_or_fulfillment", source_entity_id=request_row.id, occurred_at=occurred_at); db.session.add(summary)
    else: summary.department_id, summary.record_type, summary.description, summary.amount, summary.currency, summary.status, summary.occurred_at = request_row.department_id, "expense", description, cash_out, request_row.currency, "posted", occurred_at
    return ledger


def scoped_department(user, requested_department_id=None):
    if user.role in {"owner", "admin", "finance", "procurement"} and requested_department_id:
        department = Department.query.filter_by(id=requested_department_id, organization_id=user.organization_id, is_active=True).first()
    else: department = user.department
    if not department: raise ValueError("A valid department is required for this action.")
    return department


def ensure_catalog_item(user, department, name, category=None, unit="unit"):
    item = CatalogItem.query.filter(func.lower(CatalogItem.name) == name.lower(), CatalogItem.organization_id == user.organization_id, CatalogItem.department_id == department.id).first()
    if item: return item
    item = CatalogItem(organization_id=user.organization_id, department_id=department.id, name=name.strip(), category=(category or "").strip() or None, unit=(unit or "unit").strip(), created_by_id=user.id, is_custom=True)
    db.session.add(item); return item


# ==========================================================
# REQUEST CREATION / OWNER DECISIONS
# ==========================================================

def create_request(app, user, payload):
    department = scoped_department(user, payload.get("department_id")); title = (payload.get("title") or payload.get("item_name") or "").strip(); purpose = (payload.get("purpose") or "").strip()
    if not title: raise ValueError("Request title or item name is required.")
    items = payload.get("items") if isinstance(payload.get("items"), list) else [{"item_name": payload.get("item_name") or title, "category": payload.get("category"), "unit": payload.get("unit") or "unit", "quantity": payload.get("quantity") or 1, "unit_cost": payload.get("unit_cost") or payload.get("estimated_unit_cost") or 0}]
    request_row = PurchaseRequest(reference=next_reference("REQ", PurchaseRequest, user.organization_id), organization_id=user.organization_id, department_id=department.id, requester_id=user.id, title=title, purpose=purpose or None, urgency=(payload.get("urgency") or "normal").strip().lower(), status="draft" if payload.get("save_as_draft") else "submitted", currency=user.organization.currency)
    db.session.add(request_row); db.session.flush(); total = Decimal("0"); item_details = []
    for raw in items:
        name = str(raw.get("item_name") or "").strip()
        if not name: continue
        unit = (raw.get("unit") or "unit").strip(); qty, unit_cost = quantity(raw.get("quantity"), "1"), money(raw.get("unit_cost"), "0"); line_total = (qty * unit_cost).quantize(Decimal("0.01")); total += line_total
        db.session.add(RequestItem(request_id=request_row.id, item_name=name, category=(raw.get("category") or "").strip() or None, unit=unit, quantity=qty, unit_cost=unit_cost, estimated_total=line_total)); ensure_catalog_item(user, department, name, raw.get("category"), unit); item_details.append({"name": name, "quantity": float(qty), "unit": unit, "unit_cost": float(unit_cost), "line_total": float(line_total)})
    if total <= 0: raise ValueError("Add at least one item with a valid estimated amount.")
    request_row.estimated_total = total; request_row.submitted_at = datetime.now(timezone.utc) if request_row.status == "submitted" else None
    balance_requested = money(payload.get("balance_to_apply"), "0") if request_row.status == "submitted" else Decimal("0"); balance_applied, _balance_rows = allocate_request_balance(app, user, request_row, balance_requested) if balance_requested > 0 else (Decimal("0"), []); owner_needed = max(total - balance_applied, Decimal("0")); request_row._balance_applied, request_row._owner_amount_needed = balance_applied, owner_needed
    item_summary = "; ".join(f"{item['name']} — {item['quantity']:g} {item['unit']} × {user.organization.currency} {item['unit_cost']:,.2f}" for item in item_details); title_text = "Request submitted" if request_row.status == "submitted" else "Request saved as draft"; balance_note = f" Existing balance applied: {user.organization.currency} {balance_applied:,.2f}; new owner funding required: {user.organization.currency} {owner_needed:,.2f}." if balance_applied > 0 else ""; description = f"{user.display_name} {'submitted' if request_row.status == 'submitted' else 'saved'} {request_row.reference} for {department.name}: {request_row.title} ({user.organization.currency} {total:,.2f}).{balance_note}{f' Items: {item_summary}.' if item_summary else ''}"
    record_activity(app, user, "request_created", title_text, description, "request", request_row.id, {"reference": request_row.reference, "amount": float(total), "balance_applied": float(balance_applied), "owner_needed": float(owner_needed), "status": request_row.status, "items": item_details}, notify_owner=request_row.status == "submitted", email_owner=request_row.status == "submitted", level="warning" if request_row.status == "submitted" else "info")
    db.session.commit(); return request_row


def decide_request(app, actor, request_row, action, note=None):
    action = (action or "").strip().lower(); now = datetime.now(timezone.utc); note = (note or "").strip() or None; before = {"status":request_row.status,"approved_by_id":request_row.approved_by_id,"money_sent_by_id":request_row.money_sent_by_id,"rejected_by_id":request_row.rejected_by_id,"decision_note":request_row.decision_note}
    if action in {"approve", "reject"}:
        allowed, reason, rule = can_actor_approve_request(actor, request_row)
        if not allowed: raise PermissionError(reason)
    elif actor.organization_id != request_row.organization_id or actor.role not in {"owner", "admin", "finance"}: raise PermissionError("Only Owner/Admin/Finance can record funding or money-sent actions.")
    if action == "approve":
        if request_row.status not in {"submitted"}: raise ValueError("Only submitted requests can be approved.")
        request_row.status, request_row.approved_at, request_row.approved_by_id, request_row.decision_note = "approved", now, actor.id, note
        owner_needed = request_balance_breakdown(request_row)["owner_needed"]
        if not request_row.funding: db.session.add(RequestFunding(request_id=request_row.id, organization_id=actor.organization_id, department_id=request_row.department_id, recorded_by_id=actor.id, approved_budget=owner_needed, amount_sent=0, currency=request_row.currency))
        from services.budget_control_service import sync_request_budget
        sync_request_budget(request_row, actor, amount=owner_needed)
        title, message, level = "Request approved", f"{request_row.reference} for {request_row.title} was approved by {actor.display_name}. Stage 2 acquisition logging is now available; funding can be recorded separately.", "success"
    elif action == "money_sent":
        if request_row.status not in {"approved"}: raise ValueError("Approve the request before recording money sent/granted.")
        request_row.status, request_row.money_sent_at, request_row.money_sent_by_id, request_row.decision_note = "money_sent", now, actor.id, note
        owner_needed = request_balance_breakdown(request_row)["owner_needed"]; funding = request_row.funding or RequestFunding(request_id=request_row.id, organization_id=actor.organization_id, department_id=request_row.department_id, recorded_by_id=actor.id, approved_budget=owner_needed, amount_sent=owner_needed, currency=request_row.currency); funding.amount_sent = funding.amount_sent or owner_needed; funding.funded_at = now; funding.recorded_by_id = actor.id; db.session.add(funding); db.session.flush(); sync_request_release_finance(actor, request_row)
        title, message, level = "Money sent / request granted", f"{request_row.reference}: {request_row.currency} {funding.amount_sent:,.2f} was recorded as released for {request_row.title}. The amount is now visible to the department and in Expenses; Stage 2 can record the actual purchase and remaining balance.", "success"
    elif action == "reject":
        if request_row.status not in {"submitted", "approved"}: raise ValueError("This request cannot be rejected at its current stage.")
        request_row.status, request_row.rejected_at, request_row.rejected_by_id, request_row.decision_note = "rejected", now, actor.id, note
        restored = Decimal("0")
        for tx in RequestBalanceTransaction.query.filter_by(organization_id=request_row.organization_id, target_request_id=request_row.id, transaction_type="allocation", status="posted").all(): restored += Decimal(tx.amount or 0); tx.status = "void"
        if restored > 0: record_activity(app, actor, "request_balance_restored", "Applied balance restored", f"{request_row.reference} was rejected, so {request_row.currency} {restored:,.2f} of inherited request balance was automatically restored to the staff member's earlier request balance.", "request", request_row.id, {"restored_balance":float(restored)}, notify_owner=False, level="info")
        from services.budget_control_service import sync_request_budget
        sync_request_budget(request_row, actor, release=True)
        title, message, level = "Request rejected", f"{request_row.reference} for {request_row.title} was rejected by {actor.display_name}.{(' Note: ' + note) if note else ''}", "danger"
    else: raise ValueError("Unsupported request action.")
    if request_row.requester: notify_user(app, request_row.requester, title, message, level, "request", request_row.id, email=True)
    record_revision(actor, "request", request_row.id, f"request_{action}", before, {"status":request_row.status,"approved_by_id":request_row.approved_by_id,"money_sent_by_id":request_row.money_sent_by_id,"rejected_by_id":request_row.rejected_by_id,"decision_note":request_row.decision_note}, f"{request_row.reference} moved from {before['status']} to {request_row.status}."); record_activity(app, actor, f"request_{action}", title, message, "request", request_row.id, {"reference": request_row.reference, "status": request_row.status, "approval_rule": rule.name if action in {"approve", "reject"} and rule else "default"}, notify_owner=True)
    db.session.commit(); return request_row


def save_request_funding(app, actor, request_row, payload):
    """Record an approved budget and external cash release; any released amount becomes one traceable SAGE expense without pretending SAGE moved the money."""
    if actor.organization_id != request_row.organization_id or actor.role not in {"owner", "admin", "finance"}: raise PermissionError("You do not have permission to record request funding.")
    if request_row.status not in {"approved", "money_sent", "fulfilled", "verified"}: raise ValueError("Approve the request before recording its budget/funding.")
    funding = request_row.funding or RequestFunding(request_id=request_row.id, organization_id=actor.organization_id, department_id=request_row.department_id, recorded_by_id=actor.id, currency=request_row.currency); before = {"request_status":request_row.status,"approved_budget":funding.approved_budget,"amount_sent":funding.amount_sent,"payment_method":funding.payment_method,"payment_reference":funding.payment_reference,"funded_at":funding.funded_at}
    funding.approved_budget = money(payload.get("approved_budget"), request_row.estimated_total); funding.amount_sent = money(payload.get("amount_sent"), funding.amount_sent or 0); funding.payment_method = str(payload.get("payment_method") or "").strip() or None; funding.payment_reference = str(payload.get("payment_reference") or "").strip() or None; funding.note = str(payload.get("note") or "").strip() or None; funding.recorded_by_id = actor.id
    # Management may intentionally release below, equal to, or above the request/budget. SAGE records the exact external-release instant independently from the request date.
    from services.budget_control_service import sync_request_budget
    sync_request_budget(request_row, actor, amount=funding.approved_budget, budget_id=payload.get("budget_id")); now = datetime.now(timezone.utc); release_now = funding.amount_sent > 0
    release_at = parse_client_datetime(payload.get("funded_at"), funding.funded_at or request_row.money_sent_at or now) if release_now else funding.funded_at
    if release_now and release_at > now + timedelta(minutes=5): raise ValueError("Money release date/time cannot be in the future. Record it when the money has actually been sent.")
    if release_now:
        if request_row.status == "approved": request_row.status = "money_sent"
        request_row.money_sent_at, request_row.money_sent_by_id, funding.funded_at = release_at, actor.id, release_at
    db.session.add(funding); db.session.flush(); sync_request_release_finance(actor, request_row); detail = request_balance_breakdown(request_row); sent, actual, balance = detail["owner_sent"], detail["actual"], detail["balance"]; balance_label = "balance" if balance >= 0 else "shortfall"; release_variance = sent - Decimal(request_row.estimated_total or 0)
    release_stamp = funding.funded_at.isoformat() if funding.funded_at else None; description = f"{actor.display_name} updated funding for {request_row.reference}: requested {request_row.currency} {request_row.estimated_total:,.2f}; approved budget {request_row.currency} {funding.approved_budget:,.2f}; owner released {request_row.currency} {sent:,.2f}; release time {release_stamp or 'not released'}; inherited balance {request_row.currency} {detail['inherited']:,.2f}; actual purchase {request_row.currency} {actual:,.2f}; {balance_label} {request_row.currency} {abs(balance):,.2f}."; record_revision(actor, "request_funding", funding.id, "request_funding_updated", before, {"request_status":request_row.status,"approved_budget":funding.approved_budget,"amount_sent":funding.amount_sent,"payment_method":funding.payment_method,"payment_reference":funding.payment_reference,"funded_at":funding.funded_at,"balance_applied":detail["inherited"],"actual_purchase":actual,"balance":balance,"release_variance":release_variance}, description); record_activity(app, actor, "request_funding_updated", "Request funds released" if release_now else "Request budget updated", description, "request", request_row.id, {"reference": request_row.reference, "requested": float(request_row.estimated_total or 0), "approved_budget": float(funding.approved_budget), "amount_sent": float(sent), "funded_at":release_stamp, "balance_applied":float(detail["inherited"]), "actual_purchase": float(actual), "balance": float(balance), "release_variance":float(release_variance), "payment_reference": funding.payment_reference}, notify_owner=False, level="success")
    team_title = "Money released for request" if release_now else "Request budget updated"; team_message = f"{request_row.reference} · {request_row.title}: management {'released' if release_now else 'budgeted'} {request_row.currency} {sent if release_now else funding.approved_budget:,.2f}. Existing balance applied {request_row.currency} {detail['inherited']:,.2f}; current purchase {request_row.currency} {actual:,.2f}; {balance_label} {request_row.currency} {abs(balance):,.2f}."
    notify_request_team(app, actor, request_row, team_title, team_message, "success" if release_now else "info", "request", request_row.id, requester_email=True, include_actor=False)
    notify_user(app, actor, "Funding record saved" if release_now else "Budget record saved", f"{request_row.reference} · {request_row.title}: {request_row.currency} {sent:,.2f} released. SAGE posted the money-out record and updated the request balance.", "success", "request", request_row.id, email=False)
    db.session.commit(); return funding


# ==========================================================
# PURCHASE / ITEM FULFILLMENT
# ==========================================================

def save_fulfillment(app, user, request_row, form, receipt_file=None, item_image_file=None):
    if request_row.organization_id != user.organization_id: raise PermissionError("Request is outside your organization.")
    if user.role not in {"owner", "admin", "finance", "procurement"} and request_row.requester_id != user.id and request_row.department_id != user.department_id: raise PermissionError("You cannot record this acquisition.")
    if request_row.status not in {"approved", "money_sent", "fulfilled"}: raise ValueError("The request must be approved before Stage 2 acquisition details can be recorded.")
    fulfillment = request_row.fulfillment or PurchaseFulfillment(request_id=request_row.id, organization_id=user.organization_id, department_id=request_row.department_id, recorded_by_id=user.id)
    if fulfillment.locked: raise ValueError("This acquisition record has already been submitted and is locked against editing.")
    source_type = (form.get("source_type") or "self_purchase").strip(); fulfillment.source_type = source_type if source_type in {"self_purchase", "received_from_other"} else "self_purchase"; fulfillment.supplied_by = (form.get("supplied_by") or "").strip() or None; fulfillment.supplier_name = (form.get("supplier_name") or "").strip() or None; ensure_supplier(user, fulfillment.supplier_name) if fulfillment.supplier_name else None; fulfillment.notes = (form.get("notes") or "").strip() or None
    if fulfillment.source_type == "received_from_other" and not fulfillment.supplied_by: raise ValueError("Enter or select the staff/person who delivered or supplied the item.")
    purchase_date = (form.get("purchase_date") or "").strip(); fulfillment.purchase_date = date.fromisoformat(purchase_date) if purchase_date else date.today(); finalize = str(form.get("finalize") or "false").lower() in {"1", "true", "yes"}; fulfillment.is_draft = not finalize
    db.session.add(fulfillment); db.session.flush(); delivered_at_raw = str(form.get("delivered_at") or "").strip(); delivered_at = datetime.fromisoformat(delivered_at_raw) if delivered_at_raw else datetime.now(timezone.utc); delivered_at = as_utc(delivered_at)
    actual_total = Decimal("0"); line_rows = []
    for request_item in request_row.items:
        actual_qty = quantity(form.get(f"actual_quantity_{request_item.id}"), request_item.quantity); actual_unit_cost = money(form.get(f"actual_unit_cost_{request_item.id}"), request_item.unit_cost); line_total = (actual_qty * actual_unit_cost).quantize(Decimal("0.01")); actual_total += line_total
        line = FulfillmentLine.query.filter_by(fulfillment_id=fulfillment.id, request_item_id=request_item.id).first() or FulfillmentLine(fulfillment_id=fulfillment.id, request_item_id=request_item.id, item_name=request_item.item_name, unit=request_item.unit, requested_quantity=request_item.quantity, requested_unit_cost=request_item.unit_cost)
        line.actual_quantity, line.actual_unit_cost, line.actual_total, line.delivered_at, line.notes = actual_qty, actual_unit_cost, line_total, delivered_at, str(form.get(f"line_note_{request_item.id}") or "").strip() or None; db.session.add(line); line_rows.append(line)
    fulfillment.actual_total = actual_total if line_rows else money(form.get("actual_total"), request_row.estimated_total)
    if finalize and line_rows and sum(Decimal(line.actual_quantity or 0) for line in line_rows) <= 0: raise ValueError("Enter at least one actual quantity received before final submission.")
    receipt = save_attachment(app, receipt_file, user, "fulfillment", fulfillment.id, "receipts", final=finalize) if receipt_file and receipt_file.filename else None; item_image = save_attachment(app, item_image_file, user, "fulfillment", fulfillment.id, "item_images", final=finalize) if item_image_file and item_image_file.filename else None
    existing_receipt = receipt or Attachment.query.filter(Attachment.organization_id == user.organization_id, Attachment.entity_type == "fulfillment", Attachment.entity_id == fulfillment.id, Attachment.kind == "receipts").order_by(Attachment.created_at.desc()).first()
    if finalize and not existing_receipt: raise ValueError("Upload the receipt/invoice before final submission. Receipt evidence is required for every acquisition record.")
    if finalize:
        fulfillment.confirmed_at, request_row.status = datetime.now(timezone.utc), "fulfilled"
        for evidence in Attachment.query.filter_by(organization_id=user.organization_id, entity_type="fulfillment", entity_id=fulfillment.id).all(): evidence.is_final = True
        record_as = (form.get("record_as") or "stock").strip().lower(); record_as = record_as if record_as in {"stock", "asset"} else "stock"
        if record_as == "asset": post_fulfillment_to_assets(user, request_row, fulfillment, form)
        else: post_fulfillment_to_inventory(user, request_row, fulfillment, form)
        from services.budget_control_service import sync_request_budget
        sync_request_budget(request_row, user, actual=fulfillment.actual_total); sync_request_release_finance(user, request_row)
        funding = request_row.funding; budget = Decimal(funding.approved_budget or request_row.estimated_total) if funding else Decimal(request_row.estimated_total or 0); detail = request_balance_breakdown(request_row); sent, balance = detail["owner_sent"], detail["balance"]; variance = budget - Decimal(fulfillment.actual_total or 0); source_label = user.display_name if fulfillment.source_type == "self_purchase" else (fulfillment.supplied_by or "another staff/person"); balance_label = "balance left" if balance >= 0 else "funding shortfall"
        description = f"{user.display_name} submitted Stage 2 for {request_row.reference}: owner released {user.organization.currency} {sent:,.2f}, inherited balance {user.organization.currency} {detail['inherited']:,.2f}, actual purchase {user.organization.currency} {fulfillment.actual_total:,.2f}, {balance_label} {user.organization.currency} {abs(balance):,.2f}, approved budget {user.organization.currency} {budget:,.2f}; source {source_label}; {len(line_rows)} line item(s); receipt attached{' and item image attached' if item_image else ''}."
        record_activity(app, user, "acquisition_submitted", "Acquisition log submitted", description, "fulfillment", fulfillment.id, {"request": request_row.reference, "actual_total": float(fulfillment.actual_total), "money_sent": float(sent), "balance_applied":float(detail["inherited"]), "funds_available":float(detail["available_before_purchase"]), "balance": float(balance), "budget": float(budget), "variance": float(variance), "receipt": existing_receipt.original_name if existing_receipt else None, "item_image": item_image.original_name if item_image else None, "record_as": record_as}, notify_owner=True, email_owner=True, level="success")
        notify_request_team(app, user, request_row, "Purchase evidence recorded", f"{request_row.reference}: actual purchase {request_row.currency} {fulfillment.actual_total:,.2f}; {balance_label} {request_row.currency} {abs(balance):,.2f}. Receipt evidence has been submitted.", "success", "fulfillment", fulfillment.id, requester_email=True, include_actor=False)
        notify_user(app, user, "Acquisition submitted", f"{request_row.reference}: {request_row.currency} {fulfillment.actual_total:,.2f} recorded; {balance_label} {request_row.currency} {abs(balance):,.2f}. Evidence is locked for management review.", "success", "fulfillment", fulfillment.id, email=False)
    else:
        description = f"{user.display_name} saved a Stage 2 draft for {request_row.reference}." + (f" Receipt uploaded: {receipt.original_name}." if receipt else "") + (f" Item image uploaded: {item_image.original_name}." if item_image else "")
        record_activity(app, user, "acquisition_draft_saved", "Acquisition draft saved", description, "fulfillment", fulfillment.id, {"request": request_row.reference, "actual_total": float(fulfillment.actual_total), "receipt": receipt.original_name if receipt else None, "item_image": item_image.original_name if item_image else None}, notify_owner=True, email_owner=bool(receipt), level="info")
    db.session.commit(); return fulfillment


def verify_fulfillment(app, actor, request_row):
    """Management verification completes the purchase chain after evidence/delivery has been submitted."""
    fulfillment = request_row.fulfillment
    if actor.organization_id != request_row.organization_id or actor.role not in {"owner", "admin", "finance"}: raise PermissionError("Only Owner/Admin/Finance can verify a completed acquisition.")
    if not fulfillment or not fulfillment.confirmed_at: raise ValueError("The acquisition must be completed with receipt evidence before verification.")
    if fulfillment.verified_at: return fulfillment
    before = {"request_status":request_row.status,"verified_at":fulfillment.verified_at,"verified_by_id":fulfillment.verified_by_id}; fulfillment.verified_at, fulfillment.verified_by_id, request_row.status = datetime.now(timezone.utc), actor.id, "verified"
    record_revision(actor, "fulfillment", fulfillment.id, "acquisition_verified", before, {"request_status":request_row.status,"verified_at":fulfillment.verified_at,"verified_by_id":fulfillment.verified_by_id}, f"{request_row.reference} acquisition verified by {actor.display_name}."); record_activity(app, actor, "acquisition_verified", "Acquisition verified", f"{request_row.reference} · {request_row.title} was verified by {actor.display_name} after purchase evidence and delivery were recorded.", "fulfillment", fulfillment.id, {"request":request_row.reference,"actual_total":float(fulfillment.actual_total or 0)}, notify_owner=False, level="success")
    if request_row.requester: notify_user(app, request_row.requester, "Acquisition verified", f"{request_row.reference} has been verified by management.", "success", "fulfillment", fulfillment.id, email=True)
    db.session.commit(); return fulfillment


def post_fulfillment_to_inventory(user, request_row, fulfillment, form=None):
    actual_by_request_item = {line.request_item_id: line for line in fulfillment.lines}
    for requested in request_row.items:
        actual = actual_by_request_item.get(requested.id); qty = Decimal(actual.actual_quantity or 0) if actual else Decimal(requested.quantity or 0); unit_value = Decimal(actual.actual_unit_cost or 0) if actual else Decimal(requested.unit_cost or 0)
        if qty <= 0: continue
        item = InventoryItem.query.filter(func.lower(InventoryItem.name) == requested.item_name.lower(), InventoryItem.organization_id == user.organization_id, InventoryItem.department_id == request_row.department_id).first()
        if not item:
            item = InventoryItem(organization_id=user.organization_id, department_id=request_row.department_id, name=requested.item_name, sku=f"STK-{re.sub(r'[^A-Z0-9]', '', requested.item_name.upper())[:6]}-{InventoryItem.query.filter_by(organization_id=user.organization_id).count()+1:04d}", category=requested.category, unit=requested.unit, quantity=0, unit_value=unit_value, location=((form or {}).get("location") or (request_row.department.name if request_row.department else "Department Store")), added_by_id=user.id); db.session.add(item); db.session.flush()
        old_qty, old_value = Decimal(item.quantity or 0), Decimal(item.unit_value or 0); new_qty = old_qty + qty; item.unit_value = (((old_qty * old_value) + (qty * unit_value)) / new_qty).quantize(Decimal("0.01")) if new_qty > 0 else unit_value; item.quantity = new_qty
        db.session.add(StockMovement(organization_id=user.organization_id, inventory_item_id=item.id, user_id=user.id, movement_type="stock_in", quantity=qty, source=fulfillment.supplier_name or fulfillment.supplied_by or user.display_name, destination=item.location, reason=f"Stage 2 acquisition for {request_row.reference}", reference=request_row.reference))


def next_asset_tag(organization_id):
    """Generate a compact tenant-scoped asset tag without reusing an existing tag after deletions/imports."""
    org_code = str(organization_id or "ORG").replace("-", "")[:6].upper(); index = AssetItem.query.filter_by(organization_id=organization_id).count() + 1
    while AssetItem.query.filter_by(organization_id=organization_id, asset_tag=f"AST-{org_code}-{index:05d}").first(): index += 1
    return f"AST-{org_code}-{index:05d}"


def post_fulfillment_to_assets(user, request_row, fulfillment, form):
    """Convert the actual Stage 2 quantities/costs into the department asset register."""
    location = (form.get("location") or (request_row.department.name if request_row.department else "Department")).strip(); custodian_id = (form.get("custodian_user_id") or "").strip() or None; serial = (form.get("serial_number") or "").strip() or None; condition = (form.get("condition") or "good").strip().lower() or "good"
    if custodian_id and not User.query.filter_by(id=custodian_id, organization_id=user.organization_id).first(): raise ValueError("Choose a valid asset custodian from this organization.")
    actual_by_request_item = {line.request_item_id: line for line in fulfillment.lines}
    for index, requested in enumerate(request_row.items):
        actual = actual_by_request_item.get(requested.id); qty = Decimal(actual.actual_quantity or 0) if actual else Decimal(requested.quantity or 0); unit_value = Decimal(actual.actual_unit_cost or 0) if actual else Decimal(requested.unit_cost or 0)
        if qty <= 0: continue
        asset = AssetItem(organization_id=user.organization_id, department_id=request_row.department_id, custodian_user_id=custodian_id, source_request_id=request_row.id, created_by_id=user.id, name=requested.item_name, category=requested.category, asset_tag=next_asset_tag(user.organization_id), serial_number=serial if index == 0 else None, quantity=qty, unit_value=unit_value, location=location, condition=condition, status="assigned" if custodian_id else "active", acquired_at=fulfillment.purchase_date, notes=f"Created from Stage 2 acquisition {request_row.reference}")
        db.session.add(asset); db.session.flush(); db.session.add(AssetMovement(organization_id=user.organization_id, asset_id=asset.id, user_id=user.id, movement_type="register", quantity=qty, destination_department_id=request_row.department_id, custodian_user_id=custodian_id, destination_location=location, reason=f"Acquired through {request_row.reference}", reference=request_row.reference))


def move_stock(app, user, item, movement_type, qty, destination=None, destination_department=None, reason=None, recipient=None):
    """Post a controlled stock movement; transfers create/update the destination department balance instead of losing stock."""
    movement_type = (movement_type or "").strip().lower(); qty = quantity(qty, "0")
    if item.organization_id != user.organization_id: raise PermissionError("Inventory item is outside your organization.")
    if destination_department and destination_department.organization_id != user.organization_id: raise PermissionError("Destination department is outside your organization.")
    if movement_type not in {"stock_out", "transfer", "return", "write_off", "adjustment_in", "damaged", "lost"}: raise ValueError("Choose a valid stock movement type.")
    if recipient and recipient.organization_id != user.organization_id: raise PermissionError("Recipient is outside your organization.")
    if qty <= 0: raise ValueError("Movement quantity must be greater than zero.")
    current = Decimal(item.quantity or 0); before = {"quantity":current,"department_id":item.department_id,"location":item.location}; subtract = movement_type in {"stock_out", "transfer", "write_off", "damaged", "lost"}
    if subtract and qty > current: raise ValueError("Movement quantity is greater than the available stock.")
    source = item.location; destination_department = destination_department or item.department; destination = (destination or (destination_department.name if destination_department else item.location) or "Department").strip()
    if movement_type == "transfer":
        item.quantity = current - qty; target = InventoryItem.query.filter(func.lower(InventoryItem.name) == item.name.lower(), InventoryItem.organization_id == user.organization_id, InventoryItem.department_id == destination_department.id, InventoryItem.location == destination).first() if destination_department else None
        if not target:
            target = InventoryItem(organization_id=user.organization_id, department_id=destination_department.id if destination_department else item.department_id, name=item.name, sku=f"STK-{re.sub(r'[^A-Z0-9]', '', item.name.upper())[:6]}-{InventoryItem.query.filter_by(organization_id=user.organization_id).count()+1:04d}", category=item.category, unit=item.unit, quantity=0, unit_value=item.unit_value, reorder_level=item.reorder_level, location=destination, added_by_id=user.id); db.session.add(target); db.session.flush()
        target.quantity = Decimal(target.quantity or 0) + qty
    else: item.quantity = current - qty if subtract else current + qty
    movement = StockMovement(organization_id=user.organization_id, inventory_item_id=item.id, user_id=user.id, movement_type=movement_type, quantity=qty, source=source, destination=destination, reason=(reason or "").strip() or None); db.session.add(movement); record_revision(user, "inventory_item", item.id, f"stock_{movement_type}", before, {"quantity":item.quantity,"department_id":item.department_id,"location":item.location}, f"{movement_type.replace('_',' ').title()} {float(qty):g} {item.unit} of {item.name}."); record_activity(app, user, f"stock_{movement_type}", "Stock movement recorded", f"{user.display_name} recorded {movement_type.replace('_',' ')} of {qty:g} {item.unit} {item.name}: {source or '—'} → {destination or '—'}.", "inventory_item", item.id, {"movement_type": movement_type, "quantity": float(qty), "source": source, "destination": destination, "destination_department": destination_department.name if destination_department else None}, notify_owner=True, email_owner=True); db.session.flush()
    if recipient:
        from models import RecordLink
        db.session.add(RecordLink(organization_id=user.organization_id, source_type="stock_movement", source_id=movement.id, target_type="user", target_id=recipient.id, relation="issued_to", created_by_id=user.id))
        notify_user(app, recipient, "Stock issued to you", f"{item.name}: {qty:g} {item.unit}. Open the item history to acknowledge receipt.", "info", "stock_movement", movement.id)
    db.session.commit(); return movement


def move_asset(app, user, asset, movement_type, destination_department=None, destination_location=None, custodian=None, reason=None):
    """Record assignment, transfer, return, maintenance or write-off while preserving full asset history."""
    movement_type = (movement_type or "").strip().lower()
    if asset.organization_id != user.organization_id: raise PermissionError("Asset is outside your organization.")
    if movement_type not in {"assign", "transfer", "return", "maintenance", "write_off", "restore", "damaged", "lost"}: raise ValueError("Choose a valid asset movement type.")
    source_department_id, source_location = asset.department_id, asset.location; before = {"department_id":asset.department_id,"location":asset.location,"custodian_user_id":asset.custodian_user_id,"status":asset.status}
    if destination_department and destination_department.organization_id != user.organization_id: raise PermissionError("Destination department is outside your organization.")
    if custodian and custodian.organization_id != user.organization_id: raise PermissionError("Custodian is outside your organization.")
    if movement_type in {"assign", "transfer"}: asset.department_id = destination_department.id if destination_department else asset.department_id; asset.location = (destination_location or asset.location); asset.custodian_user_id = custodian.id if custodian else asset.custodian_user_id; asset.status = "assigned" if asset.custodian_user_id else "active"
    elif movement_type == "return": asset.custodian_user_id = None; asset.location = destination_location or (asset.department.name if asset.department else asset.location); asset.status = "active"
    elif movement_type == "maintenance": asset.status = "maintenance"; asset.location = destination_location or asset.location
    elif movement_type == "write_off": asset.status = "written_off"
    elif movement_type == "lost": asset.status = "lost"
    elif movement_type == "damaged": asset.status, asset.condition = "maintenance", "damaged"
    elif movement_type == "restore": asset.status = "active"
    movement = AssetMovement(organization_id=user.organization_id, asset_id=asset.id, user_id=user.id, movement_type=movement_type, quantity=asset.quantity, source_department_id=source_department_id, destination_department_id=asset.department_id, custodian_user_id=asset.custodian_user_id, source_location=source_location, destination_location=asset.location, reason=(reason or "").strip() or None)
    db.session.add(movement); record_revision(user, "asset", asset.id, f"asset_{movement_type}", before, {"department_id":asset.department_id,"location":asset.location,"custodian_user_id":asset.custodian_user_id,"status":asset.status}, f"{movement_type.replace('_',' ').title()} asset {asset.asset_tag}."); record_activity(app, user, f"asset_{movement_type}", "Asset movement recorded", f"{user.display_name} recorded {movement_type.replace('_',' ')} for {asset.name} ({asset.asset_tag}): {source_location or '—'} → {asset.location or '—'}.", "asset", asset.id, {"movement_type": movement_type, "asset_tag": asset.asset_tag, "source": source_location, "destination": asset.location}, notify_owner=True, email_owner=True); db.session.commit(); return movement


# ==========================================================
# FINANCE / OWNER DASHBOARD HELPERS
# ==========================================================

def add_financial_record(user, record_type, description, amount, department_id=None, category=None, source_entity_id=None, commit=True):
    if record_type not in FINANCE_TYPES: raise ValueError("Unsupported financial record type.")
    record = FinancialRecord(reference=next_reference("FIN", FinancialRecord, user.organization_id), organization_id=user.organization_id, department_id=department_id or user.department_id, created_by_id=user.id, record_type=record_type, category=category, description=(description or record_type.replace("_", " ").title()).strip(), amount=money(amount), currency=user.organization.currency, status="posted", source_entity_type="request_or_fulfillment" if source_entity_id else None, source_entity_id=source_entity_id)
    db.session.add(record)
    if commit: db.session.commit()
    return record


def finance_summary(organization_id, department_id=None):
    query = db.session.query(FinancialRecord.record_type, func.coalesce(func.sum(FinancialRecord.amount), 0)).filter(FinancialRecord.organization_id == organization_id, FinancialRecord.status == "posted")
    if department_id: query = query.filter(FinancialRecord.department_id == department_id)
    rows = query.group_by(FinancialRecord.record_type).all(); values = {kind: float(total or 0) for kind, total in rows}
    income = values.get("income", 0) + values.get("revenue", 0); gross_expenses = values.get("expense", 0) + values.get("expenditure", 0) + values.get("operating_cost", 0) + values.get("payroll", 0) + values.get("tax", 0); recoveries = values.get("expense_recovery", 0); expenses = gross_expenses - recoveries; values.update({"income_total": income, "gross_expense_total": gross_expenses, "expense_recovery_total": recoveries, "expense_total": expenses, "net": income - expenses})
    return values


def financial_month_series(organization_id, department_id=None):
    """Return current-year monthly series from real posted finance records; no dashboard demo numbers are generated."""
    year = datetime.now(timezone.utc).year; start = datetime(year, 1, 1, tzinfo=timezone.utc); query = FinancialRecord.query.filter(FinancialRecord.organization_id == organization_id, FinancialRecord.status == "posted", FinancialRecord.occurred_at >= start, FinancialRecord.occurred_at < datetime(year + 1, 1, 1, tzinfo=timezone.utc))
    if department_id: query = query.filter(FinancialRecord.department_id == department_id)
    income, expenses = [0.0] * 12, [0.0] * 12
    for row in query.all():
        index = max(0, min(11, (row.occurred_at.month if row.occurred_at else 1) - 1)); amount = float(row.amount or 0)
        if row.record_type in {"income", "revenue"}: income[index] += amount
        if row.record_type in {"expense", "expenditure", "operating_cost", "payroll", "tax"}: expenses[index] += amount
        if row.record_type == "expense_recovery": expenses[index] -= amount
    return {"labels": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], "income": income, "expenses": expenses, "net": [income[i] - expenses[i] for i in range(12)]}



def analytics_context(user):
    """Build analytics only from the signed-in tenant's real records; returns zeros/empty lists when no data exists."""
    org = user.organization_id; organization_wide = user.role in {"owner", "admin", "finance"}; department_id = None if organization_wide else user.department_id; series = financial_month_series(org, department_id); now = datetime.now(timezone.utc); current_index = now.month - 1; previous_index = max(0, current_index - 1); current_income, previous_income = series["income"][current_index], series["income"][previous_index]; current_expense = series["expenses"][current_index]
    income_growth = ((current_income - previous_income) / previous_income * 100.0) if previous_income else None; expense_ratio = (current_expense / current_income * 100.0) if current_income else None
    request_query = PurchaseRequest.query.filter_by(organization_id=org); finance_query = FinancialRecord.query.filter(FinancialRecord.organization_id == org, FinancialRecord.status == "posted")
    if department_id: request_query = request_query.filter(PurchaseRequest.department_id == department_id); finance_query = finance_query.filter(FinancialRecord.department_id == department_id)
    approved = [row for row in request_query.filter(PurchaseRequest.approved_at.isnot(None), PurchaseRequest.submitted_at.isnot(None)).all() if row.approved_at and row.submitted_at]; avg_approval_hours = (sum(max(0.0, (as_utc(row.approved_at) - as_utc(row.submitted_at)).total_seconds()) for row in approved) / len(approved) / 3600) if approved else 0.0
    completed = request_query.filter(PurchaseRequest.status.in_(["fulfilled", "verified"])).all(); completed_ids = [row.fulfillment.id for row in completed if row.fulfillment]; receipt_count = Attachment.query.filter(Attachment.organization_id == org, Attachment.entity_type == "fulfillment", Attachment.entity_id.in_(completed_ids), Attachment.is_final.is_(True)).count() if completed_ids else 0; receipt_compliance = (receipt_count / len(completed_ids) * 100.0) if completed_ids else 0.0
    expense_types = {"expense", "expenditure", "operating_cost", "payroll", "tax"}; category_rows = finance_query.filter(FinancialRecord.record_type.in_(expense_types)).all(); category_totals = {}
    for row in category_rows: category_totals[row.category or row.record_type.replace("_", " ").title()] = category_totals.get(row.category or row.record_type.replace("_", " ").title(), 0.0) + float(row.amount or 0)
    spend_categories = sorted(category_totals.items(), key=lambda item: item[1], reverse=True)[:6]; max_category = max([amount for _, amount in spend_categories], default=0) or 1
    departments = Department.query.filter_by(organization_id=org, is_active=True).order_by(Department.name.asc()).all() if organization_wide else ([user.department] if user.department else []); department_rows = []
    for dept in departments:
        income = db.session.query(func.coalesce(func.sum(FinancialRecord.amount), 0)).filter(FinancialRecord.organization_id == org, FinancialRecord.department_id == dept.id, FinancialRecord.status == "posted", FinancialRecord.record_type.in_(["income", "revenue"])).scalar() or 0; spend = db.session.query(func.coalesce(func.sum(FinancialRecord.amount), 0)).filter(FinancialRecord.organization_id == org, FinancialRecord.department_id == dept.id, FinancialRecord.status == "posted", FinancialRecord.record_type.in_(expense_types)).scalar() or 0; requests = PurchaseRequest.query.filter_by(organization_id=org, department_id=dept.id).count(); department_rows.append({"name": dept.name, "income": float(income), "spend": float(spend), "requests": requests})
    return {"income_growth": income_growth, "expense_ratio": expense_ratio, "receipt_compliance": receipt_compliance, "avg_approval_hours": avg_approval_hours, "spend_categories": [{"name": name, "amount": amount, "percent": (amount / max_category * 100.0) if max_category else 0} for name, amount in spend_categories], "department_rows": department_rows}

def owner_dashboard_context(user):
    org = user.organization_id; organization_wide = user.role in {"owner", "admin", "finance"}; department_id = None if organization_wide else user.department_id; summary = finance_summary(org, department_id if organization_wide or department_id else "__unassigned_staff__"); requests = PurchaseRequest.query.filter_by(organization_id=org).order_by(PurchaseRequest.created_at.desc()).limit(8).all() if organization_wide else PurchaseRequest.query.filter_by(organization_id=org, department_id=department_id).order_by(PurchaseRequest.created_at.desc()).limit(8).all(); activity = ActivityEvent.query.filter_by(organization_id=org).order_by(ActivityEvent.created_at.desc()).limit(10).all() if organization_wide else ActivityEvent.query.filter_by(organization_id=org, department_id=department_id).order_by(ActivityEvent.created_at.desc()).limit(10).all(); inventory = InventoryItem.query.filter_by(organization_id=org).all() if organization_wide else InventoryItem.query.filter_by(organization_id=org, department_id=department_id).all(); pending_query = PurchaseRequest.query.filter_by(organization_id=org, status="submitted") if organization_wide else PurchaseRequest.query.filter_by(organization_id=org, department_id=department_id, status="submitted")
    return {"finance_summary": summary, "finance_chart": financial_month_series(org, department_id if organization_wide or department_id else "__unassigned_staff__"), "inventory_value": sum(item.total_value for item in inventory), "low_stock_count": sum(1 for item in inventory if float(item.quantity or 0) <= float(item.reorder_level or 0)), "pending_request_count": pending_query.count()}
