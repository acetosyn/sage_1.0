# SERVICE: SAGE Department Management
# Database-backed helpers for owner/admin department creation and department-scoped views.

import re
from packages.database import db
from models import AuditLog, Department


def create_department(user, payload):
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("Department name is required.")
    existing = Department.query.filter(db.func.lower(Department.name) == name.lower(), Department.organization_id == user.organization_id).first()
    if existing:
        raise ValueError("A department with that name already exists.")
    code = (payload.get("code") or "").strip().upper() or re.sub(r"[^A-Z0-9]", "", "".join(word[:1] for word in name.upper().split()))[:8]
    department = Department(organization_id=user.organization_id, name=name, code=code or None, description=(payload.get("description") or "").strip() or None)
    db.session.add(department)
    db.session.flush()
    db.session.add(AuditLog(organization_id=user.organization_id, user_id=user.id, action="department_created", description=f"{user.display_name} created the {department.name} department."))
    db.session.commit()
    return department
