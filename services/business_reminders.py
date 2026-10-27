"""Deduplicated in-app reminders; safe to call repeatedly from web or a scheduler."""
from datetime import date, timedelta
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from models import (BillPlan, ComplianceDocument, StockProfile, InventoryItem, Customer, SalesInvoice,
                    BusinessReminder, Notification, User, EventPlan, FinancePayable, FinanceReceivable, StockBatch)
from packages.database import db
from services.business_core import inherited, OWNER


def due_bucket(due,today,compliance=False):
    days=(due-today).days
    if days<0:return 'overdue'
    if days<=1:return 'today' if days==0 else 'tomorrow'
    if days<=7:return 'within 7 days'
    if compliance and days<=30:return 'within 30 days'
    return None


def reminder(app,source,kind,due,title,description,responsible_id=None,today=None):
    today=today or date.today();bucket=due_bucket(due,today,kind=='compliance')
    if not bucket:return 0
    owners=User.query.filter(User.organization_id==source.organization_id,User.role.in_(OWNER),User.status=='active').all()
    recipients={u.id:u for u in owners}
    if responsible_id:
        person=User.query.filter_by(organization_id=source.organization_id,id=responsible_id,status='active').first()
        if person:recipients[person.id]=person
    total=0
    for person in recipients.values():
        key=f'{kind}:{source.id}:{due}:{bucket}:{person.id}'
        if BusinessReminder.query.filter_by(organization_id=source.organization_id,dedupe_key=key).first():continue
        try:
            with db.session.begin_nested():
                note=Notification(id=str(uuid4()),organization_id=source.organization_id,user_id=person.id,
                    title=title+' · '+bucket,message=description,level='warning' if bucket=='overdue' else 'info',entity_type=kind,entity_id=source.id)
                db.session.add(note);db.session.flush()
                db.session.add(BusinessReminder(**inherited(person,source),user_id=person.id,dedupe_key=key,notification_id=note.id));db.session.flush()
            total+=1
        except IntegrityError:pass  # Another scheduler won this reminder's unique key.
    return total


def generate_reminders(app,organization_id,today=None):
    today=today or date.today();total=0
    for row in BillPlan.query.filter_by(organization_id=organization_id,status='active'):
        total+=reminder(app,row,'bill',row.next_due,row.name,f'{row.name}: {row.amount:,.2f} due {row.next_due}.',row.responsible_id,today)
    for row in ComplianceDocument.query.filter_by(organization_id=organization_id,status='active'):
        total+=reminder(app,row,'compliance',row.expiry_date,row.name,f'{row.name}: renewal / filing due {row.expiry_date}.',row.responsible_id,today)
    for row in Customer.query.filter(Customer.organization_id==organization_id,Customer.next_follow_up.isnot(None)):
        total+=reminder(app,row,'customer',row.next_follow_up,'Customer follow-up',f'Follow up with {row.name} by {row.next_follow_up}.',row.assigned_to_id,today)
    for row in SalesInvoice.query.filter(SalesInvoice.organization_id==organization_id,SalesInvoice.status.in_(['issued','partial']),SalesInvoice.due_date.isnot(None)):
        total+=reminder(app,row,'sale',row.due_date,'Customer balance due',f'{row.number}: {row.total-row.paid:,.2f} outstanding; due {row.due_date}.',row.sales_person_id,today)
    for row in EventPlan.query.filter(EventPlan.organization_id==organization_id,EventPlan.status.in_(['approved','funded'])):
        total+=reminder(app,row,'event',row.start_at.date(),'Upcoming activity',f'{row.name} starts {row.start_at}.',row.manager_id,today)
    for profile in StockProfile.query.filter_by(organization_id=organization_id):
        item=InventoryItem.query.filter_by(organization_id=organization_id,id=profile.inventory_id).first()
        if item and item.quantity<=item.reorder_level:
            total+=reminder(app,profile,'inventory_item',today,'Low stock',f'{item.name}: {item.quantity:g} {item.unit} available; reorder level {item.reorder_level:g}.',item.added_by_id,today)
    for batch in StockBatch.query.filter(StockBatch.organization_id==organization_id,StockBatch.quantity>0,StockBatch.expiry_date.isnot(None)):
        total+=reminder(app,batch,'stock_expiry',batch.expiry_date,'Stock batch expiry',f'Batch {batch.number}: {batch.quantity:g} remaining; expires {batch.expiry_date}.',batch.created_by_id,today)
    linked={s.receivable_id for s in SalesInvoice.query.filter_by(organization_id=organization_id)}
    for row in FinanceReceivable.query.filter(FinanceReceivable.organization_id==organization_id,FinanceReceivable.status.in_(['open','partial','overdue']),FinanceReceivable.due_date.isnot(None)):
        if row.id not in linked and row.balance:
            total+=reminder(app,row,'receivable',row.due_date,'Customer balance due',f'{row.customer_name}: {row.balance:,.2f} due {row.due_date}.',row.created_by_id,today)
    for row in FinancePayable.query.filter(FinancePayable.organization_id==organization_id,FinancePayable.status.in_(['open','partial','overdue']),FinancePayable.due_date.isnot(None)):
        if row.balance:total+=reminder(app,row,'payable',row.due_date,'Supplier balance due',f'{row.vendor_name}: {row.balance:,.2f} due {row.due_date}.',row.created_by_id,today)
    return total
