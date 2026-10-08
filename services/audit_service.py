"""Append-only snapshots for important record changes in the same database transaction."""
import uuid
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session
from models import AuditRevision

TRACKED = {
    "User", "Department", "OrganizationWorkspace", "PurchaseRequest", "RequestFunding",
    "PurchaseFulfillment", "FulfillmentLine", "InventoryItem", "StockMovement", "AssetItem",
    "AssetMovement", "FinancialRecord", "FinanceAccount", "FinanceLedgerEntry", "BudgetAllocation",
    "FinanceReceivable", "FinancePayable", "FinanceReconciliation", "PayrollEntry", "TaxEntry",
    "DepartmentOperation", "StaffReport", "Supplier", "BranchLocation", "BranchDepartment",
    "ApprovalRule", "Attachment", "ManagementTask", "RecordLink", "FinanceVerification",
    "CustodyAcknowledgment", "ReconciliationMatch", "BudgetReservation", "TaskComment", "DirectPurchaseLine", "ObligationTerms"
}
SECRET_FIELDS = {"password_hash", "token", "auth", "p256dh"}


def value_json(value):
    if isinstance(value, dict): return {str(key):value_json(item) for key,item in value.items()}
    if isinstance(value, (list,tuple)): return [value_json(item) for item in value]
    if value is None or isinstance(value, (str, int, bool, float)): return value
    if hasattr(value, "isoformat"): return value.isoformat()
    return str(value)


def audit_flush(session, flush_context, instances):
    actor = session.info.get("sage_actor_id")
    for row in list(session.new) + list(session.dirty) + list(session.deleted):
        name = type(row).__name__
        if name == "AuditRevision" and row not in session.new:
            raise ValueError("Audit history is append-only.")
        if name not in TRACKED or not getattr(row, "organization_id", None): continue
        is_new, deleted = row in session.new, row in session.deleted
        state = inspect(row)
        changed = [attribute for attribute in state.mapper.column_attrs if state.attrs[attribute.key].history.has_changes() and attribute.key not in SECRET_FIELDS]
        if not is_new and not deleted and not changed: continue
        if getattr(row, "id", None) is None: row.id = str(uuid.uuid4())
        after, before = {}, {}
        stored = session.connection().execute(select(row.__table__).where(row.__table__.c.id == row.id)).mappings().first() if not is_new else None
        for attribute in state.mapper.column_attrs:
            key = attribute.key
            if key in SECRET_FIELDS: continue
            current = getattr(row, key)
            history = state.attrs[key].history
            after[key] = value_json(current)
            if not is_new: before[key] = value_json(stored[key] if stored else history.deleted[0] if history.deleted else current)
        action = "created" if is_new else "deleted" if deleted else "updated"
        source_actor = actor or getattr(row, "created_by_id", None) or getattr(row, "user_id", None) or getattr(row, "recorded_by_id", None)
        session.add(AuditRevision(organization_id=row.organization_id, actor_id=source_actor,
            entity_type=name, entity_id=str(row.id), action="record_" + action,
            before_json=before, after_json={} if deleted else after,
            change_summary=f"{name} {action}"))


def install_audit_tracking(app):
    if not event.contains(Session, "before_flush", audit_flush): event.listen(Session, "before_flush", audit_flush)
