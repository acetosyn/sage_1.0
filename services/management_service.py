# SERVICE: SAGE Owner / Management Executive Control
# Builds the CEO-facing financial/operational picture from real tenant records only: today, attention queue, department control and management drill-down.

from datetime import datetime, timezone
from sqlalchemy import func
from core.datetime_utils import as_utc
from packages.database import db
from models import ApprovalRule, BudgetAllocation, Department, FinanceAccount, FinanceLedgerEntry, FinancePayable, FinanceReceivable, FinancialRecord, InventoryItem, PurchaseFulfillment, PurchaseRequest, RequestFunding

INFLOW_TYPES = {"income", "revenue"}; OUTFLOW_TYPES = {"expense", "expenditure", "operating_cost", "payroll", "tax"}

def _money(value): return float(value or 0)
def _priority(rank): return {3: "Urgent", 2: "Attention Required", 1: "Normal"}.get(rank, "Normal")
def _account_balance(account):
    rows = FinanceLedgerEntry.query.filter_by(organization_id=account.organization_id, account_id=account.id).filter(FinanceLedgerEntry.status.in_(["posted", "reconciled"])).all(); balance = _money(account.opening_balance)
    for row in rows: balance += _money(row.amount) if row.direction == "in" else (-_money(row.amount) if row.direction == "out" else 0)
    return balance

