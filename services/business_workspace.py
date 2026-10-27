"""Scoped page data shared by the full shell and partial navigation."""
from flask import request
from models import (EventPlan, EventBudget, EventExpense, EventCash, EventResource, EventReport,
                    Attachment, InventoryItem, AssetItem, BranchLocation, FinanceAccount,
                    Customer, CustomerActivity, SalesInvoice, SalesLine, InvoicePayment, FinanceReceivable, BusinessPosting)
from models import (Supplier, SupplierProfile, SupplierQuotation, SupplierBill, FinancePayable, PurchaseRequest,
                    PurchaseFulfillment, ImprestFund, ImprestEntry, ImprestReplenishment, User)
from models import DailyClose, BranchMembership, BranchAccount, FinancialRecord, BranchDepartment, Department, BusinessRecordScope
from models import StockProfile, StockBatch, StockCount, StockMovement, BillPlan, BillPayment, ComplianceDocument, ComplianceRenewal
from models import EmployeeProfile, StaffAdvance, ExpenseClaim, PayrollRun, PayrollSlip
from services.business_core import scope, membership, individual, serialize, OWNER, FINANCE, METHODS
from services.event_service import event_outcome, event_balance, transferred_in
from services.operational_policy import can_operate

BUSINESS_PAGES = {"events", "customers", "debtors", "suppliers", "imprest", "daily_close", "branches", "stock", "bills", "compliance", "payroll", "business_reports"}


