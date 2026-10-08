# SAGE Business OS — Updated Backend & Frontend Architecture Reference

> **Purpose:** Complete technical reference for the current SAGE Business OS after the Vision prototype, SAGE rebrand, Phase 1–Phase 8 implementation programme, Owner/Individual Business upgrade, onboarding/catalogue corrections, SAGE Guide/Pulse notification refinements, mobile refinements and EMIS-style automatic cache protection.

> **Revision:** 7 October 2026

> **Current upgrade state:** Vision foundation migrated to SAGE; Phase 1–Phase 8 implemented; post-Phase-8 refinements implemented; CEO/Owner Management Upgrade Phases 1–5 implemented on 7 October 2026.

> **Scope:** Flask application architecture, PostgreSQL/SQLite database strategy, multi-tenant isolation, authentication, owner/staff/platform-admin access, organization and individual-business workspaces, business/department catalogue, requests/approvals, funding, acquisition evidence, inventory, assets, department operations, finance, staff reports, management reporting, notifications, SAGE Pulse, SAGE Guide, SAGE AI, object storage, production hardening, SPA-style navigation, deployment/cache rules and the main files/routes that now make up SAGE.

---

# Table of Contents

1. Current Architecture Snapshot
2. Development and Upgrade History
3. Product / Workspace Modes
4. Multi-Tenant, Identity and Access Rules
5. Business Types, Departments and Catalogue Architecture
6. Core End-to-End Accountability Workflows
7. Database Architecture and Main Models
8. Backend Service / Module Reference
9. Frontend / UI Architecture
10. Authentication, Registration and Staff Management
11. Requests, Approvals, Funding and Acquisition
12. Inventory, Assets and Department Operations
13. Finance & Accounts Control Centre
14. Owner Dashboards, Reports and Management Intelligence
15. Notifications, SAGE Pulse, SAGE Guide and SAGE AI
16. Platform Admin / Developer Console
17. Evidence, File Storage and Document Security
18. Routes and API Map
19. SPA Navigation, Themes, Mobile and UX Rules
20. Deployment, Production Hardening and Cache Protection
21. Current Pending / Future Expansion Areas
22. Quick File Guide
23. Validation and Safety Summary
24. Current Architecture Summary

---

# 1. Current Architecture Snapshot

SAGE is a Flask-first, multi-tenant business operating system designed to answer the management questions:

```text
What did the business earn?
What did it spend?
What does it own?
What stock does it hold?
What moved?
Who requested it?
Who approved it?
Who bought / received / moved it?
What evidence supports the action?
What is the financial effect?
```

The current build is no longer only an inventory prototype. It now combines:

- organization and individual-business registration;
- owner, staff and platform-admin access;
- role-based page visibility;
- strict organization/tenant isolation;
- configurable departments;
- 10 organization templates and a large department item catalogue;
- request and approval workflow;
- owner budget/funding records;
- Stage 2 acquisition logging;
- receipt and optional item-photo evidence;
- inventory and stock movement;
- asset registration and movement;
- department-specific operations;
- staff daily/weekly/monthly/quarterly reporting;
- finance accounts, ledger, budgets, receivables, payables, reconciliation, payroll, tax and forecasting;
- real-time notifications;
- SAGE Pulse login/recurring briefing;
- SAGE Guide contextual help;
- OpenAI-backed SAGE AI;
- platform-owner administration;
- private evidence storage;
- CSV exports;
- themes, mobile support and SPA-style page transitions;
- production hardening, health checks, push support and retention tools;
- automatic static cache-busting based on the EMIS cache-protection design.

## Current high-level chain

```text
                    SAGE PLATFORM
                         │
        ┌────────────────┴────────────────┐
        │                                 │
        ▼                                 ▼
ORGANIZATION WORKSPACE             INDIVIDUAL BUSINESS
(multi-department)                 (lean owner-operated)
        │                                 │
        ▼                                 ▼
Owner / Admin                    Owner / Entrepreneur
        │                                 │
        ├── Departments                   ├── Income / Expenses
        ├── Staff                         ├── Stock / Assets
        ├── Requests                      ├── AR / AP
        ├── Finance                       ├── Reports
        ├── Inventory                     └── SAGE AI
        ├── Assets
        ├── Operations
        └── Reports
```

## Current accountability chain

```text
Staff Need / Business Event
          ↓
Request or Direct Record
          ↓
Approval / Budget / Funding
          ↓
Actual Purchase / Delivery / Receipt
          ↓
Evidence + Actual Quantity + Actual Cost
          ↓
Inventory / Asset / Finance Posting
          ↓
Audit Event + Owner Notification
          ↓
Dashboard / Report / SAGE AI
```

---

# 2. Development and Upgrade History

# Foundation — Vision Prototype

## Purpose

The project began as **Vision**, a global business operations and stock/financial tracking application, not an Epiconsult-only system.

The original UI target was the Zenith-style dashboard supplied by the project owner: persistent sidebar, top bar, compact cards, charts, responsive mobile drawer, light/dark appearance and software-like navigation.

## Main foundation decisions

- Flask remained the main backend framework.
- React was not required for the application shell.
- Smooth navigation was implemented with normal Flask templates plus JavaScript Fetch/History/View-Transition-style behavior.
- Full-page reloads were reduced by loading partial page content into the persistent app shell.
- Main page routes remained explicit in `app.py` for easier debugging.
- Business logic was separated into `models/`, `services/`, `packages/` and `core/`.
- The app was initially named Vision and later fully renamed SAGE.

## Initial UI foundation

The first prototype included:

- responsive desktop/mobile shell;
- collapsible sidebar;
- top search / command experience;
- light and dark modes;
- dashboard cards and charts;
- Finance, Analytics, Requests, Procurement, Inventory, Assets, Departments, Staff, Reports, Audit and Settings pages;
- login and registration prototypes;
- SAGE AI/assistant placeholder;
- SPA-style partial routing.

---

# Authentication Foundation — Real Owners, Staff and Database

The prototype authentication pages were upgraded into real database-backed registration/login.

## Main changes

- PostgreSQL selected as the production database direction.
- SQLAlchemy used as ORM.
- Flask-Login used for sessions.
- secure password hashing used instead of plain-text passwords;
- Owner registration creates the first organization owner account;
- Staff use private invitation links instead of the public owner-registration URL;
- Owner can select department and role before generating a staff link;
- Staff profile captures identity/employment information;
- default role/permission framework introduced;
- organization departments become configurable database records;
- OpenAI integration introduced for SAGE AI;
- Groq configuration reserved for later receipt/document analysis use;
- `.env` introduced for API keys and platform configuration.

---

# Core Accountability Upgrade — Request to Evidence

Before the numbered SAGE phases, the core concept-note workflow was implemented:

```text
Request
  ↓
Approval
  ↓
Money Sent / Granted
  ↓
Purchase / Delivery
  ↓
Receipt / Evidence
  ↓
Final Confirmation
  ↓
Inventory / Expense / Audit
```

Key decisions:

- `Money Sent` is an accountability status only; SAGE does not transfer money.
- Staff may save uncertain acquisition information as Draft.
- Final confirmation is treated as a locked accountability record.
- Receipt/evidence is linked to the transaction.
- Owner receives visibility into requester, approver, purchaser/receiver, department, amount, quantity, time and evidence.

---

# Staff Management Expansion

Owner Staff Management was expanded with:

1. Remove Staff (soft-delete/archive)
2. Restore Removed Staff
3. Suspend / Reactivate Account
4. Edit Staff Profile
5. Transfer Staff to Another Department
6. Change Role / Access Level
7. View Individual Staff Activity
8. Accountability statistics
9. Filters by department/role/status/search
10. Bulk actions
11. CSV export
12. Session/access blocking for suspended/removed users

Historical requests, receipts and audit actions remain preserved when a staff account is removed.

---

# Phase 1 — SAGE Foundation, Tenant Isolation and Platform Administration

## Main goals

- Rename Vision → **SAGE**.
- Fix organization data leakage.
- Implement robust live activity/notification foundation.
- Create a developer-only platform management console.
- Remove fake dashboard data where touched.

## Main changes

- SAGE branding and application naming introduced.
- Strict `organization_id` scoping reinforced across users, requests, inventory, finance, notifications and activity.
- Session is bound to the signed-in tenant using `sage_tenant_org_id`.
- Cross-tenant notification leakage fixed.
- Database-backed Server-Sent Events (SSE) introduced for live feeds.
- SMTP email notification infrastructure introduced.
- Developer-only `/platform-admin` area created.
- Platform Admin controls include view, search, filter, restrict/disable, restore, subscription/plan state, developer notes, drill-down, export and live activity.
- Tenant pages use private/no-cache behavior to reduce stale cross-account display risk.
- Prototype financial figures in touched sections replaced by live database values / empty states.

---

# Phase 2 — Role-Specific Staff Workspaces + Master Catalogue

## Purpose

Staff should not all see the same generic workspace. Their tools must match their department and real job responsibilities.

## Main changes

- `Department Workspace` became role/department aware.
- `My Catalogue` / Department Catalogue introduced.
- Catalogue seeded from the SAGE Business & Department Item Master Catalogue.
- 10 organization templates supported.
- 130 department catalogues represented.
- 7,344 item assignments used as starting catalogue data.
- Items include role-relevant icons rather than plain text only.
- Search and category filtering added.
- Custom items can be added per organization/department.
- Catalogue items can prefill a request.
- Typical roles and job focus are displayed by department/position.
- Staff sidebar identity improved to show position + department.

## Catalogue principle

```text
Seed, not lock.
```

Organizations can extend the catalogue with their own items instead of being limited to hard-coded lists.

