# Owner's note: implemented coverage

The audit found existing foundations for most of the note, but incomplete links, reconciliation, budget automation, staff finance capture and individual-business parity. Those gaps were addressed in this update. The connected management workspace is available inside the dashboard for owner, admin and finance accounts.

| Owner requirement | Where it is covered |
| --- | --- |
| 1. Today at a glance | Executive metrics > Today: income, expenses, net, recorded cash, approvals, new requests and outstanding payments. |
| 2. Department breakdown | Dashboard department drill-down and management workspace > Departments: income, expenses, request counts, approved amounts, actual acquisitions and budgets. |
| 3. Purchase tracking | Purchase tracking and connected record drawer: request, approval, purchase, receipt, delivery, verification and recorded payment/funding. |
| 4. Inventory and assets | Inventory & assets, named stock issues, explicit damage/loss, returns, locations, custodians, stock valuation and movement history. |
| 5. Staff accountability | Signed-in actors on actions, staff workload, recipient/custodian acknowledgments and linked transaction/item history. |
| 6. Financial reports | Daily, weekly, monthly, quarterly, yearly and all-record exports; income, expenses, recorded net, actual recorded cash movements, receivables and payables. |
| 7. Budget control | Approval reservations, acquisition actuals, releases on rejection, finance/department expense posting, explicit cost-centre selection and budget alerts. |
| 8. Pending actions | First-page attention queue and workspace actions: approvals, documents, reviews, account allocations, reconciliation, deliveries, overdue balances, stock and assigned follow-ups. |
| 9. Branch comparison | Organization > branch > department > transaction, with selected-period financial totals and current balances. Configure the real branch/department mappings in Settings. |
| 10. Audit trail | Important ORM changes produce before/after snapshots in the same transaction. History is append-only through the application; deleted records remain viewable from retained snapshots. |
| 11. Analytics and alerts | Spend spikes, repeated invoice/payment references, unusual transactions, approval authority, acquisition overruns, receipts, comparable-unit supplier price rises and self-approval checks. |
| 12. Report export | CSV, Excel and PDF for finance, procurement, inventory, assets, people, departments, branches, suppliers and audit; connected history exports too. |
| 13. Receivables | Customer, outstanding balance, actual invoice date/age when recorded, due/overdue amounts and complete saved payment history. |
| 14. Payables | Vendor, balance, due date, overdue state and saved payment history. |
| 15. Reconciliation | Actual statement closing balance versus opening balance plus entries through the closing date; selected, checked entries are marked reconciled with a permanent match record. |
| 16. Suppliers | Supplier/source, purchase/expense history, total value, outstanding obligations and saved item-level prices for request purchases and direct purchases. |
| 17. Approval system | Configurable thresholds; department-head approvals within their department; higher-role requirements; self-approval blocked; unmatched configured ranges require the owner. |
| 18. Executive dashboard | The four leading cards plus compact receivables/payables/inventory/budget strip show all eight requested figures, followed by attention and connected workspaces. |

## Fifteen additional features

1. Selected-period comparison with the preceding calendar period.
2. Receipt-completeness percentage from completed, documented purchases.
3. Debt aging buckets: not overdue, 1-30, 31-60, 61-90, 90+ and no due date.
4. Balances due in the next seven days.
5. Exact stock shortages against recorded reorder levels.
6. Asset warranties expiring in the next 30 days.
7. Recorded cash coverage in days, based on recorded balances and the last 30 days of cash outflow. This is a ratio, not a prediction.
8. Supplier concentration as a share of recorded supplier spend.
9. Average completed request-to-verification cycle duration.
10. Staff workload: pending requests, assigned actions and period activity.
11. Requests waiting more than 48 hours for approval.
12. Saved draft recovery for finance and acquisitions.
13. Department recorded net margins, with no percentage invented when there is no recorded revenue.
14. Budget revision workflow with retained allocation history.
15. Assigned follow-ups with priorities, deadlines, progress, snoozing and append-only comments.

## Staff and individual businesses

Staff dashboards show income, expense and recorded net within their permitted scope. Ordinary staff do not receive organization-wide bank or payroll details. Unassigned staff cannot fall back to company-wide finances.

Actual Income / Actual Expense department actions create linked financial and ledger records automatically. Recognized revenue/collection and explicit expense activity types do the same. Other operational amounts remain activity logs: the system does not guess that every activity amount represents income or spending. Supporting evidence can be uploaded with the activity.

Both organization and individual owners use the shared dashboard and connected controls. In Finance, a direct purchase can be recorded as stock or an asset, with actual item quantities/prices, supplier, receipt and custody links. No owner-to-self request is generated. Posting a payment against an existing purchase does not post that purchase expense again.

Owner/admin notifications remain database-backed with SSE and polling. A dashboard change token also refreshes saved business changes across tabs. Refresh is deferred while a form or record drawer is being used, without discarding the pending change. Optional email and Web Push remain dependent on the deployment's existing configuration.

## Honest data boundaries

- No demo organization, user, transaction, invoice or forecast is seeded into the application.
- Dashboard values are saved-record totals or explicitly labelled calculations. Missing evidence, recipients, account assignments, invoice dates and prior-period baselines remain unknown or flagged.
- Recorded net is posted income/revenue less tracked expense categories. Recorded cash flow is cash-direction ledger activity and historical request disbursements, with no second expense generated for a cash-only advance/payment.
- Cash balances depend on recorded account opening balances and assigned ledger entries. Unallocated cash is surfaced for assignment.
- A purchase expense alone is not proof that payment took place. Recorded funding/payments and evidence appear separately.
- Invoice owing age uses the actual invoice date once entered. Without it, the UI says how long the balance has been recorded rather than inventing its original age.
- Historical opening receipt/payment amounts remain distinct from dated payment history. Missing original payment dates are not manufactured.
- Existing records can be connected through the supporting-record picker. Missing historical actions/documents must be entered or acknowledged by the responsible people; the application cannot reconstruct unrecorded events.
- Normal edits/deletions retain audit history. The pre-existing, explicitly authenticated platform-admin permanent tenant purge remains a deliberate exception.

## Installation and validation

Development startup with `SAGE_AUTO_CREATE_SCHEMA=true` creates the nine additive control tables. Existing business columns and records are preserved. For a deployment with automatic creation disabled, run:

```powershell
python -m flask --app app sage-upgrade-owner-controls
```

Restart `python app.py`, then reload the dashboard to load the new APIs, styles and scripts.

Run backend acceptance tests with:

```powershell
python -m unittest discover -s tests -v
```

Validation for this update includes 28 backend regression/acceptance tests and 260 browser checks, all management views on 320-1920px widths, actual copied evidence retrieval, all 51 report format/category downloads, staff-to-owner live propagation, and visual checks of PDF summary/history exports. Tests use disposable databases and copied evidence. Production PostgreSQL and externally configured SMTP/Web Push were not exercised by these local checks.
