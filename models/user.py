# MODEL: User
# Stores organization owners, admins, department heads and staff with secure password hashes and profile information.

import uuid
from datetime import date, datetime, timezone
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from packages.database import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    first_name = db.Column(db.String(80), nullable=False)
    middle_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=False)
    sex = db.Column(db.String(20), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(190), unique=True, nullable=False, index=True)
    address = db.Column(db.String(255), nullable=True)
    employee_id = db.Column(db.String(80), nullable=True)
    position = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(40), nullable=False, default="staff", index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    organization = db.relationship("Organization", back_populates="users")
    department = db.relationship("Department", back_populates="users")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def display_name(self):
        return " ".join(part for part in [self.first_name, self.middle_name, self.last_name] if part)

    @property
    def initials(self):
        return f"{self.first_name[:1]}{self.last_name[:1]}".upper()

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))

    @property
    def role_label(self):
        return self.role.replace("_", " ").title()