---

# Phase 3 — Platform Admin Redesign + Acquisition / Asset / Movement Engine

## Platform Admin changes

The Platform Console was redesigned for desktop and mobile.

`Disable` and `Delete Permanently` became separate actions:

```text
Disable
→ Owner and staff cannot sign in
→ Data remains
→ Restore is possible

Delete Permanently
→ Requires typing DELETE
→ Warns that all tenant data will be removed
→ Removes organization/workspace permanently
```

Additional console work:

- responsive sidebar / mobile toggle;
- owner cards;
- KPI cards;
- live activity;
- notification panel;
- developer audit;
- status/subscription controls;
- tenant detail inspection.

## Operational changes

- Dedicated **Acquisition Hub** added.
- Granted requests can be completed as Stock/Consumable or Asset/Equipment.
- Self-purchased vs supplied by another person supported.
- Draft vs final acquisition state supported.
- Receipt/invoice evidence integrated.
- real Asset Register introduced;
- asset tags, serials, department, custodian, location, condition, acquisition and warranty supported;
- asset movements supported;
- inventory movement supported;
- cross-department stock transfers supported;
- movement history retains actor, destination, reason and time.

---

# Phase 4 — Department Operations + Staff Reports

## Purpose

Add job-specific activity logging beyond generic Requests and Assets.

## Department-operation examples

- ICT: assignment, repair/replacement, subscriptions, network changes, downtime, consumable use.
- Inventory: receive, issue, count, variance, reorder, bin/store changes.
- HR: payroll inputs, claims, advances, training cost, staff assets.
- Maintenance: work orders, repairs, spare usage, preventive maintenance, contractor work.
- Transport: fuel, trips, repairs, assignment, fleet incidents.
- Laboratory: reagent/consumable use, analyzer service, expiry/wastage, referrals.
- Pharmacy: medicine receipt, issue/dispense, expiry/write-off, cold-chain, transfer.
- Procurement, Security, Kitchen, Housekeeping, Production, Quality, Sales, Projects and custom departments use appropriate generic/specialized action templates.

Every operation is timestamped, tenant-scoped and linked to the staff/department.

## Staff reports

Staff can generate:

```text
Daily Report
Weekly Report
Monthly Report
Quarterly Report
```

Reports derive from actual tracked activity, requests, stock movements, asset movements and department operations.

Workflow:

```text
Generate Draft
→ Review
→ Submit to Owner
→ Owner Acknowledge
→ Staff receives acknowledgement notification
```

---

# Phase 5 — Finance & Accounts Control Centre

Phase 5 converted Finance into a bank/accountant-style operational workspace.

## Implemented finance areas

1. Cash / Bank / POS / Wallet / Petty-Cash Accounts
2. General Ledger
3. Budgets / Cost Centres
4. Accounts Receivable
5. Accounts Payable
6. Reconciliation
7. Payroll
8. Tax Register
9. Financial Forecasts
10. Finance Reports
11. Committed vs Actual Spend
12. Finance Evidence
13. CSV Ledger Export

## Finance scope

The app now tracks the business concepts requested for the product:

```text
Income
Revenue
Expenses
Expenditure
Profit
Loss
Cash Flow
Budgets
Accounts Receivable
Accounts Payable
Assets
Liabilities
Inventory Value
Payroll
Procurement
Taxes
Cost of Operations
Financial Forecasting
Department Spending
Financial Reports
```

---

# Phase 6 — Themes, Reporting and Management Intelligence

## Themes

The appearance system was expanded beyond Dark/Light.

Current theme family includes:

- Dark
- Light
- Sky Blue
- Sage Green
- Warm Sand
- Slate

## Reporting / intelligence

- Management Intelligence area added.
- Income vs expenditure trend.
- Department financial comparison.
- Net position.
- AR/AP.
- Inventory and asset value.
- Budget actual/committed/available.
- Management exception centre.
- Department financial drill-down.
- CSV exports for summary, departments, inventory and requests.
- SAGE AI context expanded with authorized business intelligence.

No fake report data is created: empty database state remains zero/empty.

---

# Phase 7 — Production Hardening

## Production-oriented additions

- PostgreSQL-first production configuration.
- Development SQLite fallback retained.
- Flask-Migrate/Alembic foundation.
- `AUTO_CREATE_SCHEMA` behavior separated for development/production.
- S3/Cloudflare-R2-compatible private object storage architecture.
- Signed evidence links.
- Web Push support.
- SSE live notifications retained.
- SMTP/email retained.
- Service Worker.
- Redis-ready rate limiting.
- secure cookies / proxy support.
- security headers / CSP foundation.
- `/health` and `/ready` endpoints.
- production WSGI entry point.
- Gunicorn / Waitress support.
- Dockerfile / Procfile support.
- backup utility.
- audit/notification retention controls.
- platform permanent-delete cleanup expanded across newer tables/evidence.

---

# Phase 8 — Stage 2 Acquisition Logging + Actual Financial Posting

## Main correction

An approved request must not stop at `Approved`.

Staff now have a second-stage acquisition record for the granted request.

Example:

```text
Requested:
2 Laptops × NGN 400,000 = NGN 800,000

Owner:
Approved Budget = NGN 800,000
Money Sent      = NGN 800,000

Stage 2 Actual:
Actual Quantity = 2
Actual Unit Cost = NGN 400,000
Actual Total     = NGN 800,000
Receipt          = required
Item Photo       = optional
```

## Stage 2 captures

- requested quantity;
- actual quantity;
- requested unit price;
- actual unit price;
- actual total;
- purchase date;
- delivered/received date/time;
- supplier;
- store/current location;
- self-procured vs supplied by another person;
- staff/source details;
- notes/shortage/substitution;
- receipt/invoice;
- optional item photograph;
- draft/final state.

## Funding record

Owner/Finance can record:

- approved budget;
- amount sent/released;
- payment method;
- reference;
- management note;
- `Money Sent / Granted` status.

SAGE records the funding decision but does not transfer money.

## Actual vs requested rule

Inventory/Asset posting uses actual confirmed figures, not the original request figures.

```text
Requested 10
Actual delivered 8
→ SAGE posts 8
```

## Financial snapshot expansion

Owner dashboard now surfaces:

- Income / Revenue
- Expenses
- Profit/Loss
- Cash Flow
- Active Budgets
- Procurement Budgets
- Actual Procurement
- Procurement Variance
- Accounts Receivable
- Accounts Payable
- Inventory Value
- Asset Value
- Payroll Paid
- Tax Due

---

# Post-Phase-8 Refinement — Onboarding Department Auto-Selection

A regression caused organization registration to stop automatically listing departments.

The onboarding flow was corrected so choosing an organization type automatically preselects the full recommended department template.

Example — School / Educational Institution:

```text
Administration
Finance & Accounts
Human Resources
Academic / Classroom
ICT / Computer Laboratory
Science Laboratory
Library
Procurement
Stores / Inventory
Maintenance
Transport
Security
Admissions / Marketing / PR
Sports / Physical Education
```

The owner can still:

- uncheck/remove any suggested department;
- Select All;
- Clear All;
- add custom departments;
- preserve custom additions while moving between setup steps.

Catalogue names were synchronized to the department template naming so department→catalogue matching works consistently.

---

# Post-Phase-8 Refinement — Organization vs Individual / Entrepreneur Workspace

Owner registration now begins by asking which type of workspace is being created.

```text
Organization / Company
or
Individual / Entrepreneur
```

## Organization / Company

Uses the existing:

```text
Owner
→ Business Type
→ Suggested Departments
→ Staff / Roles
→ Organization Dashboard
```

## Individual / Entrepreneur

Designed for a sole trader, freelancer or owner-operated business with no staff or only a very small team.

Individual owners do not need to manage a large artificial department hierarchy.

### Individual business categories

- Retail Shop / Mini Mart / Boutique
- Online Store / E-commerce
- Food / Catering / Bakery
- Technology / Digital Services
- Freelancer / Professional Services
- Consulting / Coaching / Training
- Creative / Media / Photography
- Fashion / Tailoring
- Beauty / Salon / Spa
- Transport / Delivery
- Construction / Artisan / Handyman
- Agriculture / Farm / Agro-business
- Health / Wellness
- Real Estate / Property Services
- Other / Custom Business

### Individual dashboard focus

```text
Today
This Week
This Month
This Year
```

with:

- income;
- expenses;
- net position;
- profit margin;
- receivables;
- supplier obligations;
- stock value;
- asset value;
- low-stock state;
- recent transactions;
- SAGE AI.

Organization-only fields are hidden entirely from Individual setup rather than merely disabled.

---

# Post-Phase-8 Refinement — Owner Request Management

Organization owners are no longer allowed to create purchase requests to themselves.

Backend rule:

```text
Owner POST /api/requests
→ rejected
```

Owners instead use Finance, Inventory, Assets or Quick Record for direct owner-side entries.

## Request management additions

- structured request cards;
- department label;
- requester and position;
- amount;
- item count;
- purpose;
- date/time;
- urgency;
- status/stage;
- approval/funding actions;
- department request intelligence;
- Excel-like request ledger;
- filters by department/status/search;
- sorting by reference/date/amount;
- urgency states Normal/Urgent/Critical;
- CSV request export.

---

# Post-Phase-8 Refinement — SAGE Guide

Because SAGE now contains many pages, cards and workflows, an optional contextual-help system was added.

## Desktop behavior

Hover/focus over supported navigation items and components can show a brief explanation of what the area does.

## Mobile behavior

Mobile does not depend on hover. A dedicated Guide control/drawer provides the same context using touch interaction.

