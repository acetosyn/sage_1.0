# SERVICE: SAGE Phase 5 Finance & Accounts Engine
# Centralizes finance posting, account balances, budgets, AR/AP, reconciliation, payroll, taxes, forecasts and finance reporting.

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from sqlalchemy import func
from models import BudgetAllocation, Department, FinanceAccount, FinanceForecast, FinanceLedgerEntry, FinancePayable, FinanceReceivable, FinanceReconciliation, FinancialRecord, PayrollEntry, PurchaseRequest, TaxEntry
from packages.database import db
from services.notification_service import record_activity
from services.management_service import record_revision
from services.storage_service import save_attachment

LEDGER_TYPES = {"income", "revenue", "expense", "expenditure", "payroll", "tax", "operating_cost", "liability", "cash_in", "cash_out", "adjustment"}
ACCOUNT_TYPES = {"bank", "cash", "pos", "wallet", "petty_cash", "other"}
FORECAST_TYPES = {"revenue", "expense", "cashflow", "profit"}
OUTFLOW_TYPES = {"expense", "expenditure", "payroll", "tax", "operating_cost", "cash_out"}
INFLOW_TYPES = {"income", "revenue", "cash_in"}


def _money(value, default="0"):
    try:
        result = Decimal(str(value if value not in (None, "") else default)).quantize(Decimal("0.01"))
        if not result.is_finite(): raise ValueError("Enter a finite amount.")
        return result
    except (InvalidOperation, ValueError): raise ValueError("Enter a valid amount.")


def _parse_date(value, required=False):
    if isinstance(value, date): return value
    text = str(value or "").strip()
    if not text:
        if required: raise ValueError("A date is required.")
        return None
    try: return date.fromisoformat(text[:10])
    except ValueError: raise ValueError("Enter a valid date.")


def _parse_datetime(value):
    text = str(value or "").strip()
    if not text: return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00")); return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except ValueError: raise ValueError("Enter a valid transaction date/time.")


def _next_ref(prefix, model, organization_id):
    """Generate a tenant-readable reference that remains globally unique across millions of organizations."""
    today = datetime.now(timezone.utc).strftime("%y%m%d"); org_code = str(organization_id or "ORG").replace("-", "")[:6].upper(); pattern = f"{prefix}-{org_code}-{today}-%"; count = model.query.filter(getattr(model, "organization_id") == organization_id, getattr(model, "reference").like(pattern)).count() + 1
    return f"{prefix}-{org_code}-{today}-{count:04d}"


def _assert_department(user, department_id):
    if not department_id: return user.department if user.department_id else None
    row = Department.query.filter_by(id=department_id, organization_id=user.organization_id).first()
    if not row: raise ValueError("Choose a valid department in your organization.")
    return row


def _account_balance(account):
    if not account: return 0.0
    rows = FinanceLedgerEntry.query.filter_by(organization_id=account.organization_id, account_id=account.id).filter(FinanceLedgerEntry.status.in_(["posted", "reconciled"])).all(); balance = float(account.opening_balance or 0)
    for row in rows:
        amount = float(row.amount or 0); balance += amount if row.direction == "in" else (-amount if row.direction == "out" else 0)
    return balance


def _finance_record_type(entry_type):
    if entry_type in {"income", "revenue", "expense", "expenditure", "payroll", "tax", "operating_cost", "liability"}: return entry_type
    # Cash movement alone is not revenue or an expense (for example an advance or return).
    return None


# ==========================================================
# ACCOUNTS / LEDGER POSTING
# ==========================================================

def create_finance_account(app, user, payload):
    name = str(payload.get("name") or "").strip(); account_type = str(payload.get("account_type") or "bank").strip().lower()
    if not name: raise ValueError("Account name is required.")
    if account_type not in ACCOUNT_TYPES: raise ValueError("Choose a valid account type.")
    row = FinanceAccount(organization_id=user.organization_id, name=name, account_type=account_type, institution=str(payload.get("institution") or "").strip() or None, account_reference=str(payload.get("account_reference") or "").strip() or None, currency=user.organization.currency, opening_balance=_money(payload.get("opening_balance")), created_by_id=user.id); db.session.add(row); db.session.flush()
    record_activity(app, user, "finance_account_created", "Finance account created", f"{user.display_name} created finance account {row.name} ({row.account_type.replace('_',' ').title()}).", "finance_account", row.id, {"account_type": row.account_type}, notify_owner=user.role not in {"owner", "admin"}); db.session.commit(); return row


