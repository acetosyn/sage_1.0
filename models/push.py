# MODEL: SAGE Web Push Subscription
# Stores browser push endpoints per tenant/user so production notifications can reach a device even when the SAGE tab is not active.

import uuid
from datetime import datetime, timezone
from packages.database import db


def _id(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"
    __table_args__ = (db.UniqueConstraint("user_id", "endpoint_hash", name="uq_push_user_endpoint"),)

    id = db.Column(db.String(36), primary_key=True, default=_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint_hash = db.Column(db.String(64), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False)
    p256dh = db.Column(db.Text, nullable=False)
    auth = db.Column(db.Text, nullable=False)
    user_agent = db.Column(db.String(300), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    user = db.relationship("User")