## Preference

Guide can be turned **On/Off** so users who do not want contextual hints are not forced to keep them enabled.

---

# Post-Phase-8 Refinement — Daily Briefing and SAGE Pulse

The original large briefing was converted into a compact floating **SAGE Pulse** card.

## Login behavior

After successful login:

```text
Login
→ unique briefing token
→ server prepares briefing
→ Pulse visibly renders
→ browser acknowledges token
```

The briefing is not considered consumed merely because the API was fetched.

## Pulse content

Depending on role/permissions, slides can summarize:

- today's income;
- today's expenses;
- net position;
- pending/urgent requests;
- approved/funded acquisitions waiting for evidence;
- inventory value;
- low stock;
- asset value;
- receivables/payables;
- unread alerts;
- department activity.

## Pulse behavior

- compact card near the right edge on desktop;
- compact top-area card on mobile;
- close button;
- previous/next;
- slide counter;
- link to related page;
- one full sequence immediately after login;
- recurring single status Pulse every 5 minutes;
- real-time staff activity still appears immediately through live notification flow;
- notification bell remains history/drawer access.

---

# Post-Phase-8 Refinement — Sidebar / Logo / Mobile Polish

- desktop sidebar width reduced;
- collapse toggle moved to a visible topbar position;
- `Menu` text removed from the desktop collapse control;
- hover/glow state added;
- mobile uses hamburger-style behavior;
- collapsed sidebar shows small icon labels on hover/focus;
- SAGE wordmark spacing/alignment refined;
- `A`, `G`, `E` spacing corrected;
- mobile Pulse reduced and moved higher under the header;
- mobile Guide retained;
- mobile-first behavior treated as a requirement for new UX changes unless technically impossible.

---

# Post-Phase-8 Refinement — EMIS-Style Automatic Cache Protection

SAGE adopted the proven EMIS cache/version strategy so frontend replacements do not normally require manual `Ctrl + F5`.

## Current intended behavior

- `SEND_FILE_MAX_AGE_DEFAULT = 0` style protection;
- template auto reload;
- per-file static version based on physical file modification metadata;
- Jinja `url_for('static', ...)` automatically receives version values;
- hardcoded `/static/...` `src`/`href`/`poster` links can be rewritten with version values;
- HTML uses no-store/private policy;
- API/partial responses use no-store policy;
- JS/CSS/MJS use strict cache protection;
- images/fonts revalidate;
- Python backend changes still require Flask/WSGI restart.

---

# 3. Product / Workspace Modes

# 3.1 Organization Workspace

Used for multi-department organizations such as:

- schools;
- hospitals/clinics;
- hotels;
- factories;
- retail/supermarkets;
- construction/engineering;
- logistics/transport;
- restaurants/catering;
- technology/software companies;
- NGOs/non-profits.

Typical hierarchy:

```text
Organization
  ↓
Department
  ↓
Staff User
  ↓
Role / Permission
```

# 3.2 Individual / Entrepreneur Workspace

Used for owner-operated businesses.

Typical structure:

```text
Individual Business
  ↓
Owner
  ↓
Income / Expense / Stock / Assets / AR / AP / Reports
```

No unnecessary multi-department onboarding is forced on these users.

# 3.3 Platform Admin Workspace

Separate from tenant authentication.

Used only by the SAGE developer/platform administrator for owner/workspace control.

---

# 4. Multi-Tenant, Identity and Access Rules

# 4.1 Tenant authority

Every important tenant-owned record is scoped by:

```text
organization_id
```

This applies to areas such as:

- users;
- departments;
- requests;
- finance;
- inventory;
- assets;
- evidence;
- notifications;
- activity events;
- catalogue additions;
- reports.

# 4.2 Session binding

Authenticated tenant sessions bind:

```text
session['sage_tenant_org_id']
```

If the active user no longer matches the bound tenant, SAGE signs the user out rather than serving mixed-tenant content.

# 4.3 Browser-tab note

Two tabs in the same browser profile share the same login cookie. Simultaneous testing of two owners should use separate browser profiles/incognito/different browsers.

# 4.4 Current operational roles

Current code uses roles including:

```text
owner
admin
finance
procurement
department_head
staff
```

# 4.5 Visibility principles

Owner/Admin:

- organization-wide dashboard;
- all departments;
- staff management;
- requests and approvals;
- finance;
- inventory/assets;
- reports/audit;
- configuration.

Finance:

- permitted finance pages;
- finance records and controls;
- authorized organization-wide financial visibility.

Procurement:

- procurement/request/inventory areas as permitted.

Department Head / Staff:

- own department context;
- own/department requests;
- permitted operations;
- relevant catalogue;
- relevant stock/assets;
- own reports;
- no cross-tenant access.

# 4.6 Backend protection rule

Pages are not merely hidden in the sidebar.

`can_access_page()` and role guards protect server routes/APIs so typing a restricted URL directly does not grant access.

---

# 5. Business Types, Departments and Catalogue Architecture

# 5.1 Organization templates

Current organization-template families:

1. School / Educational Institution
2. Hospital / Clinic / Diagnostic Centre
3. Hotel / Hospitality Company
4. Manufacturing Company / Factory
5. Retail / Supermarket / Shopping Company
6. Construction / Engineering Company
7. Logistics / Transport Company
8. Restaurant / Fast Food / Catering Company
9. Technology / Software Company
10. NGO / Foundation / Non-Profit Organization

# 5.2 Department catalogue scale

Current master catalogue targets:

```text
10 organization types
130 department catalogues
7,344 item assignments
```

# 5.3 Item classes / behavior

Catalogue items can represent:

- Asset / Equipment
- Consumable
- Raw Material
- Resale Stock
- Spare Part
- PPE / Safety
- Furniture / Fixture
- IT / Electronic
- Medical / Laboratory Supply
- Packaging Material
- Service / Subscription

# 5.4 Catalogue principles

- default seed lists, not locked lists;
- owning/using department;
- custom additions;
- cross-department requests/transfers;
- stock or asset treatment depending on item;
- cost/evidence traceability.

# 5.5 Typical item-master information

```text
Identity
- Item / SKU
- Name
- Description
- Business Type
- Department
- Class
- Category / Subcategory
- Brand / Model

Stock
- Unit
- Pack Size
- Quantity
- Reorder Level
- Store/Bin Location

Cost
- Standard Cost
- Last Purchase Cost
- Average Cost
- Selling Price where applicable
- Cost Centre

Traceability
- Supplier
- Batch/Lot
- Expiry
- Serial Number
- Asset Tag
- Barcode/QR

Control
- Approval Required
- Restricted Item
- Custodian
- Branch / Project
- Warranty / Maintenance

Evidence
- PO
- Delivery Note
- GRN
- Invoice
- Receipt
- Photo
- Warranty / Calibration document
```

# 5.6 Custom department/item rule

Owners/admins can add missing departments and staff can add permitted custom catalogue items.

Custom records remain tenant-specific.

---

# 6. Core End-to-End Accountability Workflows

# 6.1 Purchase / Procurement

```text
Need identified
→ Staff Request
→ Owner/Authorized Approval
→ Budget/Funding Record
→ Money Sent / Granted
→ Stage 2 Acquisition
→ Receipt + optional Item Photo
→ Actual Quantity / Actual Cost
→ Final Confirmation
→ Inventory or Asset
→ Expense / Finance Effect
→ Owner Notification / Audit
```

# 6.2 Inventory

```text
Acquire / Manual Stock-In
→ Inventory Item
→ Department / Location
→ Issue / Transfer / Return / Write-Off / Adjustment
→ Stock Movement History
→ Quantity + Value update
→ Owner visibility
```

# 6.3 Asset

```text
Acquire / Manual Asset Registration
→ Asset Tag / Serial
→ Department / Custodian / Location
→ Assign / Transfer / Return / Maintenance / Write-Off
→ Asset Movement History
→ Owner visibility
```

# 6.4 Finance

```text
Account / Ledger Entry
→ Department / Counterparty / Category
→ Evidence where required
→ Posted / Draft state
→ Income or Expense Effect
→ Reports / Cash Position / P&L
```

# 6.5 Receivable

```text
Customer/Payer Owes Money
→ Receivable
→ Due Date
→ Partial/Full Payment
→ Balance
→ Cash/Income reporting
```

# 6.6 Payable

```text
Supplier/Vendor Obligation
→ Payable
→ Due Date
→ Partial/Full Settlement
→ Balance
→ Cash/Expense reporting
```

# 6.7 Department Operation

```text
Staff performs job-specific action
→ Record Operation
→ Department + Item/Amount/Location + Time
→ Activity Event
→ Owner sees operation
→ Staff report can include it
```

# 6.8 Daily / Weekly Staff Report

```text
Tracked SAGE activity
→ Generate Draft
→ Review
→ Submit
→ Owner Review/Acknowledge
→ Staff Notification
```

---

# 7. Database Architecture and Main Models

# 7.1 Database strategy

Production direction:

```text
PostgreSQL
```

Development can use a local SQLite fallback through the database service.

Database access is centralized through:

```text
packages/database.py
SQLAlchemy
```

Schema evolution is prepared for Flask-Migrate/Alembic in production workflows.

# 7.2 Main current models

The current `app.py` imports the following main model families.

## `Organization`

Tenant/business record.

Stores core organization identity and is the parent scope for tenant data.

## `OrganizationWorkspace`

Stores workspace mode/profile information added during the Owner/Individual upgrade.

Typical fields/concepts:

```text
organization_id
workspace_mode
business_category
catalog_mapping
primary_business_area
```

## `User`

Owner/admin/finance/procurement/head/staff account.