def post_ledger_entry(app, user, form, receipt=None):
    entry_type = str(form.get("entry_type") or "").strip().lower(); amount = _money(form.get("amount")); status = str(form.get("status") or "posted").strip().lower(); department = _assert_department(user, form.get("department_id")); account = FinanceAccount.query.filter_by(id=form.get("account_id"), organization_id=user.organization_id).first() if form.get("account_id") else None; budget = BudgetAllocation.query.filter_by(id=form.get("budget_id"), organization_id=user.organization_id).first() if form.get("budget_id") else None
    if entry_type not in LEDGER_TYPES: raise ValueError("Choose a valid finance entry type.")
    if amount <= 0: raise ValueError("Amount must be greater than zero.")
    if form.get("linked_request_id") and form.get("record_as") in {"stock", "asset"}: raise ValueError("A linked purchase payment must use Finance only; its acquisition already records the items.")
    if form.get("account_id") and not account: raise ValueError("Choose an account from this organization.")
    if form.get("budget_id") and not budget: raise ValueError("Choose a budget from this organization.")
    if budget and budget.department_id not in (None, department.id if department else None): raise ValueError("Budget and transaction department do not match.")
    if status not in {"draft", "posted"}: status = "posted"
    direction = "in" if entry_type in INFLOW_TYPES else ("out" if entry_type in OUTFLOW_TYPES else "neutral")
    description = str(form.get("description") or "").strip()
    if not description: raise ValueError("Description is required.")
    row = FinanceLedgerEntry(reference=_next_ref("LED", FinanceLedgerEntry, user.organization_id), organization_id=user.organization_id, department_id=department.id if department else None, account_id=account.id if account else None, budget_id=budget.id if budget else None, created_by_id=user.id, entry_type=entry_type, direction=direction, category=str(form.get("category") or "").strip() or None, counterparty=str(form.get("counterparty") or "").strip() or None, description=description, amount=amount, currency=user.organization.currency, payment_method=str(form.get("payment_method") or "").strip() or None, external_reference=str(form.get("external_reference") or "").strip() or None, status=status, occurred_at=_parse_datetime(form.get("occurred_at")), due_date=_parse_date(form.get("due_date")), notes=str(form.get("notes") or "").strip() or None, posted_at=datetime.now(timezone.utc) if status == "posted" else None); db.session.add(row); db.session.flush()
    if receipt: save_attachment(app, receipt, user, "finance_ledger", row.id, kind="finance", final=status == "posted")
    if status == "posted":
        summary_type = _finance_record_type(entry_type)
        if summary_type and not form.get("linked_request_id"):
            legacy = FinancialRecord(reference=_next_ref("FIN", FinancialRecord, user.organization_id), organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id, record_type=summary_type, category=row.category, description=row.description, amount=row.amount, currency=row.currency, status="posted", source_entity_type="finance_ledger", source_entity_id=row.id, occurred_at=row.occurred_at); db.session.add(legacy)
        if budget and direction == "out" and summary_type and not form.get("linked_request_id"): budget.actual_spend = _money(budget.actual_spend) + amount; budget.committed_amount = max(Decimal("0"), _money(budget.committed_amount) - amount)
    if form.get("linked_request_id"):
        purchase = PurchaseRequest.query.filter_by(id=form.get("linked_request_id"), organization_id=user.organization_id).first()
        if not purchase or purchase.status not in {"approved", "money_sent", "fulfilled", "verified"}: raise ValueError("Choose an approved purchase from this organization.")
        if direction != "out": raise ValueError("A purchase payment must be a cash outflow.")
        from models import RecordLink
        row.source_entity_type, row.source_entity_id = "request", purchase.id
        db.session.add(RecordLink(organization_id=user.organization_id, source_type="finance_ledger", source_id=row.id, target_type="request", target_id=purchase.id, relation="payment", created_by_id=user.id))
    if direction == "out" and entry_type in {"expense", "expenditure"} and row.counterparty:
        from services.management_service import ensure_supplier
        ensure_supplier(user, row.counterparty)
    if form.get("record_as") in {"stock", "asset"}:
        if not receipt or not receipt.filename: raise ValueError("Attach the actual receipt/invoice for this direct purchase.")
        from services.direct_purchase_service import post_direct_items
        post_direct_items(user, row, form)
    record_activity(app, user, "finance_ledger_posted" if status == "posted" else "finance_ledger_draft", "Money in recorded" if status == "posted" and direction == "in" else ("Finance transaction posted" if status == "posted" else "Finance draft saved"), f"{user.display_name} {'recorded' if direction == 'in' else ('posted' if status == 'posted' else 'saved')} {row.display_type}: {row.currency} {float(row.amount):,.2f} · {row.description}{' · Source: ' + row.counterparty if row.counterparty else ''}{' · ' + row.payment_method if row.payment_method else ''}.", "finance_ledger", row.id, {"type": entry_type, "amount": float(amount), "department": department.name if department else None, "account": account.name if account else None, "counterparty": row.counterparty, "payment_method": row.payment_method, "reference": row.external_reference}, notify_owner=user.role not in {"owner", "admin"}, email_owner=status == "posted"); db.session.commit(); return row


