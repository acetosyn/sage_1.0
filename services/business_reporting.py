"""Permission-scoped connected reporting and scheduler entry points."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import func
from models import (FinancialRecord, EventPlan, EventReport, Customer, SalesInvoice, FinanceReceivable, FinancePayable,
    InventoryItem, StockBatch, ImprestFund, BillPlan, ComplianceDocument, DailyClose, PayrollSlip, StaffAdvance, EventExpense,
    AutomationRun, Organization, User, BranchMembership)
from packages.database import db
from services.business_core import scope, day, money, OWNER, FINANCE, individual, membership
from services.payroll_service import employee_scope
from services.business_reminders import generate_reminders


def business_snapshot(user,start=None,end=None):
    today=date.today();start=day(start) if start else today.replace(day=1);end=day(end) if end else today
    if end<start:raise ValueError('Report end date must follow its start.')
    begin=datetime.combine(start,datetime.min.time(),tzinfo=timezone.utc);finish=datetime.combine(end+timedelta(days=1),datetime.min.time(),tzinfo=timezone.utc)
    records=scope(FinancialRecord.query,FinancialRecord,user).filter(FinancialRecord.status=='posted',FinancialRecord.occurred_at>=begin,FinancialRecord.occurred_at<finish).all()
    income=sum((r.amount for r in records if r.record_type in {'revenue','income'}),Decimal(0))
    expense=sum((r.amount for r in records if r.record_type in {'expense','expenditure','payroll','tax','operating_cost'}),Decimal(0))
    events=scope(EventPlan.query,EventPlan,user).all();reports=scope(EventReport.query,EventReport,user).filter(EventReport.created_at>=begin,EventReport.created_at<finish).all()
    event_expenses=scope(EventExpense.query,EventExpense,user).filter(EventExpense.occurred_at>=begin,EventExpense.occurred_at<finish).all()
    invoices=scope(SalesInvoice.query,SalesInvoice,user).filter(SalesInvoice.issued_at>=begin,SalesInvoice.issued_at<finish).all()
    receivables=scope(FinanceReceivable.query,FinanceReceivable,user).filter(FinanceReceivable.status!='cancelled').all()
    payables=scope(FinancePayable.query,FinancePayable,user).filter(FinancePayable.status!='cancelled').all() if user.role in FINANCE else []
    stock=scope(InventoryItem.query,InventoryItem,user,broad=FINANCE|{'procurement'}).all()
    batches=scope(StockBatch.query,StockBatch,user,broad=FINANCE|{'procurement'}).filter(StockBatch.quantity>0,StockBatch.expiry_date<today).all()
    imprest=scope(ImprestFund.query,ImprestFund,user).filter_by(status='active').all()
    bills=scope(BillPlan.query,BillPlan,user).filter(BillPlan.status=='active',BillPlan.next_due<=today+timedelta(days=7)).all() if user.role in FINANCE else []
    docs=scope(ComplianceDocument.query,ComplianceDocument,user).filter(ComplianceDocument.status=='active',ComplianceDocument.expiry_date<today).all() if user.role in FINANCE else []
    advances=employee_scope(StaffAdvance,user).filter_by(status='issued').all()
    from services.event_service import event_balance
    payroll=employee_scope(PayrollSlip,user).filter(PayrollSlip.period_start>=start,PayrollSlip.period_start<=end).all()
    customers=scope(Customer.query,Customer,user).filter(Customer.created_at>=begin,Customer.created_at<finish).count()
    return dict(start=start.isoformat(),end=end.isoformat(),currency=user.organization.currency,income=income,expenses=expense,net=income-expense,
        receivables=sum((money(r.balance) for r in receivables),Decimal(0)),payables=sum((money(r.balance) for r in payables),Decimal(0)),
        overdue_receivables=sum((money(r.balance) for r in receivables if r.due_date and r.due_date<today),Decimal(0)),
        new_customers=customers,sales=len(invoices),event_count=sum(e.kind=='event' and e.completed_at is not None and start<=e.completed_at.date()<=end for e in events),
        event_expenditure=sum((r.amount for r in event_expenses),Decimal(0)),
        event_leads=sum(r.leads for r in reports),event_customers=sum(r.customers for r in reports),
        event_revenue=sum((s.total-s.tax for s in invoices if s.event_id),Decimal(0)),
        reported_event_revenue=sum((r.revenue for r in reports),Decimal(0)),
        unretired_events=sum((event_balance(e) for e in events),Decimal(0)),
        imprest_held=sum((f.issued-f.spent-f.returned for f in imprest),Decimal(0)),staff_advance_balance=sum((a.amount-a.repaid for a in advances),Decimal(0)),
        low_stock=sum(s.quantity<=s.reorder_level for s in stock),expired_batches=len(batches),
        bills_due=sum((b.amount for b in bills),Decimal(0)),bills_due_count=len(bills),overdue_compliance=len(docs),
        payroll_net=sum((s.net for s in payroll),Decimal(0)),payroll_gross=sum((s.gross for s in payroll),Decimal(0)),
        bills=[dict(name=b.name,amount=str(b.amount),due=b.next_due.isoformat()) for b in bills],
        compliance=[dict(name=d.name,due=d.expiry_date.isoformat()) for d in docs])


def run_automation(app,user):
    require=user.role in FINANCE
    if not require:raise PermissionError('Finance or owner access is required.')
    member=membership(user) if user.role not in OWNER else None
    run=AutomationRun(id=str(uuid4()),organization_id=user.organization_id,department_id=user.department_id,
        branch_id=member.branch_id if member else None,created_by_id=user.id,scope_key=member.branch_id if member else 'business',
        reminders_created=generate_reminders(app,user.organization_id),completed_at=datetime.now(timezone.utc))
    db.session.add(run);return run


def automation_tick(app):
    from flask import request
    from flask_login import current_user
    if request.method!='GET' or request.path.startswith(('/static/','/api/','/evidence/','/platform-admin')) or not current_user.is_authenticated or current_user.role not in FINANCE:return
    member=membership(current_user) if current_user.role not in OWNER else None;key=member.branch_id if member else 'business'
    latest=AutomationRun.query.filter_by(organization_id=current_user.organization_id,scope_key=key).order_by(AutomationRun.completed_at.desc()).first()
    from core.datetime_utils import as_utc
    if latest and datetime.now(timezone.utc)-as_utc(latest.completed_at)<timedelta(minutes=15):return
    run_automation(app,current_user);db.session.commit()


def export_table(user,kind,start=None,end=None):
    if kind=='summary':
        snapshot=business_snapshot(user,start,end)
        return ['Metric','Value'],[[key,value] for key,value in snapshot.items() if not isinstance(value,(list,dict))]
    models={
        'events':(EventPlan,['name','kind','status','requested','approved','released','spent','returned','start_at','end_at']),
        'customers':(Customer,['name','phone','email','business','stage','next_follow_up']),
        'sales':(SalesInvoice,['number','description','total','paid','due_date','status','issued_at']),
        'bills':(BillPlan,['name','amount','frequency','next_due','status']),
        'payroll':(PayrollSlip,['user_id','period_start','salary','allowance','bonus','commission','gross','paye','pension','advance_deduction','net'])}
    if kind not in models:raise ValueError('Choose a supported export.')
    if kind in {'bills','payroll'} and user.role not in FINANCE:raise PermissionError('Finance access is required for this export.')
    model,columns=models[kind];rows=scope(model.query,model,user).all()
    if start or end:
        begin=day(start) if start else date.min;finish=day(end) if end else date.max
        field='issued_at' if kind=='sales' else 'period_start' if kind=='payroll' else 'start_at' if kind=='events' else 'created_at'
        rows=[row for row in rows if begin<=(getattr(row,field).date() if isinstance(getattr(row,field),datetime) else getattr(row,field))<=finish]
    return [c.replace('_',' ').title() for c in columns],[[getattr(row,c) if getattr(row,c) is not None else '' for c in columns] for row in rows]
