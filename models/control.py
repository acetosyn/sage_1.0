"""Additive management controls; existing business tables and records are preserved."""
import uuid
from datetime import datetime, timezone
from packages.database import db


def new_id(): return str(uuid.uuid4())
def utcnow(): return datetime.now(timezone.utc)


class RecordLink(db.Model):
    __tablename__ = "record_links"
    __table_args__ = (db.UniqueConstraint("organization_id", "source_type", "source_id", "target_type", "target_id", "relation", name="uq_record_link"),)
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    source_type = db.Column(db.String(40), nullable=False)
    source_id = db.Column(db.String(36), nullable=False, index=True)
    target_type = db.Column(db.String(40), nullable=False)
    target_id = db.Column(db.String(36), nullable=False, index=True)
    relation = db.Column(db.String(40), nullable=False, default="related")
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class BudgetReservation(db.Model):
    __tablename__ = "budget_reservations"
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    request_id = db.Column(db.String(36), db.ForeignKey("purchase_requests.id"), nullable=False, unique=True)
    budget_id = db.Column(db.String(36), db.ForeignKey("budget_allocations.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    actual_amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="committed")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    budget = db.relationship("BudgetAllocation")


class ReconciliationMatch(db.Model):
    __tablename__ = "reconciliation_matches"
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    reconciliation_id = db.Column(db.String(36), db.ForeignKey("finance_reconciliations.id"), nullable=False, index=True)
    ledger_id = db.Column(db.String(36), db.ForeignKey("finance_ledger_entries.id"), nullable=False, unique=True)
    statement_reference = db.Column(db.String(120), nullable=True)
    matched_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class FinanceVerification(db.Model):
    __tablename__ = "finance_verifications"
    __table_args__ = (db.UniqueConstraint("organization_id", "entity_type", "entity_id", name="uq_finance_verification"),)
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.String(36), nullable=False, index=True)
    verified_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    notes = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    verified_by = db.relationship("User")


class CustodyAcknowledgment(db.Model):
    __tablename__ = "custody_acknowledgments"
    __table_args__ = (db.UniqueConstraint("organization_id", "entity_type", "entity_id", "user_id", "action", name="uq_custody_acknowledgment"),)
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.String(36), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    user = db.relationship("User")


class ManagementTask(db.Model):
    __tablename__ = "management_tasks"
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    assigned_to_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True, index=True)
    title = db.Column(db.String(180), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(20), nullable=False, default="attention")
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    due_date = db.Column(db.Date, nullable=True)
    snoozed_until = db.Column(db.Date, nullable=True)
    entity_type = db.Column(db.String(40), nullable=True)
    entity_id = db.Column(db.String(36), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])


class TaskComment(db.Model):
    __tablename__ = "task_comments"
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    task_id = db.Column(db.String(36), db.ForeignKey("management_tasks.id"), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    user = db.relationship("User")


class DirectPurchaseLine(db.Model):
    __tablename__ = "direct_purchase_lines"
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    ledger_id = db.Column(db.String(36), db.ForeignKey("finance_ledger_entries.id"), nullable=False, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    item_name = db.Column(db.String(180), nullable=False)
    quantity = db.Column(db.Numeric(18, 3), nullable=False)
    unit = db.Column(db.String(60), nullable=False, default="unit")
    unit_cost = db.Column(db.Numeric(18, 2), nullable=False)
    record_as = db.Column(db.String(20), nullable=False)
    inventory_id = db.Column(db.String(36), db.ForeignKey("inventory_items.id"), nullable=True)
    asset_id = db.Column(db.String(36), db.ForeignKey("asset_items.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    ledger = db.relationship("FinanceLedgerEntry")


class ObligationTerms(db.Model):
    __tablename__ = "obligation_terms"
    __table_args__ = (db.UniqueConstraint("organization_id", "entity_type", "entity_id", name="uq_obligation_terms"),)
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    entity_type = db.Column(db.String(20), nullable=False)
    entity_id = db.Column(db.String(36), nullable=False, index=True)
    invoice_date = db.Column(db.Date, nullable=False)
    recorded_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
