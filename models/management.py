# MODELS: SAGE CEO / Management Upgrade
# New additive tables for management controls. Additive tables are safe for existing deployments because db.create_all()/migrations can create them without altering historical transaction tables.

import uuid
from datetime import datetime, timezone
from packages.database import db

def new_id(): return str(uuid.uuid4())
def utcnow(): return datetime.now(timezone.utc)

# ==========================================================
# SUPPLIER MASTER
# Supplier spend/prices remain derived from immutable fulfillment lines so management always sees the real purchase history.
# ==========================================================

class Supplier(db.Model):
    __tablename__ = "suppliers"
    __table_args__ = (db.UniqueConstraint("organization_id", "normalized_name", name="uq_supplier_org_name"),)

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    normalized_name = db.Column(db.String(180), nullable=False, index=True)
    phone = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(180), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="active", index=True)
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    created_by = db.relationship("User", foreign_keys=[created_by_id])

# ==========================================================
# BRANCH / LOCATION CONTROL
# Departments are mapped to one branch/location. Separate Department records should be used when the same function exists at multiple branches.
# ==========================================================

class BranchLocation(db.Model):
    __tablename__ = "branch_locations"
    __table_args__ = (db.UniqueConstraint("organization_id", "code", name="uq_branch_org_code"),)

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(180), nullable=False)
    code = db.Column(db.String(40), nullable=False, index=True)
    address = db.Column(db.String(255), nullable=True)
    is_head_office = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    department_links = db.relationship("BranchDepartment", back_populates="branch", cascade="all, delete-orphan")


class BranchDepartment(db.Model):
    __tablename__ = "branch_departments"
    __table_args__ = (db.UniqueConstraint("organization_id", "department_id", name="uq_branch_department_once"),)

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = db.Column(db.String(36), db.ForeignKey("branch_locations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    branch = db.relationship("BranchLocation", back_populates="department_links")
    department = db.relationship("Department", foreign_keys=[department_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])


# ==========================================================
# CONFIGURABLE APPROVAL LIMITS
# Example: department head 0–100k, finance 100k–500k, owner 500k+.
# ==========================================================

class ApprovalRule(db.Model):
    __tablename__ = "approval_rules"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    min_amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    max_amount = db.Column(db.Numeric(18, 2), nullable=True)
    required_role = db.Column(db.String(40), nullable=False, default="owner", index=True)
    priority = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    created_by = db.relationship("User", foreign_keys=[created_by_id])

# ==========================================================
# IMMUTABLE CHANGE HISTORY
# Important mutable records write before/after snapshots here. Normal application routes expose no edit/delete action for these rows.
# ==========================================================

class AuditRevision(db.Model):
    __tablename__ = "audit_revisions"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    entity_type = db.Column(db.String(60), nullable=False, index=True)
    entity_id = db.Column(db.String(36), nullable=False, index=True)
    action = db.Column(db.String(120), nullable=False, index=True)
    before_json = db.Column(db.JSON, nullable=True)
    after_json = db.Column(db.JSON, nullable=True)
    change_summary = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    actor = db.relationship("User", foreign_keys=[actor_id])
