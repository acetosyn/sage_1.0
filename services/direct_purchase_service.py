"""Record owner/finance purchases directly, with actual item costs and custody links."""
import json
from decimal import Decimal
from models import AssetItem, AssetMovement, DirectPurchaseLine, InventoryItem, StockMovement, RecordLink, User
from packages.database import db
from services.operations_service import next_asset_tag, quantity, money


def post_direct_items(user, ledger, form):
    mode = form.get("record_as", "finance")
    if mode not in {"stock", "asset"}: return []
    if ledger.status != "posted" or ledger.entry_type not in {"expense", "expenditure"}: raise ValueError("Only posted purchase expenses can create stock or assets.")
    if not ledger.counterparty: raise ValueError("Record the supplier for this purchase.")
    raw = form.get("purchase_lines")
    lines = json.loads(raw) if isinstance(raw,str) and raw else raw if isinstance(raw,list) else [{"name":form.get("purchase_item_name"),"quantity":form.get("purchase_quantity"),"unit_cost":form.get("purchase_unit_cost"),"unit":form.get("purchase_unit")}]
    if not isinstance(lines,list) or not lines or len(lines)>100: raise ValueError("Enter between one and 100 actual purchase lines.")
    parsed = []
    for item in lines:
        if not isinstance(item,dict): raise ValueError("Enter valid purchase lines.")
        if item.get("quantity") in (None, "") or item.get("unit_cost") in (None, ""): raise ValueError("Enter the actual quantity and unit cost; missing costs are not assumed to be zero.")
        name = str(item.get("name") or "").strip()[:180]; qty = quantity(item.get("quantity")); cost = money(item.get("unit_cost"))
        if not name or qty <= 0 or not qty.is_finite(): raise ValueError("Enter an item name and positive actual quantity.")
        parsed.append((name,qty,cost,str(item.get("unit") or "unit")[:60]))
    if sum(qty*cost for _,qty,cost,_ in parsed) > Decimal(ledger.amount): raise ValueError("Item costs exceed the total purchase expense. Check the actual amounts.")
    custodian = User.query.filter_by(id=form.get("purchase_custodian_id"),organization_id=user.organization_id,status="active").first() if form.get("purchase_custodian_id") else None
    if form.get("purchase_custodian_id") and not custodian: raise ValueError("Choose an active custodian from this business.")
    location = str(form.get("purchase_location") or "").strip()[:160] or None
    output = []
    for name,qty,cost,unit in parsed:
        line = DirectPurchaseLine(organization_id=user.organization_id,ledger_id=ledger.id,created_by_id=user.id,item_name=name,quantity=qty,unit=unit,unit_cost=cost,record_as=mode)
        if mode == "stock":
            item = InventoryItem.query.filter_by(organization_id=user.organization_id,department_id=ledger.department_id,name=name,unit=unit).with_for_update().first()
            if not item:
                item = InventoryItem(organization_id=user.organization_id,department_id=ledger.department_id,name=name,unit=unit,quantity=0,unit_value=cost,location=location,added_by_id=user.id);db.session.add(item);db.session.flush()
            old_qty = Decimal(item.quantity or 0); new_qty = old_qty+qty
            item.unit_value = ((old_qty*Decimal(item.unit_value or 0)+qty*cost)/new_qty).quantize(Decimal("0.01"));item.quantity=new_qty
            line.inventory_id = item.id
            movement = StockMovement(organization_id=user.organization_id,inventory_item_id=item.id,user_id=user.id,movement_type="stock_in",quantity=qty,source=ledger.counterparty,destination=item.location,reference=ledger.reference,reason="Direct purchase recorded in finance")
            db.session.add(movement);db.session.flush()
            target_type,target_id = "inventory_item",item.id
            db.session.add(RecordLink(organization_id=user.organization_id,source_type="finance_ledger",source_id=ledger.id,target_type="stock_movement",target_id=movement.id,relation="purchase_receipt",created_by_id=user.id))
        else:
            item = AssetItem(organization_id=user.organization_id,department_id=ledger.department_id,created_by_id=user.id,custodian_user_id=custodian.id if custodian else None,name=name,asset_tag=next_asset_tag(user.organization_id),quantity=qty,unit_value=cost,location=location,condition="good",status="assigned" if custodian else "active",acquired_at=ledger.occurred_at.date())
            db.session.add(item);db.session.flush();line.asset_id=item.id
            db.session.add(AssetMovement(organization_id=user.organization_id,asset_id=item.id,user_id=user.id,movement_type="register",quantity=qty,destination_department_id=ledger.department_id,custodian_user_id=item.custodian_user_id,destination_location=location,reference=ledger.reference,reason="Direct purchase recorded in finance"))
            target_type,target_id = "asset",item.id
        db.session.add(line)
        db.session.add(RecordLink(organization_id=user.organization_id,source_type="finance_ledger",source_id=ledger.id,target_type=target_type,target_id=target_id,relation="purchase_entry",created_by_id=user.id))
        output.append(line)
    return output
