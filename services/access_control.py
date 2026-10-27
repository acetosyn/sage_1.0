# SERVICE: SAGE Role-Based + Department-Aware Access Control
# Sidebar visibility and backend authorization are calculated together; department workers receive job-relevant pages without gaining owner-wide visibility.

OWNER_ROLES = {"owner", "admin"}
ALL_PAGES = {"dashboard", "workspace", "catalog", "analytics", "income", "expenses", "finance", "requests", "fulfillment", "procurement", "inventory", "assets", "departments", "staff", "reports", "audit", "settings", "operations"}
ROLE_PAGE_ACCESS = {
    "owner": ALL_PAGES, "admin": ALL_PAGES,
    "finance": {"dashboard", "workspace", "catalog", "analytics", "income", "expenses", "finance", "requests", "fulfillment", "operations", "reports", "audit"},
    "procurement": {"dashboard", "workspace", "catalog", "expenses", "requests", "fulfillment", "procurement", "inventory", "assets", "operations", "reports"},
    "department_head": {"dashboard", "workspace", "catalog", "expenses", "requests", "fulfillment", "operations", "reports", "departments"},
    "staff": {"dashboard", "workspace", "catalog", "requests", "fulfillment", "operations", "reports", "departments"},
}

# Department workers get operational screens relevant to physical custody/purchasing without inheriting organization-wide finance/admin rights.
DEPARTMENT_PAGE_RULES = [
    ({"procurement", "purchasing", "buyer"}, {"procurement", "inventory", "assets"}),
    ({"store", "inventory", "warehouse"}, {"procurement", "inventory", "assets"}),
    ({"ict", "technology", "maintenance", "engineering", "mechanic", "workshop", "fleet", "transport", "logistics"}, {"assets"}),
]


def allowed_pages(user):
    from services.operational_policy import can_operate, is_individual_workspace
    allowed = set(ROLE_PAGE_ACCESS.get(user.role, {"dashboard", "workspace"})); department_name = (user.department.name if getattr(user, "department", None) else "").lower()
    for keywords, extra in DEPARTMENT_PAGE_RULES:
        if any(keyword in department_name for keyword in keywords): allowed.update(extra)
    allowed.add("events")

    # SAGE 5.0 delegated operations: organization owners retain visibility; staff receive the operational pages their role/department owns.
    if user.role in OWNER_ROLES or is_individual_workspace(user):
        allowed.update({"customers", "debtors", "imprest", "daily_close", "suppliers", "bills", "compliance", "payroll", "branches", "stock"})
    else:
        if can_operate(user, "crm"):
            allowed.add("customers")
        if can_operate(user, "sales") or can_operate(user, "collections"):
            allowed.add("debtors")
        if can_operate(user, "supplier"):
            allowed.add("suppliers")
        if can_operate(user, "finance_ops"):
            allowed.update({"finance", "income", "expenses", "imprest", "daily_close", "bills", "compliance", "payroll"})
        if can_operate(user, "daily_close"):
            allowed.add("daily_close")
        if can_operate(user, "money_in"):
            allowed.add("income")
        if can_operate(user, "bills"):
            allowed.add("bills")
        if can_operate(user, "compliance"):
            allowed.add("compliance")
        if can_operate(user, "stock"):
            allowed.update({"stock", "inventory"})
        if can_operate(user, "payroll"):
            allowed.add("payroll")

    if user.role in {'owner','admin','finance','department_head'}: allowed.add('business_reports')
    if user.role in {"owner","admin","finance","department_head"}: allowed.add("branches")
    if user.role not in OWNER_ROLES:
        from services.business_core import membership
        branch_member=membership(user)
        if branch_member and branch_member.is_manager: allowed.update({"branches","reports","analytics"})

    # Assigned scheduled obligations remain visible even when the staff member is not a finance operator.
    if user.role not in OWNER_ROLES and not can_operate(user, "finance_ops"):
        from models import BillPlan,ComplianceDocument,ImprestFund
        if BillPlan.query.filter_by(organization_id=user.organization_id,responsible_id=user.id).first():allowed.add('bills')
        if ComplianceDocument.query.filter_by(organization_id=user.organization_id,responsible_id=user.id).first():allowed.add('compliance')
        if ImprestFund.query.filter_by(organization_id=user.organization_id,holder_id=user.id,status='active').first():allowed.add('imprest')
    if 'inventory' in allowed:allowed.add('stock')
    return allowed

def can_access_page(user, page): return bool(user and user.is_authenticated and page in allowed_pages(user))

def filter_navigation(nav_items, user):
    allowed, filtered = allowed_pages(user), []; profile = getattr(getattr(user, "organization", None), "workspace_profile", None); individual_owner = bool(user.role == "owner" and profile and profile.workspace_mode == "individual")
    for section in nav_items:
        items = [dict(item) for item in section["items"] if item["page"] in allowed and not (individual_owner and item["page"] in {"requests", "departments"})]
        for item in items:
            if user.role not in OWNER_ROLES:
                if item["page"] == "departments": item["label"] = "My Department"
                if item["page"] == "workspace": item["label"] = "My Workspace"
                if item["page"] == "catalog": item["label"] = "My Catalogue"
            elif individual_owner:
                if item["page"] == "workspace": item["label"] = "Business Workspace"
                if item["page"] == "catalog": item["label"] = "Business Catalogue"
                if item["page"] == "operations": item["label"] = "Business Operations"
                if item["page"] == "staff": item["label"] = "People / Staff"
        if items: filtered.append({"section": section["section"], "key": section.get("key", section["section"].lower().replace(" ", "-")), "tone": section.get("tone", "blue"), "items": items})
    return filtered

def is_owner_admin(user): return bool(user and user.is_authenticated and user.role in OWNER_ROLES)
