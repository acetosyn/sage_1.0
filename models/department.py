# MODEL: Department
# Configurable organization unit. Owners/admins can add, rename or archive departments without code changes.

import uuid
from datetime import datetime, timezone
from packages.database import db


class Department(db.Model):
    __tablename__ = "departments"
    __table_args__ = (db.UniqueConstraint("organization_id", "name", name="uq_department_org_name"),)

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(140), nullable=False)
    code = db.Column(db.String(30), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    organization = db.relationship("Organization", back_populates="departments")
    users = db.relationship("User", back_populates="department", lazy="dynamic")
