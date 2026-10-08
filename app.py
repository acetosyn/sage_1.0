# MODULE: SAGE Main Application
# Flask entry point for SAGE authentication, strict tenant isolation, platform administration, PostgreSQL, RBAC, SPA pages, live activity, requests/approvals, procurement evidence, inventory, finance and AI.

import csv
import io
import click
import json
import os
import re
import time
import hmac
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, unquote
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_file, send_from_directory, session, stream_with_context, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_

from core.config import Config
from packages.database import db, init_database
from packages.security import init_security, roles_required
from services.access_control import allowed_pages, can_access_page, filter_navigation, is_owner_admin
from services.ai_service import ask_vision_ai
from services.auth_service import authenticate, change_password, create_staff_invitation, register_owner, register_staff
from services.department_capabilities import department_profile, role_focus
from services.department_service import create_department
from services.department_operations import acknowledge_staff_report, create_department_operation, department_operations_profile, generate_staff_report, report_metrics
from services.finance_service import create_budget, create_finance_account, create_forecast, create_payable, create_payroll, create_receivable, create_reconciliation, create_tax, finance_control_context, post_ledger_entry, settle_payable, settle_receivable
from services.demo_data import NAV_ITEMS, PAGE_TITLES
from services.notification_service import notification_route, notify_user, record_activity
from services.operations_service import FINANCE_TYPES, add_financial_record, analytics_context, create_request, decide_request, finance_summary, move_asset, move_stock, next_asset_tag, owner_dashboard_context, save_fulfillment, save_request_funding, scoped_department, verify_fulfillment
from services.organization_catalog import BUSINESS_TYPES, INDIVIDUAL_BUSINESS_TYPES
from services.item_catalog import department_catalog, organization_catalog_summary
from services.platform_service import get_control, organization_rows, permanent_delete_organization, platform_summary, record_platform_admin, update_control
from services.reporting_service import management_export_rows, reporting_context
from services.export_service import build_report_export
from services.management_service import assign_department_to_branch, audit_revision_context, branch_comparison_context, can_actor_approve_request, create_approval_rule, create_branch, executive_dashboard_context, management_anomaly_context, management_settings_context, procurement_management_context
from services.briefing_service import build_daily_briefing
from services.push_service import disable_subscription, public_push_config, push_enabled, save_subscription
from services.production_service import apply_retention_policy, apply_security_headers, health_snapshot, install_proxy_support, production_warnings
from services.storage_service import attachment_response
from services.workspace_service import individual_dashboard_context, request_management_context, workspace_profile_context
from services.owner_control_service import scoped_finance_summary
from services.income_service import income_export_rows, income_workspace_context
from services.expense_service import expense_export_rows, expense_workspace_context
from services.performance_service import performance_target_context, save_performance_target
from services.attention_service import attention_additions
from services.audit_service import install_audit_tracking
from modules.control_routes import register_control_routes

# ==========================================================
# PATHS / FLASK APPLICATION
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR, TEMPLATE_DIR = BASE_DIR / "static", BASE_DIR / "templates"
app = Flask(__name__, static_folder=str(STATIC_DIR), template_folder=str(TEMPLATE_DIR)); app.config.from_object(Config)
app.secret_key = os.getenv("SECRET_KEY", app.config.get("SECRET_KEY", "sage-development-secret")); install_proxy_support(app)

# ==========================================================
# SAGE STRICT TEMPLATE / STATIC CACHE PROTECTION
# Changed HTML/CSS/JS should appear immediately after deployment without Ctrl+F5 or manual ?v= edits.
# ==========================================================

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0; app.config["TEMPLATES_AUTO_RELOAD"] = True; app.jinja_env.auto_reload = True
STARTUP_VERSION = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"); ASSET_VERSION = os.getenv("ASSET_VERSION", "").strip() or STARTUP_VERSION

def _static_root_for_endpoint(endpoint):
    """Resolve the physical static folder for the main app or a Blueprint static endpoint."""
    if endpoint == "static":
        try: return Path(app.static_folder).resolve()
        except Exception: return STATIC_DIR.resolve()
    if str(endpoint or "").endswith(".static"):
        blueprint = app.blueprints.get(str(endpoint).rsplit(".", 1)[0])
        if blueprint and blueprint.static_folder:
            try:
                static_path = Path(blueprint.static_folder); static_path = static_path if static_path.is_absolute() else Path(blueprint.root_path) / static_path; return static_path.resolve()
            except Exception: pass
    return None

def _safe_asset_path(static_root, filename):
    """Resolve a static file safely while preventing ../ traversal outside its static directory."""
    if not static_root: return None
    filename = str(filename or "").strip().replace("\\", "/").lstrip("/")
    if not filename: return None
    try:
        root = Path(static_root).resolve(); candidate = (root / filename).resolve(); candidate.relative_to(root); return candidate
    except Exception: return None

def static_asset_version(filename, endpoint="static"):
    """Return a per-file version based on deployment version + nanosecond mtime + file size."""
    asset_path = _safe_asset_path(_static_root_for_endpoint(endpoint), filename)
    if asset_path:
        try:
            stat = asset_path.stat(); return f"{ASSET_VERSION}-{int(stat.st_mtime_ns)}-{int(stat.st_size)}"
        except OSError: pass
    return ASSET_VERSION

def versioned_template_url_for(endpoint, **values):
    """Jinja url_for replacement: static assets automatically receive the current per-file ?v= token."""
    endpoint = str(endpoint or "")
    if endpoint == "static" or endpoint.endswith(".static"):
        filename = str(values.get("filename") or "").strip(); values["v"] = static_asset_version(filename, endpoint) if filename else ASSET_VERSION
    return url_for(endpoint, **values)

app.jinja_env.globals["url_for"] = versioned_template_url_for; app.jinja_env.globals["ASSET_VERSION"] = ASSET_VERSION; app.jinja_env.globals["static_asset_version"] = static_asset_version

# Protect legacy/hardcoded HTML such as <script src="/static/js/vision.js"> that bypasses Jinja url_for.
STATIC_HTML_ATTRIBUTE_RE = re.compile(r'(?P<prefix>\b(?:src|href|poster)\s*=\s*["\'])(?P<url>[^"\']*?/static/[^"\']+)(?P<suffix>["\'])', flags=re.IGNORECASE)

def _version_static_url(raw_url):
    raw_url = str(raw_url or "").strip()
    if not raw_url: return raw_url
    try:
        parts = urlsplit(raw_url)
        if parts.netloc and parts.netloc.lower() != request.host.lower(): return raw_url
        marker, path = "/static/", parts.path or ""; marker_index = path.find(marker)
        if marker_index < 0: return raw_url
        filename = unquote(path[marker_index + len(marker):]).strip()
        if not filename: return raw_url
        query_items = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key.lower() != "v"]; query_items.append(("v", static_asset_version(filename, "static")))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))
    except Exception: return raw_url

def rewrite_static_urls_in_html(html):
    """Automatically add current versions to hardcoded same-origin /static/... src/href/poster references."""
    if not html or "/static/" not in html: return html
    return STATIC_HTML_ATTRIBUTE_RE.sub(lambda match: match.group("prefix") + _version_static_url(match.group("url")) + match.group("suffix"), html)

def _set_no_store_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"; response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"; response.headers["Surrogate-Control"] = "no-store"; return response

def _set_static_revalidation_headers(response):
    response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"; response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"; return response

def _set_code_asset_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"; response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"; response.headers["Surrogate-Control"] = "no-store"; return response

# Optional distributed-aware rate limiting. SAGE still boots if Flask-Limiter is not installed yet.
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address, app=app, storage_uri=app.config.get("RATELIMIT_STORAGE_URI", "memory://"), default_limits=["600 per minute"], headers_enabled=True)
except ImportError:
    limiter = None

def rate_limit(rule): return limiter.limit(rule) if limiter else (lambda view: view)

# ==========================================================
# DATABASE / SECURITY BOOTSTRAP
# ==========================================================

database_label = init_database(app); init_security(app)
from models import ActivityEvent, AssetItem, AssetMovement, Attachment, BudgetAllocation, CatalogItem, Department, DepartmentOperation, FinanceAccount, FinanceForecast, FinanceLedgerEntry, FinancePayable, FinanceReceivable, FinanceReconciliation, FinancialRecord, FulfillmentLine, InventoryItem, Notification, Organization, OrganizationWorkspace, PayrollEntry, PlatformAdminAudit, PlatformOwnerControl, PurchaseRequest, RequestFunding, StaffInvitation, StaffReport, StockMovement, TaxEntry, User, PushSubscription, Supplier, BranchLocation, BranchDepartment, ApprovalRule  # noqa: E402

with app.app_context():
    Path(app.config["STORAGE_DIR"]).mkdir(parents=True, exist_ok=True); db.create_all() if app.config.get("AUTO_CREATE_SCHEMA", True) else None; PlatformOwnerControl.query.filter(PlatformOwnerControl.status.in_(["restricted", "deleted"])).update({"status": "disabled"}, synchronize_session=False); db.session.commit(); print(f"[SAGE] Database backend: {app.extensions.get('vision_database_label', database_label)}")
    for warning in production_warnings(app): app.logger.warning("PRODUCTION CHECK: %s", warning)

install_audit_tracking(app)
register_control_routes(app)

@app.before_request
def bind_audit_actor():
    db.session.info["sage_actor_id"] = current_user.id if current_user.is_authenticated else None

# ==========================================================
# SHARED PAGE CONTEXT / TENANT SCOPING
# ==========================================================

PAGES = set(PAGE_TITLES.keys())

# ==========================================================
# STRICT TENANT SESSION / CACHE FIREWALL
# Prevents stale HTML/API content or a mismatched browser session from leaking data between organization workspaces.
# ==========================================================

@app.before_request
def enforce_tenant_session():
    if request.path.startswith("/platform-admin"): return None
    if current_user.is_authenticated:
        current_org = str(current_user.organization_id); bound_org = session.get("sage_tenant_org_id")
        if bound_org and str(bound_org) != current_org:
            logout_user(); session.pop("sage_tenant_org_id", None)
            return json_error("Your organization session changed. Please sign in again.", 401) if request.path.startswith(("/api/", "/partial/")) else redirect(url_for("login"))
        session["sage_tenant_org_id"] = current_org
    return None

@app.after_request
def apply_private_cache_policy(response):
    """SAGE cache firewall: no stale HTML/API/SSE, strict JS/CSS protection, versioned static links and security headers."""
    try:
        request_path, mimetype = str(request.path or ""), str(response.mimetype or "").lower()

        # HTML: rewrite any hardcoded /static/... URLs and never reuse stale authenticated/public pages.
        if mimetype == "text/html":
            if response.status_code == 200 and not response.direct_passthrough:
                try:
                    html = response.get_data(as_text=True); rewritten = rewrite_static_urls_in_html(html); response.set_data(rewritten) if rewritten != html else None
                except Exception as error: app.logger.warning("SAGE CACHE HTML rewrite warning: %s", error)
            _set_no_store_headers(response); vary = response.headers.get("Vary", ""); response.headers["Vary"] = f"{vary}, Cookie".strip(", ") if "cookie" not in vary.lower() else vary

        # API / SPA partials / platform admin / live SSE: all are session- or data-sensitive and must never be stale.
        elif mimetype in {"application/json", "text/event-stream"} or request_path.startswith(("/api/", "/partial/", "/platform-admin")):
            _set_no_store_headers(response); vary = response.headers.get("Vary", ""); response.headers["Vary"] = f"{vary}, Cookie".strip(", ") if "cookie" not in vary.lower() else vary

        # Main static path: executable CSS/JS is never reused stale; images/fonts must revalidate.
        elif request_path.startswith("/static/"):
            _set_code_asset_headers(response) if Path(request_path).suffix.lower() in {".js", ".css", ".mjs"} else _set_static_revalidation_headers(response)

        # Root service-worker / manifest routes also revalidate so deployment updates propagate promptly.
        elif request_path in {"/sw.js", "/manifest.webmanifest"}:
            _set_code_asset_headers(response) if request_path.endswith(".js") else _set_static_revalidation_headers(response)
    except Exception as error:
        app.logger.warning("SAGE CACHE response policy warning: %s", error)
    return apply_security_headers(app, response)