Stores identity, role, department, employment and login/account state.

## `Department`

Tenant-specific department/unit.

## `StaffInvitation`

Secure invitation token for controlled staff registration.

## `PurchaseRequest`

Core staff request record.

## Request item records

Each request may contain one or more requested items with quantity/unit/cost information.

## `RequestFunding`

Owner/Finance approved-budget and amount-sent accountability record.

## Fulfillment / acquisition record

Represents Stage 2 actual procurement/delivery information.

## `FulfillmentLine`

Stores item-level requested-vs-actual values.

Examples:

```text
request_item_id
actual_quantity
actual_unit_cost
delivered_at
notes
```

## `Attachment`

Metadata for receipt/invoice/item photo/other evidence.

## `CatalogItem`

Tenant-created custom catalogue item.

## `InventoryItem`

Tracked stock item.

## `StockMovement`

Stock-in/issue/transfer/return/write-off/adjustment history.

## `AssetItem`

Tracked equipment/asset record.

## `AssetMovement`

Asset registration/assignment/transfer/return/maintenance/write-off history.

## `DepartmentOperation`

Role/department-specific operational activity record.

## `StaffReport`

Daily/weekly activity report generated from SAGE tracking.

## `FinancialRecord`

Simpler financial record layer used by dashboard/general financial tracking.

## `FinanceAccount`

Cash/bank/POS/wallet/petty-cash account.

## `FinanceLedgerEntry`

General ledger transaction.

## `BudgetAllocation`

Department/cost-centre/project budget record.

## `FinanceReceivable`

Money owed to the business.

## `FinancePayable`

Money owed by the business.

## `FinanceReconciliation`

Calculated-vs-statement balance reconciliation record.

## `PayrollEntry`

Payroll register record.

## `TaxEntry`

Tax obligation/status record.

## `FinanceForecast`

Revenue/expense/cash/profit forecast record.

## `Notification`

Tenant/user-scoped live notification history.

## `ActivityEvent`

Audit/activity event used for accountability and owner live tracking.

## `PushSubscription`

Browser Web Push subscription metadata.

## `PlatformOwnerControl`

Developer/platform-level owner account state, plan/subscription/notes/control.

## `PlatformAdminAudit`

Developer console audit trail.

---

# 8. Backend Service / Module Reference

# 8.1 `app.py`

## Purpose

Main Flask bootstrap and explicit route layer.

## Responsibilities

- Flask creation/config;
- DB/security initialization;
- rate limiting;
- tenant session firewall;
- page context;
- authentication routes;
- Platform Admin routes;
- staff management APIs;
- request/funding/acquisition APIs;
- finance/inventory/asset APIs;
- operations/reports APIs;
- notifications/SSE;
- evidence access;
- push/health endpoints;
- SAGE AI route;
- explicit page routes;
- partial-page SPA route;
- error handling;
- cache/static-version handling;
- development startup.

# 8.2 `core/config.py`

Central application configuration.

Typical responsibilities include:

- host/port/debug;
- secret key;
- database configuration;
- storage paths/backend;
- mail/push/security settings;
- template reload;
- production flags;
- rate-limit storage.

# 8.3 `packages/database.py`

Database initialization and backend selection.

Supports production PostgreSQL direction and development fallback behavior.

# 8.4 `packages/security.py`

Authentication/role security helpers including role guards and access checks.

# 8.5 `services/access_control.py`

## Purpose

Page-level role and navigation permission engine.

Important concepts:

```text
allowed_pages()
can_access_page()
filter_navigation()
is_owner_admin()
```

# 8.6 `services/auth_service.py`

## Purpose

Owner/staff registration and authentication.

Main responsibilities:

- authenticate login;
- register owner;
- create staff invitation;
- register invited staff;
- create workspace/organization data;
- apply role/department linkage.

# 8.7 `services/organization_catalog.py`

Organization and individual-business template definitions.

Contains:

```text
BUSINESS_TYPES
INDIVIDUAL_BUSINESS_TYPES
```

Also supports automatic department onboarding templates.

# 8.8 `services/item_catalog.py`

Department item catalogue lookup, matching, grouping and organization catalogue summary.

# 8.9 `services/department_capabilities.py`

Department profiles and role-focus presentation.

Important concepts:

```text
department_profile()
role_focus()
```

# 8.10 `services/department_service.py`

Tenant-specific department creation/validation.

# 8.11 `services/department_operations.py`

Department-specific operational records and staff-report aggregation.

Important concepts:

```text
create_department_operation()
department_operations_profile()
generate_staff_report()
report_metrics()
acknowledge_staff_report()
```

# 8.12 `services/operations_service.py`

Core operational/business engine.

Current responsibilities include:

- request creation;
- request decision;
- request funding;
- Stage 2 fulfillment/acquisition;
- basic financial records;
- inventory/asset movement;
- dashboard/analytics summaries;
- department scoping;
- asset tag generation.

Important functions imported by `app.py`:

```text
create_request()
decide_request()
save_request_funding()
save_fulfillment()
add_financial_record()
finance_summary()
owner_dashboard_context()
analytics_context()
move_asset()
move_stock()
next_asset_tag()
scoped_department()
```

# 8.13 `services/finance_service.py`

Finance & Accounts Control Centre.

Important functions:

```text
create_finance_account()
post_ledger_entry()
create_budget()
create_receivable()
settle_receivable()
create_payable()
settle_payable()
create_reconciliation()
create_payroll()
create_tax()
create_forecast()
finance_control_context()
```

# 8.14 `services/reporting_service.py`

Management reporting / intelligence context and CSV export rows.

Important concepts:

```text
reporting_context()
management_export_rows()
```

# 8.15 `services/workspace_service.py`

Workspace-mode behavior added for Organization vs Individual Business.

Important functions:

```text
workspace_profile_context()
individual_dashboard_context()
request_management_context()
```

# 8.16 `services/notification_service.py`

Notification and activity creation.

Important concepts:

```text
notify_user()
record_activity()
```

Supports tenant-scoped notification creation, audit activity, owner escalation and email triggers.

# 8.17 `services/briefing_service.py`

Builds the permission-aware Daily SAGE Brief / Pulse slide data.

# 8.18 `services/ai_service.py`

OpenAI-backed SAGE AI layer.

The AI receives role-scoped/tenant-scoped business context rather than unrestricted global data.

# 8.19 `services/storage_service.py`

Attachment/evidence delivery abstraction.

Supports local development storage and production private-object-storage direction.

# 8.20 `services/push_service.py`

Browser push configuration/subscription helpers.

# 8.21 `services/platform_service.py`

Developer Platform Admin owner-management logic.

Important concepts:

```text
get_control()
organization_rows()
permanent_delete_organization()
platform_summary()
record_platform_admin()
update_control()
```

# 8.22 `services/production_service.py`

Production health, security, proxy and retention utilities.

Important concepts:

```text
apply_retention_policy()
apply_security_headers()
health_snapshot()
install_proxy_support()
production_warnings()
```

# 8.23 `services/demo_data.py`

Despite the historical filename, the current app imports navigation/page-title definitions here:

```text
NAV_ITEMS
PAGE_TITLES
```

Production pages should continue to avoid fake financial/business records.

---

# 9. Frontend / UI Architecture

# 9.1 `templates/app_shell.html`

Persistent signed-in application shell.

Responsibilities:

- desktop sidebar;
- mobile sidebar;
- topbar;
- search;
- SAGE AI;
- Quick Record / Quick Add behavior;
- theme selector;
- notification bell/drawer;
- user identity;
- SAGE Guide controls;
- SAGE Pulse container;
- page-content host for SPA partial navigation;
- floating mobile actions.

# 9.2 Authentication templates

Typical templates:

```text
templates/auth/login.html
templates/auth/register.html
templates/auth/staff_register.html
```

## Login

Split-screen SAGE login design with:

- SAGE HTML/CSS wordmark;
- business/dashboard visual left panel;
- right sign-in form;
- Platform Admin entry;
- owner workspace creation link;
- responsive mobile behavior.

## Owner registration

Wizard-style flow:

```text
Owner
→ Workspace Type
→ Business
→ Setup
```

Organization mode shows business/department setup.

Individual mode hides organization-only fields.

## Staff registration

Private invitation token controls department/role context.

# 9.3 Main page templates

Current page route family:

```text
pages/dashboard.html
pages/workspace.html
pages/catalog.html
pages/analytics.html
pages/finance.html
pages/requests.html
pages/operations.html
pages/procurement.html
pages/fulfillment.html
pages/inventory.html
pages/assets.html
pages/departments.html
pages/staff.html
pages/reports.html
pages/audit.html
pages/settings.html
```

# 9.4 `static/js/vision.js`

Historical filename retained from Vision.

Current responsibilities include major signed-in frontend behavior such as:

- SPA-style navigation;
- sidebar/mobile interactions;
- modals;
- request/finance/asset/inventory forms;
- notification drawer;
- SSE/polling notification behavior;
- SAGE Pulse;
- recurring 5-minute Pulse;
- Guide behavior;
- theme/appearance behavior;
- command/search UI;
- charts/interactions;
- collapsed-sidebar labels.

# 9.5 `static/css/vision.css`

Historical filename retained.

Contains shared SAGE shell/page styling including:

- themes;
- desktop/mobile responsive rules;
- sidebar/topbar;
- cards/tables;
- finance/requests/inventory/assets;
- Guide;
- Pulse;
- collapsed state;
- mobile Pulse positioning;
- SAGE wordmark spacing.

# 9.6 `static/js/auth.js`

Registration/login/onboarding behavior including organization department auto-selection.

# 9.7 Catalogue data