def executive_dashboard_context(user):
    """Organization-owner dashboard requested by management; zero/empty values are returned when real records do not exist."""
    org = user.organization_id; now = datetime.now(timezone.utc); today_start = now.replace(hour=0, minute=0, second=0, microsecond=0); financial = FinancialRecord.query.filter_by(organization_id=org, status="posted").all(); today_rows = [row for row in financial if row.occurred_at and as_utc(row.occurred_at) >= today_start]
    today_income = sum(_money(row.amount) for row in today_rows if str(row.record_type or "").lower() in INFLOW_TYPES); today_expenses = sum(_money(row.amount) for row in today_rows if str(row.record_type or "").lower() in OUTFLOW_TYPES)
    accounts = FinanceAccount.query.filter_by(organization_id=org, is_active=True).all(); available_cash = sum(_account_balance(row) for row in accounts)
    pending_approvals = PurchaseRequest.query.filter_by(organization_id=org, status="submitted").count(); new_requests = PurchaseRequest.query.filter(PurchaseRequest.organization_id == org, PurchaseRequest.created_at >= today_start).count()
    receivables = FinanceReceivable.query.filter(FinanceReceivable.organization_id == org, ~FinanceReceivable.status.in_(["paid", "cancelled"])).all(); payables = FinancePayable.query.filter(FinancePayable.organization_id == org, ~FinancePayable.status.in_(["paid", "cancelled"])).all(); receivable_total = sum(row.balance for row in receivables); payable_total = sum(row.balance for row in payables)
    inventory = InventoryItem.query.filter_by(organization_id=org).all(); inventory_value = sum(row.total_value for row in inventory); low_stock = [row for row in inventory if _money(row.reorder_level) > 0 and _money(row.quantity) <= _money(row.reorder_level)]
    budgets = BudgetAllocation.query.filter_by(organization_id=org, status="active").all(); budget_total = sum(row.total_budget for row in budgets); budget_used = sum(_money(row.actual_spend) + _money(row.committed_amount) for row in budgets); budget_usage = (budget_used / budget_total * 100.0) if budget_total else 0.0
    all_income = sum(_money(row.amount) for row in financial if str(row.record_type or "").lower() in INFLOW_TYPES); all_expenses = sum(_money(row.amount) for row in financial if str(row.record_type or "").lower() in OUTFLOW_TYPES)

    departments, department_rows = Department.query.filter_by(organization_id=org, is_active=True).order_by(Department.name.asc()).all(), []
    for department in departments:
        dept_finance = [row for row in financial if row.department_id == department.id]; dept_income = sum(_money(row.amount) for row in dept_finance if str(row.record_type or "").lower() in INFLOW_TYPES); dept_expenses = sum(_money(row.amount) for row in dept_finance if str(row.record_type or "").lower() in OUTFLOW_TYPES)
        dept_requests = PurchaseRequest.query.filter_by(organization_id=org, department_id=department.id).order_by(PurchaseRequest.created_at.desc()).all(); approved = db.session.query(func.coalesce(func.sum(RequestFunding.approved_budget), 0)).filter(RequestFunding.organization_id == org, RequestFunding.department_id == department.id).scalar() or 0; actual = db.session.query(func.coalesce(func.sum(PurchaseFulfillment.actual_total), 0)).filter(PurchaseFulfillment.organization_id == org, PurchaseFulfillment.department_id == department.id, PurchaseFulfillment.confirmed_at.isnot(None)).scalar() or 0
        dept_budgets = [row for row in budgets if row.department_id == department.id]; allocation = sum(row.total_budget for row in dept_budgets); committed = sum(_money(row.committed_amount) for row in dept_budgets); budget_actual = sum(_money(row.actual_spend) for row in dept_budgets); remaining = allocation - committed - budget_actual; used_percent = ((committed + budget_actual) / allocation * 100.0) if allocation else 0.0
        department_rows.append({"id": department.id, "name": department.name, "income": dept_income, "expenses": dept_expenses, "requests": len(dept_requests), "pending": sum(1 for row in dept_requests if row.status == "submitted"), "approved_amount": _money(approved), "actual_spent": _money(actual), "budget": allocation, "committed": committed, "budget_actual": budget_actual, "remaining_budget": remaining, "budget_usage": used_percent, "net": dept_income - dept_expenses, "recent_requests": dept_requests[:3]})

    today = now.date(); overdue_payables = [row for row in payables if row.due_date and row.due_date < today and row.balance > 0]; missing_receipt = PurchaseRequest.query.filter(PurchaseRequest.organization_id == org, PurchaseRequest.status.in_(["money_sent", "approved"])).count(); unverified = PurchaseFulfillment.query.filter(PurchaseFulfillment.organization_id == org, PurchaseFulfillment.confirmed_at.isnot(None), PurchaseFulfillment.verified_at.is_(None)).count(); unreconciled = FinanceLedgerEntry.query.filter(FinanceLedgerEntry.organization_id == org, FinanceLedgerEntry.account_id.isnot(None), FinanceLedgerEntry.status == "posted", FinanceLedgerEntry.direction.in_(["in", "out"])).count()
    attention = []
    def add(rank, title, detail, route, metric=None): attention.append({"rank": rank, "priority": _priority(rank), "title": title, "detail": detail, "route": route, "metric": metric})
    if pending_approvals: add(3, "Pending approvals", f"{pending_approvals} request(s) are waiting for a management decision.", "requests", str(pending_approvals))
    if unreconciled: add(3 if unreconciled >= 10 else 2, "Unreconciled transactions", f"{unreconciled} posted bank/cash transaction(s) still require reconciliation.", "finance", str(unreconciled))
    if missing_receipt: add(2, "Acquisitions awaiting evidence", f"{missing_receipt} approved/funded request(s) still need purchase completion and receipt evidence.", "fulfillment", str(missing_receipt))
    if unverified: add(2, "Unverified acquisitions", f"{unverified} completed acquisition(s) still require verification.", "fulfillment", str(unverified))
    if overdue_payables: add(3, "Overdue supplier payments", f"{len(overdue_payables)} payable(s) are past due with an outstanding balance.", "finance", str(len(overdue_payables)))
    if low_stock: add(2, "Low stock", f"{len(low_stock)} inventory item(s) are at or below reorder level.", "inventory", str(len(low_stock)))
    for row in department_rows:
        if row["budget"] and row["budget_usage"] >= 100: add(3, f"{row['name']} is over budget", f"Budget usage is {row['budget_usage']:.1f}% with {_money(row['remaining_budget']):,.0f} remaining.", "reports", f"{row['budget_usage']:.0f}%")
        elif row["budget"] and row["budget_usage"] >= 85: add(2, f"{row['name']} budget pressure", f"Budget usage has reached {row['budget_usage']:.1f}%.", "reports", f"{row['budget_usage']:.0f}%")
    for alert in management_anomaly_context(user)["alerts"][:4]: add(alert["rank"], alert["title"], alert["detail"], alert["route"], alert.get("metric"))
    attention.sort(key=lambda item: item["rank"], reverse=True)

    return {"currency": user.organization.currency, "today": {"income": today_income, "expenses": today_expenses, "net": today_income - today_expenses, "available_cash": available_cash, "pending_approvals": pending_approvals, "new_requests": new_requests, "outstanding_payments": payable_total}, "executive": {"income": all_income, "expenses": all_expenses, "net": all_income - all_expenses, "receivables": receivable_total, "payables": payable_total, "inventory_value": inventory_value, "pending_approvals": pending_approvals, "budget_usage": budget_usage}, "departments": department_rows, "attention": attention, "attention_count": len(attention), "low_stock_count": len(low_stock), "account_count": len(accounts), "budget_count": len(budgets)}

