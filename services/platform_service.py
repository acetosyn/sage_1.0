# SERVICE: SAGE Platform / Tenant Control
# Developer-only helpers for workspace status, owner summaries, platform audits and strict organization access checks.

from datetime import datetime, timezone
from sqlalchemy import func
from models import ActivityEvent, AssetItem, AssetMovement, Attachment, AuditLog, BudgetAllocation, CatalogItem, Department, DepartmentOperation, FinanceAccount, FinanceForecast, FinanceLedgerEntry, FinancePayable, FinanceReceivable, FinanceReconciliation, FinancialRecord, InventoryItem, Notification, Organization, OrganizationWorkspace, PayrollEntry, PlatformAdminAudit, PlatformOwnerControl, FulfillmentLine, PurchaseFulfillment, PurchaseRequest, PushSubscription, RequestFunding, RequestItem, StaffInvitation, StaffReport, StockMovement, TaxEntry, User
from packages.database import db


def get_control(organization_id, create=True):
    control = PlatformOwnerControl.query.filter_by(organization_id=organization_id).first()
    if not control and create:
        control = PlatformOwnerControl(organization_id=organization_id); db.session.add(control); db.session.flush()
    return control


def organization_access_status(organization_id):
    control = get_control(organization_id, create=False)
    return (control.status if control else "active"), control


def organization_is_accessible(organization_id):
    status, _ = organization_access_status(organization_id); return status == "active"


def record_platform_admin(admin_username, action, description, organization_id=None, commit=True):
    row = PlatformAdminAudit(organization_id=organization_id, admin_username=admin_username, action=action, description=description); db.session.add(row)
    if commit: db.session.commit()
    return row


def update_control(organization_id, admin_username, payload):
    control = get_control(organization_id, create=True)
    if "status" in payload:
        status = str(payload.get("status") or "").strip().lower()
        if status == "restricted": status = "disabled"
        if status not in {"active", "disabled"}: raise ValueError("Choose Active or Disabled workspace status.")
        control.status = status
    if "plan" in payload: control.plan = (str(payload.get("plan") or "standard").strip() or "standard")[:40]
    if "subscription_status" in payload:
        subscription = str(payload.get("subscription_status") or "trial").strip().lower()
        if subscription not in {"trial", "active", "past_due", "cancelled"}: raise ValueError("Choose a valid subscription status.")
        control.subscription_status = subscription
    if "note" in payload: control.note = (str(payload.get("note") or "").strip() or None)
    control.updated_by = admin_username
    record_platform_admin(admin_username, "workspace_control_updated", f"Workspace control updated: status={control.status}, plan={control.plan}, subscription={control.subscription_status}.", organization_id, commit=False); db.session.commit(); return control


def organization_rows(search="", status="all", limit=120):
    query = Organization.query
    if search:
        term = f"%{search.strip().lower()}%"; query = query.filter(func.lower(Organization.name).like(term))
    organizations = query.order_by(Organization.created_at.desc()).limit(limit).all(); rows = []
    for org in organizations:
        control = get_control(org.id, create=True)
        if status != "all" and control.status != status: continue
        owner = User.query.filter_by(organization_id=org.id, role="owner").order_by(User.created_at.asc()).first()
        staff_count = User.query.filter(User.organization_id == org.id, User.role != "owner", User.status != "deleted").count(); total_users = User.query.filter_by(organization_id=org.id).count(); departments = Department.query.filter_by(organization_id=org.id, is_active=True).count(); requests = PurchaseRequest.query.filter_by(organization_id=org.id).count(); inventory = InventoryItem.query.filter_by(organization_id=org.id).count(); attachments = Attachment.query.filter_by(organization_id=org.id).count(); activity_count = ActivityEvent.query.filter_by(organization_id=org.id).count(); last_activity = ActivityEvent.query.filter_by(organization_id=org.id).order_by(ActivityEvent.created_at.desc()).first()
        income = db.session.query(func.coalesce(func.sum(FinancialRecord.amount), 0)).filter(FinancialRecord.organization_id == org.id, FinancialRecord.record_type.in_(["income", "revenue"]), FinancialRecord.status == "posted").scalar() or 0
        expenses = db.session.query(func.coalesce(func.sum(FinancialRecord.amount), 0)).filter(FinancialRecord.organization_id == org.id, FinancialRecord.record_type.in_(["expense", "expenditure", "operating_cost", "payroll", "tax"]), FinancialRecord.status == "posted").scalar() or 0
        rows.append({"organization": org, "control": control, "owner": owner, "staff_count": staff_count, "total_users": total_users, "department_count": departments, "request_count": requests, "inventory_count": inventory, "attachment_count": attachments, "activity_count": activity_count, "last_activity": last_activity, "income": float(income), "expenses": float(expenses), "net": float(income) - float(expenses)})
    db.session.commit(); return rows