```text
static/data/sage_item_catalog.json
```

Large organization/department item seed catalogue.

# 9.8 PWA assets

```text
static/sw.js
static/manifest.webmanifest
```

Used for Web Push/PWA-ready behavior.

# 9.9 Platform Admin frontend

Typical files:

```text
templates/platform_admin/login.html
templates/platform_admin/dashboard.html
```

with shared/static console styling/scripts integrated into the SAGE frontend set.

---

# 10. Authentication, Registration and Staff Management

# 10.1 Public login

```text
/login
```

Owner and staff use their database account credentials.

# 10.2 Public owner registration

```text
/register
```

Only for creating a new owner/workspace.

# 10.3 Owner registration data

Major identity/business fields include concepts such as:

```text
First Name
Middle Name
Last Name
Sex
Date of Birth
Phone
Email
Password
Workspace Mode
Business / Organization Name
Business Type / Individual Category
Country
State / Region
Address
Currency
Branches where relevant
Organization Size where relevant
```

# 10.4 Staff registration

Staff do not use the public owner form.

Owner/Admin creates an invitation:

```text
/register/staff/<secure-token>
```

Invitation context stores organization, department and role.

# 10.5 Staff profile information

Typical captured information includes:

- first/middle/last name;
- sex;
- DOB;
- phone;
- address;
- employee ID;
- position;
- department;
- role;
- password/account state;
- created date / last login.

# 10.6 Staff Management

Owner/Admin can:

- invite;
- edit;
- transfer department;
- change role;
- suspend;
- reactivate;
- soft-delete/archive;
- restore;
- inspect activity;
- bulk activate/suspend/delete;
- export CSV.

# 10.7 Owner-account restriction

Tenant Owner cannot be removed through normal staff-management endpoints.

Platform Admin controls the owner/workspace instead.

---

# 11. Requests, Approvals, Funding and Acquisition

# 11.1 Request creation

Staff request can capture:

- title/item;
- department;
- catalogue category;
- quantity;
- unit;
- unit cost;
- estimated total;
- purpose/justification;
- urgency;
- draft/submitted state.

# 11.2 Owner restriction

Organization Owner cannot POST a new staff-style request to self.

# 11.3 Request statuses

Current workflow includes states such as:

```text
draft
submitted
approved
money_sent
fulfilled
verified
rejected
```

# 11.4 Owner request view

Owner request management now includes:

- department grouping;
- requester name;
- position;
- purpose;
- amount;
- item count;
- urgency;
- date/time;
- stage/status;
- approval/funding actions;
- filters/sorting/search;
- request ledger/export.

# 11.5 Funding

Funding record stores approved budget and external money-released information.

No bank transfer is performed by SAGE.

# 11.6 Stage 2 Acquisition Log

Approved/Money-Sent requests can be opened for actual acquisition recording.

Modes:

```text
Purchased / Procured by Me
Delivered / Brought by Another Staff/Person
```

# 11.7 Evidence rule

Final acquisition submission requires receipt/invoice evidence.

Optional item image can be attached.

# 11.8 Draft rule

Uncertain purchase details can remain Draft.

Final confirmation is treated as locked accounting/evidence state.

# 11.9 Final posting

Confirmed acquisition can update:

- inventory quantity/value;
- asset register;
- expense/financial reporting;
- owner notification;
- activity audit.

---

# 12. Inventory, Assets and Department Operations

# 12.1 Inventory Item

Typical fields:

```text
Name
Category
Unit
Quantity
Unit Value
Total Value
Reorder Level
Department
Location
Added By
Updated At
```

# 12.2 Stock movements

Supported patterns include:

- stock in;
- issue/use;
- transfer;
- return;
- write-off/damage;
- positive/negative adjustment.

# 12.3 Cross-department transfer

Transfers can update the destination department instead of only decreasing the source quantity.

# 12.4 Asset fields

Typical asset record includes:

```text
Name
Category
Asset Tag
Serial Number
Quantity
Unit Value
Department
Custodian
Location
Condition
Status
Acquired Date
Warranty Expiry
Notes
```

# 12.5 Asset movements

Typical movement types:

- register;
- assign;
- transfer;
- return;
- maintenance;
- write-off;
- restore/reactivate where supported.

# 12.6 Department Operations

Allows staff to record work unique to their role without forcing every activity through a purchase request.

# 12.7 Staff Reports

Daily/weekly summaries use real SAGE activity rather than manual retyping.

---

# 13. Finance & Accounts Control Centre

# 13.1 Finance Accounts

Supports account types such as:

```text
Bank
Cash
POS
Wallet
Petty Cash
```

# 13.2 General Ledger

Ledger entry fields/concepts include:

- type;
- direction;
- description;
- counterparty;
- department;
- account;
- amount;
- currency;
- date/time;
- status;
- payment method/reference;
- external reference;
- evidence.

# 13.3 Budgets

Tracks:

```text
Original / Approved Budget
Revised Budget where supported
Committed Spend
Actual Spend
Available Balance
Utilization
Department / Cost Centre / Project
```

# 13.4 Accounts Receivable

Tracks customer/payer, reference, amount owed, amount received, outstanding balance, due date and status.

# 13.5 Accounts Payable

Tracks supplier/vendor, bill/reference, amount payable, amount settled, balance, due date and status.

# 13.6 Reconciliation

Compares statement closing balance against SAGE calculated account position and stores variance/status.

# 13.7 Payroll

Tracks concepts such as:

- employee/staff;
- pay period;
- gross;
- deductions;
- tax;
- net;
- status.

Paid payroll contributes to expenditure reporting.

# 13.8 Taxes

Tax Register supports custom tax labels such as VAT/PAYE/WHT and tracks authority, period, taxable amount, tax amount, due date and status.

# 13.9 Forecasts

Can store revenue, expense, cash-flow and profit forecast assumptions separately from actual transactions.

# 13.10 Finance exports

Ledger CSV export is implemented.

---

# 14. Owner Dashboards, Reports and Management Intelligence

# 14.1 Organization Owner Dashboard

Current owner overview can include:

- Income / Revenue
- Expenses / Expenditure
- Net Position
- Pending Approvals
- Financial Control Snapshot
- Inventory Position
- Asset Position
- recent requests/activity
- live alerts
- SAGE Pulse

# 14.2 Individual Owner Dashboard

Different from multi-department owner dashboard.

Focuses on owner-operated business KPIs rather than department hierarchy.

# 14.3 Reports

Implemented report/intelligence areas include:

- Income / Revenue
- Profit / Loss
- Cash Position
- Budget Position
- AR
- AP
- Procurement
- Department Spending
- Inventory Valuation
- Asset Value
- Staff Accountability
- Audit/Evidence
- exception/attention areas.

# 14.4 CSV report exports

Current management export types include:

```text
summary
departments
inventory
requests
```

# 14.5 No fake data rule

If SAGE has no underlying records, the dashboard/report should display zero or an empty state rather than manufactured sample numbers.

---

# 15. Notifications, SAGE Pulse, SAGE Guide and SAGE AI

# 15.1 Notification architecture

Current notification channels include:

- database Notification records;
- SSE live stream;
- polling/fallback logic in frontend;
- bell/history drawer;
- email escalation where SMTP is configured;
- Web Push where configured;
- SAGE Pulse visible floating cards.

# 15.2 Notification isolation

Notification queries require both:

```text
organization_id
user_id
```

# 15.3 SSE

Live endpoint repeatedly refreshes the SQLAlchemy session so newly committed notifications are visible.

It emits:

```text
ready
notification
heartbeat
```

# 15.4 SAGE Pulse

See Phase/refinement history above.

Pulse is the visible briefing/flash surface, while the bell retains history.

# 15.5 SAGE Guide

Optional contextual guidance.

Desktop: hover/focus hints.

Mobile: touch/drawer Guide.

Can be switched On/Off.

# 15.6 SAGE AI

Route:

```text
POST /api/ai/chat
```

Uses OpenAI configuration and role-scoped SAGE context.

Owner examples:

```text
How much did we spend this week?
Which department spent the most?
Which requests need attention?
What stock is low?
What are our outstanding receivables/payables?
Summarize the current business position.
```

AI must not expose data outside the current user's permissions/tenant.

# 15.7 Groq preparation

Groq keys/model configuration was prepared for later receipt/document/image analysis workflows, with higher-numbered configured keys preferred first in the earlier design.

Receipt-image understanding is separate from normal SAGE chat and should only be treated as implemented when the actual analysis workflow is wired and tested.

---

# 16. Platform Admin / Developer Console

# 16.1 Authentication

Separate developer credentials are loaded from `.env`.

Recommended names:

```text
SAGE_ADMIN_USERNAME
SAGE_ADMIN_PASSWORD
```

Current app also supports platform-admin configuration through `Config`.

# 16.2 Main routes

```text
/platform-admin/login
/platform-admin
/platform-admin/logout
```

# 16.3 Main owner-management features

- list owners/workspaces;
- search/filter;
- see active/disabled states;
- plan/subscription controls;
- developer note;
- organization/user/request/inventory/asset/finance detail;
- live platform activity;
- export owners CSV;
- disable owner/workspace;
- restore owner/workspace;
- permanently delete owner/workspace;
- audit developer actions.

# 16.4 Disable vs Delete

Disable is recoverable.

Permanent Delete requires confirmation text and tenant-name validation.

# 16.5 Live platform activity

Separate SSE feed provides platform-wide activity to the developer console.

---

# 17. Evidence, File Storage and Document Security

# 17.1 Storage principle

Actual image/PDF evidence should not be stored as large binary blobs directly in normal relational transaction rows.

