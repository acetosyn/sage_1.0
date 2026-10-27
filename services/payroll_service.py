"""Financial HR: explicit salary policy, commission, loans, claims and audited payroll."""
import calendar
from uuid import uuid4
from datetime import date, datetime, time, timedelta, timezone
from models import (EmployeeProfile, StaffAdvance, ExpenseClaim, PayrollRun, PayrollSlip, PayrollAdvanceRecovery,
                    PayrollEntry, TaxEntry, SalesInvoice, User)
from packages.database import db
from services.business_core import *
from services.storage_service import save_attachment
from services.operational_policy import can_operate, require_operational


def employee_scope(model,user):
    if user.role in FINANCE or can_operate(user,"payroll") or can_operate(user,"finance_ops"):
        return model.query.filter(model.organization_id==user.organization_id)
    return scope(model.query,model,user).filter(model.user_id==user.id)


def employee_record(model,user,row_id,lock=True):
    row=employee_scope(model,user).filter(model.id==row_id)
    record=(row.with_for_update() if lock else row).first()
    if not record:raise LookupError('Record not found in your permitted staff profile.')
    return record


def save_employee(app,user,data):
    require_operational(user,"payroll","staff finance / payroll profile maintenance");person=worker(user,data.get('user_id'))
    dims=dimensions(user,dict(data,department_id=person.department_id or ''))
    row=EmployeeProfile.query.filter_by(organization_id=user.organization_id,user_id=person.id).with_for_update().first()
    if not row:row=EmployeeProfile(id=str(uuid4()),**dims,user_id=person.id);db.session.add(row)
    row.employment_date=day(data.get('employment_date'))
    for field in ('salary','allowance','paye','other_deduction','loan_deduction'):setattr(row,field,money(data.get(field)))
    for field in ('commission_rate','pension_rate','employer_pension_rate'):
        value=money(data.get(field),places='0.001')
        if value>100:raise ValueError('Rates must be between zero and 100 percent.')
        setattr(row,field,value)
    row.is_active=str(data.get('is_active','true')).lower() in {'true','1','yes'}
    row.notes=text_value(data,'notes')
    db.session.flush();activity(app,user,row,'employee_profile','Staff financial profile saved','payroll_v4');return row


def request_advance(app,user,data):
    person=worker(user,data.get('user_id'))
    if not (can_operate(user,"payroll") or can_operate(user,"finance_ops")) and person.id!=user.id:raise PermissionError('You can only request your own advance or loan.')
    kind=data.get('kind','salary_advance')
    if kind not in {'salary_advance','staff_loan'}:raise ValueError('Choose salary advance or staff loan.')
    row=StaffAdvance(id=str(uuid4()),**dimensions(user,dict(data,department_id=person.department_id or '')),user_id=person.id,kind=kind,
        amount=money(data.get('amount'),True),due_date=day(data.get('due_date')),reason=text_value(data,'reason',True))
    if individual(user) and user.role in OWNER:row.status='approved';row.approved_by_id=user.id;row.approved_at=instant()
    db.session.add(row);db.session.flush();activity(app,user,row,'advance_requested','Staff advance / loan requested','payroll_v4');return row


def advance_action(app,user,row,action,data):
    if action=='approve':
        require_role(user,OWNER)
        if row.status!='submitted':raise ValueError('Only submitted advances can be approved.')
        row.status='approved';row.approved_by_id=user.id;row.approved_at=instant()
    elif action=='reject':
        require_role(user,OWNER)
        if row.status!='submitted':raise ValueError('Only submitted advances can be rejected.')
        row.status='rejected';row.reason+='\nRejected: '+text_value(data,'reason',True)
    elif action=='issue':
        require_operational(user,'finance_ops','staff advance funding')
        if row.status!='approved':raise ValueError('Approve the advance before releasing funds.')
        posting=post(user,row,'staff-advance:'+row.id,row.amount,'cash_out','out',data,description=row.kind.replace('_',' ').title())
        row.status='issued';row.issued_at=posting.occurred_at
    elif action=='repay':
        require_operational(user,'finance_ops','staff advance repayment recording')
        if row.status!='issued':raise ValueError('This advance has no open issued balance.')
        amount=money(data.get('amount'),True)
        if amount>row.amount-row.repaid:raise ValueError('Repayment exceeds the outstanding staff advance.')
        post(user,row,'staff-repayment:'+str(uuid4()),amount,'cash_in','in',data,description='Staff loan / advance repayment')
        row.repaid+=amount
        if row.repaid==row.amount:row.status='settled';row.settled_at=instant()
    else:raise ValueError('Unsupported advance action.')
    activity(app,user,row,'advance_'+action,'Staff advance · '+action,'payroll_v4');return row


