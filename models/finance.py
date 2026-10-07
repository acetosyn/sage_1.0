# MODELS: SAGE Finance & Accounts Control Centre
# Dedicated Phase 5 finance schema for accounts, ledger posting, budgets, AR/AP, reconciliation, payroll, tax and forecasts.

import uuid
from datetime import datetime, timezone
from packages.database import db


def new_id(): return str(uuid.uuid4())
def utcnow(): return datetime.now(timezone.utc)


# ==========================================================
# CASH / BANK / POS / WALLET ACCOUNTS
# ==========================================================

class FinanceAccount(db.Model):
    __tablename__ = "finance_accounts"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    account_type = db.Column(db.String(40), nullable=False, default="bank", index=True)  # bank / cash / pos / wallet / petty_cash / other
    institution = db.Column(db.String(160), nullable=True)
    account_reference = db.Column(db.String(120), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    opening_balance = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    created_by = db.relationship("User", foreign_keys=[created_by_id])


# ==========================================================
# DOUBLE-SIDED OPERATIONAL LEDGER
# Rich finance posting data; FinancialRecord remains the summary-compatible source for existing dashboards.
# ==========================================================

class FinanceLedgerEntry(db.Model):
    __tablename__ = "finance_ledger_entries"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    reference = db.Column(db.String(36), unique=True, nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    account_id = db.Column(db.String(36), db.ForeignKey("finance_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    budget_id = db.Column(db.String(36), db.ForeignKey("budget_allocations.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    entry_type = db.Column(db.String(48), nullable=False, index=True)  # income/revenue/expense/expenditure/payroll/tax/operating_cost/liability/cash_in/cash_out/adjustment
    direction = db.Column(db.String(12), nullable=False, default="out", index=True)  # in / out / neutral
    category = db.Column(db.String(120), nullable=True, index=True)
    counterparty = db.Column(db.String(180), nullable=True)
    description = db.Column(db.String(300), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    payment_method = db.Column(db.String(60), nullable=True)
    external_reference = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="posted", index=True)  # draft / posted / reconciled / void
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    due_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    source_entity_type = db.Column(db.String(60), nullable=True)
    source_entity_id = db.Column(db.String(36), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    posted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reconciled_at = db.Column(db.DateTime(timezone=True), nullable=True)

    department = db.relationship("Department", foreign_keys=[department_id])
    account = db.relationship("FinanceAccount", foreign_keys=[account_id])
    budget = db.relationship("BudgetAllocation", foreign_keys=[budget_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    @property
    def display_type(self): return self.entry_type.replace("_", " ").title()


# ==========================================================
# BUDGETS / COST CENTRES
# Tracks original allocation, revisions, committed spend and actual spend separately.
# ==========================================================

class BudgetAllocation(db.Model):
    __tablename__ = "budget_allocations"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(120), nullable=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    original_budget = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    revised_budget = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    committed_amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    actual_spend = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    status = db.Column(db.String(24), nullable=False, default="active", index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    department = db.relationship("Department", foreign_keys=[department_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    @property
    def total_budget(self): return float(self.revised_budget or self.original_budget or 0)
    @property
    def available_balance(self): return self.total_budget - float(self.committed_amount or 0) - float(self.actual_spend or 0)
    @property
    def utilization_percent(self): return min(100.0, ((float(self.committed_amount or 0) + float(self.actual_spend or 0)) / self.total_budget * 100.0)) if self.total_budget else 0.0


# ==========================================================
# ACCOUNTS RECEIVABLE / PAYABLE
# ==========================================================

class FinanceReceivable(db.Model):
    __tablename__ = "finance_receivables"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    reference = db.Column(db.String(36), unique=True, nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    customer_name = db.Column(db.String(180), nullable=False)
    invoice_number = db.Column(db.String(120), nullable=True, index=True)
    description = db.Column(db.String(300), nullable=False)
    total_amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    amount_received = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    due_date = db.Column(db.Date, nullable=True, index=True)
    status = db.Column(db.String(24), nullable=False, default="open", index=True)  # open / partial / paid / overdue / cancelled
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    department = db.relationship("Department", foreign_keys=[department_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    @property
    def balance(self): return max(0.0, float(self.total_amount or 0) - float(self.amount_received or 0))


class FinancePayable(db.Model):
    __tablename__ = "finance_payables"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    reference = db.Column(db.String(36), unique=True, nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    vendor_name = db.Column(db.String(180), nullable=False)
    bill_number = db.Column(db.String(120), nullable=True, index=True)
    description = db.Column(db.String(300), nullable=False)
    total_amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    due_date = db.Column(db.Date, nullable=True, index=True)
    status = db.Column(db.String(24), nullable=False, default="open", index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    department = db.relationship("Department", foreign_keys=[department_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    @property
    def balance(self): return max(0.0, float(self.total_amount or 0) - float(self.amount_paid or 0))


# ==========================================================
# RECONCILIATION / PAYROLL / TAX / FORECASTING
# ==========================================================

class FinanceReconciliation(db.Model):
    __tablename__ = "finance_reconciliations"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = db.Column(db.String(36), db.ForeignKey("finance_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    completed_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    statement_balance = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    system_balance = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    variance = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    status = db.Column(db.String(24), nullable=False, default="open", index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    account = db.relationship("FinanceAccount", foreign_keys=[account_id])
    completed_by = db.relationship("User", foreign_keys=[completed_by_id])


class PayrollEntry(db.Model):
    __tablename__ = "payroll_entries"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    staff_name = db.Column(db.String(180), nullable=False)
    employee_reference = db.Column(db.String(100), nullable=True)
    pay_period = db.Column(db.String(80), nullable=False, index=True)
    gross_pay = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    deductions = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    net_pay = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    department = db.relationship("Department", foreign_keys=[department_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])


class TaxEntry(db.Model):
    __tablename__ = "tax_entries"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tax_type = db.Column(db.String(120), nullable=False)
    authority = db.Column(db.String(180), nullable=True)
    period = db.Column(db.String(100), nullable=False)
    taxable_amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="due", index=True)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    department = db.relationship("Department", foreign_keys=[department_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])


class FinanceForecast(db.Model):
    __tablename__ = "finance_forecasts"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = db.Column(db.String(180), nullable=False)
    forecast_type = db.Column(db.String(48), nullable=False, index=True)  # revenue / expense / cashflow / profit
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    currency = db.Column(db.String(12), nullable=False, default="NGN")
    assumptions = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    department = db.relationship("Department", foreign_keys=[department_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
