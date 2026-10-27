"""Recurring bills and dated compliance evidence; payments use the common ledger."""
import calendar
from datetime import timedelta
from uuid import uuid4
from models import BillPlan, BillPayment, ComplianceDocument, ComplianceRenewal, Supplier
from packages.database import db
from services.business_core import *
from services.storage_service import save_attachment
from services.operational_policy import require_operational

FREQUENCIES=('once','weekly','monthly','quarterly','yearly')


def next_due(row):
    if row.frequency=='weekly':return row.next_due+timedelta(days=7)
    months={'monthly':1,'quarterly':3,'yearly':12}[row.frequency]
    index=row.next_due.year*12+row.next_due.month-1+months;year,month=divmod(index,12);month+=1
    return row.next_due.replace(year=year,month=month,day=min(row.first_due.day,calendar.monthrange(year,month)[1]))


def create_bill(app,user,data):
    require_operational(user,"bills","bill / subscription scheduling");frequency=data.get('frequency','monthly')
    if frequency not in FREQUENCIES:raise ValueError('Choose a valid payment frequency.')
    row=BillPlan(id=str(uuid4()),**dimensions(user,data),responsible_id=user.id,name=text_value(data,'name',True,180),
        category=text_value(data,'category',True,100),amount=money(data.get('amount'),True),frequency=frequency,
        first_due=day(data.get('next_due')),next_due=day(data.get('next_due')),notes=text_value(data,'notes'))
    responsible=worker(user,data.get('responsible_id'));align_worker(user,row,responsible,data);row.responsible_id=responsible.id
    if data.get('supplier_id'):row.supplier_id=tenant_row(Supplier,user,data['supplier_id']).id
    db.session.add(row);db.session.flush();activity(app,user,row,'bill_created','Bill / subscription scheduled','bill')
    return row


def bill_action(app,user,row,action,data,files=None):
    require_operational(user,"bills","bill / renewal operations");files=files or {}
    if action=='pay':
        if row.status!='active':raise ValueError('This bill is no longer active.')
        due=day(data.get('period_due'))
        if due!=row.next_due:raise ValueError('The due period changed. Refresh before paying.')
        payment=BillPayment(id=str(uuid4()),**inherited(user,row),bill_id=row.id,period_due=due,amount=row.amount,paid_at=instant(data.get('occurred_at')))
        posting=post(user,row,'bill:'+row.id+':'+due.isoformat(),row.amount,'expense','out',data,'expense',row.name+' · '+due.isoformat())
        payment.posting_id=posting.id;db.session.add(payment)
        if files.get('evidence'):save_attachment(app,files['evidence'],user,'bill',row.id,'bill_receipt',True)
        if row.frequency=='once':row.status='paid';row.closed_at=instant()
        else:row.next_due=next_due(row)
    elif action=='cancel':
        if row.status!='active':raise ValueError('Only active bills can be cancelled.')
        row.notes=(row.notes or '')+'\nCancelled: '+text_value(data,'reason',True);row.status='cancelled';row.closed_at=instant()
    elif action=='update':
        if row.status!='active':raise ValueError('Only active bills can change.')
        row.amount=money(data.get('amount'),True);row.notes=text_value(data,'notes',True)
    elif action=='evidence':
        if not files.get('evidence'):raise ValueError('Choose a document.')
        save_attachment(app,files['evidence'],user,'bill',row.id,'bill_document')
    else:raise ValueError('Unsupported bill action.')
    activity(app,user,row,'bill_'+action,'Bill · '+action,'bill');return row


def create_document(app,user,data,files=None):
    require_operational(user,"compliance","compliance document registration");files=files or {}
    row=ComplianceDocument(id=str(uuid4()),**dimensions(user,data),responsible_id=user.id,
        name=text_value(data,'name',True,180),category=text_value(data,'category',True,100),identifier=text_value(data,'identifier',limit=180),
        issued_date=day(data.get('issued_date'),False),expiry_date=day(data.get('expiry_date')),notes=text_value(data,'notes'))
    responsible=worker(user,data.get('responsible_id'));align_worker(user,row,responsible,data);row.responsible_id=responsible.id
    if row.issued_date and row.issued_date>row.expiry_date:raise ValueError('Expiry cannot precede the issue date.')
    if data.get('bill_id'):row.bill_id=get_row(BillPlan,user,data['bill_id']).id
    if not files.get('evidence'):raise ValueError('Attach the compliance document.')
    db.session.add(row);db.session.flush();save_attachment(app,files['evidence'],user,'compliance',row.id,'compliance_document')
    activity(app,user,row,'compliance_created','Compliance document registered','compliance');return row


def document_action(app,user,row,action,data,files=None):
    require_operational(user,"compliance","compliance renewal / document control");files=files or {}
    if action=='renew':
        if row.status!='active':raise ValueError('Archived documents cannot be renewed.')
        expiry=day(data.get('expiry_date'))
        if expiry<=row.expiry_date:raise ValueError('Renewal must extend the current expiry date.')
        if not files.get('evidence'):raise ValueError('Attach the renewed document.')
        db.session.add(ComplianceRenewal(**inherited(user,row),document_id=row.id,previous_expiry=row.expiry_date,new_expiry=expiry,notes=text_value(data,'notes',True)))
        row.expiry_date=expiry;row.renewed_at=instant();save_attachment(app,files['evidence'],user,'compliance',row.id,'compliance_renewal')
    elif action=='archive':row.status='archived';row.notes=(row.notes or '')+'\nArchived: '+text_value(data,'reason',True)
    elif action=='evidence':
        if not files.get('evidence'):raise ValueError('Choose a document.')
        save_attachment(app,files['evidence'],user,'compliance',row.id,'compliance_document')
    else:raise ValueError('Unsupported compliance action.')
    activity(app,user,row,'compliance_'+action,'Compliance · '+action,'compliance');return row
