# SERVICE: SAGE Phase 7 Production Runtime
# Production diagnostics, security headers, proxy support and deployment health checks without changing tenant business logic.

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import text
from packages.database import db


def install_proxy_support(app):
    """Honor reverse-proxy headers only when explicitly enabled for deployed SAGE."""
    if not app.config.get("TRUST_PROXY_HEADERS"): return
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    except Exception as error: app.logger.warning("SAGE ProxyFix could not be enabled: %s", error)


def apply_security_headers(app, response):
    """Safe-by-default browser hardening compatible with the current HTML/CSS/JS implementation."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff"); response.headers.setdefault("X-Frame-Options", "DENY"); response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin"); response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; script-src 'self' 'unsafe-inline'; connect-src 'self' https://api.openai.com https://api.groq.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    if app.config.get("ENVIRONMENT") == "production" and app.config.get("FORCE_HTTPS"): response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
    return response


def health_snapshot(app, deep=False):
    """Return deployment health without exposing secrets or tenant content."""
    result = {"ok": True, "service": "SAGE", "environment": app.config.get("ENVIRONMENT"), "database": "unknown", "storage": "unknown", "push": "disabled", "redis": "not configured"}
    try:
        db.session.execute(text("SELECT 1")); result["database"] = app.extensions.get("vision_database_label", "connected")
    except Exception as error: result["ok"], result["database"] = False, f"unavailable: {type(error).__name__}"
    try:
        backend = app.config.get("STORAGE_BACKEND", "local")
        if backend == "local":
            path = Path(app.config["STORAGE_DIR"]); path.mkdir(parents=True, exist_ok=True); probe = path / ".sage-health"; probe.write_text("ok", encoding="utf-8"); probe.unlink(missing_ok=True); result["storage"] = "local: writable"
        elif not app.config.get("S3_BUCKET"): result["ok"], result["storage"] = False, f"{backend}: missing bucket"
        elif deep:
            from services.storage_service import _s3_client
            _s3_client(app).head_bucket(Bucket=app.config["S3_BUCKET"]); result["storage"] = f"{backend}: connected"
        else: result["storage"] = f"{backend}: configured"
    except Exception as error: result["ok"], result["storage"] = False, f"unavailable: {type(error).__name__}"
    result["push"] = "configured" if app.config.get("WEB_PUSH_ENABLED") and app.config.get("VAPID_PUBLIC_KEY") and app.config.get("VAPID_PRIVATE_KEY") else "disabled"
    if deep and app.config.get("REDIS_URL"):
        try:
            import redis
            client = redis.Redis.from_url(app.config["REDIS_URL"], socket_connect_timeout=2, socket_timeout=2); client.ping(); result["redis"] = "connected"
        except Exception as error: result["redis"] = f"unavailable: {type(error).__name__}"
    return result


def apply_retention_policy(app, dry_run=False):
    """Prune only records older than configured retention windows; defaults preserve audit history for seven years."""
    from models import ActivityEvent, AuditLog, Notification, PlatformAdminAudit, PushSubscription
    audit_days = max(365, int(app.config.get("AUDIT_RETENTION_DAYS", 2555))); notification_days = max(30, int(app.config.get("NOTIFICATION_RETENTION_DAYS", 365))); now = datetime.now(timezone.utc); audit_cutoff = now - timedelta(days=audit_days); notification_cutoff = now - timedelta(days=notification_days)
    counts = {"notifications": Notification.query.filter(Notification.is_read.is_(True), Notification.created_at < notification_cutoff).count(), "activity_events": ActivityEvent.query.filter(ActivityEvent.created_at < audit_cutoff).count(), "audit_logs": AuditLog.query.filter(AuditLog.created_at < audit_cutoff).count(), "platform_audits": PlatformAdminAudit.query.filter(PlatformAdminAudit.created_at < audit_cutoff).count(), "inactive_push": PushSubscription.query.filter(PushSubscription.is_active.is_(False), PushSubscription.updated_at < notification_cutoff).count()}
    if not dry_run:
        Notification.query.filter(Notification.is_read.is_(True), Notification.created_at < notification_cutoff).delete(synchronize_session=False); ActivityEvent.query.filter(ActivityEvent.created_at < audit_cutoff).delete(synchronize_session=False); AuditLog.query.filter(AuditLog.created_at < audit_cutoff).delete(synchronize_session=False); PlatformAdminAudit.query.filter(PlatformAdminAudit.created_at < audit_cutoff).delete(synchronize_session=False); PushSubscription.query.filter(PushSubscription.is_active.is_(False), PushSubscription.updated_at < notification_cutoff).delete(synchronize_session=False); db.session.commit()
    return {"dry_run": bool(dry_run), "audit_retention_days": audit_days, "notification_retention_days": notification_days, "eligible_records": counts}


def production_warnings(app):
    """Return startup warnings that matter before a public deployment."""
    warnings = []
    if app.config.get("ENVIRONMENT") != "production": return warnings
    if str(app.config.get("SECRET_KEY") or "").lower() in {"", "change-this-before-production", "vision-development-secret", "sage-development-secret"}: warnings.append("SECRET_KEY must be replaced before production.")
    if str(app.config.get("SQLALCHEMY_DATABASE_URI") or "").startswith("sqlite"): warnings.append("Production is using SQLite; configure PostgreSQL DATABASE_URL.")
    if not app.config.get("SESSION_COOKIE_SECURE"): warnings.append("SESSION_COOKIE_SECURE should be enabled behind HTTPS.")
    if app.config.get("STORAGE_BACKEND") == "local": warnings.append("Local file storage is enabled; use S3/R2-compatible storage for horizontally scaled production.")
    return warnings
