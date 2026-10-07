# SERVICE: SAGE Navigation / Page Metadata
# Keeps static navigation labels separate while operational page data now comes from the real database.

NAV_ITEMS = [
    {"section": "OVERVIEW", "items": [
        {"page": "dashboard", "label": "Dashboard", "icon": "dashboard"}, {"page": "workspace", "label": "Department Workspace", "icon": "briefcase"}, {"page": "catalog", "label": "Department Catalogue", "icon": "inventory"}, {"page": "analytics", "label": "Analytics", "icon": "analytics"}, {"page": "finance", "label": "Finance", "icon": "wallet"},
    ]},
    {"section": "OPERATIONS", "items": [
        {"page": "requests", "label": "Requests & Approvals", "icon": "requests"}, {"page": "operations", "label": "Department Operations", "icon": "briefcase"}, {"page": "fulfillment", "label": "Acquisition Hub", "icon": "check"}, {"page": "procurement", "label": "Procurement", "icon": "cart"}, {"page": "inventory", "label": "Inventory", "icon": "inventory"}, {"page": "assets", "label": "Assets", "icon": "assets"},
    ]},
    {"section": "ORGANIZATION", "items": [
        {"page": "departments", "label": "Departments", "icon": "building"}, {"page": "staff", "label": "Staff", "icon": "users"}, {"page": "reports", "label": "Reports", "icon": "reports"}, {"page": "audit", "label": "Live Activity & Audit", "icon": "audit"},
    ]},
    {"section": "SYSTEM", "items": [{"page": "settings", "label": "Settings", "icon": "settings"}]},
]

PAGE_TITLES = {
    "dashboard": ("Dashboard", "Live organization-wide financial and operational position."),
    "workspace": ("Department Workspace", "Job-focused tools, actions and KPIs for the signed-in department."),
    "catalog": ("Department Catalogue", "Role-aware equipment, materials, consumables and custom items for the signed-in department."),
    "analytics": ("Analytics", "Explore financial, operational and departmental performance."),
    "finance": ("Finance", "Income, revenue, expenditure, cash flow, budgets and financial position."),
    "requests": ("Requests & Approvals", "From staff need to approval, money-sent confirmation, purchase evidence and final accountability."),
    "operations": ("Department Operations", "Job-specific operational actions, accountable records and live staff activity."),
    "fulfillment": ("Acquisition Hub", "Turn granted requests into confirmed stock or assets with receipts, custody and immutable evidence."),
    "procurement": ("Procurement", "Track requested items, sourcing, commitments, buying activity and fulfillment."),
    "inventory": ("Inventory", "Monitor received items, stock value, usage, transfers and replenishment."),
    "assets": ("Assets", "Track equipment, custodians, locations and movements."),
    "departments": ("Departments", "Create and manage every department, unit, branch or special team."),
    "staff": ("Staff", "Manage people, roles, departments and accountability."),
    "reports": ("Reports", "Management-ready finance, procurement, inventory, department and audit reports."),
    "audit": ("Live Activity & Audit", "Owner-visible timeline of staff actions, evidence, approvals and changes."),
    "settings": ("Settings", "Configure organization profile, approvals, roles and notification preferences."),
}

ACTIVITIES, RECENT_REQUESTS = [], []
