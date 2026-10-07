# SERVICE: SAGE Department Operations + Staff Reporting
# Provides role/department-specific operational actions, real action logging, auto-generated daily/weekly reports and owner acknowledgement.

from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy import or_
from packages.database import db
from models import ActivityEvent, AssetMovement, Department, DepartmentOperation, PurchaseRequest, StaffReport, StockMovement, InventoryItem
from services.notification_service import notify_user, record_activity

# ==========================================================
# OPERATION PROFILES
# Each profile defines practical work actions without hard-coding a tenant. Unknown/custom departments safely fall back to DEFAULT_OPERATIONS.
# ==========================================================

DEFAULT_OPERATIONS = [
    {"type":"activity_completed","label":"Record Completed Activity","icon":"check","detail":"Log a completed departmental task or service."},
    {"type":"item_used","label":"Record Item / Material Used","icon":"inventory","detail":"Record materials, consumables or supplies used during work."},
    {"type":"item_moved","label":"Record Item Movement","icon":"assets","detail":"Log an item or equipment movement not already captured by stock/assets."},
    {"type":"document_logged","label":"Record Document / Evidence","icon":"document","detail":"Log an operational document, reference or accountable record."},
    {"type":"incident","label":"Record Incident / Exception","icon":"audit","detail":"Capture an exception, issue, loss, delay or operational incident."},
]

