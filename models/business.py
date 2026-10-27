"""SAGE 4.0 additive business schema. Existing tables and records are retained."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.orm import declared_attr
from packages.database import db


def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)


class BusinessRow:
    id = db.Column(db.String(36), primary_key=True, default=uid)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id"), index=True)
    branch_id = db.Column(db.String(36), db.ForeignKey("branch_locations.id"), index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now, onupdate=now)
    version = db.Column(db.Integer, nullable=False, default=1)

    @declared_attr
    def __mapper_args__(cls): return {"version_id_col": cls.version}


class BusinessCommand(db.Model):
    __tablename__ = "business_commands"
    __table_args__ = (db.UniqueConstraint("organization_id", "key", name="uq_business_command"),)
    id = db.Column(db.String(36), primary_key=True, default=uid)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False)
    actor_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    key = db.Column(db.String(100), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    result_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)


class BusinessPosting(BusinessRow, db.Model):
    __tablename__ = "business_postings"
    __table_args__ = (db.UniqueConstraint("organization_id", "source_key", name="uq_business_posting"),)
    source_key = db.Column(db.String(180), nullable=False)
    entity_type = db.Column(db.String(60), nullable=False, index=True)
    entity_id = db.Column(db.String(36), nullable=False, index=True)
    ledger_id = db.Column(db.String(36), db.ForeignKey("finance_ledger_entries.id"), nullable=False)
    financial_record_id = db.Column(db.String(36), db.ForeignKey("financial_records.id"))
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    method = db.Column(db.String(60), nullable=False)
    external_reference = db.Column(db.String(120))
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False)


class BranchMembership(BusinessRow, db.Model):
    __tablename__ = "business_branch_memberships"
    __table_args__ = (db.UniqueConstraint("organization_id", "user_id", name="uq_business_user_branch"),)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    is_manager = db.Column(db.Boolean, nullable=False, default=False)


class EventPlan(BusinessRow, db.Model):
    __tablename__ = "business_events"
    parent_id = db.Column(db.String(36), db.ForeignKey("business_events.id"), index=True)
    manager_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    kind = db.Column(db.String(16), nullable=False, default="event")
    category = db.Column(db.String(100), nullable=False)
    objective = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    venue = db.Column(db.String(255))
    start_at = db.Column(db.DateTime(timezone=True), nullable=False)
    end_at = db.Column(db.DateTime(timezone=True), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)
    requested = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    approved = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    released = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    spent = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    returned = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    expected_reach = db.Column(db.Integer, nullable=False, default=0)
    expected_leads = db.Column(db.Integer, nullable=False, default=0)
    expected_customers = db.Column(db.Integer, nullable=False, default=0)
    expected_revenue = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    staffing = db.Column(db.Text)
    notes = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime(timezone=True))
    approved_at = db.Column(db.DateTime(timezone=True))
    approved_by_id = db.Column(db.String(36), db.ForeignKey("users.id"))
    funded_at = db.Column(db.DateTime(timezone=True))
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    closed_at = db.Column(db.DateTime(timezone=True))


class EventBudget(BusinessRow, db.Model):
    __tablename__ = "business_event_budgets"
    event_id = db.Column(db.String(36), db.ForeignKey("business_events.id"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)


class EventCash(BusinessRow, db.Model):
    __tablename__ = "business_event_cash"
    event_id = db.Column(db.String(36), db.ForeignKey("business_events.id"), nullable=False, index=True)
    receiver_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    kind = db.Column(db.String(16), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    posting_id = db.Column(db.String(36), db.ForeignKey("business_postings.id"), nullable=False)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False)


class EventExpense(BusinessRow, db.Model):
    __tablename__ = "business_event_expenses"
    event_id = db.Column(db.String(36), db.ForeignKey("business_events.id"), nullable=False, index=True)
    budget_id = db.Column(db.String(36), db.ForeignKey("business_event_budgets.id"))
    description = db.Column(db.String(300), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    posting_id = db.Column(db.String(36), db.ForeignKey("business_postings.id"), nullable=False)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False)


class EventResource(BusinessRow, db.Model):
    __tablename__ = "business_event_resources"
    event_id = db.Column(db.String(36), db.ForeignKey("business_events.id"), nullable=False, index=True)
    inventory_id = db.Column(db.String(36), db.ForeignKey("inventory_items.id"))
    asset_id = db.Column(db.String(36), db.ForeignKey("asset_items.id"))
    name = db.Column(db.String(180), nullable=False)
    issued = db.Column(db.Numeric(18, 3), nullable=False)
    returned = db.Column(db.Numeric(18, 3), nullable=False, default=0)
    distributed = db.Column(db.Numeric(18, 3), nullable=False, default=0)
    missing = db.Column(db.Numeric(18, 3), nullable=False, default=0)
    resolved_at = db.Column(db.DateTime(timezone=True))
    resolution = db.Column(db.Text)


class EventReport(BusinessRow, db.Model):
    __tablename__ = "business_event_reports"
    __table_args__ = (db.UniqueConstraint("event_id", name="uq_event_report"),)
    event_id = db.Column(db.String(36), db.ForeignKey("business_events.id"), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    successful = db.Column(db.Boolean, nullable=False)
    reach = db.Column(db.Integer, nullable=False, default=0)
    leads = db.Column(db.Integer, nullable=False, default=0)
    prospects = db.Column(db.Integer, nullable=False, default=0)
    customers = db.Column(db.Integer, nullable=False, default=0)
    sales = db.Column(db.Integer, nullable=False, default=0)
    revenue = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    challenges = db.Column(db.Text)
    lessons = db.Column(db.Text, nullable=False)
    follow_up = db.Column(db.Text, nullable=False)
    objective_status = db.Column(db.String(24), nullable=False)
    comments = db.Column(db.Text)
    management_review = db.Column(db.Text)
    reviewed_by_id = db.Column(db.String(36), db.ForeignKey("users.id"))


class Customer(BusinessRow, db.Model):
    __tablename__ = "business_customers"
    name = db.Column(db.String(180), nullable=False, index=True)
    phone = db.Column(db.String(80))
    email = db.Column(db.String(180))
    business = db.Column(db.String(180))
    address = db.Column(db.String(255))
    stage = db.Column(db.String(24), nullable=False, default="lead", index=True)
    event_id = db.Column(db.String(36), db.ForeignKey("business_events.id"), index=True)
    assigned_to_id = db.Column(db.String(36), db.ForeignKey("users.id"))
    next_follow_up = db.Column(db.Date, index=True)
    notes = db.Column(db.Text)


class CustomerActivity(BusinessRow, db.Model):
    __tablename__ = "business_customer_activities"
    customer_id = db.Column(db.String(36), db.ForeignKey("business_customers.id"), nullable=False, index=True)
    kind = db.Column(db.String(24), nullable=False)
    notes = db.Column(db.Text, nullable=False)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)


class SalesInvoice(BusinessRow, db.Model):
    __tablename__ = "business_sales_invoices"
    __table_args__ = (db.UniqueConstraint("organization_id", "number", name="uq_business_invoice_number"),)
    customer_id = db.Column(db.String(36), db.ForeignKey("business_customers.id"), nullable=False, index=True)
    event_id = db.Column(db.String(36), db.ForeignKey("business_events.id"), index=True)
    sales_person_id = db.Column(db.String(36), db.ForeignKey("users.id"))
    receivable_id = db.Column(db.String(36), db.ForeignKey("finance_receivables.id"), unique=True)
    number = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    currency = db.Column(db.String(12), nullable=False)
    subtotal = db.Column(db.Numeric(18, 2), nullable=False)
    discount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    tax = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(18, 2), nullable=False)
    paid = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    due_date = db.Column(db.Date, index=True)
    issued_at = db.Column(db.DateTime(timezone=True), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="issued", index=True)
    closed_at = db.Column(db.DateTime(timezone=True))
    # Future e-invoicing transmission is a separate lifecycle from a business sale.
    external_invoice_id = db.Column(db.String(180))
    transmission_status = db.Column(db.String(24), nullable=False, default="not_submitted")
    tax_metadata = db.Column(db.JSON)


class SalesLine(BusinessRow, db.Model):
    __tablename__ = "business_sales_lines"
    invoice_id = db.Column(db.String(36), db.ForeignKey("business_sales_invoices.id"), nullable=False, index=True)
    inventory_id = db.Column(db.String(36), db.ForeignKey("inventory_items.id"))
    description = db.Column(db.String(180), nullable=False)
    quantity = db.Column(db.Numeric(18, 3), nullable=False)
    unit_price = db.Column(db.Numeric(18, 2), nullable=False)
    cost_price = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(18, 2), nullable=False)


class InvoicePayment(BusinessRow, db.Model):
    __tablename__ = "business_invoice_payments"
    invoice_id = db.Column(db.String(36), db.ForeignKey("business_sales_invoices.id"), nullable=False, index=True)
    posting_id = db.Column(db.String(36), db.ForeignKey("business_postings.id"), nullable=False, unique=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False)


class SupplierProfile(BusinessRow, db.Model):
    __tablename__ = "business_supplier_profiles"
    supplier_id = db.Column(db.String(36), db.ForeignKey("suppliers.id"), nullable=False, unique=True)
    contact_person = db.Column(db.String(180))
    bank_name = db.Column(db.String(160))
    bank_account = db.Column(db.String(80))
    account_name = db.Column(db.String(180))
    tin = db.Column(db.String(80))
    offerings = db.Column(db.Text)
    rating = db.Column(db.Integer)


class SupplierQuotation(BusinessRow, db.Model):
    __tablename__ = "business_supplier_quotations"
    supplier_id = db.Column(db.String(36), db.ForeignKey("suppliers.id"), nullable=False, index=True)
    request_id = db.Column(db.String(36), db.ForeignKey("purchase_requests.id"))
    description = db.Column(db.String(300), nullable=False)
    quoted = db.Column(db.Numeric(18, 2), nullable=False)
    negotiated = db.Column(db.Numeric(18, 2), nullable=False)
    quantity = db.Column(db.Numeric(18, 3), nullable=False)
    delivered = db.Column(db.Numeric(18, 3), nullable=False, default=0)
    promised_date = db.Column(db.Date)
    delivered_at = db.Column(db.DateTime(timezone=True))


class SupplierBill(BusinessRow, db.Model):
    __tablename__ = "business_supplier_bills"
    supplier_id = db.Column(db.String(36), db.ForeignKey("suppliers.id"), nullable=False, index=True)
    payable_id = db.Column(db.String(36), db.ForeignKey("finance_payables.id"), nullable=False, unique=True)
    fulfillment_id = db.Column(db.String(36), db.ForeignKey("purchase_fulfillments.id"), unique=True)


class ImprestFund(BusinessRow, db.Model):
    __tablename__ = "business_imprest_funds"
    holder_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    ceiling = db.Column(db.Numeric(18, 2), nullable=False)
    issued = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    spent = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    returned = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    status = db.Column(db.String(24), nullable=False, default="active")
    closed_at = db.Column(db.DateTime(timezone=True))


class ImprestEntry(BusinessRow, db.Model):
    __tablename__ = "business_imprest_entries"
    fund_id = db.Column(db.String(36), db.ForeignKey("business_imprest_funds.id"), nullable=False, index=True)
    kind = db.Column(db.String(24), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    posting_id = db.Column(db.String(36), db.ForeignKey("business_postings.id"), nullable=False)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False)


class ImprestReplenishment(BusinessRow, db.Model):
    __tablename__ = "business_imprest_replenishments"
    fund_id = db.Column(db.String(36), db.ForeignKey("business_imprest_funds.id"), nullable=False, index=True)
    request_id = db.Column(db.String(36), db.ForeignKey("purchase_requests.id"), nullable=False, unique=True)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="submitted")
    paid_at = db.Column(db.DateTime(timezone=True))


class BusinessRecordScope(BusinessRow, db.Model):
    __tablename__ = "business_record_scopes"
    __table_args__ = (db.UniqueConstraint('organization_id','entity_type','entity_id',name='uq_business_record_scope'),)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.String(36), nullable=False, index=True)


class BranchAccount(BusinessRow, db.Model):
    __tablename__ = "business_branch_accounts"
    account_id = db.Column(db.String(36), db.ForeignKey('finance_accounts.id'), nullable=False, unique=True)


class DailyClose(BusinessRow, db.Model):
    __tablename__ = "business_daily_closes"
    __table_args__ = (db.UniqueConstraint('organization_id','scope_key','business_date',name='uq_business_daily_close'),)
    scope_key = db.Column(db.String(80), nullable=False)
    business_date = db.Column(db.Date, nullable=False, index=True)
    expected_json = db.Column(db.JSON, nullable=False)
    counted_json = db.Column(db.JSON, nullable=False)
    ledger_ids = db.Column(db.JSON, nullable=False)
    expected_total = db.Column(db.Numeric(18, 2), nullable=False)
    counted_total = db.Column(db.Numeric(18, 2), nullable=False)
    variance = db.Column(db.Numeric(18, 2), nullable=False)
    explanation = db.Column(db.Text)
    status = db.Column(db.String(24), nullable=False, default='draft')
    submitted_at = db.Column(db.DateTime(timezone=True))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    reviewed_by_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    review_notes = db.Column(db.Text)


class StockProfile(BusinessRow, db.Model):
    __tablename__ = 'business_stock_profiles'
    inventory_id = db.Column(db.String(36), db.ForeignKey('inventory_items.id'), nullable=False, unique=True)
    selling_price = db.Column(db.Numeric(18,2), nullable=False, default=0)


class StockBatch(BusinessRow, db.Model):
    __tablename__ = 'business_stock_batches'
    __table_args__ = (db.UniqueConstraint('organization_id','inventory_id','number',name='uq_business_stock_batch'),)
    inventory_id = db.Column(db.String(36), db.ForeignKey('inventory_items.id'), nullable=False, index=True)
    fulfillment_id = db.Column(db.String(36), db.ForeignKey('purchase_fulfillments.id'))
    number = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Numeric(18,3), nullable=False)
    cost_price = db.Column(db.Numeric(18,2), nullable=False)
    expiry_date = db.Column(db.Date, index=True)
    received_at = db.Column(db.DateTime(timezone=True), nullable=False)


class StockAllocation(BusinessRow, db.Model):
    __tablename__ = 'business_stock_allocations'
    inventory_id = db.Column(db.String(36), db.ForeignKey('inventory_items.id'), nullable=False, index=True)
    batch_id = db.Column(db.String(36), db.ForeignKey('business_stock_batches.id'))
    source_type = db.Column(db.String(80), nullable=False)
    source_id = db.Column(db.String(36), nullable=False, index=True)
    quantity = db.Column(db.Numeric(18,3), nullable=False)
    returned = db.Column(db.Numeric(18,3), nullable=False, default=0)


class StockCount(BusinessRow, db.Model):
    __tablename__ = 'business_stock_counts'
    inventory_id = db.Column(db.String(36), db.ForeignKey('inventory_items.id'), nullable=False, index=True)
    expected = db.Column(db.Numeric(18,3), nullable=False)
    counted = db.Column(db.Numeric(18,3), nullable=False)
    variance = db.Column(db.Numeric(18,3), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    approved_by_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime(timezone=True))


class BillPlan(BusinessRow, db.Model):
    __tablename__ = 'business_bills'
    supplier_id = db.Column(db.String(36), db.ForeignKey('suppliers.id'))
    responsible_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(18,2), nullable=False)
    frequency = db.Column(db.String(24), nullable=False)
    first_due = db.Column(db.Date, nullable=False)
    next_due = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(24), nullable=False, default='active')
    notes = db.Column(db.Text)
    closed_at = db.Column(db.DateTime(timezone=True))


class BillPayment(BusinessRow, db.Model):
    __tablename__ = 'business_bill_payments'
    __table_args__ = (db.UniqueConstraint('bill_id','period_due',name='uq_business_bill_period'),)
    bill_id = db.Column(db.String(36), db.ForeignKey('business_bills.id'), nullable=False, index=True)
    period_due = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(18,2), nullable=False)
    posting_id = db.Column(db.String(36), db.ForeignKey('business_postings.id'), nullable=False)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=False)


class ComplianceDocument(BusinessRow, db.Model):
    __tablename__ = 'business_compliance_documents'
    responsible_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    bill_id = db.Column(db.String(36), db.ForeignKey('business_bills.id'))
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    identifier = db.Column(db.String(180))
    issued_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(24), nullable=False, default='active')
    notes = db.Column(db.Text)
    renewed_at = db.Column(db.DateTime(timezone=True))


class ComplianceRenewal(BusinessRow, db.Model):
    __tablename__ = 'business_compliance_renewals'
    document_id = db.Column(db.String(36), db.ForeignKey('business_compliance_documents.id'), nullable=False, index=True)
    previous_expiry = db.Column(db.Date, nullable=False)
    new_expiry = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=False)


class BusinessReminder(BusinessRow, db.Model):
    __tablename__ = 'business_reminders'
    __table_args__ = (db.UniqueConstraint('organization_id','dedupe_key',name='uq_business_reminder'),)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    dedupe_key = db.Column(db.String(240), nullable=False)
    notification_id = db.Column(db.String(36), db.ForeignKey('notifications.id'), nullable=False)


class EmployeeProfile(BusinessRow, db.Model):
    __tablename__ = 'business_employee_profiles'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, unique=True)
    employment_date = db.Column(db.Date, nullable=False)
    salary = db.Column(db.Numeric(18,2), nullable=False, default=0)
    allowance = db.Column(db.Numeric(18,2), nullable=False, default=0)
    commission_rate = db.Column(db.Numeric(8,3), nullable=False, default=0)
    paye = db.Column(db.Numeric(18,2), nullable=False, default=0)
    pension_rate = db.Column(db.Numeric(8,3), nullable=False, default=0)
    employer_pension_rate = db.Column(db.Numeric(8,3), nullable=False, default=0)
    other_deduction = db.Column(db.Numeric(18,2), nullable=False, default=0)
    loan_deduction = db.Column(db.Numeric(18,2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.Text)


class StaffAdvance(BusinessRow, db.Model):
    __tablename__ = 'business_staff_advances'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    kind = db.Column(db.String(24), nullable=False)
    amount = db.Column(db.Numeric(18,2), nullable=False)
    repaid = db.Column(db.Numeric(18,2), nullable=False, default=0)
    due_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(24), nullable=False, default='submitted')
    approved_by_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime(timezone=True))
    issued_at = db.Column(db.DateTime(timezone=True))
    settled_at = db.Column(db.DateTime(timezone=True))


class ExpenseClaim(BusinessRow, db.Model):
    __tablename__ = 'business_expense_claims'
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    description = db.Column(db.String(300), nullable=False)
    amount = db.Column(db.Numeric(18,2), nullable=False)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False)
    status = db.Column(db.String(24), nullable=False, default='submitted')
    reviewed_by_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    review_notes = db.Column(db.Text)
    paid_at = db.Column(db.DateTime(timezone=True))


class PayrollRun(BusinessRow, db.Model):
    __tablename__ = 'business_payroll_runs'
    name = db.Column(db.String(180), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(24), nullable=False, default='draft')
    approved_by_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime(timezone=True))
    paid_at = db.Column(db.DateTime(timezone=True))
    remitted_at = db.Column(db.DateTime(timezone=True))
    notes = db.Column(db.Text)


class PayrollSlip(BusinessRow, db.Model):
    __tablename__ = 'business_payroll_slips'
    __table_args__ = (db.UniqueConstraint('organization_id','user_id','period_start',name='uq_business_employee_payroll_month'),)
    run_id = db.Column(db.String(36), db.ForeignKey('business_payroll_runs.id'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    payroll_entry_id = db.Column(db.String(36), db.ForeignKey('payroll_entries.id'), nullable=False, unique=True)
    tax_entry_id = db.Column(db.String(36), db.ForeignKey('tax_entries.id'))
    period_start = db.Column(db.Date, nullable=False)
    salary = db.Column(db.Numeric(18,2), nullable=False)
    allowance = db.Column(db.Numeric(18,2), nullable=False)
    bonus = db.Column(db.Numeric(18,2), nullable=False, default=0)
    sales = db.Column(db.Numeric(18,2), nullable=False)
    commission_rate = db.Column(db.Numeric(8,3), nullable=False)
    commission = db.Column(db.Numeric(18,2), nullable=False)
    gross = db.Column(db.Numeric(18,2), nullable=False)
    paye = db.Column(db.Numeric(18,2), nullable=False)
    pension = db.Column(db.Numeric(18,2), nullable=False)
    employer_pension = db.Column(db.Numeric(18,2), nullable=False)
    other_deduction = db.Column(db.Numeric(18,2), nullable=False)
    advance_deduction = db.Column(db.Numeric(18,2), nullable=False)
    net = db.Column(db.Numeric(18,2), nullable=False)
    notes = db.Column(db.Text)


class PayrollAdvanceRecovery(BusinessRow, db.Model):
    __tablename__ = 'business_payroll_advance_recoveries'
    slip_id = db.Column(db.String(36), db.ForeignKey('business_payroll_slips.id'), nullable=False)
    advance_id = db.Column(db.String(36), db.ForeignKey('business_staff_advances.id'), nullable=False)
    amount = db.Column(db.Numeric(18,2), nullable=False)


class AutomationRun(BusinessRow, db.Model):
    __tablename__ = 'business_automation_runs'
    scope_key = db.Column(db.String(80), nullable=False, index=True)
    reminders_created = db.Column(db.Integer, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)


class EventTransfer(BusinessRow, db.Model):
    __tablename__ = 'business_event_transfers'
    campaign_id = db.Column(db.String(36), db.ForeignKey('business_events.id'), nullable=False, index=True)
    event_id = db.Column(db.String(36), db.ForeignKey('business_events.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(18,2), nullable=False)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    notes = db.Column(db.Text, nullable=False)