# ==========================================================
# BUDGETS / RECEIVABLES / PAYABLES
# ==========================================================

def create_budget(app, user, payload):
    department = _assert_department(user, payload.get("department_id")); original = _money(payload.get("original_budget")); revised = _money(payload.get("revised_budget"), original)
    if not str(payload.get("name") or "").strip(): raise ValueError("Budget name is required.")
    if original < 0 or revised < 0 or _money(payload.get("committed_amount")) < 0 or _money(payload.get("actual_spend")) < 0: raise ValueError("Budget amounts cannot be negative.")
    if _parse_date(payload.get("period_start"), True) > _parse_date(payload.get("period_end"), True): raise ValueError("Budget end date precedes its start.")
    row = BudgetAllocation(organization_id=user.organization_id, department_id=department.id if department else None, created_by_id=user.id, name=str(payload.get("name")).strip(), category=str(payload.get("category") or "").strip() or None, period_start=_parse_date(payload.get("period_start"), True), period_end=_parse_date(payload.get("period_end"), True), original_budget=original, revised_budget=revised, committed_amount=_money(payload.get("committed_amount")), actual_spend=_money(payload.get("actual_spend")), notes=str(payload.get("notes") or "").strip() or None); db.session.add(row); db.session.flush(); record_activity(app, user, "budget_created", "Budget created", f"{user.display_name} created {row.name} budget of {user.organization.currency} {row.total_budget:,.2f}.", "budget", row.id, {"department": department.name if department else None, "budget": row.total_budget}, notify_owner=user.role not in {"owner", "admin"}); db.session.commit(); return row


def create_receivable(app, user, payload):
    department = _assert_department(user, payload.get("department_id")); total = _money(payload.get("total_amount")); received = _money(payload.get("amount_received")); status = "paid" if received >= total and total > 0 else ("partial" if received > 0 else "open")
    if not str(payload.get("customer_name") or "").strip(): raise ValueError("Customer/payer name is required.")
    if total <= 0 or received < 0 or received > total: raise ValueError("Enter a positive total and an opening receipt between zero and the total.")
    row = FinanceReceivable(reference=_next_ref("AR", FinanceReceivable, user.organization_id), organization_id=user.organization_id, department_id=department.id if department else None, created_by_id=user.id, customer_name=str(payload.get("customer_name")).strip(), invoice_number=str(payload.get("invoice_number") or "").strip() or None, description=str(payload.get("description") or "Receivable").strip(), total_amount=total, amount_received=received, currency=user.organization.currency, due_date=_parse_date(payload.get("due_date")), status=status, notes=str(payload.get("notes") or "").strip() or None); db.session.add(row); db.session.flush(); record_activity(app, user, "receivable_created", "Accounts receivable recorded", f"{row.reference} · {row.customer_name} owes {row.currency} {row.balance:,.2f}.", "receivable", row.id, {"balance": row.balance}, notify_owner=user.role not in {"owner", "admin"}); db.session.commit(); return row


