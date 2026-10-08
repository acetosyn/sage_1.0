# SERVICE: SAGE Authentication / Onboarding
# Creates the first owner workspace, suggested departments, staff invitations and staff accounts.

import re
from datetime import date, datetime, timezone
from sqlalchemy import func
from packages.database import db
from models import AuditLog, Department, Organization, OrganizationWorkspace, PlatformOwnerControl, StaffInvitation, User
from services.organization_catalog import BUSINESS_TYPE_MAP, canonical_business_for_individual, suggested_departments


# ==========================================================
# GENERAL HELPERS
# ==========================================================

def clean_email(value):
    return (value or "").strip().lower()


def parse_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def unique_slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", (name or "vision").lower()).strip("-") or "vision"
    slug, index = base, 2
    while Organization.query.filter_by(slug=slug).first():
        slug, index = f"{base}-{index}", index + 1
    return slug


def create_audit(organization_id, user_id, action, description):
    db.session.add(AuditLog(organization_id=organization_id, user_id=user_id, action=action, description=description))


# ==========================================================
# OWNER REGISTRATION
# ==========================================================

def register_owner(payload):
    email = clean_email(payload.get("email"))
    if not email or User.query.filter(func.lower(User.email) == email).first(): raise ValueError("That email address is already registered.")
    if len(payload.get("password") or "") < 8: raise ValueError("Password must contain at least 8 characters.")

    workspace_mode = str(payload.get("workspace_mode") or "organization").strip().lower()
    if workspace_mode not in {"organization", "individual"}: workspace_mode = "organization"
    if workspace_mode == "individual":
        individual = canonical_business_for_individual(payload.get("individual_business_type")); business_key = individual["catalog_key"]; business = BUSINESS_TYPE_MAP.get(business_key, BUSINESS_TYPE_MAP["other"]); business_category_key, business_category_label, primary_department_name = individual["key"], individual["label"], individual["primary_department"]
    else:
        business_key = (payload.get("business_type") or "other").strip(); business = BUSINESS_TYPE_MAP.get(business_key, BUSINESS_TYPE_MAP["other"]); business_category_key, business_category_label, primary_department_name = business_key, business["label"], None

    org_name = (payload.get("organization_name") or "").strip()
    if not org_name: raise ValueError("Business / organization name is required.")
    branch_count = 1 if workspace_mode == "individual" else max(1, int(payload.get("branch_count") or 1))
    employee_range = (payload.get("employee_range") or ("1-2" if workspace_mode == "individual" else "")).strip() or None
    organization = Organization(name=org_name, slug=unique_slug(org_name), business_type=business["label"], country=(payload.get("country") or "Nigeria").strip(), state=(payload.get("state") or "").strip() or None, address=(payload.get("organization_address") or "").strip() or None, currency=(payload.get("currency") or "NGN").strip(), employee_range=employee_range, branch_count=branch_count)
    db.session.add(organization); db.session.flush(); db.session.add(PlatformOwnerControl(organization_id=organization.id, status="active", plan="standard", subscription_status="trial")); db.session.add(OrganizationWorkspace(organization_id=organization.id, workspace_mode=workspace_mode, business_category_key=business_category_key, business_category_label=business_category_label, catalog_key=business_key, primary_department_name=primary_department_name))

    chosen_departments = ([primary_department_name] if workspace_mode == "individual" else (payload.get("departments") or suggested_departments(business_key))); seen, first_department = set(), None
    for name in chosen_departments:
        name = str(name or "").strip(); normalized = name.lower()
        if name and normalized not in seen:
            seen.add(normalized); department = Department(organization_id=organization.id, name=name, code=re.sub(r"[^A-Z0-9]", "", "".join(word[:1] for word in name.upper().split()))[:8] or None, description="Primary owner-operated business area" if workspace_mode == "individual" and first_department is None else None); db.session.add(department); db.session.flush(); first_department = first_department or department

    owner = User(organization_id=organization.id, department_id=first_department.id if workspace_mode == "individual" and first_department else None, first_name=(payload.get("first_name") or "").strip(), middle_name=(payload.get("middle_name") or "").strip() or None, last_name=(payload.get("last_name") or "").strip(), sex=(payload.get("sex") or "").strip() or None, date_of_birth=parse_date(payload.get("date_of_birth")), phone=(payload.get("phone") or "").strip() or None, email=email, address=(payload.get("address") or "").strip() or None, position="Business Owner" if workspace_mode == "individual" else "Organization Owner", role="owner", status="active")
    if not owner.first_name or not owner.last_name: raise ValueError("First name and last name are required.")
    owner.set_password(payload.get("password")); db.session.add(owner); db.session.flush(); create_audit(organization.id, owner.id, "owner_registered", f"{owner.display_name} created a SAGE {workspace_mode} workspace."); db.session.commit(); return owner