def _requests_for_user(user, limit=100):
    query = PurchaseRequest.query.filter_by(organization_id=user.organization_id)
    if user.role not in {"owner", "admin", "finance", "procurement"}: query = query.filter(PurchaseRequest.department_id == user.department_id) if user.department_id else query.filter(PurchaseRequest.requester_id == user.id)
    return query.order_by(PurchaseRequest.created_at.desc()).limit(limit).all()

def _inventory_for_user(user):
    query = InventoryItem.query.filter_by(organization_id=user.organization_id)
    if user.role not in {"owner", "admin", "finance", "procurement"}: query = query.filter(InventoryItem.department_id == user.department_id) if user.department_id else query.filter(InventoryItem.added_by_id == user.id)
    return query.order_by(InventoryItem.updated_at.desc()).all()


def _assets_for_user(user):
    query = AssetItem.query.filter_by(organization_id=user.organization_id)
    if user.role not in {"owner", "admin", "finance", "procurement"}: query = query.filter(AssetItem.department_id == user.department_id) if user.department_id else query.filter(AssetItem.custodian_user_id == user.id)
    return query.order_by(AssetItem.updated_at.desc()).all()


def _asset_movements_for_user(user, limit=80):
    query = AssetMovement.query.filter_by(organization_id=user.organization_id)
    if user.role not in {"owner", "admin", "finance", "procurement"}: query = query.filter(or_(AssetMovement.source_department_id == user.department_id, AssetMovement.destination_department_id == user.department_id))
    return query.order_by(AssetMovement.created_at.desc()).limit(limit).all()

def _stock_movements_for_user(user, limit=80):
    query = StockMovement.query.join(InventoryItem, StockMovement.inventory_item_id == InventoryItem.id).filter(StockMovement.organization_id == user.organization_id)
    if user.role not in {"owner", "admin", "finance", "procurement"}: query = query.filter(InventoryItem.department_id == user.department_id) if user.department_id else query.filter(InventoryItem.added_by_id == user.id)
    return query.order_by(StockMovement.created_at.desc()).limit(limit).all()

def _activity_for_user(user, limit=100):
    query = ActivityEvent.query.filter_by(organization_id=user.organization_id)
    if user.role not in {"owner", "admin", "finance"}: query = query.filter(ActivityEvent.department_id == user.department_id) if user.department_id else query.filter(ActivityEvent.actor_id == user.id)
    return query.order_by(ActivityEvent.created_at.desc()).limit(limit).all()

def page_context(page):
    """Build tenant-aware real database context for both full-shell and SPA partial rendering."""
    if page not in PAGES: abort(404)
    if not can_access_page(current_user, page): abort(403)
    title, subtitle = PAGE_TITLES[page]; owner_admin = is_owner_admin(current_user)
    organization_departments = Department.query.filter_by(organization_id=current_user.organization_id, is_active=True).order_by(Department.name.asc()).all(); departments = organization_departments if owner_admin else ([current_user.department] if current_user.department else [])
    all_staff = User.query.filter_by(organization_id=current_user.organization_id).order_by(User.created_at.desc()).all() if owner_admin else [current_user]
    staff_users = [user for user in all_staff if user.status != "deleted"]; archived_staff_users = [user for user in all_staff if user.status == "deleted"]
    staff_stats = {"total": len(all_staff), "active": sum(1 for user in all_staff if user.status == "active"), "suspended": sum(1 for user in all_staff if user.status == "suspended"), "deleted": len(archived_staff_users), "departments": len({user.department_id for user in all_staff if user.department_id})}
    live_requests, inventory_items, asset_items, activity_events = _requests_for_user(current_user, None if page == "requests" else 100), _inventory_for_user(current_user), _assets_for_user(current_user), _activity_for_user(current_user)
    count_query = db.session.query(PurchaseRequest.status, func.count(PurchaseRequest.id)).filter(PurchaseRequest.organization_id == current_user.organization_id)
    if current_user.role not in {"owner", "admin", "finance", "procurement"}:
        count_query = count_query.filter(PurchaseRequest.department_id == current_user.department_id) if current_user.department_id else count_query.filter(PurchaseRequest.requester_id == current_user.id)
    counted = dict(count_query.group_by(PurchaseRequest.status).all())
    request_counts = {status: counted.get(status,0) for status in {"draft", "submitted", "approved", "money_sent", "fulfilled", "verified", "rejected"}}
    request_counts["completed"] = request_counts["fulfilled"] + request_counts["verified"]
    attachments = Attachment.query.filter_by(organization_id=current_user.organization_id, entity_type="fulfillment").order_by(Attachment.created_at.desc()).all(); fulfillment_attachments, fulfillment_evidence = {}, {}
    for attachment in attachments:
        fulfillment_attachments.setdefault(attachment.entity_id, attachment); fulfillment_evidence.setdefault(attachment.entity_id, {}).setdefault(attachment.kind, attachment)
    custom_catalog_query = CatalogItem.query.filter_by(organization_id=current_user.organization_id); custom_catalog_query = custom_catalog_query.filter_by(department_id=current_user.department_id) if current_user.department_id and not owner_admin else custom_catalog_query
    custom_catalog_items = custom_catalog_query.order_by(CatalogItem.created_at.desc()).all(); department_name = current_user.department.name if current_user.department else ""; department_catalog_info = department_catalog(current_user.organization.business_type, department_name, custom_catalog_items if current_user.department_id else []) if department_name else {"business_name": current_user.organization.business_type, "matched_department": None, "requested_department": "", "items": [], "groups": [], "count": 0, "custom_count": 0, "matched": False}
    request_catalog_items = department_catalog_info["items"][:240] if department_catalog_info["items"] else [{"name": item.name, "category": item.category, "unit": item.unit, "icon": "inventory", "is_custom": True} for item in custom_catalog_items[:120]]
    workspace_profile_data = department_profile(department_name); permitted_pages = allowed_pages(current_user); workspace_profile_data["tools"] = [tool for tool in workspace_profile_data.get("tools", []) if tool.get("action") == "request" or tool.get("route") in permitted_pages]
    operation_query = DepartmentOperation.query.filter_by(organization_id=current_user.organization_id); operation_query = operation_query if owner_admin else operation_query.filter_by(department_id=current_user.department_id); department_operations = operation_query.order_by(DepartmentOperation.occurred_at.desc()).limit(120).all()
    report_query = StaffReport.query.filter_by(organization_id=current_user.organization_id); report_query = report_query.order_by(StaffReport.created_at.desc()) if owner_admin else report_query.filter_by(user_id=current_user.id).order_by(StaffReport.created_at.desc()); staff_reports = report_query.limit(100).all()
    today_report_metrics = report_metrics(current_user, "daily") if not owner_admin else None; week_report_metrics = report_metrics(current_user, "weekly") if not owner_admin else None; month_report_metrics = report_metrics(current_user, "monthly") if not owner_admin else None; quarter_report_metrics = report_metrics(current_user, "quarterly") if not owner_admin else None
    operation_templates = department_operations_profile(department_name) if department_name else []
    if "operations" in permitted_pages and not any(tool.get("route") == "operations" for tool in workspace_profile_data.get("tools", [])): workspace_profile_data.setdefault("tools", []).insert(0, {"label":"Department Operations","detail":"Record job-specific work, usage, incidents, movements and accountable activity.","icon":workspace_profile_data.get("icon","briefcase"),"route":"operations"})
    if "reports" in permitted_pages and not any(tool.get("route") == "reports" for tool in workspace_profile_data.get("tools", [])): workspace_profile_data.setdefault("tools", []).append({"label":"My Activity Reports","detail":"Generate daily, weekly, monthly or quarterly reports from your real SAGE activity.","icon":"reports","route":"reports"})
    sage_workspace = workspace_profile_context(current_user.organization); individual_business = individual_dashboard_context(current_user) if current_user.role == "owner" and sage_workspace["is_individual"] and page == "dashboard" else None; request_management = request_management_context(current_user, live_requests) if owner_admin and page in {"dashboard", "requests"} else None; executive_management = executive_dashboard_context(current_user) if owner_admin and page == "dashboard" else None
    if executive_management:
        executive_management["attention"].extend(attention_additions(current_user))
        executive_management["attention"].sort(key=lambda item:item["rank"], reverse=True)
        executive_management["attention_count"] = len(executive_management["attention"])
    # SAGE PULSE BOOTSTRAP: build the once-per-login recap on the server for full page loads so the visible Pulse does not depend only on a delayed browser fetch.
    briefing_token = str(session.get("sage_daily_briefing_token") or ""); briefing_ack = str(session.get("sage_daily_briefing_ack") or ""); boot_briefing = None
    if request.headers.get("X-Sage-Partial") != "1" and briefing_token and briefing_ack != briefing_token:
        try: boot_briefing = {"show": True, "briefing_token": briefing_token, **build_daily_briefing(current_user)}
        except Exception as exc: app.logger.warning("SAGE Pulse bootstrap skipped: %s", exc)
    context = {"page": page, "page_title": title, "page_subtitle": subtitle, "nav_items": filter_navigation(NAV_ITEMS, current_user), "departments": departments, "organization_departments": organization_departments, "asset_custodians": User.query.filter_by(organization_id=current_user.organization_id, status="active").order_by(User.first_name.asc(), User.last_name.asc()).all(), "staff_users": staff_users, "archived_staff_users": archived_staff_users, "staff_stats": staff_stats, "owner_admin": owner_admin, "business_types": BUSINESS_TYPES, "live_requests": live_requests, "request_counts": request_counts, "inventory_items": inventory_items, "asset_items": asset_items, "asset_value": sum(item.total_value for item in asset_items), "asset_movements": _asset_movements_for_user(current_user), "stock_movements": _stock_movements_for_user(current_user), "granted_requests": [row for row in live_requests if row.status in {"approved", "money_sent", "fulfilled", "verified"}], "activity_events": activity_events, "fulfillment_attachments": fulfillment_attachments, "fulfillment_evidence": fulfillment_evidence, "finance_summary": finance_summary(current_user.organization_id), "catalog_items": custom_catalog_items, "request_catalog_items": request_catalog_items, "department_catalog": department_catalog_info, "organization_catalog": organization_catalog_summary(current_user.organization.business_type), "notifications": Notification.query.filter_by(organization_id=current_user.organization_id, user_id=current_user.id).order_by(Notification.created_at.desc()).limit(12).all(), "unread_notifications": Notification.query.filter_by(organization_id=current_user.organization_id, user_id=current_user.id, is_read=False).count(), "workspace_profile": workspace_profile_data, "role_focus": role_focus(current_user.position or current_user.role_label, department_name), "finance_types": sorted(FINANCE_TYPES), "operation_templates": operation_templates, "department_operations": department_operations, "staff_reports": staff_reports, "today_report_metrics": today_report_metrics, "week_report_metrics": week_report_metrics, "month_report_metrics": month_report_metrics, "quarter_report_metrics": quarter_report_metrics, "finance_control": finance_control_context(current_user) if page in {"finance", "income", "expenses"} and current_user.role in {"owner", "admin", "finance"} else None, "income_workspace": income_workspace_context(current_user) if page == "income" or (page == "dashboard" and owner_admin) else None, "expense_workspace": expense_workspace_context(current_user) if page == "expenses" else None, "performance_targets": performance_target_context(current_user) if page in {"income", "dashboard"} and owner_admin else None, "reporting": reporting_context(current_user) if page == "reports" else None, "financial_intelligence": reporting_context(current_user) if page in {"dashboard", "requests", "fulfillment"} else None, "push_enabled": push_enabled(app), "sage_workspace": sage_workspace, "workspace_mode": sage_workspace["mode"], "individual_business": individual_business, "request_management": request_management, "executive_management": executive_management, "procurement_management": procurement_management_context(current_user) if page == "procurement" and owner_admin else None, "management_settings": management_settings_context(current_user) if page == "settings" and owner_admin else None, "branch_management": branch_comparison_context(current_user) if page == "reports" and owner_admin else None, "audit_revisions": audit_revision_context(current_user) if page == "audit" and owner_admin else None, "management_anomalies": management_anomaly_context(current_user) if page in {"analytics", "audit"} and owner_admin else None, "boot_briefing": boot_briefing}
    context.update(owner_dashboard_context(current_user)); context.update({"analytics": analytics_context(current_user), "staff_finance": scoped_finance_summary(current_user), "approval_permissions": {row.id: can_actor_approve_request(current_user, row)[0] for row in live_requests if row.status == 'submitted'}}); return context

