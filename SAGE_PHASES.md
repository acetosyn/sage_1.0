# SAGE — 7-Phase Upgrade Roadmap

## Phase 1 — Platform Foundation, Tenant Isolation & Real-Time Control ✅
- Rename user-facing Vision product to **SAGE** and use the supplied SAGE logo.
- Enforce organization/tenant isolation on notifications, pages, staff, requests, inventory and finance context.
- Add private/no-cache tenant response protection to prevent stale cross-account browser data.
- Replace fragile notification refresh with database-backed **Server-Sent Events + polling fallback** and EMS-style floating live alerts.
- Email owner alerts for meaningful staff actions when SMTP is enabled.
- Add developer-only **Platform Admin Console** for owner/workspace management, restrictions, removal/restore, plan/subscription controls, notes, export, workspace metrics and live activity.
- Remove key dashboard/analytics prototype numbers; charts now use real financial records.

## Phase 2 — Role-Specific Staff Workspaces & Department Item Catalogue
- Load the SAGE Business & Department Item Master Catalogue by organization type + department.
- Unique staff roles, job cards, department actions, item/equipment icons and custom item additions.
- Replace generic staff workspace with real role-specific dashboards.

## Phase 3 — Assets, Stock, Granted Requests & Movement Engine
- Real Add Asset / Add Stock pages.
- Granted-request fulfilment centre for self-procured vs supplied-by-another-person items.
- Asset tags, serials, quantities, store balance, custody, transfers, issue, return, write-off and movement history.

## Phase 4 — Department Operations & Staff Reporting
- Department-specific actions across ICT, Inventory, HR, Maintenance, Transport, Laboratory, Pharmacy, Sales, Projects and other configured units.
- Staff daily/weekly activity reports generated from real actions.
- Owner receives submitted reports and live drill-down activity.

## Phase 5 — Finance & Accounts Control Centre
- Accountant/bank-like finance workspace covering income, revenue, expenses, expenditure, profit/loss, cash flow, budgets, AR/AP, liabilities, payroll, taxes, cost of operations, department spend and forecasts.
- Reconciliation, evidence, financial posting, finance reports and controls.

## Phase 6 — Themes, UX, Reporting & Intelligence
- Add Sky Blue plus at least three additional calm themes alongside Light/Dark.
- Department-specific icons, richer reports, export tools, drill-down charts and polished responsive/mobile UX.
- Expand SAGE AI over authorized business data.

## Phase 7 — Production Hardening & Deployment
- PostgreSQL migration hardening, object storage, background jobs/Redis where needed, email/push delivery, backups, audit retention, security review, performance tuning and deployment readiness.
