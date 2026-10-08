"""Connected, tenant-scoped provenance for transactions, stock and assets."""
from collections import deque
from datetime import datetime
from sqlalchemy import or_
from core.datetime_utils import as_utc
from models import (ActivityEvent, AssetItem, AssetMovement, Attachment, AuditRevision,
    CustodyAcknowledgment, DepartmentOperation, FinanceLedgerEntry, FinancePayable,
    FinanceReceivable, FinanceVerification, FinancialRecord, InventoryItem, PurchaseFulfillment, DirectPurchaseLine,
    PurchaseRequest, RecordLink, RequestFunding, StockMovement, User, BudgetAllocation,
    Supplier, FinanceAccount, FinanceReconciliation, BudgetReservation, ReconciliationMatch)
from packages.database import db

ENTITIES = {"request": PurchaseRequest, "fulfillment": PurchaseFulfillment,
    "financial_record": FinancialRecord, "finance_ledger": FinanceLedgerEntry,
    "inventory_item": InventoryItem, "asset": AssetItem, "stock_movement": StockMovement,
    "asset_movement": AssetMovement, "department_operation": DepartmentOperation,
    "receivable": FinanceReceivable, "payable": FinancePayable, "user": User,
    "budget": BudgetAllocation, "supplier": Supplier, "account": FinanceAccount,
    "reconciliation": FinanceReconciliation, "request_funding": RequestFunding}


def permitted(user, row):
    if row.organization_id != user.organization_id: return False
    if user.role in {"owner", "admin", "finance"}: return True
    if isinstance(row, (FinancialRecord, FinanceLedgerEntry, FinanceReceivable, FinancePayable)):
        if row.created_by_id == user.id: return True
        source_kind, source_id = getattr(row, "source_entity_type", None), getattr(row, "source_entity_id", None)
        if source_kind == "request_or_fulfillment":
            source = PurchaseFulfillment.query.filter_by(id=source_id, organization_id=user.organization_id).first() or PurchaseRequest.query.filter_by(id=source_id, organization_id=user.organization_id).first()
            return bool(source and permitted(user, source))
        if source_kind in {"request", "department_operation"}:
            source = ENTITIES[source_kind].query.filter_by(id=source_id, organization_id=user.organization_id).first()
            return bool(source and permitted(user, source))
        if source_kind == "finance_ledger":
            source = FinanceLedgerEntry.query.filter_by(id=source_id, organization_id=user.organization_id).first()
            return bool(source and permitted(user, source))
        return False
    if user.role == "procurement" and isinstance(row, (PurchaseRequest, PurchaseFulfillment, InventoryItem, AssetItem, StockMovement, AssetMovement)): return True
    if getattr(row, "department_id", None) and row.department_id == user.department_id: return True
    if isinstance(row, StockMovement):
        assigned = RecordLink.query.filter_by(organization_id=user.organization_id, source_type="stock_movement", source_id=row.id, target_type="user", target_id=user.id, relation="issued_to").first()
        return bool(assigned) or permitted(user, row.item)
    if isinstance(row, AssetMovement): return permitted(user, row.asset)
    return any(getattr(row, field, None) == user.id for field in ("requester_id", "created_by_id", "user_id", "added_by_id", "custodian_user_id")) or (isinstance(row, User) and row.id == user.id)


def get_record(user, entity_type, entity_id):
    model = ENTITIES.get(entity_type)
    if not model: raise ValueError("Unsupported record type.")
    row = model.query.filter_by(id=entity_id, organization_id=user.organization_id).first()
    if not row or not permitted(user, row): raise LookupError("Record not found in your access scope.")
    return row


