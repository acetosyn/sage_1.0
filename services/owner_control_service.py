"""Real-record management workspace, financial scope and fifteen extra controls."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import func
from core.datetime_utils import as_utc
from models import (ActivityEvent, AssetItem, AssetMovement, Attachment, AuditRevision,
    BudgetAllocation, BudgetReservation, CustodyAcknowledgment, Department,
    DepartmentOperation, FinanceAccount, FinanceLedgerEntry, FinancePayable,
    FinanceReceivable, FinanceVerification, FinancialRecord, ManagementTask,
    PurchaseFulfillment, PurchaseRequest, RecordLink, RequestFunding, StaffReport,
    StockMovement, Supplier, TaskComment, User, InventoryItem, ApprovalRule, DirectPurchaseLine, ObligationTerms)
from packages.database import db
from services.management_service import branch_comparison_context, management_anomaly_context
from services.notification_service import notify_user, record_activity
from services.period_service import period_bounds, previous_bounds
from services.record_trace_service import describe, get_record

MANAGEMENT = {"owner", "admin", "finance"}
INCOME = {"income", "revenue"}
EXPENSE = {"expense", "expenditure", "operating_cost", "payroll", "tax"}


def number(value): return round(float(value or 0), 2)
def total(rows, field="amount"): return number(sum(Decimal(str(getattr(row, field, 0) or 0)) for row in rows))
def in_period(value, bounds):
    if not value: return bounds[0] is None
    value = as_utc(value)
    return (bounds[0] is None or value >= bounds[0]) and (bounds[1] is None or value < bounds[1])
def scoped(model, user):
    query = model.query.filter_by(organization_id=user.organization_id)
    if user.role not in MANAGEMENT:
        if user.department_id and hasattr(model, "department_id"): query = query.filter(model.department_id == user.department_id)
        elif hasattr(model, "created_by_id"): query = query.filter(model.created_by_id == user.id)
        elif hasattr(model, "user_id"): query = query.filter(model.user_id == user.id)
        elif hasattr(model, "requester_id"): query = query.filter(model.requester_id == user.id)
        else: query = query.filter(False)
    return query


def scoped_finance_summary(user, period="all"):
    bounds = period_bounds(period)
    rows = [row for row in scoped(FinancialRecord, user).filter_by(status="posted").all() if in_period(row.occurred_at, bounds)]
    income, expenses = total([row for row in rows if row.record_type in INCOME]), total([row for row in rows if row.record_type in EXPENSE])
    return {"income": income, "expenses": expenses, "net": number(income - expenses), "period": period,
        "scope": user.organization.name if user.role in MANAGEMENT else user.department.name if user.department else "Your recorded transactions"}


def aging(rows, today, payments, name_field, kind):
    buckets = {key: 0.0 for key in ("Not overdue", "1–30 days", "31–60 days", "61–90 days", "90+ days", "No due date")}
    output = []
    for row in rows:
        if row.status in {"paid", "cancelled"} or row.balance <= 0: continue
        days = max(0, (today - row.due_date).days) if row.due_date else 0
        bucket = "No due date" if not row.due_date else "Not overdue" if days == 0 else "1–30 days" if days <= 30 else "31–60 days" if days <= 60 else "61–90 days" if days <= 90 else "90+ days"
        buckets[bucket] += row.balance
        terms = ObligationTerms.query.filter_by(organization_id=row.organization_id, entity_type=kind, entity_id=row.id).first()
        output.append({"id": row.id, "type": kind, "reference": row.reference, "name": getattr(row, name_field),
            "amount": number(row.total_amount), "balance": number(row.balance), "due_date": row.due_date.isoformat() if row.due_date else None,
            "age_days": max(0, (today - terms.invoice_date).days) if terms else None,
            "invoice_date": terms.invoice_date.isoformat() if terms else None,
            "recorded_days": max(0, (today - as_utc(row.created_at).date()).days), "overdue_days": days,
            "opening_payment": max(0, number(getattr(row,"amount_received",getattr(row,"amount_paid",0))) - total(payments.get(row.id,[]))),
            "status": "overdue" if days else row.status, "bucket": bucket,
            "payments": [describe("finance_ledger", entry) for entry in payments.get(row.id, [])]})
    output.sort(key=lambda row: (row["overdue_days"], row["balance"]), reverse=True)
    return {"rows": output, "total": number(sum(row["balance"] for row in output)), "overdue": number(sum(row["balance"] for row in output if row["overdue_days"])), "buckets": {key: number(value) for key, value in buckets.items()}}


def management_workspace(user, period="monthly"):
    if user.role not in MANAGEMENT: raise PermissionError("Management access is required.")
    org, now = user.organization_id, datetime.now(timezone.utc)
    today, bounds, previous = now.date(), period_bounds(period, now), previous_bounds(period, now)
    all_financial = scoped(FinancialRecord, user).filter_by(status="posted").order_by(FinancialRecord.occurred_at.desc()).all()
    financial = [row for row in all_financial if in_period(row.occurred_at, bounds)]
    previous_financial = [row for row in all_financial if previous[0] is not None and in_period(row.occurred_at, previous)]
    income, expenses = total([row for row in financial if row.record_type in INCOME]), total([row for row in financial if row.record_type in EXPENSE])
    previous_income, previous_expenses = total([row for row in previous_financial if row.record_type in INCOME]), total([row for row in previous_financial if row.record_type in EXPENSE])
    ledger = scoped(FinanceLedgerEntry, user).order_by(FinanceLedgerEntry.occurred_at.desc()).all()
    posted_ledger = [row for row in ledger if row.status in {"posted", "reconciled"}]
    period_ledger = [row for row in posted_ledger if in_period(row.occurred_at, bounds)]
    accounts = FinanceAccount.query.filter_by(organization_id=org, is_active=True).all()
    cash_accounts = [{"id": row.id, "name": row.name, "balance": number(Decimal(row.opening_balance or 0) + sum((Decimal(entry.amount or 0) if entry.direction == "in" else -Decimal(entry.amount or 0) if entry.direction == "out" else Decimal("0") for entry in posted_ledger if entry.account_id == row.id), Decimal("0")))} for row in accounts]
    available_cash = number(sum(row["balance"] for row in cash_accounts))
    receivables, payables = scoped(FinanceReceivable, user).all(), scoped(FinancePayable, user).all()
    payment_map = defaultdict(list)
    for row in posted_ledger:
        if row.source_entity_type in {"receivable", "payable"}: payment_map[row.source_entity_id].append(row)
    ar, ap = aging(receivables, today, payment_map, "customer_name", "receivable"), aging(payables, today, payment_map, "vendor_name", "payable")
    requests = scoped(PurchaseRequest, user).order_by(PurchaseRequest.created_at.desc()).all()
    fulfillments = scoped(PurchaseFulfillment, user).all()
    completed = [row for row in fulfillments if row.confirmed_at]
    attachments = Attachment.query.filter_by(organization_id=org).all()
    evidence_ids = {row.entity_id for row in attachments}
    receipt_ids = {row.entity_id for row in attachments if row.kind == "receipts"}
    verification_ids = {row.entity_id for row in FinanceVerification.query.filter_by(organization_id=org).all()}
    acknowledgments = CustodyAcknowledgment.query.filter_by(organization_id=org, action="received").all()
    acknowledged_requests = {row.entity_id for row in acknowledgments if row.entity_type == "request"}
    for row in completed:
        if row.verified_at: verification_ids.add(row.id)
    def evidence_for(row):
        return row.id in evidence_ids or (row.source_entity_id in evidence_ids if row.source_entity_id else False)
    expense_rows = [row for row in all_financial if row.record_type in EXPENSE]
    missing_evidence = [row for row in expense_rows if not evidence_for(row)]
    unverified = [row for row in expense_rows if row.id not in verification_ids and row.source_entity_id not in verification_ids]
    inventory, assets = scoped(InventoryItem, user).all(), scoped(AssetItem, user).all()
    stock = StockMovement.query.filter_by(organization_id=org).order_by(StockMovement.created_at.desc()).all()
    moves = AssetMovement.query.filter_by(organization_id=org).order_by(AssetMovement.created_at.desc()).all()
    low_stock = [row for row in inventory if number(row.reorder_level) > 0 and number(row.quantity) <= number(row.reorder_level)]
    budgets = scoped(BudgetAllocation, user).filter_by(status="active").all()
    reservations = BudgetReservation.query.filter_by(organization_id=org).all()
    reserved_ids = {row.request_id for row in reservations if row.status != "released"}
    budget_rows = [{"id": row.id, "name": row.name, "department": row.department.name if row.department else "Business-wide",
        "budget": row.total_budget, "spent": number(row.actual_spend), "committed": number(row.committed_amount), "remaining": number(row.available_balance),
        "used_percent": number((number(row.actual_spend) + number(row.committed_amount)) / row.total_budget * 100) if row.total_budget else None,
        "period_start": row.period_start.isoformat(), "period_end": row.period_end.isoformat()} for row in budgets]
    departments = []
    for department in Department.query.filter_by(organization_id=org, is_active=True).order_by(Department.name.asc()).all():
        records = [row for row in financial if row.department_id == department.id]
        dept_income, dept_expenses = total([row for row in records if row.record_type in INCOME]), total([row for row in records if row.record_type in EXPENSE])
        dept_requests = [row for row in requests if row.department_id == department.id]
        dept_budgets = [row for row in budgets if row.department_id == department.id]
        departments.append({"id": department.id, "name": department.name, "income": dept_income, "expenses": dept_expenses, "net": number(dept_income - dept_expenses),
            "margin_percent": number((dept_income - dept_expenses) / dept_income * 100) if dept_income else None,
            "requests": len(dept_requests), "approved": number(sum(number(row.funding.approved_budget if row.funding else row.estimated_total) for row in dept_requests if row.approved_at)),
            "actual_spent": total([row for row in completed if row.department_id == department.id], "actual_total"),
            "budget": number(sum(row.total_budget for row in dept_budgets)), "remaining_budget": number(sum(row.available_balance for row in dept_budgets)),
            "transactions": [describe("financial_record", row) for row in records]})
    funding = RequestFunding.query.filter_by(organization_id=org).all()
    represented_funding = defaultdict(float)
    for row in posted_ledger:
        if row.source_entity_type == "request_funding": represented_funding[row.source_entity_id] += number(row.amount) if row.direction == "out" else -number(row.amount) if row.direction == "in" else 0
    historical_funding = [{"type": "request_funding", "id": row.id, "reference": row.request.reference, "title": "Recorded purchase disbursement", "amount": max(0, number(row.amount_sent) - represented_funding[row.id]), "currency": row.currency, "direction": "out", "date": as_utc(row.funded_at).isoformat() if row.funded_at else None, "actor": row.recorded_by.display_name if row.recorded_by else None} for row in funding if row.amount_sent and in_period(row.funded_at, bounds) and number(row.amount_sent) > represented_funding[row.id]]
    historical_cash_out = sum(row["amount"] for row in historical_funding)
    cash_in, cash_out = total([row for row in period_ledger if row.direction == "in"]), total([row for row in period_ledger if row.direction == "out"]) + historical_cash_out
    stale_requests = [row for row in requests if row.status == "submitted" and row.submitted_at and (now - as_utc(row.submitted_at)).total_seconds() >= 48 * 3600]
    cycles = [(as_utc(row.verified_at) - as_utc(row.request.submitted_at)).total_seconds() / 86400 for row in completed if row.verified_at and row.request.submitted_at and as_utc(row.verified_at) >= as_utc(row.request.submitted_at)]
    supplier_totals, supplier_history, prices = defaultdict(float), defaultdict(list), defaultdict(list)
    for row in completed:
        name = (row.supplier_name or row.supplied_by or "").strip()
        if not name: continue
        key = " ".join(name.casefold().split())
        supplier_totals[key] += number(row.actual_total)
        supplier_history[key].append({"type": "request", "id": row.request_id, "title": row.request.title, "amount": number(row.actual_total), "date": as_utc(row.confirmed_at).isoformat()})
        prices[key] += [{"item": line.item_name, "price": number(line.actual_unit_cost), "unit": line.unit, "date": as_utc(line.updated_at or line.created_at).isoformat()} for line in row.lines]
    for row in posted_ledger:
        if row.entry_type not in {"expense", "expenditure"} or row.source_entity_type in {"payable", "request_funding", "request"} or not row.counterparty: continue
        key = " ".join(row.counterparty.casefold().split())
        supplier_totals[key] += number(row.amount)
        supplier_history[key].append({"type": "finance_ledger", "id": row.id, "title": row.description, "amount": number(row.amount), "date": as_utc(row.occurred_at).isoformat()})
    for line in DirectPurchaseLine.query.filter_by(organization_id=org).all():
        if line.ledger.counterparty:
            key = " ".join(line.ledger.counterparty.casefold().split())
            prices[key].append({"item":line.item_name,"price":number(line.unit_cost),"unit":line.unit,"date":as_utc(line.created_at).isoformat()})
    supplier_master = {row.normalized_name: row for row in Supplier.query.filter_by(organization_id=org).all()}
    supplier_keys = set(supplier_master) | set(supplier_totals) | {" ".join(row.vendor_name.casefold().split()) for row in payables}
    supplier_total = sum(supplier_totals.values())
    suppliers = [{"name": supplier_master[key].name if key in supplier_master else key.title(), "spend": number(supplier_totals[key]),
        "share_percent": number(supplier_totals[key] / supplier_total * 100) if supplier_total else 0,
        "outstanding": number(sum(row.balance for row in payables if row.status not in {"paid", "cancelled"} and " ".join(row.vendor_name.casefold().split()) == key)),
        "history": sorted(supplier_history[key], key=lambda item: item["date"], reverse=True), "prices": sorted(prices[key], key=lambda item: item["date"], reverse=True)} for key in supplier_keys]
    suppliers.sort(key=lambda row: row["spend"], reverse=True)
    tasks = ManagementTask.query.filter_by(organization_id=org).order_by(ManagementTask.created_at.desc()).all()
    users = User.query.filter_by(organization_id=org).order_by(User.first_name.asc()).all()
    activities = ActivityEvent.query.filter(ActivityEvent.organization_id == org, ActivityEvent.action != "page_view").order_by(ActivityEvent.created_at.desc()).all()
    staff_workload = [{"id": worker.id, "name": worker.display_name, "role": worker.role_label,
        "pending_requests": sum(row.requester_id == worker.id and row.status == "submitted" for row in requests),
        "assigned_tasks": sum(row.assigned_to_id == worker.id and row.status != "completed" for row in tasks),
        "period_actions": sum(row.actor_id == worker.id and in_period(row.created_at, bounds) for row in activities)} for worker in users if worker.status == "active"]
    alerts = []
    def alert(priority, title, count, kind=None, rows=None):
        if count: alerts.append({"priority": priority, "title": title, "count": count, "records": [describe(kind, row) for row in (rows or [])] if kind else []})
    alert("urgent", "Pending approvals", sum(row.status == "submitted" for row in requests), "request", [row for row in requests if row.status == "submitted"])
    alert("attention", "Expenses missing supporting evidence", len(missing_evidence), "financial_record", missing_evidence)
    alert("attention", "Expenses awaiting verification", len(unverified), "financial_record", unverified)
    unreconciled = [row for row in posted_ledger if row.account_id and row.status == "posted" and row.direction in {"in", "out"}]
    alert("attention", "Unreconciled bank / cash transactions", len(unreconciled), "finance_ledger", unreconciled)
    alert("urgent", "Overdue supplier payments", sum(row["overdue_days"] > 0 for row in ap["rows"]), "payable", [row for row in payables if row.balance and row.due_date and row.due_date < today and row.status != "cancelled"])
    alert("attention", "Low-stock items", len(low_stock), "inventory_item", low_stock)
    alert("attention", "Approvals waiting more than 48 hours", len(stale_requests), "request", stale_requests)
    alert("attention", "Deliveries awaiting named recipient acknowledgment", sum(row.request_id not in acknowledged_requests for row in completed), "request", [row.request for row in completed if row.request_id not in acknowledged_requests])
    active_tasks = [row for row in tasks if row.status != "completed" and (not row.snoozed_until or row.snoozed_until <= today)]
    for priority in ("urgent", "attention", "normal"):
        selected = [row for row in active_tasks if ("urgent" if row.due_date and row.due_date < today else row.priority) == priority]
        if selected: alerts.append({"priority":priority,"title":"Management follow-ups due / open","count":len(selected),"detail":"; ".join(row.title for row in selected),"records":[],"section":"tasks"})
    unpaid_purchases = [row.request for row in completed if not (row.request.funding and row.request.funding.amount_sent) and not any(entry.source_entity_type == "request" and entry.source_entity_id == row.request_id and entry.direction == "out" for entry in posted_ledger)]
    alert("attention", "Purchases with no recorded payment or funding", len(unpaid_purchases), "request", unpaid_purchases)
    for row in budget_rows:
        if row["remaining"] < 0: alert("urgent", f"{row['name']} is over budget", 1)
        elif row["used_percent"] is not None and row["used_percent"] >= 85: alert("attention", f"{row['name']} budget usage is {row['used_percent']}%", 1)
    for row in completed:
        approved = number(row.request.funding.approved_budget if row.request.funding else row.request.estimated_total)
        if number(row.actual_total) > approved: alert("urgent", f"{row.request.reference} actual cost exceeds approval by {row.currency if hasattr(row, 'currency') else user.organization.currency} {number(row.actual_total) - approved:,.2f}", 1, "request", [row.request])
    from services.management_service import approval_rule_for_amount, ROLE_RANK
    configured_rules = ApprovalRule.query.filter_by(organization_id=org,is_active=True).first()
    unapproved = []
    for expense in expense_rows:
        if expense.source_entity_type == "request_or_fulfillment" or not expense.created_by: continue
        rule = approval_rule_for_amount(org,expense.amount)
        if rule and ROLE_RANK.get(expense.created_by.role,0) < ROLE_RANK.get(rule.required_role,4): unapproved.append(expense)
        elif configured_rules and not rule and expense.created_by.role != "owner": unapproved.append(expense)
    alert("urgent","Reported expenses above the recorder's approval authority",len(unapproved),"financial_record",unapproved)
    for item in management_anomaly_context(user)["alerts"]:
        alerts.append({"priority": "urgent" if item["rank"] == 3 else "attention", "title": item["title"], "count": item.get("metric") or 1, "detail": item["detail"], "records": []})
    coverage = number(sum(row.id in receipt_ids for row in completed) / len(completed) * 100) if completed else None
    thirty_days = (now - timedelta(days=30), now)
    recent_cash_out = total([row for row in posted_ledger if row.direction == "out" and in_period(row.occurred_at, thirty_days)]) + sum(max(0, number(row.amount_sent) - represented_funding[row.id]) for row in funding if row.amount_sent and in_period(row.funded_at, thirty_days))
    drafts = [describe("finance_ledger", row) for row in ledger if row.status == "draft"] + [describe("fulfillment", row) for row in fulfillments if row.is_draft]
    revisions = AuditRevision.query.filter_by(organization_id=org).order_by(AuditRevision.created_at.desc()).limit(100).all()
    branches = branch_comparison_context(user)["branches"]
    for branch in branches:
        for department in branch["departments"]:
            department_records = [row for row in financial if row.department_id == department["id"]]
            department["income"] = total([row for row in department_records if row.record_type in INCOME])
            department["expenses"] = total([row for row in department_records if row.record_type in EXPENSE])
            department["recent"] = [describe("financial_record", row) for row in department_records]
        branch["income"] = number(sum(row["income"] for row in branch["departments"]))
        branch["expenses"] = number(sum(row["expenses"] for row in branch["departments"]))
        branch["net"] = number(branch["income"] - branch["expenses"])
    return {"period": period, "generated_at": now.isoformat(), "currency": user.organization.currency,
        "totals": {"income": income, "expenses": expenses, "net": number(income - expenses), "available_cash": available_cash, "cash_in": number(cash_in), "cash_out": number(cash_out), "cash_net": number(cash_in - cash_out), "receivables": ar["total"], "payables": ap["total"], "inventory_value": number(sum(row.total_value for row in inventory)), "pending": sum(row.status == "submitted" for row in requests)},
        "comparison": {"income": previous_income, "expenses": previous_expenses, "net": number(previous_income - previous_expenses), "available": previous[0] is not None},
        "cash_movements": [{**describe("finance_ledger", row), "direction": row.direction, "account": row.account.name if row.account else "Unallocated"} for row in period_ledger if row.direction in {"in", "out"}] + historical_funding,
        "approval_rules": [{"id": row.id, "name": row.name, "minimum": number(row.min_amount), "maximum": number(row.max_amount) if row.max_amount is not None else None, "role": row.required_role, "priority": row.priority} for row in ApprovalRule.query.filter_by(organization_id=org, is_active=True).order_by(ApprovalRule.priority.asc()).all()],
        "today": scoped_finance_summary(user, "daily"), "departments": departments,
        "transactions": [describe("financial_record", row) for row in financial], "receivables": ar, "payables": ap,
        "accounts": cash_accounts, "unreconciled": [describe("finance_ledger", row) for row in unreconciled],
        "unallocated_cash": [describe("finance_ledger", row) for row in posted_ledger if not row.account_id and row.direction in {"in", "out"}],
        "inventory": [{"id": row.id, "name": row.name, "quantity": float(row.quantity or 0), "unit": row.unit, "value": number(row.total_value), "location": row.location, "reorder_deficit": max(0, float(row.reorder_level or 0) - float(row.quantity or 0))} for row in inventory],
        "assets": [{**describe("asset", row), "condition": row.condition, "quantity": float(row.quantity or 0), "value": number(row.total_value), "warranty_expiry": row.warranty_expiry.isoformat() if row.warranty_expiry else None} for row in assets],
        "stock_movements": [{"id": row.id, "type": "stock_movement", "item": row.item.name if row.item else "Former item", "movement": row.movement_type, "quantity": float(row.quantity), "actor": row.user.display_name if row.user else "Former user", "date": as_utc(row.created_at).isoformat()} for row in stock[:50]],
        "asset_movements": [describe("asset_movement", row) for row in moves[:50]], "budgets": budget_rows, "alerts": alerts,
        "purchases": [{"id": row.id, "type": "request", "reference": row.reference, "title": row.title, "status": row.status, "approved": number(row.funding.approved_budget if row.funding else row.estimated_total) if row.approved_at else 0, "actual": number(row.fulfillment.actual_total) if row.fulfillment else 0, "supplier": row.fulfillment.supplier_name if row.fulfillment else None, "requester": row.requester.display_name if row.requester else "Former user", "approver": row.approved_by.display_name if row.approved_by else None, "buyer": row.fulfillment.recorded_by.display_name if row.fulfillment and row.fulfillment.recorded_by else None} for row in requests],
        "suppliers": suppliers, "staff": staff_workload, "branches": branches,
        "tasks": [task_dict(row) for row in tasks], "audit": [{"id": row.id, "entity_type": row.entity_type, "entity_id": row.entity_id, "action": row.action, "actor": row.actor.display_name if row.actor else "System / former user", "date": as_utc(row.created_at).isoformat(), "before": row.before_json, "after": row.after_json} for row in revisions],
        "insights": {"evidence_coverage": coverage, "purchase_cycle_days": number(sum(cycles) / len(cycles)) if cycles else None,
            "cash_coverage_days": number(available_cash / (recent_cash_out / 30)) if accounts and recent_cash_out > 0 and available_cash >= 0 else None,
            "due_soon": [row for row in ar["rows"] + ap["rows"] if row["due_date"] and today.isoformat() <= row["due_date"] <= (today + timedelta(days=7)).isoformat()],
            "reorder": [{"id": row.id, "type": "inventory_item", "name": row.name, "deficit": max(0, float(row.reorder_level) - float(row.quantity)), "quantity": float(row.quantity), "unit": row.unit} for row in low_stock],
            "warranties": [{"id": row.id, "type": "asset", "name": row.name, "date": row.warranty_expiry.isoformat()} for row in assets if row.warranty_expiry and today <= row.warranty_expiry <= today + timedelta(days=30)],
            "stale_requests": [describe("request", row) for row in stale_requests], "drafts": drafts,
            "unbudgeted_requests": [describe("request", row) for row in requests if row.status in {"approved", "money_sent"} and row.id not in reserved_ids]},
        "users": [{"id": row.id, "name": row.display_name} for row in users if row.status == "active"]}


def task_dict(row):
    return {"id": row.id, "title": row.title, "notes": row.notes, "priority": row.priority, "status": row.status,
        "assignee": row.assigned_to.display_name if row.assigned_to else "Unassigned", "assigned_to_id": row.assigned_to_id,
        "due_date": row.due_date.isoformat() if row.due_date else None, "snoozed_until": row.snoozed_until.isoformat() if row.snoozed_until else None,
        "entity_type": row.entity_type, "entity_id": row.entity_id,
        "comments": [{"body": item.body, "actor": item.user.display_name, "date": as_utc(item.created_at).isoformat()} for item in TaskComment.query.filter_by(organization_id=row.organization_id, task_id=row.id).order_by(TaskComment.created_at.asc()).all()]}


def save_task(app, user, payload, row=None):
    from datetime import date
    if row and row.organization_id != user.organization_id: raise PermissionError("Task is outside your organization.")
    manager = user.role in MANAGEMENT
    if not manager and (not row or row.assigned_to_id != user.id): raise PermissionError("You can update only your assigned tasks.")
    if row is None:
        title = str(payload.get("title") or "").strip()[:180]
        if not title: raise ValueError("Task title is required.")
        row = ManagementTask(organization_id=user.organization_id, created_by_id=user.id, title=title, status="open", priority="attention")
        db.session.add(row)
    if manager:
        assignee = User.query.filter_by(id=payload.get("assigned_to_id"), organization_id=user.organization_id, status="active").first() if payload.get("assigned_to_id") else None
        if payload.get("assigned_to_id") and not assignee: raise ValueError("Choose an active person in this organization.")
        if "assigned_to_id" in payload: row.assigned_to_id = assignee.id if assignee else None
        if "notes" in payload: row.notes = str(payload.get("notes") or "").strip()[:5000]
        if "priority" in payload:
            if payload["priority"] not in {"urgent", "attention", "normal"}: raise ValueError("Choose a valid priority.")
            row.priority = payload["priority"]
        for field in ("due_date", "snoozed_until"):
            if field in payload: setattr(row, field, date.fromisoformat(payload[field]) if payload[field] else None)
        if payload.get("entity_type") and payload.get("entity_id"):
            get_record(user, payload["entity_type"], payload["entity_id"])
            row.entity_type, row.entity_id = payload["entity_type"], payload["entity_id"]
    if "status" in payload:
        if payload["status"] not in {"open", "in_progress", "completed"}: raise ValueError("Choose a valid task status.")
        row.status = payload["status"]
        row.completed_at = datetime.now(timezone.utc) if row.status == "completed" else None
    db.session.flush()
    comment = str(payload.get("comment") or "").strip()[:5000]
    if comment: db.session.add(TaskComment(organization_id=user.organization_id, task_id=row.id, user_id=user.id, body=comment))
    record_activity(app, user, "management_task_updated", "Management follow-up updated", f"{user.display_name}: {row.title} · {row.status.replace('_', ' ')}.", "management_task", row.id, notify_owner=True)
    if row.assigned_to_id and row.assigned_to_id != user.id:
        notify_user(app, User.query.filter_by(id=row.assigned_to_id, organization_id=user.organization_id).one(), "Your management follow-up", row.title, "warning" if row.priority == "urgent" else "info", "management_task", row.id)
    db.session.commit()
    return row
