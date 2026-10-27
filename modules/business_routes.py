"""Atomic, authenticated SAGE 4.0 API boundary."""
import hashlib
import json
from functools import wraps
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from models import BusinessCommand, EventPlan
from packages.database import db
from services.business_core import get_row, serialize
from services.event_service import create_event, event_action
from models import Customer, SalesInvoice
from services.sales_service import create_customer, customer_action, create_invoice, collect_invoice
from models import Supplier, SupplierProfile, SupplierBill, ImprestFund
from services.supplier_imprest_service import create_supplier, supplier_action, supplier_profile, pay_supplier_bill, create_imprest, imprest_action, BUYERS
from services.business_core import tenant_row
from services.business_core import membership,OWNER
from services.operational_policy import require_operational, is_organization_owner_observer
from models import DailyClose
from services.branch_close_service import save_membership, assign_account, assign_property, create_close, close_action, install_branch_scope
from models import InventoryItem, BillPlan, ComplianceDocument
from services.stock_service import create_stock, stock_action, STOCK_ROLES
from services.renewal_service import create_bill, bill_action, create_document, document_action
from models import StaffAdvance, ExpenseClaim, PayrollRun
from services.payroll_service import (save_employee,request_advance,advance_action,create_claim,claim_action,
    generate_payroll,payroll_action,employee_record)
from services.business_reporting import run_automation, export_table

business = Blueprint("business", __name__, url_prefix="/api/v4")