def describe(entity_type, row):
    actor = next((getattr(row, field, None) for field in ("created_by", "requester", "recorded_by", "user", "added_by") if getattr(row, field, None)), None)
    when = getattr(row, "occurred_at", None) or getattr(row, "created_at", None)
    if isinstance(when, str): when = datetime.fromisoformat(when)
    if actor is None and getattr(row, "archived", False):
        actor_id = getattr(row, "created_by_id", None) or getattr(row, "requester_id", None) or getattr(row, "user_id", None)
        actor = User.query.filter_by(id=actor_id, organization_id=row.organization_id).first() if actor_id else None
    amount = next((getattr(row, field, None) for field in ("amount", "actual_total", "amount_sent", "estimated_total", "total_amount", "total_value", "total_budget", "opening_balance") if getattr(row, field, None) is not None), None)
    return {"type": entity_type, "id": row.id, "reference": getattr(row, "reference", None) or getattr(row, "asset_tag", None) or getattr(row, "sku", None),
        "title": next((getattr(row, field, None) for field in ("title", "description", "name", "display_name") if getattr(row, field, None)), entity_type.replace("_", " ").title()),
        "amount": str(amount) if amount is not None else None, "balance": getattr(row, "balance", None), "account_id": getattr(row, "account_id", None),
        "party": getattr(row,"customer_name",None) or getattr(row,"vendor_name",None) or getattr(row,"counterparty",None),
        "currency": getattr(row, "currency", None), "status": getattr(row, "status", None),
        "date": as_utc(when).isoformat() if when else None, "actor": actor.display_name if actor else None,
        "department": row.department.name if getattr(row, "department", None) else None,
        "supplier": getattr(row, "supplier_name", None) or getattr(row, "counterparty", None),
        "location": getattr(row, "location", None), "custodian": row.custodian.display_name if getattr(row, "custodian", None) else None, "archived": bool(getattr(row, "archived", False))}


def neighbours(user, kind, row):
    org = user.organization_id
    linked = []
    if kind == "request":
        if row.fulfillment: linked.append(("fulfillment", row.fulfillment))
        linked += [("asset", item) for item in AssetItem.query.filter_by(organization_id=org, source_request_id=row.id).all()]
        linked += [("stock_movement", item) for item in StockMovement.query.filter_by(organization_id=org, reference=row.reference).all()]
        funding = row.funding
        if funding: linked += [("finance_ledger", item) for item in FinanceLedgerEntry.query.filter_by(organization_id=org, source_entity_type="request_funding", source_entity_id=funding.id).all()]
    elif kind == "request_funding": linked.append(("request", row.request))
    elif kind == "budget":
        linked += [("finance_ledger", item) for item in FinanceLedgerEntry.query.filter_by(organization_id=org, budget_id=row.id).all()]
        reservations = BudgetReservation.query.filter_by(organization_id=org, budget_id=row.id).all()
        linked += [("request", item) for item in PurchaseRequest.query.filter(PurchaseRequest.organization_id == org, PurchaseRequest.id.in_([entry.request_id for entry in reservations])).all()]
    elif kind == "reconciliation":
        matches = ReconciliationMatch.query.filter_by(organization_id=org, reconciliation_id=row.id).all()
        linked += [("finance_ledger", item) for item in FinanceLedgerEntry.query.filter(FinanceLedgerEntry.organization_id == org, FinanceLedgerEntry.id.in_([entry.ledger_id for entry in matches])).all()]
    elif kind == "fulfillment":
        linked.append(("request", row.request))
        linked += [("financial_record", item) for item in FinancialRecord.query.filter_by(organization_id=org, source_entity_id=row.id).all()]
    elif kind == "inventory_item":
        linked += [("stock_movement", item) for item in StockMovement.query.filter_by(organization_id=org, inventory_item_id=row.id).all()]
    elif kind == "asset":
        if row.source_request: linked.append(("request", row.source_request))
        linked += [("asset_movement", item) for item in AssetMovement.query.filter_by(organization_id=org, asset_id=row.id).all()]
    elif kind == "stock_movement":
        linked.append(("inventory_item", row.item))
        if row.reference:
            source = PurchaseRequest.query.filter_by(organization_id=org, reference=row.reference).first()
            if source: linked.append(("request", source))
    elif kind == "asset_movement": linked.append(("asset", row.asset))
    elif kind in {"financial_record", "finance_ledger"}:
        source_kind, source_id = row.source_entity_type, row.source_entity_id
        if source_kind == "request_or_fulfillment" and source_id:
            source = PurchaseFulfillment.query.filter_by(id=source_id, organization_id=org).first()
            if source: linked.append(("fulfillment", source))
            else:
                source = PurchaseRequest.query.filter_by(id=source_id, organization_id=org).first()
                if source: linked.append(("request", source))
        elif source_kind in ENTITIES and source_id:
            source = ENTITIES[source_kind].query.filter_by(id=source_id, organization_id=org).first()
            if source: linked.append((source_kind, source))
        elif source_kind == "request_funding" and source_id:
            funding = RequestFunding.query.filter_by(id=source_id, organization_id=org).first()
            if funding: linked.append(("request", funding.request))
    if kind in {"receivable", "payable", "department_operation", "finance_ledger"}:
        linked += [("finance_ledger", item) for item in FinanceLedgerEntry.query.filter_by(organization_id=org, source_entity_type=kind, source_entity_id=row.id).all()]
        linked += [("financial_record", item) for item in FinancialRecord.query.filter_by(organization_id=org, source_entity_type=kind, source_entity_id=row.id).all()]
    links = RecordLink.query.filter(RecordLink.organization_id == org, or_((RecordLink.source_type == kind) & (RecordLink.source_id == row.id), (RecordLink.target_type == kind) & (RecordLink.target_id == row.id))).all()
    for edge in links:
        target_kind, target_id = (edge.target_type, edge.target_id) if edge.source_type == kind and edge.source_id == row.id else (edge.source_type, edge.source_id)
        if target_kind in ENTITIES:
            target = ENTITIES[target_kind].query.filter_by(id=target_id, organization_id=org).first()
            if target: linked.append((target_kind, target))
    return [(target_kind, target) for target_kind, target in linked if permitted(user, target)]