def render_vision_page(page): return render_template("app_shell.html", **page_context(page))
def json_error(message, status=400): return jsonify({"ok": False, "message": str(message)}), status

def _get_request_or_404(request_id):
    row = PurchaseRequest.query.filter_by(id=request_id, organization_id=current_user.organization_id).first()
    if not row: abort(404)
    if current_user.role not in {"owner", "admin", "finance", "procurement"} and row.department_id != current_user.department_id: abort(403)
    return row


def _staff_target_or_404(user_id):
    """Return one staff account inside the signed-in owner's organization; cross-tenant IDs are never exposed."""
    row = User.query.filter_by(id=user_id, organization_id=current_user.organization_id).first()
    if not row: abort(404)
    return row

# ==========================================================
# SAGE PLATFORM ADMIN AUTHENTICATION / OWNER MANAGEMENT
# Developer-only area is independent from organization owner/staff authentication.
# ==========================================================

def _platform_admin_authenticated(): return bool(session.get("sage_platform_admin") is True)
def _platform_admin_username(): return str(session.get("sage_platform_admin_username") or app.config.get("PLATFORM_ADMIN_USERNAME") or "developer")

# ==========================================================
# PLATFORM FINANCIAL ACCOUNTABILITY TRACE
# Developer visibility is built from the same immutable tenant ActivityEvent stream used by Owner audit/notifications.
# No second financial ledger is created here; this is a forensic read-model showing who did what, where and when.
# ==========================================================

PLATFORM_FINANCIAL_ENTITIES = {"request", "fulfillment", "financial_record", "finance_account", "finance_ledger", "budget", "receivable", "payable", "reconciliation", "payroll", "tax", "forecast", "finance_performance_target", "direct_purchase"}
PLATFORM_FINANCIAL_ACTION_HINTS = ("finance_", "request_", "funding", "payment", "budget", "receivable", "payable", "reconcil", "payroll", "tax_", "forecast", "performance_target", "income", "expense", "revenue", "purchase", "fulfillment", "verified")

def _platform_is_financial_event(event):
    action, entity_type = str(event.action or "").lower(), str(event.entity_type or "").lower()
    return entity_type in PLATFORM_FINANCIAL_ENTITIES or any(token in action for token in PLATFORM_FINANCIAL_ACTION_HINTS)

def _platform_financial_category(event):
    action, title, details = str(event.action or "").lower(), str(event.title or "").lower(), (event.details_json or {})
    if "approve" in action or "reject" in action: return "approval"
    if "fund" in action or "money_sent" in action: return "funding"
    if "reconcil" in action: return "reconciliation"
    if "budget" in action or "target" in action: return "budget"
    if "receivable" in action or "payable" in action or "payment" in action: return "settlement"
    if details.get("direction") == "in" or "money in" in title or "income" in action or "revenue" in action: return "money_in"
    if details.get("direction") == "out" or "expense" in action or "payroll" in action or "tax" in action: return "money_out"
    return "financial"

def _platform_financial_rows(limit=220):
    candidates = ActivityEvent.query.order_by(ActivityEvent.created_at.desc()).limit(max(700, limit * 4)).all(); events = [row for row in candidates if _platform_is_financial_event(row)][:limit]
    org_ids = {row.organization_id for row in events}; organizations = {row.id: row for row in Organization.query.filter(Organization.id.in_(org_ids)).all()} if org_ids else {}; request_ids = {row.entity_id for row in events if row.entity_type == "request" and row.entity_id}; requests = {row.id: row for row in PurchaseRequest.query.filter(PurchaseRequest.id.in_(request_ids)).all()} if request_ids else {}; rows = []
    amount_keys = ("amount", "approved_budget", "amount_sent", "balance", "budget", "net_pay", "tax_amount", "variance")
    for event in events:
        details, actor, org = event.details_json or {}, event.actor, organizations.get(event.organization_id); amount = next((details.get(key) for key in amount_keys if details.get(key) not in (None, "")), None); reference = details.get("reference") or details.get("payment_reference") or details.get("external_reference") or (event.entity_id[:8].upper() if event.entity_id else "—"); category = _platform_financial_category(event); flag = "Tracked"
        request_row = requests.get(event.entity_id) if event.entity_type == "request" else None
        if request_row and "approve" in str(event.action or "").lower() and request_row.requester_id and request_row.requester_id == event.actor_id: flag = "SELF APPROVAL"
        currency = org.currency if org else "NGN"
        try: amount_label = f"{currency} {float(amount):,.2f}" if amount is not None else "—"
        except (TypeError, ValueError): amount_label = str(amount or "—")
        role = actor.role_label if actor else "System"; scope = "management" if actor and actor.role in {"owner", "admin"} else ("staff" if actor else "system")
        rows.append({"id": event.id, "organization": org.name if org else "Unknown organization", "actor_name": actor.display_name if actor else "System", "actor_role": role, "actor_scope": scope, "department": event.department.name if event.department else "Organization-wide", "action": str(event.action or "").replace("_", " ").title(), "title": event.title, "description": event.description or "", "category": category, "reference": reference, "amount_label": amount_label, "flag": flag, "ip_address": event.ip_address or "—", "user_agent": event.user_agent or "", "created_at": event.created_at})
    summary = {"total": len(rows), "management": sum(1 for row in rows if row["actor_scope"] == "management"), "staff": sum(1 for row in rows if row["actor_scope"] == "staff"), "approvals": sum(1 for row in rows if row["category"] in {"approval", "funding"})}
    return rows, summary

