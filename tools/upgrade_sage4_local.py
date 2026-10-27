"""Back up and add SAGE 4.0 tables to the active SQLite development database."""
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def fingerprint(connection):
    result={}
    for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        if name.startswith('business_'):continue
        quoted='"'+name.replace('"','""')+'"'
        rows=connection.execute('SELECT * FROM '+quoted).fetchall()
        result[name]={'rows':len(rows),'sha256':hashlib.sha256(repr(sorted(repr(row) for row in rows)).encode()).hexdigest()}
    return result


def main():
    from core.config import Config
    from packages.database import resolve_database_uri,db
    from flask import Flask
    uri,label=resolve_database_uri(Config.DATABASE_URL,ROOT,Config.VISION_SQLITE_FALLBACK)
    if not uri.startswith('sqlite:///'):raise RuntimeError('This helper only upgrades SQLite. Back up PostgreSQL, then use flask --app app sage-upgrade-4.')
    source=Path(uri[len('sqlite:///'):]).resolve()
    if not source.is_file():raise FileNotFoundError('The active SQLite database does not exist.')
    backup_dir=ROOT/'storage'/'backups';backup_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup=backup_dir/f'sage_before_v4_{stamp}.db'
    with sqlite3.connect(source) as existing,sqlite3.connect(backup) as saved:
        before=fingerprint(existing);existing.backup(saved)
    app=Flask(__name__);app.config['SQLALCHEMY_DATABASE_URI']=uri;db.init_app(app)
    import models
    from services.business_schema import install_business_schema
    with app.app_context():created=install_business_schema()
    with sqlite3.connect(source) as existing:
        after=fingerprint(existing)
        integrity=existing.execute('PRAGMA integrity_check').fetchone()[0]
    if before!=after or integrity!='ok':raise RuntimeError('Database verification failed; the pre-upgrade backup has been retained.')
    report={'backend':label,'backup':str(backup),'created_tables':created,'legacy_tables_unchanged':len(before),'integrity':integrity}
    target=backup_dir/f'sage_v4_verification_{stamp}.json';target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
