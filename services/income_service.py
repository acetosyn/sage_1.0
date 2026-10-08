# SERVICE: SAGE Income, Sales & Money-In Workspace
# Provides one accountable income register plus compact source/payment/department intelligence without duplicating the finance ledger.

from datetime import datetime, timezone
from models import Attachment, FinanceLedgerEntry
from services.period_service import period_bounds, previous_bounds

INCOME_TYPES = {"income", "revenue"}; MANAGEMENT_ROLES = {"owner", "admin", "finance"}


def _scoped_income_query(user):
    query = FinanceLedgerEntry.query.filter(FinanceLedgerEntry.organization_id == user.organization_id, FinanceLedgerEntry.status.in_(["posted", "reconciled"]), FinanceLedgerEntry.entry_type.in_(INCOME_TYPES))
    if user.role not in MANAGEMENT_ROLES: query = query.filter(FinanceLedgerEntry.department_id == user.department_id) if user.department_id else query.filter(FinanceLedgerEntry.created_by_id == user.id)
    return query


def _aware(value): return value if not value or value.tzinfo else value.replace(tzinfo=timezone.utc)
def _between_total(rows, start=None, end=None): return round(sum(float(row.amount or 0) for row in rows if row.occurred_at and (not start or _aware(row.occurred_at) >= start) and (not end or _aware(row.occurred_at) < end)), 2)
def _period_total(rows, period, now=None):
    start, end = period_bounds(period, now or datetime.now(timezone.utc)); return _between_total(rows, start, end) if start else round(sum(float(row.amount or 0) for row in rows), 2)
def _change(current, previous): return round(((current - previous) / previous * 100), 1) if previous else (100.0 if current else 0.0)
def _rank(mapping, limit=6): return sorted(mapping.items(), key=lambda item: item[1], reverse=True)[:limit]


def income_workspace_context(user):
    """Build detailed money-in records and management intelligence. Staff remain restricted to their department/own entries."""
    rows = _scoped_income_query(user).order_by(FinanceLedgerEntry.occurred_at.desc()).limit(800).all(); ids = [row.id for row in rows]
    evidence_rows = Attachment.query.filter(Attachment.organization_id == user.organization_id, Attachment.entity_type == "finance_ledger", Attachment.entity_id.in_(ids)).order_by(Attachment.created_at.desc()).all() if ids else []; evidence = {}
    for item in evidence_rows: evidence.setdefault(item.entity_id, item)
    source_groups = {}
    for row in rows:
        if row.id in evidence or not row.source_entity_type or not row.source_entity_id: continue
        source_groups.setdefault(row.source_entity_type, set()).add(row.source_entity_id)
    for entity_type, entity_ids in source_groups.items():
        attachments = Attachment.query.filter(Attachment.organization_id == user.organization_id, Attachment.entity_type == entity_type, Attachment.entity_id.in_(list(entity_ids))).order_by(Attachment.created_at.desc()).all()
        by_source = {}
        for item in attachments: by_source.setdefault(item.entity_id, item)
        for row in rows:
            if row.id not in evidence and row.source_entity_type == entity_type and row.source_entity_id in by_source: evidence[row.id] = by_source[row.source_entity_id]
    category_totals, source_totals, payment_totals, department_totals = {}, {}, {}, {}
    for row in rows:
        amount=float(row.amount or 0); category=row.category or "Uncategorized"; source=row.counterparty or "Walk-in / Not specified"; method=row.payment_method or "Not specified"; department=row.department.name if row.department else "Organization-wide"
        category_totals[category]=category_totals.get(category,0)+amount; source_totals[source]=source_totals.get(source,0)+amount; payment_totals[method]=payment_totals.get(method,0)+amount; department_totals[department]=department_totals.get(department,0)+amount
    now=datetime.now(timezone.utc); today_start,today_end=period_bounds("daily",now); prev_day_start,prev_day_end=previous_bounds("daily",now); month_start,month_end=period_bounds("monthly",now); prev_month_start,prev_month_end=previous_bounds("monthly",now)
    today=_between_total(rows,today_start,today_end); previous_day=_between_total(rows,prev_day_start,prev_day_end); month=_between_total(rows,month_start,month_end); previous_month=_between_total(rows,prev_month_start,prev_month_end); all_time=round(sum(float(row.amount or 0) for row in rows),2); missing_evidence=sum(1 for row in rows if row.id not in evidence); largest=max(rows,key=lambda row:float(row.amount or 0),default=None)
    return {"rows":rows,"evidence":evidence,"today":today,"week":_period_total(rows,"weekly",now),"month":month,"quarter":_period_total(rows,"quarterly",now),"year":_period_total(rows,"yearly",now),"all_time":all_time,"categories":_rank(category_totals,8),"sources":_rank(source_totals),"payment_methods":_rank(payment_totals),"payment_method_options":sorted(payment_totals.keys()),"departments":_rank(department_totals),"count":len(rows),"revenue_count":sum(1 for row in rows if row.entry_type=="revenue"),"income_count":sum(1 for row in rows if row.entry_type=="income"),"average":round(all_time/len(rows),2) if rows else 0,"largest":largest,"evidence_count":len(rows)-missing_evidence,"missing_evidence":missing_evidence,"evidence_coverage":round(((len(rows)-missing_evidence)/len(rows)*100),1) if rows else 0,"previous_day":previous_day,"today_change":_change(today,previous_day),"previous_month":previous_month,"month_change":_change(month,previous_month),"management":user.role in MANAGEMENT_ROLES}


def income_export_rows(user):
    """Role-scoped CSV rows: normal staff can export only what the Income page already permits them to see."""
    rows=_scoped_income_query(user).order_by(FinanceLedgerEntry.occurred_at.desc()).limit(5000).all(); headers=["Date/Time","Reference","Type","Description","Category","Source/Customer","Department","Recorded By","Position","Payment Method","External Reference","Amount","Currency","Status"]
    data=[[row.occurred_at.isoformat() if row.occurred_at else "",row.reference,row.entry_type,row.description,row.category or "",row.counterparty or "",row.department.name if row.department else "Organization",row.created_by.display_name if row.created_by else "Former user",row.created_by.position if row.created_by and row.created_by.position else "",row.payment_method or "",row.external_reference or "",float(row.amount or 0),row.currency,row.status] for row in rows]
    return headers,data