def _platform_activity_payload(row, organization_name=None):
    actor, details = row.actor, row.details_json or {}; org_name = organization_name or (actor.organization.name if actor and actor.organization else "Unknown organization")
    return {"id": row.id, "organization_id": row.organization_id, "organization": org_name, "title": row.title, "description": row.description or "", "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "details": details, "financial": _platform_is_financial_event(row), "financial_category": _platform_financial_category(row) if _platform_is_financial_event(row) else None, "created_at": row.created_at.isoformat(), "actor": actor.display_name if actor else "System", "actor_role": actor.role_label if actor else "System", "actor_scope": "management" if actor and actor.role in {"owner", "admin"} else ("staff" if actor else "system"), "department": row.department.name if row.department else "Organization-wide", "ip_address": row.ip_address or "—", "user_agent": row.user_agent or ""}
def _platform_admin_required():
    if not _platform_admin_authenticated(): abort(401)

def _platform_owner_or_404(organization_id):
    row = Organization.query.filter_by(id=organization_id).first()
    if not row: abort(404)
    return row

@app.route("/platform-admin/login", methods=["GET", "POST"])
@rate_limit("6 per minute")
def platform_admin_login():
    if request.method == "GET": return redirect(url_for("platform_admin_dashboard")) if _platform_admin_authenticated() else render_template("platform_admin/login.html", configured=bool(app.config.get("PLATFORM_ADMIN_USERNAME") and app.config.get("PLATFORM_ADMIN_PASSWORD")))
    payload = request.get_json(silent=True) or request.form; username, password = str(payload.get("username") or "").strip(), str(payload.get("password") or "")
    expected_user, expected_password = app.config.get("PLATFORM_ADMIN_USERNAME") or "", app.config.get("PLATFORM_ADMIN_PASSWORD") or ""
    if not expected_user or not expected_password: return json_error("Platform admin credentials are not configured in .env.", 503)
    if not hmac.compare_digest(username, expected_user) or not hmac.compare_digest(password, expected_password): return json_error("Invalid platform administrator credentials.", 401)
    session["sage_platform_admin"], session["sage_platform_admin_username"] = True, username; record_platform_admin(username, "platform_login", "Platform administrator signed in.")
    return jsonify({"ok": True, "redirect": url_for("platform_admin_dashboard")})

@app.route("/platform-admin/logout", methods=["GET", "POST"])
def platform_admin_logout():
    if _platform_admin_authenticated(): record_platform_admin(_platform_admin_username(), "platform_logout", "Platform administrator signed out.")
    session.pop("sage_platform_admin", None); session.pop("sage_platform_admin_username", None); return redirect(url_for("platform_admin_login"))

@app.get("/platform-admin")
def platform_admin_dashboard():
    if not _platform_admin_authenticated(): return redirect(url_for("platform_admin_login"))
    search = str(request.args.get("q") or "").strip(); status = str(request.args.get("status") or "all").strip().lower()
    rows = organization_rows(search=search, status=status); activity = ActivityEvent.query.order_by(ActivityEvent.created_at.desc()).limit(40).all(); platform_users = User.query.order_by(User.created_at.desc()).limit(1500).all(); financial_activity, financial_summary = _platform_financial_rows()
    return render_template("platform_admin/dashboard.html", owner_rows=rows, platform_summary=platform_summary(), platform_activity=activity, platform_users=platform_users, platform_financial_activity=financial_activity, platform_financial_summary=financial_summary, search=search, status_filter=status, admin_username=_platform_admin_username())

@app.post("/platform-admin/api/users/<user_id>/reset-password")
@rate_limit("20 per hour")
def platform_admin_reset_user_password(user_id):
    """Generate a one-time temporary password for support; SAGE never exposes stored password hashes or recoverable plaintext passwords."""
    _platform_admin_required(); user = User.query.filter_by(id=user_id).first()
    if not user: abort(404)
    temporary_password = f"Sage!{secrets.token_urlsafe(9)}"; user.set_password(temporary_password); record_platform_admin(_platform_admin_username(), "user_password_reset", f"Reset sign-in password for {user.display_name} ({user.email}).", user.organization_id, commit=False); db.session.commit()
    return jsonify({"ok": True, "message": "Temporary password created. It is shown only in this response.", "user": {"id": user.id, "name": user.display_name, "email": user.email, "organization": user.organization.name if user.organization else "—"}, "temporary_password": temporary_password})

@app.get("/platform-admin/api/owners/<organization_id>/detail")
def platform_admin_owner_detail(organization_id):
    _platform_admin_required(); org = _platform_owner_or_404(organization_id); control = get_control(org.id, create=True)
    users = User.query.filter_by(organization_id=org.id).order_by(User.created_at.desc()).limit(100).all(); requests = PurchaseRequest.query.filter_by(organization_id=org.id).order_by(PurchaseRequest.created_at.desc()).limit(30).all(); inventory = InventoryItem.query.filter_by(organization_id=org.id).order_by(InventoryItem.updated_at.desc()).limit(30).all(); assets = AssetItem.query.filter_by(organization_id=org.id).order_by(AssetItem.updated_at.desc()).limit(30).all(); finance = FinancialRecord.query.filter_by(organization_id=org.id).order_by(FinancialRecord.occurred_at.desc()).limit(30).all(); activity = ActivityEvent.query.filter_by(organization_id=org.id).order_by(ActivityEvent.created_at.desc()).limit(30).all()
    return jsonify({"ok": True, "organization": {"id": org.id, "name": org.name, "business_type": org.business_type, "currency": org.currency, "status": control.status, "plan": control.plan, "subscription_status": control.subscription_status}, "users": [{"id": row.id, "name": row.display_name, "email": row.email, "role": row.role_label, "department": row.department.name if row.department else "—", "status": row.status, "last_login": row.last_login_at.isoformat() if row.last_login_at else None} for row in users], "requests": [{"id": row.id, "reference": row.reference, "title": row.title, "status": row.display_status, "amount": float(row.estimated_total or 0), "department": row.department.name if row.department else "—", "requester": row.requester.display_name if row.requester else "—", "created_at": row.created_at.isoformat()} for row in requests], "inventory": [{"id": row.id, "name": row.name, "quantity": float(row.quantity or 0), "unit": row.unit, "value": row.total_value, "department": row.department.name if row.department else "—", "location": row.location or "—"} for row in inventory], "assets": [{"id": row.id, "name": row.name, "tag": row.asset_tag, "serial": row.serial_number or "—", "status": row.status, "department": row.department.name if row.department else "—", "custodian": row.custodian.display_name if row.custodian else "—", "location": row.location or "—", "value": row.total_value} for row in assets], "finance": [{"id": row.id, "reference": row.reference, "type": row.record_type.replace("_", " ").title(), "description": row.description, "amount": float(row.amount or 0), "currency": row.currency, "department": row.department.name if row.department else "—", "occurred_at": row.occurred_at.isoformat()} for row in finance], "activity": [{"id": row.id, "title": row.title, "description": row.description or "", "actor": row.actor.display_name if row.actor else "System", "created_at": row.created_at.isoformat()} for row in activity]})

@app.patch("/platform-admin/api/owners/<organization_id>")
def platform_admin_update_owner(organization_id):
    _platform_admin_required(); org = _platform_owner_or_404(organization_id)
    try:
        control = update_control(org.id, _platform_admin_username(), request.get_json(silent=True) or {}); return jsonify({"ok": True, "message": f"{org.name} updated.", "status": control.status, "plan": control.plan, "subscription_status": control.subscription_status})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/platform-admin/api/owners/<organization_id>/disable")
def platform_admin_disable_owner(organization_id):
    _platform_admin_required(); org = _platform_owner_or_404(organization_id); payload = request.get_json(silent=True) or {}; reason = str(payload.get("reason") or "Workspace disabled by platform administrator").strip()[:500]; control = update_control(org.id, _platform_admin_username(), {"status": "disabled", "note": reason}); return jsonify({"ok": True, "message": f"{org.name} disabled. Owner and staff cannot sign in until restored.", "status": control.status})

@app.post("/platform-admin/api/owners/<organization_id>/restore")
def platform_admin_restore_owner(organization_id):
    _platform_admin_required(); org = _platform_owner_or_404(organization_id); control = update_control(org.id, _platform_admin_username(), {"status": "active"}); return jsonify({"ok": True, "message": f"{org.name} restored.", "status": control.status})

@app.delete("/platform-admin/api/owners/<organization_id>")
def platform_admin_delete_owner(organization_id):
    _platform_admin_required(); org = _platform_owner_or_404(organization_id); payload = request.get_json(silent=True) or {}
    if str(payload.get("confirmation") or "").strip() != "DELETE": return json_error("Type DELETE exactly to permanently delete this organization.", 400)
    if str(payload.get("organization_name") or "").strip() != org.name: return json_error("Organization confirmation does not match.", 400)
    try: name = permanent_delete_organization(app, org.id, _platform_admin_username()); return jsonify({"ok": True, "message": f"{name} and all tenant data were permanently deleted."})
    except Exception: db.session.rollback(); app.logger.exception("Permanent organization deletion failed"); return json_error("Permanent deletion failed. No partial deletion was committed.", 500)

@app.get("/platform-admin/api/owners.csv")
def platform_admin_export_owners():
    _platform_admin_required(); output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Organization", "Owner", "Owner Email", "Business Type", "Status", "Plan", "Subscription", "Created"])
    for item in organization_rows(limit=5000):
        org, owner, control = item["organization"], item["owner"], item["control"]; writer.writerow([org.name, owner.display_name if owner else "", owner.email if owner else "", org.business_type, control.status, control.plan, control.subscription_status, org.created_at.isoformat()])
    response = Response(output.getvalue(), mimetype="text/csv"); response.headers["Content-Disposition"] = "attachment; filename=sage_owners.csv"; return response

@app.get("/platform-admin/api/activity")
def platform_admin_activity():
    _platform_admin_required(); rows = ActivityEvent.query.order_by(ActivityEvent.created_at.desc()).limit(50).all(); org_names = {org.id: org.name for org in Organization.query.filter(Organization.id.in_({row.organization_id for row in rows})).all()} if rows else {}
    return jsonify({"ok": True, "events": [_platform_activity_payload(row, org_names.get(row.organization_id, "Unknown organization")) for row in rows]})

@app.get("/platform-admin/api/activity/stream")
def platform_admin_activity_stream():
    _platform_admin_required()
    @stream_with_context
    def event_stream():
        db.session.remove(); initial = ActivityEvent.query.order_by(ActivityEvent.created_at.desc()).limit(60).all(); seen = {row.id for row in initial}; heartbeat = 0
        yield "event: ready\ndata: {}\n\n"
        while True:
            db.session.remove(); rows = ActivityEvent.query.order_by(ActivityEvent.created_at.desc()).limit(60).all(); fresh = [row for row in reversed(rows) if row.id not in seen]
            for row in fresh:
                org = Organization.query.filter_by(id=row.organization_id).first(); payload = _platform_activity_payload(row, org.name if org else "Unknown organization"); seen.add(row.id); yield f"id: {row.id}\nevent: activity\ndata: {json.dumps(payload)}\n\n"
            heartbeat += 1
            if heartbeat % 10 == 0: yield "event: heartbeat\ndata: {}\n\n"
            if len(seen) > 500: seen = {row.id for row in rows}
            time.sleep(1.5)
    return Response(event_stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

# ==========================================================
# HOME / AUTHENTICATION PAGES
# ==========================================================

@app.route("/")
def home(): return redirect(url_for("dashboard") if current_user.is_authenticated else url_for("login"))

@app.route("/login")
def login(): return redirect(url_for("dashboard")) if current_user.is_authenticated else render_template("auth/login.html")

@app.route("/register")
def register(): return redirect(url_for("dashboard")) if current_user.is_authenticated else render_template("auth/register.html", business_types=BUSINESS_TYPES, individual_business_types=INDIVIDUAL_BUSINESS_TYPES)

@app.route("/register/staff/<token>")
def staff_register(token):
    if current_user.is_authenticated: return redirect(url_for("dashboard"))
    invitation = StaffInvitation.query.filter_by(token=token).first()
    if not invitation or not invitation.is_valid: return render_template("auth/staff_register.html", invitation=None), 410
    return render_template("auth/staff_register.html", invitation=invitation)

@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user(); [session.pop(key, None) for key in ("sage_tenant_org_id", "sage_daily_briefing_pending", "sage_daily_briefing_token", "sage_daily_briefing_ack")]; return redirect(url_for("login"))

def mark_daily_briefing_pending():
    # A unique token per successful sign-in makes the compact SAGE Pulse reliably appear once per login and prevents a failed first fetch from consuming the briefing.
    token = secrets.token_urlsafe(12); session["sage_daily_briefing_token"] = token; session["sage_daily_briefing_pending"] = True; session.pop("sage_daily_briefing_ack", None); return token

# ==========================================================
# AUTHENTICATION API
# ==========================================================

@app.post("/api/auth/register-owner")
@rate_limit("8 per minute")
def api_register_owner():
    try:
        owner = register_owner(request.get_json(silent=True) or {}); login_user(owner, remember=True); session["sage_tenant_org_id"] = owner.organization_id; mark_daily_briefing_pending()
        return jsonify({"ok": True, "redirect": url_for("dashboard"), "organization": owner.organization.name, "name": owner.display_name})
    except (ValueError, TypeError) as error: db.session.rollback(); return json_error(error)
    except Exception: db.session.rollback(); app.logger.exception("Owner registration failed"); return json_error("Registration could not be completed. Check the database connection and try again.", 500)

@app.post("/api/auth/login")
@rate_limit("12 per minute")
def api_login():
    try:
        payload = request.get_json(silent=True) or {}; user = authenticate(payload.get("email"), payload.get("password"))
        if not user: return json_error("Invalid email address or password.", 401)
        login_user(user, remember=bool(payload.get("remember"))); session["sage_tenant_org_id"] = user.organization_id; mark_daily_briefing_pending()
        if user.role != "owner": record_activity(app, user, "staff_login", "Staff signed in", f"{user.display_name} signed in to SAGE.", "user", user.id, {"role": user.role, "department": user.department.name if user.department else None}, notify_owner=True, email_owner=False, level="info"); db.session.commit()
        return jsonify({"ok": True, "redirect": url_for("dashboard"), "name": user.display_name, "role": user.role_label})
    except ValueError as error: return json_error(error, 403)
    except Exception: app.logger.exception("Login failed"); return json_error("Sign in could not be completed. Please try again.", 500)

@app.post("/api/auth/change-password")
@rate_limit("8 per minute")
def api_change_password():
    """Public sign-in helper: verified users may change their password without changing their email/login identifier."""
    payload = request.get_json(silent=True) or {}
    try:
        new_password, confirmation = str(payload.get("new_password") or ""), str(payload.get("confirm_password") or "")
        if new_password != confirmation: return json_error("New password and confirmation do not match.")
        user = change_password(payload.get("email"), payload.get("current_password"), new_password); record_activity(app, user, "password_changed", "Password changed", f"{user.display_name} changed their SAGE sign-in password.", "user", user.id, {"email": user.email}, notify_owner=True, email_owner=False, level="info"); db.session.commit()
        return jsonify({"ok": True, "message": "Password changed successfully. Your email/login remains the same."})
    except ValueError as error: db.session.rollback(); return json_error(error, 400)
    except Exception: db.session.rollback(); app.logger.exception("Password change failed"); return json_error("Password could not be changed. Please try again.", 500)

@app.post("/api/auth/register-staff/<token>")
@rate_limit("10 per minute")
def api_register_staff(token):
    invitation = StaffInvitation.query.filter_by(token=token).first()
    try:
        user = register_staff(invitation, request.get_json(silent=True) or {}); login_user(user, remember=True); session["sage_tenant_org_id"] = user.organization_id; mark_daily_briefing_pending()
        record_activity(app, user, "staff_registered", "New staff account activated", f"{user.display_name} completed SAGE registration for {user.department.name if user.department else 'the organization'} as {user.role_label}.", "user", user.id, {"role": user.role, "department": user.department.name if user.department else None}, notify_owner=True, email_owner=True, level="success"); db.session.commit()
        return jsonify({"ok": True, "redirect": url_for("dashboard"), "name": user.display_name, "department": user.department.name if user.department else ""})
    except (ValueError, TypeError) as error: db.session.rollback(); return json_error(error)
    except Exception: db.session.rollback(); app.logger.exception("Staff registration failed"); return json_error("Staff registration could not be completed. Please try again.", 500)

# ==========================================================
# DAILY BRIEFING API
# Returns a large, sequential, permission-aware status summary once after sign-in; users can replay it any time from SAGE Guide.
# ==========================================================

@app.get("/api/daily-briefing")
@login_required
def api_daily_briefing():
    # Do not consume the briefing merely because it was fetched. The browser acknowledges it only after the Pulse card has actually rendered.
    force = request.args.get("force") == "1"; token = session.get("sage_daily_briefing_token")
    if not token: token = mark_daily_briefing_pending()  # Compatibility: already-signed-in users receive one briefing after installing this patch.
    if not force and session.get("sage_daily_briefing_ack") == token: return jsonify({"ok": True, "show": False, "slides": [], "briefing_token": token})
    briefing = build_daily_briefing(current_user); return jsonify({"ok": True, "show": True, "briefing_token": token, **briefing})

@app.post("/api/daily-briefing/ack")
@login_required
def api_daily_briefing_ack():
    token = str((request.get_json(silent=True) or {}).get("briefing_token") or ""); current = str(session.get("sage_daily_briefing_token") or "")
    if token and hmac.compare_digest(token, current): session["sage_daily_briefing_ack"] = current; session["sage_daily_briefing_pending"] = False
    return jsonify({"ok": True})

# ==========================================================
# STAFF / DEPARTMENT ADMINISTRATION API
# ==========================================================

@app.post("/api/staff/invite")
@login_required
@roles_required("owner", "admin")
def api_staff_invite():
    try:
        payload = request.get_json(silent=True) or {}; invitation = create_staff_invitation(current_user, payload); invite_url = url_for("staff_register", token=invitation.token, _external=True); delivery = str(payload.get("delivery") or "link").strip().lower()
        mailed = False
        if delivery == "email":
            from services.email_service import send_staff_invitation_email
            mailed = send_staff_invitation_email(app, invitation, invite_url, current_user)
            record_activity(app, current_user, "staff_invitation_emailed", "Staff invitation emailed", f"{current_user.display_name} sent a SAGE registration invitation to {invitation.email} for {invitation.department.name if invitation.department else 'the organization'}.", "user", invitation.id, {"email": invitation.email, "department": invitation.department.name if invitation.department else None, "role": invitation.role}, notify_owner=False)
            db.session.commit()
        message = "Invitation email queued successfully." if mailed else ("Invitation created, but email is not configured. Copy and send the private link below." if delivery == "email" else "Staff invitation created. Copy the private link or use Mail Invite.")
        return jsonify({"ok": True, "message": message, "invite_url": invite_url, "email": invitation.email, "delivery": delivery, "mailed": mailed})
    except ValueError as error: db.session.rollback(); return json_error(error)


# ==========================================================
# OWNER STAFF DIRECTORY / ACCOUNT CONTROL API
# ==========================================================
# Staff removal is intentionally a soft-delete. Financial requests, receipts and audit history keep their original actor instead of becoming orphaned.

@app.patch("/api/staff/<user_id>")
@login_required
@roles_required("owner", "admin")
def api_staff_update(user_id):
    target, payload = _staff_target_or_404(user_id), request.get_json(silent=True) or {}
    if target.role == "owner": return json_error("The organization owner account cannot be edited from Staff Management.", 403)
    try:
        old_department, old_role = target.department.name if target.department else "No department", target.role_label
        for field in ("first_name", "middle_name", "last_name", "phone", "position", "employee_id", "address", "sex"):
            if field in payload and hasattr(target, field): setattr(target, field, (str(payload.get(field) or "").strip() or None) if field not in {"first_name", "last_name"} else str(payload.get(field) or "").strip())
        if not target.first_name or not target.last_name: raise ValueError("First name and last name are required.")
        role = str(payload.get("role") or target.role).strip().lower(); allowed_roles = {"admin", "finance", "procurement", "department_head", "staff"}
        if role not in allowed_roles: raise ValueError("Select a valid staff role.")
        department = Department.query.filter_by(id=payload.get("department_id"), organization_id=current_user.organization_id, is_active=True).first()
        if not department: raise ValueError("Select a valid active department.")
        target.role, target.department_id = role, department.id
        description = f"{current_user.display_name} updated {target.display_name}: {old_role} / {old_department} → {target.role_label} / {department.name}."
        record_activity(app, current_user, "staff_updated", "Staff profile updated", description, "user", target.id, {"old_role": old_role, "new_role": target.role_label, "old_department": old_department, "new_department": department.name}, notify_owner=True); notify_user(app, target, "Account details updated", f"Your SAGE role/department profile was updated by {current_user.display_name}.", "info", "user", target.id, email=True); db.session.commit()
        return jsonify({"ok": True, "message": "Staff profile updated.", "user": {"id": target.id, "name": target.display_name, "role": target.role_label, "department": department.name, "status": target.status}})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/staff/<user_id>/status")
@login_required
@roles_required("owner", "admin")
def api_staff_status(user_id):
    target, action = _staff_target_or_404(user_id), str((request.get_json(silent=True) or {}).get("action") or "").strip().lower()
    if target.id == current_user.id or target.role == "owner": return json_error("The owner/current account cannot be suspended from this screen.", 403)
    if action not in {"suspend", "activate"}: return json_error("Choose suspend or activate.")
    target.status = "suspended" if action == "suspend" else "active"; label = "suspended" if action == "suspend" else "reactivated"
    record_activity(app, current_user, f"staff_{label}", f"Staff account {label}", f"{current_user.display_name} {label} {target.display_name}'s SAGE account.", "user", target.id, {"status": target.status}, notify_owner=True); notify_user(app, target, f"SAGE account {label}", f"Your SAGE account was {label} by {current_user.display_name}.", "warning" if action == "suspend" else "success", "user", target.id, email=True); db.session.commit()
    return jsonify({"ok": True, "message": f"{target.display_name} has been {label}.", "status": target.status})

@app.delete("/api/staff/<user_id>")
@login_required
@roles_required("owner", "admin")
def api_staff_delete(user_id):
    target, payload = _staff_target_or_404(user_id), request.get_json(silent=True) or {}
    if target.id == current_user.id or target.role == "owner": return json_error("The owner/current account cannot be deleted.", 403)
    reason = str(payload.get("reason") or "Removed by organization management").strip()[:300]; target.status = "deleted"
    record_activity(app, current_user, "staff_deleted", "Staff removed", f"{current_user.display_name} removed {target.display_name} from active SAGE access. Reason: {reason}", "user", target.id, {"reason": reason, "soft_delete": True}, notify_owner=True); notify_user(app, target, "SAGE account removed", f"Your SAGE account was removed by {current_user.display_name}. Contact your organization if this was unexpected.", "warning", "user", target.id, email=True); db.session.commit()
    return jsonify({"ok": True, "message": f"{target.display_name} was removed. Historical requests, receipts and audit records were preserved."})

@app.post("/api/staff/<user_id>/restore")
@login_required
@roles_required("owner", "admin")
def api_staff_restore(user_id):
    target = _staff_target_or_404(user_id)
    if target.status != "deleted": return json_error("This account is not in the removed staff archive.")
    target.status = "active"; record_activity(app, current_user, "staff_restored", "Staff account restored", f"{current_user.display_name} restored {target.display_name}'s SAGE access.", "user", target.id, {"status": "active"}, notify_owner=True); notify_user(app, target, "SAGE account restored", f"Your SAGE account was restored by {current_user.display_name}.", "success", "user", target.id, email=True); db.session.commit()
    return jsonify({"ok": True, "message": f"{target.display_name} was restored."})

@app.get("/api/staff/<user_id>/activity")
@login_required
@roles_required("owner", "admin")
def api_staff_activity(user_id):
    target = _staff_target_or_404(user_id); events = ActivityEvent.query.filter_by(organization_id=current_user.organization_id, actor_id=target.id).order_by(ActivityEvent.created_at.desc()).limit(30).all()
    counts = {"requests": PurchaseRequest.query.filter_by(organization_id=current_user.organization_id, requester_id=target.id).count(), "uploads": Attachment.query.filter_by(organization_id=current_user.organization_id, uploaded_by_id=target.id).count(), "financial_records": FinancialRecord.query.filter_by(organization_id=current_user.organization_id, created_by_id=target.id).count(), "inventory_items": InventoryItem.query.filter_by(organization_id=current_user.organization_id, added_by_id=target.id).count(), "activity_events": ActivityEvent.query.filter_by(organization_id=current_user.organization_id, actor_id=target.id).count()}
    return jsonify({"ok": True, "user": {"id": target.id, "name": target.display_name, "email": target.email, "role": target.role_label, "department": target.department.name if target.department else "No department", "status": target.status, "last_login": target.last_login_at.isoformat() if target.last_login_at else None}, "counts": counts, "events": [{"action": event.action, "title": event.title, "description": event.description, "created_at": event.created_at.isoformat(), "ip": event.ip_address} for event in events]})

@app.post("/api/staff/bulk")
@login_required
@roles_required("owner", "admin")
def api_staff_bulk():
    payload = request.get_json(silent=True) or {}; action, user_ids = str(payload.get("action") or "").strip().lower(), list(dict.fromkeys(payload.get("user_ids") or []))
    if action not in {"activate", "suspend", "delete"} or not user_ids: return json_error("Choose staff accounts and a valid bulk action.")
    targets = User.query.filter(User.organization_id == current_user.organization_id, User.id.in_(user_ids)).all(); changed = []
    for target in targets:
        if target.id == current_user.id or target.role == "owner": continue
        target.status = {"activate": "active", "suspend": "suspended", "delete": "deleted"}[action]; changed.append(target.display_name)
    if changed: record_activity(app, current_user, f"staff_bulk_{action}", "Bulk staff update", f"{current_user.display_name} applied {action} to {len(changed)} staff account(s): {', '.join(changed[:8])}.", "user", None, {"action": action, "count": len(changed)}, notify_owner=True); db.session.commit()
    return jsonify({"ok": True, "message": f"{len(changed)} staff account(s) updated.", "count": len(changed)})

@app.get("/api/staff/export.csv")
@login_required
@roles_required("owner", "admin")
def api_staff_export():
    rows = User.query.filter_by(organization_id=current_user.organization_id).order_by(User.created_at.desc()).all(); output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Full Name", "Email", "Phone", "Employee ID", "Position", "Department", "Role", "Status", "Last Login", "Created"])
    for user in rows: writer.writerow([user.display_name, user.email, user.phone or "", user.employee_id or "", user.position or "", user.department.name if user.department else "", user.role_label, user.status.title(), user.last_login_at.isoformat() if user.last_login_at else "", user.created_at.isoformat() if user.created_at else ""])
    record_activity(app, current_user, "staff_exported", "Staff directory exported", f"{current_user.display_name} exported the organization staff directory.", "report", "staff", {"rows": len(rows)}, notify_owner=True); db.session.commit()
    filename = f"vision_staff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"; return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.post("/api/departments")
@login_required
@roles_required("owner", "admin")
def api_departments_create():
    try:
        department = create_department(current_user, request.get_json(silent=True) or {}); record_activity(app, current_user, "department_created", "Department created", f"{current_user.display_name} created {department.name}.", "department", department.id, notify_owner=False); db.session.commit()
        return jsonify({"ok": True, "message": "Department created.", "department": {"id": department.id, "name": department.name, "code": department.code}})
    except ValueError as error: db.session.rollback(); return json_error(error)


# ==========================================================
# CEO UPGRADE PHASE 3: BRANCH / LOCATION + APPROVAL LIMITS
# ==========================================================

@app.post("/api/management/branches")
@login_required
@roles_required("owner", "admin")
def api_management_branch_create():
    try:
        row = create_branch(current_user, request.get_json(silent=True) or {}); record_activity(app, current_user, "branch_saved", "Branch/location saved", f"{current_user.display_name} configured branch {row.name} ({row.code}).", "branch", row.id, notify_owner=False); db.session.commit(); return jsonify({"ok": True, "message": f"{row.name} saved.", "id": row.id})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/management/branch-departments")
@login_required
@roles_required("owner", "admin")
def api_management_branch_department():
    try:
        row = assign_department_to_branch(current_user, request.get_json(silent=True) or {}); record_activity(app, current_user, "branch_department_assigned", "Department assigned to branch", f"{row.department.name} assigned to {row.branch.name}.", "branch", row.branch_id, {"department_id": row.department_id}, notify_owner=False); db.session.commit(); return jsonify({"ok": True, "message": f"{row.department.name} assigned to {row.branch.name}."})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/management/approval-rules")
@login_required
@roles_required("owner", "admin")
def api_management_approval_rule():
    try:
        row = create_approval_rule(current_user, request.get_json(silent=True) or {}); record_activity(app, current_user, "approval_rule_created", "Approval limit created", f"{row.name}: {row.required_role.replace('_',' ').title()} approval from {current_user.organization.currency} {row.min_amount:,.2f}{' to ' + current_user.organization.currency + ' ' + format(row.max_amount, ',.2f') if row.max_amount is not None else ' and above'}.", "approval_rule", row.id, notify_owner=False); db.session.commit(); return jsonify({"ok": True, "message": f"Approval rule {row.name} created.", "id": row.id})
    except (ValueError, TypeError) as error: db.session.rollback(); return json_error(error)

# ==========================================================
# REQUEST / APPROVAL / PURCHASE EVIDENCE API
# ==========================================================

@app.post("/api/requests")
@login_required
def api_requests_create():
    if current_user.role == "owner": return json_error("Organization owners do not submit requests to themselves. Use Finance, Inventory, Assets or Quick Record instead.", 403)
    try:
        row = create_request(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "request": {"id": row.id, "reference": row.reference, "status": row.status, "amount": float(row.estimated_total)}, "message": "Request submitted." if row.status == "submitted" else "Draft request saved."})
    except (ValueError, TypeError) as error: db.session.rollback(); return json_error(error)
    except Exception: db.session.rollback(); app.logger.exception("Request creation failed"); return json_error("The request could not be saved.", 500)

@app.post("/api/requests/<request_id>/action")
@login_required
def api_request_action(request_id):
    row = _get_request_or_404(request_id); payload = request.get_json(silent=True) or {}
    try:
        row = decide_request(app, current_user, row, payload.get("action"), payload.get("note")); return jsonify({"ok": True, "status": row.status, "label": row.display_status, "message": f"Request is now {row.display_status}."})
    except PermissionError as error: db.session.rollback(); return json_error(error, 403)
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.get("/api/requests/<request_id>/fulfillment")
@login_required
def api_request_fulfillment_context(request_id):
    # PHASE 8: Stage 2 context keeps requested vs actual quantities/costs, funding, staff source and evidence together.
    row = _get_request_or_404(request_id); fulfillment = row.fulfillment; evidence = Attachment.query.filter_by(organization_id=current_user.organization_id, entity_type="fulfillment", entity_id=fulfillment.id).order_by(Attachment.created_at.desc()).all() if fulfillment else []; line_map = {line.request_item_id: line for line in (fulfillment.lines if fulfillment else [])}; funding = row.funding
    return jsonify({"ok": True, "request": {"id": row.id, "reference": row.reference, "title": row.title, "status": row.status, "estimated_total": float(row.estimated_total or 0), "currency": row.currency, "requester": row.requester.display_name if row.requester else "Unknown", "department": row.department.name if row.department else ""}, "funding": {"approved_budget": float(funding.approved_budget or 0), "amount_sent": float(funding.amount_sent or 0), "payment_method": funding.payment_method or "", "payment_reference": funding.payment_reference or "", "note": funding.note or ""} if funding else None, "items": [{"id": item.id, "name": item.item_name, "category": item.category or "", "unit": item.unit, "requested_quantity": float(item.quantity or 0), "requested_unit_cost": float(item.unit_cost or 0), "requested_total": float(item.estimated_total or 0), "actual_quantity": float(line_map[item.id].actual_quantity or 0) if item.id in line_map else float(item.quantity or 0), "actual_unit_cost": float(line_map[item.id].actual_unit_cost or 0) if item.id in line_map else float(item.unit_cost or 0), "delivery_at": line_map[item.id].delivered_at.isoformat() if item.id in line_map and line_map[item.id].delivered_at else None, "note": (line_map[item.id].notes or "") if item.id in line_map else ""} for item in row.items], "fulfillment": {"source_type": fulfillment.source_type, "supplied_by": fulfillment.supplied_by or "", "supplier_name": fulfillment.supplier_name or "", "actual_total": float(fulfillment.actual_total or 0), "purchase_date": fulfillment.purchase_date.isoformat() if fulfillment.purchase_date else None, "notes": fulfillment.notes or "", "draft": fulfillment.is_draft, "confirmed": bool(fulfillment.confirmed_at), "recorded_by": fulfillment.recorded_by.display_name if fulfillment.recorded_by else ""} if fulfillment else None, "evidence": [{"id": item.id, "kind": item.kind, "name": item.original_name, "final": item.is_final} for item in evidence]})

@app.post("/api/requests/<request_id>/fulfillment")
@login_required
def api_request_fulfillment(request_id):
    row = _get_request_or_404(request_id)
    try:
        fulfillment = save_fulfillment(app, current_user, row, request.form, request.files.get("receipt"), request.files.get("item_image")); return jsonify({"ok": True, "draft": fulfillment.is_draft, "confirmed": bool(fulfillment.confirmed_at), "message": "Stage 2 acquisition submitted, evidence locked and records posted." if fulfillment.confirmed_at else "Stage 2 acquisition draft saved."})
    except PermissionError as error: db.session.rollback(); return json_error(error, 403)
    except (ValueError, TypeError) as error: db.session.rollback(); return json_error(error)
    except Exception: db.session.rollback(); app.logger.exception("Purchase fulfillment failed"); return json_error("Acquisition details could not be saved.", 500)

@app.post("/api/requests/<request_id>/verify")
@login_required
def api_request_verify(request_id):
    row = _get_request_or_404(request_id)
    try:
        fulfillment = verify_fulfillment(app, current_user, row); return jsonify({"ok":True,"status":row.status,"verified_at":fulfillment.verified_at.isoformat() if fulfillment.verified_at else None,"message":"Acquisition verified and accountability chain completed."})
    except PermissionError as error: db.session.rollback(); return json_error(error, 403)
    except ValueError as error: db.session.rollback(); return json_error(error)
    except Exception: db.session.rollback(); app.logger.exception("Acquisition verification failed"); return json_error("The acquisition could not be verified.", 500)

@app.post("/api/requests/<request_id>/funding")
@login_required
def api_request_funding(request_id):
    # PHASE 8: owner/finance budget and external-money-sent register; SAGE records the decision but does not transfer money.
    row = _get_request_or_404(request_id)
    try:
        funding = save_request_funding(app, current_user, row, request.get_json(silent=True) or {}); return jsonify({"ok": True, "message": "Budget/funding record updated.", "approved_budget": float(funding.approved_budget or 0), "amount_sent": float(funding.amount_sent or 0), "status": row.status})
    except PermissionError as error: db.session.rollback(); return json_error(error, 403)
    except (ValueError, TypeError) as error: db.session.rollback(); return json_error(error)


# ==========================================================
# FINANCE / INVENTORY API
# ==========================================================

# ==========================================================
# SAGE UPGRADE PHASE 2: INCOME / SALES ENTRY
# Any authenticated staff member can record real money-in; organization-wide finance controls remain restricted.
# ==========================================================

@app.post("/api/finance/performance-targets")
@login_required
@roles_required("owner", "admin")
def api_finance_performance_target():
    try:
        row = save_performance_target(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "id": row.id, "message": f"{row.name} saved."})
    except ValueError as error: db.session.rollback(); return json_error(error)
    except Exception: db.session.rollback(); app.logger.exception("Performance target save failed"); return json_error("Financial target could not be saved.", 500)