def create_payable(app, user, payload):
    department = _assert_department(user, payload.get("department_id")); total = _money(payload.get("total_amount")); paid = _money(payload.get("amount_paid")); status = "paid" if paid >= total and total > 0 else ("partial" if paid > 0 else "open")
    if not str(payload.get("vendor_name") or "").strip(): raise ValueError("Vendor/payee name is required.")
    if total <= 0 or paid < 0 or paid > total: raise ValueError("Enter a positive total and an opening payment between zero and the total.")
    row = FinancePayable(reference=_next_ref("AP", FinancePayable, user.organization_id), organization_id=user.organization_id, department_id=department.id if department else None, created_by_id=user.id, vendor_name=str(payload.get("vendor_name")).strip(), bill_number=str(payload.get("bill_number") or "").strip() or None, description=str(payload.get("description") or "Payable").strip(), total_amount=total, amount_paid=paid, currency=user.organization.currency, due_date=_parse_date(payload.get("due_date")), status=status, notes=str(payload.get("notes") or "").strip() or None); db.session.add(row); db.session.flush(); record_activity(app, user, "payable_created", "Accounts payable recorded", f"{row.reference} · {row.vendor_name} is owed {row.currency} {row.balance:,.2f}.", "payable", row.id, {"balance": row.balance}, notify_owner=user.role not in {"owner", "admin"}); db.session.commit(); return row


def settle_receivable(app, user, row, amount):
    paid = _money(amount)
    if row.organization_id != user.organization_id: raise PermissionError("Receivable is outside your organization.")
    if paid <= 0 or paid > Decimal(str(row.balance)): raise ValueError("Enter an amount not greater than the outstanding receivable.")
    before = {"amount_received":row.amount_received,"balance":row.balance,"status":row.status}
    row.amount_received = _money(row.amount_received) + paid; row.status = "paid" if row.balance <= 0.009 else "partial"
    ledger = FinanceLedgerEntry(reference=_next_ref("LED", FinanceLedgerEntry, user.organization_id), organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id, entry_type="revenue", direction="in", category="Accounts Receivable", counterparty=row.customer_name, description=f"Receivable collection · {row.reference}", amount=paid, currency=row.currency, external_reference=row.invoice_number, status="posted", source_entity_type="receivable", source_entity_id=row.id, posted_at=datetime.now(timezone.utc)); db.session.add(ledger); db.session.add(FinancialRecord(reference=_next_ref("FIN", FinancialRecord, user.organization_id), organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id, record_type="revenue", category="Accounts Receivable", description=ledger.description, amount=paid, currency=row.currency, status="posted", source_entity_type="receivable", source_entity_id=row.id))
    record_revision(user, "receivable", row.id, "receivable_payment", before, {"amount_received":row.amount_received,"balance":row.balance,"status":row.status}, f"Payment of {row.currency} {float(paid):,.2f} recorded against {row.reference}."); record_activity(app, user, "receivable_payment", "Receivable payment recorded", f"{row.reference} received {row.currency} {float(paid):,.2f}; remaining balance {row.currency} {row.balance:,.2f}.", "receivable", row.id, {"amount": float(paid), "balance": row.balance}, notify_owner=user.role not in {"owner", "admin"}); db.session.commit(); return row


def settle_payable(app, user, row, amount):
    paid = _money(amount)
    if row.organization_id != user.organization_id: raise PermissionError("Payable is outside your organization.")
    if paid <= 0 or paid > Decimal(str(row.balance)): raise ValueError("Enter an amount not greater than the outstanding payable.")
    before = {"amount_paid":row.amount_paid,"balance":row.balance,"status":row.status}
    row.amount_paid = _money(row.amount_paid) + paid; row.status = "paid" if row.balance <= 0.009 else "partial"
    ledger = FinanceLedgerEntry(reference=_next_ref("LED", FinanceLedgerEntry, user.organization_id), organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id, entry_type="expenditure", direction="out", category="Accounts Payable", counterparty=row.vendor_name, description=f"Payable settlement · {row.reference}", amount=paid, currency=row.currency, external_reference=row.bill_number, status="posted", source_entity_type="payable", source_entity_id=row.id, posted_at=datetime.now(timezone.utc)); db.session.add(ledger); db.session.add(FinancialRecord(reference=_next_ref("FIN", FinancialRecord, user.organization_id), organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id, record_type="expenditure", category="Accounts Payable", description=ledger.description, amount=paid, currency=row.currency, status="posted", source_entity_type="payable", source_entity_id=row.id))
    record_revision(user, "payable", row.id, "payable_payment", before, {"amount_paid":row.amount_paid,"balance":row.balance,"status":row.status}, f"Payment of {row.currency} {float(paid):,.2f} recorded against {row.reference}."); record_activity(app, user, "payable_payment", "Payable payment recorded", f"{row.reference} paid {row.currency} {float(paid):,.2f}; remaining balance {row.currency} {row.balance:,.2f}.", "payable", row.id, {"amount": float(paid), "balance": row.balance}, notify_owner=user.role not in {"owner", "admin"}); db.session.commit(); return row