OPERATION_PROFILES = [
    ({"procurement","purchasing","buyer"}, [
        {"type":"rfq_issued","label":"RFQ / Sourcing Activity","icon":"cart","detail":"Record request-for-quotation, sourcing or vendor-contact activity."},
        {"type":"quotation_received","label":"Quotation Received","icon":"document","detail":"Record quotation receipt, price, validity or comparison note."},
        {"type":"supplier_evaluation","label":"Supplier Evaluation","icon":"users","detail":"Record vendor assessment, performance or compliance review."},
        {"type":"purchase_order","label":"Purchase Order / Commitment","icon":"requests","detail":"Record PO, supplier commitment or approved procurement step."},
        {"type":"delivery_followup","label":"Delivery Follow-up","icon":"clock","detail":"Record delivery status, delay, discrepancy or supplier follow-up."},
        {"type":"price_variance","label":"Price / Savings Note","icon":"analytics","detail":"Record purchase-price variance, negotiated saving or exception."},
    ]),
    ({"security","loss prevention","cctv","guard"}, [
        {"type":"security_incident","label":"Security Incident","icon":"shield","detail":"Record security incident, loss, breach or response."},
        {"type":"visitor_exception","label":"Visitor / Access Exception","icon":"users","detail":"Record unusual access, gate-pass or visitor activity."},
        {"type":"security_asset_issue","label":"Security Equipment Issue","icon":"assets","detail":"Record radio, key, access device or security equipment issue/return."},
        {"type":"cctv_event","label":"CCTV / Surveillance Event","icon":"eye","detail":"Record monitored incident, footage reference or equipment issue."},
        {"type":"loss_prevention","label":"Loss Prevention Action","icon":"audit","detail":"Record prevention, recovery or suspected loss/fraud action."},
    ]),
    ({"kitchen","culinary","food","catering"}, [
        {"type":"production_batch","label":"Food / Production Batch","icon":"food","detail":"Record production, preparation batch or kitchen output."},
        {"type":"ingredient_usage","label":"Ingredient / Raw Material Used","icon":"inventory","detail":"Record ingredients or food stock consumed in production."},
        {"type":"food_wastage","label":"Waste / Spoilage","icon":"audit","detail":"Record spoilage, waste, rejected food or variance."},
        {"type":"kitchen_stock_check","label":"Kitchen Stock Check","icon":"check","detail":"Record count, reorder need or storage observation."},
        {"type":"equipment_incident","label":"Kitchen Equipment Incident","icon":"tool","detail":"Record breakdown, repair requirement or downtime."},
    ]),
    ({"housekeeping","laundry"}, [
        {"type":"supply_usage","label":"Cleaning / Guest Supply Usage","icon":"cleaning","detail":"Record chemicals, toiletries or housekeeping consumables used."},
        {"type":"linen_issue","label":"Linen Issue / Return","icon":"inventory","detail":"Record linen, towel, uniform or laundry movement."},
        {"type":"damage_loss","label":"Damage / Missing Item","icon":"audit","detail":"Record damaged, missing or replaced housekeeping item."},
        {"type":"room_consumption","label":"Room / Area Consumption","icon":"building","detail":"Record accountable supplies consumed by room, area or service."},
        {"type":"laundry_activity","label":"Laundry Activity","icon":"cleaning","detail":"Record laundry volume, chemical usage or linen processing."},
    ]),
    ({"production","factory","manufacturing"}, [
        {"type":"production_output","label":"Production Output","icon":"settings","detail":"Record batch, line or shift output."},
        {"type":"raw_material_usage","label":"Raw Material Usage","icon":"inventory","detail":"Record materials consumed by production."},
        {"type":"scrap_waste","label":"Scrap / Waste / Rework","icon":"audit","detail":"Record production waste, scrap or rework."},
        {"type":"machine_downtime","label":"Machine Downtime","icon":"clock","detail":"Record line/machine downtime and cause."},
        {"type":"shift_consumption","label":"Shift Cost / Consumption","icon":"finance","detail":"Record accountable shift resources or cost."},
    ]),
    ({"quality","quality control","quality assurance","qa","qc"}, [
        {"type":"quality_inspection","label":"Inspection / Test","icon":"check","detail":"Record quality inspection, sample test or result."},
        {"type":"rejection","label":"Reject / Nonconformance","icon":"audit","detail":"Record rejected item, batch, supplier or process nonconformance."},
        {"type":"calibration","label":"Calibration / Verification","icon":"tool","detail":"Record calibration, reference standard or equipment verification."},
        {"type":"batch_release","label":"Batch Release / Hold","icon":"document","detail":"Record release, hold or quality disposition."},
        {"type":"supplier_quality","label":"Supplier Quality Event","icon":"cart","detail":"Record supplier defect, return or quality review."},
    ]),
    ({"ict","technology","software","cyber","infrastructure"}, [
        {"type":"device_assignment","label":"Assign / Recover Device","icon":"device","detail":"Record assignment, recovery or custody of a technology device."},
        {"type":"repair_completed","label":"Device Repair / Replacement","icon":"tool","detail":"Record repair, replacement, diagnosis or parts used."},
        {"type":"subscription_renewal","label":"Software / Subscription Renewal","icon":"cloud","detail":"Track licence, domain, hosting or subscription renewal activity."},
        {"type":"network_change","label":"Network / Infrastructure Change","icon":"network","detail":"Log router, switch, cabling, server or infrastructure changes."},
        {"type":"downtime_incident","label":"Downtime / IT Incident","icon":"audit","detail":"Record an outage, fault, downtime duration and resolution."},
        {"type":"technology_stock_use","label":"IT Consumable / Spare Used","icon":"cable","detail":"Record cable, toner, SSD, RAM, adapter or other technology stock usage."},
    ]),
    ({"store","inventory","warehouse"}, [
        {"type":"stock_receipt","label":"Receive Stock","icon":"inventory","detail":"Record goods physically received into store custody."},
        {"type":"stock_issue","label":"Issue Stock","icon":"box","detail":"Record items issued to a person, team or department."},
        {"type":"stock_count","label":"Stock Count / Cycle Count","icon":"check","detail":"Record a physical count and accountability note."},
        {"type":"stock_variance","label":"Stock Variance","icon":"audit","detail":"Record shortage, surplus, damage or unexplained variance."},
        {"type":"reorder_review","label":"Reorder Review","icon":"requests","detail":"Record replenishment review, reorder action or stockout risk."},
        {"type":"store_housekeeping","label":"Store / Bin Reorganization","icon":"inventory","detail":"Record shelf, bin, location or storage-control changes."},
    ]),
    ({"human","hr","people"}, [
        {"type":"payroll_input","label":"Payroll Input / Staff Cost","icon":"finance","detail":"Record an approved payroll input, allowance, deduction or people cost."},
        {"type":"staff_claim","label":"Staff Claim / Reimbursement","icon":"receipt","detail":"Record a staff claim, reimbursement or supporting reference."},
        {"type":"staff_advance","label":"Staff Advance / Retirement","icon":"wallet","detail":"Record an advance issued, used, returned or retired."},
        {"type":"training_activity","label":"Training / Development Cost","icon":"users","detail":"Record training, certification, onboarding or development activity."},
        {"type":"staff_asset_issue","label":"Staff Asset / Resource Issue","icon":"assets","detail":"Record uniforms, IDs, devices or other resources issued to staff."},
        {"type":"hr_operating_cost","label":"HR Operating Activity","icon":"briefcase","detail":"Record recruitment, welfare, medical, travel or HR operating cost."},
    ]),
    ({"maintenance","engineering","mechanic","workshop","biomedical"}, [
        {"type":"work_order","label":"Work Order / Fault","icon":"tool","detail":"Record a fault, job request, inspection or repair requirement."},
        {"type":"repair_completed","label":"Repair Completed","icon":"check","detail":"Record completed repair, labour, materials and outcome."},
        {"type":"spare_part_used","label":"Spare Part / Material Used","icon":"inventory","detail":"Record spare parts, electrical, plumbing or mechanical materials used."},
        {"type":"preventive_maintenance","label":"Preventive Maintenance","icon":"settings","detail":"Record scheduled inspection, service or preventive work."},
        {"type":"downtime_incident","label":"Equipment Downtime","icon":"clock","detail":"Record equipment/facility downtime and operational impact."},
        {"type":"contractor_service","label":"Contractor / External Service","icon":"briefcase","detail":"Record external technician or contractor service activity."},
    ]),
    ({"transport","logistics","fleet","dispatch"}, [
        {"type":"fuel_log","label":"Fuel Log","icon":"vehicle","detail":"Record fuel quantity, amount, vehicle and trip purpose."},
        {"type":"trip_dispatch","label":"Trip / Dispatch","icon":"map","detail":"Record trip, route, dispatch, delivery or movement activity."},
        {"type":"vehicle_repair","label":"Vehicle Repair / Service","icon":"tool","detail":"Record servicing, tyres, parts, repairs or maintenance cost."},
        {"type":"vehicle_assignment","label":"Vehicle Assignment","icon":"vehicle","detail":"Record temporary or permanent assignment of a vehicle/resource."},
        {"type":"transport_income","label":"Transport Income / Collection","icon":"finance","detail":"Record transport-related income where the department earns revenue."},
        {"type":"fleet_incident","label":"Fleet Incident / Exception","icon":"audit","detail":"Record breakdown, accident, delay, penalty or operational exception."},
    ]),
    ({"laboratory","lab"}, [
        {"type":"reagent_usage","label":"Reagent / Kit Usage","icon":"flask","detail":"Record reagent, kit, control or calibrator consumption."},
        {"type":"consumable_issue","label":"Laboratory Consumable Usage","icon":"inventory","detail":"Record tubes, gloves, tips, slides or other consumables used."},
        {"type":"equipment_service","label":"Analyzer / Equipment Service","icon":"tool","detail":"Record analyzer maintenance, calibration or external service."},
        {"type":"wastage_expiry","label":"Wastage / Expiry","icon":"audit","detail":"Record expired, wasted, damaged or rejected laboratory stock."},
        {"type":"stock_check","label":"Lab Stock Check","icon":"check","detail":"Record reagent/consumable count and reorder observation."},
        {"type":"external_referral_cost","label":"External Referral / Outsource","icon":"briefcase","detail":"Record a test/service referred externally and its accountable cost."},
    ]),
    ({"pharmacy"}, [
        {"type":"medicine_receipt","label":"Medicine / Stock Receipt","icon":"pill","detail":"Record medicine or consumable stock received."},
        {"type":"medicine_issue","label":"Medicine Issue / Dispense","icon":"pill","detail":"Record accountable stock issue/dispensing activity."},
        {"type":"expiry_writeoff","label":"Expiry / Write-off","icon":"audit","detail":"Record expired, damaged, returned or written-off medicines."},
        {"type":"cold_chain_check","label":"Cold-chain / Temperature Check","icon":"medical","detail":"Record refrigerator/cold-chain monitoring activity."},
        {"type":"stock_transfer","label":"Pharmacy Stock Transfer","icon":"inventory","detail":"Record transfer between stores, branches or service points."},
        {"type":"supplier_delivery","label":"Supplier Delivery Review","icon":"cart","detail":"Record received supplier delivery, discrepancy or batch note."},
    ]),
    ({"sales","revenue","admission","front office","customer","marketing"}, [
        {"type":"revenue_activity","label":"Revenue / Sales Activity","icon":"finance","detail":"Record a revenue-generating sale/service or accountable sales activity."},
        {"type":"collection","label":"Collection / Payment Follow-up","icon":"wallet","detail":"Record payment collection, deposit or receivable follow-up."},
        {"type":"invoice_raised","label":"Invoice / Billing Activity","icon":"document","detail":"Record invoice, fee, quotation or billing activity."},
        {"type":"discount_refund","label":"Discount / Refund Exception","icon":"receipt","detail":"Record an approved discount, refund or revenue exception."},
        {"type":"campaign_cost","label":"Campaign / Acquisition Cost","icon":"media","detail":"Record campaign, event, outreach or sales-acquisition spend."},
        {"type":"customer_activity","label":"Customer / Client Activity","icon":"users","detail":"Record customer-facing service, enquiry, conversion or account activity."},
    ]),
    ({"project","operation","program","field"}, [
        {"type":"field_expense","label":"Field / Operational Expense","icon":"wallet","detail":"Record field spend, transport, venue or operational cost."},
        {"type":"material_issue","label":"Project Material Usage","icon":"inventory","detail":"Record project materials issued, consumed or moved."},
        {"type":"milestone","label":"Milestone / Deliverable","icon":"check","detail":"Record milestone completion, output or billable deliverable."},
        {"type":"advance_retirement","label":"Advance Retirement","icon":"receipt","detail":"Record field/staff advance retirement and supporting evidence status."},
        {"type":"project_progress","label":"Project Progress Update","icon":"analytics","detail":"Record progress, percentage completion or operational status."},
        {"type":"project_income","label":"Project Income / Funding","icon":"finance","detail":"Record project funding, milestone payment or project revenue activity."},
    ]),
]


