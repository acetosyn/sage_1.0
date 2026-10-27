# SAGE Upgrade 4.0

The current workspace, including its uncommitted UI improvements, is the source of truth. This release extends the existing Flask/SQLAlchemy services and SAGE shell. No replacement project or data reset is used.

## Dependency-aware implementation

1. **Foundations and Events:** additive schema, scoped access, transactional financial posting/idempotency, event/campaign plans, budgets/funding, resources and outcome review.
2. **Customers and credit sales:** shared CRM, invoices, receivables, partial collections, event attribution and customer history.
3. **Suppliers and imprest:** extend the supplier master, procurement/payables history, accountable cash advances, expenditure, returns and replenishment approval.
4. **Daily reconciliation and branches:** channel totals from actual collections, counted cash/variance approval, branch membership, scoped operations and branch comparison.
5. **Stock and recurring obligations:** batch/expiry/pricing, movements/transfers/counts, bills/renewals, compliance documents and deduplicated reminders.
6. **People and connected intelligence:** employee financial profiles, commission/advances/loans/claims, payroll approval/payment, reports/exports, automation and SAGE AI context.

## Accounting rules

- Business postings and payment histories are append-only and carry source identifiers and transaction dates.
- Cash advances are cash movements; retirement records expense without paying cash twice.
- Credit invoices recognize sales once; collections reduce receivables and move cash without recognizing the sale again.
- Every new mutation is committed atomically with its audit/activity records. Idempotency keys and optimistic versions prevent duplicate retries and stale concurrent changes.
- Existing records are retained. New tables are additive; legacy finance models remain the summary source used by existing dashboards.

## Verification

Each phase receives integration tests against an isolated database before proceeding. Final verification includes existing regressions, tenant/role/branch denial cases, retry/concurrency checks, native page rendering, responsive layout and JavaScript syntax checks. Production schema installation is available through a dedicated CLI command; reminders have a scheduler-friendly CLI command.

Progress and precise validation results will be recorded here as implementation proceeds.

### Phase 1

Implemented shared additive models, atomic API commands, idempotent financial postings and optimistic record versions. Events now support campaign children, budget items, approval/funding, cash returns, receipt-backed expenditure, stock/asset issues and reconciliation, post-event reports, management review and closure. Individual owners approve their submitted plan automatically. Six isolated integration tests pass for lifecycle, tenant/role denial, funding/expense separation, retry protection, retirement and stock accountability.

### Phase 2

Implemented shared CRM contacts, lead/prospect/customer progression, dated interactions and follow-ups, event attribution, itemized invoice API, stock-backed sales, credit due dates, partial collections and customer history. The existing finance receivable is updated rather than duplicated. Existing Finance collection actions recognize linked SAGE 4.0 invoices and do not post revenue a second time. Invoice tax is separately recorded as a liability. Eleven cumulative acceptance tests pass.

### Phase 3

Extended existing suppliers with contact/bank/TIN/service/rating data, procurement-linked quotations and delivery totals, documents and bills. Acquisition-linked bills reuse the existing expense; standalone bills recognize expense once and subsequent payments only move cash. Added petty-cash opening issues, receipt-backed retirement, returns, Requests-based replenishment approval and cash ceilings. Existing Acquisition/Funding actions reject imprest replenishments so they cannot become duplicate purchases. Fifteen cumulative tests pass, including rendering all five new native pages with actual fixture records.

### Phase 4

Implemented branch memberships, branch finance-account assignment, and a request-scoped ORM firewall for branch-restricted legacy and new operational data. Added branch comparison and daily channel reconciliation based on recorded collections rather than unpaid invoice totals. Closes enforce variance explanations, submission, independent review, stale-transaction detection and audited reopening; individual owners can reconcile their own close. Eighteen cumulative tests pass, including branch restrictions on legacy financial queries and new event actions.

### Phase 5

Added inventory profiles, batch/expiry and FEFO allocations, prices/margins, branch transfers retaining batch history, damage/expiry, controlled adjustments and stale-safe stock counts. Sales and event resources now use the same stock engine. Batch registration on acquisitions cannot receive quantities twice. Bills have calendar-safe recurrence, period-specific payment protection, expense posting and cancellation history. Compliance documents retain renewal evidence/history. Reminders for upcoming/overdue bills, documents, CRM follow-ups and credit invoices are deduplicated. Twenty-three cumulative acceptance tests pass, including rendering all ten native module pages.

### Phase 6

Added employee salary policies, sales-based commission, bonus/allowance/deduction adjustments, requested/approved/issued staff advances and loans, direct and payroll-based recovery, receipt-backed claims, monthly draft/approval/payment payroll, individual payslips, PAYE records and separately recorded statutory remittance. Existing Finance payroll entries are linked to the new slips. Payroll cost is recognized once at gross plus employer pension; net cash and later remittance do not create additional expenses.

