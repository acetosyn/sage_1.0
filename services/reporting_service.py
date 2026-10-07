# SERVICE: SAGE Phase 6 Reporting & Business Intelligence
# Builds tenant-scoped management KPIs, chart series, exception queues and export rows from real SAGE records only.

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json
from models import AssetItem, BudgetAllocation, FinancePayable, FinanceReceivable, FinancialRecord, InventoryItem, PayrollEntry, PurchaseFulfillment, PurchaseRequest, RequestFunding, TaxEntry

INFLOW_TYPES = {"income", "revenue"}
OUTFLOW_TYPES = {"expense", "expenditure", "operating_cost", "payroll", "tax"}


def _month_start(value): return value.replace(day=1)
def _shift_month(value, delta):
    month_index = value.year * 12 + value.month - 1 + delta; year, month_zero = divmod(month_index, 12); return date(year, month_zero + 1, 1)
def _money(value): return float(value or 0)


def _scoped_query(query, model, user):
    """Keep reporting inside the signed-in organization and, for ordinary staff, their department."""
    query = query.filter(model.organization_id == user.organization_id)
    if user.role not in {"owner", "admin", "finance", "procurement"} and hasattr(model, "department_id") and user.department_id: query = query.filter(model.department_id == user.department_id)
    return query


def reporting_context(user, months=12):
    """Return compact real-data intelligence used by Reports, charts and SAGE AI."""
    today = datetime.now(timezone.utc).date(); current_month = _month_start(today); month_starts = [_shift_month(current_month, i - (months - 1)) for i in range(months)]; oldest = datetime.combine(month_starts[0], datetime.min.time(), tzinfo=timezone.utc)
    financial_rows = _scoped_query(FinancialRecord.query, FinancialRecord, user).filter(FinancialRecord.status == "posted", FinancialRecord.occurred_at >= oldest).order_by(FinancialRecord.occurred_at.asc()).all()

    monthly = {row.strftime("%Y-%m"): {"month": row.strftime("%b %Y"), "income": 0.0, "expenses": 0.0, "net": 0.0} for row in month_starts}; department_rows, category_rows = defaultdict(lambda: {"income": 0.0, "expenses": 0.0}), defaultdict(float)
    income_total = expense_total = 0.0
    for row in financial_rows:
        amount = _money(row.amount); key = row.occurred_at.strftime("%Y-%m") if row.occurred_at else current_month.strftime("%Y-%m"); department = row.department.name if row.department else "Unassigned"; record_type = str(row.record_type or "").lower()
        if record_type in INFLOW_TYPES:
            income_total += amount; department_rows[department]["income"] += amount
            if key in monthly: monthly[key]["income"] += amount
        elif record_type in OUTFLOW_TYPES:
            expense_total += amount; department_rows[department]["expenses"] += amount; category_rows[row.category or "Uncategorized"] += amount
            if key in monthly: monthly[key]["expenses"] += amount
    for item in monthly.values(): item["net"] = item["income"] - item["expenses"]

    department_breakdown = sorted(({"name": name, "income": values["income"], "expenses": values["expenses"], "net": values["income"] - values["expenses"]} for name, values in department_rows.items()), key=lambda item: item["expenses"], reverse=True)
    category_spend = sorted(({"name": name, "amount": amount} for name, amount in category_rows.items()), key=lambda item: item["amount"], reverse=True)[:8]

    inventory = _scoped_query(InventoryItem.query, InventoryItem, user).all(); assets = _scoped_query(AssetItem.query, AssetItem, user).all(); inventory_value = sum(item.total_value for item in inventory); asset_value = sum(item.total_value for item in assets); low_stock = [item for item in inventory if _money(item.reorder_level) > 0 and _money(item.quantity) <= _money(item.reorder_level)]
    requests = _scoped_query(PurchaseRequest.query, PurchaseRequest, user).order_by(PurchaseRequest.created_at.desc()).all(); request_status = defaultdict(int)
    for row in requests: request_status[row.status] += 1

    budgets = _scoped_query(BudgetAllocation.query, BudgetAllocation, user).filter(BudgetAllocation.status == "active").all(); budget_total = sum(row.total_budget for row in budgets); budget_actual = sum(_money(row.actual_spend) for row in budgets); budget_committed = sum(_money(row.committed_amount) for row in budgets); budget_overruns = [row for row in budgets if row.total_budget and (_money(row.actual_spend) + _money(row.committed_amount)) > row.total_budget]
    receivables = _scoped_query(FinanceReceivable.query, FinanceReceivable, user).filter(~FinanceReceivable.status.in_(["paid", "cancelled"])).all(); payables = _scoped_query(FinancePayable.query, FinancePayable, user).filter(~FinancePayable.status.in_(["paid", "cancelled"])).all(); ar_balance = sum(row.balance for row in receivables); ap_balance = sum(row.balance for row in payables); overdue_ar = [row for row in receivables if row.due_date and row.due_date < today and row.balance > 0]; overdue_ap = [row for row in payables if row.due_date and row.due_date < today and row.balance > 0]
    funding_query = RequestFunding.query.filter(RequestFunding.organization_id == user.organization_id); fulfillment_query = PurchaseFulfillment.query.filter(PurchaseFulfillment.organization_id == user.organization_id, PurchaseFulfillment.confirmed_at.isnot(None)); payroll_query = PayrollEntry.query.filter(PayrollEntry.organization_id == user.organization_id); tax_query = TaxEntry.query.filter(TaxEntry.organization_id == user.organization_id)
    if user.role not in {"owner", "admin", "finance", "procurement"} and user.department_id: funding_query = funding_query.filter(RequestFunding.department_id == user.department_id); fulfillment_query = fulfillment_query.filter(PurchaseFulfillment.department_id == user.department_id); payroll_query = payroll_query.filter(PayrollEntry.department_id == user.department_id); tax_query = tax_query.filter(TaxEntry.department_id == user.department_id)
    funding_rows, fulfillment_rows = funding_query.all(), fulfillment_query.all(); procurement_budget = sum(_money(row.approved_budget) for row in funding_rows); procurement_sent = sum(_money(row.amount_sent) for row in funding_rows); procurement_actual = sum(_money(row.actual_total) for row in fulfillment_rows); procurement_variance = procurement_budget - procurement_actual; procurement_overruns = sum(1 for row in fulfillment_rows if row.request and row.request.funding and _money(row.actual_total) > _money(row.request.funding.approved_budget)); payroll_paid = sum(_money(row.net_pay) for row in payroll_query.filter(PayrollEntry.status == "paid").all()); tax_due = sum(_money(row.tax_amount) for row in tax_query.filter(~TaxEntry.status.in_(["paid", "cancelled"])).all())

    exceptions = []
    if low_stock: exceptions.append({"severity": "warning", "title": "Low stock", "detail": f"{len(low_stock)} item(s) are at or below reorder level.", "route": "inventory"})
    if overdue_ar: exceptions.append({"severity": "warning", "title": "Overdue receivables", "detail": f"{len(overdue_ar)} receivable(s) are past due.", "route": "finance"})
    if overdue_ap: exceptions.append({"severity": "danger", "title": "Overdue payables", "detail": f"{len(overdue_ap)} payable(s) are past due.", "route": "finance"})
    if budget_overruns: exceptions.append({"severity": "danger", "title": "Budget pressure", "detail": f"{len(budget_overruns)} active budget(s) have commitments/actuals above allocation.", "route": "finance"})
    money_sent = [row for row in requests if row.status == "money_sent"]
    if money_sent: exceptions.append({"severity": "info", "title": "Awaiting acquisition evidence", "detail": f"{len(money_sent)} funded request(s) still await final acquisition recording.", "route": "fulfillment"})

    return {
        "currency": user.organization.currency, "period_months": months, "income_total": income_total, "expense_total": expense_total, "net": income_total - expense_total,
        "inventory_value": inventory_value, "asset_value": asset_value, "ar_balance": ar_balance, "ap_balance": ap_balance,
        "budget_total": budget_total, "budget_actual": budget_actual, "budget_committed": budget_committed, "budget_available": budget_total - budget_actual - budget_committed,
        "procurement_budget": procurement_budget, "procurement_sent": procurement_sent, "procurement_actual": procurement_actual, "procurement_variance": procurement_variance, "procurement_overrun_count": procurement_overruns, "payroll_paid": payroll_paid, "tax_due": tax_due,
        "monthly": list(monthly.values()), "department_breakdown": department_breakdown[:10], "category_spend": category_spend,
        "request_status": dict(request_status), "exceptions": exceptions, "low_stock_count": len(low_stock), "overdue_ar_count": len(overdue_ar), "overdue_ap_count": len(overdue_ap),
        "budget_overrun_count": len(budget_overruns), "request_count": len(requests), "inventory_count": len(inventory), "asset_count": len(assets),
    }


