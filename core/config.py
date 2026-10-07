# MODULE: SAGE Application Configuration
# Central environment-backed configuration for Flask, PostgreSQL, secure storage, platform administration, notifications, AI, themes and production deployment.

import os
from pathlib import Path
from dotenv import load_dotenv

# ==========================================================
# ENVIRONMENT / PATHS
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _flag(name, default="false"): return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

def _integer(name, default):
    try: return int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError): return int(default)


# ==========================================================
# FLASK / DATABASE / STORAGE / EMAIL / AI / PRODUCTION
# ==========================================================

class Config:
    BASE_DIR = BASE_DIR
    ENVIRONMENT = (os.getenv("SAGE_ENV") or os.getenv("FLASK_ENV") or "development").strip().lower()
    DEBUG = _flag("SAGE_DEBUG", "true" if ENVIRONMENT != "production" else "false")
    HOST = os.getenv("SAGE_HOST", "0.0.0.0").strip() or "0.0.0.0"
    PORT = _integer("SAGE_PORT", 5005)

    SECRET_KEY = os.getenv("SECRET_KEY", "sage-development-secret")
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": _integer("DB_POOL_RECYCLE", 1800), "pool_size": _integer("DB_POOL_SIZE", 10), "max_overflow": _integer("DB_MAX_OVERFLOW", 20)} if DATABASE_URL and not DATABASE_URL.startswith("sqlite") else {"pool_pre_ping": True}
    TEMPLATES_AUTO_RELOAD = ENVIRONMENT != "production"
    SEND_FILE_MAX_AGE_DEFAULT = 0 if ENVIRONMENT != "production" else _integer("STATIC_CACHE_SECONDS", 3600)
    VISION_SQLITE_FALLBACK = _flag("SAGE_SQLITE_FALLBACK", "true" if ENVIRONMENT != "production" else "false")
    AUTO_CREATE_SCHEMA = _flag("SAGE_AUTO_CREATE_SCHEMA", "true" if ENVIRONMENT != "production" else "false")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE", "true" if ENVIRONMENT == "production" else "false")
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = _integer("SESSION_LIFETIME_SECONDS", 43200)
    TRUST_PROXY_HEADERS = _flag("TRUST_PROXY_HEADERS", "true" if ENVIRONMENT == "production" else "false")
    FORCE_HTTPS = _flag("FORCE_HTTPS", "false")

    PLATFORM_ADMIN_USERNAME = (os.getenv("SAGE_ADMIN_USERNAME") or os.getenv("PLATFORM_ADMIN_USERNAME") or os.getenv("ADMIN_USERNAME") or os.getenv("ADMIN_USER") or os.getenv("SUPER_ADMIN_USERNAME") or os.getenv("DEVELOPER_USERNAME") or "").strip()
    PLATFORM_ADMIN_PASSWORD = (os.getenv("SAGE_ADMIN_PASSWORD") or os.getenv("PLATFORM_ADMIN_PASSWORD") or os.getenv("ADMIN_PASSWORD") or os.getenv("ADMIN_PASS") or os.getenv("SUPER_ADMIN_PASSWORD") or os.getenv("DEVELOPER_PASSWORD") or "").strip()

    STORAGE_BACKEND = os.getenv("SAGE_STORAGE_BACKEND", "local").strip().lower() or "local"
    STORAGE_DIR = Path(os.getenv("SAGE_STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
    MAX_UPLOAD_MB = _integer("MAX_UPLOAD_MB", 12)
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
    S3_REGION = os.getenv("S3_REGION", "auto").strip()
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "").strip()
    S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "").strip()
    S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "").strip()
    S3_PRESIGNED_SECONDS = _integer("S3_PRESIGNED_SECONDS", 300)

    EMAIL_NOTIFICATIONS_ENABLED = _flag("EMAIL_NOTIFICATIONS_ENABLED", "false")
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = _integer("SMTP_PORT", 587)
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "").strip()
    SMTP_USE_TLS = _flag("SMTP_USE_TLS", "true")

    WEB_PUSH_ENABLED = _flag("WEB_PUSH_ENABLED", "false")
    VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "").strip()

    REDIS_URL = os.getenv("REDIS_URL", "").strip()
    RATELIMIT_STORAGE_URI = REDIS_URL or "memory://"
    SAGE_BACKUP_DIR = Path(os.getenv("SAGE_BACKUP_DIR", str(BASE_DIR / "backups"))).resolve()
    AUDIT_RETENTION_DAYS = _integer("SAGE_AUDIT_RETENTION_DAYS", 2555)
    NOTIFICATION_RETENTION_DAYS = _integer("SAGE_NOTIFICATION_RETENTION_DAYS", 365)

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL_SOLVER = os.getenv("OPENAI_MODEL_SOLVER", "gpt-5.4").strip()
    OPENAI_MODEL_VERIFIER = os.getenv("OPENAI_MODEL_VERIFIER", "gpt-5.4").strip()
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
