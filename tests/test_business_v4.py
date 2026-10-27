"""SAGE 4.0 acceptance tests use a temporary database and never touch business data."""
import io
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from flask import Flask, g
from flask_login import current_user
from werkzeug.datastructures import FileStorage
from models import (Organization, OrganizationWorkspace, Department, User, EventPlan, EventReport,
                    FinancialRecord, FinanceLedgerEntry, BusinessPosting, InventoryItem, EventResource)
from models import Customer, SalesInvoice, InvoicePayment, FinanceReceivable
from models import Supplier, SupplierProfile, SupplierBill, FinancePayable, ImprestFund, ImprestReplenishment, PurchaseRequest
from models import BranchLocation, BranchDepartment, BranchMembership, DailyClose
from models import StockProfile, StockBatch, StockCount, BillPlan, BillPayment, ComplianceDocument, Notification
from models import EmployeeProfile, StaffAdvance, PayrollRun, PayrollSlip, PayrollEntry, ExpenseClaim
from packages.database import db
from packages.security import init_security
from services.audit_service import install_audit_tracking
from modules.business_routes import register_business_routes
from services.event_service import create_event, event_action


class BusinessV4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sage-v4-")
        self.app = Flask(__name__)
        self.app.config.update(SECRET_KEY="test", TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            STORAGE_DIR=Path(self.temp.name), MAX_UPLOAD_MB=12, EMAIL_NOTIFICATIONS_ENABLED=False, WEB_PUSH_ENABLED=False)
        db.init_app(self.app); init_security(self.app); register_business_routes(self.app); install_audit_tracking(self.app)
        @self.app.before_request
        def actor():
            g.pop('_login_user',None)
            db.session.info['sage_actor_id'] = current_user.id if current_user.is_authenticated else None
        @self.app.get('/branch-probe')
        def branch_probe():
            from services.operations_service import finance_summary
            return {'amounts':[str(row.amount) for row in FinancialRecord.query.filter_by(organization_id=current_user.organization_id).all()],
                    'events':[row.name for row in EventPlan.query.filter_by(organization_id=current_user.organization_id).all()],
                    'income_total':finance_summary(current_user.organization_id)['income_total']}
        self.ctx=self.app.app_context(); self.ctx.push(); db.create_all()
        self.org=Organization(name="Business",slug="v4",business_type="Retail")
        self.other=Organization(name="Other",slug="other",business_type="Retail")
        db.session.add_all([self.org,self.other]);db.session.flush()
        self.dept=Department(organization_id=self.org.id,name="Sales");db.session.add(self.dept);db.session.flush()
        self.owner=User(organization_id=self.org.id,first_name="Owner",last_name="Test",email="owner@test.local",role="owner",password_hash="test")
        self.staff=User(organization_id=self.org.id,department_id=self.dept.id,first_name="Staff",last_name="Test",email="staff@test.local",role="staff",password_hash="test")
        self.outsider=User(organization_id=self.other.id,first_name="Other",last_name="Test",email="other@test.local",role="owner",password_hash="test")
        db.session.add_all([self.owner,self.staff,self.outsider]);db.session.commit(); self.key=0

    def tearDown(self):
        db.session.remove();db.engine.dispose();self.ctx.pop();self.temp.cleanup()

    def client(self,user=None):
        g.pop('_login_user',None)
        client=self.app.test_client()
        with client.session_transaction() as s:s['_user_id']=(user or self.owner).id;s['_fresh']=True
        return client

    def send(self,path,payload=None,user=None,key=None):
        self.key+=1
        return self.client(user).post('/api/v4/'+path,json=payload or {},headers={'Idempotency-Key':key or str(self.key)})

    def plan(self,user=None,**changes):
        payload=dict(name="Outreach",kind="event",category="Marketing",objective="Acquire customers",
                     start_at="2026-11-15T09:00:00Z",end_at="2026-11-15T18:00:00Z",requested="500",expected_leads=150)
        payload.update(changes)
        response=self.send('events',payload,user)
        self.assertEqual(response.status_code,200,response.json)
        return db.session.get(EventPlan,response.json['record']['id'])

    def approve_fund(self,row):
        for action,data in [('submit',{}),('approve',{'amount':'450'}),('fund',{'amount':'300'})]:
            r=self.send('events/'+row.id+'/'+action,data);self.assertEqual(r.status_code,200,r.json)

    def test_event_lifecycle_permissions_and_tenant_isolation(self):
        row=self.plan(self.staff)
        self.assertEqual(self.send('events/'+row.id+'/complete',user=self.staff).status_code,400)
        self.assertEqual(self.send('events/'+row.id+'/approve',{'amount':10},self.staff).status_code,403)
        self.assertEqual(self.send('events/'+row.id+'/submit',user=self.outsider).status_code,404)

    def test_funding_is_cash_movement_and_spend_is_one_expense(self):
        row=self.plan();self.approve_fund(row)
        self.assertEqual(FinancialRecord.query.count(),0)
        self.assertEqual(self.send('events/'+row.id+'/fund',{'amount':'151'}).status_code,400)
        receipt=FileStorage(io.BytesIO(b'%PDF-1.4 test receipt'),filename='receipt.pdf',content_type='application/pdf')
        event_action(self.app,self.owner,row,'expense',{'amount':'200','description':'Venue'}, {'evidence':receipt});db.session.commit()
        self.assertEqual(FinancialRecord.query.count(),1)
        self.assertEqual(sum(float(x.amount) for x in FinanceLedgerEntry.query.filter_by(direction='out').all()),300)
        self.assertEqual(float(row.released-row.spent-row.returned),100)

    def test_payment_retry_does_not_double_fund(self):
        row=self.plan();self.approve_fund(row)
        path='events/'+row.id+'/fund'
        first=self.send(path,{'amount':'10'},key='stable-key');second=self.send(path,{'amount':'10'},key='stable-key')
        self.assertEqual(first.json,second.json);self.assertEqual(float(row.released),310)
        self.assertEqual(self.send(path,{'amount':'11'},key='stable-key').status_code,409)

    def test_event_close_requires_report_review_and_retirement(self):
        row=self.plan();self.approve_fund(row)
        self.send('events/'+row.id+'/start');self.send('events/'+row.id+'/complete')
        self.assertEqual(self.send('events/'+row.id+'/close').status_code,400)
        data=dict(summary='Activity held',lessons='Follow up early',follow_up='Contact leads',reach=420,leads=187,customers=31,revenue=820)
        self.assertEqual(self.send('events/'+row.id+'/report',data).status_code,200)
        self.send('events/'+row.id+'/review',{'management_review':'Checked evidence'})
        self.assertEqual(self.send('events/'+row.id+'/close').status_code,400)
        self.send('events/'+row.id+'/return_funds',{'amount':300})
        self.assertEqual(self.send('events/'+row.id+'/close').status_code,200)
        self.assertEqual(FinancialRecord.query.count(),0)

    def test_individual_owner_bypasses_submission_approval(self):
        db.session.add(OrganizationWorkspace(organization_id=self.org.id,workspace_mode='individual'));db.session.commit()
        row=self.plan();self.send('events/'+row.id+'/submit')
        self.assertEqual(row.status,'approved');self.assertEqual(float(row.approved),500)

    def test_stock_resources_are_reconciled_without_negative_stock(self):
        row=self.plan();self.approve_fund(row)
        item=InventoryItem(organization_id=self.org.id,name="Flyers",quantity=500,added_by_id=self.owner.id);db.session.add(item);db.session.commit()
        self.assertEqual(self.send('events/'+row.id+'/resource',dict(inventory_id=item.id,quantity=501)).status_code,400)
        self.assertEqual(self.send('events/'+row.id+'/resource',dict(inventory_id=item.id,quantity=500)).status_code,200)
        resource=EventResource.query.one()
        self.assertEqual(self.send('events/'+row.id+'/resource_return',dict(resource_id=resource.id,returned=70,distributed=430)).status_code,200)
        self.assertEqual(float(item.quantity),70)

    def customer(self,**extra):
        response=self.send('customers',dict(name='Ada',phone='08000000000',**extra))
        self.assertEqual(response.status_code,200,response.json)
        return db.session.get(Customer,response.json['record']['id'])

    def sale(self,customer,**extra):
        data=dict(customer_id=customer.id,description='Consultation',quantity=1,unit_price=250,amount_paid=150,due_date='2026-11-01')
        data.update(extra);response=self.send('sales',data)
        self.assertEqual(response.status_code,200,response.json)
        return db.session.get(SalesInvoice,response.json['record']['id'])

    def test_credit_sale_and_collections_recognize_revenue_once(self):
        customer=self.customer();sale=self.sale(customer)
        self.assertEqual(float(FinanceReceivable.query.one().balance),100)
        self.assertEqual(float(FinancialRecord.query.one().amount),250)
        self.assertEqual(self.send('sales/'+sale.id+'/payment',{'amount':40}).status_code,200)
        self.assertEqual(self.send('sales/'+sale.id+'/payment',{'amount':61}).status_code,400)
        from services.owner_control_service import management_workspace
        workspace=management_workspace(self.owner,'all')
        self.assertEqual(len(workspace['receivables']['rows'][0]['payments']),2)
        self.assertEqual(workspace['receivables']['rows'][0]['opening_payment'],0)
        self.assertEqual(self.send('sales/'+sale.id+'/payment',{'amount':60}).status_code,200)
        self.assertEqual(sale.status,'paid');self.assertEqual(FinancialRecord.query.count(),1)
        self.assertEqual(float(FinanceReceivable.query.one().balance),0)
        self.assertEqual(InvoicePayment.query.count(),3)
        from services.finance_service import finance_control_context
        context=finance_control_context(self.owner)
        self.assertEqual(len(context['receivable_payments'][sale.receivable_id]),3)

    def test_legacy_finance_collection_of_crm_invoice_does_not_duplicate_sales(self):
        from services.finance_service import settle_receivable
        sale=self.sale(self.customer())
        settle_receivable(self.app,self.owner,FinanceReceivable.query.one(),100)
        self.assertEqual(FinancialRecord.query.count(),1);self.assertEqual(float(sale.paid),250)

    def test_sales_stock_rollback_and_cross_tenant_customer(self):
        customer=self.customer()
        item=InventoryItem(organization_id=self.org.id,name='Medicine',quantity=2,added_by_id=self.owner.id);db.session.add(item);db.session.commit()
        response=self.send('sales',dict(customer_id=customer.id,description='Medicine',inventory_id=item.id,quantity=3,unit_price=10,amount_paid=30))
        self.assertEqual(response.status_code,400);self.assertEqual(float(item.quantity),2)
        self.assertEqual(SalesInvoice.query.count(),0)
        self.assertEqual(self.send('sales',dict(customer_id=customer.id,description='Other sale',unit_price=10),self.outsider).status_code,404)

    def test_repeat_customer_and_event_attribution(self):
        event=self.plan();customer=self.customer(event_id=event.id)
        sale=self.sale(customer);self.assertEqual(sale.event_id,event.id)
        self.sale(customer);self.assertEqual(customer.stage,'repeat_customer')

    def test_invoice_tax_is_separate_from_revenue(self):
        self.sale(self.customer(),unit_price=200,tax=15,amount_paid=215)
        self.assertEqual(float(FinancialRecord.query.one().amount),200)
        self.assertEqual(float(FinanceLedgerEntry.query.filter_by(entry_type='liability').one().amount),15)

    def test_supplier_bill_and_payments_do_not_duplicate_expense(self):
        self.assertEqual(self.send('suppliers',dict(name='ABC Technologies',contact_person='Ada',rating=5)).status_code,200)
        supplier=Supplier.query.one()
        self.assertEqual(self.send('suppliers/'+supplier.id+'/bill',dict(bill_number='ABC-1',description='Services',amount=100,due_date='2026-11-30')).status_code,200)
        bill=SupplierBill.query.one()
        self.assertEqual(self.send('supplier-bills/'+bill.id+'/payment',dict(amount=20)).status_code,200)
        from services.finance_service import settle_payable
        settle_payable(self.app,self.owner,FinancePayable.query.one(),80)
        self.assertEqual(FinancialRecord.query.count(),1);self.assertEqual(float(FinancialRecord.query.one().amount),100)
        self.assertEqual(float(FinancePayable.query.one().balance),0)
        from services.finance_service import finance_control_context
        self.assertEqual(len(finance_control_context(self.owner)['payable_payments'][bill.payable_id]),2)
        self.assertEqual(self.send('supplier-bills/'+bill.id+'/payment',dict(amount=1)).status_code,400)

    def test_imprest_receipts_and_replenishment_use_existing_requests(self):
        response=self.send('imprest',dict(name='Admin imprest',ceiling=100,holder_id=self.staff.id,department_id=self.dept.id));self.assertEqual(response.status_code,200,response.json)
        fund=db.session.get(ImprestFund,response.json['record']['id']);base='imprest/'+fund.id+'/'
        self.assertEqual(self.send(base+'issue',dict(amount=100,description='Opening float')).status_code,200)
        from services.supplier_imprest_service import imprest_action
        receipt=FileStorage(io.BytesIO(b'%PDF-1.4 imprest test receipt'),filename='imprest.pdf',content_type='application/pdf')
        imprest_action(self.app,self.owner,fund,'spend',dict(amount='38.50',description='Fuel and printing'),{'evidence':receipt});db.session.commit()
        self.assertEqual(self.send(base+'request_replenishment',dict(amount=40,description='Refill')).status_code,400)
        self.assertEqual(self.send(base+'request_replenishment',dict(amount='38.50',description='Refill spent cash'),self.staff).status_code,200)
        replenishment=ImprestReplenishment.query.one()
        self.assertEqual(self.send(base+'replenish',dict(replenishment_id=replenishment.id)).status_code,400)
        from services.operations_service import decide_request
        decide_request(self.app,self.owner,db.session.get(PurchaseRequest,replenishment.request_id),'approve')
        self.assertEqual(self.send(base+'replenish',dict(replenishment_id=replenishment.id)).status_code,200)
        self.assertEqual(float(fund.issued-fund.spent-fund.returned),100)
        self.assertEqual(float(FinancialRecord.query.one().amount),38.5)
        self.assertEqual(self.send(base+'replenish',dict(replenishment_id=replenishment.id)).status_code,400)

    def test_supplier_and_imprest_finance_actions_are_restricted(self):
        self.assertEqual(self.send('suppliers',dict(name='Private vendor'),self.staff).status_code,403)
        self.assertEqual(self.send('imprest',dict(name='Staff float',ceiling=100),self.staff).status_code,403)

    def test_new_native_pages_render_with_real_records(self):
        from flask import render_template
        from flask_login import login_user
        from jinja2 import FileSystemLoader
        from services.business_workspace import business_context
        self.app.jinja_loader=FileSystemLoader(str(Path(__file__).resolve().parents[1]/'templates'))
        self.app.jinja_env.globals['sage_money']=lambda value,*args:str(value)
        self.app.jinja_env.filters['sage_iso']=lambda value:value.isoformat()
        event=self.plan();self.approve_fund(event);customer=self.customer();invoice=self.sale(customer)
        self.send('suppliers',dict(name='Test Supplier'))
        self.send('imprest',dict(name='Test Cash',ceiling=100))
        bill_id=self.send('bills',dict(name='Test Internet',category='Internet',amount=57,next_due='2026-01-31')).json['record']['id']
        self.send('bills/'+bill_id+'/pay',dict(period_due='2026-01-31'))
        item=self.stock_item()
        self.employee();payroll=self.send('payroll',dict(month=datetime.now(timezone.utc).strftime('%Y-%m'))).json['record']['id']
        for page,params in [('events','?record='+event.id),('customers','?record='+customer.id+'&invoice='+invoice.id),('debtors','?invoice='+invoice.id),('suppliers','?record='+Supplier.query.one().id),('imprest','?record='+ImprestFund.query.one().id),('daily_close',''),('branches',''),('stock','?record='+item.id),('bills','?record='+bill_id),('compliance',''),('payroll','?record='+payroll),('business_reports','')]:
            with self.subTest(page=page),self.app.test_request_context('/'+page+params):
                g.pop('_login_user',None);login_user(self.owner)
                html=render_template('pages/'+page+'.html',owner_admin=True,departments=[self.dept],asset_custodians=[self.owner,self.staff],**business_context(self.owner,page))
                self.assertIn('data-v4-workspace',html);self.assertIn('<table',html)

    def branch_fixtures(self):
        a=BranchLocation(organization_id=self.org.id,name='Wuse',code='WUS');b=BranchLocation(organization_id=self.org.id,name='Kubwa',code='KUB')
        db.session.add_all([a,b]);db.session.flush()
        db.session.add(BranchDepartment(organization_id=self.org.id,department_id=self.dept.id,branch_id=a.id))
        db.session.commit();return a,b

    def test_branch_scope_applies_to_legacy_orm_reads_and_new_actions(self):
        a,b=self.branch_fixtures()
        self.assertEqual(self.send('branches/memberships',dict(user_id=self.staff.id,branch_id=a.id,is_manager='true')).status_code,200)
        db.session.add_all([FinancialRecord(reference='BR-A',organization_id=self.org.id,department_id=self.dept.id,record_type='revenue',description='Local',amount=100),
                           FinancialRecord(reference='BR-B',organization_id=self.org.id,record_type='revenue',description='Private',amount=900)])
        db.session.commit()
        foreign=self.plan(branch_id=b.id)
        response=self.client(self.staff).get('/branch-probe')
        self.assertEqual(response.json['amounts'],['100.00']);self.assertEqual(response.json['events'],[])
        self.assertEqual(response.json['income_total'],100)
        self.assertEqual(self.send('events/'+foreign.id+'/submit',user=self.staff).status_code,404)
        self.assertEqual(self.send('events',dict(name='Forbidden',category='Test',objective='Test',branch_id=b.id,start_at='2026-11-15T10:00Z',end_at='2026-11-15T11:00Z'),self.staff).status_code,400)
        self.assertEqual(len(self.client(self.owner).get('/branch-probe').json['amounts']),2)

    def test_daily_close_uses_collections_and_requires_independent_review(self):
        response=self.send('customers',dict(name='Local buyer'),self.staff)
        customer=db.session.get(Customer,response.json['record']['id'])
        response=self.send('sales',dict(customer_id=customer.id,description='Credit sale',quantity=1,unit_price=250,amount_paid=150,due_date='2026-11-30',method='cash'),self.staff)
        self.assertEqual(response.status_code,200,response.json)
        response=self.send('daily-close',dict(business_date=datetime.now(timezone.utc).date().isoformat(),counted_cash=150),self.staff)
        self.assertEqual(response.status_code,200,response.json);close=db.session.get(DailyClose,response.json['record']['id'])
        self.assertEqual(float(close.expected_total),150)
        self.assertEqual(self.send('daily-close/'+close.id+'/submit',user=self.staff).status_code,200)
        self.assertEqual(self.send('daily-close/'+close.id+'/approve',dict(review_notes='Self approve'),self.staff).status_code,403)
        self.assertEqual(self.send('daily-close/'+close.id+'/approve',dict(review_notes='Checked cash and POS')).status_code,200)
        self.assertEqual(FinancialRecord.query.count(),1)

    def test_daily_close_detects_late_transactions_and_requires_variance_reason(self):
        sale=self.sale(self.customer(),method='cash')
        response=self.send('daily-close',dict(business_date=datetime.now(timezone.utc).date().isoformat(),counted_cash=140))
        self.assertEqual(response.status_code,400)
        response=self.send('daily-close',dict(business_date=datetime.now(timezone.utc).date().isoformat(),counted_cash=140,explanation='Short by ten'))
        self.assertEqual(response.status_code,200,response.json);close=db.session.get(DailyClose,response.json['record']['id'])
        self.send('daily-close/'+close.id+'/submit')
        self.send('sales/'+sale.id+'/payment',dict(amount=10,method='cash'))
        # Independent finance actor uses the same business and sees the newly posted collection.
        self.staff.role='finance';db.session.commit()
        self.assertEqual(self.send('daily-close/'+close.id+'/approve',dict(review_notes='Checked'),self.staff).status_code,400)

    def stock_item(self,**extra):
        data=dict(name='Medicine',quantity=10,cost_price=5,selling_price=8);data.update(extra)
        response=self.send('stock',data);self.assertEqual(response.status_code,200,response.json)
        profile=db.session.get(StockProfile,response.json['record']['id'])
        return db.session.get(InventoryItem,profile.inventory_id)

    def test_expired_stock_is_not_sold_and_fefo_updates_batches(self):
        item=self.stock_item()
        past=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat();future=(datetime.now(timezone.utc).date()+timedelta(days=10)).isoformat()
        self.assertEqual(self.send('stock/'+item.id+'/register_batch',dict(number='OLD',quantity=5,cost_price=5,expiry_date=past)).status_code,200)
        self.assertEqual(self.send('stock/'+item.id+'/register_batch',dict(number='NEW',quantity=5,cost_price=5,expiry_date=future)).status_code,200)
        customer=self.customer()
        self.assertEqual(self.send('sales',dict(customer_id=customer.id,description='Stock sale',inventory_id=item.id,quantity=6,unit_price=8,amount_paid=48)).status_code,400)
        sale=self.sale(customer,description='Stock sale',inventory_id=item.id,quantity=4,unit_price=8,amount_paid=32)
        self.assertEqual(float(item.quantity),6)
        self.assertEqual(float(StockBatch.query.filter_by(number='NEW').one().quantity),1)
        self.assertEqual(float(StockBatch.query.filter_by(number='OLD').one().quantity),5)

    def test_transfer_keeps_total_stock_and_batch_expiry(self):
        source=self.stock_item(quantity=10);target=self.stock_item(quantity=0,location='Second shop')
        self.send('stock/'+source.id+'/register_batch',dict(number='B1',quantity=10,cost_price=5,expiry_date='2027-10-01'))
        self.assertEqual(self.send('stock/'+source.id+'/transfer',dict(target_id=target.id,quantity=3,reason='Restock second shop')).status_code,200)
        self.assertEqual(float(source.quantity+target.quantity),10)
        self.assertEqual(float(StockBatch.query.filter_by(inventory_id=target.id).one().quantity),3)
        self.assertEqual(str(StockBatch.query.filter_by(inventory_id=target.id).one().expiry_date),'2027-10-01')

    def test_stock_count_approval_rejects_stale_count(self):
        item=self.stock_item();self.send('stock/'+item.id+'/count',dict(counted=8,reason='Physical count'))
        count=StockCount.query.one()
        self.send('stock/'+item.id+'/issue',dict(quantity=1,reason='Usage after count'))
        self.assertEqual(self.send('stock/'+item.id+'/approve_count',dict(count_id=count.id)).status_code,400)
        self.assertEqual(float(item.quantity),9)

    def test_bill_payment_is_once_per_period_and_month_end_is_preserved(self):
        response=self.send('bills',dict(name='Internet',category='Internet',amount=57,frequency='monthly',next_due='2026-01-31'))
        self.assertEqual(response.status_code,200,response.json);bill=db.session.get(BillPlan,response.json['record']['id'])
        self.assertEqual(self.send('bills/'+bill.id+'/pay',dict(period_due='2026-01-31')).status_code,200)
        self.assertEqual(str(bill.next_due),'2026-02-28')
        self.assertEqual(self.send('bills/'+bill.id+'/pay',dict(period_due='2026-01-31')).status_code,400)
        self.assertEqual(self.send('bills/'+bill.id+'/pay',dict(period_due='2026-02-28')).status_code,200)
        self.assertEqual(str(bill.next_due),'2026-03-31');self.assertEqual(FinancialRecord.query.count(),2)

    def test_compliance_history_and_reminders_are_deduplicated(self):
        from services.renewal_service import create_document,document_action
        from services.business_reminders import generate_reminders
        due=datetime.now(timezone.utc).date()+timedelta(days=1)
        file=FileStorage(io.BytesIO(b'%PDF-1.4 insurance test'),filename='insurance.pdf')
        document=create_document(self.app,self.owner,dict(name='Insurance',category='Insurance',expiry_date=due.isoformat()),{'evidence':file});db.session.commit()
        self.assertEqual(generate_reminders(self.app,self.org.id),1);db.session.commit()
        self.assertEqual(generate_reminders(self.app,self.org.id),0)
        self.assertEqual(Notification.query.filter_by(entity_type='compliance').count(),1)
        renewed=FileStorage(io.BytesIO(b'%PDF-1.4 renewed insurance'),filename='renewed.pdf')
        document_action(self.app,self.owner,document,'renew',dict(expiry_date=(due+timedelta(days=365)).isoformat(),notes='Renewed policy'),{'evidence':renewed});db.session.commit()
        self.assertIsNotNone(document.renewed_at)

    def employee(self,**extra):
        data=dict(user_id=self.staff.id,employment_date='2020-01-01',salary=1000,allowance=100,commission_rate=3,paye=100,pension_rate=8,employer_pension_rate=10,loan_deduction=50)
        data.update(extra);response=self.send('employees',data);self.assertEqual(response.status_code,200,response.json)
        return db.session.get(EmployeeProfile,response.json['record']['id'])

    def test_payroll_commission_advance_recovery_and_cash_are_connected(self):
        self.employee()
        customer_response=self.send('customers',dict(name='Commission buyer'),self.staff)
        customer=db.session.get(Customer,customer_response.json['record']['id'])
        response=self.send('sales',dict(customer_id=customer.id,description='Commission sale',quantity=1,unit_price=1000,amount_paid=1000),self.staff)
        self.assertEqual(response.status_code,200,response.json)
        response=self.send('advances',dict(amount=200,due_date='2026-12-31',kind='staff_loan',reason='Staff loan'),self.staff)
        advance=db.session.get(StaffAdvance,response.json['record']['id'])
        self.send('advances/'+advance.id+'/approve');self.send('advances/'+advance.id+'/issue')
        response=self.send('payroll',dict(month=datetime.now(timezone.utc).strftime('%Y-%m')))
        self.assertEqual(response.status_code,200,response.json);run=db.session.get(PayrollRun,response.json['record']['id']);slip=PayrollSlip.query.one()
        self.assertEqual(float(slip.commission),30);self.assertEqual(float(slip.net),892)
        self.assertEqual(self.send('payroll/'+run.id+'/pay',dict(tax_due_date='2026-12-10')).status_code,400)
        self.assertIn(self.send('payroll/'+run.id+'/approve',user=self.staff).status_code,{403,404})
        self.send('payroll/'+run.id+'/approve')
        self.assertEqual(self.send('payroll/'+run.id+'/pay',dict(tax_due_date='2026-12-10')).status_code,200)
        self.assertEqual(float(advance.repaid),50)
        self.assertEqual(float(FinancialRecord.query.filter_by(record_type='payroll').one().amount),1240)
        self.assertEqual(PayrollEntry.query.one().status,'paid')
        self.assertEqual(self.send('payroll/'+run.id+'/pay',dict(tax_due_date='2026-12-10')).status_code,400)
        self.assertEqual(self.send('payroll/'+run.id+'/remit').status_code,200)
        self.assertEqual(FinancialRecord.query.filter_by(record_type='payroll').count(),1)
        self.assertEqual(self.send('payroll',dict(month=datetime.now(timezone.utc).strftime('%Y-%m'))).status_code,400)

    def test_payroll_rejects_deductions_greater_than_pay(self):
        self.employee(salary=10,allowance=0,paye=100)
        self.assertEqual(self.send('payroll',dict(month=datetime.now(timezone.utc).strftime('%Y-%m'))).status_code,400)
        self.assertEqual(PayrollRun.query.count(),0);self.assertEqual(PayrollEntry.query.count(),0)

    def test_claim_payment_is_one_expense_and_staff_cannot_approve(self):
        from services.payroll_service import create_claim
        file=FileStorage(io.BytesIO(b'%PDF-1.4 claim receipt'),filename='claim.pdf')
        claim=create_claim(self.app,self.staff,dict(description='Transport',amount=25),{'evidence':file});db.session.commit()
        self.assertEqual(self.send('claims/'+claim.id+'/approve',dict(review_notes='Self approval'),self.staff).status_code,403)
        self.assertEqual(self.send('claims/'+claim.id+'/approve',dict(review_notes='Checked receipt')).status_code,200)
        self.assertEqual(self.send('claims/'+claim.id+'/pay').status_code,200)
        self.assertEqual(self.send('claims/'+claim.id+'/pay').status_code,400)
        self.assertEqual(float(FinancialRecord.query.one().amount),25)

    def test_report_exports_and_automation_are_scoped(self):
        self.sale(self.customer())
        from services.finance_service import post_ledger_entry
        post_ledger_entry(self.app,self.owner,dict(entry_type='expense',description='Reporting expense',amount=300))
        response=self.client(self.owner).get('/api/v4/export/summary.csv')
        self.assertEqual(response.status_code,200);self.assertIn('receivables',response.text)
        import csv
        values=dict(list(csv.reader(io.StringIO(response.text.lstrip('\ufeff'))))[1:])
        self.assertEqual(float(values['net']),-50)
        self.assertEqual(self.send('customers',dict(name='=1+1')).status_code,200)
        self.assertIn("'=1+1",self.client(self.owner).get('/api/v4/export/customers.csv').text)
        self.assertEqual(self.client(self.staff).get('/api/v4/export/payroll.csv').status_code,403)
        self.assertEqual(self.send('automation/run',user=self.staff).status_code,403)
        self.assertEqual(self.send('automation/run').status_code,200)

    def test_campaign_allocates_existing_funds_without_second_cash_outflow(self):
        campaign=self.plan(kind='campaign',requested=1000)
        self.send('events/'+campaign.id+'/submit');self.send('events/'+campaign.id+'/approve',dict(amount=1000))
        child=self.plan(parent_id=campaign.id,requested=600)
        self.send('events/'+child.id+'/submit');self.send('events/'+child.id+'/approve',dict(amount=600))
        self.assertEqual(self.send('events/'+campaign.id+'/fund',dict(amount=1000)).status_code,200)
        self.assertEqual(self.send('events/'+child.id+'/fund',dict(amount=600)).status_code,400)
        response=self.send('events/'+campaign.id+'/allocate',dict(event_id=child.id,amount=600,notes='Release to activity manager'))
        self.assertEqual(response.status_code,200,response.json)
        from services.event_service import event_balance,event_outcome
        self.assertEqual(float(event_balance(campaign)),400);self.assertEqual(float(event_balance(child)),600)
        self.assertEqual(float(event_outcome(self.owner,campaign)['released']),1000)
        self.assertEqual(sum(float(e.amount) for e in FinanceLedgerEntry.query.filter_by(direction='out')),1000)
        extra=self.plan(parent_id=campaign.id,requested=500)
        self.send('events/'+extra.id+'/submit')
        self.assertEqual(self.send('events/'+extra.id+'/approve',dict(amount=500)).status_code,400)

    def test_schema_install_is_idempotent_and_preserves_existing_rows(self):
        from services.business_schema import install_business_schema
        before=User.query.count();self.assertEqual(install_business_schema(),[])
        self.assertEqual(install_business_schema(),[]);self.assertEqual(User.query.count(),before)

    def test_imprest_request_cannot_be_funded_again_through_legacy_grant_action(self):
        from services.operations_service import decide_request
        self.send('imprest',dict(name='Accountable float',ceiling=100,holder_id=self.staff.id,department_id=self.dept.id))
        fund=ImprestFund.query.one()
        req=PurchaseRequest(organization_id=self.org.id,department_id=self.dept.id,requester_id=self.staff.id,reference='IMP-BYPASS',title='Replenish',estimated_total=20,status='approved')
        db.session.add(req);db.session.flush()
        db.session.add(ImprestReplenishment(organization_id=self.org.id,department_id=self.dept.id,created_by_id=self.staff.id,fund_id=fund.id,request_id=req.id,amount=20));db.session.commit()
        with self.assertRaises(ValueError):decide_request(self.app,self.owner,req,' MONEY_SENT ')
        self.assertEqual(FinanceLedgerEntry.query.count(),0)
        decide_request(self.app,self.owner,req,'reject')
        self.assertEqual(ImprestReplenishment.query.one().status,'rejected')

    def test_property_can_be_assigned_to_a_branch_without_departments(self):
        a,b=self.branch_fixtures();item=self.stock_item()
        response=self.send('branches/property',dict(record='stock:'+item.id,branch_id=b.id,reason='Opening branch allocation'))
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(StockProfile.query.filter_by(inventory_id=item.id).one().branch_id,b.id)
        self.assertEqual(self.send('branches/property',dict(record='stock:'+item.id,branch_id=a.id,reason='Unsafe reassignment')).status_code,400)

    def test_financial_trace_connects_crm_sale_and_event(self):
        from services.record_trace_service import record_trace
        from services.event_service import event_outcome
        event=self.plan();customer=self.customer(event_id=event.id);sale=self.sale(customer)
        financial=FinancialRecord.query.one();trace=record_trace(self.owner,'financial_record',financial.id)
        ids={r['id'] for r in trace['records']}
        self.assertIn(sale.id,ids);self.assertIn(customer.id,ids);self.assertIn(event.id,ids)
        self.assertEqual(float(event_outcome(self.owner,event)['invoice_revenue']),250)

    def test_stale_concurrent_updates_cannot_overwrite_financial_state(self):
        from sqlalchemy.orm import Session
        from sqlalchemy.orm.exc import StaleDataError
        event=self.plan()
        with Session(db.engine) as first,Session(db.engine) as second:
            a=first.get(EventPlan,event.id);b=second.get(EventPlan,event.id)
            a.notes='First committed change';first.commit()
            b.notes='Stale overwrite'
            with self.assertRaises(StaleDataError):second.commit()
            second.rollback()
        db.session.expire_all();self.assertEqual(db.session.get(EventPlan,event.id).notes,'First committed change')

    def test_nonfinite_amounts_and_fractional_headcounts_are_rejected(self):
        for value in ['NaN','Infinity','-1']:
            self.assertEqual(self.send('bills',dict(name='Invalid',category='Test',amount=value,next_due='2026-11-01')).status_code,400)
        response=self.send('events',dict(name='Invalid count',category='Test',objective='Test',start_at='2026-11-01T09:00Z',end_at='2026-11-01T17:00Z',expected_leads='1.001'))
        self.assertEqual(response.status_code,400)

    def test_assigned_staff_can_find_plans_and_cash_without_owner_selecting_departments(self):
        event=self.plan(manager_id=self.staff.id)
        self.assertEqual(event.department_id,self.dept.id)
        self.assertEqual(self.send('events/'+event.id+'/submit',user=self.staff).status_code,200)
        response=self.send('imprest',dict(name='Assigned float',ceiling=100,holder_id=self.staff.id))
        self.assertEqual(response.status_code,200,response.json)
        fund=db.session.get(ImprestFund,response.json['record']['id']);self.assertEqual(fund.department_id,self.dept.id)

    def test_assigned_bill_is_readable_but_staff_cannot_pay(self):
        from services.business_core import get_row
        from services.access_control import can_access_page
        response=self.send('bills',dict(name='Assigned internet',category='Internet',amount=57,next_due='2026-11-01',responsible_id=self.staff.id))
        self.assertEqual(response.status_code,200,response.json);bill=db.session.get(BillPlan,response.json['record']['id'])
        self.assertEqual(get_row(BillPlan,self.staff,bill.id).id,bill.id)
        self.assertTrue(can_access_page(self.staff,'bills'))
        self.assertEqual(self.send('bills/'+bill.id+'/pay',dict(period_due='2026-11-01'),self.staff).status_code,403)