# ==========================================================
# RECONCILIATION / PAYROLL / TAX / FORECAST
# ==========================================================

def create_reconciliation(app, user, payload):
    from datetime import time, timedelta
    from models import ReconciliationMatch
    account = FinanceAccount.query.filter_by(id=payload.get("account_id"), organization_id=user.organization_id).first()
    if not account: raise ValueError("Choose a finance account.")
    start_date, end_date = _parse_date(payload.get("period_start"), True), _parse_date(payload.get("period_end"), True)
    if start_date > end_date: raise ValueError("The reconciliation end date precedes its start.")
    closing = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    entries = FinanceLedgerEntry.query.filter(FinanceLedgerEntry.organization_id == user.organization_id, FinanceLedgerEntry.account_id == account.id, FinanceLedgerEntry.status.in_(["posted", "reconciled"]), FinanceLedgerEntry.occurred_at < closing).with_for_update().all()
    system = _money(account.opening_balance) + sum((_money(entry.amount) if entry.direction == "in" else -_money(entry.amount) if entry.direction == "out" else Decimal("0") for entry in entries), Decimal("0"))
    statement = _money(payload.get("statement_balance")); variance = statement - system
    selected = payload.get("ledger_ids") or []
    if isinstance(selected, str): selected = [value.strip() for value in selected.split(",") if value.strip()]
    if not isinstance(selected, list): raise ValueError("Select the bank/cash entries you matched to the statement.")
    selected = set(str(value) for value in selected)
    matches = [entry for entry in entries if entry.id in selected and entry.status == "posted" and entry.direction in {"in", "out"} and start_date <= entry.occurred_at.date() <= end_date]
    if len(matches) != len(selected): raise ValueError("A selected entry is outside this account/period or already reconciled.")
    if matches and abs(variance) >= Decimal("0.01"): raise ValueError("Resolve the closing balance variance before confirming matched entries.")
    row = FinanceReconciliation(organization_id=user.organization_id, account_id=account.id, completed_by_id=user.id, period_start=start_date, period_end=end_date, statement_balance=statement, system_balance=system, variance=variance, status="matched" if abs(variance) < Decimal("0.01") else "variance", notes=str(payload.get("notes") or "").strip() or None, completed_at=datetime.now(timezone.utc))
    db.session.add(row); db.session.flush()
    for entry in matches:
        entry.status, entry.reconciled_at = "reconciled", datetime.now(timezone.utc)
        db.session.add(ReconciliationMatch(organization_id=user.organization_id, reconciliation_id=row.id, ledger_id=entry.id, statement_reference=str(payload.get("statement_reference") or "").strip()[:120] or None, matched_by_id=user.id))
    record_activity(app, user, "finance_reconciled", "Account reconciliation completed", f"{account.name}: variance {account.currency} {float(variance):,.2f}; {len(matches)} statement-matched transaction(s).", "reconciliation", row.id, {"variance": float(variance), "matched_transactions": len(matches)}, notify_owner=True)
    db.session.commit(); return row


