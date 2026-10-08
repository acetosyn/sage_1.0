"""Authenticated management APIs and record history; no external data or demo seeds."""
import io
from datetime import date, datetime, timezone
from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy import or_
from models import (ActivityEvent, Attachment, AuditRevision, BudgetAllocation, FinanceAccount,
    FinanceLedgerEntry, FinanceVerification, CustodyAcknowledgment, ManagementTask, RecordLink,
    PurchaseRequest, TaskComment, User, ObligationTerms)
from packages.database import db
from services.budget_control_service import sync_request_budget
from services.export_service import build_report_export
from services.finance_service import _money
from services.notification_service import record_activity
from services.owner_control_service import MANAGEMENT, management_workspace, save_task, scoped_finance_summary, task_dict
from services.record_trace_service import ENTITIES, get_record, permitted, record_trace
from services.storage_service import save_attachment

control = Blueprint("management_control", __name__, url_prefix="/api/management")


def manager():
    if current_user.role not in MANAGEMENT: raise PermissionError("Management access is required.")


@control.errorhandler(ValueError)
def invalid(error): db.session.rollback(); return jsonify(ok=False, message=str(error)), 400
@control.errorhandler(PermissionError)
def forbidden(error): db.session.rollback(); return jsonify(ok=False, message=str(error)), 403
@control.errorhandler(LookupError)
def missing(error): db.session.rollback(); return jsonify(ok=False, message=str(error)), 404


@control.get("/workspace")
@login_required
def workspace():
    manager()
    return jsonify(ok=True, data=management_workspace(current_user, request.args.get("period", "monthly")))


@control.get("/staff-finance")
@login_required
def staff_finance():
    from models import AssetItem
    from services.record_trace_service import describe
    assets=[describe("asset",row) for row in AssetItem.query.filter_by(organization_id=current_user.organization_id,custodian_user_id=current_user.id).all()]
    issues=RecordLink.query.filter_by(organization_id=current_user.organization_id,target_type="user",target_id=current_user.id,relation="issued_to").all()
    return jsonify(ok=True, summary=scoped_finance_summary(current_user, request.args.get("period", "all")), custody=assets+[dict(type="stock_movement",id=row.source_id,title="Stock issue assigned to you") for row in issues], tasks=[task_dict(row) for row in ManagementTask.query.filter_by(organization_id=current_user.organization_id, assigned_to_id=current_user.id).order_by(ManagementTask.created_at.desc()).all()])


@control.get("/change-token")
@login_required
def change_token():
    activity = ActivityEvent.query.filter(ActivityEvent.organization_id == current_user.organization_id, ActivityEvent.action != "page_view").order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc()).first()
    revision = AuditRevision.query.filter_by(organization_id=current_user.organization_id).order_by(AuditRevision.created_at.desc(), AuditRevision.id.desc()).first()
    return jsonify(ok=True, token="|".join(str(row.id) for row in (activity, revision) if row))