def create_claim(app,user,data,files):
    if not files.get('evidence'):raise ValueError('Attach the expense-claim receipt.')
    row=ExpenseClaim(id=str(uuid4()),**dimensions(user,data),user_id=user.id,description=text_value(data,'description',True,300),
        amount=money(data.get('amount'),True),occurred_at=instant(data.get('occurred_at')))
    if row.occurred_at>instant():raise ValueError('An expense claim cannot be dated in the future.')
    db.session.add(row);db.session.flush();save_attachment(app,files['evidence'],user,'expense_claim',row.id,'expense_claim_receipt',True)
    activity(app,user,row,'claim_submitted','Staff expense claim submitted','payroll_v4');return row


def claim_action(app,user,row,action,data):
    if action in {'approve','reject'}:
        require_role(user,OWNER)
        if row.status!='submitted':raise ValueError('This claim has already been reviewed.')
        row.status='approved' if action=='approve' else 'rejected';row.reviewed_by_id=user.id;row.reviewed_at=instant();row.review_notes=text_value(data,'review_notes',True)
    elif action=='pay':
        require_operational(user,'finance_ops','approved expense claim payment')
        if row.status!='approved':raise ValueError('Approve the claim before payment.')
        posting=post(user,row,'expense-claim:'+row.id,row.amount,'expense','out',data,'expense',row.description)
        row.status='paid';row.paid_at=posting.occurred_at
    else:raise ValueError('Unsupported expense-claim action.')
    activity(app,user,row,'claim_'+action,'Expense claim · '+action,'payroll_v4');return row


def month_period(value):
    try:
        start=date.fromisoformat(str(value)+'-01');end=start.replace(day=calendar.monthrange(start.year,start.month)[1]);return start,end
    except ValueError:raise ValueError('Choose a payroll month in YYYY-MM format.')


def calculate_slip(slip):
    slip.gross=money(slip.salary+slip.allowance+slip.bonus+slip.commission)
    deductions=slip.paye+slip.pension+slip.other_deduction+slip.advance_deduction
    if deductions>slip.gross:raise ValueError('Payroll deductions exceed gross pay; revise the staff policy or draft adjustments.')
    slip.net=slip.gross-deductions


def sync_legacy(user,slip):
    legacy=tenant_row(PayrollEntry,user,slip.payroll_entry_id)
    legacy.gross_pay=slip.gross;legacy.tax_amount=slip.paye;legacy.deductions=slip.pension+slip.other_deduction+slip.advance_deduction;legacy.net_pay=slip.net
    return legacy


def generate_payroll(app,user,data):
    require_operational(user,"payroll","payroll generation");start,end=month_period(data.get('month'));dims=dimensions(user,data)
    profiles=employee_scope(EmployeeProfile,user).filter(EmployeeProfile.is_active==True,EmployeeProfile.employment_date<=end)
    if dims['branch_id']:profiles=profiles.filter_by(branch_id=dims['branch_id'])
    elif dims['department_id']:profiles=profiles.filter_by(department_id=dims['department_id'])
    if data.get('user_id'):profiles=profiles.filter_by(user_id=data['user_id'])
    profiles=profiles.all()
    if not profiles:raise ValueError('No active employee financial profiles match this payroll scope.')
    run=PayrollRun(id=str(uuid4()),**dims,name='Payroll · '+start.strftime('%B %Y'),period_start=start,period_end=end,notes=text_value(data,'notes'))
    db.session.add(run);db.session.flush()
    for profile in profiles:
        person=worker(user,profile.user_id)
        if PayrollEntry.query.filter_by(organization_id=user.organization_id,staff_name=person.display_name,pay_period=start.strftime('%B %Y')).first():raise ValueError('A payroll entry already exists for '+person.display_name+' in this period.')
        begin=datetime.combine(start,time.min,tzinfo=timezone.utc);finish=datetime.combine(end+timedelta(days=1),time.min,tzinfo=timezone.utc)
        invoices=SalesInvoice.query.filter(SalesInvoice.organization_id==user.organization_id,SalesInvoice.sales_person_id==person.id,SalesInvoice.issued_at>=begin,SalesInvoice.issued_at<finish).all()
        sales=sum((sale.subtotal-sale.discount for sale in invoices),Decimal(0))
        outstanding=sum((loan.amount-loan.repaid for loan in StaffAdvance.query.filter_by(organization_id=user.organization_id,user_id=person.id,status='issued')),Decimal(0))
        legacy=PayrollEntry(id=str(uuid4()),organization_id=user.organization_id,department_id=profile.department_id,created_by_id=user.id,
            staff_name=person.display_name,employee_reference=person.employee_id or person.id,pay_period=start.strftime('%B %Y'),currency=user.organization.currency,status='draft')
        db.session.add(legacy)
        slip=PayrollSlip(id=str(uuid4()),**inherited(user,profile),run_id=run.id,user_id=person.id,payroll_entry_id=legacy.id,period_start=start,
            salary=profile.salary,allowance=profile.allowance,bonus=Decimal(0),sales=sales,commission_rate=profile.commission_rate,
            commission=money(sales*profile.commission_rate/100),paye=profile.paye,
            pension=money((profile.salary+profile.allowance)*profile.pension_rate/100),
            employer_pension=money((profile.salary+profile.allowance)*profile.employer_pension_rate/100),
            other_deduction=profile.other_deduction,advance_deduction=min(profile.loan_deduction,outstanding))
        calculate_slip(slip);db.session.add(slip);db.session.flush();sync_legacy(user,slip);tag_branch(user,slip,legacy)
    activity(app,user,run,'payroll_generated','Payroll draft generated','payroll_v4');return run