def department_operations_profile(department_name):
    name = str(department_name or "").strip().lower()
    for keywords, operations in OPERATION_PROFILES:
        if any(keyword in name for keyword in keywords): return operations
    return DEFAULT_OPERATIONS


def operation_label(department_name, operation_type):
    match = next((row for row in department_operations_profile(department_name) if row["type"] == operation_type), None)
    return match["label"] if match else str(operation_type or "activity").replace("_", " ").title()

# ==========================================================
# OPERATION CREATION
# ==========================================================

def create_department_operation(app, user, payload):
    department = user.department if user.role not in {"owner", "admin"} else Department.query.filter_by(id=payload.get("department_id") or user.department_id, organization_id=user.organization_id, is_active=True).first()
    if not department: raise ValueError("Choose a valid department before recording an operation.")
    operation_type = str(payload.get("operation_type") or "").strip(); valid_types = {row["type"] for row in department_operations_profile(department.name)} | {row["type"] for row in DEFAULT_OPERATIONS}
    if operation_type not in valid_types: raise ValueError("Choose a valid department operation.")
    title = str(payload.get("title") or operation_label(department.name, operation_type)).strip()[:180]; item_name = str(payload.get("item_name") or "").strip()[:180] or None; destination = Department.query.filter_by(id=payload.get("destination_department_id"), organization_id=user.organization_id, is_active=True).first() if payload.get("destination_department_id") else None
    occurred_at = datetime.fromisoformat(str(payload.get("occurred_at")).replace("Z", "+00:00")) if payload.get("occurred_at") else datetime.now(timezone.utc)
    if occurred_at.tzinfo is None: occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    reference = f"OPS-{datetime.now().strftime('%y%m%d')}-{DepartmentOperation.query.filter_by(organization_id=user.organization_id).count()+1:05d}"
    row = DepartmentOperation(reference=reference, organization_id=user.organization_id, department_id=department.id, user_id=user.id, operation_type=operation_type, title=title, item_name=item_name, quantity=float(payload.get("quantity") or 0), unit=str(payload.get("unit") or "").strip()[:60] or None, amount=float(payload.get("amount") or 0), currency=user.organization.currency or "NGN", location=str(payload.get("location") or "").strip()[:180] or None, destination_department_id=destination.id if destination else None, external_reference=str(payload.get("external_reference") or "").strip()[:120] or None, notes=str(payload.get("notes") or "").strip() or None, details_json={"position": user.position or user.role_label}, status="posted", occurred_at=occurred_at)
    db.session.add(row); db.session.flush(); details = f"{user.display_name} recorded {operation_label(department.name, operation_type)} in {department.name}."
    if item_name: details += f" Item/activity: {item_name}."
    if float(row.quantity or 0): details += f" Quantity: {float(row.quantity):g} {row.unit or ''}."
    if float(row.amount or 0): details += f" Amount: {row.currency} {float(row.amount):,.2f}."
    record_activity(app, user, "department_operation", "Department operation recorded", details, "department_operation", row.id, {"reference": row.reference, "operation_type": row.operation_type, "department": department.name, "amount": float(row.amount or 0), "quantity": float(row.quantity or 0)}, notify_owner=True, email_owner=False); db.session.commit(); return row

