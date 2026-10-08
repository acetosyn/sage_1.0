# SERVICE: SAGE Daily Briefing / Guided Status Summary
# Builds a permission-aware login briefing from real tenant data so owners and staff can understand today's position without opening every page.

from collections import Counter
from datetime import datetime, timezone
from sqlalchemy import func
from core.datetime_utils import as_utc
from models import ActivityEvent, AssetItem, DepartmentOperation, FinancePayable, FinanceReceivable, FinancialRecord, InventoryItem, Notification, PurchaseRequest, StaffReport
from packages.database import db

INCOME_TYPES = {"income", "revenue"}
EXPENSE_TYPES = {"expense", "expenditure", "operating_cost", "payroll", "tax"}
MANAGEMENT_ROLES = {"owner", "admin", "finance"}
REQUEST_OVERSIGHT_ROLES = {"owner", "admin", "finance", "procurement"}


def _money(value):
    try: return float(value or 0)
    except (TypeError, ValueError): return 0.0


def _fmt(currency, value):
    return f"{currency} {_money(value):,.0f}"


def _scope(query, model, user, management_roles=MANAGEMENT_ROLES):
    if user.role not in management_roles:
        if user.department_id and hasattr(model, "department_id"): query = query.filter(model.department_id == user.department_id)
        elif hasattr(model, "created_by_id"): query = query.filter(model.created_by_id == user.id)
        elif hasattr(model, "added_by_id"): query = query.filter(model.added_by_id == user.id)
        else: query = query.filter(False)
    return query