def business_context(user, page):
    if page in {'dashboard','reports','analytics'}:
        from services.business_reporting import business_snapshot
        return {'sage4_summary':business_snapshot(user)} if user.role in FINANCE else {}
    if page not in BUSINESS_PAGES: return {}
    events = scope(EventPlan.query, EventPlan, user).order_by(EventPlan.start_at.desc()).all()
    finance_operator = user.role in FINANCE or can_operate(user, "finance_ops")
    result = {"v4_methods": METHODS, "v4_individual": individual(user), "v4_finance": finance_operator,
        "v4_branches": BranchLocation.query.filter_by(organization_id=user.organization_id, is_active=True).all() if user.role in OWNER else [],
        "v4_accounts": FinanceAccount.query.filter_by(organization_id=user.organization_id, is_active=True).all() if finance_operator else [],
        "v4_events": events, "v4_event_balances":{row.id:event_balance(row) for row in events}, "v4_event": next((row for row in events if row.id == request.args.get("record")), None)}
    if page == "events":
        from datetime import datetime,timezone
        from models import EventExpense
        month=datetime.now(timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        monthly_reports=scope(EventReport.query,EventReport,user).filter(EventReport.created_at>=month).all()
        monthly_expenses=scope(EventExpense.query,EventExpense,user).filter(EventExpense.occurred_at>=month).all()
        event_sales=scope(SalesInvoice.query,SalesInvoice,user).filter(SalesInvoice.event_id.isnot(None),SalesInvoice.issued_at>=month).all()
        result["v4_metrics"] = [("Upcoming", sum(row.status in {"approved", "funded"} for row in events)),
            ("Ongoing", sum(row.status == "ongoing" for row in events)), ("Awaiting approval", sum(row.status == "submitted" for row in events)),
            ('Approved budget this month',sum(row.approved for row in events if not row.parent_id and row.start_at.date().replace(day=1)==month.date())),
            ('Actual spend this month',sum(x.amount for x in monthly_expenses)),('Reported leads this month',sum(x.leads for x in monthly_reports)),
            ('Customers acquired this month',sum(x.customers for x in monthly_reports)),('Attributed sales this month',sum(x.subtotal-x.discount for x in event_sales)),
            ("Unretired funds", sum(event_balance(row) for row in events))]
        result['v4_money_metrics']={'Unretired funds','Approved budget this month','Actual spend this month','Attributed sales this month'}
        row = result["v4_event"]
        if row:
            children=[child for child in events if child.parent_id==row.id]
            result['v4_children']=children
            result['v4_funding_outstanding']=row.approved-row.released-sum((child.released-transferred_in(child) for child in children),0)
            result.update(v4_outcome=event_outcome(user,row),
                v4_budget=EventBudget.query.filter_by(organization_id=user.organization_id,event_id=row.id).all(),
                v4_expenses=EventExpense.query.filter_by(organization_id=user.organization_id,event_id=row.id).all(),
                v4_cash=EventCash.query.filter_by(organization_id=user.organization_id,event_id=row.id).all(),
                v4_resources=EventResource.query.filter_by(organization_id=user.organization_id,event_id=row.id).all(),
                v4_report=EventReport.query.filter_by(organization_id=user.organization_id,event_id=row.id).first(),
                v4_evidence=Attachment.query.filter_by(organization_id=user.organization_id,entity_type="event",entity_id=row.id).all(),
                v4_stock=scope(InventoryItem.query,InventoryItem,user,broad=FINANCE|{"procurement"}).all(),
                v4_assets=scope(AssetItem.query,AssetItem,user,broad=FINANCE|{"procurement"}).all())
            result['v4_people']={p.id:p for p in User.query.filter_by(organization_id=user.organization_id)}
            result['v4_cash_postings']={p.id:p for p in scope(BusinessPosting.query,BusinessPosting,user).filter_by(entity_type='business_events',entity_id=row.id)}
    if page in {"customers","debtors"}:
        customers=scope(Customer.query,Customer,user).order_by(Customer.name).all()
        invoices=scope(SalesInvoice.query,SalesInvoice,user).order_by(SalesInvoice.issued_at.desc()).all()
        balances=scope(FinanceReceivable.query,FinanceReceivable,user).filter(FinanceReceivable.status != 'cancelled').all()
        from datetime import date,timedelta
        today=date.today()
        selected=next((item for item in customers if item.id==request.args.get('record')),None)
        invoice=next((item for item in invoices if item.id==request.args.get('invoice')),None)
        result.update(v4_customers=customers,v4_invoices=invoices,v4_customer=selected,v4_invoice=invoice,
            v4_receivables=balances,v4_today=today,
            v4_customer_totals={item.id:dict(revenue=sum(s.total for s in invoices if s.customer_id==item.id),
                outstanding=sum(s.total-s.paid for s in invoices if s.customer_id==item.id),
                purchases=sum(s.customer_id==item.id for s in invoices),last=max((s.issued_at for s in invoices if s.customer_id==item.id),default=None)) for item in customers},
            v4_credit_metrics=[('Receivables',sum(item.balance for item in balances)),('Due today',sum(item.balance for item in balances if item.due_date==today)),
                ('Overdue',sum(item.balance for item in balances if item.due_date and item.due_date<today)),
                ('Over 30 days',sum(item.balance for item in balances if item.due_date and item.due_date<today-timedelta(days=30)))],
            v4_stock=scope(InventoryItem.query,InventoryItem,user,broad=FINANCE|{'procurement'}).all())
        if selected: result['v4_customer_activities']=CustomerActivity.query.filter_by(organization_id=user.organization_id,customer_id=selected.id).order_by(CustomerActivity.occurred_at.desc()).all()
        if invoice: result.update(v4_invoice_lines=SalesLine.query.filter_by(organization_id=user.organization_id,invoice_id=invoice.id).all(),
            v4_invoice_payments=InvoicePayment.query.filter_by(organization_id=user.organization_id,invoice_id=invoice.id).order_by(InvoicePayment.occurred_at).all())
        if invoice:result['v4_payment_postings']={p.id:p for p in scope(BusinessPosting.query,BusinessPosting,user).filter_by(entity_type='business_sales_invoices',entity_id=invoice.id)}
    if page=='suppliers':
        supplier_rows=Supplier.query.filter_by(organization_id=user.organization_id).order_by(Supplier.name).all()
        profiles=scope(SupplierProfile.query,SupplierProfile,user,broad=FINANCE|{'procurement'}).all()
        if membership(user) and user.role not in OWNER: supplier_rows=[s for s in supplier_rows if any(p.supplier_id==s.id for p in profiles)]
        selected=next((s for s in supplier_rows if s.id==request.args.get('record')),None)
        payables=scope(FinancePayable.query,FinancePayable,user,broad=FINANCE|{'procurement'}).all()
        result.update(v4_suppliers=supplier_rows,v4_supplier=selected,
            v4_supplier_profiles={p.supplier_id:p for p in profiles},v4_payables=payables,
            v4_requests=scope(PurchaseRequest.query,PurchaseRequest,user,broad=FINANCE|{'procurement'}).all())
        if selected:
            acquisitions=scope(PurchaseFulfillment.query,PurchaseFulfillment,user,broad=FINANCE|{'procurement'}).filter(PurchaseFulfillment.supplier_name.ilike(selected.name)).all()
            result.update(v4_quotations=scope(SupplierQuotation.query,SupplierQuotation,user,broad=FINANCE|{'procurement'}).filter_by(supplier_id=selected.id).all(),
                v4_supplier_bills=scope(SupplierBill.query,SupplierBill,user).filter_by(supplier_id=selected.id).all(),
                v4_supplier_purchases=acquisitions,v4_profile=next((p for p in profiles if p.supplier_id==selected.id),None),
                v4_evidence=Attachment.query.filter_by(organization_id=user.organization_id,entity_type='supplier',entity_id=selected.id).all())
            from models import FinanceLedgerEntry
            result['v4_supplier_payments']={bill.id:FinanceLedgerEntry.query.filter_by(organization_id=user.organization_id,source_entity_type='business_supplier_bills',source_entity_id=bill.id,direction='out').order_by(FinanceLedgerEntry.occurred_at).all() for bill in result['v4_supplier_bills']}
    if page=='imprest':
        funds=scope(ImprestFund.query,ImprestFund,user).all()
        if not finance_operator:funds=[f for f in funds if f.holder_id==user.id]
        selected=next((f for f in funds if f.id==request.args.get('record')),None)
        result.update(v4_funds=funds,v4_fund=selected)
        if selected: result.update(v4_imprest_entries=ImprestEntry.query.filter_by(organization_id=user.organization_id,fund_id=selected.id).order_by(ImprestEntry.occurred_at.desc()).all(),
            v4_replenishments=ImprestReplenishment.query.filter_by(organization_id=user.organization_id,fund_id=selected.id).all(),
            v4_evidence=Attachment.query.filter_by(organization_id=user.organization_id,entity_type='imprest',entity_id=selected.id).all())
    if page=='daily_close':
        from datetime import date
        from services.branch_close_service import takings
        closes=scope(DailyClose.query,DailyClose,user).order_by(DailyClose.business_date.desc()).all()
        selected=next((c for c in closes if c.id==request.args.get('record')),None)
        expected,_=takings(user,date.today())
        result.update(v4_closes=closes,v4_close=selected,v4_expected=expected,v4_today=date.today())
    if page=='branches':
        branches=BranchLocation.query.filter_by(organization_id=user.organization_id).all()
        finance=FinancialRecord.query.filter_by(organization_id=user.organization_id,status='posted').all()
        tags=BusinessRecordScope.query.filter_by(organization_id=user.organization_id,entity_type='financial_records').all()
        memberships=BranchMembership.query.filter_by(organization_id=user.organization_id).all()
        rows=[]
        for branch in branches:
            dept_ids={link.department_id for link in BranchDepartment.query.filter_by(organization_id=user.organization_id,branch_id=branch.id)}
            record_ids={tag.entity_id for tag in tags if tag.branch_id==branch.id}
            records=[f for f in finance if f.department_id in dept_ids or f.id in record_ids]
            income=sum(f.amount for f in records if f.record_type in {'income','revenue'});expenses=sum(f.amount for f in records if f.record_type in {'expense','expenditure','operating_cost','payroll','tax'})
            property_tags=BusinessRecordScope.query.filter_by(organization_id=user.organization_id,branch_id=branch.id).all()
            stock_ids={tag.entity_id for tag in property_tags if tag.entity_type=='inventory_items'};asset_ids={tag.entity_id for tag in property_tags if tag.entity_type=='asset_items'}
            stock=[item for item in InventoryItem.query.filter_by(organization_id=user.organization_id) if item.department_id in dept_ids or item.id in stock_ids]
            assets=[item for item in AssetItem.query.filter_by(organization_id=user.organization_id) if item.department_id in dept_ids or item.id in asset_ids]
            people={p.id for p in User.query.filter_by(organization_id=user.organization_id) if p.department_id in dept_ids}|{m.user_id for m in memberships if m.branch_id==branch.id}
            requests=PurchaseRequest.query.filter(PurchaseRequest.organization_id==user.organization_id,PurchaseRequest.department_id.in_(dept_ids),PurchaseRequest.status.in_(['submitted','approved','money_sent'])).count()
            cash=ImprestFund.query.filter_by(organization_id=user.organization_id,branch_id=branch.id,status='active').all()
            rows.append(dict(branch=branch,income=income,expenses=expenses,net=income-expenses,stock=sum(i.total_value for i in stock),assets=sum(a.total_value for a in assets),requests=requests,imprest=sum(f.issued-f.spent-f.returned for f in cash),departments=[d for d in Department.query.filter(Department.organization_id==user.organization_id,Department.id.in_(dept_ids))],staff_count=len(people)))
        property_choices=[dict(id='asset:'+item.id,name='Asset · '+item.name+' · '+item.asset_tag) for item in AssetItem.query.filter_by(organization_id=user.organization_id)]
        property_choices += [dict(id='stock:'+item.id,name='Stock · '+item.name+' · '+(item.location or item.sku or 'Unassigned')) for item in InventoryItem.query.filter_by(organization_id=user.organization_id)]
        result.update(v4_property_choices=property_choices,v4_branch_rows=rows,v4_memberships=memberships,v4_branch_accounts=BranchAccount.query.filter_by(organization_id=user.organization_id).all())
    if page=='stock':
        from datetime import date
        stock=scope(InventoryItem.query,InventoryItem,user,broad=FINANCE|{'procurement'}).all()
        selected=next((s for s in stock if s.id==request.args.get('record')),None)
        profiles=scope(StockProfile.query,StockProfile,user,broad=FINANCE|{'procurement'}).all()
        result.update(v4_stock=stock,v4_stock_item=selected,v4_stock_profiles={p.inventory_id:p for p in profiles},v4_today=date.today())
        if selected:result.update(v4_batches=scope(StockBatch.query,StockBatch,user,broad=FINANCE|{'procurement'}).filter_by(inventory_id=selected.id).all(),
            v4_counts=scope(StockCount.query,StockCount,user,broad=FINANCE|{'procurement'}).filter_by(inventory_id=selected.id).all(),
            v4_movements=StockMovement.query.filter_by(organization_id=user.organization_id,inventory_item_id=selected.id).order_by(StockMovement.created_at.desc()).all(),
            v4_acquisitions=scope(PurchaseFulfillment.query,PurchaseFulfillment,user,broad=FINANCE|{'procurement'}).filter_by(is_draft=False).all())
    if page=='bills':
        from datetime import date
        bills=scope(BillPlan.query,BillPlan,user).all();selected=next((r for r in bills if r.id==request.args.get('record')),None)
        result.update(v4_bills=bills,v4_bill=selected,v4_today=date.today(),v4_suppliers=Supplier.query.filter_by(organization_id=user.organization_id).all())
        if selected:result.update(v4_bill_payments=BillPayment.query.filter_by(organization_id=user.organization_id,bill_id=selected.id).order_by(BillPayment.paid_at.desc()).all(),v4_evidence=Attachment.query.filter_by(organization_id=user.organization_id,entity_type='bill',entity_id=selected.id).all())
    if page=='compliance':
        from datetime import date
        docs=scope(ComplianceDocument.query,ComplianceDocument,user).all();selected=next((d for d in docs if d.id==request.args.get('record')),None)
        result.update(v4_documents=docs,v4_document=selected,v4_today=date.today(),v4_bills=scope(BillPlan.query,BillPlan,user).filter_by(status='active').all())
        if selected:result.update(v4_renewals=ComplianceRenewal.query.filter_by(organization_id=user.organization_id,document_id=selected.id).order_by(ComplianceRenewal.created_at.desc()).all(),v4_evidence=Attachment.query.filter_by(organization_id=user.organization_id,entity_type='compliance',entity_id=selected.id).all())
    if page=='payroll':
        from services.payroll_service import employee_scope
        from datetime import date
        profiles=employee_scope(EmployeeProfile,user).all();slips=employee_scope(PayrollSlip,user).all()
        runs=(PayrollRun.query.filter_by(organization_id=user.organization_id).order_by(PayrollRun.period_start.desc()).all() if can_operate(user,'payroll') else scope(PayrollRun.query,PayrollRun,user).order_by(PayrollRun.period_start.desc()).all()) if (finance_operator or can_operate(user,'payroll')) else []
        selected=next((r for r in runs if r.id==request.args.get('record')),None)
        own_slip=next((s for s in slips if s.id==request.args.get('slip')),None)
        result.update(v4_employee_profiles=profiles,v4_payroll_runs=runs,v4_payroll_run=selected,v4_slips=slips,v4_selected_slip=own_slip,
            v4_advances=employee_scope(StaffAdvance,user).all(),v4_claims=employee_scope(ExpenseClaim,user).all(),
            v4_people={p.id:p for p in User.query.filter_by(organization_id=user.organization_id).all()},v4_month=date.today().strftime('%Y-%m'))
        result['v4_claim_evidence']={claim.id:Attachment.query.filter_by(organization_id=user.organization_id,entity_type='expense_claim',entity_id=claim.id).all() for claim in result['v4_claims']}
        if selected:result['v4_run_slips']=[s for s in slips if s.run_id==selected.id]
    if page=='business_reports':
        from services.business_reporting import business_snapshot
        from models import AutomationRun
        result.update(v4_snapshot=business_snapshot(user,request.args.get('start'),request.args.get('end')),
            v4_automation=scope(AutomationRun.query,AutomationRun,user).order_by(AutomationRun.completed_at.desc()).first())
    return result