@app.get("/api/income/export.csv")
@login_required
def api_income_export_csv():
    """Export exactly the income register the signed-in user is permitted to see; staff never receive organization-wide rows."""
    headers, rows = income_export_rows(current_user); output = io.StringIO(); writer = csv.writer(output); writer.writerow(headers); writer.writerows(rows); payload = io.BytesIO(output.getvalue().encode("utf-8-sig")); payload.seek(0)
    return send_file(payload, mimetype="text/csv; charset=utf-8", as_attachment=True, download_name=f"SAGE_Income_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")

@app.post("/api/income/entries")
@login_required
def api_income_entry():
    try:
        payload = dict(request.form); payload["entry_type"] = str(payload.get("entry_type") or "revenue").lower(); payload["status"] = "posted"
        if payload["entry_type"] not in {"income", "revenue"}: return json_error("Income & Sales only accepts income or revenue entries.")
        if current_user.role not in {"owner", "admin", "finance"}: payload["department_id"], payload["account_id"] = current_user.department_id or "", ""
        row = post_ledger_entry(app, current_user, payload, request.files.get("evidence")); return jsonify({"ok": True, "id": row.id, "reference": row.reference, "message": f"{row.display_type} recorded and sent to management tracking."})
    except ValueError as error: db.session.rollback(); return json_error(error)
    except Exception: db.session.rollback(); app.logger.exception("Income / sales entry failed"); return json_error("Income or sales entry could not be saved.", 500)

