"""Branch access applies to legacy ORM reads as well as the new business modules."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import uuid4
from flask import g, has_request_context
from flask_login import current_user
from sqlalchemy import event, select, or_
from sqlalchemy.orm import Session, with_loader_criteria
from models import (BranchLocation, BranchDepartment, BranchMembership, BranchAccount, BusinessRecordScope,
    DailyClose, FinanceLedgerEntry, BusinessPosting, Department, FinanceAccount, User, InventoryItem, AssetItem)
from packages.database import db
from services.business_core import *
from services.operational_policy import can_operate, require_operational


def branch_orm_scope(state):
    limits=getattr(g,'sage_branch_limits',None) if has_request_context() else None
    if not limits or not state.is_select:return
    org_id,branch_id,dept_ids,account_ids,supplier_ids=limits
    for mapper in db.Model.registry.mappers:
        model=mapper.class_;table=model.__table__
        if 'organization_id' not in table.c:continue
        condition=None
        if model is User:continue  # Identity lookups also deliver owner notifications; staff lists are scoped at the page/API boundary.
        if model is BranchLocation:condition=model.id==branch_id
        elif model is Department:condition=model.id.in_(dept_ids)
        elif model is FinanceAccount:condition=model.id.in_(account_ids)
        elif table.name=='suppliers':condition=model.id.in_(supplier_ids)
        elif table.name=='stock_movements':
            linked=select(BusinessRecordScope.entity_id).where(BusinessRecordScope.organization_id==org_id,BusinessRecordScope.branch_id==branch_id,BusinessRecordScope.entity_type=='inventory_items')
            items=select(InventoryItem.id).where(InventoryItem.organization_id==org_id,or_(InventoryItem.department_id.in_(dept_ids),InventoryItem.id.in_(linked)))
            condition=model.inventory_item_id.in_(items)
        elif table.name=='asset_movements':
            tagged=select(BusinessRecordScope.entity_id).where(BusinessRecordScope.organization_id==org_id,BusinessRecordScope.branch_id==branch_id,BusinessRecordScope.entity_type=='asset_items')
            condition=or_(model.source_department_id.in_(dept_ids),model.destination_department_id.in_(dept_ids),model.asset_id.in_(select(AssetItem.id).where(AssetItem.organization_id==org_id,or_(AssetItem.department_id.in_(dept_ids),AssetItem.id.in_(tagged)))))
        elif 'branch_id' in table.c:
            condition=or_(model.branch_id==branch_id,model.department_id.in_(dept_ids))
        elif 'department_id' in table.c:
            linked=select(BusinessRecordScope.entity_id).where(BusinessRecordScope.organization_id==org_id,BusinessRecordScope.branch_id==branch_id,BusinessRecordScope.entity_type==table.name)
            condition=or_(model.department_id.in_(dept_ids),model.id.in_(linked))
        if condition is not None:
            state.statement=state.statement.options(with_loader_criteria(model,condition,include_aliases=True))


def bind_branch_scope():
    g.pop('sage_branch_limits',None)
    from flask import request
    if request.path.startswith('/platform-admin'):return
    if not current_user.is_authenticated or current_user.role in OWNER:return
    # Read memberships through Core to avoid recursively applying their own scope.
    connection=db.session.connection();member=connection.execute(select(BranchMembership.__table__).where(BranchMembership.user_id==current_user.id,BranchMembership.organization_id==current_user.organization_id)).mappings().first()
    if not member:return
    org=current_user.organization_id;branch_id=member['branch_id']
    departments=tuple(connection.execute(select(BranchDepartment.department_id).where(BranchDepartment.organization_id==org,BranchDepartment.branch_id==branch_id)).scalars())
    accounts=tuple(connection.execute(select(BranchAccount.account_id).where(BranchAccount.organization_id==org,BranchAccount.branch_id==branch_id)).scalars())
    from models import SupplierProfile
    suppliers=tuple(connection.execute(select(SupplierProfile.supplier_id).where(SupplierProfile.organization_id==org,SupplierProfile.branch_id==branch_id)).scalars())
    g.sage_branch_limits=(org,branch_id,departments,accounts,suppliers)


def install_branch_scope(app):
    if not event.contains(Session,'do_orm_execute',branch_orm_scope):event.listen(Session,'do_orm_execute',branch_orm_scope)
    app.before_request(bind_branch_scope)


def save_membership(app,user,data):
    require_role(user,OWNER)
    person=worker(user,data.get('user_id'))
    if person.role in OWNER:raise ValueError('Owners already have business-wide access.')
    branch=tenant_row(BranchLocation,user,data.get('branch_id'))
    if not branch.is_active:raise ValueError('Choose an active branch.')
    link=BranchDepartment.query.filter_by(organization_id=user.organization_id,department_id=person.department_id).first() if person.department_id else None
    if link and link.branch_id!=branch.id:raise ValueError('Move the staff department into the same branch before assigning branch access.')
    row=BranchMembership.query.filter_by(organization_id=user.organization_id,user_id=person.id).first()
    if not row:row=BranchMembership(id=str(uuid4()),**dimensions(user,dict(branch_id=branch.id,department_id='')),user_id=person.id);db.session.add(row)
    row.branch_id=branch.id;row.is_manager=str(data.get('is_manager','false')).lower() in {'true','1','yes'}
    activity(app,user,row,'branch_access','Branch access assigned','branch')
    return row


def assign_account(app,user,data):
    require_role(user,OWNER)
    branch=tenant_row(BranchLocation,user,data.get('branch_id'));account=tenant_row(FinanceAccount,user,data.get('account_id'))
    row=BranchAccount.query.filter_by(organization_id=user.organization_id,account_id=account.id).first()
    if not row:row=BranchAccount(id=str(uuid4()),**dimensions(user,dict(branch_id=branch.id,department_id='')),account_id=account.id);db.session.add(row)
    row.branch_id=branch.id
    activity(app,user,row,'branch_account','Branch finance account assigned','branch')
    return row


def assign_property(app,user,data):
    require_role(user,OWNER)
    from models import StockProfile,StockBatch
    record=str(data.get('record') or '').split(':',1)
    if len(record)!=2 or record[0] not in {'asset','stock'}:raise ValueError('Choose a stock balance or asset.')
    item=get_row(AssetItem if record[0]=='asset' else InventoryItem,user,record[1],True)
    dims=dimensions(user,dict(branch_id=data.get('branch_id'),department_id=item.department_id or ''))
    if not dims['branch_id']:raise ValueError('Choose a branch.')
    tagged=BusinessRecordScope.query.filter_by(organization_id=user.organization_id,entity_type=item.__tablename__,entity_id=item.id).first()
    if tagged and tagged.branch_id!=dims['branch_id']:raise ValueError('Use an accountable transfer to move property already assigned to another branch.')
    if not tagged:
        tagged=BusinessRecordScope(id=str(uuid4()),**dims,entity_type=item.__tablename__,entity_id=item.id);db.session.add(tagged)
    if record[0]=='stock':
        from services.stock_service import stock_profile
        profile=stock_profile(user,item)
        if profile.branch_id and profile.branch_id!=dims['branch_id']:raise ValueError('Use Stock Control to transfer this balance.')
        profile.branch_id=dims['branch_id']
        for batch in StockBatch.query.filter_by(organization_id=user.organization_id,inventory_id=item.id):batch.branch_id=dims['branch_id']
    activity(app,user,tagged,'branch_property','Property assigned to branch: '+text_value(data,'reason',True),'branch')
    return tagged


def channel(value):
    normalized=str(value or 'other').lower().replace(' ','_').replace('-','_')
    return {'transfer':'bank_transfer','bank':'bank_transfer','banktransfer':'bank_transfer'}.get(normalized,normalized if normalized in METHODS else 'other')


def takings(user,business_date,branch_id=None,department_id=None):
    zone=ZoneInfo('Africa/Lagos') if user.organization.country.lower()=='nigeria' else timezone.utc
    start=datetime.combine(business_date,time.min,tzinfo=zone).astimezone(timezone.utc);end=(datetime.combine(business_date+timedelta(days=1),time.min,tzinfo=zone)).astimezone(timezone.utc)
    query=scope(FinanceLedgerEntry.query,FinanceLedgerEntry,user).filter(FinanceLedgerEntry.direction=='in',FinanceLedgerEntry.status.in_(['posted','reconciled']),FinanceLedgerEntry.occurred_at>=start,FinanceLedgerEntry.occurred_at<end)
    if branch_id:
        depts=select(BranchDepartment.department_id).where(BranchDepartment.organization_id==user.organization_id,BranchDepartment.branch_id==branch_id)
        tagged=select(BusinessRecordScope.entity_id).where(BusinessRecordScope.organization_id==user.organization_id,BusinessRecordScope.branch_id==branch_id,BusinessRecordScope.entity_type=='finance_ledger_entries')
        query=query.filter(or_(FinanceLedgerEntry.department_id.in_(depts),FinanceLedgerEntry.id.in_(tagged)))
    elif department_id:query=query.filter_by(department_id=department_id)
    rows=query.all();totals={method:Decimal(0) for method in METHODS};ids=[]
    invoice_ledgers={p.ledger_id for p in scope(BusinessPosting.query,BusinessPosting,user).filter_by(entity_type='business_sales_invoices').all()}
    for row in rows:
        if row.entry_type not in {'income','revenue'} and row.id not in invoice_ledgers:continue
        totals[channel(row.payment_method)]+=row.amount;ids.append(row.id)
    return totals,sorted(ids)


def close_counts(data,expected):
    counted={method:money(data.get('counted_'+method)) for method in METHODS}
    difference=sum(counted.values())-sum(expected.values())
    explanation=text_value(data,'explanation',required=bool(difference))
    return counted,difference,explanation


def create_close(app,user,data):
    dims=dimensions(user,data);when=day(data.get('business_date'))
    if when>instant().date():raise ValueError('A daily close cannot be in the future.')
    if user.role in OWNER and not dims['branch_id'] and BranchLocation.query.filter_by(organization_id=user.organization_id,is_active=True).count():raise ValueError('Choose the branch being reconciled.')
    expected,ids=takings(user,when,dims['branch_id'],dims['department_id']);counted,difference,explanation=close_counts(data,expected)
    row=DailyClose(id=str(uuid4()),**dims,scope_key=dims['branch_id'] or dims['department_id'] or 'business',business_date=when,
        expected_json={k:str(v) for k,v in expected.items()},counted_json={k:str(v) for k,v in counted.items()},ledger_ids=ids,
        expected_total=sum(expected.values()),counted_total=sum(counted.values()),variance=difference,explanation=explanation)
    db.session.add(row);db.session.flush();activity(app,user,row,'daily_close_created','Daily takings reconciliation prepared','daily_close')
    return row


def close_action(app,user,row,action,data):
    if action=='submit':
        if row.status!='draft':raise ValueError('Only a draft close can be submitted.')
        if user.id!=row.created_by_id and not can_operate(user,'finance_ops'):raise PermissionError('Only the preparer or Finance can submit this close.')
        expected,ids=takings(user,row.business_date,row.branch_id,row.department_id)
        if expected!={k:Decimal(v) for k,v in row.expected_json.items()} or ids!=row.ledger_ids:raise ValueError('Takings changed. Recount this draft before submitting.')
        row.status='submitted';row.submitted_at=instant()
        if individual(user) and user.role in OWNER:row.status='reconciled';row.reviewed_by_id=user.id;row.reviewed_at=instant();row.review_notes='Individual owner close'
    elif action=='recount':
        if row.status!='draft':raise ValueError('Reopen the close before recounting.')
        if user.id!=row.created_by_id and not can_operate(user,'finance_ops'):raise PermissionError('Only the preparer or Finance can recount.')
        expected,ids=takings(user,row.business_date,row.branch_id,row.department_id);counted,difference,explanation=close_counts(data,expected)
        row.expected_json={k:str(v) for k,v in expected.items()};row.counted_json={k:str(v) for k,v in counted.items()};row.ledger_ids=ids
        row.expected_total=sum(expected.values());row.counted_total=sum(counted.values());row.variance=difference;row.explanation=explanation
    elif action=='approve':
        require_operational(user,"finance_ops","daily reconciliation review")
        if row.status!='submitted':raise ValueError('Submit the close before approval.')
        if user.id==row.created_by_id and not (individual(user) and user.role in OWNER):raise PermissionError('Another authorized person must review this close.')
        expected,ids=takings(user,row.business_date,row.branch_id,row.department_id)
        if ids!=row.ledger_ids or expected!={k:Decimal(v) for k,v in row.expected_json.items()}:raise ValueError('Transactions changed after submission. Reopen and recount.')
        row.review_notes=text_value(data,'review_notes',True);row.status='reconciled';row.reviewed_by_id=user.id;row.reviewed_at=instant()
    elif action=='reopen':
        require_role(user,OWNER);row.review_notes=text_value(data,'review_notes',True);row.status='draft';row.reviewed_at=None;row.reviewed_by_id=None
    else:raise ValueError('Unsupported reconciliation action.')
    activity(app,user,row,'daily_close_'+action,'Daily close · '+action,'daily_close')
    return row
