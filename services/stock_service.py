"""Advanced stock extends InventoryItem; batch quantities never replace its live balance."""
from uuid import uuid4
from datetime import date
from sqlalchemy import func
from models import (InventoryItem, StockMovement, StockProfile, StockBatch, StockAllocation, StockCount, PurchaseFulfillment)
from packages.database import db
from services.business_core import *
from services.operational_policy import require_operational

STOCK_ROLES=FINANCE|{'procurement'}

def stock_permission(user):
    from services.access_control import can_access_page
    if user.role not in STOCK_ROLES and not can_access_page(user,'inventory'):raise PermissionError('Inventory access is required.')


def stock_profile(user,item):
    profile=StockProfile.query.filter_by(organization_id=user.organization_id,inventory_id=item.id).with_for_update().first()
    if not profile:
        profile=StockProfile(id=str(uuid4()),**dimensions(user,dict(department_id=item.department_id or '')),inventory_id=item.id)
        db.session.add(profile);db.session.flush()
    profile.updated_at=instant()
    return profile


def take_stock(user,item,quantity,source_type,source_id,allow_expired=False,batch_id=None):
    """FEFO allocation plus optimistic profile lock also protects SQLite stock updates."""
    profile=stock_profile(user,item);quantity=money(quantity,True,'0.001')
    batches=StockBatch.query.filter_by(organization_id=user.organization_id,inventory_id=item.id).order_by(StockBatch.expiry_date.asc().nullslast(),StockBatch.received_at).with_for_update().all()
    tracked=sum((b.quantity for b in batches),Decimal(0));unbatched=item.quantity-tracked
    if unbatched<0:raise ValueError('Batch balances exceed stock. Review the stock history before continuing.')
    available=[b for b in batches if (not batch_id or b.id==batch_id) and (allow_expired or not b.expiry_date or b.expiry_date>=date.today())]
    available_quantity=sum((b.quantity for b in available),Decimal(0))+(unbatched if not batch_id else 0)
    if quantity>available_quantity:raise ValueError('Insufficient usable stock. Expired batches cannot be sold or issued.')
    remaining=quantity;cost=Decimal(0)
    for batch in available:
        used=min(remaining,batch.quantity)
        if used:
            batch.quantity-=used;remaining-=used;cost+=used*batch.cost_price
            db.session.add(StockAllocation(**inherited(user,profile),inventory_id=item.id,batch_id=batch.id,source_type=source_type,source_id=source_id,quantity=used))
        if not remaining:break
    if remaining:
        cost+=remaining*item.unit_value
        db.session.add(StockAllocation(**inherited(user,profile),inventory_id=item.id,source_type=source_type,source_id=source_id,quantity=remaining))
    item.quantity-=quantity
    return money(cost/quantity)


def restore_stock(user,item,quantity,source_type,source_id):
    profile=stock_profile(user,item);remaining=money(quantity,places='0.001')
    allocations=StockAllocation.query.filter_by(organization_id=user.organization_id,inventory_id=item.id,source_type=source_type,source_id=source_id).with_for_update().all()
    available=sum((a.quantity-a.returned for a in allocations),Decimal(0))
    if remaining>available:raise ValueError('The return exceeds stock issued from this source.')
    for allocation in allocations:
        restored=min(remaining,allocation.quantity-allocation.returned)
        if allocation.batch_id:
            batch=tenant_row(StockBatch,user,allocation.batch_id);batch.quantity+=restored
        allocation.returned+=restored;remaining-=restored
        if not remaining:break
    item.quantity+=money(quantity,places='0.001')


def create_stock(app,user,data):
    stock_permission(user)
    dims=dimensions(user,data)
    item=InventoryItem(id=str(uuid4()),organization_id=user.organization_id,department_id=dims['department_id'],added_by_id=user.id,
        name=text_value(data,'name',True,180),sku=text_value(data,'sku',limit=80),category=text_value(data,'category',limit=120),
        unit=text_value(data,'unit',limit=60) or 'unit',quantity=money(data.get('quantity'),places='0.001'),unit_value=money(data.get('cost_price')),
        reorder_level=money(data.get('reorder_level'),places='0.001'),location=text_value(data,'location',limit=160))
    db.session.add(item);db.session.flush()
    profile=StockProfile(id=str(uuid4()),**dims,inventory_id=item.id,selling_price=money(data.get('selling_price')))
    db.session.add(profile);tag_branch(user,profile,item)
    db.session.add(StockMovement(organization_id=user.organization_id,inventory_item_id=item.id,user_id=user.id,movement_type='stock_in',quantity=item.quantity,reason='Opening stock'))
    activity(app,user,profile,'stock_created','Stock item opened','inventory_item')
    return profile