@control.get("/record-options")
@login_required
def record_options():
    manager()
    kind = request.args.get("kind", "request")
    model = ENTITIES.get(kind)
    if not model or kind == "user": raise ValueError("Choose a supported business record type.")
    query = model.query.filter_by(organization_id=current_user.organization_id)
    text = request.args.get("q", "").strip()[:120]
    fields = [getattr(model, field) for field in ("reference", "title", "description", "name", "asset_tag", "sku") if hasattr(model, field)]
    if text and fields: query = query.filter(or_(*[field.ilike("%" + text.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\") for field in fields]))
    from services.record_trace_service import describe
    rows = query.order_by(model.created_at.desc()).limit(100).all()
    return jsonify(ok=True, records=[describe(kind, row) for row in rows], has_more=len(rows) == 100)


@control.get("/records/<kind>/<entity_id>")
@login_required
def history(kind, entity_id):
    offset = max(0, int(request.args.get("offset", "0")))
    return jsonify(ok=True, data=record_trace(current_user, kind, entity_id, offset))


@control.get("/records/<kind>/<entity_id>/export.<file_format>")
@login_required
def history_export(kind, entity_id, file_format):
    if file_format not in {"csv", "xlsx", "pdf"}: raise LookupError("Report format not found.")
    data = record_trace(current_user, kind, entity_id)
    events = list(data["history"])
    offset = data["next_history_offset"]
    while offset is not None:
        more = record_trace(current_user, kind, entity_id, offset)
        events.extend(more["history"]); offset = more["next_history_offset"]
    headers = ["Date / Time", "Actor", "Action", "Description", "Before", "After"]
    import json
    rows = [[row["date"], row["actor"], row["action"], row.get("description") or row["title"], json.dumps(row.get("before", {}), ensure_ascii=False), json.dumps(row.get("after", {}), ensure_ascii=False)] for row in events]
    payload, mimetype = build_report_export(headers, rows, file_format, "SAGE Record History", data["record"]["title"])
    return send_file(payload, mimetype=mimetype, as_attachment=True, download_name=f"SAGE_History_{entity_id}.{file_format}")


@control.post("/records/<kind>/<entity_id>/links")
@login_required
def link_record(kind, entity_id):
    manager(); get_record(current_user, kind, entity_id)
    payload = request.get_json(silent=True) or {}
    target_kind, target_id = payload.get("target_type"), payload.get("target_id")
    get_record(current_user, target_kind, target_id)
    if kind == target_kind and entity_id == target_id: raise ValueError("Choose a different supporting record.")
    relation = str(payload.get("relation") or "related").strip()[:40]
    row = RecordLink.query.filter_by(organization_id=current_user.organization_id, source_type=kind, source_id=entity_id, target_type=target_kind, target_id=target_id, relation=relation).first()
    if not row:
        db.session.add(RecordLink(organization_id=current_user.organization_id, source_type=kind, source_id=entity_id, target_type=target_kind, target_id=target_id, relation=relation, created_by_id=current_user.id))
        record_activity(current_app, current_user, "record_linked", "Supporting records connected", f"{current_user.display_name} linked {kind} to {target_kind} ({relation}).", kind, entity_id, notify_owner=True)
        db.session.commit()
    return jsonify(ok=True, message="Supporting record linked.")


@control.post("/records/<kind>/<entity_id>/evidence")
@login_required
def upload_evidence(kind, entity_id):
    get_record(current_user, kind, entity_id)
    if kind not in {"financial_record", "finance_ledger", "department_operation", "request", "receivable", "payable", "asset", "inventory_item"}: raise ValueError("Evidence cannot be added to this record type.")
    file = request.files.get("evidence")
    if not file or not file.filename: raise ValueError("Choose a receipt or supporting document.")
    attachment = save_attachment(current_app, file, current_user, kind, entity_id, "receipts", final=True)
    record_activity(current_app, current_user, "supporting_evidence_uploaded", "Supporting document attached", f"{current_user.display_name} attached {attachment.original_name}.", kind, entity_id, notify_owner=True)
    db.session.commit()
    return jsonify(ok=True, message="Supporting document saved.", id=attachment.id)


@control.post("/records/<kind>/<entity_id>/verify")
@login_required
def verify_expense(kind, entity_id):
    manager(); row = get_record(current_user, kind, entity_id)
    if kind not in {"financial_record", "finance_ledger"} or row.status not in {"posted", "reconciled"}: raise ValueError("Choose a posted expense to verify.")
    if kind == "financial_record" and row.record_type not in {"expense", "expenditure", "operating_cost", "payroll", "tax"}: raise ValueError("This record is not an expense.")
    if kind == "finance_ledger" and row.direction != "out": raise ValueError("This record is not an outflow.")
    payload = request.get_json(silent=True) or {}
    notes = str(payload.get("notes") or "").strip()[:5000]
    if not notes: raise ValueError("Explain what you checked before verifying.")
    evidence_ids = {row.id}
    if row.source_entity_id: evidence_ids.add(row.source_entity_id)
    if row.source_entity_type == "request":
        purchase = get_record(current_user, "request", row.source_entity_id)
        if purchase.fulfillment: evidence_ids.add(purchase.fulfillment.id)
    if not Attachment.query.filter(Attachment.organization_id == current_user.organization_id, Attachment.entity_id.in_(evidence_ids)).first(): raise ValueError("Attach supporting evidence before verification.")
    existing = FinanceVerification.query.filter_by(organization_id=current_user.organization_id, entity_type=kind, entity_id=entity_id).first()
    if existing: return jsonify(ok=True, message="Expense has already been reviewed.")
    individual = getattr(getattr(current_user.organization, "workspace_profile", None), "workspace_mode", "organization") == "individual"
    if row.created_by_id == current_user.id and current_user.role != "owner": raise PermissionError("Ask another authorized manager to review your own posting.")
    if row.created_by_id == current_user.id: notes = "Owner attestation: " + notes
    db.session.add(FinanceVerification(organization_id=current_user.organization_id, entity_type=kind, entity_id=entity_id, verified_by_id=current_user.id, notes=notes))
    record_activity(current_app, current_user, "expense_verified", "Expense evidence reviewed", f"{current_user.display_name} reviewed the supporting documents. {notes}", kind, entity_id, notify_owner=True)
    db.session.commit(); return jsonify(ok=True, message="Evidence review recorded.")


@control.post("/records/<kind>/<entity_id>/acknowledge")
@login_required
def acknowledge(kind, entity_id):
    row = get_record(current_user, kind, entity_id)
    if kind not in {"request", "stock_movement", "asset"}: raise ValueError("Choose a purchase, stock movement or asset.")
    payload = request.get_json(silent=True) or {}
    action, notes = payload.get("action", "received"), str(payload.get("notes") or "").strip()[:5000]
    if action not in {"received", "used", "returned"} or not notes: raise ValueError("Choose an action and describe your own receipt, use or return.")
    if kind == "request" and (not row.fulfillment or not row.fulfillment.confirmed_at): raise ValueError("The purchase must be completed before acknowledging custody.")
    if kind == "asset" and row.custodian_user_id != current_user.id: raise PermissionError("Only the assigned custodian can acknowledge this asset.")
    if kind == "stock_movement":
        recipients = RecordLink.query.filter_by(organization_id=current_user.organization_id, source_type=kind, source_id=entity_id, relation="issued_to").all()
        if recipients and not any(link.target_id == current_user.id for link in recipients): raise PermissionError("This issue is assigned to another person.")
        if action == "returned" and row.movement_type != "return": raise ValueError("Record the physical stock return first.")
    if not CustodyAcknowledgment.query.filter_by(organization_id=current_user.organization_id, entity_type=kind, entity_id=entity_id, user_id=current_user.id, action=action).first():
        db.session.add(CustodyAcknowledgment(organization_id=current_user.organization_id, entity_type=kind, entity_id=entity_id, user_id=current_user.id, action=action, notes=notes))
        record_activity(current_app, current_user, "custody_" + action, "Receipt / usage acknowledged", f"{current_user.display_name} confirmed {action}: {notes}", kind, entity_id, notify_owner=True)
        db.session.commit()
    return jsonify(ok=True, message="Your acknowledgment is recorded in the history.")


@control.post("/tasks")
@login_required
def create_task():
    manager(); row = save_task(current_app, current_user, request.get_json(silent=True) or {})
    return jsonify(ok=True, task=task_dict(row), message="Follow-up saved.")


@control.patch("/tasks/<task_id>")
@login_required
def update_task(task_id):
    row = ManagementTask.query.filter_by(id=task_id, organization_id=current_user.organization_id).first()
    if not row: raise LookupError("Task not found.")
    row = save_task(current_app, current_user, request.get_json(silent=True) or {}, row)
    return jsonify(ok=True, task=task_dict(row), message="Follow-up updated.")


@control.post("/budget-reservations")
@login_required
def reserve_budget():
    manager(); payload = request.get_json(silent=True) or {}
    purchase = get_record(current_user, "request", payload.get("request_id"))
    if purchase.status not in {"approved", "money_sent", "fulfilled", "verified"}: raise ValueError("Choose an approved request.")
    reservation = sync_request_budget(purchase, current_user, amount=purchase.funding.approved_budget if purchase.funding else purchase.estimated_total, budget_id=payload.get("budget_id"), actual=purchase.fulfillment.actual_total if purchase.fulfillment and purchase.fulfillment.confirmed_at else None)
    if reservation is None: raise ValueError("Choose one active cost-centre budget.")
    record_activity(current_app, current_user, "budget_reserved", "Purchase budget linked", f"{purchase.reference} linked to {reservation.budget.name}.", "request", purchase.id, notify_owner=True)
    db.session.commit(); return jsonify(ok=True, message="Budget commitment and actual spend updated.")


@control.patch("/budgets/<budget_id>")
@login_required
def revise_budget(budget_id):
    manager(); row = BudgetAllocation.query.filter_by(id=budget_id, organization_id=current_user.organization_id).first()
    if not row: raise LookupError("Budget not found.")
    payload = request.get_json(silent=True) or {}; amount = _money(payload.get("revised_budget")); notes = str(payload.get("notes") or "").strip()
    if amount <= 0 or not notes: raise ValueError("Enter a positive revised allocation and the reason for the change.")
    row.revised_budget = amount; row.notes = notes
    record_activity(current_app, current_user, "budget_revised", "Budget allocation revised", f"{row.name}: {current_user.organization.currency} {amount:,.2f}. {notes}", "budget", row.id, notify_owner=True)
    db.session.commit(); return jsonify(ok=True, message="Budget revised; the previous allocation remains in audit history.")


@control.post("/ledger/<entry_id>/account")
@login_required
def allocate_account(entry_id):
    manager(); row = get_record(current_user, "finance_ledger", entry_id)
    if row.status != "posted" or row.account_id: raise ValueError("Choose a posted transaction that has no account yet.")
    payload = request.get_json(silent=True) or {}
    account = FinanceAccount.query.filter_by(id=payload.get("account_id"), organization_id=current_user.organization_id, is_active=True).first()
    if not account: raise ValueError("Choose an active bank/cash account.")
    row.account_id = account.id
    record_activity(current_app, current_user, "cash_account_allocated", "Cash posting assigned to account", f"{row.reference} assigned to {account.name}.", "finance_ledger", row.id, notify_owner=True)
    db.session.commit(); return jsonify(ok=True, message="The existing posting is now included in this account's balance.")


@control.patch("/obligations/<kind>/<entity_id>/terms")
@login_required
def obligation_terms(kind, entity_id):
    manager()
    if kind not in {"receivable", "payable"}: raise ValueError("Choose a receivable or payable.")
    debt = get_record(current_user,kind,entity_id); payload = request.get_json(silent=True) or {}
    issued = date.fromisoformat(payload.get("invoice_date") or "")
    if issued > datetime.now(timezone.utc).date(): raise ValueError("The invoice issue date cannot be in the future.")
    terms = ObligationTerms.query.filter_by(organization_id=current_user.organization_id,entity_type=kind,entity_id=entity_id).first()
    previous = terms.invoice_date if terms else None
    if not terms:
        terms=ObligationTerms(organization_id=current_user.organization_id,entity_type=kind,entity_id=entity_id,recorded_by_id=current_user.id,invoice_date=issued);db.session.add(terms)
    terms.invoice_date = issued
    from services.management_service import record_revision
    record_revision(current_user,kind,entity_id,"invoice_date_updated",{"invoice_date":previous},{"invoice_date":issued},"Actual invoice date recorded for aging.")
    record_activity(current_app,current_user,"invoice_date_recorded","Invoice age recorded",f"{debt.reference}: actual invoice date {issued.isoformat()}.",kind,entity_id,notify_owner=True)
    db.session.commit();return jsonify(ok=True,message="The invoice issue date now controls its recorded owing age.")


def register_control_routes(app):
    app.register_blueprint(control)