# ==========================================================
# REPORT METRICS / GENERATION
# ==========================================================

def _period_bounds(period_type, today=None):
    today = today or date.today(); start = today if period_type == "daily" else today - timedelta(days=today.weekday())
    return start, today


def _datetime_bounds(start_date, end_date):
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc); end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start_dt, end_dt


def report_metrics(user, period_type="daily", period_start=None, period_end=None):
    start_date, end_date = (period_start, period_end) if period_start and period_end else _period_bounds(period_type); start_dt, end_dt = _datetime_bounds(start_date, end_date)
    operations = DepartmentOperation.query.filter(DepartmentOperation.organization_id == user.organization_id, DepartmentOperation.user_id == user.id, DepartmentOperation.occurred_at >= start_dt, DepartmentOperation.occurred_at < end_dt).order_by(DepartmentOperation.occurred_at.desc()).all()
    requests = PurchaseRequest.query.filter(PurchaseRequest.organization_id == user.organization_id, PurchaseRequest.requester_id == user.id, PurchaseRequest.created_at >= start_dt, PurchaseRequest.created_at < end_dt).order_by(PurchaseRequest.created_at.desc()).all()
    stock = StockMovement.query.filter(StockMovement.organization_id == user.organization_id, StockMovement.user_id == user.id, StockMovement.created_at >= start_dt, StockMovement.created_at < end_dt).order_by(StockMovement.created_at.desc()).all()
    assets = AssetMovement.query.filter(AssetMovement.organization_id == user.organization_id, AssetMovement.user_id == user.id, AssetMovement.created_at >= start_dt, AssetMovement.created_at < end_dt).order_by(AssetMovement.created_at.desc()).all()
    tracked = ActivityEvent.query.filter(ActivityEvent.organization_id == user.organization_id, ActivityEvent.actor_id == user.id, ActivityEvent.created_at >= start_dt, ActivityEvent.created_at < end_dt).count()
    amount = sum(float(row.amount or 0) for row in operations); actions = []
    for row in operations[:20]: actions.append({"kind":"operation","title":row.title,"detail":operation_label(row.department.name if row.department else "", row.operation_type),"timestamp":row.occurred_at.isoformat(),"reference":row.reference})
    for row in requests[:10]: actions.append({"kind":"request","title":row.title,"detail":f"Request · {row.display_status}","timestamp":row.created_at.isoformat(),"reference":row.reference})
    actions.sort(key=lambda row: row["timestamp"], reverse=True)
    metrics = {"operations":len(operations),"requests":len(requests),"stock_movements":len(stock),"asset_movements":len(assets),"tracked_events":tracked,"amount_recorded":amount,"activity_total":len(operations)+len(requests)+len(stock)+len(assets)}
    return {"period_start":start_date,"period_end":end_date,"metrics":metrics,"actions":actions[:25],"operations":operations,"requests":requests,"stock":stock,"assets":assets}


