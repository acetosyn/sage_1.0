# SERVICE: SAGE Production Web Push
# Optional VAPID web-push delivery. In-app SSE and email remain available when push is not configured.

import hashlib
import json
from threading import Thread
from flask import request
from models import PushSubscription
from packages.database import db


def push_enabled(app): return bool(app.config.get("WEB_PUSH_ENABLED") and app.config.get("VAPID_PUBLIC_KEY") and app.config.get("VAPID_PRIVATE_KEY"))


def public_push_config(app): return {"enabled": push_enabled(app), "public_key": app.config.get("VAPID_PUBLIC_KEY", "") if push_enabled(app) else ""}


def save_subscription(app, user, payload):
    subscription = payload.get("subscription") if isinstance(payload, dict) else None; subscription = subscription if isinstance(subscription, dict) else payload
    endpoint = str((subscription or {}).get("endpoint") or "").strip(); keys = (subscription or {}).get("keys") or {}; p256dh, auth = str(keys.get("p256dh") or "").strip(), str(keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth: raise ValueError("Browser push subscription is incomplete.")
    endpoint_hash = hashlib.sha256(endpoint.encode("utf-8")).hexdigest(); row = PushSubscription.query.filter_by(user_id=user.id, endpoint_hash=endpoint_hash).first()
    if not row: row = PushSubscription(organization_id=user.organization_id, user_id=user.id, endpoint_hash=endpoint_hash, endpoint=endpoint, p256dh=p256dh, auth=auth); db.session.add(row)
    row.endpoint, row.p256dh, row.auth, row.is_active = endpoint, p256dh, auth, True
    try: row.user_agent = (request.user_agent.string or "")[:300]
    except RuntimeError: pass
    db.session.commit(); return row


def disable_subscription(user, endpoint):
    endpoint_hash = hashlib.sha256(str(endpoint or "").encode("utf-8")).hexdigest(); row = PushSubscription.query.filter_by(user_id=user.id, organization_id=user.organization_id, endpoint_hash=endpoint_hash).first()
    if row: row.is_active = False; db.session.commit()
    return row


def _deliver(app, subscription_id, title, message, level="info", url="/dashboard"):
    if not push_enabled(app): return
    try:
        from pywebpush import WebPushException, webpush
        with app.app_context():
            row = PushSubscription.query.filter_by(id=subscription_id, is_active=True).first()
            if not row: return
            data = json.dumps({"title": title, "body": message, "level": level, "url": url, "icon": "/static/img/sage.png"})
            try: webpush(subscription_info={"endpoint": row.endpoint, "keys": {"p256dh": row.p256dh, "auth": row.auth}}, data=data, vapid_private_key=app.config["VAPID_PRIVATE_KEY"], vapid_claims={"sub": app.config.get("VAPID_SUBJECT") or "mailto:admin@example.com"}, ttl=3600)
            except WebPushException as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                if status in {404, 410}: row.is_active = False; db.session.commit()
                else: app.logger.warning("SAGE web push delivery failed: %s", error)
    except ImportError: app.logger.debug("pywebpush is not installed; web push skipped.")
    except Exception as error: app.logger.warning("SAGE web push delivery failed: %s", error)


def send_push_to_user(app, user, title, message, level="info", url="/dashboard"):
    if not push_enabled(app): return
    rows = PushSubscription.query.filter_by(organization_id=user.organization_id, user_id=user.id, is_active=True).all()
    for row in rows: Thread(target=_deliver, args=(app, row.id, title, message, level, url), daemon=True).start()
