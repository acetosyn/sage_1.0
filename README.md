# SAGE — Business Operations, Finance & Accountability Platform

SAGE is a Flask-first multi-tenant business operating system for owners, departments and staff. It keeps traditional Python/Flask architecture while using partial navigation, live events and responsive UI so the workspace behaves more like installed software than a page-by-page website.

## Current development build — Phases 1–7

- **Phase 1:** tenant isolation, authentication, real-time SSE notifications, email escalation and Platform Admin.
- **Phase 2:** role-specific staff workspaces, department catalogue, custom items and department-aware tools.
- **Phase 3:** Acquisition Hub, granted-request completion, inventory/assets and movement/custody history.
- **Phase 4:** department operations plus staff daily/weekly reports and owner drill-down.
- **Phase 5:** finance control centre — accounts, ledger, budgets, AR/AP, payroll, tax, reconciliation and forecasts.
- **Phase 6:** six themes, management intelligence, drill-down reporting, CSV exports, responsive UX and deeper permission-aware SAGE AI context.
- **Phase 7:** PostgreSQL-first production settings, S3/R2 object storage, Web Push, Redis-ready rate limiting, health/readiness checks, deployment files, backups and security hardening.

## Main URLs

```text
Owner/staff login:      http://127.0.0.1:5005/login
New owner registration: http://127.0.0.1:5005/register
Platform admin:         http://127.0.0.1:5005/platform-admin/login
Health probe:           http://127.0.0.1:5005/health
Readiness probe:        http://127.0.0.1:5005/ready
```

## Development

```bash
pip install -r requirements.txt
python app.py
```

Development defaults remain `host=0.0.0.0`, `port=5005`, `debug=True`. SAGE can keep the existing local SQLite database during development, while production should use PostgreSQL.

## Themes

SAGE now includes **Dark, Light, Sky Blue, Sage Green, Warm Sand and Slate**. Theme choice is saved in the browser. The desktop and mobile **Menu** controls are intentionally prominent and glow on hover/focus.

## Management intelligence

The Reports workspace uses real tenant records only. Owner/admin views include income vs expenditure trends, net position, AR/AP, inventory/asset value, budgets, department spending, exception detection and CSV exports. Staff remain scoped to their permitted organization/department data. SAGE AI receives the same permission-aware management context and is instructed not to invent missing business figures.

## Production services

Production can be configured with:

- PostgreSQL + Flask-Migrate/Alembic
- S3 / Cloudflare R2-compatible private evidence storage
- Redis-backed distributed rate limiting
- SMTP email notifications
- VAPID browser Web Push
- Gunicorn/Waitress behind a reverse proxy
- Backup utility in `tools/backup_sage.py`
- `/health` and `/ready` deployment probes

See **`DEPLOYMENT.md`** for the deployment checklist and **`SAGE_PHASES.md`** for the completed roadmap.
