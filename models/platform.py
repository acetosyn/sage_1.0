# MODEL: SAGE Platform Administration
# Stores developer-only controls for each organization without mixing tenant business data into owner/staff tables.

import uuid
from datetime import datetime, timezone
from packages.database import db


def _id(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# ==========================================================
# PLATFORM OWNER / WORKSPACE CONTROL
# ==========================================================

class PlatformOwnerControl(db.Model):
    __tablename__ = "platform_owner_controls"

    id = db.Column(db.String(36), primary_key=True, default=_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    status = db.Column(db.String(24), nullable=False, default="active", index=True)  # active / restricted / deleted
    plan = db.Column(db.String(40), nullable=False, default="standard")
    subscription_status = db.Column(db.String(32), nullable=False, default="trial", index=True)  # trial / active / past_due / cancelled
    note = db.Column(db.String(600), nullable=True)
    updated_by = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    organization = db.relationship("Organization")


# ==========================================================
# PLATFORM ADMIN AUDIT TRAIL
# ==========================================================

class PlatformAdminAudit(db.Model):
    __tablename__ = "platform_admin_audits"

    id = db.Column(db.String(36), primary_key=True, default=_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    admin_username = db.Column(db.String(120), nullable=False)
    action = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.String(700), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now, index=True)

    organization = db.relationship("Organization")