Database stores metadata/reference; file bytes live in storage.

# 17.2 Development storage

Local storage can use folders under the configured SAGE storage directory.

Typical evidence categories:

```text
receipts
invoices
quotations
assets
staff documents
item images
other supporting evidence
```

# 17.3 Production storage

Architecture supports private S3-compatible storage such as AWS S3 or Cloudflare R2.

# 17.4 Evidence access

Evidence route verifies tenant ownership before returning the file.

```text
/evidence/<attachment_id>
```

# 17.5 Evidence metadata

Attachment metadata can include:

- tenant;
- uploader;
- entity type/id;
- evidence kind;
- original name;
- storage key/path;
- final/locked state;
- created date;
- file hash where used.

# 17.6 Security principle

Receipts and internal documents should not be exposed as guessable public URLs.

Production storage should remain private and use controlled/signed access.

---

# 18. Routes and API Map

# 18.1 Main page routes

```text
/                     → login or dashboard
/login
/register
/register/staff/<token>
/logout

/dashboard
/workspace
/catalog
/analytics
/finance
/requests
/operations
/procurement
/fulfillment
/inventory
/assets
/departments
/staff
/reports
/audit
/settings

/partial/<page>
```

# 18.2 Platform Admin routes

```text
/platform-admin/login
/platform-admin/logout
/platform-admin
/platform-admin/api/owners/<organization_id>/detail
/platform-admin/api/owners/<organization_id>
/platform-admin/api/owners/<organization_id>/disable
/platform-admin/api/owners/<organization_id>/restore
/platform-admin/api/owners/<organization_id>   [DELETE]
/platform-admin/api/owners.csv
/platform-admin/api/activity
/platform-admin/api/activity/stream
```

# 18.3 Authentication APIs

```text
POST /api/auth/register-owner
POST /api/auth/login
POST /api/auth/register-staff/<token>
```

# 18.4 Daily briefing / Pulse APIs

```text
GET  /api/daily-briefing
POST /api/daily-briefing/ack
```

# 18.5 Staff / Department APIs

```text
POST   /api/staff/invite
PATCH  /api/staff/<user_id>
POST   /api/staff/<user_id>/status
DELETE /api/staff/<user_id>
POST   /api/staff/<user_id>/restore
GET    /api/staff/<user_id>/activity
POST   /api/staff/bulk
GET    /api/staff/export.csv
POST   /api/departments
```

# 18.6 Request / Acquisition APIs

```text
POST /api/requests
POST /api/requests/<request_id>/action
GET  /api/requests/<request_id>/fulfillment
POST /api/requests/<request_id>/fulfillment
POST /api/requests/<request_id>/funding
```

# 18.7 Finance APIs

```text
POST /api/finance/records
POST /api/finance/accounts
POST /api/finance/ledger
POST /api/finance/budgets
POST /api/finance/receivables
POST /api/finance/receivables/<row_id>/payment
POST /api/finance/payables
POST /api/finance/payables/<row_id>/payment
POST /api/finance/reconciliations
POST /api/finance/payroll
POST /api/finance/taxes
POST /api/finance/forecasts
GET  /api/finance/export.csv
```

# 18.8 Catalogue / Inventory / Asset APIs

```text
POST /api/catalog/items
POST /api/inventory/items
POST /api/inventory/items/<item_id>/move
POST /api/assets
POST /api/assets/<asset_id>/move
```

# 18.9 Department operation / report APIs

```text
POST /api/operations
POST /api/staff-reports
POST /api/staff-reports/<report_id>/acknowledge
```

# 18.10 Activity / Notification APIs

```text
POST /api/activity/page-view
GET  /api/notifications
POST /api/notifications/read
GET  /api/notifications/stream
GET  /evidence/<attachment_id>
```

# 18.11 Report / Push / Health APIs

```text
GET  /api/reports/export/<report_type>.csv
GET  /api/push/config
POST /api/push/subscribe
POST /api/push/unsubscribe
GET  /sw.js
GET  /manifest.webmanifest
GET  /health
GET  /ready
```

# 18.12 SAGE AI

```text
POST /api/ai/chat
```

# 18.13 Operations CLI

```text
flask --app app sage-retention --dry-run
flask --app app sage-retention
```

---

# 19. SPA Navigation, Themes, Mobile and UX Rules

# 19.1 SPA-style navigation

SAGE remains Flask/Jinja, but internal navigation can load page partials rather than forcing a full shell reload.

Flow:

```text
Sidebar click
→ Fetch /partial/<page>
→ replace content area
→ update history / title / active nav
→ keep shell/sidebar/header alive
```

# 19.2 Explicit route design

Main display routes remain directly visible in `app.py` by design.

Business logic belongs in services/models rather than moving every route into hidden modules.

# 19.3 Themes

Current appearance choices:

```text
Dark
Light
Sky Blue
Sage Green
Warm Sand
Slate
```

# 19.4 Sidebar

- desktop collapsible;
- reduced width;
- compact collapsed mode;
- icon labels on hover/focus when collapsed;
- separate mobile drawer behavior.

# 19.5 Mobile rule

New user-facing features should be reflected on mobile unless a feature fundamentally cannot operate in the same way.

Examples already adapted:

- sidebar;
- Guide;
- Pulse;
- topbar;
- theme/notification controls;
- authentication;
- Platform Admin;
- forms/cards/tables where possible.

# 19.6 Accessibility / clarity principles

- avoid tiny text for critical operational information;
- keep major numbers readable;
- keep notifications compact but visible;
- allow Guide to be disabled;
- empty states instead of fake data;
- mobile touch targets must remain usable;
- avoid owner/staff workflows that expose actions they cannot logically perform.

---

# 20. Deployment, Production Hardening and Cache Protection

# 20.1 Development startup

Typical local startup remains:

```text
host = 0.0.0.0
port = 5005
debug = True   (development only)
```

# 20.2 Production database

Preferred:

```text
PostgreSQL
```

SQLite fallback is for local development/testing, not the intended multi-user production deployment.

# 20.3 Rate limiting

Flask-Limiter is optional.

Current bootstrap uses configurable storage and defaults safely when the extension is unavailable.

Sensitive auth endpoints have explicit per-minute limits.

# 20.4 Proxy / HTTPS

Production service installs proxy support and secure-header behavior for deployment behind a reverse proxy.

# 20.5 Health

```text
/health
/ready
```

`/ready` performs deeper readiness checks.

# 20.6 Web Push / PWA

Service worker and manifest are available.

Push requires deployment configuration such as VAPID settings.

# 20.7 Email

SMTP notification infrastructure is optional and driven by `.env`.

# 20.8 Retention

Retention CLI supports dry-run before deletion.

Audit retention was designed for long-lived accountability rather than aggressive short cleanup.

# 20.9 Cache protection

SAGE now follows the EMIS-style protection model.

## Static versioning

A physical static file change changes the version appended to its URL.

Example:

```text
/static/css/vision.css
→ /static/css/vision.css?v=<deployment-file-version>
```

## Cache policy

HTML/API/partials:

```text
no-store, no-cache, must-revalidate, private
```

JS/CSS:

- strict no-store/no-cache;
- automatic versioned URL.

Other static assets:

- revalidation before reuse.

## Template reload

Jinja auto reload is enabled for development/configured environments.

## Deployment rule

Python/backend changes still require restart:

```text
Restart Flask / WSGI / Passenger / process manager
```

Frontend-only changes should normally not require manual Ctrl+F5 because the asset URL changes automatically.

---

# 21. Current Pending / Future Expansion Areas

The following are useful next-stage areas and should not be confused with already completed work.

# 21.1 Receipt AI / OCR-style understanding

The storage/evidence pipeline exists and Groq/OpenAI configuration was prepared, but fully verified automatic receipt extraction/analysis should be treated as a separate implementation/test stage.

Potential future fields:

- merchant/supplier;
- receipt date;
- total;
- item lines;
- tax;
- payment reference;
- duplicate/fraud checks.

# 21.2 Supplier / Vendor master

The concept note includes supplier/vendor management, quotation history and performance. Full dedicated vendor master and quotation comparison can be expanded further.

# 21.3 Purchase Orders

A formal PO document lifecycle can be added between approved request and acquisition.

# 21.4 Cash Advance / Petty Cash retirement

Finance foundations exist, but a dedicated staff advance-retirement workflow can be expanded.

# 21.5 Multi-branch / Multi-company hierarchy

Organization model already has branch-related onboarding concepts, but deep branch/sub-company consolidation can be expanded.

# 21.6 Barcode / QR workflows

Item fields/design support the concept, but scanning/label-generation workflows can be extended.

# 21.7 Auditor/read-only role

The concept supports auditor-style access. A dedicated first-class read-only role can be formalized further if required.

# 21.8 More automated recurring transactions

Rent, subscriptions and repeating payments can be formalized into recurring schedules.

# 21.9 Full automated migrations

Production deployments should move fully to tested migration-driven schema changes instead of relying on `db.create_all()`.

# 21.10 End-to-end regression suite

Before public launch, build automated tests for:

- tenant isolation;
- owner vs staff permissions;
- request/funding/acquisition posting;
- file/evidence authorization;
- finance ledger integrity;
- inventory/asset movement;
- platform permanent deletion;
- push/SSE/email fallbacks;
- mobile critical workflows;
- production migrations.

---

# 22. Quick File Guide

