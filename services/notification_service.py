# SERVICE: SAGE Live Accountability / Notifications
# Centralizes activity events, owner visibility, staff status alerts and optional email escalation.

from flask import request
from models import ActivityEvent, Notification, User
from packages.database import db
from services.email_service import send_email
from services.push_service import send_push_to_user

OWNER_ROLES = {"owner", "admin"}


def _request_meta():
    try: return request.headers.get("X-Forwarded-For", request.remote_addr), (request.user_agent.string or "")[:300]
    except RuntimeError: return None, None


def notify_user(app, user, title, message, level="info", entity_type=None, entity_id=None, email=False):
    notification = Notification(organization_id=user.organization_id, user_id=user.id, title=title, message=message, level=level, entity_type=entity_type, entity_id=entity_id, email_attempted=bool(email))
    db.session.add(notification)
    if email: send_email(app, user.email, f"SAGE: {title}", message)
    send_push_to_user(app, user, title, message, level=level, url="/dashboard")
    return notification


def notify_owners(app, organization_id, actor_id, title, message, level="info", entity_type=None, entity_id=None, email=False):
    owners = User.query.filter(User.organization_id == organization_id, User.role.in_(OWNER_ROLES), User.status == "active").all()
    for owner in owners:
        if owner.id != actor_id: notify_user(app, owner, title, message, level, entity_type, entity_id, email)


def record_activity(app, actor, action, title, description, entity_type=None, entity_id=None, details=None, notify_owner=True, email_owner=False, level="info"):
    ip, agent = _request_meta(); event = ActivityEvent(organization_id=actor.organization_id, actor_id=actor.id, department_id=actor.department_id, action=action, title=title, description=description, entity_type=entity_type, entity_id=entity_id, details_json=details or {}, ip_address=ip, user_agent=agent)
    db.session.add(event)
    # Every meaningful owner-visible staff action is persisted immediately. When SMTP is enabled, owner alerts also leave the browser by email.
    if notify_owner: notify_owners(app, actor.organization_id, actor.id, title, description, level, entity_type, entity_id, bool(email_owner or action not in {"page_view"}))
    return event