# ==========================================================
# CEO UPGRADE PHASE 2 — PROCUREMENT TRACEABILITY / SUPPLIERS
# ==========================================================

def _normalized_supplier(name): return " ".join(str(name or "").strip().lower().split())

def ensure_supplier(user, name):
    """Persist a supplier master record the first time a real acquisition names the supplier."""
    from models import Supplier
    normalized = _normalized_supplier(name)
    if not normalized: return None
    row = Supplier.query.filter_by(organization_id=user.organization_id, normalized_name=normalized).first()
    if row: return row
    row = Supplier(organization_id=user.organization_id, name=str(name).strip(), normalized_name=normalized, created_by_id=user.id); db.session.add(row); return row

def procurement_management_context(user):
    """Build end-to-end purchase chain and supplier intelligence from the existing request/funding/evidence/fulfillment/finance records."""
    from models import Attachment, FinancialRecord, FulfillmentLine, Supplier
    org = user.organization_id; requests = PurchaseRequest.query.filter_by(organization_id=org).order_by(PurchaseRequest.created_at.desc()).limit(100).all(); traces = []
    for row in requests:
        fulfillment, funding = row.fulfillment, row.funding; receipt = Attachment.query.filter_by(organization_id=org, entity_type="fulfillment", entity_id=fulfillment.id if fulfillment else "", kind="receipts").order_by(Attachment.created_at.desc()).first() if fulfillment else None; payment = FinanceLedgerEntry.query.filter(FinanceLedgerEntry.organization_id == org, FinanceLedgerEntry.direction == "out", FinanceLedgerEntry.status.in_(["posted", "reconciled"]), FinanceLedgerEntry.source_entity_id.in_([row.id, funding.id if funding else "", fulfillment.id if fulfillment else ""])).first(); delivered_at = max([line.delivered_at for line in fulfillment.lines if line.delivered_at], key=as_utc, default=None) if fulfillment else None
        stages = [{"key":"request","label":"Request","done":True,"at":row.submitted_at or row.created_at},{"key":"approval","label":"Approval","done":bool(row.approved_at),"at":row.approved_at},{"key":"purchase","label":"Purchase","done":bool(fulfillment and fulfillment.confirmed_at),"at":fulfillment.confirmed_at if fulfillment else None},{"key":"receipt","label":"Receipt","done":bool(receipt),"at":receipt.created_at if receipt else None},{"key":"delivery","label":"Delivery","done":bool(delivered_at),"at":delivered_at},{"key":"verification","label":"Verification","done":bool(fulfillment and fulfillment.verified_at),"at":fulfillment.verified_at if fulfillment else None},{"key":"payment","label":"Payment","done":bool(payment or (funding and _money(funding.amount_sent) > 0)),"at":payment.occurred_at if payment else (funding.funded_at if funding else None)}]
        traces.append({"request":row,"fulfillment":fulfillment,"funding":funding,"receipt":receipt,"payment":payment,"delivered_at":delivered_at,"stages":stages,"approved_amount":_money(funding.approved_budget) if funding else _money(row.estimated_total),"actual_spent":_money(fulfillment.actual_total) if fulfillment else 0.0,"supplier":fulfillment.supplier_name if fulfillment else None,"requested_by":row.requester.display_name if row.requester else "Unknown","approved_by":row.approved_by.display_name if row.approved_by else "—","purchased_by":fulfillment.recorded_by.display_name if fulfillment and fulfillment.recorded_by else "—","received_by":(fulfillment.supplied_by if fulfillment and fulfillment.source_type == "received_from_other" and fulfillment.supplied_by else (fulfillment.recorded_by.display_name if fulfillment and fulfillment.recorded_by else "—")),"verified_by":fulfillment.verified_by.display_name if fulfillment and fulfillment.verified_by else "—"})

    fulfillments = PurchaseFulfillment.query.filter(PurchaseFulfillment.organization_id == org, PurchaseFulfillment.confirmed_at.isnot(None)).order_by(PurchaseFulfillment.confirmed_at.desc()).all(); payables = FinancePayable.query.filter(FinancePayable.organization_id == org, ~FinancePayable.status.in_(["paid", "cancelled"])).all(); supplier_master = {row.normalized_name: row for row in Supplier.query.filter_by(organization_id=org).all()}; supplier_names = set(supplier_master.keys()) | {_normalized_supplier(row.supplier_name) for row in fulfillments if _normalized_supplier(row.supplier_name)}; suppliers = []
    for normalized in supplier_names:
        master = supplier_master.get(normalized); purchases = [row for row in fulfillments if _normalized_supplier(row.supplier_name) == normalized]; obligations = [row for row in payables if _normalized_supplier(row.vendor_name) == normalized]; lines = [line for purchase in purchases for line in purchase.lines]; price_map = {}
        for line in lines:
            current = price_map.get(line.item_name)
            if not current or as_utc(line.updated_at or line.created_at) >= as_utc(current["at"]): price_map[line.item_name] = {"item":line.item_name,"price":_money(line.actual_unit_cost),"unit":line.unit,"at":line.updated_at or line.created_at}
        suppliers.append({"id":master.id if master else None,"name":master.name if master else next((row.supplier_name for row in purchases if row.supplier_name), normalized.title()),"status":master.status if master else "historical","purchase_count":len(purchases),"total_spend":sum(_money(row.actual_total) for row in purchases),"outstanding":sum(row.balance for row in obligations),"last_purchase":purchases[0].confirmed_at if purchases else None,"prices":sorted(price_map.values(), key=lambda item:as_utc(item["at"]), reverse=True)[:4]})
    suppliers.sort(key=lambda row: row["total_spend"], reverse=True)
    return {"currency":user.organization.currency,"traces":traces,"suppliers":suppliers,"supplier_count":len(suppliers),"completed_purchase_count":len(fulfillments),"supplier_spend":sum(_money(row.actual_total) for row in fulfillments),"supplier_outstanding":sum(row.balance for row in payables)}