| Need to Change | Main File(s) |
|---|---|
| Flask bootstrap / central routes | `app.py` |
| Main configuration | `core/config.py` |
| Database initialization | `packages/database.py` |
| Role/security helpers | `packages/security.py` |
| Page permissions/navigation filtering | `services/access_control.py` |
| Owner/staff authentication | `services/auth_service.py` |
| Organization + individual business templates | `services/organization_catalog.py` |
| Department item catalogue logic | `services/item_catalog.py` |
| Department role profiles | `services/department_capabilities.py` |
| Department creation | `services/department_service.py` |
| Request / funding / acquisition / stock / asset core | `services/operations_service.py` |
| Department operations / staff reports | `services/department_operations.py` |
| Finance control centre | `services/finance_service.py` |
| Reporting / exports | `services/reporting_service.py` |
| Individual vs organization workspace behavior | `services/workspace_service.py` |
| Notifications / activity | `services/notification_service.py` |
| Daily Brief / Pulse data | `services/briefing_service.py` |
| SAGE AI | `services/ai_service.py` |
| File/evidence storage | `services/storage_service.py` |
| Web Push | `services/push_service.py` |
| Platform owner management | `services/platform_service.py` |
| Production security/health/retention | `services/production_service.py` |
| Database models | `models/` |
| Main signed-in shell | `templates/app_shell.html` |
| Login | `templates/auth/login.html` |
| Owner registration | `templates/auth/register.html` |
| Staff registration | `templates/auth/staff_register.html` |
| Platform Admin login/dashboard | `templates/platform_admin/` |
| Main content pages | `templates/pages/` |
| Main application JS | `static/js/vision.js` |
| Registration/auth JS | `static/js/auth.js` |
| Main application CSS/themes/mobile/Pulse | `static/css/vision.css` |
| Master item catalogue | `static/data/sage_item_catalog.json` |
| Service worker | `static/sw.js` |
| Web app manifest | `static/manifest.webmanifest` |
| Environment secrets/config | `.env` |
| Production dependency list | `requirements.txt` |
| WSGI / production runner | production entry files / server config |

---

# 23. Validation and Safety Summary

Across the phased SAGE upgrade work, validation repeatedly included combinations of:

```text
Python syntax / compile checks
JavaScript syntax checks
Jinja template parsing
ZIP integrity checks
HTML/JS integration checks
Role/permission path checks
Tenant-scoping reviews
Notification isolation checks
Catalogue/template matching checks
Request state-flow checks
Actual-vs-requested acquisition checks
Inventory/asset movement logic checks
Finance route/model integration checks
Platform Admin destructive-action guards
Responsive/mobile CSS review
Static cache/version protection review
```

## Critical permanent rules

```text
1. Tenant data is always scoped by organization_id.
2. Notifications are scoped by organization_id + user_id.
3. Staff must not see another organization's records.
4. Organization owners do not submit approval requests to themselves.
5. Money Sent records accountability; SAGE does not transfer money.
6. Actual acquisition quantity/cost overrides requested values for final stock/asset posting.
7. Receipt/invoice evidence is required for final Stage 2 acquisition submission.
8. Draft records remain editable; final accountability records should not be casually altered.
9. Staff soft-delete must preserve historical accountability records.
10. Platform owner Disable is recoverable; Permanent Delete is destructive and confirmation-protected.
11. Production receipts/evidence must be private and permission-controlled.
12. Individual Business users must not be forced through irrelevant organization/department setup.
13. Empty SAGE datasets should show zero/empty state, not fake demo business values.
14. Role access must be enforced in backend routes, not only hidden in the UI.
15. SAGE AI must respect tenant and role permissions.
16. Mobile support is expected for major user-facing features.
17. Guide is optional and can be disabled.
18. Pulse appears once after login, can recur on the configured interval, and must not replace the notification history drawer.
19. Python changes require application restart.
20. Static assets use automatic versioning/cache protection to reduce stale frontend files.
```

---

# 24. Current Architecture Summary

```text
                                      ┌──────────────────────────┐
                                      │      SAGE PLATFORM       │
                                      │  Flask + SQLAlchemy      │
                                      └────────────┬─────────────┘
                                                   │
                  ┌────────────────────────────────┼────────────────────────────────┐
                  │                                │                                │
                  ▼                                ▼                                ▼
        PLATFORM ADMIN                   ORGANIZATION OWNER              INDIVIDUAL OWNER
        Developer Console                Multi-Department                Lean Business
                  │                                │                                │
                  │                                ▼                                ▼
                  │                       Departments / Staff         Direct Business Records
                  │                                │                                │
                  │                  ┌─────────────┼─────────────┐                  │
                  │                  │             │             │                  │
                  │                  ▼             ▼             ▼                  │
                  │              Requests       Finance      Inventory/Assets        │
                  │                  │             │             │                  │
                  │                  ▼             │             │                  │
                  │           Approve / Fund       │             │                  │
                  │                  │             │             │                  │
                  │                  ▼             │             │                  │
                  │            Stage 2 Acquire     │             │                  │
                  │          Receipt + Item Photo  │             │                  │
                  │                  │             │             │                  │
                  │                  └───────┬─────┴──────┬──────┘                  │
                  │                          │            │                         │
                  │                          ▼            ▼                         │
                  │                      Audit/Live   Reports/AI                     │
                  │                      Activity      Intelligence                  │
                  │                          │            │                         │
                  └──────────────────────────┴────────────┴─────────────────────────┘
                                             │
                                             ▼
                                   SAGE GUIDE + SAGE PULSE
                                  SSE + Email + Push + Drawer
                                             │
                                             ▼
                                   Private Evidence Storage
                                 Local Dev → S3/R2 Production
```

## Technology summary

```text
Backend             Python + Flask
ORM                 SQLAlchemy
Primary DB          PostgreSQL
Dev DB              SQLite fallback
Authentication      Flask-Login
Permissions         Role + page access + tenant scoping
Frontend            Jinja HTML + CSS + JavaScript
Navigation          Fetch/History/partial SPA-style shell
Charts/Reports       Frontend charting + live DB context
AI                  OpenAI SAGE AI; Groq prepared for document-analysis expansion
Notifications       DB + SSE + email + Web Push + SAGE Pulse
Evidence Storage    Local development / private S3-R2-compatible production
Exports             CSV + downloadable evidence
Deployment          WSGI/Gunicorn/Waitress/Docker-ready foundation
Cache               automatic per-file static versioning + no-store/revalidation
```

---

# End of Reference

This document reflects the SAGE architecture and implementation history through **7 October 2026**, including the original Vision foundation, SAGE Phases 1–8, organization/individual workspace split, department onboarding/catalogue correction, structured owner request management, SAGE Guide, Daily Brief/SAGE Pulse, 5-minute recurring Pulse behavior, desktop/mobile sidebar refinements, SAGE wordmark polish and EMIS-style automatic cache/version protection.

The next major development work should build on these rules rather than bypassing them, especially the tenant-isolation, evidence, actual-vs-requested, role-access, private-storage and audit/accountability guarantees.

---

# 25. CEO / Owner Management Upgrade — Phases 1–5 (7 October 2026)

This five-phase upgrade was implemented against the Owner/Management requirements supplied on 7 October 2026. It extends the existing SAGE Phase 1–8 foundation instead of duplicating finance, request, inventory or audit data.

## CEO Upgrade Phase 1 — Executive Control Dashboard + Department Workspace Fix

- Fixed the Owner → Department Workspace Jinja crash caused by slicing `department_catalog.items` as if it were a list. The template now explicitly reads `department_catalog['items']`.
- Added the Owner Executive Dashboard KPIs: Income, Expenses, Net Position, Receivables, Payables, Inventory Value, Pending Approvals and Budget Usage.
- Added Today at a Glance: income, expenses, net, available cash, pending approvals, new requests and outstanding payments.
- Added `Requires Your Attention` with management priority states: Urgent, Attention Required and Normal.
- Added department breakdown/drill-down with income, expenses, request count, approved amount, actual spend, budget, committed amount, remaining budget and utilization.
- Added `services/management_service.py` as the management aggregation layer so dashboards continue to use real tenant records only.

## CEO Upgrade Phase 2 — Purchase Chain + Supplier Management

- Added a complete Request → Approval → Purchase → Receipt → Delivery → Verification → Payment trace view.
- Shows requested/approved/actual amounts, supplier, receipt, requester, approver, purchaser/logger, receiver and verifier.
- Added `Supplier` master records, automatically created from actual acquisition supplier names.
- Supplier intelligence shows cumulative spend, outstanding payables, purchase count/history and latest prices charged per item.
- Existing acquisition/fulfillment data remains the source of truth; no shadow purchase ledger was introduced.

## CEO Upgrade Phase 3 — Branches + Configurable Approval Limits

- Added `BranchLocation` and `BranchDepartment` models.
- Added Owner Settings controls for branch/location creation and department assignment.
- Added Organization → Branch → Department → Transaction drill-down comparing income, expenses, profit/loss, budget usage, inventory value, receivables and payables.
- Added `ApprovalRule` with minimum amount, optional maximum amount, required role and priority.
- Approval decisions now enforce configured thresholds and prevent a requester from approving their own request.
- Department Head approval is restricted to the Head's own department when the configured rule requires Department Head approval.

## CEO Upgrade Phase 4 — Retained Audit History + Management Anomalies

- Added append-only `AuditRevision` before/after snapshots for important mutable states.
- Request decisions, request funding, receivable/payable settlements, stock movement, asset movement and acquisition verification now retain state-change history.
- Added a real management verification action for completed acquisitions; the verifier and verification time now complete the procurement accountability chain.
- AR/AP screens now show payment history derived from their linked finance-ledger settlements.
- Added anomaly/exception checks for spending spikes, duplicate invoice/bill references, duplicate outgoing payment references, unusually large expenses, approval-limit violations, confirmed purchases missing receipts, supplier price increases and historical requester self-approval.
- Management anomaly results appear in Analytics, Audit and the Owner dashboard attention queue.

