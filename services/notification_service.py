# SERVICE: SAGE Live Accountability / Notifications
# Centralizes activity events, owner visibility, deep-linked alerts, staff status events and optional email escalation.

from flask import request
from models import ActivityEvent, Notification, User
from packages.database import db
from services.email_service import send_email
from services.push_service import send_push_to_user

OWNER_ROLES = {"owner", "admin"}; QUIET_OWNER_ACTIONS = {"page_view", "finance_ledger_draft", "staff_report_generated", "acquisition_draft_saved"}
ENTITY_ROUTES = {"user":"staff", "request":"requests", "fulfillment":"procurement", "inventory_item":"inventory", "stock_movement":"inventory", "asset":"assets", "asset_movement":"assets", "department_operation":"operations", "staff_report":"reports", "financial_record":"finance", "finance_account":"finance", "finance_ledger":"finance", "budget":"finance", "receivable":"finance", "payable":"finance", "reconciliation":"finance", "payroll":"finance", "tax":"finance", "forecast":"finance", "finance_performance_target":"income", "department":"departments", "catalog_item":"catalog", "branch":"reports", "approval_rule":"settings", "management_task":"dashboard", "report":"reports"}


def _request_meta():
    try: return request.headers.get("X-Forwarded-For", request.remote_addr), (request.user_agent.string or "")[:300]
    except RuntimeError: return None, None


def notification_route(entity_type=None, title=""):
    """Return the closest SAGE page for an alert so bell items, Pulse cards and browser push all open useful context."""
    if entity_type == "finance_ledger" and str(title or "").lower().startswith("money in"): return "income"
    return ENTITY_ROUTES.get(str(entity_type or "").strip().lower(), "dashboard")


def notify_user(app, user, title, message, level="info", entity_type=None, entity_id=None, email=False):
    route = notification_route(entity_type, title); notification = Notification(organization_id=user.organization_id, user_id=user.id, title=title, message=message, level=level, entity_type=entity_type, entity_id=entity_id, email_attempted=bool(email)); db.session.add(notification)
    if email: send_email(app, user.email, f"SAGE: {title}", message)
    send_push_to_user(app, user, title, message, level=level, url=f"/{route}")
    return notification


def notify_owners(app, organization_id, actor_id, title, message, level="info", entity_type=None, entity_id=None, email=False):
    owners = User.query.filter(User.organization_id == organization_id, User.role.in_(OWNER_ROLES), User.status == "active").all()
    for owner in owners:
        if owner.id != actor_id: notify_user(app, owner, title, message, level, entity_type, entity_id, email)


def record_activity(app, actor, action, title, description, entity_type=None, entity_id=None, details=None, notify_owner=True, email_owner=False, level="info"):
    ip, agent = _request_meta(); details = details or {}; event = ActivityEvent(organization_id=actor.organization_id, actor_id=actor.id, department_id=actor.department_id, action=action, title=title, description=description, entity_type=entity_type, entity_id=entity_id, details_json=details, ip_address=ip, user_agent=agent); db.session.add(event)
    # Owner coverage rule: every meaningful action performed by somebody other than the owner generates a real-time owner/admin alert even when an older caller passed notify_owner=False. Quiet drafts/page views remain audit-only to avoid notification noise.
    draft_request = action == "request_created" and str(details.get("status") or "").lower() == "draft"; should_notify = bool(notify_owner or (actor.role != "owner" and action not in QUIET_OWNER_ACTIONS and not draft_request))
    if should_notify: notify_owners(app, actor.organization_id, actor.id, title, description, level, entity_type, entity_id, bool(email_owner))
    return event