@app.get("/api/expenses/export.csv")
@login_required
def api_expense_export_csv():
    """Export the same role-scoped expense register visible on the Expenses & Expenditure page."""
    if "expenses" not in allowed_pages(current_user): abort(403)
    headers, rows = expense_export_rows(current_user); output = io.StringIO(); writer = csv.writer(output); writer.writerow(headers); writer.writerows(rows); payload = io.BytesIO(output.getvalue().encode("utf-8-sig")); payload.seek(0)
    return send_file(payload, mimetype="text/csv; charset=utf-8", as_attachment=True, download_name=f"SAGE_Expenses_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")

@app.post("/api/expenses/entries")
@login_required
@roles_required("owner", "admin", "finance")
def api_expense_entry():
    try:
        payload = dict(request.form); payload["entry_type"] = str(payload.get("entry_type") or "expense").lower(); payload["status"] = "posted"
        if payload["entry_type"] not in {"expense", "expenditure", "operating_cost", "tax"}: return json_error("Choose a valid expense or expenditure type.")
        row = post_ledger_entry(app, current_user, payload, request.files.get("evidence")); return jsonify({"ok": True, "id": row.id, "reference": row.reference, "message": f"{row.display_type} recorded and added to expenditure tracking."})
    except ValueError as error: db.session.rollback(); return json_error(error)
    except Exception: db.session.rollback(); app.logger.exception("Expense entry failed"); return json_error("Expense or expenditure could not be saved.", 500)

@app.post("/api/finance/records")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_record():
    payload = request.get_json(silent=True) or {}
    try:
        department = scoped_department(current_user, payload.get("department_id")); row = add_financial_record(current_user, (payload.get("record_type") or "").strip(), payload.get("description"), payload.get("amount"), department.id, payload.get("category"), commit=False); record_activity(app, current_user, "financial_record_added", "Financial record posted", f"{current_user.display_name} posted {row.record_type.replace('_',' ')}: {row.description} ({row.currency} {row.amount:,.2f}) for {department.name}.", "financial_record", row.id, {"type": row.record_type, "amount": float(row.amount)}, email_owner=True); db.session.commit()
        return jsonify({"ok": True, "reference": row.reference, "message": "Financial record posted."})
    except ValueError as error: db.session.rollback(); return json_error(error)

# ==========================================================
# PHASE 5: FINANCE & ACCOUNTS CONTROL CENTRE API
# Bank-like operational finance controls; every endpoint is tenant-scoped and owner/finance restricted.
# ==========================================================

@app.post("/api/finance/accounts")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_account_create():
    try:
        row = create_finance_account(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "id": row.id, "message": f"{row.name} created."})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/finance/ledger")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_ledger_post():
    try:
        row = post_ledger_entry(app, current_user, request.form, request.files.get("evidence")); return jsonify({"ok": True, "id": row.id, "reference": row.reference, "message": "Finance transaction posted." if row.status == "posted" else "Finance draft saved."})
    except (ValueError, PermissionError) as error: db.session.rollback(); return json_error(error, 403 if isinstance(error, PermissionError) else 400)
    except Exception: db.session.rollback(); app.logger.exception("Finance ledger posting failed"); return json_error("Finance transaction could not be saved.", 500)

@app.post("/api/finance/budgets")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_budget_create():
    try:
        row = create_budget(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "id": row.id, "message": "Budget created."})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/finance/receivables")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_receivable_create():
    try:
        row = create_receivable(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "id": row.id, "reference": row.reference, "message": "Receivable recorded."})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/finance/receivables/<row_id>/payment")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_receivable_payment(row_id):
    row = FinanceReceivable.query.filter_by(id=row_id, organization_id=current_user.organization_id).first_or_404()
    try:
        row = settle_receivable(app, current_user, row, (request.get_json(silent=True) or {}).get("amount")); return jsonify({"ok": True, "balance": row.balance, "status": row.status, "message": "Receivable payment recorded."})
    except (ValueError, PermissionError) as error: db.session.rollback(); return json_error(error, 403 if isinstance(error, PermissionError) else 400)

@app.post("/api/finance/payables")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_payable_create():
    try:
        row = create_payable(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "id": row.id, "reference": row.reference, "message": "Payable recorded."})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/finance/payables/<row_id>/payment")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_payable_payment(row_id):
    row = FinancePayable.query.filter_by(id=row_id, organization_id=current_user.organization_id).first_or_404()
    try:
        row = settle_payable(app, current_user, row, (request.get_json(silent=True) or {}).get("amount")); return jsonify({"ok": True, "balance": row.balance, "status": row.status, "message": "Payable payment recorded."})
    except (ValueError, PermissionError) as error: db.session.rollback(); return json_error(error, 403 if isinstance(error, PermissionError) else 400)