def stock_action(app,user,item,action,data):
    stock_permission(user)
    profile=stock_profile(user,item)
    if action=='settings':
        profile.selling_price=money(data.get('selling_price'));item.reorder_level=money(data.get('reorder_level'),places='0.001')
    elif action in {'receive','register_batch'}:
        quantity=money(data.get('quantity'),True,'0.001');cost=money(data.get('cost_price'))
        batch=StockBatch(id=str(uuid4()),**inherited(user,profile),inventory_id=item.id,number=text_value(data,'number',True,100),
            quantity=quantity,cost_price=cost,expiry_date=day(data.get('expiry_date'),False),received_at=instant(data.get('occurred_at')))
        if batch.received_at>instant():raise ValueError('Stock cannot be received in the future.')
        if data.get('fulfillment_id'):
            fulfillment=get_row(PurchaseFulfillment,user,data['fulfillment_id'],broad=STOCK_ROLES)
            if fulfillment.is_draft:raise ValueError('Choose a finalized acquisition.')
            if action!='register_batch':raise ValueError('Acquisition stock is already received. Register its batch without adding it again.')
            batch.fulfillment_id=fulfillment.id
        if action=='register_batch':
            tracked=sum((b.quantity for b in StockBatch.query.filter_by(organization_id=user.organization_id,inventory_id=item.id)),Decimal(0))
            if quantity>item.quantity-tracked:raise ValueError('Batch registration exceeds existing unbatched stock.')
        else:
            old=item.quantity;item.quantity+=quantity
            item.unit_value=money((old*item.unit_value+quantity*cost)/item.quantity)
            db.session.add(StockMovement(organization_id=user.organization_id,inventory_item_id=item.id,user_id=user.id,movement_type='stock_in',quantity=quantity,reason=text_value(data,'reason',True,500)))
        db.session.add(batch)
    elif action in {'issue','damage','expiry','adjustment_out'}:
        quantity=money(data.get('quantity'),True,'0.001');reason=text_value(data,'reason',True,500)
        if action=='adjustment_out':require_operational(user,'stock','stock adjustment')
        batch_id=data.get('batch_id') or None
        if action=='expiry':
            batch=tenant_row(StockBatch,user,batch_id)
            if batch.inventory_id!=item.id or not batch.expiry_date or batch.expiry_date>=date.today():raise ValueError('Choose an expired batch for this item.')
        reference=str(uuid4());take_stock(user,item,quantity,action,reference,allow_expired=action in {'damage','expiry','adjustment_out'},batch_id=batch_id)
        db.session.add(StockMovement(organization_id=user.organization_id,inventory_item_id=item.id,user_id=user.id,movement_type=action,quantity=quantity,reason=reason,reference=reference))
    elif action in {'return','adjustment_in'}:
        require_operational(user,'stock','stock return / adjustment')
        quantity=money(data.get('quantity'),True,'0.001');item.quantity+=quantity
        db.session.add(StockMovement(organization_id=user.organization_id,inventory_item_id=item.id,user_id=user.id,movement_type=action,quantity=quantity,reason=text_value(data,'reason',True,500)))
    elif action=='transfer':
        target=get_row(InventoryItem,user,data.get('target_id'),True,broad=STOCK_ROLES)
        if target.id==item.id or target.unit!=item.unit or target.name.casefold()!=item.name.casefold():raise ValueError('Choose a different balance for the same stock item and unit.')
        destination=stock_profile(user,target);quantity=money(data.get('quantity'),True,'0.001');reference=str(uuid4())
        reason=text_value(data,'reason',True,500)
        cost=take_stock(user,item,quantity,'transfer',reference)
        old=target.quantity;target.quantity+=quantity;target.unit_value=money((old*target.unit_value+quantity*cost)/target.quantity)
        db.session.flush()
        for allocation in StockAllocation.query.filter_by(organization_id=user.organization_id,source_type='transfer',source_id=reference):
            if allocation.batch_id:
                source=tenant_row(StockBatch,user,allocation.batch_id)
                batch=StockBatch.query.filter_by(organization_id=user.organization_id,inventory_id=target.id,number=source.number).first()
                if batch and (batch.expiry_date!=source.expiry_date or batch.cost_price!=source.cost_price):raise ValueError('Destination batch has different expiry or cost details.')
                if batch:batch.quantity+=allocation.quantity
                else:db.session.add(StockBatch(**inherited(user,destination),inventory_id=target.id,number=source.number,quantity=allocation.quantity,cost_price=source.cost_price,expiry_date=source.expiry_date,received_at=source.received_at))
        for record,kind in [(item,'transfer'),(target,'stock_in')]:
            db.session.add(StockMovement(organization_id=user.organization_id,inventory_item_id=record.id,user_id=user.id,movement_type=kind,quantity=quantity,source=item.location,destination=target.location,reason=reason,reference=reference))
    elif action=='count':
        counted=money(data.get('counted'),places='0.001')
        db.session.add(StockCount(**inherited(user,profile),inventory_id=item.id,expected=item.quantity,counted=counted,variance=counted-item.quantity,reason=text_value(data,'reason',True)))
    elif action=='approve_count':
        require_role(user,OWNER)
        count_row=get_row(StockCount,user,data.get('count_id'),True)
        if count_row.inventory_id!=item.id or count_row.approved_at:raise ValueError('Choose a pending count for this item.')
        if count_row.expected!=item.quantity:raise ValueError('Stock moved after this count. Perform a fresh count.')
        if count_row.variance<0:take_stock(user,item,-count_row.variance,'physical_count',count_row.id,True)
        else:item.quantity+=count_row.variance
        count_row.approved_by_id=user.id;count_row.approved_at=instant()
        db.session.add(StockMovement(organization_id=user.organization_id,inventory_item_id=item.id,user_id=user.id,movement_type='physical_count',quantity=abs(count_row.variance),reason=count_row.reason,reference=count_row.id))
    else:raise ValueError('Unsupported stock action.')
    activity(app,user,profile,'stock_'+action,'Stock · '+action.replace('_',' '),'inventory_item')
    return profile