def generate_staff_report(app, user, period_type="daily", staff_note="", submit=False):
    period_type = period_type if period_type in {"daily","weekly"} else "daily"; data = report_metrics(user, period_type); start_date, end_date, metrics = data["period_start"], data["period_end"], data["metrics"]
    existing = StaffReport.query.filter_by(organization_id=user.organization_id, user_id=user.id, period_type=period_type, period_start=start_date, period_end=end_date).first(); row = existing or StaffReport(reference=f"RPT-{datetime.now().strftime('%y%m%d')}-{StaffReport.query.filter_by(organization_id=user.organization_id).count()+1:05d}", organization_id=user.organization_id, department_id=user.department_id, user_id=user.id, period_type=period_type, period_start=start_date, period_end=end_date, title=f"{period_type.title()} Activity Report · {user.display_name}")
    summary = f"{user.display_name} recorded {metrics['operations']} department operation(s), {metrics['requests']} request(s), {metrics['stock_movements']} stock movement(s) and {metrics['asset_movements']} asset movement(s) during this {period_type} period."
    row.summary, row.metrics_json, row.activity_json = summary, metrics, data["actions"]; note = str(staff_note or "").strip(); row.staff_note = note if note else (row.staff_note if existing else None)
    if submit: row.status, row.submitted_at = "submitted", datetime.now(timezone.utc)
    elif row.status not in {"submitted","acknowledged"}: row.status = "draft"
    if not existing: db.session.add(row)
    db.session.flush(); action = "staff_report_submitted" if submit else "staff_report_generated"; title = "Staff report submitted" if submit else "Staff report generated"
    record_activity(app, user, action, title, f"{user.display_name} {'submitted' if submit else 'generated'} a {period_type} activity report for {start_date.strftime('%d %b')} to {end_date.strftime('%d %b %Y')}.", "staff_report", row.id, {"reference":row.reference,"period_type":period_type,"metrics":metrics}, notify_owner=submit, email_owner=submit); db.session.commit(); return row


def acknowledge_staff_report(app, actor, report):
    if actor.role not in {"owner","admin"}: raise PermissionError("Only organization management can acknowledge staff reports.")
    if report.organization_id != actor.organization_id: raise PermissionError("Cross-organization access denied.")
    report.status, report.acknowledged_by_id, report.acknowledged_at = "acknowledged", actor.id, datetime.now(timezone.utc)
    notify_user(app, report.user, "Report acknowledged", f"{actor.display_name} acknowledged your {report.period_type} activity report {report.reference}.", "success", "staff_report", report.id, email=False)
    record_activity(app, actor, "staff_report_acknowledged", "Staff report acknowledged", f"{actor.display_name} acknowledged {report.user.display_name if report.user else 'staff'} report {report.reference}.", "staff_report", report.id, {"reference":report.reference}, notify_owner=False); db.session.commit(); return report
