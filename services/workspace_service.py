# SERVICE: SAGE Workspace Modes / Individual Business Intelligence
# Keeps organization workspaces and individual/entrepreneur workspaces distinct while reusing the same secure finance, inventory, asset and reporting engines.

from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from models import AssetItem, FinancePayable, FinanceReceivable, FinancialRecord, InventoryItem, OrganizationWorkspace, PurchaseRequest, RequestBalanceTransaction
from packages.database import db
from services.operations_service import request_balance_breakdown

INFLOW_TYPES = {"income", "revenue"}
OUTFLOW_TYPES = {"expense", "expenditure", "operating_cost", "payroll", "tax"}
RECOVERY_TYPES = {"expense_recovery"}


def workspace_record(organization_id): return OrganizationWorkspace.query.filter_by(organization_id=organization_id).first()
def workspace_mode(organization): return getattr(getattr(organization, "workspace_profile", None), "workspace_mode", None) or "organization"
def workspace_profile_context(organization):
    row = getattr(organization, "workspace_profile", None)
    return {"mode": getattr(row, "workspace_mode", None) or "organization", "is_individual": bool(row and row.workspace_mode == "individual"), "business_category_key": getattr(row, "business_category_key", None), "business_category_label": getattr(row, "business_category_label", None) or organization.business_type, "catalog_key": getattr(row, "catalog_key", None), "primary_department_name": getattr(row, "primary_department_name", None)}


def _period_totals(organization_id, start):
    rows = db.session.query(FinancialRecord.record_type, func.coalesce(func.sum(FinancialRecord.amount), 0)).filter(FinancialRecord.organization_id == organization_id, FinancialRecord.status == "posted", FinancialRecord.occurred_at >= start).group_by(FinancialRecord.record_type).all(); values = {kind: float(total or 0) for kind, total in rows}; income = sum(values.get(kind, 0) for kind in INFLOW_TYPES); expenses = sum(values.get(kind, 0) for kind in OUTFLOW_TYPES) - sum(values.get(kind, 0) for kind in RECOVERY_TYPES); return {"income": income, "expenses": expenses, "net": income - expenses}


def individual_dashboard_context(user):
    """Owner-focused business pulse for a sole trader/entrepreneur; all values come from real SAGE records."""
    now = datetime.now(timezone.utc); today_start = now.replace(hour=0, minute=0, second=0, microsecond=0); week_start = today_start - timedelta(days=today_start.weekday()); month_start = today_start.replace(day=1); year_start = today_start.replace(month=1, day=1)
    periods = {"today": _period_totals(user.organization_id, today_start), "week": _period_totals(user.organization_id, week_start), "month": _period_totals(user.organization_id, month_start), "year": _period_totals(user.organization_id, year_start)}
    inventory = InventoryItem.query.filter_by(organization_id=user.organization_id).order_by(InventoryItem.updated_at.desc()).all(); assets = AssetItem.query.filter_by(organization_id=user.organization_id).order_by(AssetItem.updated_at.desc()).all(); receivables = FinanceReceivable.query.filter(FinanceReceivable.organization_id == user.organization_id, ~FinanceReceivable.status.in_(["paid", "cancelled"])).all(); payables = FinancePayable.query.filter(FinancePayable.organization_id == user.organization_id, ~FinancePayable.status.in_(["paid", "cancelled"])).all(); recent_finance = FinancialRecord.query.filter_by(organization_id=user.organization_id, status="posted").order_by(FinancialRecord.occurred_at.desc()).limit(8).all(); requests = PurchaseRequest.query.filter_by(organization_id=user.organization_id).order_by(PurchaseRequest.created_at.desc()).limit(6).all()
    month_income, month_expenses = periods["month"]["income"], periods["month"]["expenses"]; margin = ((month_income - month_expenses) / month_income * 100.0) if month_income else 0.0
    return {"periods": periods, "inventory_value": sum(row.total_value for row in inventory), "asset_value": sum(row.total_value for row in assets), "inventory_count": len(inventory), "asset_count": len(assets), "low_stock_count": sum(1 for row in inventory if float(row.reorder_level or 0) > 0 and float(row.quantity or 0) <= float(row.reorder_level or 0)), "receivable_balance": sum(float(row.balance or 0) for row in receivables), "payable_balance": sum(float(row.balance or 0) for row in payables), "profit_margin": margin, "recent_finance": recent_finance, "recent_requests": requests}