def platform_summary():
    total_orgs = Organization.query.count(); controls = PlatformOwnerControl.query.all(); control_map = {row.organization_id: row for row in controls}; active = disabled = 0
    for org in Organization.query.with_entities(Organization.id).all():
        status = control_map.get(org.id).status if control_map.get(org.id) else "active"
        active += status == "active"; disabled += status in {"disabled", "restricted"}
    return {"organizations": total_orgs, "active": int(active), "disabled": int(disabled), "users": User.query.count(), "requests": PurchaseRequest.query.count(), "attachments": Attachment.query.count()}


# ==========================================================
# PERMANENT WORKSPACE DELETION
# ==========================================================

def permanent_delete_organization(app, organization_id, admin_username):
    """Irreversibly delete one tenant, production evidence and every known tenant-scoped Phase 1-8 record."""
    org = Organization.query.filter_by(id=organization_id).first()
    if not org: raise ValueError("Organization no longer exists.")
    org_name = org.name; attachments = Attachment.query.filter_by(organization_id=organization_id).all()
    from services.storage_service import delete_attachment_file
    for attachment in attachments: delete_attachment_file(app, attachment)

    # Keep the developer audit sentence while detaching historical admin rows from the tenant being removed.
    PlatformAdminAudit.query.filter_by(organization_id=organization_id).update({"organization_id": None}, synchronize_session=False)

    # Child/operational records first. The ordering deliberately avoids restrictive FK chains on PostgreSQL and SQLite.
    PushSubscription.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); FinanceReconciliation.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); FinanceLedgerEntry.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); BudgetAllocation.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); FinanceReceivable.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); FinancePayable.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); PayrollEntry.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); TaxEntry.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); FinanceForecast.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); FinanceAccount.query.filter_by(organization_id=organization_id).delete(synchronize_session=False)
    StaffReport.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); DepartmentOperation.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); AssetMovement.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); AssetItem.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); StockMovement.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); InventoryItem.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); Notification.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); ActivityEvent.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); Attachment.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); FinancialRecord.query.filter_by(organization_id=organization_id).delete(synchronize_session=False)
    fulfillment_ids = [row[0] for row in db.session.query(PurchaseFulfillment.id).filter(PurchaseFulfillment.organization_id == organization_id).all()]
    if fulfillment_ids: FulfillmentLine.query.filter(FulfillmentLine.fulfillment_id.in_(fulfillment_ids)).delete(synchronize_session=False)
    RequestFunding.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); PurchaseFulfillment.query.filter_by(organization_id=organization_id).delete(synchronize_session=False)
    request_ids = [row[0] for row in db.session.query(PurchaseRequest.id).filter(PurchaseRequest.organization_id == organization_id).all()]
    if request_ids: RequestItem.query.filter(RequestItem.request_id.in_(request_ids)).delete(synchronize_session=False)
    PurchaseRequest.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); CatalogItem.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); StaffInvitation.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); AuditLog.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); PlatformOwnerControl.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); OrganizationWorkspace.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); User.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); Department.query.filter_by(organization_id=organization_id).delete(synchronize_session=False); Organization.query.filter_by(id=organization_id).delete(synchronize_session=False)
    db.session.add(PlatformAdminAudit(organization_id=None, admin_username=admin_username, action="workspace_permanently_deleted", description=f"Permanently deleted organization '{org_name}' and all tenant business records.")); db.session.commit(); return org_name
