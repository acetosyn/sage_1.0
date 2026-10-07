# MODEL: SAGE Workspace Profile
# Stores whether an owner created a multi-department organization or a lean individual/entrepreneur workspace without altering legacy organization rows.

import uuid
from datetime import datetime, timezone
from packages.database import db


class OrganizationWorkspace(db.Model):
    __tablename__ = "organization_workspaces"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    workspace_mode = db.Column(db.String(24), nullable=False, default="organization", index=True)
    business_category_key = db.Column(db.String(80), nullable=True)
    business_category_label = db.Column(db.String(140), nullable=True)
    catalog_key = db.Column(db.String(80), nullable=True)
    primary_department_name = db.Column(db.String(140), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    organization = db.relationship("Organization", back_populates="workspace_profile")

    @property
    def is_individual(self): return self.workspace_mode == "individual"
