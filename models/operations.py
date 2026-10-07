# MODELS: SAGE Operations / Finance / Tracking
# Transaction models for requests, approvals, procurement evidence, inventory, financial records, notifications and live activity.

import uuid
from datetime import datetime, timezone
from packages.database import db


def new_id(): return str(uuid.uuid4())
def utcnow(): return datetime.now(timezone.utc)


# ==========================================================
# PURCHASE / OPERATIONAL REQUESTS
# ==========================================================

class PurchaseRequest(db.Model):
    __tablename__ = "purchase_requests"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    reference = db.Column(db.String(32), unique=True, nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    requester_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title = db.Column(db.String(180), nullable=False)
    purpose = db.Column(db.Text, nullable=True)
    urgency = db.Column(db.String(24), nullable=False, default="normal")
    status = db.Column(db.String(32), nullable=False, default="draft", index=True)  # draft/submitted/approved/money_sent/rejected/fulfilled/verified
    estimated_total = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    approved_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    money_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    money_sent_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_at = db.Column(db.DateTime(timezone=True), nullable=True)
    rejected_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision_note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    department = db.relationship("Department", foreign_keys=[department_id])
    requester = db.relationship("User", foreign_keys=[requester_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])
    money_sent_by = db.relationship("User", foreign_keys=[money_sent_by_id])
    rejected_by = db.relationship("User", foreign_keys=[rejected_by_id])
    items = db.relationship("RequestItem", back_populates="request", cascade="all, delete-orphan", order_by="RequestItem.created_at")
    fulfillment = db.relationship("PurchaseFulfillment", back_populates="request", uselist=False, cascade="all, delete-orphan")
    funding = db.relationship("RequestFunding", back_populates="request", uselist=False, cascade="all, delete-orphan")

    @property
    def display_status(self): return self.status.replace("_", " ").title()


class RequestItem(db.Model):
    __tablename__ = "request_items"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    request_id = db.Column(db.String(36), db.ForeignKey("purchase_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    item_name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(120), nullable=True)
    unit = db.Column(db.String(60), nullable=False, default="unit")
    quantity = db.Column(db.Numeric(18, 3), nullable=False, default=1)
    unit_cost = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    estimated_total = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    request = db.relationship("PurchaseRequest", back_populates="items")


# ==========================================================
# REQUEST FUNDING / OWNER BUDGET CONTROL
# ==========================================================

class RequestFunding(db.Model):
    __tablename__ = "request_funding"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    request_id = db.Column(db.String(36), db.ForeignKey("purchase_requests.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    recorded_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_budget = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    amount_sent = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    payment_method = db.Column(db.String(80), nullable=True)
    payment_reference = db.Column(db.String(120), nullable=True)
    note = db.Column(db.String(500), nullable=True)
    funded_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    request = db.relationship("PurchaseRequest", back_populates="funding")
    recorded_by = db.relationship("User", foreign_keys=[recorded_by_id])

    @property
    def remaining_budget(self): return float(self.approved_budget or 0) - float(self.amount_sent or 0)


# ==========================================================
# PROCUREMENT / PURCHASE FULFILLMENT + EVIDENCE
# ==========================================================

class PurchaseFulfillment(db.Model):
    __tablename__ = "purchase_fulfillments"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    request_id = db.Column(db.String(36), db.ForeignKey("purchase_requests.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    recorded_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source_type = db.Column(db.String(32), nullable=False, default="self_purchase")  # self_purchase / received_from_other
    supplied_by = db.Column(db.String(180), nullable=True)
    supplier_name = db.Column(db.String(180), nullable=True)
    actual_total = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    purchase_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_draft = db.Column(db.Boolean, nullable=False, default=True, index=True)
    confirmed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    verified_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    request = db.relationship("PurchaseRequest", back_populates="fulfillment")
    recorded_by = db.relationship("User", foreign_keys=[recorded_by_id])
    verified_by = db.relationship("User", foreign_keys=[verified_by_id])
    lines = db.relationship("FulfillmentLine", back_populates="fulfillment", cascade="all, delete-orphan", order_by="FulfillmentLine.created_at")

    @property
    def locked(self): return bool(self.confirmed_at and not self.is_draft)


class FulfillmentLine(db.Model):
    __tablename__ = "fulfillment_lines"
    __table_args__ = (db.UniqueConstraint("fulfillment_id", "request_item_id", name="uq_fulfillment_request_item"),)

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    fulfillment_id = db.Column(db.String(36), db.ForeignKey("purchase_fulfillments.id", ondelete="CASCADE"), nullable=False, index=True)
    request_item_id = db.Column(db.String(36), db.ForeignKey("request_items.id", ondelete="SET NULL"), nullable=True, index=True)
    item_name = db.Column(db.String(180), nullable=False)
    unit = db.Column(db.String(60), nullable=False, default="unit")
    requested_quantity = db.Column(db.Numeric(18, 3), nullable=False, default=0)
    actual_quantity = db.Column(db.Numeric(18, 3), nullable=False, default=0)
    requested_unit_cost = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    actual_unit_cost = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    actual_total = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    delivered_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    notes = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    fulfillment = db.relationship("PurchaseFulfillment", back_populates="lines")
    request_item = db.relationship("RequestItem", foreign_keys=[request_item_id])

    @property
    def quantity_variance(self): return float(self.actual_quantity or 0) - float(self.requested_quantity or 0)
    @property
    def cost_variance(self): return float(self.actual_total or 0) - (float(self.requested_quantity or 0) * float(self.requested_unit_cost or 0))


class Attachment(db.Model):
    __tablename__ = "attachments"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    entity_type = db.Column(db.String(60), nullable=False, index=True)
    entity_id = db.Column(db.String(36), nullable=False, index=True)
    kind = db.Column(db.String(60), nullable=False, default="document")
    original_name = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(120), nullable=True)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    sha256 = db.Column(db.String(64), nullable=False, index=True)
    is_final = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    uploaded_by = db.relationship("User")


# ==========================================================
# ITEM CATALOG / INVENTORY
# ==========================================================

class CatalogItem(db.Model):
    __tablename__ = "catalog_items"
    __table_args__ = (db.UniqueConstraint("organization_id", "department_id", "name", name="uq_catalog_org_department_name"),)

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(120), nullable=True)
    unit = db.Column(db.String(60), nullable=False, default="unit")
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_custom = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    department = db.relationship("Department")
    created_by = db.relationship("User")


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    sku = db.Column(db.String(80), nullable=True, index=True)
    category = db.Column(db.String(120), nullable=True)
    unit = db.Column(db.String(60), nullable=False, default="unit")
    quantity = db.Column(db.Numeric(18, 3), nullable=False, default=0)
    unit_value = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    reorder_level = db.Column(db.Numeric(18, 3), nullable=False, default=0)
    location = db.Column(db.String(160), nullable=True)
    added_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    department = db.relationship("Department")
    added_by = db.relationship("User")

    @property
    def total_value(self): return float(self.quantity or 0) * float(self.unit_value or 0)


class StockMovement(db.Model):
    __tablename__ = "stock_movements"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    inventory_item_id = db.Column(db.String(36), db.ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    movement_type = db.Column(db.String(32), nullable=False, index=True)  # stock_in/out/transfer/return/write_off/adjustment
    quantity = db.Column(db.Numeric(18, 3), nullable=False, default=0)
    source = db.Column(db.String(160), nullable=True)
    destination = db.Column(db.String(160), nullable=True)
    reason = db.Column(db.String(500), nullable=True)
    reference = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    item = db.relationship("InventoryItem")
    user = db.relationship("User")


# ==========================================================
# ASSET REGISTER / CUSTODY / MOVEMENT
# ==========================================================

class AssetItem(db.Model):
    __tablename__ = "asset_items"
    __table_args__ = (db.UniqueConstraint("organization_id", "asset_tag", name="uq_asset_org_tag"),)

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    custodian_user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source_request_id = db.Column(db.String(36), db.ForeignKey("purchase_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    category = db.Column(db.String(120), nullable=True)
    asset_tag = db.Column(db.String(80), nullable=False, index=True)
    serial_number = db.Column(db.String(120), nullable=True, index=True)
    quantity = db.Column(db.Numeric(18, 3), nullable=False, default=1)
    unit_value = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    location = db.Column(db.String(160), nullable=True)
    condition = db.Column(db.String(40), nullable=False, default="good")
    status = db.Column(db.String(32), nullable=False, default="active", index=True)  # active / assigned / maintenance / written_off / disposed
    acquired_at = db.Column(db.Date, nullable=True)
    warranty_expiry = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    department = db.relationship("Department", foreign_keys=[department_id])
    custodian = db.relationship("User", foreign_keys=[custodian_user_id])
    source_request = db.relationship("PurchaseRequest", foreign_keys=[source_request_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    @property
    def total_value(self): return float(self.quantity or 0) * float(self.unit_value or 0)


class AssetMovement(db.Model):
    __tablename__ = "asset_movements"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = db.Column(db.String(36), db.ForeignKey("asset_items.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    movement_type = db.Column(db.String(32), nullable=False, index=True)  # register / assign / transfer / return / maintenance / write_off / restore
    quantity = db.Column(db.Numeric(18, 3), nullable=False, default=1)
    source_department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    destination_department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    custodian_user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_location = db.Column(db.String(160), nullable=True)
    destination_location = db.Column(db.String(160), nullable=True)
    reason = db.Column(db.String(500), nullable=True)
    reference = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    asset = db.relationship("AssetItem", foreign_keys=[asset_id])
    user = db.relationship("User", foreign_keys=[user_id])
    custodian = db.relationship("User", foreign_keys=[custodian_user_id])
    source_department = db.relationship("Department", foreign_keys=[source_department_id])
    destination_department = db.relationship("Department", foreign_keys=[destination_department_id])


# ==========================================================
# FINANCE / ACCOUNTABILITY
# ==========================================================

class FinancialRecord(db.Model):
    __tablename__ = "financial_records"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    reference = db.Column(db.String(32), unique=True, nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    record_type = db.Column(db.String(48), nullable=False, index=True)
    category = db.Column(db.String(120), nullable=True)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    status = db.Column(db.String(32), nullable=False, default="posted", index=True)
    source_entity_type = db.Column(db.String(60), nullable=True)
    source_entity_id = db.Column(db.String(36), nullable=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    department = db.relationship("Department")
    created_by = db.relationship("User")


# ==========================================================
# LIVE NOTIFICATIONS / ACTIVITY STREAM
# ==========================================================

class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    level = db.Column(db.String(24), nullable=False, default="info")
    entity_type = db.Column(db.String(60), nullable=True)
    entity_id = db.Column(db.String(36), nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    email_attempted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    user = db.relationship("User")


class ActivityEvent(db.Model):
    __tablename__ = "activity_events"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    action = db.Column(db.String(120), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.String(700), nullable=True)
    entity_type = db.Column(db.String(60), nullable=True, index=True)
    entity_id = db.Column(db.String(36), nullable=True, index=True)
    details_json = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    actor = db.relationship("User", foreign_keys=[actor_id])
    department = db.relationship("Department", foreign_keys=[department_id])

# ==========================================================
# PHASE 4: DEPARTMENT OPERATIONS / STAFF REPORTING
# Every department action is tenant-scoped, timestamped and attributable to the staff member who recorded it.
# ==========================================================

class DepartmentOperation(db.Model):
    __tablename__ = "department_operations"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    reference = db.Column(db.String(32), unique=True, nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    operation_type = db.Column(db.String(80), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    item_name = db.Column(db.String(180), nullable=True)
    quantity = db.Column(db.Numeric(18, 3), nullable=False, default=0)
    unit = db.Column(db.String(60), nullable=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    location = db.Column(db.String(180), nullable=True)
    destination_department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    external_reference = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    details_json = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(32), nullable=False, default="posted", index=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    department = db.relationship("Department", foreign_keys=[department_id])
    destination_department = db.relationship("Department", foreign_keys=[destination_department_id])
    user = db.relationship("User", foreign_keys=[user_id])

    @property
    def display_type(self): return self.operation_type.replace("_", " ").title()


class StaffReport(db.Model):
    __tablename__ = "staff_reports"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    reference = db.Column(db.String(32), unique=True, nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    period_type = db.Column(db.String(24), nullable=False, default="daily", index=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    title = db.Column(db.String(180), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    staff_note = db.Column(db.Text, nullable=True)
    metrics_json = db.Column(db.JSON, nullable=True)
    activity_json = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)  # draft / submitted / acknowledged
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    acknowledged_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    department = db.relationship("Department", foreign_keys=[department_id])
    user = db.relationship("User", foreign_keys=[user_id])
    acknowledged_by = db.relationship("User", foreign_keys=[acknowledged_by_id])

    @property
    def display_status(self): return self.status.replace("_", " ").title()
