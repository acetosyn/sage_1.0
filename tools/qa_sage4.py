"""Isolated full-app smoke/browser harness. Never opens the user's live database."""
import os
import sys
import tempfile
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
QA_DIR=tempfile.TemporaryDirectory(prefix='sage-v4-browser-')
os.environ.update(DATABASE_URL='sqlite:///'+(Path(QA_DIR.name)/'qa.db').as_posix(),SAGE_STORAGE_DIR=QA_DIR.name,
    SAGE_AUTO_CREATE_SCHEMA='true',SAGE_DEBUG='false',EMAIL_NOTIFICATIONS_ENABLED='false',WEB_PUSH_ENABLED='false',
    SESSION_COOKIE_SECURE='false',SAGE_ENV='development',SECRET_KEY='isolated-qa-secret')
from app import app
from packages.database import db
from models import Organization,OrganizationWorkspace,User,Department,EventPlan,StockProfile,InventoryItem
from flask import g,redirect
from flask_login import login_user
from services.event_service import create_event
from services.sales_service import create_customer,create_invoice
from services.stock_service import create_stock
from services.renewal_service import create_bill
from services.payroll_service import save_employee,generate_payroll


def fixtures():
    with app.app_context():
        org=Organization(name='SAGE 4.0 QA Organization',slug='qa-organization',business_type='Retail')
        solo=Organization(name='SAGE 4.0 QA Entrepreneur',slug='qa-individual',business_type='Retail')
        db.session.add_all([org,solo]);db.session.flush()
        db.session.add_all([OrganizationWorkspace(organization_id=org.id,workspace_mode='organization'),OrganizationWorkspace(organization_id=solo.id,workspace_mode='individual')])
        dept=Department(organization_id=org.id,name='Sales');db.session.add(dept);db.session.flush()
        users={}
        for name,role,business,department in [('owner','owner',org,None),('staff','staff',org,dept),('finance','finance',org,dept),('solo','owner',solo,None)]:
            person=User(organization_id=business.id,department_id=department.id if department else None,first_name=name.title(),last_name='QA',email=name+'@sage-qa.test',role=role)
            person.set_password('isolated-qa-only');db.session.add(person);users[name]=person
        db.session.commit()
        now=datetime.now(timezone.utc)
        for name in ('owner','solo'):
            owner=users[name]
            event=create_event(app,owner,dict(name='Customer Acquisition Outreach',category='Marketing',objective='Acquire qualified customer leads',start_at=(now+timedelta(days=7)).isoformat(),end_at=(now+timedelta(days=7,hours=8)).isoformat(),requested=500000,expected_leads=150,expected_customers=30))
            profile=create_stock(app,owner,dict(name='Health Kit',quantity=50,cost_price=4500,selling_price=7500,reorder_level=5,unit='kit'))
            customer=create_customer(app,owner,dict(name='Ada Example',phone='08000000000',stage='prospect',event_id=event.id))
            create_invoice(app,owner,dict(customer_id=customer.id,description='Business service package',unit_price=250000,quantity=1,amount_paid=150000,due_date=(now+timedelta(days=7)).date().isoformat(),method='bank_transfer'))
            create_bill(app,owner,dict(name='Business Internet',category='Internet',amount=57000,frequency='monthly',next_due=(now+timedelta(days=4)).date().isoformat()))
        save_employee(app,users['owner'],dict(user_id=users['staff'].id,employment_date='2020-01-01',salary=100000,allowance=10000))
        generate_payroll(app,users['owner'],dict(month=now.strftime('%Y-%m')))
        db.session.commit()
        return {name:person.id for name,person in users.items()}


USERS=fixtures()

@app.get('/qa-session/<name>')
def qa_session(name):
    from flask import session,abort
    if name not in USERS:abort(404)
    session.clear();g.pop('_login_user',None);login_user(db.session.get(User,USERS[name]));return redirect('/events')


def smoke():
    pages=['dashboard','events','customers','debtors','suppliers','imprest','daily_close','branches','stock','bills','compliance','payroll','business_reports','income','expenses','finance','requests','procurement','inventory','assets','reports','audit','settings']
    failures=[];checked=0
    for name in USERS:
        with app.test_client() as client:
            client.get('/qa-session/'+name)
            for page in pages:
                response=client.get('/'+page)
                expected=200
                from services.access_control import can_access_page
                with app.app_context():expected=200 if can_access_page(db.session.get(User,USERS[name]),page) else 403
                if response.status_code!=expected:failures.append((name,page,response.status_code,expected))
                checked+=1
                if expected==200:
                    response=client.get('/partial/'+page)
                    if response.status_code!=200:failures.append((name,'partial/'+page,response.status_code,200))
                    checked+=1
    print({'smoke_responses_checked':checked,'failures':failures})
    if failures:raise SystemExit(1)


if __name__=='__main__':
    try:
        if '--smoke' in sys.argv:smoke()
        else:
            logging.getLogger('werkzeug').setLevel(logging.ERROR)
            app.run(host='127.0.0.1',port=5016,debug=False,use_reloader=False)
    finally:
        with app.app_context():db.session.remove();db.engine.dispose()
        QA_DIR.cleanup()
