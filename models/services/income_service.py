# SERVICE: SAGE Income, Sales & Money-In Workspace
# Provides one accountable income register for owners, finance teams and department staff without duplicating the existing finance ledger.

from datetime import datetime, timezone
from models import Attachment, FinanceLedgerEntry
from services.period_service import period_bounds

INCOME_TYPES = {"income", "revenue"}; MANAGEMENT_ROLES = {"owner", "admin", "finance"}


def _scoped_income_query(user):
    query = FinanceLedgerEntry.query.filter(FinanceLedgerEntry.organization_id == user.organization_id, FinanceLedgerEntry.status.in_(["posted", "reconciled"]), FinanceLedgerEntry.entry_type.in_(INCOME_TYPES))
    if user.role not in MANAGEMENT_ROLES: query = query.filter(FinanceLedgerEntry.department_id == user.department_id) if user.department_id else query.filter(FinanceLedgerEntry.created_by_id == user.id)
    return query


def _period_total(rows, period, now=None):
    start, end = period_bounds(period, now or datetime.now(timezone.utc))
    if not start: return round(sum(float(row.amount or 0) for row in rows), 2)
    return round(sum(float(row.amount or 0) for row in rows if row.occurred_at and start <= (row.occurred_at if row.occurred_at.tzinfo else row.occurred_at.replace(tzinfo=timezone.utc)) < end), 2)


def income_workspace_context(user):
    """Build the detailed money-in register. Staff see their department scope; management sees the entire tenant."""
    rows = _scoped_income_query(user).order_by(FinanceLedgerEntry.occurred_at.desc()).limit(500).all(); ids = [row.id for row in rows]
    evidence_rows = Attachment.query.filter(Attachment.organization_id == user.organization_id, Attachment.entity_type == "finance_ledger", Attachment.entity_id.in_(ids)).order_by(Attachment.created_at.desc()).all() if ids else []
    evidence = {}; [evidence.setdefault(item.entity_id, item) for item in evidence_rows]
    category_totals = {}
    for row in rows: category_totals[row.category or "Uncategorized"] = category_totals.get(row.category or "Uncategorized", 0) + float(row.amount or 0)
    return {"rows": rows, "evidence": evidence, "today": _period_total(rows, "daily"), "week": _period_total(rows, "weekly"), "month": _period_total(rows, "monthly"), "quarter": _period_total(rows, "quarterly"), "year": _period_total(rows, "yearly"), "all_time": _period_total(rows, "all"), "categories": sorted(category_totals.items(), key=lambda item: item[1], reverse=True)[:8], "count": len(rows), "management": user.role in MANAGEMENT_ROLES}
