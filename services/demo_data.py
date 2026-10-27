# SERVICE: SAGE Navigation / Page Metadata
# Keeps static navigation labels separate while operational page data now comes from the real database.

NAV_ITEMS = [
    # ==========================================================
    # SAGE SIDEBAR NAVIGATION — compact accordion sections
    # Section keys/tone names drive the shared desktop + mobile sidebar styling without changing page routes.
    # ==========================================================
    {"section": "FINANCE & CONTROL", "key": "finance-control", "tone": "blue", "items": [
        {"page": "dashboard", "label": "Dashboard", "icon": "dashboard"}, {"page": "requests", "label": "Requests & Approvals", "icon": "requests"}, {"page": "income", "label": "Income & Sales", "icon": "arrow-up"}, {"page": "expenses", "label": "Expenses & Expenditure", "icon": "arrow-down"}, {"page": "finance", "label": "Finance", "icon": "wallet"},
    ]},
    {"section": "DEPARTMENTS & OPERATIONS", "key": "departments-operations", "tone": "green", "items": [
        {"page": "workspace", "label": "Department Workspace", "icon": "briefcase"}, {"page": "catalog", "label": "Department Catalogue", "icon": "inventory"}, {"page": "operations", "label": "Department Operations", "icon": "briefcase"}, {"page": "fulfillment", "label": "Acquisition Hub", "icon": "check"}, {"page": "procurement", "label": "Procurement", "icon": "cart"}, {"page": "inventory", "label": "Inventory", "icon": "inventory"}, {"page": "assets", "label": "Assets & Expenditure", "icon": "assets"},
    ]},
    {"section": "ORGANIZATION", "key": "organization", "tone": "violet", "items": [
        {"page": "departments", "label": "Departments", "icon": "building"}, {"page": "staff", "label": "Staff", "icon": "users"}, {"page": "reports", "label": "Reports", "icon": "reports"}, {"page": "audit", "label": "Audit Trail", "icon": "audit"},
    ]},
    {"section": "INSIGHTS", "key": "insights", "tone": "cyan", "items": [{"page": "analytics", "label": "Analytics", "icon": "analytics"}]},
    {"section": "SYSTEM", "key": "system", "tone": "orange", "items": [{"page": "settings", "label": "Settings", "icon": "settings"}]},
]

PAGE_TITLES = {
    "dashboard": ("Dashboard", "Live organization-wide financial and operational position."),
    "workspace": ("Department Workspace", "Job-focused tools, actions and KPIs for the signed-in department."),
    "catalog": ("Department Catalogue", "Role-aware equipment, materials, consumables and custom items for the signed-in department."),
    "analytics": ("Analytics", "Explore financial, operational and departmental performance."),
    "income": ("Income & Sales", "Sales, fees, service income and other money coming into the organization, with staff accountability."),
    "expenses": ("Expenses & Expenditure", "Detailed money-out tracking by department, date, vendor, payment method and accountable staff."),
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
    "audit": ("Audit Trail", "Time-aware organization history across finance, requests, purchases, inventory, assets, staff access and retained changes."),
    "settings": ("Settings", "Configure organization profile, approvals, roles and notification preferences."),
}

ACTIVITIES, RECENT_REQUESTS = [], []

PAGE_TITLES["events"] = ("Events & Campaigns", "Planning, funding, accountability and measurable business outcomes.")
NAV_ITEMS[1]["items"].append({"page":"events", "label":"Events & Campaigns", "icon":"briefcase"})
PAGE_TITLES.update({"customers":("Customers & Sales CRM","Contacts, customer history, invoices and connected credit sales."),"debtors":("Debtors & Credit Sales","Outstanding invoices, due dates and payment history.")})
NAV_ITEMS[0]["items"].append({"page":"debtors","label":"Debtors & Credit Sales","icon":"wallet"})
NAV_ITEMS[2]["items"].insert(0,{"page":"customers","label":"Customers & CRM","icon":"users"})
PAGE_TITLES.update({"suppliers":("Suppliers & Vendors","Supplier details, quotations, acquisition history and payable balances."),"imprest":("Petty Cash & Imprest","Accountable cash, receipt-backed retirement and approved replenishment.")})
NAV_ITEMS[0]["items"].append({"page":"imprest","label":"Petty Cash & Imprest","icon":"wallet"})
NAV_ITEMS[2]["items"].insert(1,{"page":"suppliers","label":"Suppliers & Vendors","icon":"cart"})
PAGE_TITLES.update({"daily_close":("Daily Sales & Cash Reconciliation","Compare recorded collections with counted payment channels."),"branches":("Branches & Shops","Branch performance, staff access and finance-account allocation.")})
NAV_ITEMS[0]["items"].append({"page":"daily_close","label":"Daily Sales / POS Close","icon":"check"})
NAV_ITEMS[2]["items"].insert(2,{"page":"branches","label":"Branches & Shops","icon":"building"})
PAGE_TITLES.update({'stock':('Advanced Stock Control','Batches, expiry, prices, transfers and physical counts.'),'bills':('Bills & Renewals','Subscriptions, recurring costs, due dates and payments.'),'compliance':('Compliance Centre','Business documents, renewal history and expiry accountability.')})
NAV_ITEMS[1]['items'].append({'page':'stock','label':'Advanced Stock Control','icon':'inventory'})
NAV_ITEMS[3]['items'].extend([{'page':'bills','label':'Bills & Renewals','icon':'wallet'},{'page':'compliance','label':'Compliance Centre','icon':'audit'}])
PAGE_TITLES.update({'payroll':('Staff Finance & Payroll','Salary policy, commissions, payslips, claims and staff advances.'),'business_reports':('Business Operations Reports','Connected operating results, receivables, cash accountability and upcoming obligations.')})
NAV_ITEMS[2]['items'].append({'page':'payroll','label':'Staff Finance & Payroll','icon':'users'})
NAV_ITEMS[3]['items'].append({'page':'business_reports','label':'Business Operations Reports','icon':'reports'})