# ==========================================================
# CEO UPGRADE PHASE 3 — BRANCHES / APPROVAL LIMITS / BUDGET CONTROL
# ==========================================================

ROLE_RANK = {"staff":0, "procurement":1, "department_head":1, "finance":2, "admin":3, "owner":4}

def approval_rule_for_amount(organization_id, amount):
    from models import ApprovalRule
    value = _money(amount); rows = ApprovalRule.query.filter_by(organization_id=organization_id, is_active=True).order_by(ApprovalRule.priority.asc(), ApprovalRule.min_amount.desc()).all()
    for row in rows:
        if value >= _money(row.min_amount) and (row.max_amount is None or value <= _money(row.max_amount)): return row
    return None

def can_actor_approve_request(actor, request_row):
    """Enforce configurable thresholds and block requesters from approving their own transaction."""
    if actor.organization_id != request_row.organization_id: return False, "Request is outside your organization.", None
    if actor.id == request_row.requester_id: return False, "A requester cannot approve their own transaction.", approval_rule_for_amount(actor.organization_id, request_row.estimated_total)
    rule = approval_rule_for_amount(actor.organization_id, request_row.estimated_total)
    if not rule:
        configured = ApprovalRule.query.filter_by(organization_id=actor.organization_id, is_active=True).first()
        if configured: return actor.role == "owner", "No configured limit covers this amount; owner approval is required.", None
        return actor.role in {"owner", "admin", "finance"}, "Only Owner/Admin/Finance can approve until approval limits are configured.", None
    required_rank, actor_rank = ROLE_RANK.get(rule.required_role, 4), ROLE_RANK.get(actor.role, 0)
    if actor_rank < required_rank: return False, f"{rule.name} requires {rule.required_role.replace('_',' ').title()} approval for this amount.", rule
    if rule.required_role == "department_head" and actor.role == "department_head" and actor.department_id != request_row.department_id: return False, "Department Heads can approve only requests from their own department.", rule
    return True, f"Approval permitted under {rule.name}.", rule

