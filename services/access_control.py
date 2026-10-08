# SERVICE: SAGE Role-Based + Department-Aware Access Control
# Sidebar visibility and backend authorization are calculated together; department workers receive job-relevant pages without gaining owner-wide visibility.

OWNER_ROLES = {"owner", "admin"}
ALL_PAGES = {"dashboard", "workspace", "catalog", "analytics", "income", "expenses", "finance", "requests", "fulfillment", "procurement", "inventory", "assets", "departments", "staff", "reports", "audit", "settings", "operations"}
ROLE_PAGE_ACCESS = {
    "owner": ALL_PAGES, "admin": ALL_PAGES,
    "finance": {"dashboard", "workspace", "catalog", "analytics", "income", "expenses", "finance", "requests", "fulfillment", "operations", "reports", "audit"},
    "procurement": {"dashboard", "workspace", "catalog", "income", "expenses", "requests", "fulfillment", "procurement", "inventory", "assets", "operations", "reports"},
    "department_head": {"dashboard", "workspace", "catalog", "income", "expenses", "requests", "fulfillment", "operations", "reports", "departments"}, "staff": {"dashboard", "workspace", "catalog", "income", "requests", "fulfillment", "operations", "reports", "departments"},
}

# Department workers get operational screens relevant to physical custody/purchasing without inheriting organization-wide finance/admin rights.
DEPARTMENT_PAGE_RULES = [
    ({"procurement", "purchasing", "buyer"}, {"procurement", "inventory", "assets"}),
    ({"store", "inventory", "warehouse"}, {"procurement", "inventory", "assets"}),
    ({"ict", "technology", "maintenance", "engineering", "mechanic", "workshop", "fleet", "transport", "logistics"}, {"assets"}),
]


def allowed_pages(user):
    allowed = set(ROLE_PAGE_ACCESS.get(user.role, {"dashboard", "workspace"})); department_name = (user.department.name if getattr(user, "department", None) else "").lower()
    for keywords, extra in DEPARTMENT_PAGE_RULES:
        if any(keyword in department_name for keyword in keywords): allowed.update(extra)
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
        if items: filtered.append({"section": section["section"], "items": items})
    return filtered

def is_owner_admin(user): return bool(user and user.is_authenticated and user.role in OWNER_ROLES)