def report_period_start(period):
    """Resolve management period names to the current calendar period in UTC."""
    period = str(period or "all").strip().lower(); now = datetime.now(timezone.utc)
    if period == "daily": return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "weekly":
        day = now - timedelta(days=now.weekday()); return day.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "monthly": return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "quarterly": return now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "yearly": return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


def _period_filter(query, field, period):
    start = report_period_start(period); return query.filter(field >= start) if start else query


def management_export_rows(user, report_type="summary", period="all"):
    """Return headers + real tenant rows for CSV/XLSX/PDF. All exports obey tenant/department scope and optional current-period filters."""
    from models import ActivityEvent, AssetItem, AuditRevision, BranchDepartment, BranchLocation, Department, DepartmentOperation, FinanceLedgerEntry, StaffReport, Supplier
    report_type = str(report_type or "summary").strip().lower(); period = str(period or "all").strip().lower(); start = report_period_start(period); currency = user.organization.currency
    financial_query = _scoped_query(FinancialRecord.query, FinancialRecord, user).filter(FinancialRecord.status == "posted"); financial_query = _period_filter(financial_query, FinancialRecord.occurred_at, period); financial = financial_query.order_by(FinancialRecord.occurred_at.desc()).all()
    income_rows = [row for row in financial if str(row.record_type or "").lower() in INFLOW_TYPES]; expense_rows = [row for row in financial if str(row.record_type or "").lower() in OUTFLOW_TYPES]

    if report_type == "departments":
        departments = Department.query.filter_by(organization_id=user.organization_id, is_active=True).order_by(Department.name.asc()).all(); headers = ["Department", "Income", "Expenses", "Net", "Period"]
        rows = []
        for department in departments:
            scoped = [row for row in financial if row.department_id == department.id]; income = sum(_money(row.amount) for row in scoped if row.record_type in INFLOW_TYPES); expenses = sum(_money(row.amount) for row in scoped if row.record_type in OUTFLOW_TYPES); rows.append([department.name, f"{income:.2f}", f"{expenses:.2f}", f"{income-expenses:.2f}", period.title()])
    elif report_type == "inventory":
        items = _scoped_query(InventoryItem.query, InventoryItem, user).order_by(InventoryItem.name.asc()).all(); headers = ["Item", "Department", "Quantity", "Unit", "Unit Value", "Total Value", "Reorder Level", "Low Stock", "Location"]
        rows = [[row.name, row.department.name if row.department else "", f"{_money(row.quantity):.3f}", row.unit or "", f"{_money(row.unit_value):.2f}", f"{row.total_value:.2f}", f"{_money(row.reorder_level):.3f}", "Yes" if _money(row.reorder_level) > 0 and _money(row.quantity) <= _money(row.reorder_level) else "No", row.location or ""] for row in items]
    elif report_type in {"requests", "procurement"}:
        query = _scoped_query(PurchaseRequest.query, PurchaseRequest, user); query = _period_filter(query, PurchaseRequest.created_at, period); requests = query.order_by(PurchaseRequest.created_at.desc()).all(); headers = ["Reference", "Created", "Department", "Requester", "Title", "Requested", "Approved", "Actual Spent", "Supplier", "Approved By", "Purchased/Logged By", "Verified By", "Status"]
        rows = [[row.reference, row.created_at.isoformat() if row.created_at else "", row.department.name if row.department else "", row.requester.display_name if row.requester else "", row.title, f"{_money(row.estimated_total):.2f}", f"{_money(row.funding.approved_budget if row.funding else row.estimated_total):.2f}", f"{_money(row.fulfillment.actual_total if row.fulfillment else 0):.2f}", row.fulfillment.supplier_name if row.fulfillment else "", row.approved_by.display_name if row.approved_by else "", row.fulfillment.recorded_by.display_name if row.fulfillment and row.fulfillment.recorded_by else "", row.fulfillment.verified_by.display_name if row.fulfillment and row.fulfillment.verified_by else "", row.status] for row in requests]
    elif report_type == "assets":
        assets = _scoped_query(AssetItem.query, AssetItem, user).order_by(AssetItem.name.asc()).all(); headers = ["Asset", "Tag", "Serial", "Department", "Custodian", "Location", "Condition", "Status", "Quantity", "Unit Value", "Total Value", "Acquired"]
        rows = [[row.name, row.asset_tag or "", row.serial_number or "", row.department.name if row.department else "", row.custodian.display_name if row.custodian else "", row.location or "", row.condition or "", row.status, f"{_money(row.quantity):.3f}", f"{_money(row.unit_value):.2f}", f"{row.total_value:.2f}", row.acquired_at.isoformat() if row.acquired_at else ""] for row in assets]
    elif report_type == "staff":
        query = ActivityEvent.query.filter_by(organization_id=user.organization_id); query = query.filter(ActivityEvent.department_id == user.department_id) if user.role not in {"owner","admin","finance","procurement"} and user.department_id else query; query = _period_filter(query, ActivityEvent.created_at, period); events = query.order_by(ActivityEvent.created_at.desc()).all(); headers = ["Date/Time", "Staff", "Department", "Action", "Title", "Detail", "Entity", "Entity ID"]
        rows = [[row.created_at.isoformat() if row.created_at else "", row.actor.display_name if row.actor else "Former/System User", row.department.name if row.department else "", row.action, row.title, row.description or "", row.entity_type or "", row.entity_id or ""] for row in events]
    elif report_type == "audit":
        query = AuditRevision.query.filter_by(organization_id=user.organization_id); query = _period_filter(query, AuditRevision.created_at, period); revisions = query.order_by(AuditRevision.created_at.desc()).all(); headers = ["Date/Time", "Actor", "Entity", "Entity ID", "Action", "Summary", "Before", "After"]
        rows = [[row.created_at.isoformat() if row.created_at else "", row.actor.display_name if row.actor else "System / Removed User", row.entity_type, row.entity_id, row.action, row.change_summary or "", json.dumps(row.before_json or {}, ensure_ascii=False, default=str), json.dumps(row.after_json or {}, ensure_ascii=False, default=str)] for row in revisions]
    elif report_type == "finance":
        query = _scoped_query(FinanceLedgerEntry.query, FinanceLedgerEntry, user); query = _period_filter(query, FinanceLedgerEntry.occurred_at, period); ledger = query.order_by(FinanceLedgerEntry.occurred_at.desc()).all(); headers = ["Reference", "Date", "Type", "Direction", "Description", "Counterparty", "Department", "Amount", "Currency", "Status", "External Reference"]
        rows = [[row.reference, row.occurred_at.isoformat() if row.occurred_at else "", row.display_type, row.direction, row.description, row.counterparty or "", row.department.name if row.department else "", f"{_money(row.amount):.2f}", row.currency, row.status, row.external_reference or ""] for row in ledger]
    elif report_type in {"income", "expenses", "cash-flow"}:
        source = income_rows if report_type == "income" else (expense_rows if report_type == "expenses" else financial); headers = ["Reference", "Date", "Type", "Category", "Department", "Description", "Amount", "Currency"]
        rows = [[row.reference, row.occurred_at.isoformat() if row.occurred_at else "", row.record_type.replace("_"," ").title(), row.category or "", row.department.name if row.department else "", row.description, f"{_money(row.amount):.2f}", row.currency] for row in source]
    elif report_type == "profit-loss":
        income = sum(_money(row.amount) for row in income_rows); expenses = sum(_money(row.amount) for row in expense_rows); headers = ["Metric", "Value", "Currency", "Period"]; rows = [["Income / Revenue", f"{income:.2f}", currency, period.title()], ["Expenses / Expenditure", f"{expenses:.2f}", currency, period.title()], ["Profit / Loss", f"{income-expenses:.2f}", currency, period.title()]]
    elif report_type == "receivables":
        query = _scoped_query(FinanceReceivable.query, FinanceReceivable, user); query = _period_filter(query, FinanceReceivable.created_at, period); data = query.order_by(FinanceReceivable.created_at.desc()).all(); headers = ["Reference", "Customer", "Invoice", "Created", "Due", "Total", "Received", "Outstanding", "Status"]
        rows = [[row.reference, row.customer_name, row.invoice_number or "", row.created_at.isoformat() if row.created_at else "", row.due_date.isoformat() if row.due_date else "", f"{_money(row.total_amount):.2f}", f"{_money(row.amount_received):.2f}", f"{row.balance:.2f}", row.status] for row in data]
    elif report_type == "payables":
        query = _scoped_query(FinancePayable.query, FinancePayable, user); query = _period_filter(query, FinancePayable.created_at, period); data = query.order_by(FinancePayable.created_at.desc()).all(); headers = ["Reference", "Vendor", "Bill", "Created", "Due", "Total", "Paid", "Outstanding", "Status"]
        rows = [[row.reference, row.vendor_name, row.bill_number or "", row.created_at.isoformat() if row.created_at else "", row.due_date.isoformat() if row.due_date else "", f"{_money(row.total_amount):.2f}", f"{_money(row.amount_paid):.2f}", f"{row.balance:.2f}", row.status] for row in data]
    elif report_type == "suppliers":
        from services.management_service import procurement_management_context
        supplier_rows = procurement_management_context(user)["suppliers"]; headers = ["Supplier", "Purchases", "Total Spent", "Outstanding", "Last Purchase", "Status", "Latest Prices"]
        rows = [[row["name"], row["purchase_count"], f'{row["total_spend"]:.2f}', f'{row["outstanding"]:.2f}', row["last_purchase"].isoformat() if row["last_purchase"] else "", row["status"], "; ".join(f'{item["item"]}: {item["price"]:.2f}/{item["unit"]}' for item in row["prices"])] for row in supplier_rows]
    elif report_type == "branches":
        from services.management_service import branch_comparison_context
        data = branch_comparison_context(user)["branches"]; headers = ["Branch", "Code", "Income", "Expenses", "Profit/Loss", "Budget", "Budget Usage %", "Inventory Value", "Receivables", "Payables"]
        rows = [[row["name"], row["code"], f'{row["income"]:.2f}', f'{row["expenses"]:.2f}', f'{row["net"]:.2f}', f'{row["budget_total"]:.2f}', f'{row["budget_usage"]:.2f}', f'{row["inventory_value"]:.2f}', f'{row["receivables"]:.2f}', f'{row["payables"]:.2f}'] for row in data]
    else:
        income = sum(_money(row.amount) for row in income_rows); expenses = sum(_money(row.amount) for row in expense_rows); inventory = _scoped_query(InventoryItem.query, InventoryItem, user).all(); assets = _scoped_query(AssetItem.query, AssetItem, user).all(); receivables = _scoped_query(FinanceReceivable.query, FinanceReceivable, user).all(); payables = _scoped_query(FinancePayable.query, FinancePayable, user).all(); headers = ["Metric", "Value", "Currency / Unit", "Period"]
        rows = [["Income / Revenue", f"{income:.2f}", currency, period.title()], ["Expenses / Expenditure", f"{expenses:.2f}", currency, period.title()], ["Net Position", f"{income-expenses:.2f}", currency, period.title()], ["Accounts Receivable", f"{sum(row.balance for row in receivables if row.status not in {'paid','cancelled'}):.2f}", currency, "Current"], ["Accounts Payable", f"{sum(row.balance for row in payables if row.status not in {'paid','cancelled'}):.2f}", currency, "Current"], ["Inventory Value", f"{sum(row.total_value for row in inventory):.2f}", currency, "Current"], ["Asset Value", f"{sum(row.total_value for row in assets):.2f}", currency, "Current"]]
    return headers, rows
