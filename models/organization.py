# MODEL: Organization
# Represents one tenant/workspace in Vision; all staff, departments and future financial data belong to an organization.

import uuid
from datetime import datetime, timezone
from packages.database import db


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(190), unique=True, nullable=False, index=True)
    business_type = db.Column(db.String(120), nullable=False)
    country = db.Column(db.String(80), nullable=False, default="Nigeria")
    state = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    employee_range = db.Column(db.String(40), nullable=True)
    branch_count = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    users = db.relationship("User", back_populates="organization", lazy="dynamic", cascade="all, delete-orphan")
    departments = db.relationship("Department", back_populates="organization", lazy="dynamic", cascade="all, delete-orphan")
    workspace_profile = db.relationship("OrganizationWorkspace", back_populates="organization", uselist=False, cascade="all, delete-orphan")
