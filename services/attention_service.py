"""Small first-page checks so unresolved records remain visible without opening other pages."""
from datetime import datetime, timezone
from models import (Attachment, CustodyAcknowledgment, FinanceLedgerEntry, FinanceVerification,
    FinancialRecord, ManagementTask, PurchaseFulfillment, PurchaseRequest)


def attention_additions(user):
    org=user.organization_id; today=datetime.now(timezone.utc).date(); output=[]
    def add(rank,title,detail,count):
        if count: output.append({"rank":rank,"priority":{3:"Urgent",2:"Attention Required",1:"Normal"}[rank],"title":title,"detail":detail,"metric":str(count),"route":"dashboard","section":"actions"})
    evidence={row.entity_id for row in Attachment.query.filter_by(organization_id=org).all()}
    reviewed={row.entity_id for row in FinanceVerification.query.filter_by(organization_id=org).all()}
    purchases=PurchaseFulfillment.query.filter(PurchaseFulfillment.organization_id==org,PurchaseFulfillment.confirmed_at.isnot(None)).all()
    fulfillment_ids={row.id for row in purchases}
    expenses=FinancialRecord.query.filter(FinancialRecord.organization_id==org,FinancialRecord.status=="posted",FinancialRecord.record_type.in_(["expense","expenditure","operating_cost","payroll","tax"])).all()
    missing=[row for row in expenses if row.id not in evidence and row.source_entity_id not in evidence]
    direct_unreviewed=[row for row in expenses if row.source_entity_id not in fulfillment_ids and row.id not in reviewed and row.source_entity_id not in reviewed]
    add(2,"Expenses missing supporting documents",f"{len(missing)} posted expense(s) need a receipt or supporting document.",len(missing))
    add(2,"Direct expenses awaiting evidence review",f"{len(direct_unreviewed)} expense posting(s) await a management review.",len(direct_unreviewed))
    unallocated=FinanceLedgerEntry.query.filter(FinanceLedgerEntry.organization_id==org,FinanceLedgerEntry.status.in_(["posted","reconciled"]),FinanceLedgerEntry.direction.in_(["in","out"]),FinanceLedgerEntry.account_id.is_(None)).count()
    add(2,"Cash postings need an account",f"{unallocated} recorded cash movement(s) have no bank/cash account assigned.",unallocated)
    received={row.entity_id for row in CustodyAcknowledgment.query.filter_by(organization_id=org,entity_type="request",action="received").all()}
    unacknowledged=[row for row in purchases if row.request_id not in received]
    add(2,"Named delivery acknowledgment pending",f"{len(unacknowledged)} acquisition(s) have no signed-in recipient acknowledgment.",len(unacknowledged))
    tasks=ManagementTask.query.filter(ManagementTask.organization_id==org,ManagementTask.status!="completed").all()
    due=[row for row in tasks if row.due_date and row.due_date<today and (not row.snoozed_until or row.snoozed_until<=today)]
    add(3,"Overdue management follow-ups",f"{len(due)} assigned action(s) are past their recorded due date.",len(due))
    return output