def build_daily_briefing(user):
    """Return large, sequential, permission-aware briefing slides from today's real records and current outstanding positions."""
    now = datetime.now(timezone.utc); today = now.replace(hour=0, minute=0, second=0, microsecond=0); currency = user.organization.currency or "NGN"; scope_name = user.organization.name if user.role in MANAGEMENT_ROLES else (user.department.name if user.department else user.organization.name)

    finance_query = _scope(FinancialRecord.query.filter(FinancialRecord.organization_id == user.organization_id, FinancialRecord.status == "posted", FinancialRecord.occurred_at >= today), FinancialRecord, user)
    finance_rows = finance_query.all(); today_income = sum(_money(row.amount) for row in finance_rows if row.record_type in INCOME_TYPES); today_expense = sum(_money(row.amount) for row in finance_rows if row.record_type in EXPENSE_TYPES); today_net = today_income - today_expense

    request_query = PurchaseRequest.query.filter(PurchaseRequest.organization_id == user.organization_id); request_query = request_query if user.role in REQUEST_OVERSIGHT_ROLES else request_query.filter(PurchaseRequest.department_id == user.department_id)
    request_rows = request_query.order_by(PurchaseRequest.created_at.desc()).all(); new_requests = sum(1 for row in request_rows if row.created_at and as_utc(row.created_at) >= today); pending_requests = sum(1 for row in request_rows if row.status == "submitted"); urgent_requests = sum(1 for row in request_rows if row.status == "submitted" and str(row.urgency or "").lower() in {"urgent", "critical"}); acquisition_due = sum(1 for row in request_rows if row.status in {"approved", "money_sent"})

    inventory_query = _scope(InventoryItem.query.filter(InventoryItem.organization_id == user.organization_id), InventoryItem, user, REQUEST_OVERSIGHT_ROLES); inventory_rows = inventory_query.all(); inventory_value = sum(row.total_value for row in inventory_rows); low_stock = sum(1 for row in inventory_rows if _money(row.reorder_level) > 0 and _money(row.quantity) <= _money(row.reorder_level))
    asset_query = _scope(AssetItem.query.filter(AssetItem.organization_id == user.organization_id), AssetItem, user, REQUEST_OVERSIGHT_ROLES); asset_rows = asset_query.all(); asset_value = sum(row.total_value for row in asset_rows)

    operation_query = _scope(DepartmentOperation.query.filter(DepartmentOperation.organization_id == user.organization_id, DepartmentOperation.occurred_at >= today), DepartmentOperation, user, {"owner", "admin"}); operations_today = operation_query.count()
    activity_query = ActivityEvent.query.filter(ActivityEvent.organization_id == user.organization_id, ActivityEvent.created_at >= today, ActivityEvent.action != "page_view"); activity_query = activity_query if user.role in MANAGEMENT_ROLES else activity_query.filter(ActivityEvent.department_id == user.department_id); activity_rows = activity_query.order_by(ActivityEvent.created_at.desc()).limit(120).all(); activity_count = len(activity_rows)
    department_counts = Counter((row.department.name if row.department else "General") for row in activity_rows); busiest_department = department_counts.most_common(1)[0] if department_counts else None

    receivable_query = _scope(FinanceReceivable.query.filter(FinanceReceivable.organization_id == user.organization_id, ~FinanceReceivable.status.in_(["paid", "cancelled"])), FinanceReceivable, user); payable_query = _scope(FinancePayable.query.filter(FinancePayable.organization_id == user.organization_id, ~FinancePayable.status.in_(["paid", "cancelled"])), FinancePayable, user); ar_balance = sum(row.balance for row in receivable_query.all()); ap_balance = sum(row.balance for row in payable_query.all())
    unread = Notification.query.filter_by(organization_id=user.organization_id, user_id=user.id, is_read=False).count(); reports_waiting = StaffReport.query.filter_by(organization_id=user.organization_id, status="submitted").count() if user.role in {"owner","admin"} else 0

    slides = [
        {"tone":"blue","icon":"sparkles","kicker":"YOUR SAGE BRIEF","title":f"Good {('morning' if now.hour < 12 else 'afternoon' if now.hour < 17 else 'evening')}, {user.first_name}.","message":f"Here is the live status for {scope_name}. These figures come from your current SAGE records and update as your team works.","metric":f"{activity_count} accountable action{'s' if activity_count != 1 else ''} today","route":"dashboard","action_label":"View dashboard"},
        {"tone":"green" if today_net >= 0 else "red","icon":"wallet","kicker":"TODAY · MONEY","title":f"Net position: {_fmt(currency, today_net)}","message":f"Income is {_fmt(currency, today_income)} and tracked expenditure is {_fmt(currency, today_expense)} today.","metric":f"{_fmt(currency, today_income)} in · {_fmt(currency, today_expense)} out","route":"finance","action_label":"Open finance"},
        {"tone":"orange" if pending_requests else "green","icon":"requests","kicker":"REQUESTS & APPROVALS","title":f"{pending_requests} request{'s' if pending_requests != 1 else ''} waiting","message":f"{new_requests} new today · {urgent_requests} urgent/critical · {acquisition_due} approved or funded request(s) ready for Stage 2 recording.","metric":f"{len(request_rows)} tracked request{'s' if len(request_rows) != 1 else ''}","route":"requests","action_label":"Review requests"},
        {"tone":"violet" if low_stock else "blue","icon":"inventory","kicker":"STOCK & ASSETS","title":f"{low_stock} low-stock item{'s' if low_stock != 1 else ''}","message":f"Tracked inventory value is {_fmt(currency, inventory_value)} and asset value is {_fmt(currency, asset_value)} across your permitted workspace.","metric":f"{len(inventory_rows)} stock item(s) · {len(asset_rows)} asset(s)","route":"inventory","action_label":"Open inventory"},
        {"tone":"blue","icon":"briefcase","kicker":"TODAY · OPERATIONS","title":f"{operations_today} department operation{'s' if operations_today != 1 else ''} recorded","message":(f"{busiest_department[0]} currently has the most tracked activity today ({busiest_department[1]} event(s))." if busiest_department else "No non-navigation operational activity has been recorded yet today."),"metric":f"{activity_count} meaningful tracked event{'s' if activity_count != 1 else ''}","route":"operations","action_label":"Open operations"},
    ]
    if user.role in MANAGEMENT_ROLES or user.role == "finance": slides.append({"tone":"orange" if ap_balance else "blue","icon":"finance","kicker":"OUTSTANDING MONEY","title":f"Receivable {_fmt(currency, ar_balance)} · Payable {_fmt(currency, ap_balance)}","message":"This shows money customers still owe and supplier/other obligations currently outstanding in SAGE.","metric":f"Net outstanding {_fmt(currency, ar_balance - ap_balance)}","route":"finance","action_label":"Review AR / AP"})
    if user.role in {"owner","admin"}: slides.append({"tone":"orange" if reports_waiting else "green","icon":"reports","kicker":"STAFF REPORTS","title":f"{reports_waiting} report{'s' if reports_waiting != 1 else ''} waiting for review","message":"Submitted Daily, Weekly, Monthly and Quarterly staff reports are available in your Report Inbox with written notes and source activity.","metric":"Management acknowledgement keeps the reporting loop accountable","route":"reports","action_label":"Open Report Inbox"})
    slides.append({"tone":"red" if unread else "green","icon":"bell","kicker":"YOUR ALERTS","title":f"{unread} unread notification{'s' if unread != 1 else ''}","message":"Important approvals, staff submissions, evidence uploads and system alerts stay available in the notification centre after this briefing closes.","metric":"Live tracking is active","route":"audit" if user.role in {"owner", "admin", "finance"} else "dashboard","action_label":"View activity"})
    return {"generated_at": now.isoformat(), "scope": scope_name, "currency": currency, "slides": slides}