def request_management_context(user, requests):
    """Owner request intelligence including original request value, inherited balances and the net amount still needed from management."""
    rows = list(requests or []); department_map = {}; pending_total = approved_total = gross_total = balance_applied_total = 0.0; urgent_count = 0
    for row in rows:
        detail = request_balance_breakdown(row); department = row.department.name if row.department else "Unassigned"; bucket = department_map.setdefault(department, {"name": department, "count": 0, "pending": 0, "approved": 0, "amount": 0.0, "balance_applied":0.0, "owner_needed":0.0}); amount = float(row.estimated_total or 0); applied = float(detail["inherited"]); owner_needed = max(amount-applied,0.0); bucket["count"] += 1; bucket["amount"] += amount; bucket["balance_applied"] += applied; bucket["owner_needed"] += owner_needed; gross_total += amount; balance_applied_total += applied
        if row.status == "submitted": bucket["pending"] += 1; pending_total += owner_needed
        if row.status in {"approved", "money_sent", "fulfilled", "verified"}: bucket["approved"] += 1; approved_total += amount
        if str(row.urgency or "").lower() in {"urgent", "critical"}: urgent_count += 1
    department_rows = sorted(department_map.values(), key=lambda item: (item["pending"], item["count"], item["owner_needed"]), reverse=True); active = [row for row in rows if row.status in {"submitted", "approved", "money_sent"}]; history = [row for row in rows if row.status in {"fulfilled", "verified", "rejected"}]; history_counts = {"fulfilled":sum(1 for row in history if row.status == "fulfilled"), "verified":sum(1 for row in history if row.status == "verified"), "rejected":sum(1 for row in history if row.status == "rejected")}
    return {"department_rows": department_rows, "pending_total": pending_total, "approved_total": approved_total, "gross_total":gross_total, "balance_applied_total":balance_applied_total, "urgent_count": urgent_count, "request_count": len(rows), "departments_with_requests": len(department_rows), "latest": rows[:8], "active":active, "active_count":len(active), "history":history, "history_count":len(history), "history_counts":history_counts}