Connected operations reports, period filters, safe CSV exports, dashboard/report summaries, SAGE AI context and deduplicated reminder automation are implemented. Reminder checks run during active owner/finance use every 15 minutes, or unattended through the CLI. Campaigns can allocate money already released to child events without a second bank outflow; child approvals and external funding cannot exceed the campaign envelope. Record history connects new sales/customers/events to existing finance records.

## Verification completed

- **64 automated tests pass**, including the existing owner-control and datetime suites.
- **166 full-shell/partial HTTP responses pass** across Organization owner, finance, staff and Individual owner accounts, including denied pages.
- All 12 new pages render with real isolated fixture records. Browser checks cover desktop, a 390 px mobile viewport, mobile event creation and partial navigation to CRM.
- JavaScript syntax checks pass for the new module script and modified navigation script.
- All **40 business tables compile for PostgreSQL**. A live PostgreSQL run was unavailable because this local environment lacks `psycopg`; its existing configured fallback is SQLite.
- The active local SQLite database was backed up using SQLite's online backup API. The additive schema install retained content fingerprints for **all 50 legacy tables**, and `PRAGMA integrity_check` returned `ok`. The backup and verification JSON are in `storage/backups/`, which is excluded from Git.

## Running and deploying

The existing development command remains `python app.py`. Restart an already running SAGE process to load the Python changes.

For a production database, take a database-native backup, install the existing requirements (including `psycopg`), and run:

```text
flask --app app sage-upgrade-4
```

This creates/verifies only additive `business_*` tables. It does not drop, recreate or overwrite historical tables. The command is idempotent. The SQLite-specific backup/upgrade helper used locally is `python tools/upgrade_sage4_local.py`.

For unattended reminders, run this command from the deployment's existing scheduler, for example every 15 minutes:

```text
flask --app app sage-reminders
```

The reminder worker never pays bills or releases funds automatically. It creates deduplicated SAGE notifications for due/overdue obligations, customer follow-ups and balances, upcoming events, low stock and batch expiry.

## Operating notes

- Departments, branches and approval handoffs are optional for Individual businesses. Individual event plans self-approve on submission, and individual daily closes can self-reconcile. Financial actions still require explicit recorded amounts and dates.
- PAYE amounts and pension bases/rates are configured by the business and retained on each payslip. This release maintains payroll/tax records; it does not claim automatic statutory tax determination or submit returns to government systems.
- Invoices preserve item/tax breakdown, stable identifiers and separate external-invoice/transmission fields. Government e-invoicing transmission is not enabled without a real authorized external integration.
- Financial postings use the tenant's accounting currency. Existing SAGE display-currency conversion remains presentation-only.
- Opening stock and physical receipts do not themselves fabricate a cash payment. Record purchase costs through existing Procurement/direct purchases or supplier bills. Use **Assign batch to existing stock** for an acquisition already received.
- Daily closes compare recorded collections with counted channels; unpaid credit amounts remain receivables. No synthetic cash adjustment is posted to hide a variance.
- In event outcomes, connected invoice revenue is distinguished from declared post-event revenue. Campaign reports capture direct results; child results are aggregated automatically.
- New payment actions require idempotency keys, retain source links and use optimistic versions. Branch restrictions cover legacy finance, property/movement reads, evidence downloads and the new modules. Staff see their own payroll/claims/advance details.
- Assigning a manager, cash holder or salesperson infers their department/branch when the owner leaves those fields blank. Staff assigned to bills or compliance documents can read those records and evidence; financial and renewal actions remain restricted to Finance/owners.

## Requirement-to-workspace map

| Requirement | Native workspace / integration |
| --- | --- |
| Events, campaigns, budgets, funding, resources, reports and ROI | Events & Campaigns, existing finance/stock/assets/evidence/history |
| Leads, prospects, repeat customers, invoices and contact history | Customers & CRM |
| Credit sales, due/overdue balances, aging and partial payments | Debtors & Credit Sales plus existing Finance receivables |
| Vendor details, quotations, procurement/delivery history and payables | Suppliers & Vendors plus existing supplier/acquisition/payable records |
| Petty cash, receipts, returns and replenishment | Petty Cash & Imprest plus Requests approval |
| Daily cash, transfer, POS and other payment-channel accountability | Daily Sales / POS Close |
| Branch results, staff/account access and property allocation | Branches & Shops, department mappings and scoped legacy reads |
| Batches, expiry, pricing, FEFO, transfers, damage and stock counts | Advanced Stock Control plus existing Inventory |
| Recurring costs, due stages and expense posting | Bills & Renewals |
| Documents, expiry, renewal evidence/history and alerts | Compliance Centre |
| Salary, commission, loans, claims, payslips and payroll records | Staff Finance & Payroll plus existing Finance payroll/tax registers |
| Period reporting, exports, reminders and cross-module intelligence | Business Operations Reports, dashboard, Reports, Audit, Notifications and SAGE AI |
