# SERVICE: SAGE Department Item Catalogue
# Loads the cross-industry seed catalogue, matches the signed-in organization/department and supplies icon-aware role-specific item data without hard-coding one tenant.

import json
import re
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CATALOG_FILE = BASE_DIR / "static" / "data" / "sage_item_catalog.json"

STOP_WORDS = {"and", "the", "department", "unit", "office", "company", "centre", "center", "service", "services"}
BUSINESS_LABEL_ALIASES = {"School / Educational Institution": "School / Educational Institution", "Hospital / Clinic / Diagnostic Centre": "Hospital / Clinic / Diagnostic Centre", "Hotel / Hospitality Company": "Hotel / Hospitality Company", "Manufacturing Company / Factory": "Manufacturing Company / Factory", "Retail / Supermarket / Shopping Company": "Retail / Supermarket / Shopping Company", "Construction / Engineering Company": "Construction / Engineering Company", "Logistics / Transport Company": "Logistics / Transport Company", "Restaurant / Fast Food / Catering Company": "Restaurant / Fast Food / Catering Company", "Technology / Software Company": "Technology / Software Company", "NGO / Foundation / Non-Profit Organization": "NGO / Foundation / Non-Profit Organization"}

# Explicit aliases cover common onboarding names that are shorter than the master-catalogue headings.
DEPARTMENT_ALIASES = {
    "ict": ["ict / it", "ict / computer laboratory", "ict / infrastructure"], "it": ["ict / it", "ict / computer laboratory", "ict / infrastructure"],
    "laboratory": ["medical laboratory", "science laboratory"], "stores / inventory": ["stores / inventory", "stores / medical store", "warehouse / stores"],
    "stores": ["stores / inventory", "stores / medical store", "warehouse / stores"], "maintenance": ["maintenance / biomedical", "maintenance / engineering", "engineering / maintenance"],
    "finance": ["finance & accounts", "finance / accounts"], "finance & accounts": ["finance & accounts", "finance / accounts"],
    "front office": ["front office / reception"], "human resources": ["human resources"], "academic department": ["academic / classroom"],
    "sales / pos": ["sales / pos", "sales"], "customer service": ["customer service", "front desk / customer care"], "logistics": ["operations / control room", "dispatch / last mile", "warehouse / fulfilment"], "procurement": ["procurement"],
}

ICON_RULES = [
    (("laptop", "computer", "desktop", "workstation", "tablet", "monitor", "server", "nas", "thin client", "mini pc"), "device"),
    (("router", "switch", "firewall", "network", "wifi", "wi-fi", "access point", "patch panel", "transceiver"), "network"),
    (("cable", "cord", "connector", "adapter", "usb", "hdmi", "displayport", "vga", "charger", "extension"), "cable"),
    (("printer", "scanner", "photocopier", "label printer", "receipt printer"), "printer"),
    (("chair", "desk", "table", "cabinet", "shelf", "shelving", "rack", "cupboard", "locker", "trolley"), "furniture"),
    (("tool", "screwdriver", "spanner", "wrench", "plier", "hammer", "drill", "multimeter", "solder", "grinder", "saw"), "tool"),
    (("vehicle", "bus", "van", "truck", "car", "tyre", "tire", "fuel", "engine oil", "brake", "driver"), "vehicle"),
    (("microscope", "centrifuge", "reagent", "pipette", "test tube", "cuvette", "analyzer", "analyser", "laboratory", "specimen"), "flask"),
    (("drug", "medicine", "tablet", "capsule", "syrup", "injection", "vaccine", "insulin", "pharmacy"), "pill"),
    (("stethoscope", "bp monitor", "blood-pressure", "oxygen", "nebulizer", "patient", "hospital bed", "wheelchair", "clinical"), "medical"),
    (("glove", "mask", "goggle", "helmet", "hard hat", "ppe", "first-aid", "fire extinguisher", "safety", "biohazard"), "safety"),
    (("mop", "broom", "detergent", "bleach", "cleaner", "cleaning", "tissue", "toilet roll", "sanitizer", "disinfectant"), "cleaning"),
    (("rice", "flour", "meat", "fish", "oil", "spice", "food", "kitchen", "plate", "cutlery", "glass", "cup"), "food"),
    (("receipt", "invoice", "cashbook", "ledger", "voucher", "cheque", "pos terminal", "currency", "bank", "calculator"), "finance"),
    (("camera", "tripod", "gimbal", "microphone", "banner", "brochure", "flyer", "marketing", "backdrop"), "media"),
    (("paper", "book", "file", "form", "register", "folder", "envelope", "notepad", "label", "document"), "document"),
    (("box", "carton", "pallet", "bin", "stock", "packaging", "bag", "bottle", "container"), "box"),
    (("software", "licence", "license", "subscription", "hosting", "domain", "cloud", "ssl"), "cloud"),
    (("phone", "headset", "radio", "walkie", "intercom"), "phone"),
    (("battery", "electrical", "socket", "switch", "circuit", "ups", "inverter", "power"), "power"),
    (("cctv", "security", "access control", "padlock", "key", "alarm", "detector"), "lock"),
]


