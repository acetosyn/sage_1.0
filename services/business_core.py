"""Shared tenant controls and atomic posting for SAGE 4.0 services (no commits)."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from sqlalchemy import or_
from models import (Department, User, BranchLocation, BranchDepartment, BranchMembership,
                    FinanceAccount, FinanceLedgerEntry, FinancialRecord, BusinessPosting)
from models import BusinessRecordScope, BranchAccount
from packages.database import db
from services.notification_service import record_activity

OWNER = {"owner", "admin"}
FINANCE = OWNER | {"finance"}
METHODS = ("cash", "bank_transfer", "pos", "paystack", "moniepoint", "opay", "bank_pos", "cheque", "other")


def money(value=0, positive=False, places="0.01"):
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal(places))
        if not amount.is_finite() or amount < 0 or (positive and amount <= 0) or amount >= Decimal("1000000000000000"):
            raise ValueError()
        return amount
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Enter a valid %snon-negative amount." % ("positive, " if positive else ""))


def count(value=0):
    try:amount=Decimal(str(value or 0))
    except (InvalidOperation,ValueError,TypeError):raise ValueError('Enter a whole number within range.')
    if not amount.is_finite() or amount<0 or amount != amount.to_integral_value() or amount > 2147483647: raise ValueError("Enter a whole number within range.")
    return int(amount)


def day(value, required=True):
    if not value and not required: return None
    try: return date.fromisoformat(str(value))
    except (TypeError, ValueError): raise ValueError("Enter a valid date.")


def instant(value=None):
    if not value: return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except ValueError: raise ValueError("Enter a valid date and time.")


def text_value(payload, name, required=False, limit=4000):
    value = str(payload.get(name) or "").strip()
    if required and not value: raise ValueError(name.replace("_", " ").title() + " is required.")
    if len(value) > limit: raise ValueError(name.replace("_", " ").title() + " is too long.")
    return value or None


def require_role(user, roles):
    if user.role not in roles: raise PermissionError("Your role cannot perform this action.")


def individual(user):
    profile = user.organization.workspace_profile
    return bool(profile and profile.workspace_mode == "individual")


def membership(user):
    return BranchMembership.query.filter_by(organization_id=user.organization_id, user_id=user.id).first()


def _delegated_broad_access(user, broad):
    if user.role in broad: return True
    from services.operational_policy import can_operate
    if "finance" in broad and can_operate(user, "finance_ops"): return True
    if "procurement" in broad and (can_operate(user, "supplier") or can_operate(user, "stock")): return True
    return False


def scope(query, model, user, broad=FINANCE):
    query = query.filter(model.organization_id == user.organization_id)
    finance_broad = _delegated_broad_access(user, FINANCE)
    assigned_only=model.__name__ in {'BillPlan','ComplianceDocument'} and not finance_broad
    if assigned_only:query=query.filter(model.responsible_id==user.id)
    member = membership(user) if user.role not in OWNER else None
    if member:
        departments = db.session.query(BranchDepartment.department_id).filter_by(organization_id=user.organization_id, branch_id=member.branch_id)
        if hasattr(model, "branch_id"):
            return query.filter(or_(model.branch_id == member.branch_id, model.department_id.in_(departments)))
        if hasattr(model, "department_id"): return query.filter(model.department_id.in_(departments))
        return query.filter(False)
    if _delegated_broad_access(user, broad): return query
    if assigned_only:return query
    if user.department_id: return query.filter(model.department_id == user.department_id)
    creator = getattr(model, "created_by_id", None)
    if creator is None: creator = getattr(model, "added_by_id", None)
    return query.filter(creator == user.id) if creator is not None else query.filter(False)


def get_row(model, user, row_id, lock=False, broad=FINANCE):
    query = scope(model.query, model, user, broad).filter(model.id == row_id)
    row = (query.with_for_update() if lock else query).first()
    if not row: raise LookupError("Record not found in your permitted workspace.")
    return row


def tenant_row(model, user, row_id):
    row = model.query.filter_by(id=row_id, organization_id=user.organization_id).first()
    if not row: raise ValueError("Choose a valid record from your business.")
    return row


def dimensions(user, payload):
    dept_id = (payload.get("department_id") or None) if user.role in OWNER and 'department_id' in payload else (payload.get("department_id") or user.department_id or None)
    branch_id = payload.get("branch_id") or None
    if dept_id: tenant_row(Department, user, dept_id)
    member = membership(user) if user.role not in OWNER else None
    if member: branch_id = branch_id or member.branch_id
    if branch_id:
        branch = tenant_row(BranchLocation, user, branch_id)
        if not branch.is_active: raise ValueError("This branch is inactive.")
    mapping = BranchDepartment.query.filter_by(organization_id=user.organization_id, department_id=dept_id).first() if dept_id else None
    if mapping:
        if branch_id and branch_id != mapping.branch_id: raise ValueError("The department belongs to another branch.")
        branch_id = mapping.branch_id
    if member and (branch_id != member.branch_id or (dept_id and (not mapping or mapping.branch_id != member.branch_id))):
        raise PermissionError("Choose your assigned branch and its departments.")
    from services.operational_policy import can_operate
    delegated_cross_department = can_operate(user, "finance_ops") or can_operate(user, "supplier") or can_operate(user, "stock") or can_operate(user, "payroll") or can_operate(user, "compliance")
    if not member and user.role not in FINANCE | {"procurement"} and not delegated_cross_department and dept_id != user.department_id:
        raise PermissionError("Choose your assigned department.")
    return dict(organization_id=user.organization_id, department_id=dept_id, branch_id=branch_id, created_by_id=user.id)


def inherited(user, row):
    return dict(organization_id=user.organization_id, department_id=getattr(row,'department_id',None), branch_id=getattr(row,'branch_id',None), created_by_id=user.id)


def worker(user, worker_id, row=None):
    person = tenant_row(User, user, worker_id or user.id)
    if person.status != "active": raise ValueError("Choose an active staff member.")
    if row and person.role not in OWNER:
        target_member = membership(person)
        if row.branch_id and target_member and target_member.branch_id != row.branch_id: raise ValueError("Staff member belongs to another branch.")
        if row.department_id and person.department_id != row.department_id: raise ValueError("Staff member belongs to another department.")
    return person


def align_worker(user,row,person,payload):
    """An assigned manager/holder can find their record even when an owner omits departments."""
    if not payload.get('department_id') and person.role not in OWNER:
        assigned=membership(person)
        dims=dimensions(user,dict(payload,department_id=person.department_id or '',branch_id=payload.get('branch_id') or (assigned.branch_id if assigned else None)))
        row.department_id,row.branch_id=dims['department_id'],dims['branch_id']
    worker(user,person.id,row)


def activity(app, user, row, action, message, entity=None):
    entity_id=(getattr(row,'supplier_id',None) if entity=='supplier' else getattr(row,'inventory_id',None) if entity=='inventory_item' else None) or row.id
    event=record_activity(app, user, "v4_" + action, message, message, entity or row.__tablename__, entity_id,
                    {"version": row.version,"source_type":row.__tablename__,"source_id":row.id}, notify_owner=True)
    event.id=str(uuid4());event.department_id=getattr(row,'department_id',None)
    if getattr(row,'branch_id',None):tag_branch(user,row,event)


def post(user, row, source_key, amount, kind, direction, payload, summary=None, description=None):
    """One operational posting, at most one summary; caller owns the transaction."""
    existing = BusinessPosting.query.filter_by(organization_id=user.organization_id, source_key=source_key).first()
    if existing: raise ValueError("This financial action has already been posted.")
    amount = money(amount, positive=True)
    method = payload.get("method") or "bank_transfer"
    if method not in METHODS: raise ValueError("Choose a supported payment method.")
    account_id = payload.get("account_id") or None
    if account_id:
        account = tenant_row(FinanceAccount, user, account_id)
        if not account.is_active or account.currency != user.organization.currency: raise ValueError("Choose an active account in the business currency.")
        member=membership(user) if user.role not in OWNER else None
        if member and not BranchAccount.query.filter_by(organization_id=user.organization_id,branch_id=member.branch_id,account_id=account.id).first():
            raise PermissionError("This finance account is not assigned to your branch.")
    occurred = instant(payload.get("occurred_at"))
    if occurred > datetime.now(timezone.utc): raise ValueError("A completed financial transaction cannot be dated in the future.")
    reference = text_value(payload, "external_reference", limit=120)
    if reference and BusinessPosting.query.filter_by(organization_id=user.organization_id, external_reference=reference, method=method).first():
        raise ValueError("This payment reference has already been recorded.")
    description = description or getattr(row, "name", None) or getattr(row, "description", None) or kind.replace("_", " ").title()
    ledger = FinanceLedgerEntry(id=str(uuid4()), reference="V4-"+uuid4().hex[:22].upper(),
        organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id,
        account_id=account_id, entry_type=kind, direction=direction, category="SAGE 4.0", description=description,
        amount=amount, currency=user.organization.currency, payment_method=method, external_reference=reference,
        status="posted", source_entity_type=row.__tablename__, source_entity_id=row.id,
        occurred_at=occurred, posted_at=datetime.now(timezone.utc))
    db.session.add(ledger)
    financial = None
    if summary:
        financial = FinancialRecord(id=str(uuid4()), reference="V4-"+uuid4().hex[:22].upper(),
            organization_id=user.organization_id, department_id=row.department_id, created_by_id=user.id,
            record_type=summary, category="SAGE 4.0", description=description, amount=amount,
            currency=user.organization.currency, status="posted", source_entity_type="finance_ledger",
            source_entity_id=ledger.id, occurred_at=occurred)
        db.session.add(financial)
    posting = BusinessPosting(id=str(uuid4()), **inherited(user, row), source_key=source_key,
        entity_type=row.__tablename__, entity_id=row.id, ledger_id=ledger.id,
        financial_record_id=financial.id if financial else None, amount=amount, method=method,
        external_reference=reference, occurred_at=occurred)
    db.session.add(posting)
    tag_branch(user, row, ledger)
    if financial: tag_branch(user, row, financial)
    db.session.flush()
    return posting


def tag_branch(user, source, target):
    if source.branch_id:
        db.session.add(BusinessRecordScope(**inherited(user,source),entity_type=target.__tablename__,entity_id=target.id))


def serialize(row):
    from services.audit_service import value_json
    return {column.name: value_json(getattr(row, column.name)) for column in row.__table__.columns}


def business_payment_targets(user):
    """Bridge cash collections to existing AR/AP histories without another payment."""
    from models import SalesInvoice,SupplierBill
    targets={('business_sales_invoices',row.id):('receivable',row.receivable_id) for row in scope(SalesInvoice.query,SalesInvoice,user)}
    targets.update({('business_supplier_bills',row.id):('payable',row.payable_id) for row in scope(SupplierBill.query,SupplierBill,user)})
    return targets
