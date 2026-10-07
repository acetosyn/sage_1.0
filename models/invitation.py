# MODEL: Staff Invitation
# Securely links a staff registration to the correct organization, department and role before the user creates a password.

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from packages.database import db


class StaffInvitation(db.Model):
    __tablename__ = "staff_invitations"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token = db.Column(db.String(96), unique=True, nullable=False, index=True, default=lambda: secrets.token_urlsafe(40))
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    invited_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email = db.Column(db.String(190), nullable=False, index=True)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    role = db.Column(db.String(40), nullable=False, default="staff")
    status = db.Column(db.String(24), nullable=False, default="pending")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc) + timedelta(days=7))

    organization = db.relationship("Organization")
    department = db.relationship("Department")
    invited_by = db.relationship("User", foreign_keys=[invited_by_id])

    @property
    def is_valid(self):
        now = datetime.now(timezone.utc)
        expires = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return self.status == "pending" and expires > now
