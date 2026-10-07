# SERVICE: SAGE Organization Catalog
# Canonical business categories + complete department suggestions used during first-owner onboarding.
# Department names are synchronized with the supplied SAGE Business & Department Item Master Catalogue so onboarding and role/item catalogues use the same structure.

BUSINESS_TYPES = [
    {"key": "school", "label": "School / Educational Institution", "departments": ["Administration", "Finance & Accounts", "Human Resources", "Academic / Classroom", "ICT / Computer Laboratory", "Science Laboratory", "Library", "Procurement", "Stores / Inventory", "Maintenance", "Transport", "Security", "Admissions / Marketing / PR", "Sports / Physical Education"]},
    {"key": "healthcare", "label": "Hospital / Clinic / Diagnostic Centre", "departments": ["Administration", "Finance & Accounts", "Human Resources", "Medical / Doctors / Consultation", "Nursing", "Medical Laboratory", "Pharmacy", "Radiology / Imaging", "Front Desk / Customer Care", "Procurement", "Stores / Medical Store", "ICT / IT", "Maintenance / Biomedical", "Marketing / Business Development"]},
    {"key": "hospitality", "label": "Hotel / Hospitality Company", "departments": ["Front Office / Reception", "Housekeeping", "Food & Beverage Service", "Kitchen / Culinary", "Laundry", "Finance & Accounts", "Human Resources", "Procurement", "Stores / Inventory", "Maintenance / Engineering", "Security", "Sales / Marketing / Events", "ICT / IT"]},
    {"key": "manufacturing", "label": "Manufacturing Company / Factory", "departments": ["Production", "Quality Control / Quality Assurance", "Engineering / Maintenance", "Packaging", "Procurement", "Warehouse / Stores", "Finance & Accounts", "Human Resources", "Sales", "Marketing", "Logistics / Distribution", "Health, Safety & Environment (HSE)", "ICT / IT"]},
    {"key": "retail", "label": "Retail / Supermarket / Shopping Company", "departments": ["Sales Floor", "Cashier / POS", "Procurement / Buying", "Inventory Control", "Warehouse / Back Store", "Finance & Accounts", "Human Resources", "Customer Service", "Marketing / Visual Merchandising", "Logistics / Delivery", "Security / Loss Prevention", "ICT / IT", "E-commerce / Online Orders"]},
    {"key": "construction", "label": "Construction / Engineering Company", "departments": ["Projects / Project Management", "Civil / Structural Engineering", "Quantity Surveying / Cost Control", "Surveying / Geomatics", "Site Operations / Civil Works", "Plant / Equipment", "Procurement", "Stores / Warehouse", "Health, Safety & Environment (HSE)", "Logistics", "Finance & Accounts", "Human Resources / Administration", "ICT / IT"]},
    {"key": "logistics", "label": "Logistics / Transport Company", "departments": ["Operations / Control Room", "Fleet Management", "Dispatch / Last Mile", "Warehouse / Fulfilment", "Maintenance / Workshop", "Procurement", "Finance & Accounts", "Human Resources", "Customer Service", "ICT / IT", "Sales / Marketing", "Health & Safety"]},
    {"key": "restaurant", "label": "Restaurant / Fast Food / Catering Company", "departments": ["Kitchen", "Food Production / Bakery / Prep", "Front of House / Customer Service", "Sales / POS", "Procurement", "Stores / Inventory", "Delivery / Dispatch", "Quality Control / Food Safety", "Finance & Accounts", "Human Resources", "Marketing", "Maintenance"]},
    {"key": "technology", "label": "Technology / Software Company", "departments": ["Software Development / Engineering", "UI / UX Design", "Product Management", "ICT / Infrastructure / DevOps", "Quality Assurance / Testing", "Cybersecurity", "Data / AI / Analytics", "Sales", "Marketing / Growth", "Customer Support / Success", "Finance & Accounts", "Human Resources / People Operations", "Administration / Workplace"]},
    {"key": "ngo", "label": "NGO / Foundation / Non-Profit Organization", "departments": ["Administration", "Finance & Accounts", "Human Resources", "Programs", "Projects / Implementation", "Monitoring, Evaluation, Accountability & Learning (MEAL/M&E)", "Procurement", "Logistics / Fleet", "Communications / Advocacy", "Partnerships / Fundraising", "ICT / IT", "Field Operations", "Grants / Compliance"]},
    {"key": "other", "label": "Other / Custom Organization", "departments": ["Administration", "Finance & Accounts", "Human Resources", "Procurement", "Stores / Inventory", "Operations", "ICT / IT"]},
]

