# TOOL: SAGE Database + Local Storage Backup
# Run manually or from cron/scheduler. PostgreSQL uses pg_dump; SQLite is copied safely; local evidence can be archived with the database backup.

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent; load_dotenv(BASE_DIR / ".env")
BACKUP_DIR = Path(os.getenv("SAGE_BACKUP_DIR", BASE_DIR / "backups")).resolve(); BACKUP_DIR.mkdir(parents=True, exist_ok=True)
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S"); DATABASE_URL = os.getenv("DATABASE_URL", "").strip(); storage = Path(os.getenv("SAGE_STORAGE_DIR", BASE_DIR / "storage")).resolve()


def backup_database():
    if DATABASE_URL.startswith("postgresql"):
        target = BACKUP_DIR / f"sage_postgres_{STAMP}.dump"; command = ["pg_dump", "--format=custom", "--file", str(target), DATABASE_URL]
        subprocess.run(command, check=True); return target
    sqlite_path = BASE_DIR / "vision_dev.db"
    if DATABASE_URL.startswith("sqlite:///"): sqlite_path = Path(DATABASE_URL.replace("sqlite:///", "", 1)).resolve()
    if not sqlite_path.exists(): raise FileNotFoundError(f"Database not found: {sqlite_path}")
    target = BACKUP_DIR / f"sage_sqlite_{STAMP}.db"; shutil.copy2(sqlite_path, target); return target


def backup_storage():
    if os.getenv("SAGE_STORAGE_BACKEND", "local").strip().lower() != "local" or not storage.exists(): return None
    target_base = BACKUP_DIR / f"sage_storage_{STAMP}"; archive = shutil.make_archive(str(target_base), "zip", root_dir=storage); return Path(archive)


if __name__ == "__main__":
    try:
        database_file = backup_database(); storage_file = backup_storage(); print(f"[SAGE BACKUP] Database: {database_file}"); print(f"[SAGE BACKUP] Storage: {storage_file or 'external/object storage - not archived locally'}")
    except Exception as error: print(f"[SAGE BACKUP] FAILED: {error}", file=sys.stderr); raise
