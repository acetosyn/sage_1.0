# SERVICE: SAGE 5.0 Delegated Operations Policy
# Keeps organization owners in oversight/approval mode while individual owners remain hands-on operators.
# Staff operational access is derived from explicit SAGE role plus department/position responsibility.

from functools import wraps


def _profile(user):
    return getattr(getattr(user, "organization", None), "workspace_profile", None)


def is_individual_workspace(user):
    profile = _profile(user)
    return bool(profile and getattr(profile, "workspace_mode", None) == "individual")


def is_organization_owner_observer(user):
    return bool(user and getattr(user, "role", None) == "owner" and not is_individual_workspace(user))


def _work_text(user):
    department = getattr(getattr(user, "department", None), "name", "") or ""
    position = getattr(user, "position", "") or ""
    return f"{department} {position}".strip().lower()


def _has_any(text, words):
    return any(word in text for word in words)


# Department/position vocabulary intentionally includes common Nigerian/African business naming.
SALES_WORDS = {"sales", "revenue", "cashier", "front office", "front desk", "admission", "billing", "commercial", "retail", "shop", "business development", "marketing", "reception"}
FINANCE_WORDS = {"finance", "account", "accounts", "accounting", "treasury", "audit", "auditor"}
PROCUREMENT_WORDS = {"procurement", "purchasing", "purchase", "buyer", "supply chain", "sourcing"}
STOCK_WORDS = {"store", "stores", "inventory", "warehouse", "stock", "logistics"}
CRM_WORDS = SALES_WORDS | {"client service", "customer care", "customer service", "relationship", "crm", "human resources", "hr"}
BILLS_WORDS = FINANCE_WORDS | {"administration", "admin", "office management", "facility", "facilities", "operations"}
COMPLIANCE_WORDS = FINANCE_WORDS | {"compliance", "legal", "regulatory", "quality", "hse", "health & safety", "administration", "admin"}
PAYROLL_WORDS = FINANCE_WORDS | {"payroll", "human resources", "hr", "people", "personnel", "people operations"}
DAILY_CLOSE_WORDS = FINANCE_WORDS | {"sales", "cashier", "front office", "front desk", "billing", "retail", "shop", "reception"}
MONEY_IN_WORDS = SALES_WORDS | FINANCE_WORDS | {"laboratory", "lab", "clinic", "restaurant", "food & beverage", "kitchen", "laundry", "transport"}


ROLE_CAPABILITIES = {
    "admin": {"crm", "sales", "collections", "supplier", "finance_ops", "expense", "imprest_open", "daily_close", "bills", "compliance", "stock", "payroll"},
    "finance": {"crm", "sales", "collections", "finance_ops", "expense", "imprest_open", "daily_close", "bills", "compliance", "payroll"},
    "procurement": {"supplier", "stock"},
}


def can_operate(user, capability):
    """Return whether this user should perform routine operational data-entry for a capability.

    Organization owners intentionally return False for routine operations. Individual owners return True,
    because in that workspace the owner is also the operator. Owner-only management/approval routes are
    handled separately by their existing permission rules and are not routed through this helper.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = str(getattr(user, "role", "") or "").lower()
    if role == "owner":
        return is_individual_workspace(user)
    if capability in ROLE_CAPABILITIES.get(role, set()):
        return True

    text = _work_text(user)
    if capability == "crm": return _has_any(text, CRM_WORDS)
    if capability in {"sales", "collections"}: return _has_any(text, SALES_WORDS | FINANCE_WORDS)
    if capability == "supplier": return _has_any(text, PROCUREMENT_WORDS | STOCK_WORDS)
    if capability in {"finance_ops", "expense", "imprest_open"}: return _has_any(text, FINANCE_WORDS)
    if capability == "bills": return _has_any(text, BILLS_WORDS)
    if capability == "daily_close": return _has_any(text, DAILY_CLOSE_WORDS)
    if capability == "compliance": return _has_any(text, COMPLIANCE_WORDS)
    if capability == "stock": return _has_any(text, STOCK_WORDS | PROCUREMENT_WORDS)
    if capability == "payroll": return _has_any(text, PAYROLL_WORDS)
    if capability == "money_in": return _has_any(text, MONEY_IN_WORDS)
    return False


def operational_context(user):
    capabilities = ("crm", "sales", "collections", "supplier", "finance_ops", "expense", "imprest_open", "daily_close", "bills", "compliance", "stock", "payroll", "money_in")
    result = {name: can_operate(user, name) for name in capabilities}
    result.update({
        "owner_observer": is_organization_owner_observer(user),
        "individual_owner": bool(getattr(user, "role", None) == "owner" and is_individual_workspace(user)),
        "workspace_mode": "individual" if is_individual_workspace(user) else "organization",
    })
    return result


def require_operational(user, capability, label=None):
    if not can_operate(user, capability):
        action = label or capability.replace("_", " ")
        if is_organization_owner_observer(user):
            raise PermissionError(f"Organization owners have oversight access here. Delegate {action} to the responsible staff member; SAGE will show the resulting record in your management view.")
        raise PermissionError(f"Your role or department is not assigned to {action}.")
    return True