def create_payroll(app, user, payload):
    department = _assert_department(user, payload.get("department_id")); gross = _money(payload.get("gross_pay")); deductions = _money(payload.get("deductions")); tax = _money(payload.get("tax_amount")); net = max(Decimal("0"), gross - deductions - tax); status = str(payload.get("status") or "draft").strip().lower(); status = status if status in {"draft", "approved", "paid"} else "draft"
    if not str(payload.get("staff_name") or "").strip(): raise ValueError("Staff name is required.")
    row = PayrollEntry(organization_id=user.organization_id, department_id=department.id if department else None, created_by_id=user.id, staff_name=str(payload.get("staff_name")).strip(), employee_reference=str(payload.get("employee_reference") or "").strip() or None, pay_period=str(payload.get("pay_period") or "").strip() or datetime.now().strftime("%B %Y"), gross_pay=gross, deductions=deductions, tax_amount=tax, net_pay=net, currency=user.organization.currency, status=status, paid_at=datetime.now(timezone.utc) if status == "paid" else None, notes=str(payload.get("notes") or "").strip() or None); db.session.add(row); db.session.flush()
    if status == "paid":
        ledger = FinanceLedgerEntry(reference=_next_ref("LED", FinanceLedgerEntry, user.organization_id), organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id, entry_type="payroll", direction="out", category="Payroll", counterparty=row.staff_name, description=f"Payroll · {row.staff_name} · {row.pay_period}", amount=row.net_pay, currency=row.currency, status="posted", source_entity_type="payroll", source_entity_id=row.id, posted_at=datetime.now(timezone.utc)); db.session.add(ledger); db.session.add(FinancialRecord(reference=_next_ref("FIN", FinancialRecord, user.organization_id), organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id, record_type="payroll", category="Payroll", description=ledger.description, amount=row.net_pay, currency=row.currency, status="posted", source_entity_type="payroll", source_entity_id=row.id))
    record_activity(app, user, "payroll_recorded", "Payroll record saved", f"{row.staff_name} · {row.pay_period} · net {row.currency} {float(row.net_pay):,.2f} · {row.status.title()}.", "payroll", row.id, {"net_pay": float(row.net_pay), "status": row.status}, notify_owner=user.role not in {"owner", "admin"}); db.session.commit(); return row


def create_tax(app, user, payload):
    department = _assert_department(user, payload.get("department_id")); amount = _money(payload.get("tax_amount")); status = str(payload.get("status") or "due").strip().lower(); status = status if status in {"due", "filed", "paid"} else "due"
    if not str(payload.get("tax_type") or "").strip(): raise ValueError("Tax type is required.")
    row = TaxEntry(organization_id=user.organization_id, department_id=department.id if department else None, created_by_id=user.id, tax_type=str(payload.get("tax_type")).strip(), authority=str(payload.get("authority") or "").strip() or None, period=str(payload.get("period") or "").strip() or datetime.now().strftime("%B %Y"), taxable_amount=_money(payload.get("taxable_amount")), tax_amount=amount, currency=user.organization.currency, due_date=_parse_date(payload.get("due_date")), status=status, paid_at=datetime.now(timezone.utc) if status == "paid" else None, notes=str(payload.get("notes") or "").strip() or None); db.session.add(row); db.session.flush()
    if status == "paid":
        ledger = FinanceLedgerEntry(reference=_next_ref("LED", FinanceLedgerEntry, user.organization_id), organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id, entry_type="tax", direction="out", category=row.tax_type, counterparty=row.authority, description=f"{row.tax_type} · {row.period}", amount=row.tax_amount, currency=row.currency, status="posted", source_entity_type="tax", source_entity_id=row.id, posted_at=datetime.now(timezone.utc)); db.session.add(ledger); db.session.add(FinancialRecord(reference=_next_ref("FIN", FinancialRecord, user.organization_id), organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id, record_type="tax", category=row.tax_type, description=ledger.description, amount=row.tax_amount, currency=row.currency, status="posted", source_entity_type="tax", source_entity_id=row.id))
    record_activity(app, user, "tax_recorded", "Tax record saved", f"{row.tax_type} · {row.period} · {row.currency} {float(row.tax_amount):,.2f} · {row.status.title()}.", "tax", row.id, {"tax_amount": float(row.tax_amount), "status": row.status}, notify_owner=user.role not in {"owner", "admin"}); db.session.commit(); return row


def create_forecast(app, user, payload):
    department = _assert_department(user, payload.get("department_id")); kind = str(payload.get("forecast_type") or "").strip().lower()
    if kind not in FORECAST_TYPES: raise ValueError("Choose a valid forecast type.")
    row = FinanceForecast(organization_id=user.organization_id, department_id=department.id if department else None, created_by_id=user.id, name=str(payload.get("name") or kind.title()).strip(), forecast_type=kind, period_start=_parse_date(payload.get("period_start"), True), period_end=_parse_date(payload.get("period_end"), True), amount=_money(payload.get("amount")), currency=user.organization.currency, assumptions=str(payload.get("assumptions") or "").strip() or None); db.session.add(row); db.session.flush(); record_activity(app, user, "forecast_created", "Financial forecast created", f"{row.name}: {row.currency} {float(row.amount):,.2f} for {row.period_start} to {row.period_end}.", "forecast", row.id, {"type": row.forecast_type, "amount": float(row.amount)}, notify_owner=user.role not in {"owner", "admin"}); db.session.commit(); return row