BUSINESS_TYPE_MAP = {item["key"]: item for item in BUSINESS_TYPES}


def suggested_departments(business_type_key):
    return list(BUSINESS_TYPE_MAP.get(business_type_key, BUSINESS_TYPE_MAP["other"])["departments"])

# ==========================================================
# INDIVIDUAL / ENTREPRENEUR BUSINESS TYPES
# These map lean owner-operated businesses to the nearest SAGE master catalogue while keeping a distinct dashboard/workspace mode.
# ==========================================================
INDIVIDUAL_BUSINESS_TYPES = [
    {"key":"retail_shop","label":"Retail Shop / Mini Mart / Boutique","catalog_key":"retail","primary_department":"Sales Floor"},
    {"key":"ecommerce","label":"Online Store / E-commerce Business","catalog_key":"retail","primary_department":"E-commerce / Online Orders"},
    {"key":"food","label":"Food / Catering / Bakery Business","catalog_key":"restaurant","primary_department":"Kitchen"},
    {"key":"technology","label":"Technology / Digital Services","catalog_key":"technology","primary_department":"ICT / Infrastructure / DevOps"},
    {"key":"freelance","label":"Freelancer / Professional Services","catalog_key":"technology","primary_department":"Administration / Workplace"},
    {"key":"consulting","label":"Consulting / Coaching / Training","catalog_key":"technology","primary_department":"Administration / Workplace"},
    {"key":"creative","label":"Creative / Media / Photography Business","catalog_key":"technology","primary_department":"Marketing / Growth"},
    {"key":"fashion","label":"Fashion / Tailoring / Clothing Business","catalog_key":"retail","primary_department":"Sales Floor"},
    {"key":"beauty","label":"Beauty / Salon / Spa Business","catalog_key":"retail","primary_department":"Customer Service"},
    {"key":"transport","label":"Transport / Delivery / Dispatch Business","catalog_key":"logistics","primary_department":"Operations / Control Room"},
    {"key":"construction","label":"Construction / Artisan / Handyman Business","catalog_key":"construction","primary_department":"Site Operations / Civil Works"},
    {"key":"agriculture","label":"Agriculture / Farm / Agro-business","catalog_key":"manufacturing","primary_department":"Production"},
    {"key":"health","label":"Health / Wellness Practice","catalog_key":"healthcare","primary_department":"Administration"},
    {"key":"real_estate","label":"Real Estate / Property Services","catalog_key":"construction","primary_department":"Projects / Project Management"},
    {"key":"other","label":"Other / Custom Individual Business","catalog_key":"other","primary_department":"Business Operations"},
]
INDIVIDUAL_BUSINESS_TYPE_MAP = {item["key"]: item for item in INDIVIDUAL_BUSINESS_TYPES}


def individual_business_type(key): return INDIVIDUAL_BUSINESS_TYPE_MAP.get(str(key or "").strip(), INDIVIDUAL_BUSINESS_TYPE_MAP["other"])
def canonical_business_for_individual(key):
    item = individual_business_type(key); catalog = BUSINESS_TYPE_MAP.get(item["catalog_key"], BUSINESS_TYPE_MAP["other"]); return {**item, "catalog_label": catalog["label"]}