def mutation(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        try:
            from urllib.parse import urlsplit
            origin=request.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=request.host:raise PermissionError('Submit this action from your SAGE workspace.')
            payload = request.get_json(silent=True) if request.is_json else request.form.to_dict()
            if not isinstance(payload, dict): raise ValueError("A form or JSON object is required.")
            key = request.headers.get("Idempotency-Key") or payload.get("idempotency_key")
            if not key or len(str(key)) > 100: raise ValueError("A valid idempotency key is required. Refresh this form and retry.")
            member=membership(current_user) if current_user.role not in OWNER else None
            permission_state=[current_user.role,current_user.department_id,member.branch_id if member else None,member.version if member else None]
            fingerprint = hashlib.sha256(json.dumps([request.path, current_user.id, permission_state,payload], sort_keys=True).encode()).hexdigest()
            command = BusinessCommand.query.filter_by(organization_id=current_user.organization_id, key=key).first()
            if command:
                if command.actor_id != current_user.id or command.fingerprint != fingerprint: return jsonify(ok=False, message="This request key was used for another action."), 409
                return jsonify(command.result_json)
            command = BusinessCommand(organization_id=current_user.organization_id, actor_id=current_user.id, key=key, fingerprint=fingerprint)
            db.session.add(command); db.session.flush()
            row = fn(payload, *args, **kwargs)
            db.session.flush()
            result = dict(ok=True, message="Saved successfully.", record=serialize(row))
            command.result_json = result; db.session.commit()
            return jsonify(result)
        except (ValueError, PermissionError, LookupError) as exc:
            db.session.rollback()
            return jsonify(ok=False, message=str(exc)), 403 if isinstance(exc, PermissionError) else 404 if isinstance(exc, LookupError) else 400
        except (IntegrityError, StaleDataError):
            db.session.rollback()
            return jsonify(ok=False, message="This record changed or this action was already submitted. Refresh before retrying."), 409
    return wrapped


@business.post("/events")
@mutation
def events_create(data): return create_event(current_app, current_user, data)


@business.post("/events/<row_id>/<action>")
@mutation
def events_action(data, row_id, action):
    row = get_row(EventPlan, current_user, row_id, True)
    if data.get("version") and int(data["version"]) != row.version: raise ValueError("The event changed. Refresh before submitting.")
    return event_action(current_app, current_user, row, action, data, request.files)


def register_business_routes(app):
    app.register_blueprint(business)
    install_branch_scope(app)

@business.post("/customers")
@mutation
def customers_create(data): require_operational(current_user,"crm","customer / CRM data entry"); return create_customer(current_app,current_user,data)

@business.post("/customers/<row_id>/<action>")
@mutation
def customers_action(data,row_id,action): require_operational(current_user,"crm","customer / CRM updates"); return customer_action(current_app,current_user,get_row(Customer,current_user,row_id,True),action,data)

@business.post("/sales")
@mutation
def sales_create(data): require_operational(current_user,"sales","sales and credit invoice recording"); return create_invoice(current_app,current_user,data)

@business.post("/sales/<row_id>/payment")
@mutation
def sales_collect(data,row_id): require_operational(current_user,"collections","customer payment collection"); return collect_invoice(current_app,current_user,get_row(SalesInvoice,current_user,row_id,True),data)

@business.post('/suppliers')
@mutation
def suppliers_create(data): require_operational(current_user,'supplier','supplier / vendor registration'); return create_supplier(current_app,current_user,data)

@business.post('/suppliers/<row_id>/<action>')
@mutation
def suppliers_action(data,row_id,action):
    require_operational(current_user,'finance_ops' if action=='bill' else 'supplier','supplier / vendor operations')
    supplier=tenant_row(Supplier,current_user,row_id)
    profile=SupplierProfile.query.filter_by(organization_id=current_user.organization_id,supplier_id=supplier.id).first()
    if profile: profile=get_row(SupplierProfile,current_user,profile.id,True,broad=BUYERS)
    else: profile=supplier_profile(current_user,supplier)
    return supplier_action(current_app,current_user,profile,action,data,request.files)

@business.post('/supplier-bills/<row_id>/payment')
@mutation
def supplier_bill_payment(data,row_id): require_operational(current_user,'finance_ops','supplier payment recording'); return pay_supplier_bill(current_app,current_user,get_row(SupplierBill,current_user,row_id,True),data)

@business.post('/imprest')
@mutation
def imprest_create(data): require_operational(current_user,'imprest_open','petty cash / imprest fund setup'); return create_imprest(current_app,current_user,data)

@business.post('/imprest/<row_id>/<action>')
@mutation
def imprests_action(data,row_id,action):
    if action=='close':
        return imprest_action(current_app,current_user,get_row(ImprestFund,current_user,row_id,True),action,data,request.files)
    if is_organization_owner_observer(current_user):
        raise PermissionError('Organization owners have oversight access to imprest records. The assigned finance staff or fund holder should record imprest activity.')
    if action in {'issue','replenish'}: require_operational(current_user,'finance_ops','imprest funding')
    return imprest_action(current_app,current_user,get_row(ImprestFund,current_user,row_id,True),action,data,request.files)

@business.post('/branches/memberships')
@mutation
def branch_member(data):return save_membership(current_app,current_user,data)

@business.post('/branches/accounts')
@mutation
def branch_account(data):return assign_account(current_app,current_user,data)

@business.post('/branches/property')
@mutation
def branch_property(data):return assign_property(current_app,current_user,data)

@business.post('/daily-close')
@mutation
def daily_close_create(data):require_operational(current_user,'daily_close','daily sales / POS reconciliation');return create_close(current_app,current_user,data)

@business.post('/daily-close/<row_id>/<action>')
@mutation
def daily_close_action(data,row_id,action):
    if action in {'recount','submit'}: require_operational(current_user,'daily_close','daily sales / POS reconciliation')
    elif action=='approve': require_operational(current_user,'finance_ops','daily reconciliation review')
    elif action=='reopen' and is_organization_owner_observer(current_user): raise PermissionError('Organization owners have oversight access to daily reconciliation. Finance should reopen and recount operational closes.')
    return close_action(current_app,current_user,get_row(DailyClose,current_user,row_id,True),action,data)

@business.post('/stock')
@mutation
def stock_create(data):require_operational(current_user,'stock','stock setup and control');return create_stock(current_app,current_user,data)

@business.post('/stock/<row_id>/<action>')
@mutation
def stocks_action(data,row_id,action):require_operational(current_user,'stock','stock movement and control');return stock_action(current_app,current_user,get_row(InventoryItem,current_user,row_id,True,broad=STOCK_ROLES),action,data)

@business.post('/bills')
@mutation
def bills_create(data):require_operational(current_user,'bills','bill / subscription scheduling');return create_bill(current_app,current_user,data)

@business.post('/bills/<row_id>/<action>')
@mutation
def bills_action(data,row_id,action):require_operational(current_user,'bills','bill / renewal operations');return bill_action(current_app,current_user,get_row(BillPlan,current_user,row_id,True),action,data,request.files)

@business.post('/compliance')
@mutation
def documents_create(data):require_operational(current_user,'compliance','compliance document registration');return create_document(current_app,current_user,data,request.files)

@business.post('/compliance/<row_id>/<action>')
@mutation
def documents_action(data,row_id,action):require_operational(current_user,'compliance','compliance renewal / document control');return document_action(current_app,current_user,get_row(ComplianceDocument,current_user,row_id,True),action,data,request.files)

@business.post('/employees')
@mutation
def employees_save(data):require_operational(current_user,'payroll','staff finance / payroll profile maintenance');return save_employee(current_app,current_user,data)

@business.post('/advances')
@mutation
def advance_create(data):
    if is_organization_owner_observer(current_user): raise PermissionError('Organization owners review staff advances; staff members submit their own requests.')
    return request_advance(current_app,current_user,data)

@business.post('/advances/<row_id>/<action>')
@mutation
def advances_action(data,row_id,action):
    if action in {'issue','repay'}: require_operational(current_user,'finance_ops','staff advance funding / repayment recording')
    return advance_action(current_app,current_user,employee_record(StaffAdvance,current_user,row_id),action,data)

@business.post('/claims')
@mutation
def claims_create(data):
    if is_organization_owner_observer(current_user): raise PermissionError('Organization owners review staff claims; staff members submit their own expense claims.')
    return create_claim(current_app,current_user,data,request.files)

@business.post('/claims/<row_id>/<action>')
@mutation
def claims_action(data,row_id,action):
    if action=='pay': require_operational(current_user,'finance_ops','approved expense claim payment')
    return claim_action(current_app,current_user,employee_record(ExpenseClaim,current_user,row_id),action,data)

@business.post('/payroll')
@mutation
def payroll_create(data):require_operational(current_user,'payroll','payroll generation');return generate_payroll(current_app,current_user,data)

@business.post('/payroll/<row_id>/<action>')
@mutation
def payrolls_action(data,row_id,action):
    if action!='approve': require_operational(current_user,'payroll','payroll processing')
    return payroll_action(current_app,current_user,get_row(PayrollRun,current_user,row_id,True),action,data)

@business.post('/automation/run')
@mutation
def automation_run(data):return run_automation(current_app,current_user)

@business.get('/export/<kind>.csv')
@login_required
def business_export(kind):
    import csv,io
    from flask import Response
    try:
        columns,rows=export_table(current_user,kind,request.args.get('start'),request.args.get('end'))
        stream=io.StringIO();writer=csv.writer(stream);writer.writerow(columns)
        # Neutralize spreadsheet formula execution in customer/vendor-supplied text.
        for row in rows:writer.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for v in row])
        return Response('\ufeff'+stream.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="sage-{kind}.csv"'})
    except (ValueError,PermissionError) as exc:return jsonify(ok=False,message=str(exc)),403 if isinstance(exc,PermissionError) else 400