@app.post("/api/finance/reconciliations")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_reconciliation_create():
    try:
        row = create_reconciliation(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "id": row.id, "variance": float(row.variance or 0), "status": row.status, "message": "Account reconciliation completed."})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/finance/payroll")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_payroll_create():
    try:
        row = create_payroll(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "id": row.id, "message": "Payroll record saved."})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/finance/taxes")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_tax_create():
    try:
        row = create_tax(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "id": row.id, "message": "Tax record saved."})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/finance/forecasts")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_forecast_create():
    try:
        row = create_forecast(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "id": row.id, "message": "Financial forecast created."})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.get("/api/finance/export.csv")
@login_required
@roles_required("owner", "admin", "finance")
def api_finance_export_csv():
    output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Reference", "Date", "Type", "Direction", "Description", "Counterparty", "Department", "Account", "Amount", "Currency", "Status", "External Reference"])
    rows = FinanceLedgerEntry.query.filter_by(organization_id=current_user.organization_id).order_by(FinanceLedgerEntry.occurred_at.desc()).all()
    for row in rows: writer.writerow([row.reference, row.occurred_at.isoformat() if row.occurred_at else "", row.display_type, row.direction, row.description, row.counterparty or "", row.department.name if row.department else "", row.account.name if row.account else "", float(row.amount or 0), row.currency, row.status, row.external_reference or ""])
    payload = io.BytesIO(output.getvalue().encode("utf-8-sig")); payload.seek(0); return send_file(payload, mimetype="text/csv", as_attachment=True, download_name=f"SAGE_Finance_Ledger_{datetime.now().strftime('%Y%m%d')}.csv")

@app.post("/api/catalog/items")
@login_required
def api_catalog_item():
    # Phase 2: staff can extend their own department catalogue; owners/admins may target any department in their tenant.
    payload = request.get_json(silent=True) or {}
    try:
        department = scoped_department(current_user, payload.get("department_id")); name = (payload.get("name") or "").strip(); category = (payload.get("category") or "Custom").strip() or "Custom"; unit = (payload.get("unit") or "unit").strip() or "unit"
        if not name: raise ValueError("Item name is required.")
        existing = CatalogItem.query.filter(func.lower(CatalogItem.name) == name.lower(), CatalogItem.organization_id == current_user.organization_id, CatalogItem.department_id == department.id).first()
        if existing: return jsonify({"ok": True, "id": existing.id, "message": "This item already exists in your custom catalogue."})
        item = CatalogItem(organization_id=current_user.organization_id, department_id=department.id, name=name, category=category, unit=unit, created_by_id=current_user.id, is_custom=True); db.session.add(item); db.session.flush(); record_activity(app, current_user, "catalog_item_added", "Department catalogue item added", f"{current_user.display_name} added {name} to the {department.name} catalogue.", "catalog_item", item.id, {"category": category, "unit": unit}, notify_owner=current_user.role not in {"owner", "admin"}); db.session.commit()
        return jsonify({"ok": True, "id": item.id, "message": f"{name} added to {department.name}."})
    except ValueError as error: db.session.rollback(); return json_error(error)

@app.post("/api/inventory/items")
@login_required
def api_inventory_item():
    payload = request.get_json(silent=True) or {}
    try:
        department = scoped_department(current_user, payload.get("department_id")); name = (payload.get("name") or "").strip()
        if not name: raise ValueError("Item name is required.")
        item = InventoryItem(organization_id=current_user.organization_id, department_id=department.id, name=name, category=(payload.get("category") or "").strip() or None, unit=(payload.get("unit") or "unit").strip(), quantity=float(payload.get("quantity") or 0), unit_value=float(payload.get("unit_value") or 0), reorder_level=float(payload.get("reorder_level") or 0), location=(payload.get("location") or department.name).strip(), added_by_id=current_user.id); db.session.add(item); db.session.flush(); db.session.add(StockMovement(organization_id=current_user.organization_id, inventory_item_id=item.id, user_id=current_user.id, movement_type="stock_in", quantity=item.quantity, source="Manual stock entry", destination=item.location, reason="Initial item record")); record_activity(app, current_user, "inventory_item_added", "Inventory item added", f"{current_user.display_name} added {item.name} ({item.quantity:g} {item.unit}) to {department.name}.", "inventory_item", item.id, {"quantity": float(item.quantity), "unit_value": float(item.unit_value)}, email_owner=True); db.session.commit()
        return jsonify({"ok": True, "message": "Inventory item added.", "id": item.id})
    except ValueError as error: db.session.rollback(); return json_error(error)

# ==========================================================
# PHASE 3: ASSET / STOCK / MOVEMENT ENGINE
# ==========================================================

@app.post("/api/assets")
@login_required
def api_asset_create():
    payload = request.get_json(silent=True) or {}
    try:
        department = scoped_department(current_user, payload.get("department_id")); name = str(payload.get("name") or "").strip()
        if not name: raise ValueError("Asset name is required.")
        custodian_id = str(payload.get("custodian_user_id") or "").strip() or None; custodian = User.query.filter_by(id=custodian_id, organization_id=current_user.organization_id).first() if custodian_id else None
        if custodian_id and not custodian: raise ValueError("Choose a valid custodian.")
        acquired_at = datetime.strptime(payload.get("acquired_at"), "%Y-%m-%d").date() if payload.get("acquired_at") else None; warranty = datetime.strptime(payload.get("warranty_expiry"), "%Y-%m-%d").date() if payload.get("warranty_expiry") else None
        asset = AssetItem(organization_id=current_user.organization_id, department_id=department.id, custodian_user_id=custodian.id if custodian else None, created_by_id=current_user.id, name=name, category=str(payload.get("category") or "").strip() or None, asset_tag=str(payload.get("asset_tag") or "").strip() or next_asset_tag(current_user.organization_id), serial_number=str(payload.get("serial_number") or "").strip() or None, quantity=float(payload.get("quantity") or 1), unit_value=float(payload.get("unit_value") or 0), location=str(payload.get("location") or department.name).strip(), condition=str(payload.get("condition") or "good").strip(), status="assigned" if custodian else "active", acquired_at=acquired_at, warranty_expiry=warranty, notes=str(payload.get("notes") or "").strip() or None); db.session.add(asset); db.session.flush(); db.session.add(AssetMovement(organization_id=current_user.organization_id, asset_id=asset.id, user_id=current_user.id, movement_type="register", quantity=asset.quantity, destination_department_id=department.id, custodian_user_id=custodian.id if custodian else None, destination_location=asset.location, reason="Manual asset registration")); record_activity(app, current_user, "asset_registered", "Asset registered", f"{current_user.display_name} registered {asset.name} ({asset.asset_tag}) in {department.name}.", "asset", asset.id, {"asset_tag": asset.asset_tag, "serial": asset.serial_number, "quantity": float(asset.quantity)}, notify_owner=True, email_owner=True); db.session.commit(); return jsonify({"ok": True, "id": asset.id, "message": f"{asset.name} added to the asset register."})
    except (ValueError, TypeError) as error: db.session.rollback(); return json_error(error)

@app.post("/api/assets/<asset_id>/move")
@login_required
def api_asset_move(asset_id):
    asset = AssetItem.query.filter_by(id=asset_id, organization_id=current_user.organization_id).first_or_404(); payload = request.get_json(silent=True) or {}
    if current_user.role not in {"owner", "admin", "finance", "procurement"} and asset.department_id != current_user.department_id: abort(403)
    try:
        department = Department.query.filter_by(id=payload.get("department_id"), organization_id=current_user.organization_id, is_active=True).first() if payload.get("department_id") else None; custodian = User.query.filter_by(id=payload.get("custodian_user_id"), organization_id=current_user.organization_id).first() if payload.get("custodian_user_id") else None; move_asset(app, current_user, asset, payload.get("movement_type"), department, str(payload.get("location") or "").strip() or None, custodian, payload.get("reason")); return jsonify({"ok": True, "message": "Asset movement recorded."})
    except (ValueError, PermissionError) as error: db.session.rollback(); return json_error(error, 403 if isinstance(error, PermissionError) else 400)

@app.post("/api/inventory/items/<item_id>/move")
@login_required
def api_inventory_move(item_id):
    item = InventoryItem.query.filter_by(id=item_id, organization_id=current_user.organization_id).first_or_404(); payload = request.get_json(silent=True) or {}
    if current_user.role not in {"owner", "admin", "finance", "procurement"} and item.department_id != current_user.department_id: abort(403)
    try:
        destination_department = Department.query.filter_by(id=payload.get("destination_department_id"), organization_id=current_user.organization_id, is_active=True).first() if payload.get("destination_department_id") else item.department; move_stock(app, current_user, item, payload.get("movement_type"), payload.get("quantity"), payload.get("destination"), destination_department, payload.get("reason"), User.query.filter_by(id=payload.get("recipient_user_id"), organization_id=current_user.organization_id).first() if payload.get("recipient_user_id") else None); return jsonify({"ok": True, "message": "Stock movement recorded.", "quantity": float(item.quantity or 0)})
    except (ValueError, PermissionError) as error: db.session.rollback(); return json_error(error, 403 if isinstance(error, PermissionError) else 400)

# ==========================================================
# PHASE 4: DEPARTMENT OPERATIONS / STAFF REPORTS
# Job-specific operational records are timestamped, tenant-scoped and immediately visible to owner management.
# ==========================================================

@app.post("/api/operations")
@login_required
def api_department_operation_create():
    try:
        payload = request.form.to_dict() if request.form else request.get_json(silent=True) or {}
        row = create_department_operation(app, current_user, payload, request.files.get("evidence")); return jsonify({"ok": True, "message": "Department operation recorded and management tracking updated.", "reference": row.reference})
    except (ValueError, TypeError) as error: db.session.rollback(); return json_error(error)

@app.post("/api/staff-reports")
@login_required
def api_staff_report_generate():
    payload = request.get_json(silent=True) or {}; submit = str(payload.get("action") or "draft").lower() == "submit"
    try:
        row = generate_staff_report(app, current_user, str(payload.get("period_type") or "daily").lower(), payload.get("staff_note"), submit=submit); return jsonify({"ok": True, "message": "Report submitted to management." if submit else "Report draft generated from your tracked SAGE activity.", "reference": row.reference, "status": row.status})
    except (ValueError, TypeError) as error: db.session.rollback(); return json_error(error)

@app.post("/api/staff-reports/<report_id>/acknowledge")
@login_required
@roles_required("owner", "admin")
def api_staff_report_acknowledge(report_id):
    row = StaffReport.query.filter_by(id=report_id, organization_id=current_user.organization_id).first_or_404()
    try:
        acknowledge_staff_report(app, current_user, row); return jsonify({"ok": True, "message": "Staff report acknowledged."})
    except PermissionError as error: db.session.rollback(); return json_error(error, 403)

@app.get("/api/staff-reports/export.<file_format>")
@login_required
@roles_required("owner", "admin")
def api_staff_reports_export(file_format):
    """Download every submitted/acknowledged staff report with its written note and generated activity metrics."""
    if file_format not in {"csv", "xlsx", "pdf"}: abort(404)
    reports = StaffReport.query.filter(StaffReport.organization_id == current_user.organization_id, StaffReport.status.in_(["submitted", "acknowledged"])).order_by(StaffReport.submitted_at.desc(), StaffReport.created_at.desc()).all(); headers = ["Reference","Staff","Department","Period","Period Start","Period End","Status","Submitted At","Acknowledged At","Summary","Staff Note","Operations","Requests","Stock Movements","Asset Movements","Tracked Events"]
    rows = [[row.reference,row.user.display_name if row.user else "Former staff",row.department.name if row.department else "",row.period_type.title(),row.period_start.isoformat(),row.period_end.isoformat(),row.display_status,row.submitted_at.isoformat() if row.submitted_at else "",row.acknowledged_at.isoformat() if row.acknowledged_at else "",row.summary or "",row.staff_note or "",(row.metrics_json or {}).get("operations",0),(row.metrics_json or {}).get("requests",0),(row.metrics_json or {}).get("stock_movements",0),(row.metrics_json or {}).get("asset_movements",0),(row.metrics_json or {}).get("tracked_events",0)] for row in reports]
    payload, mimetype = build_report_export(headers, rows, file_format, "SAGE Staff Reports", f"{current_user.organization.name} · {len(rows)} submitted report(s)"); return send_file(payload, mimetype=mimetype, as_attachment=True, download_name=f"SAGE_Staff_Reports_{datetime.now().strftime('%Y%m%d')}.{file_format}")

