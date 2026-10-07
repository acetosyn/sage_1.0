# SERVICE: SAGE Workspace Modes / Individual Business Intelligence
# Keeps organization workspaces and individual/entrepreneur workspaces distinct while reusing the same secure finance, inventory, asset and reporting engines.

from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from models import AssetItem, FinancePayable, FinanceReceivable, FinancialRecord, InventoryItem, OrganizationWorkspace, PurchaseRequest
from packages.database import db

INFLOW_TYPES = {"income", "revenue"}
OUTFLOW_TYPES = {"expense", "expenditure", "operating_cost", "payroll", "tax"}


def workspace_record(organization_id): return OrganizationWorkspace.query.filter_by(organization_id=organization_id).first()
def workspace_mode(organization): return getattr(getattr(organization, "workspace_profile", None), "workspace_mode", None) or "organization"
def workspace_profile_context(organization):
    row = getattr(organization, "workspace_profile", None)
    return {"mode": getattr(row, "workspace_mode", None) or "organization", "is_individual": bool(row and row.workspace_mode == "individual"), "business_category_key": getattr(row, "business_category_key", None), "business_category_label": getattr(row, "business_category_label", None) or organization.business_type, "catalog_key": getattr(row, "catalog_key", None), "primary_department_name": getattr(row, "primary_department_name", None)}


def _period_totals(organization_id, start):
    rows = db.session.query(FinancialRecord.record_type, func.coalesce(func.sum(FinancialRecord.amount), 0)).filter(FinancialRecord.organization_id == organization_id, FinancialRecord.status == "posted", FinancialRecord.occurred_at >= start).group_by(FinancialRecord.record_type).all(); values = {kind: float(total or 0) for kind, total in rows}; income = sum(values.get(kind, 0) for kind in INFLOW_TYPES); expenses = sum(values.get(kind, 0) for kind in OUTFLOW_TYPES); return {"income": income, "expenses": expenses, "net": income - expenses}


def individual_dashboard_context(user):
    """Owner-focused business pulse for a sole trader/entrepreneur; all values come from real SAGE records."""
    now = datetime.now(timezone.utc); today_start = now.replace(hour=0, minute=0, second=0, microsecond=0); week_start = today_start - timedelta(days=today_start.weekday()); month_start = today_start.replace(day=1); year_start = today_start.replace(month=1, day=1)
    periods = {"today": _period_totals(user.organization_id, today_start), "week": _period_totals(user.organization_id, week_start), "month": _period_totals(user.organization_id, month_start), "year": _period_totals(user.organization_id, year_start)}
    inventory = InventoryItem.query.filter_by(organization_id=user.organization_id).order_by(InventoryItem.updated_at.desc()).all(); assets = AssetItem.query.filter_by(organization_id=user.organization_id).order_by(AssetItem.updated_at.desc()).all(); receivables = FinanceReceivable.query.filter(FinanceReceivable.organization_id == user.organization_id, ~FinanceReceivable.status.in_(["paid", "cancelled"])).all(); payables = FinancePayable.query.filter(FinancePayable.organization_id == user.organization_id, ~FinancePayable.status.in_(["paid", "cancelled"])).all(); recent_finance = FinancialRecord.query.filter_by(organization_id=user.organization_id, status="posted").order_by(FinancialRecord.occurred_at.desc()).limit(8).all(); requests = PurchaseRequest.query.filter_by(organization_id=user.organization_id).order_by(PurchaseRequest.created_at.desc()).limit(6).all()
    month_income, month_expenses = periods["month"]["income"], periods["month"]["expenses"]; margin = ((month_income - month_expenses) / month_income * 100.0) if month_income else 0.0
    return {"periods": periods, "inventory_value": sum(row.total_value for row in inventory), "asset_value": sum(row.total_value for row in assets), "inventory_count": len(inventory), "asset_count": len(assets), "low_stock_count": sum(1 for row in inventory if float(row.reorder_level or 0) > 0 and float(row.quantity or 0) <= float(row.reorder_level or 0)), "receivable_balance": sum(float(row.balance or 0) for row in receivables), "payable_balance": sum(float(row.balance or 0) for row in payables), "profit_margin": margin, "recent_finance": recent_finance, "recent_requests": requests}


def request_management_context(user, requests):
    """Owner request intelligence for structured inbox cards, department summaries and an Excel-like request ledger."""
    rows = list(requests or []); department_map = {}; pending_total = approved_total = 0.0; urgent_count = 0
    for row in rows:
        department = row.department.name if row.department else "Unassigned"; bucket = department_map.setdefault(department, {"name": department, "count": 0, "pending": 0, "approved": 0, "amount": 0.0}); amount = float(row.estimated_total or 0); bucket["count"] += 1; bucket["amount"] += amount
        if row.status == "submitted": bucket["pending"] += 1; pending_total += amount
        if row.status in {"approved", "money_sent", "fulfilled", "verified"}: bucket["approved"] += 1; approved_total += amount
        if str(row.urgency or "").lower() in {"urgent", "critical"}: urgent_count += 1
    department_rows = sorted(department_map.values(), key=lambda item: (item["pending"], item["count"], item["amount"]), reverse=True)
    return {"department_rows": department_rows, "pending_total": pending_total, "approved_total": approved_total, "urgent_count": urgent_count, "request_count": len(rows), "departments_with_requests": len(department_rows), "latest": rows[:8]}