def recover_advances(user,slip):
    remaining=slip.advance_deduction
    loans=StaffAdvance.query.filter_by(organization_id=user.organization_id,user_id=slip.user_id,status='issued').order_by(StaffAdvance.due_date,StaffAdvance.issued_at).with_for_update().all()
    if remaining>sum((loan.amount-loan.repaid for loan in loans),Decimal(0)):raise ValueError('Staff advance balances changed; revise this payroll deduction before payment.')
    for loan in loans:
        recovered=min(remaining,loan.amount-loan.repaid)
        if recovered:
            loan.repaid+=recovered;remaining-=recovered
            db.session.add(PayrollAdvanceRecovery(**inherited(user,slip),slip_id=slip.id,advance_id=loan.id,amount=recovered))
            if loan.amount==loan.repaid:loan.status='settled';loan.settled_at=instant()
        if not remaining:break


def payroll_action(app,user,run,action,data):
    if action == "approve": require_role(user, OWNER)
    else: require_operational(user, "payroll", "payroll processing")
    slips=PayrollSlip.query.filter_by(organization_id=user.organization_id,run_id=run.id).with_for_update().all()
    if action=='adjust':
        if run.status!='draft':raise ValueError('Only draft payroll can be adjusted.')
        slip=next((s for s in slips if s.id==data.get('slip_id')),None)
        if not slip:raise ValueError('Choose a payslip in this payroll run.')
        for field in ('salary','allowance','bonus','paye','pension','employer_pension','other_deduction','advance_deduction'):
            if field in data:setattr(slip,field,money(data.get(field)))
        slip.notes=text_value(data,'notes',True);calculate_slip(slip);sync_legacy(user,slip)
        run.updated_at=instant()
    elif action=='approve':
        if run.status!='draft':raise ValueError('Only draft payroll can be approved.')
        run.status='approved';run.approved_at=instant();run.approved_by_id=user.id
        for slip in slips:sync_legacy(user,slip).status='approved'
    elif action=='pay':
        if run.status!='approved':raise ValueError('Approve payroll before payment.')
        total_net=sum((slip.net for slip in slips),Decimal(0))
        if total_net:post(user,run,'payroll-cash:'+run.id,total_net,'cash_out','out',data,description=run.name+' · net payment batch')
        for slip in slips:
            recover_advances(user,slip)
            gross_cost=slip.gross+slip.employer_pension
            if gross_cost:post(user,slip,'payroll-expense:'+slip.id,gross_cost,'payroll','neutral',{},'payroll',run.name)
            withheld=slip.paye+slip.pension+slip.employer_pension+slip.other_deduction
            if withheld:post(user,slip,'payroll-withheld:'+slip.id,withheld,'liability','neutral',{},description=run.name+' · deductions withheld')
            legacy=sync_legacy(user,slip);legacy.status='paid';legacy.paid_at=instant(data.get('occurred_at'))
            if slip.paye:
                tax=TaxEntry(id=str(uuid4()),organization_id=user.organization_id,department_id=slip.department_id,created_by_id=user.id,
                    tax_type='PAYE',authority='Configured payroll tax authority',period=run.period_start.strftime('%B %Y'),taxable_amount=slip.gross,tax_amount=slip.paye,
                    currency=user.organization.currency,due_date=day(data.get('tax_due_date')),status='due',notes='Payroll withholding; remit through the connected payroll run.')
                db.session.add(tax);slip.tax_entry_id=tax.id;tag_branch(user,slip,tax)
        run.status='paid';run.paid_at=instant()
    elif action=='remit':
        if run.status!='paid' or run.remitted_at:raise ValueError('This payroll has no unremitted statutory deductions.')
        total=sum((s.paye+s.pension+s.employer_pension for s in slips),Decimal(0))
        if not total:raise ValueError('There are no statutory deductions to remit.')
        post(user,run,'payroll-remittance:'+run.id,total,'cash_out','out',data,description=run.name+' · PAYE / pension remittance')
        run.remitted_at=instant(data.get('occurred_at'))
        for slip in slips:
            if slip.tax_entry_id:
                tax=tenant_row(TaxEntry,user,slip.tax_entry_id);tax.status='paid';tax.paid_at=run.remitted_at
    else:raise ValueError('Unsupported payroll action.')
    activity(app,user,run,'payroll_'+action,'Payroll · '+action,'payroll_v4');return run