def normalize(value): return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
def tokens(value): return {word for word in normalize(value).split() if word not in STOP_WORDS and len(word) > 1}


@lru_cache(maxsize=1)
def load_catalog():
    try:
        with CATALOG_FILE.open("r", encoding="utf-8") as handle: return json.load(handle)
    except (OSError, json.JSONDecodeError): return {}


def business_catalog(business_type):
    catalogue = load_catalog(); exact = BUSINESS_LABEL_ALIASES.get(str(business_type or "").strip())
    if exact and exact in catalogue: return exact, catalogue[exact]
    wanted = tokens(business_type); best = max(catalogue.items(), key=lambda row: len(wanted & tokens(row[0])), default=(None, {}))
    return best if best[0] and wanted else (None, {})


def department_match(business_type, department_name):
    business_name, departments = business_catalog(business_type)
    if not departments: return business_name, None, []
    requested = normalize(department_name); direct = {normalize(name): name for name in departments}
    if requested in direct: matched = direct[requested]; return business_name, matched, departments[matched]
    for alias in DEPARTMENT_ALIASES.get(requested, []):
        if normalize(alias) in direct: matched = direct[normalize(alias)]; return business_name, matched, departments[matched]
    wanted = tokens(department_name); ranked = []
    for name, items in departments.items():
        candidate = tokens(name); overlap = len(wanted & candidate); coverage = overlap / max(1, len(wanted)); specificity = overlap / max(1, len(candidate)); ranked.append((coverage * 3 + specificity + overlap, name, items))
    score, matched, items = max(ranked, default=(0, None, []), key=lambda row: row[0])
    return (business_name, matched, items) if score > 0 else (business_name, None, [])


def item_icon(name, category=""):
    haystack = normalize(f"{category} {name}")
    for keywords, icon in ICON_RULES:
        if any(keyword in haystack for keyword in keywords): return icon
    return "inventory"


def department_catalog(business_type, department_name, custom_items=None):
    business_name, matched_department, seed_items = department_match(business_type, department_name); custom_items = custom_items or []
    records, seen = [], set()
    for row in custom_items:
        name, category = str(row.name or "").strip(), str(row.category or "Custom").strip() or "Custom"; key = normalize(name)
        if name and key not in seen: seen.add(key); records.append({"id": row.id, "name": name, "category": category, "unit": row.unit or "unit", "icon": item_icon(name, category), "is_custom": True})
    for row in seed_items:
        name, category = str(row.get("name") or "").strip(), str(row.get("category") or "General").strip(); key = normalize(name)
        if name and key not in seen: seen.add(key); records.append({"id": None, "name": name, "category": category, "unit": "unit", "icon": item_icon(name, category), "is_custom": False})
    groups = {}
    for row in records: groups.setdefault(row["category"], []).append(row)
    return {"business_name": business_name, "matched_department": matched_department, "requested_department": department_name, "items": records, "groups": [{"name": name, "icon": item_icon("", name), "items": items} for name, items in groups.items()], "count": len(records), "custom_count": sum(1 for row in records if row["is_custom"]), "matched": bool(matched_department)}


def organization_catalog_summary(business_type):
    business_name, departments = business_catalog(business_type)
    return {"business_name": business_name, "departments": [{"name": name, "count": len(items)} for name, items in departments.items()], "total_items": sum(len(items) for items in departments.values())}