def request_funds_context(user, requests):
    """Summarize owner releases, inherited balances, purchases, returns and reusable staff balances without double-counting internal reallocations."""
    rows = list(requests or []); funded = []; total_budget = total_sent = total_actual = total_returned = total_allocated = total_inherited = released_today = spent_today = 0.0; now = datetime.now(timezone.utc); today = now.date(); department_map = {}; staff_map = {}; reusable_total = 0.0
    management = user.role in {"owner","admin","finance","procurement"}
    for row in rows:
        if not management and row.requester_id != user.id: continue
        funding, fulfillment = row.funding, row.fulfillment; detail = request_balance_breakdown(row); actual = float(detail["actual"]); budget = float(funding.approved_budget or 0) if funding else float(row.estimated_total or 0); sent = float(detail["owner_sent"]); inherited = float(detail["inherited"]); allocated_out = float(detail["allocated_out"]); returned = float(detail["returned"]); balance = float(detail["balance"]); reusable = float(detail["reusable"]); total_budget += budget; total_sent += sent; total_actual += actual; total_returned += returned; total_allocated += allocated_out; total_inherited += inherited; reusable_total += reusable
        funded_at = funding.funded_at if funding and funding.funded_at and funding.funded_at.tzinfo else (funding.funded_at.replace(tzinfo=timezone.utc) if funding and funding.funded_at else None); confirmed_at = fulfillment.confirmed_at if fulfillment and fulfillment.confirmed_at and fulfillment.confirmed_at.tzinfo else (fulfillment.confirmed_at.replace(tzinfo=timezone.utc) if fulfillment and fulfillment.confirmed_at else None)
        if funded_at and funded_at.date() == today: released_today += sent
        if confirmed_at and confirmed_at.date() == today: spent_today += actual
        if funding or inherited > 0 or actual > 0:
            item={"request":row,"funding":funding,"budget":budget,"sent":sent,"inherited":inherited,"funds_available":sent+inherited,"actual":actual,"allocated_out":allocated_out,"returned":returned,"balance":balance,"reusable":reusable,"owner_needed":float(detail["owner_needed"]),"funded_at":funded_at,"confirmed_at":confirmed_at,"release_percent":min(100.0,(sent/budget*100.0)) if budget else (100.0 if sent else 0.0)}; funded.append(item)
        dept_name = row.department.name if row.department else "Unassigned"; dept = department_map.setdefault(dept_name,{"name":dept_name,"department_id":row.department_id,"balance":0.0,"reusable":0.0,"sent":0.0,"actual":0.0,"returned":0.0,"requests":0}); dept["balance"] += balance; dept["reusable"] += reusable; dept["sent"] += sent; dept["actual"] += actual; dept["returned"] += returned; dept["requests"] += 1
        staff_name = row.requester.display_name if row.requester else "Former staff"; staff_key = row.requester_id or staff_name; staff = staff_map.setdefault(staff_key,{"name":staff_name,"user_id":row.requester_id,"department":dept_name,"balance":0.0,"reusable":0.0,"sent":0.0,"actual":0.0,"returned":0.0}); staff["balance"] += balance; staff["reusable"] += reusable; staff["sent"] += sent; staff["actual"] += actual; staff["returned"] += returned
    funded.sort(key=lambda item: ((item["funded_at"] or item["request"].created_at or datetime.min).replace(tzinfo=timezone.utc) if not (item["funded_at"] or item["request"].created_at or datetime.min).tzinfo else (item["funded_at"] or item["request"].created_at or datetime.min)).timestamp(), reverse=True); available = total_sent - total_actual - total_returned; latest = funded[0] if funded else None; department_rows = sorted(department_map.values(),key=lambda item:item["balance"],reverse=True); staff_rows = sorted(staff_map.values(),key=lambda item:item["balance"],reverse=True)
    movement_query = RequestBalanceTransaction.query.filter_by(organization_id=user.organization_id).filter(RequestBalanceTransaction.status == "posted")
    if not management: movement_query = movement_query.filter(RequestBalanceTransaction.holder_user_id == user.id)
    movement_rows = movement_query.order_by(RequestBalanceTransaction.created_at.desc()).limit(20).all(); balance_movements = [{"row":tx,"type":tx.transaction_type,"amount":float(tx.amount or 0),"holder":tx.holder.display_name if tx.holder else "Former staff","department":tx.source_request.department.name if tx.source_request and tx.source_request.department else "Unassigned","source":tx.source_request.reference if tx.source_request else "—","source_title":tx.source_request.title if tx.source_request else "","target":tx.target_request.reference if tx.target_request else None,"target_title":tx.target_request.title if tx.target_request else None,"method":tx.payment_method or "","reference":tx.payment_reference or ""} for tx in movement_rows]
    return {"total_budget":total_budget,"total_sent":total_sent,"total_actual":total_actual,"total_returned":total_returned,"total_allocated":total_allocated,"total_inherited":total_inherited,"available_balance":available,"reusable_balance":reusable_total,"released_today":released_today,"spent_today":spent_today,"funded_count":len(funded),"open_funded_count":sum(1 for item in funded if item["request"].status in {"money_sent","approved"} and (item["sent"]+item["inherited"])>0),"awaiting_evidence_count":sum(1 for item in funded if (item["sent"]+item["inherited"])>0 and item["actual"]<=0),"reconciled_count":sum(1 for item in funded if item["actual"]>0),"partial_release_count":sum(1 for item in funded if item["owner_needed"]>0 and 0<item["sent"]<item["owner_needed"]),"overfunded_count":sum(1 for item in funded if item["sent"]>item["owner_needed"]),"shortfall":abs(min(0.0,available)),"usage_percent":(total_actual/(total_sent+total_inherited)*100.0) if (total_sent+total_inherited)>0 else 0.0,"latest":latest,"rows":funded,"department_balances":department_rows,"staff_balances":staff_rows,"balance_movements":balance_movements}