def create_branch(user, payload):
    from models import BranchLocation
    name = str(payload.get("name") or "").strip(); code = str(payload.get("code") or "").strip().upper(); address = str(payload.get("address") or "").strip() or None
    if not name or not code: raise ValueError("Branch name and code are required.")
    existing = BranchLocation.query.filter_by(organization_id=user.organization_id, code=code).first()
    if existing: existing.name, existing.address, existing.is_active = name, address, True; row = existing
    else: row = BranchLocation(organization_id=user.organization_id, name=name, code=code, address=address, is_head_office=str(payload.get("is_head_office") or "false").lower() in {"1","true","yes"}, created_by_id=user.id); db.session.add(row)
    db.session.flush(); return row

def assign_department_to_branch(user, payload):
    from models import BranchDepartment, BranchLocation
    branch = BranchLocation.query.filter_by(id=payload.get("branch_id"), organization_id=user.organization_id, is_active=True).first(); department = Department.query.filter_by(id=payload.get("department_id"), organization_id=user.organization_id, is_active=True).first()
    if not branch or not department: raise ValueError("Choose a valid branch and department.")
    row = BranchDepartment.query.filter_by(organization_id=user.organization_id, department_id=department.id).first()
    if row: row.branch_id, row.created_by_id = branch.id, user.id
    else: row = BranchDepartment(organization_id=user.organization_id, branch_id=branch.id, department_id=department.id, created_by_id=user.id); db.session.add(row)
    db.session.flush(); return row

def create_approval_rule(user, payload):
    from decimal import Decimal, InvalidOperation
    from models import ApprovalRule
    name = str(payload.get("name") or "").strip(); required_role = str(payload.get("required_role") or "owner").strip().lower()
    if not name: raise ValueError("Approval rule name is required.")
    if required_role not in {"department_head", "finance", "admin", "owner"}: raise ValueError("Choose Department Head, Finance, Admin or Owner as the required approver.")
    try: minimum = Decimal(str(payload.get("min_amount") or 0)).quantize(Decimal("0.01")); maximum = Decimal(str(payload.get("max_amount"))).quantize(Decimal("0.01")) if payload.get("max_amount") not in (None, "") else None
    except (InvalidOperation, ValueError): raise ValueError("Enter valid approval amounts.")
    if not minimum.is_finite() or (maximum is not None and not maximum.is_finite()) or minimum < 0 or (maximum is not None and maximum < minimum): raise ValueError("Enter finite approval amounts; maximum must be blank or greater than/equal to the minimum.")
    row = ApprovalRule(organization_id=user.organization_id, name=name, min_amount=minimum, max_amount=maximum, required_role=required_role, priority=int(payload.get("priority") or 100), created_by_id=user.id); db.session.add(row); db.session.flush(); return row

