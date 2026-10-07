# SERVICE: SAGE AI
# OpenAI-powered business copilot with tenant/role-scoped live operational context; receipt-content extraction remains isolated for a later document-analysis layer.

from openai import OpenAI
from services.reporting_service import reporting_context

# ==========================================================
# ROLE-SCOPED LIVE CONTEXT
# ==========================================================

def _live_context(user):
    from models import ActivityEvent, FinancialRecord, InventoryItem, PurchaseRequest
    from services.operations_service import finance_summary

    owner_scope = user.role in {"owner", "admin", "finance", "procurement"}
    request_query = PurchaseRequest.query.filter_by(organization_id=user.organization_id)
    inventory_query = InventoryItem.query.filter_by(organization_id=user.organization_id)
    activity_query = ActivityEvent.query.filter_by(organization_id=user.organization_id)
    if not owner_scope:
        request_query = request_query.filter(PurchaseRequest.department_id == user.department_id); inventory_query = inventory_query.filter(InventoryItem.department_id == user.department_id); activity_query = activity_query.filter(ActivityEvent.department_id == user.department_id)

    requests = request_query.order_by(PurchaseRequest.created_at.desc()).limit(12).all(); inventory = inventory_query.order_by(InventoryItem.updated_at.desc()).limit(12).all(); activity = activity_query.order_by(ActivityEvent.created_at.desc()).limit(12).all()
    finance = finance_summary(user.organization_id) if user.role in {"owner", "admin", "finance"} else {}
    intelligence = reporting_context(user, months=6)
    return {
        "finance": finance,
        "intelligence": {"income_total": intelligence["income_total"], "expense_total": intelligence["expense_total"], "net": intelligence["net"], "accounts_receivable": intelligence["ar_balance"], "accounts_payable": intelligence["ap_balance"], "inventory_value": intelligence["inventory_value"], "asset_value": intelligence["asset_value"], "budget_available": intelligence["budget_available"], "request_status": intelligence["request_status"], "exceptions": intelligence["exceptions"], "monthly": intelligence["monthly"], "department_breakdown": intelligence["department_breakdown"][:6]},
        "requests": [{"reference": r.reference, "title": r.title, "department": r.department.name if r.department else None, "status": r.status, "amount": float(r.estimated_total or 0), "requester": r.requester.display_name if r.requester else None} for r in requests],
        "inventory": [{"name": i.name, "department": i.department.name if i.department else None, "quantity": float(i.quantity or 0), "unit": i.unit, "unit_value": float(i.unit_value or 0), "reorder_level": float(i.reorder_level or 0)} for i in inventory],
        "recent_activity": [{"title": a.title, "description": a.description, "actor": a.actor.display_name if a.actor else None, "department": a.department.name if a.department else None, "time": a.created_at.isoformat()} for a in activity],
    }

# ==========================================================
# OPENAI CHAT
# ==========================================================

def ask_vision_ai(app, user, message, history=None):
    api_key = (app.config.get("OPENAI_API_KEY") or "").strip(); model = (app.config.get("OPENAI_MODEL_SOLVER") or "gpt-5.4").strip()
    if not api_key or api_key.lower().startswith("sk-xxxx"): raise RuntimeError("OpenAI is not configured yet. Paste the real OPENAI_API_KEY into .env and restart SAGE.")

    scope = "organization-wide information" if user.role in {"owner", "admin"} else f"authorized information for {user.department.name if user.department else 'the assigned workspace'}"
    context = _live_context(user)
    instructions = (
        "You are SAGE AI, a concise finance and business-operations copilot inside SAGE. Use only the supplied live tenant context and general app guidance. "
        f"Signed-in user: {user.display_name}; role: {user.role_label}; organization: {user.organization.name}; authorization scope: {scope}. "
        "Never reveal another organization's information and never expand beyond the user's authorization scope. Distinguish committed procurement from actual expenditure. "
        "Use the supplied management intelligence for trend, exception, budget, receivable/payable, inventory-value and department-spend questions. When figures are absent, say there is no recorded data instead of inventing values. "
        "Final purchase records and receipt evidence are auditable; do not imply receipt-image contents were analyzed unless extracted content is explicitly supplied. Keep answers compact, numeric when possible, and action-oriented. "
        f"LIVE SAGE CONTEXT: {context}"
    )
    input_items = []
    for item in (history or [])[-8:]:
        role = item.get("role") if item.get("role") in {"user", "assistant"} else "user"; content = str(item.get("content") or "").strip()
        if content: input_items.append({"role": role, "content": content})
    input_items.append({"role": "user", "content": message})
    client = OpenAI(api_key=api_key); response = client.responses.create(model=model, instructions=instructions, input=input_items)
    return (response.output_text or "I could not produce a response.").strip(), model