def record_trace(user, kind, entity_id, history_offset=0):
    try: initial = get_record(user, kind, entity_id)
    except LookupError:
        if user.role not in {"owner", "admin", "finance"} or kind not in ENTITIES: raise
        revision = AuditRevision.query.filter_by(organization_id=user.organization_id, entity_type=ENTITIES[kind].__name__, entity_id=entity_id, action="record_deleted").order_by(AuditRevision.created_at.desc()).first()
        if not revision: raise
        from types import SimpleNamespace
        saved = dict(revision.before_json or {})
        saved.update(id=entity_id, organization_id=user.organization_id, archived=True, status="archived")
        initial = SimpleNamespace(**saved)
    queue, seen, records = deque([(kind, initial)]), set(), []
    while queue and len(seen) < 250:
        node_kind, row = queue.popleft()
        if (node_kind, row.id) in seen: continue
        seen.add((node_kind, row.id)); records.append((node_kind, row))
        if not getattr(row, "archived", False): queue.extend(neighbours(user, node_kind, row))
    ids = {row.id for record_kind, row in records if record_kind != "user" or user.role in {"owner", "admin", "finance"}}
    org = user.organization_id
    evidence = Attachment.query.filter(Attachment.organization_id == org, Attachment.entity_id.in_(ids)).order_by(Attachment.created_at.asc()).all()
    events = ActivityEvent.query.filter(ActivityEvent.organization_id == org, ActivityEvent.entity_id.in_(ids)).all()
    revisions = AuditRevision.query.filter(AuditRevision.organization_id == org, AuditRevision.entity_id.in_(ids)).all()
    acknowledgments = CustodyAcknowledgment.query.filter(CustodyAcknowledgment.organization_id == org, CustodyAcknowledgment.entity_id.in_(ids)).all()
    verifications = FinanceVerification.query.filter(FinanceVerification.organization_id == org, FinanceVerification.entity_id.in_(ids)).all()
    history = [{"id": item.id, "action": item.action, "title": item.title, "description": item.description, "actor": item.actor.display_name if item.actor else "System / former user", "date": as_utc(item.created_at).isoformat()} for item in events]
    history += [{"id": item.id, "action": item.action, "title": item.change_summary or item.action, "actor": item.actor.display_name if item.actor else "System / former user", "date": as_utc(item.created_at).isoformat(), "before": item.before_json, "after": item.after_json} for item in revisions]
    history += [{"id": item.id, "action": item.action, "title": "Custody " + item.action, "description": item.notes, "actor": item.user.display_name, "date": as_utc(item.created_at).isoformat()} for item in acknowledgments]
    history += [{"id": item.id, "action": "expense_verified", "title": "Expense evidence reviewed", "description": item.notes, "actor": item.verified_by.display_name, "date": as_utc(item.created_at).isoformat()} for item in verifications]
    history.sort(key=lambda item: (item["date"], item["id"]), reverse=True)
    request_row = next((row for node_kind, row in records if node_kind == "request" and not getattr(row, "archived", False)), None)
    stages = []
    if request_row:
        fulfillment, funding = request_row.fulfillment, request_row.funding
        receipts = [item for item in evidence if item.kind == "receipts" and fulfillment and item.entity_id == fulfillment.id]
        received = [item for item in acknowledgments if item.entity_type == "request" and item.entity_id == request_row.id and item.action == "received"]
        delivery = max((line.delivered_at for line in fulfillment.lines if line.delivered_at), key=as_utc, default=None) if fulfillment else None
        payments = [row for node_kind, row in records if node_kind == "finance_ledger" and row.direction == "out" and row.status in {"posted", "reconciled"}]
        for label, at, actor in [
            ("Request", request_row.submitted_at or request_row.created_at, request_row.requester),
            ("Approval", request_row.approved_at, request_row.approved_by),
            ("Purchase", fulfillment.confirmed_at if fulfillment else None, fulfillment.recorded_by if fulfillment else None),
            ("Receipt", receipts[0].created_at if receipts else None, receipts[0].uploaded_by if receipts else None),
            ("Delivery", received[0].created_at if received else delivery, received[0].user if received else None),
            ("Verification", fulfillment.verified_at if fulfillment else None, fulfillment.verified_by if fulfillment else None),
            ("Payment", payments[0].occurred_at if payments else funding.funded_at if funding and funding.amount_sent else None, payments[0].created_by if payments else funding.recorded_by if funding and funding.amount_sent else None)
        ]: stages.append({"label": label, "done": bool(at), "date": as_utc(at).isoformat() if at else None, "actor": actor.display_name if actor else None})
    direct_lines = DirectPurchaseLine.query.filter(DirectPurchaseLine.organization_id == org, DirectPurchaseLine.ledger_id.in_(ids)).all()
    return {"record": describe(kind, initial), "records": [describe(node_kind, row) for node_kind, row in records],
        "stages": stages, "evidence": [{"id": item.id, "name": item.original_name, "kind": item.kind, "sha256": item.sha256, "url": "/evidence/" + item.id, "uploaded_by": item.uploaded_by.display_name if item.uploaded_by else None} for item in evidence],
        "history": history[history_offset:history_offset + 100], "history_total": len(history), "history_offset": history_offset,
        "next_history_offset": history_offset + 100 if history_offset + 100 < len(history) else None,
        "purchase_lines": [{"item":line.item_name,"quantity":float(line.quantity),"unit":line.unit,"unit_cost":float(line.unit_cost),"ledger_id":line.ledger_id} for line in direct_lines],
        "linked_records_truncated": bool(queue), "verified": bool(verifications), "acknowledgments": [{"action": item.action, "actor": item.user.display_name, "notes": item.notes} for item in acknowledgments]}