# ==========================================================
# LOGIN
# ==========================================================

def authenticate(email, password):
    user = User.query.filter(func.lower(User.email) == clean_email(email)).first()
    if not user or not user.check_password(password or ""): return None
    if user.status != "active": raise ValueError("This account is not active. Please contact your organization administrator.")
    from services.platform_service import organization_access_status
    workspace_status, _ = organization_access_status(user.organization_id)
    if workspace_status in {"disabled", "restricted"}: raise ValueError("This organization workspace is disabled. Please contact SAGE support.")
    if workspace_status == "deleted": raise ValueError("This organization workspace is no longer active. Please contact SAGE support.")
    user.last_login_at = datetime.now(timezone.utc)
    create_audit(user.organization_id, user.id, "login", f"{user.display_name} signed in to SAGE.")
    db.session.commit()
    return user


def change_password(email, current_password, new_password):
    """Allow an account holder to rotate only their password; the email/login identifier is never changed here."""
    user = User.query.filter(func.lower(User.email) == clean_email(email)).first()
    if not user or not user.check_password(current_password or ""): raise ValueError("The email address or current password is incorrect.")
    if user.status != "active": raise ValueError("This account is not active. Please contact your organization administrator.")
    if len(new_password or "") < 8: raise ValueError("New password must contain at least 8 characters.")
    if user.check_password(new_password or ""): raise ValueError("Choose a new password that is different from your current password.")
    user.set_password(new_password); create_audit(user.organization_id, user.id, "password_changed", f"{user.display_name} changed their SAGE sign-in password."); db.session.commit(); return user


# ==========================================================
# STAFF INVITATION / REGISTRATION
# ==========================================================

def create_staff_invitation(owner, payload):
    email = clean_email(payload.get("email"))
    if not email:
        raise ValueError("Staff email address is required.")
    if User.query.filter(func.lower(User.email) == email).first():
        raise ValueError("A user with this email is already registered.")
    department = Department.query.filter_by(id=payload.get("department_id"), organization_id=owner.organization_id, is_active=True).first()
    if not department:
        raise ValueError("Select a valid department.")
    role = (payload.get("role") or "staff").strip().lower()
    if role not in {"admin", "finance", "procurement", "department_head", "staff"}:
        role = "staff"

    invitation = StaffInvitation(organization_id=owner.organization_id, department_id=department.id, invited_by_id=owner.id, email=email, first_name=(payload.get("first_name") or "").strip() or None, last_name=(payload.get("last_name") or "").strip() or None, role=role)
    db.session.add(invitation)
    db.session.flush()
    create_audit(owner.organization_id, owner.id, "staff_invited", f"Invitation created for {email} in {department.name}.")
    db.session.commit()
    return invitation


def register_staff(invitation, payload):
    if not invitation or not invitation.is_valid:
        raise ValueError("This staff registration link is invalid or has expired.")
    if User.query.filter(func.lower(User.email) == invitation.email.lower()).first():
        raise ValueError("This email address is already registered.")
    if len(payload.get("password") or "") < 8:
        raise ValueError("Password must contain at least 8 characters.")

    user = User(organization_id=invitation.organization_id, department_id=invitation.department_id, first_name=(payload.get("first_name") or invitation.first_name or "").strip(), middle_name=(payload.get("middle_name") or "").strip() or None, last_name=(payload.get("last_name") or invitation.last_name or "").strip(), sex=(payload.get("sex") or "").strip() or None, date_of_birth=parse_date(payload.get("date_of_birth")), phone=(payload.get("phone") or "").strip() or None, email=invitation.email, address=(payload.get("address") or "").strip() or None, employee_id=(payload.get("employee_id") or "").strip() or None, position=(payload.get("position") or "").strip() or None, role=invitation.role, status="active")
    if not user.first_name or not user.last_name:
        raise ValueError("First name and last name are required.")
    user.set_password(payload.get("password"))
    invitation.status = "accepted"
    db.session.add(user)
    db.session.flush()
    create_audit(user.organization_id, user.id, "staff_registered", f"{user.display_name} joined {user.department.name if user.department else 'the organization'}.")
    db.session.commit()
    return user
