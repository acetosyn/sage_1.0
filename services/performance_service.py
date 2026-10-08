# SERVICE: SAGE Financial Performance Targets
# Monthly/yearly revenue and net-profit goals are owner-controlled and compared against posted real finance records.

from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from sqlalchemy import func
from models import Department, FinancePerformanceTarget, FinancialRecord
from packages.database import db
from services.notification_service import record_activity
from services.management_service import record_revision

INCOME_TYPES = {"income", "revenue"}; EXPENSE_TYPES = {"expense", "expenditure", "payroll", "tax", "operating_cost"}; TARGET_TYPES = {"revenue", "net_profit"}; PERIOD_TYPES = {"monthly", "yearly"}


def _amount(value):
    try:
        result = Decimal(str(value or "0")).quantize(Decimal("0.01"))
        if not result.is_finite() or result < 0: raise ValueError
        return result
    except (InvalidOperation, ValueError): raise ValueError("Enter a valid target amount of zero or more.")


def _period(period_type, period_value):
    text = str(period_value or "").strip()
    try:
        if period_type == "monthly":
            year, month = [int(part) for part in text.split("-")[:2]]; start = date(year, month, 1); return start, date(year, month, monthrange(year, month)[1])
        year = int(text[:4]); return date(year, 1, 1), date(year, 12, 31)
    except Exception: raise ValueError("Choose a valid month or year for this target.")


def _actual(organization_id, department_id, target_type, start, end):
    query = FinancialRecord.query.filter(FinancialRecord.organization_id == organization_id, FinancialRecord.status == "posted", FinancialRecord.occurred_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc), FinancialRecord.occurred_at < datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc))
    if department_id: query = query.filter(FinancialRecord.department_id == department_id)
    rows = query.all(); income = sum(float(row.amount or 0) for row in rows if row.record_type in INCOME_TYPES); expenses = sum(float(row.amount or 0) for row in rows if row.record_type in EXPENSE_TYPES)
    return round(income if target_type == "revenue" else income - expenses, 2), round(income, 2), round(expenses, 2)


def save_performance_target(app, user, payload):
    target_type, period_type = str(payload.get("target_type") or "revenue").lower(), str(payload.get("period_type") or "monthly").lower()
    if target_type not in TARGET_TYPES: raise ValueError("Choose Revenue or Net Profit as the target type.")
    if period_type not in PERIOD_TYPES: raise ValueError("Choose Monthly or Yearly as the target period.")
    start, end = _period(period_type, payload.get("period_value")); department = Department.query.filter_by(id=payload.get("department_id"), organization_id=user.organization_id, is_active=True).first() if payload.get("department_id") else None
    if payload.get("department_id") and not department: raise ValueError("Choose a valid department in your organization.")
    amount = _amount(payload.get("target_amount")); row = FinancePerformanceTarget.query.filter_by(organization_id=user.organization_id, department_id=department.id if department else None, target_type=target_type, period_type=period_type, period_start=start, period_end=end, is_active=True).first(); before = {"target_amount": float(row.target_amount), "notes": row.notes} if row else {}
    if not row:
        row = FinancePerformanceTarget(organization_id=user.organization_id, department_id=department.id if department else None, created_by_id=user.id, name=str(payload.get("name") or f"{start.strftime('%B %Y') if period_type == 'monthly' else start.year} {target_type.replace('_',' ').title()} Target").strip(), target_type=target_type, period_type=period_type, period_start=start, period_end=end, currency=user.organization.currency); db.session.add(row)
    row.target_amount, row.notes = amount, str(payload.get("notes") or "").strip() or None; db.session.flush(); after = {"target_amount": float(row.target_amount), "notes": row.notes, "period_start": start.isoformat(), "period_end": end.isoformat(), "target_type": target_type}
    record_revision(user, "finance_performance_target", row.id, "performance_target_saved", before, after, f"{row.name} set to {row.currency} {float(amount):,.2f}."); record_activity(app, user, "performance_target_saved", "Financial target updated", f"{user.display_name} set {row.name} to {row.currency} {float(amount):,.2f} for {department.name if department else 'the organization'}.", "finance_performance_target", row.id, after, notify_owner=True); db.session.commit(); return row


def performance_target_context(user):
    today = date.today(); rows = FinancePerformanceTarget.query.filter(FinancePerformanceTarget.organization_id == user.organization_id, FinancePerformanceTarget.is_active.is_(True), FinancePerformanceTarget.period_start <= today, FinancePerformanceTarget.period_end >= today).order_by(FinancePerformanceTarget.period_type.asc(), FinancePerformanceTarget.target_type.asc()).all(); output = []
    for row in rows:
        actual, income, expenses = _actual(user.organization_id, row.department_id, row.target_type, row.period_start, row.period_end); target = float(row.target_amount or 0); variance = actual - target; progress = (actual / target * 100) if target else None
        output.append({"row": row, "actual": actual, "income": income, "expenses": expenses, "variance": round(variance, 2), "progress": round(progress, 1) if progress is not None else None, "scope": row.department.name if row.department else "Organization-wide"})
    month = [item for item in output if item["row"].period_type == "monthly"]; year = [item for item in output if item["row"].period_type == "yearly"]
    return {"rows": output, "monthly": month, "yearly": year, "current_month": today.strftime("%Y-%m"), "current_year": str(today.year)}