# ==========================================================
# LIVE ACTIVITY / NOTIFICATIONS / SECURE EVIDENCE
# ==========================================================

@app.post("/api/activity/page-view")
@login_required
def api_page_view():
    payload = request.get_json(silent=True) or {}; page = (payload.get("page") or "").strip()
    if page in PAGES: record_activity(app, current_user, "page_view", "Page viewed", f"{current_user.display_name} opened {PAGE_TITLES[page][0]}.", "page", page, {"page": page}, notify_owner=False); db.session.commit()
    return jsonify({"ok": True})

@app.get("/api/notifications")
@login_required
def api_notifications():
    # Both organization_id AND user_id are mandatory so another tenant can never appear in this feed.
    rows = Notification.query.filter_by(organization_id=current_user.organization_id, user_id=current_user.id).order_by(Notification.created_at.desc()).limit(40).all()
    return jsonify({"ok": True, "organization_id": current_user.organization_id, "unread": Notification.query.filter_by(organization_id=current_user.organization_id,user_id=current_user.id,is_read=False).count(), "notifications": [{"id": row.id, "title": row.title, "message": row.message, "level": row.level, "entity_type": row.entity_type, "entity_id": row.entity_id, "route": notification_route(row.entity_type, row.title), "created_at": row.created_at.isoformat(), "read": row.is_read} for row in rows]})

@app.post("/api/notifications/read")
@login_required
def api_notifications_read():
    Notification.query.filter_by(organization_id=current_user.organization_id, user_id=current_user.id, is_read=False).update({"is_read": True}); db.session.commit(); return jsonify({"ok": True})

@app.get("/api/notifications/stream")
@login_required
def api_notifications_stream():
    # Robust DB-backed SSE: refreshes the SQLAlchemy session each cycle so new commits are visible immediately.
    user_id, organization_id = current_user.id, current_user.organization_id
    @stream_with_context
    def event_stream():
        db.session.remove(); initial = Notification.query.filter_by(organization_id=organization_id, user_id=user_id).order_by(Notification.created_at.desc()).limit(80).all(); seen = {row.id for row in initial}; heartbeat = 0
        yield f"event: ready\ndata: {json.dumps({'organization_id': organization_id})}\n\n"
        while True:
            db.session.remove(); rows = Notification.query.filter_by(organization_id=organization_id, user_id=user_id).order_by(Notification.created_at.desc()).limit(80).all(); fresh = [row for row in reversed(rows) if row.id not in seen]
            for row in fresh:
                payload = {"id": row.id, "title": row.title, "message": row.message, "level": row.level, "entity_type": row.entity_type, "entity_id": row.entity_id, "route": notification_route(row.entity_type, row.title), "created_at": row.created_at.isoformat()}; seen.add(row.id); yield f"id: {row.id}\nevent: notification\ndata: {json.dumps(payload)}\n\n"
            heartbeat += 1
            if heartbeat % 10 == 0: yield "event: heartbeat\ndata: {}\n\n"
            if len(seen) > 500: seen = {row.id for row in rows}
            time.sleep(1.25)
    return Response(event_stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

@app.get("/evidence/<attachment_id>")
@login_required
def view_evidence(attachment_id):
    attachment = Attachment.query.filter_by(id=attachment_id, organization_id=current_user.organization_id).first_or_404()
    if current_user.role not in {"owner", "admin", "finance"}:
        from services.record_trace_service import get_record
        try: get_record(current_user, attachment.entity_type, attachment.entity_id)
        except (LookupError, ValueError): abort(403)
    try: return attachment_response(app, attachment)
    except FileNotFoundError: abort(404)

# ==========================================================
# PHASE 6/7: REPORT EXPORTS / WEB PUSH / PRODUCTION HEALTH
# ==========================================================

@app.get("/api/reports/export/<report_type>.<file_format>")
@login_required
def api_report_export(report_type, file_format):
    # CEO UPGRADE PHASE 5: one tenant-scoped dataset powers CSV, Excel and PDF for consistent management reporting.
    allowed_reports = {"summary","departments","inventory","requests","procurement","assets","staff","audit","finance","income","expenses","profit-loss","cash-flow","receivables","payables","suppliers","branches"}; allowed_formats = {"csv","xlsx","pdf"}; period = str(request.args.get("period") or "all").strip().lower()
    if report_type not in allowed_reports or file_format not in allowed_formats or period not in {"all","daily","weekly","monthly","quarterly","yearly"}: abort(404)
    if current_user.role not in {"owner","admin","finance","procurement"}: abort(403)
    if current_user.role == "procurement" and report_type not in {"procurement", "requests", "inventory", "assets", "suppliers"}: abort(403)
    try:
        headers, rows = management_export_rows(current_user, report_type, period); title = f"SAGE {report_type.replace('-', ' ').title()} Report"; subtitle = f"{current_user.organization.name} · {period.title()} · {len(rows)} row(s)"; payload, mimetype = build_report_export(headers, rows, file_format, title, subtitle); safe_type = report_type.replace("-", "_").title(); return send_file(payload, mimetype=mimetype, as_attachment=True, download_name=f"SAGE_{safe_type}_{period.title()}_{datetime.now().strftime('%Y%m%d')}.{file_format}")
    except (ValueError, TypeError) as error: return json_error(error)
    except Exception: app.logger.exception("Management report export failed"); return json_error("The report could not be generated.", 500)

@app.get("/api/push/config")
@login_required
def api_push_config(): return jsonify({"ok": True, **public_push_config(app)})

@app.post("/api/push/subscribe")
@login_required
def api_push_subscribe():
    if not push_enabled(app): return json_error("Web push is not configured on this SAGE deployment.", 503)
    try: save_subscription(app, current_user, request.get_json(silent=True) or {}); return jsonify({"ok": True, "message": "Browser notifications enabled for this device."})
    except ValueError as error: return json_error(error)

@app.post("/api/push/unsubscribe")
@login_required
def api_push_unsubscribe():
    payload = request.get_json(silent=True) or {}; disable_subscription(current_user, payload.get("endpoint")); return jsonify({"ok": True})

@app.get("/sw.js")
def service_worker():
    response = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript"); response.headers["Service-Worker-Allowed"] = "/"; response.headers["Cache-Control"] = "no-cache"; return response

@app.get("/manifest.webmanifest")
def web_manifest(): return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")

@app.get("/health")
def health():
    snapshot = health_snapshot(app, deep=False); return jsonify(snapshot), 200 if snapshot["ok"] else 503

@app.get("/ready")
def ready():
    snapshot = health_snapshot(app, deep=True); return jsonify(snapshot), 200 if snapshot["ok"] else 503

# ==========================================================
# PHASE 7: OPERATIONS / RETENTION CLI
# Run `flask --app app sage-retention --dry-run` first, then rerun without --dry-run to apply.
# ==========================================================

@app.cli.command("sage-upgrade-owner-controls")
def sage_upgrade_owner_controls():
    """Create the additive owner-control tables; preserve existing business records."""
    from models import RecordLink, BudgetReservation, ReconciliationMatch, FinanceVerification, CustodyAcknowledgment, ManagementTask, TaskComment, DirectPurchaseLine, ObligationTerms
    tables=[model.__table__ for model in (RecordLink,BudgetReservation,ReconciliationMatch,FinanceVerification,CustodyAcknowledgment,ManagementTask,TaskComment,DirectPurchaseLine,ObligationTerms)]
    db.metadata.create_all(bind=db.engine,tables=tables,checkfirst=True)
    click.echo("Owner control tables are ready; existing records were preserved.")


@app.cli.command("sage-retention")
@click.option("--dry-run", is_flag=True, help="Preview records eligible for retention cleanup without deleting them.")
def sage_retention(dry_run):
    result = apply_retention_policy(app, dry_run=dry_run); click.echo(json.dumps(result, indent=2))

# ==========================================================
# SAGE AI API
# ==========================================================

@app.post("/api/ai/chat")
@login_required
def api_ai_chat():
    payload = request.get_json(silent=True) or {}; message = str(payload.get("message") or "").strip()
    if not message: return json_error("Type a message for SAGE AI.")
    try:
        answer, model = ask_vision_ai(app, current_user, message, payload.get("history") or []); return jsonify({"ok": True, "answer": answer, "model": model})
    except RuntimeError as error: return json_error(error, 503)
    except Exception: app.logger.exception("SAGE AI request failed"); return json_error("SAGE AI could not answer right now. Check the API key/model and try again.", 502)

# ==========================================================
# SAGE DISPLAY PAGE ROUTES
# ==========================================================
# Routes stay explicit in app.py by design; business logic remains in models/services for easier debugging and growth.

@app.route("/dashboard")
@login_required
def dashboard(): return render_vision_page("dashboard")

@app.route("/workspace")
@login_required
def workspace(): return render_vision_page("workspace")

@app.route("/catalog")
@login_required
def catalog(): return render_vision_page("catalog")

@app.route("/analytics")
@login_required
def analytics(): return render_vision_page("analytics")

@app.route("/income")
@login_required
def income(): return render_vision_page("income")

@app.route("/expenses")
@login_required
def expenses(): return render_vision_page("expenses")

@app.route("/finance")
@login_required
def finance(): return render_vision_page("finance")

@app.route("/requests")
@login_required
def requests_page(): return render_vision_page("requests")

@app.route("/operations")
@login_required
def operations(): return render_vision_page("operations")

@app.route("/procurement")
@login_required
def procurement(): return render_vision_page("procurement")

@app.route("/fulfillment")
@login_required
def fulfillment(): return render_vision_page("fulfillment")

@app.route("/inventory")
@login_required
def inventory(): return render_vision_page("inventory")

@app.route("/assets")
@login_required
def assets(): return render_vision_page("assets")

@app.route("/departments")
@login_required
def departments_page(): return render_vision_page("departments")

@app.route("/staff")
@login_required
def staff(): return render_vision_page("staff")

@app.route("/reports")
@login_required
def reports(): return render_vision_page("reports")

@app.route("/audit")
@login_required
def audit(): return render_vision_page("audit")

@app.route("/settings")
@login_required
def settings(): return render_vision_page("settings")

# ==========================================================
# SPA-STYLE PARTIAL PAGE ROUTE / ERRORS
# ==========================================================

@app.route("/partial/<page>")
@login_required
def partial(page):
    if page not in PAGES: abort(404)
    if not can_access_page(current_user, page): abort(403)
    return render_template(f"pages/{page}.html", **page_context(page))

@app.errorhandler(401)
def unauthorized(_error):
    if request.path.startswith("/platform-admin/api/"): return json_error("Platform administrator session required.", 401)
    if request.path.startswith("/platform-admin"): return redirect(url_for("platform_admin_login"))
    return json_error("Authentication required.", 401) if request.path.startswith(("/partial/", "/api/")) else redirect(url_for("login"))

@app.errorhandler(403)
def forbidden(_error): return json_error("You do not have permission to access this area.", 403) if request.path.startswith(("/partial/", "/api/", "/platform-admin/api/")) else (render_template("errors/403.html"), 403)

# ==========================================================
# APPLICATION STARTUP
# ==========================================================

if __name__ == "__main__":
    print("[SAGE] Phases 1-7 loaded: tenant isolation, live notifications, role operations, finance, intelligence and production hardening")
    print(f"[SAGE] Cache protection: per-file asset versioning ENABLED | deployment version {ASSET_VERSION}")
    print("[SAGE] HTML/API no-store + JS/CSS strict revalidation + template auto-reload ENABLED")
    app.run(host=app.config.get("HOST", "0.0.0.0"), port=int(app.config.get("PORT", 5005)), debug=bool(app.config.get("DEBUG", True)))