# ==========================================================
# FINANCE PAGE / REPORTING CONTEXT
# No fake values: every figure is derived from this organization's database.
# ==========================================================

def finance_control_context(user):
    org = user.organization_id; currency = user.organization.currency; accounts = FinanceAccount.query.filter_by(organization_id=org, is_active=True).order_by(FinanceAccount.created_at.asc()).all(); account_rows = [{"row": row, "balance": _account_balance(row)} for row in accounts]
    ledger = FinanceLedgerEntry.query.filter_by(organization_id=org).order_by(FinanceLedgerEntry.occurred_at.desc()).all(); receivable_payments, payable_payments = {}, {}; budgets = BudgetAllocation.query.filter_by(organization_id=org).order_by(BudgetAllocation.updated_at.desc()).all(); receivables = FinanceReceivable.query.filter_by(organization_id=org).order_by(FinanceReceivable.created_at.desc()).all(); payables = FinancePayable.query.filter_by(organization_id=org).order_by(FinancePayable.created_at.desc()).all(); reconciliations = FinanceReconciliation.query.filter_by(organization_id=org).order_by(FinanceReconciliation.created_at.desc()).limit(50).all(); payroll = PayrollEntry.query.filter_by(organization_id=org).order_by(PayrollEntry.created_at.desc()).limit(80).all(); taxes = TaxEntry.query.filter_by(organization_id=org).order_by(TaxEntry.created_at.desc()).limit(80).all(); forecasts = FinanceForecast.query.filter_by(organization_id=org).order_by(FinanceForecast.created_at.desc()).limit(50).all()

    for entry in ledger:
        if entry.source_entity_type == "receivable" and entry.source_entity_id: receivable_payments.setdefault(entry.source_entity_id, []).append(entry)
        elif entry.source_entity_type == "payable" and entry.source_entity_id: payable_payments.setdefault(entry.source_entity_id, []).append(entry)
    ar_balance = sum(row.balance for row in receivables if row.status not in {"paid", "cancelled"}); ap_balance = sum(row.balance for row in payables if row.status not in {"paid", "cancelled"}); cash_position = sum(row["balance"] for row in account_rows); budget_total = sum(row.total_budget for row in budgets if row.status == "active"); budget_actual = sum(float(row.actual_spend or 0) for row in budgets if row.status == "active"); budget_committed = sum(float(row.committed_amount or 0) for row in budgets if row.status == "active")
    committed_requests = PurchaseRequest.query.filter(PurchaseRequest.organization_id == org, PurchaseRequest.status.in_(["approved", "money_sent"])).all(); committed_request_total = sum(float(row.estimated_total or 0) for row in committed_requests)
    expense_types = {"expense", "expenditure", "operating_cost", "payroll", "tax"}; dept_rows = []
    for dept in Department.query.filter_by(organization_id=org, is_active=True).order_by(Department.name.asc()).all():
        income = db.session.query(func.coalesce(func.sum(FinancialRecord.amount), 0)).filter(FinancialRecord.organization_id == org, FinancialRecord.department_id == dept.id, FinancialRecord.status == "posted", FinancialRecord.record_type.in_(["income", "revenue"])).scalar() or 0; spend = db.session.query(func.coalesce(func.sum(FinancialRecord.amount), 0)).filter(FinancialRecord.organization_id == org, FinancialRecord.department_id == dept.id, FinancialRecord.status == "posted", FinancialRecord.record_type.in_(expense_types)).scalar() or 0
        if float(income or 0) or float(spend or 0): dept_rows.append({"name": dept.name, "income": float(income), "spend": float(spend), "net": float(income) - float(spend)})
    return {"currency": currency, "accounts": account_rows, "ledger": ledger, "budgets": budgets, "receivables": receivables, "payables": payables, "reconciliations": reconciliations, "payroll": payroll, "taxes": taxes, "forecasts": forecasts, "cash_position": cash_position, "ar_balance": ar_balance, "ap_balance": ap_balance, "budget_total": budget_total, "budget_actual": budget_actual, "budget_committed": budget_committed, "budget_available": budget_total - budget_actual - budget_committed, "committed_request_total": committed_request_total, "department_rows": dept_rows, "ledger_types": sorted(LEDGER_TYPES), "account_types": sorted(ACCOUNT_TYPES), "forecast_types": sorted(FORECAST_TYPES), "receivable_payments":receivable_payments, "payable_payments":payable_payments}