def management_settings_context(user):
    from models import ApprovalRule, BranchDepartment, BranchLocation
    branches = BranchLocation.query.filter_by(organization_id=user.organization_id, is_active=True).order_by(BranchLocation.is_head_office.desc(), BranchLocation.name.asc()).all(); links = BranchDepartment.query.filter_by(organization_id=user.organization_id).all(); rules = ApprovalRule.query.filter_by(organization_id=user.organization_id, is_active=True).order_by(ApprovalRule.min_amount.asc()).all(); linked = {row.department_id: row.branch_id for row in links}
    return {"branches":branches,"branch_links":links,"rules":rules,"department_branch":linked,"unassigned_departments":[row for row in Department.query.filter_by(organization_id=user.organization_id, is_active=True).order_by(Department.name.asc()).all() if row.id not in linked]}

def branch_comparison_context(user):
    from models import BranchDepartment, BranchLocation
    org = user.organization_id; branches = BranchLocation.query.filter_by(organization_id=org, is_active=True).order_by(BranchLocation.is_head_office.desc(), BranchLocation.name.asc()).all(); links = BranchDepartment.query.filter_by(organization_id=org).all(); link_map = {row.branch_id:[] for row in links}
    for row in links: link_map.setdefault(row.branch_id, []).append(row.department_id)
    output = []
    for branch in branches:
        dept_ids = link_map.get(branch.id, []); departments = Department.query.filter(Department.organization_id == org, Department.id.in_(dept_ids)).order_by(Department.name.asc()).all() if dept_ids else []; finance = FinancialRecord.query.filter(FinancialRecord.organization_id == org, FinancialRecord.department_id.in_(dept_ids), FinancialRecord.status == "posted").all() if dept_ids else []; income = sum(_money(row.amount) for row in finance if row.record_type in INFLOW_TYPES); expenses = sum(_money(row.amount) for row in finance if row.record_type in OUTFLOW_TYPES); budgets = BudgetAllocation.query.filter(BudgetAllocation.organization_id == org, BudgetAllocation.department_id.in_(dept_ids), BudgetAllocation.status == "active").all() if dept_ids else []; budget_total = sum(row.total_budget for row in budgets); budget_used = sum(_money(row.actual_spend) + _money(row.committed_amount) for row in budgets); inventory = InventoryItem.query.filter(InventoryItem.organization_id == org, InventoryItem.department_id.in_(dept_ids)).all() if dept_ids else []; ap = FinancePayable.query.filter(FinancePayable.organization_id == org, FinancePayable.department_id.in_(dept_ids), ~FinancePayable.status.in_(["paid","cancelled"])).all() if dept_ids else []; ar = FinanceReceivable.query.filter(FinanceReceivable.organization_id == org, FinanceReceivable.department_id.in_(dept_ids), ~FinanceReceivable.status.in_(["paid","cancelled"])).all() if dept_ids else []
        dept_rows = []
        for department in departments:
            dept_finance = [row for row in finance if row.department_id == department.id]; recent = sorted(dept_finance, key=lambda row:as_utc(row.occurred_at or row.created_at), reverse=True)[:4]; dept_rows.append({"id":department.id,"name":department.name,"income":sum(_money(row.amount) for row in dept_finance if row.record_type in INFLOW_TYPES),"expenses":sum(_money(row.amount) for row in dept_finance if row.record_type in OUTFLOW_TYPES),"recent":recent})
        output.append({"id":branch.id,"name":branch.name,"code":branch.code,"address":branch.address,"is_head_office":branch.is_head_office,"income":income,"expenses":expenses,"net":income-expenses,"budget_total":budget_total,"budget_usage":(budget_used/budget_total*100.0) if budget_total else 0.0,"inventory_value":sum(row.total_value for row in inventory),"receivables":sum(row.balance for row in ar),"payables":sum(row.balance for row in ap),"departments":dept_rows})
    return {"currency":user.organization.currency,"branches":output,"branch_count":len(output)}

# ==========================================================
# CEO UPGRADE PHASE 4 — IMMUTABLE CHANGE HISTORY / RISK & ANOMALY INTELLIGENCE
# ==========================================================

def _json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)): return value
    if hasattr(value, "isoformat"): return value.isoformat()
    try: return float(value)
    except (TypeError, ValueError): return str(value)

