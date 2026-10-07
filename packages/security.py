# MODULE: SAGE Authentication Security
# Flask-Login setup, tenant/workspace blocking and role helpers used by routes and templates.

from functools import wraps
from flask import abort
from flask_login import LoginManager, current_user

login_manager = LoginManager(); login_manager.login_view = "login"; login_manager.login_message = "Please sign in to continue."; login_manager.login_message_category = "info"


# ==========================================================
# LOGIN MANAGER / WORKSPACE STATUS FIREWALL
# ==========================================================

def init_security(app):
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        # Suspended/removed staff and restricted/deleted organization workspaces are invalidated on the next request.
        from models import User
        from services.platform_service import organization_is_accessible
        user = User.query.filter_by(id=user_id).first()
        if not user or user.status != "active" or not organization_is_accessible(user.organization_id): return None
        return user


# ==========================================================
# ROLE GUARDS
# ==========================================================

def roles_required(*allowed_roles):
    """Restrict a route to one or more SAGE roles."""
    allowed = {role.lower() for role in allowed_roles}
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role.lower() not in allowed: abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