## CEO Upgrade Phase 5 — Periodic Reports + CSV / Excel / PDF

- Added current Daily, Weekly, Monthly, Quarterly and Yearly report periods.
- Added one shared export engine so CSV, Excel and PDF are generated from the same tenant-scoped rows.
- Exportable management report families now include:
  - management summary;
  - finance ledger;
  - income;
  - expenses;
  - profit/loss;
  - cash flow;
  - procurement / purchase trace;
  - inventory;
  - assets;
  - staff activity;
  - departments;
  - audit change history;
  - accounts receivable;
  - accounts payable;
  - suppliers;
  - branch comparison.
- Added `services/export_service.py` for CSV/XLSX/PDF rendering.
- Added `openpyxl` and `reportlab` runtime dependencies.

## New Management Models

```text
Supplier
BranchLocation
BranchDepartment
ApprovalRule
AuditRevision
```

These are additive tables. Development deployments with `SAGE_AUTO_CREATE_SCHEMA=true` create the new tables through `db.create_all()`. Production deployments where `SAGE_AUTO_CREATE_SCHEMA=false` should create and apply the corresponding Flask-Migrate/Alembic migration before serving upgraded code.

## New / Extended Management Endpoints

```text
POST /api/management/branches
POST /api/management/branch-departments
POST /api/management/approval-rules
POST /api/requests/<request_id>/verify
GET  /api/reports/export/<report_type>.<file_format>?period=<period>
```

Export values:

```text
file_format = csv | xlsx | pdf
period      = all | daily | weekly | monthly | quarterly | yearly
```

## Owner Management Flow After Upgrade

```text
Owner opens Dashboard
→ sees Income / Expenses / Net / AR / AP / Inventory / Approvals / Budget
→ sees Today at a Glance
→ sees prioritized items requiring attention
→ can drill into Department / Branch / Procurement / Finance / Audit
→ can follow a purchase through request, approval, supplier, receipt, delivery, verification and payment
→ can identify the responsible people and retained change history
→ can export the required report in CSV, Excel or PDF.
```

---

# SAGE 1.0 Major Upgrade — Income, Mobile UX, Developer Support & Complete Live Owner Visibility

> **Upgrade date:** 8 October 2026  
> **Source baseline:** `sage_1.0.zip` supplied after the earlier CEO-management upgrade.  
> **Implementation rule:** mobile-first, tenant-scoped, compact horizontal code style, and existing finance/request/operations records remain the source of truth.

## Phase 1 — Global Modal UX Repair

- All normal SAGE modals now open near the top of the viewport instead of visually falling toward the page bottom.
- Desktop modals use a compact upper viewport position and capped height.
- Mobile modals use narrower outer margins, smaller maximum height, rounded cards and internal scrolling instead of consuming the entire screen.
- Modal headers/actions remain reachable while long forms scroll.
- Opening a modal resets its internal scroll position and locks background scrolling; closing restores the page cleanly.
- The behavior is global, so Request, Funding, Acquisition, Finance, Inventory, Assets, Staff, Operations, Income and later modals inherit the correction automatically.

## Phase 2 — Dedicated Income & Sales Workspace

- Added `Income & Sales` as a first-class SAGE page and navigation destination.
- Added accountable Sale/Revenue and Other Income entry from real staff accounts.
- Normal staff are restricted to their department/own scope; Owner/Admin/Finance retain organization-wide visibility and account allocation controls.
- Every money-in row exposes date/time, SAGE reference, description/category, source/customer, department, recorder/position, payment method/reference, evidence and exact amount.
- Money-in remains backed by the existing `FinanceLedgerEntry`/`FinancialRecord` architecture; the page does not create a duplicate income ledger.
- Owner live notifications now contain useful income details instead of only changing an aggregate dashboard total.

## Phase 3 — Revenue / Net-Profit Performance Targets

- Added `FinancePerformanceTarget` for monthly/yearly Revenue or Net Profit management targets.
- Owner/Admin may set organization-wide or department targets.
- Actual performance is calculated from posted SAGE financial records and compared with target, variance and percentage progress.
- Owner Dashboard now displays recent detailed money-in and current target progress automatically.
- Permanent tenant deletion includes the new target table.

## Phase 4 — Platform Support, Themes & Password Security

- Added a Developer `Login Directory` showing organization, staff/owner name, login email, employee ID, department/role, status and last login.
- SAGE does **not** display existing passwords or password hashes. Passwords remain one-way hashed.
- Platform Admin can generate a fresh one-time temporary password for a selected user; the temporary credential is returned only once and is not stored as recoverable plaintext.
- Added self-service `Change password` directly from the normal SAGE login screen. The user verifies their current password and the email/login identifier remains unchanged.
- Added six Platform Console themes: Midnight, Light, Ocean, Emerald, Violet and Amber.
- Developer modal/directory/theme controls have dedicated responsive mobile behavior.

## Phase 5 — Income Intelligence + Complete Owner Event Notification Coverage

### Income intelligence additions

1. Quick Sale preset.
2. Quick Other Income preset.
3. Role-scoped Income CSV export available to staff for only the rows they are allowed to see.
4. Management Income Excel export.
5. Management Income PDF export.
6. Today-versus-yesterday revenue trend.
7. Current-month-versus-previous-month trend.
8. Average money-in transaction value.
9. Largest visible income transaction.
10. Supporting-evidence coverage percentage and missing-evidence count.
11. Evidence filter: All / With Evidence / Missing Evidence.
12. Top Customer / Source ranking.
13. Payment Method mix/ranking.
14. Department Revenue leaderboard.
15. Target health labels: Behind Target / On Track / Target Achieved.

### Owner real-time coverage additions

- `record_activity()` now guarantees a real-time Owner/Admin notification for meaningful actions performed by staff, Finance, Procurement, Department Heads and Admin users even when an older feature explicitly passed `notify_owner=False`.
- Draft/page-view noise remains audit-only, so complete coverage does not turn ordinary navigation into alerts.
- Notification emails are no longer implicitly triggered for every event; email remains an explicit escalation while in-app/SSE/Web Push remains the complete real-time layer.
- Bell notifications now contain a deep-link route to the closest relevant SAGE page.
- SAGE Pulse live cards can show `Open details` for the originating module.
- Current pages such as Income, Procurement, Operations and Reports participate in automatic live refresh after incoming events.

## New / Extended Endpoints

```text
POST /api/auth/change-password
POST /platform-admin/api/users/<user_id>/reset-password
POST /api/income/entries
GET  /api/income/export.csv
POST /api/finance/performance-targets
```

## Security Notes

- Login email is the current SAGE account identifier; this upgrade does not change it during password rotation.
- Existing passwords cannot be displayed because only password hashes are stored.
- Platform password reset replaces the old password with a randomly generated temporary credential and records the action in Platform Admin Audit.
- Income queries and exports use the same role/department scope as the Income & Sales page.
- Owner notifications remain `organization_id` + recipient `user_id` scoped and therefore do not cross tenants.

---

# October 2026 — Staff Invitation & Reporting Upgrade

This upgrade builds on the completed Owner/Management control architecture without replacing the 18-point Owner requirements already covered by SAGE.

## Phase 1 — Hybrid staff invitations

- Owner/Admin can still create and copy a private staff registration link.
- A new **Mail Invite** mode sends the same secure token directly to the staff member's email address.
- SAGE now accepts both the existing `SMTP_*` configuration names and the EMIS-compatible `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USE_SSL`, `MAIL_USERNAME`, `MAIL_PASSWORD` and `EMAIL_FROM` environment variables.
- When valid mail credentials are present, email notifications are enabled automatically unless `EMAIL_NOTIFICATIONS_ENABLED` explicitly overrides the setting.
- Email delivery is queued outside the web request so SMTP delay does not block the owner interface.

## Phase 2 — Expanded organization departments

All organization templates were expanded substantially. School onboarding now includes additional operational units such as Examinations & Assessment, CBT Centre, Kitchen/Catering, Uniform/Tailoring/Garment Production, Clinic/Sick Bay, Boarding/Hostel, Events, Quality Assurance, Tahfeez, Islamiyyah, Early Years and Cleaning/Sanitation. Healthcare, hospitality, manufacturing, retail, construction, logistics, restaurant, technology, NGO and custom organizations received similar expansion.

Where an expanded department has a strong cross-industry equivalent, the item catalogue can reuse the relevant seed catalogue instead of showing an empty department catalogue.

## Phase 3 — Staff report periods and delivery

Staff accountability reports now support:

```text
Daily
Weekly
Monthly
Quarterly (calendar quarter / three-month reporting window)
```

Submission records include the period, generated metrics, written staff note and source activity. Submitted reports continue to trigger tenant-scoped Owner/Admin notifications and optional email escalation.

## Phase 4 — Reports UI 2.0

Owner/Admin Reports now starts with a searchable **Staff Report Inbox** instead of forcing management to scroll through the export centre first. The inbox exposes staff, department, reference, period, submission time, acknowledgement state, written note, generated summary, source metrics and source activity. Management can acknowledge the report directly from the expanded row.

Staff get four compact report launchers and a table-like report history with draft/submitted/acknowledged states. The report composer makes it clear that SAGE has already collected the tracked activity and the staff note should provide human context.

## Phase 5 — Owner dashboard report visibility

The Owner dashboard now includes a compact **Staff Report Inbox** with the latest submissions and an unread/review count. SAGE Pulse also tells Owner/Admin how many submitted staff reports are waiting for acknowledgement and deep-links directly to Reports.