def record_revision(actor, entity_type, entity_id, action, before=None, after=None, summary=None):
    """Append-only before/after snapshot for important business-state changes; callers commit with their parent transaction."""
    from models import AuditRevision
    clean = lambda payload: {str(k): _json_value(v) for k, v in (payload or {}).items()}
    row = AuditRevision(organization_id=actor.organization_id, actor_id=actor.id, entity_type=entity_type, entity_id=str(entity_id), action=action, before_json=clean(before), after_json=clean(after), change_summary=(summary or "").strip() or None); db.session.add(row); return row

def audit_revision_context(user):
    from models import AuditRevision
    rows = AuditRevision.query.filter_by(organization_id=user.organization_id).order_by(AuditRevision.created_at.desc()).limit(150).all(); return {"rows":rows,"count":len(rows)}

def management_anomaly_context(user):
    """Detect management exceptions from real SAGE records; no synthetic risk scores or demo alerts are generated."""
    from collections import Counter, defaultdict
    from datetime import timedelta
    from models import ApprovalRule, Attachment, FinanceLedgerEntry, FulfillmentLine
    org = user.organization_id; now = datetime.now(timezone.utc); alerts = []
    def add(rank, kind, title, detail, route="audit", metric=None): alerts.append({"rank":rank,"priority":_priority(rank),"kind":kind,"title":title,"detail":detail,"route":route,"metric":metric})

    expense_rows = FinancialRecord.query.filter(FinancialRecord.organization_id == org, FinancialRecord.status == "posted", FinancialRecord.record_type.in_(tuple(OUTFLOW_TYPES))).all(); current_start, previous_start = now - timedelta(days=30), now - timedelta(days=60)
    current_spend = sum(_money(row.amount) for row in expense_rows if row.occurred_at and as_utc(row.occurred_at) >= current_start); previous_spend = sum(_money(row.amount) for row in expense_rows if row.occurred_at and previous_start <= as_utc(row.occurred_at) < current_start)
    if previous_spend > 0 and current_spend > previous_spend * 1.5: add(3, "spend_spike", "Spending increased sharply", f"Last 30-day spend is {current_spend:,.2f}, up {((current_spend / previous_spend) - 1) * 100:.1f}% from the previous 30 days.", "analytics", f"+{((current_spend / previous_spend) - 1) * 100:.0f}%")

    receivables = FinanceReceivable.query.filter_by(organization_id=org).all(); payables = FinancePayable.query.filter_by(organization_id=org).all(); invoice_counts = Counter(str(row.invoice_number).strip().lower() for row in receivables if row.invoice_number); bill_counts = Counter(str(row.bill_number).strip().lower() for row in payables if row.bill_number)
    duplicate_invoices = [key for key, count in invoice_counts.items() if count > 1]; duplicate_bills = [key for key, count in bill_counts.items() if count > 1]
    if duplicate_invoices or duplicate_bills: add(3, "duplicate_invoice", "Possible duplicate invoices/bills", f"{len(duplicate_invoices) + len(duplicate_bills)} repeated invoice/bill reference(s) need review.", "finance", str(len(duplicate_invoices) + len(duplicate_bills)))

    ledger = FinanceLedgerEntry.query.filter(FinanceLedgerEntry.organization_id == org, FinanceLedgerEntry.direction == "out", FinanceLedgerEntry.status.in_(["posted", "reconciled"])).all(); payment_refs = Counter(str(row.external_reference).strip().lower() for row in ledger if row.external_reference); duplicate_payments = [key for key, count in payment_refs.items() if count > 1]
    if duplicate_payments: add(3, "duplicate_payment", "Possible duplicate payments", f"{len(duplicate_payments)} outgoing payment reference(s) occur more than once.", "finance", str(len(duplicate_payments)))

    amounts = sorted(_money(row.amount) for row in expense_rows if _money(row.amount) > 0); avg = (sum(amounts) / len(amounts)) if amounts else 0; unusual = [row for row in expense_rows if avg and _money(row.amount) >= avg * 3 and _money(row.amount) > 0]
    if unusual: add(2, "unusual_transaction", "Unusually large transactions", f"{len(unusual)} expense transaction(s) are at least 3× the organization's average recorded expense.", "finance", str(len(unusual)))

    requests = PurchaseRequest.query.filter_by(organization_id=org).all(); self_approved = [row for row in requests if row.requester_id and row.approved_by_id and row.requester_id == row.approved_by_id]
    if self_approved: add(3, "self_approval", "Requester approved own transaction", f"{len(self_approved)} historical request(s) show the same person as requester and approver.", "requests", str(len(self_approved)))
    rules = ApprovalRule.query.filter_by(organization_id=org, is_active=True).all(); role_rank = ROLE_RANK
    above_limit = []
    for row in requests:
        if not row.approved_by_id or not rules: continue
        rule = approval_rule_for_amount(org, row.estimated_total)
        if rule and row.approved_by and role_rank.get(row.approved_by.role, 0) < role_rank.get(rule.required_role, 4): above_limit.append(row)
    if above_limit: add(3, "approval_limit", "Approval-limit exceptions", f"{len(above_limit)} approved request(s) do not meet the currently configured approver level.", "requests", str(len(above_limit)))

    fulfillments = PurchaseFulfillment.query.filter(PurchaseFulfillment.organization_id == org, PurchaseFulfillment.confirmed_at.isnot(None)).all(); fulfillment_ids = [row.id for row in fulfillments]; receipts = set(row.entity_id for row in Attachment.query.filter(Attachment.organization_id == org, Attachment.entity_type == "fulfillment", Attachment.kind == "receipts", Attachment.entity_id.in_(fulfillment_ids)).all()) if fulfillment_ids else set(); missing = [row for row in fulfillments if row.id not in receipts]
    if missing: add(3, "missing_receipt", "Confirmed purchases missing receipts", f"{len(missing)} confirmed acquisition(s) have no receipt/invoice attachment.", "procurement", str(len(missing)))

    supplier_lines = defaultdict(list)
    for line in FulfillmentLine.query.join(PurchaseFulfillment, PurchaseFulfillment.id == FulfillmentLine.fulfillment_id).filter(PurchaseFulfillment.organization_id == org, PurchaseFulfillment.confirmed_at.isnot(None), PurchaseFulfillment.supplier_name.isnot(None)).order_by(FulfillmentLine.delivered_at.asc(), FulfillmentLine.created_at.asc()).all(): supplier_lines[(line.fulfillment.supplier_name.strip().lower(), line.item_name.strip().lower(), line.unit.strip().lower())].append(line)
    from models import DirectPurchaseLine
    from types import SimpleNamespace
    for line in DirectPurchaseLine.query.filter_by(organization_id=org).all():
        if line.ledger.counterparty:
            key=(line.ledger.counterparty.strip().lower(),line.item_name.strip().lower(),line.unit.strip().lower())
            supplier_lines[key].append(SimpleNamespace(actual_unit_cost=line.unit_cost,delivered_at=line.ledger.occurred_at,created_at=line.created_at))
    for lines in supplier_lines.values(): lines.sort(key=lambda line:as_utc(line.delivered_at or line.created_at))
    price_rises = []
    for key, lines in supplier_lines.items():
        if len(lines) < 2: continue
        previous, latest = _money(lines[-2].actual_unit_cost), _money(lines[-1].actual_unit_cost)
        if previous > 0 and latest > previous * 1.15: price_rises.append((key, previous, latest))
    if price_rises: add(2, "supplier_price", "Supplier price increases", f"{len(price_rises)} supplier/item price(s) increased by more than 15% compared with the previous recorded purchase.", "procurement", str(len(price_rises)))

    alerts.sort(key=lambda row: row["rank"], reverse=True); return {"alerts":alerts,"count":len(alerts),"urgent_count":sum(1 for row in alerts if row["rank"] == 3),"current_30_spend":current_spend,"previous_30_spend":previous_spend}
