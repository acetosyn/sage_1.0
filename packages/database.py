# MODULE: SAGE Database Foundation
# Uses PostgreSQL in production, preserves the local SQLite development fallback, and exposes SQLAlchemy/Migrate with connection health checks.

from pathlib import Path
from sqlalchemy import create_engine, text
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate


db = SQLAlchemy(); migrate = Migrate()


# ==========================================================
# DATABASE URI RESOLUTION
# ==========================================================

def _normalize_uri(uri):
    uri = str(uri or "").strip()
    if uri.startswith("postgres://"): return "postgresql+psycopg://" + uri[len("postgres://"):]
    if uri.startswith("postgresql://") and "+" not in uri.split("://", 1)[0]: return "postgresql+psycopg://" + uri[len("postgresql://"):]
    return uri


def resolve_database_uri(preferred_uri, base_dir, allow_sqlite_fallback=True):
    """Use configured PostgreSQL; local SQLite is permitted only when the environment explicitly allows the development fallback."""
    preferred_uri = _normalize_uri(preferred_uri); fallback_uri = f"sqlite:///{(Path(base_dir) / 'vision_dev.db').as_posix()}"
    if not preferred_uri:
        if not allow_sqlite_fallback: raise RuntimeError("DATABASE_URL is required because SAGE_SQLITE_FALLBACK is disabled.")
        return fallback_uri, "SQLite development fallback"
    if preferred_uri.startswith("sqlite"): return preferred_uri, "SQLite"
    try:
        engine = create_engine(preferred_uri, pool_pre_ping=True, connect_args={"connect_timeout": 3} if preferred_uri.startswith("postgresql") else {})
        with engine.connect() as connection: connection.execute(text("SELECT 1"))
        engine.dispose(); return preferred_uri, "PostgreSQL" if preferred_uri.startswith("postgresql") else "Configured database"
    except Exception as error:
        if not allow_sqlite_fallback: raise RuntimeError(f"Configured SAGE database is unavailable: {error}") from error
        print(f"[SAGE DATABASE] PostgreSQL unavailable; using local development fallback. Reason: {error}"); return fallback_uri, "SQLite development fallback"


# ==========================================================
# DATABASE INITIALIZATION
# ==========================================================

def init_database(app):
    """Resolve the active database, initialize SQLAlchemy/Migrate and publish a safe backend label for diagnostics."""
    uri, label = resolve_database_uri(app.config.get("DATABASE_URL") or app.config.get("SQLALCHEMY_DATABASE_URI"), app.config["BASE_DIR"], app.config.get("VISION_SQLITE_FALLBACK", True)); app.config["SQLALCHEMY_DATABASE_URI"] = uri
    if uri.startswith("sqlite"): app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    db.init_app(app); migrate.init_app(app, db); app.extensions["vision_database_label"] = label; return label
