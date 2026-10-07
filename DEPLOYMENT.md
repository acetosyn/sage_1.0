# SAGE Production Deployment — Phase 7

SAGE remains easy to run locally, but Phase 7 adds the pieces needed for a public multi-tenant deployment.

## 1. Production environment

Use a strong `SECRET_KEY`, PostgreSQL and HTTPS. Recommended production flags:

```env
SAGE_ENV=production
SAGE_DEBUG=false
SAGE_SQLITE_FALLBACK=false
SESSION_COOKIE_SECURE=true
TRUST_PROXY_HEADERS=true
FORCE_HTTPS=true
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/sage
```

Do not commit `.env`.

## 2. Database migrations

Development still supports `db.create_all()` through `SAGE_AUTO_CREATE_SCHEMA=true` so the current project remains simple to test. Before a controlled production release, use Flask-Migrate/Alembic:

```bash
# One-time setup when the project has no migrations folder
flask --app app db init

# Create and review a migration whenever models change
flask --app app db migrate -m "SAGE schema"
flask --app app db upgrade
```

After migrations are established in production, set:

```env
SAGE_AUTO_CREATE_SCHEMA=false
```

This prevents application startup from being used as a schema-management mechanism.

## 3. Object storage for receipts and evidence

Local files remain the development default. For Cloudflare R2, Amazon S3 or another S3-compatible service:

```env
SAGE_STORAGE_BACKEND=s3
S3_BUCKET=your-private-bucket
S3_REGION=auto
S3_ENDPOINT_URL=https://YOUR-ENDPOINT
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_PRESIGNED_SECONDS=300
```

Buckets should remain private. SAGE stores only object keys in PostgreSQL and creates short-lived signed URLs for authorized users.

## 4. Web Push

SAGE can send device/browser notifications when VAPID is configured:

```env
WEB_PUSH_ENABLED=true
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_SUBJECT=mailto:admin@yourdomain.com
```

Web Push requires HTTPS in production. Users enable it from **Settings → Browser / Device Notifications**.

## 5. Redis / distributed rate limiting

Redis is optional locally. For multi-worker/multi-instance deployment set:

```env
REDIS_URL=redis://USER:PASSWORD@HOST:6379/0
```

Flask-Limiter then uses Redis instead of process-local memory.

## 6. Production server

Linux / container:

```bash
gunicorn --workers 3 --threads 4 --timeout 120 --bind 0.0.0.0:8000 wsgi:app
```

Windows server:

```bash
waitress-serve --host=0.0.0.0 --port=8000 wsgi:app
```

The included `Dockerfile` and `Procfile` are deployment-ready starting points.

## 7. Health checks

- `/health` — database + storage readiness
- `/ready` — deeper readiness check, including Redis when configured

No tenant records or credentials are returned from either endpoint.

## 8. Backups

Run:

```bash
python tools/backup_sage.py
```

For PostgreSQL it calls `pg_dump`. For local SQLite it creates a database copy. Local evidence storage is zipped when local storage is enabled. Production object-storage versioning/lifecycle backups should be enabled at the storage provider.

## 9. Security checklist

- Replace all development passwords/keys.
- Keep SAGE Platform Admin credentials separate from organization-owner credentials.
- Use PostgreSQL with encrypted provider connections.
- Use HTTPS and secure cookies.
- Keep object-storage buckets private.
- Configure SMTP/Web Push with provider secrets only in environment variables.
- Run migrations before each release.
- Back up PostgreSQL and evidence independently.
- Review `/ready` after deploy.
- Test tenant isolation using separate browser profiles for separate owners.
