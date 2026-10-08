/* Connected management workspace. All values arrive from authenticated SAGE APIs. */
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const recordKinds={PurchaseRequest:"request",PurchaseFulfillment:"fulfillment",FinancialRecord:"financial_record",FinanceLedgerEntry:"finance_ledger",InventoryItem:"inventory_item",AssetItem:"asset",StockMovement:"stock_movement",AssetMovement:"asset_movement",DepartmentOperation:"department_operation",FinanceReceivable:"receivable",FinancePayable:"payable",BudgetAllocation:"budget",request:"request",fulfillment:"fulfillment",inventory_item:"inventory_item",asset:"asset",receivable:"receivable",payable:"payable"};
  const currency = () => window.SAGE_USER?.currency || '';
  const money = value => value === null || value === undefined ? '<span>Not recorded</span>' : `<span data-private-value>${escape(currency())} ${Number(value).toLocaleString(undefined,{maximumFractionDigits:2})}</span>`;
  const date = value => value ? escape(new Date(value).toLocaleString()) : 'Not recorded';
  const empty = message => `<div class="dashboard-empty"><strong>${escape(message)}</strong><p>Records appear here as your team saves real activity.</p></div>`;
  const recordButton = (kind,id,label) => `<button type="button" class="control-record-link" data-open-record="${escape(kind)}:${escape(id)}">${escape(label)}</button>`;
  const table = (headers,rows) => rows.length ? `<div class="control-table-scroll"><table class="data-table control-table"><thead><tr>${headers.map(header=>`<th>${escape(header)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map((cell,index)=>`<td data-label="${escape(headers[index])}">${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : empty('No matching records yet.');
  const metric = (label,value,note='') => `<article><span>${escape(label)}</span><strong>${money(value)}</strong>${note?`<small>${escape(note)}</small>`:''}</article>`;
  const heading = (title,copy) => `<div class="control-section-heading"><h3>${escape(title)}</h3><p>${escape(copy)}</p></div>`;
  const options = (rows,label='name') => rows.map(row=>`<option value="${escape(row.id)}">${escape(row[label])}</option>`).join('');
  let refreshPage, activeWorkspace, drawerData, drawerSource, opener, changeToken, checkingChanges = false;
  const drawer = document.getElementById('controlRecordDrawer');
  const backdrop = document.getElementById('controlRecordBackdrop');

  async function api(url, options={}) {
    const response = await fetch(url,{cache:'no-store',...options});
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.message || 'The request could not be completed.');
    return data;
  }
  function jsonPost(url,payload,method='POST') { return api(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); }
  function syncPrivacy() { window.SAGEDashboard?.syncPrivacy?.(); }
  function noteForm(endpoint,fields,submit='Save',method='POST') { return `<form class="control-form" data-control-form="${escape(endpoint)}" data-method="${method}">${fields}<p class="control-form-message" role="status"></p><button type="submit" class="btn primary compact">${escape(submit)}</button></form>`; }

  function render(snapshot, section, root) {
    const t=snapshot.totals, insight=snapshot.insights;
    const managerRole=root.dataset.controlRole;
    let html='';
    if(section==='actions') {
      html=heading('What needs management’s attention?','Urgent, Attention Required and Normal items from current records.')+
        snapshot.alerts.map(row=>`<details class="control-disclosure"><summary><span class="control-priority ${escape(row.priority)}">${row.priority==='urgent'?'Urgent':row.priority==='normal'?'Normal':'Attention Required'}</span><strong>${escape(row.title)}</strong><b>${escape(row.count)}</b></summary><div>${row.detail?`<p>${escape(row.detail)}</p>`:''}${row.records.map(record=>`<div class="control-list-row">${recordButton(record.type,record.id,record.reference||record.title)}<span>${escape(record.title)}</span>${money(record.amount)}</div>`).join('')}${!row.records.length?'<p>Review the relevant budget or analytics section below.</p>':''}</div></details>`).join('');
      if(!snapshot.alerts.length)html+=empty('No outstanding exceptions in the recorded data.');
    }
    if(section==='money') {
      html=heading('What came in, what went out, and where it went','Posted income and expenses use the selected calendar period. Cash flow uses recorded money movements.')+
        `<div class="control-metrics">${metric('Income',t.income)}${metric('Expenses',t.expenses)}${metric('Recorded net',t.net)}${metric('Cash received',t.cash_in)}${metric('Cash paid',t.cash_out)}${metric('Net cash movement',t.cash_net)}</div>`+
        (snapshot.comparison.available?`<div class="control-comparison">Previous period: income ${money(snapshot.comparison.income)} · expenses ${money(snapshot.comparison.expenses)} · net ${money(snapshot.comparison.net)}.<br>Change in recorded net: ${money(t.net-snapshot.comparison.net)}</div>`:'')+
        table(['Transaction','Department','Amount','Responsible person','Date'],snapshot.transactions.map(row=>[recordButton(row.type,row.id,row.title),escape(row.department||'Business-wide'),money(row.amount),escape(row.actor||'Former / system user'),date(row.date)]))+
        heading('Cash-flow records','Funding is a cash movement, not a second purchase expense.')+
        table(['Reference','Cash direction','Account','Amount','Date'],snapshot.cash_movements.map(row=>[recordButton(row.type,row.id,row.reference||row.title),escape(row.direction),escape(row.account||'Unallocated historical funding'),money(row.amount),date(row.date)]));
    }
    if(section==='departments') {
      html=heading(root.dataset.controlMode==='individual'?'Business workspaces':'Department breakdown','Income and expense figures use the selected period; budgets and purchase commitments show current recorded balances.')+
        snapshot.departments.map(row=>`<details class="control-disclosure"><summary><strong>${escape(row.name)}</strong><span>${row.requests} request(s)</span><b>${money(row.net)}</b></summary><div><div class="control-metrics">${metric('Income',row.income)}${metric('Expenses',row.expenses)}${metric('Approved amount',row.approved)}${metric('Actually spent',row.actual_spent)}${metric('Remaining budget',row.remaining_budget)}</div><p>Recorded net margin: ${row.margin_percent===null?'No recorded revenue to calculate a margin.':escape(row.margin_percent)+'%'}</p>${table(['Transaction','Amount','Recorded by','Date'],row.transactions.map(record=>[recordButton(record.type,record.id,record.title),money(record.amount),escape(record.actor||'Former user'),date(record.date)]))}</div></details>`).join('');
      if(!snapshot.departments.length)html+=empty('No departments configured.');
    }
    if(section==='purchases') {
      html=heading('Purchase tracking','Open a purchase to follow Request → Approval → Purchase → Receipt → Delivery → Verification → Payment.')+
        table(['Purchase','Status','Approved','Actual spent','Supplier','Requester / approver / buyer'],snapshot.purchases.map(row=>[recordButton(row.type,row.id,row.reference+' · '+row.title),escape(row.status),money(row.approved),money(row.actual),escape(row.supplier||'Not yet recorded'),escape([row.requester,row.approver,row.buyer].filter(Boolean).join(' / '))]));
      if(root.dataset.controlMode==='individual') html+=`<p class="control-help">Direct business expenses and their receipts are traceable in Money & transactions. You can link inventory, assets or other supporting records in their history drawer.</p>`;
    }
    if(section==='inventory') {
      html=heading('Inventory and asset custody','Open an item for its complete accountability timeline, connected purchases and supporting documents.')+
        `<div class="control-metrics">${metric('Total stock value',t.inventory_value)}<article><span>Damaged / lost assets</span><strong>${snapshot.assets.filter(row=>row.condition==='damaged'||row.status==='lost').length}</strong></article></div>`+
        table(['Stock item','Current stock','Total value','Location','Reorder shortage'],snapshot.inventory.map(row=>[recordButton('inventory_item',row.id,row.name),escape(row.quantity+' '+row.unit),money(row.value),escape(row.location||'Not recorded'),escape(row.reorder_deficit+' '+row.unit)]))+
        heading('Assets','Current location, custodian, condition and movement history.')+
        table(['Asset','Custodian','Location','Condition / status','Value'],snapshot.assets.map(row=>[recordButton('asset',row.id,row.title),escape(row.custodian||'Unassigned'),escape(row.location||'Not recorded'),escape(row.condition+' / '+row.status),money(row.value)]))+
        heading('Recent stock issues, returns, damage and loss','Open any movement or item to read the full history.')+
        table(['Item','Movement','Quantity','Responsible person','Date'],snapshot.stock_movements.map(row=>[recordButton(row.type,row.id,row.item),escape(row.movement),escape(row.quantity),escape(row.actor),date(row.date)]));
    }
    if(section==='staff') {
      html=heading('Staff accountability and workload','The selected period controls activity counts. Pending requests and assigned follow-ups are current.')+
        table(['Person','Role','Pending requests','Assigned actions','Period actions'],snapshot.staff.map(row=>[escape(row.name),escape(row.role),escape(row.pending_requests),escape(row.assigned_tasks),escape(row.period_actions)]))+
        heading('Who handled the purchase?','Transaction history shows the requester, approver, purchaser, named recipient, verifier and later stock/asset movements.')+
        table(['Request','Requester','Approver','Purchaser','Open history'],snapshot.purchases.map(row=>[escape(row.reference),escape(row.requester),escape(row.approver||'Not recorded'),escape(row.buyer||'Not recorded'),recordButton('request',row.id,'People & documents')]));
    }
    if(section==='budgets') {
      html=heading('Budget control','Approvals reserve the selected budget; finalized purchases replace the commitment with actual spend. Multiple cost centres require an explicit choice.')+
        snapshot.budgets.map(row=>`<details class="control-disclosure"><summary><strong>${recordButton('budget',row.id,row.name)}</strong><span>${escape(row.department)}</span><b>${row.used_percent===null?'No allocation':escape(row.used_percent)+'% used'}</b></summary><div><div class="control-metrics">${metric('Allocation',row.budget)}${metric('Actual spent',row.spent)}${metric('Committed',row.committed)}${metric('Remaining',row.remaining)}</div>${noteForm('/api/management/budgets/'+row.id,`<label>Revised budget<input name="revised_budget" type="number" min="0.01" step="0.01" required value="${row.budget}"></label><label>Reason<textarea name="notes" required></textarea></label>`,'Revise allocation','PATCH')}</div></details>`).join('')+
        heading('Choose a cost centre for an approved purchase','This is useful when several active budgets exist for a department.')+
        noteForm('/api/management/budget-reservations',`<label>Approved purchase<select name="request_id" required><option value="">Choose purchase</option>${snapshot.purchases.filter(row=>['approved','money_sent','fulfilled','verified'].includes(row.status)).map(row=>`<option value="${row.id}">${escape(row.reference+' · '+row.title)}</option>`).join('')}</select></label><label>Budget<select name="budget_id" required><option value="">Choose budget</option>${options(snapshot.budgets)}</select></label>`,'Link budget');
    }
    if(section==='debts') {
      html=heading('Money owed to us and by us','Aging uses days past the recorded due date. Payment history contains saved ledger payments.')+
        `<div class="control-metrics">${metric('Receivables',snapshot.receivables.total)}${metric('Overdue receivables',snapshot.receivables.overdue)}${metric('Payables',snapshot.payables.total)}${metric('Overdue payables',snapshot.payables.overdue)}</div>`;
      for(const [label,group] of [['Accounts receivable',snapshot.receivables],['Accounts payable',snapshot.payables]]) html+=heading(label,'Open a balance to see payments, evidence and changes.')+
        `<div class="control-aging">${Object.entries(group.buckets).map(([bucket,value])=>`<span>${escape(bucket)}<b>${money(value)}</b></span>`).join('')}</div>`+
        table(['Who','Outstanding','How long recorded','Due date','Overdue days','Status / history'],group.rows.map(row=>[recordButton(row.type,row.id,row.name),money(row.balance),escape(row.age_days===null?'Invoice date not recorded; first logged '+row.recorded_days+' days ago':row.age_days+' days since '+row.invoice_date),escape(row.due_date||'No date recorded'),escape(row.overdue_days),`<details><summary>${escape(row.status)} · ${row.payments.length} recorded payment(s)</summary>${row.opening_payment?'<p>Opening amount already received/paid: '+money(row.opening_payment)+'. Its original payment date was not recorded.</p>':''}${row.payments.map(payment=>`<p>${recordButton(payment.type,payment.id,payment.reference)} ${money(payment.amount)} · ${escape(payment.actor||'Former user')} · ${date(payment.date)}</p>`).join('')}</details>`]));
    }
    if(section==='reconcile') {
      html=heading('Bank and cash reconciliation','Closing balances include opening balances and posted entries through the selected end date. Match only entries you checked against the real statement.')+
        `<div class="control-metrics">${snapshot.accounts.map(row=>metric(row.name,row.balance)).join('')}</div>`;
      if(snapshot.accounts.length)html+=noteForm('/api/finance/reconciliations',`<label>Account<select name="account_id" required data-reconcile-account>${options(snapshot.accounts)}</select></label><div class="control-form-grid"><label>Period start<input type="date" name="period_start" required></label><label>Period end<input type="date" name="period_end" required></label></div><label>Statement closing balance<input type="number" step="0.01" name="statement_balance" required></label><label>Statement reference<input name="statement_reference"></label><fieldset><legend>Entries checked against the statement</legend>${snapshot.unreconciled.map(row=>`<label class="control-checkbox"><input type="checkbox" name="ledger_ids" value="${row.id}" data-ledger-account="${escape(row.account_id||'')}"><span>${escape(row.reference)} · ${money(row.amount)} · ${date(row.date)}</span></label>`).join('')||'<p>No unmatched account entries.</p>'}</fieldset><label>Reconciliation notes<textarea name="notes"></textarea></label>`,'Save reconciliation');
      else html+=empty('Record a bank or cash account in Finance to reconcile it.');
      html+=heading('Unallocated cash postings','Assign an existing posting to its real account; this does not create a second transaction.')+
        snapshot.unallocated_cash.map(row=>`<details class="control-disclosure"><summary><strong>${recordButton(row.type,row.id,row.reference)}</strong><span>${escape(row.title)}</span><b>${money(row.amount)}</b></summary><div>${noteForm('/api/management/ledger/'+row.id+'/account',`<label>Actual bank/cash account<select name="account_id" required>${options(snapshot.accounts)}</select></label>`,'Assign account')}</div></details>`).join('');
    }
    if(section==='branches') {
      html=heading('Organization → branch → department → transaction','Branch totals show recorded balances; each department opens its underlying entries.')+
        snapshot.branches.map(branch=>`<details class="control-disclosure"><summary><strong>${escape(branch.name)}</strong><span>${escape(branch.code)}</span><b>Net ${money(branch.net)}</b></summary><div><div class="control-metrics">${metric('Income',branch.income)}${metric('Expenses',branch.expenses)}${metric('Inventory',branch.inventory_value)}${metric('Receivables',branch.receivables)}${metric('Payables',branch.payables)}</div><p>Budget usage: ${escape(branch.budget_usage.toFixed(1))}%</p>${branch.departments.map(department=>`<details class="control-disclosure"><summary><strong>${escape(department.name)}</strong><b>Net ${money(department.income-department.expenses)}</b></summary><div>${table(['Transaction','Amount','Person','Date'],(snapshot.departments.find(row=>row.id===department.id)?.transactions||department.recent).map(row=>[recordButton(row.type,row.id,row.title),money(row.amount),escape(row.actor||'Former user'),date(row.date)]))}</div></details>`).join('')}</div></details>`).join('');
      if(!snapshot.branches.length)html+=empty('No branches configured. Use Settings to add real locations.');
    }
    if(section==='suppliers') {
      html=heading('Supplier management','Purchase history, prices, spend, current obligations and concentration in your recorded supplier spend.')+
        snapshot.suppliers.map(row=>`<details class="control-disclosure"><summary><strong>${escape(row.name)}</strong><span>${escape(row.share_percent)}% of recorded supplier spend</span><b>${money(row.spend)}</b></summary><div><p>Outstanding: ${money(row.outstanding)}</p>${table(['Purchase / posting','Amount','Date'],row.history.map(item=>[recordButton(item.type,item.id,item.title),money(item.amount),date(item.date)]))}${table(['Item','Unit price','Unit','Recorded date'],row.prices.map(item=>[escape(item.item),money(item.price),escape(item.unit),date(item.date)]))}</div></details>`).join('');
      if(!snapshot.suppliers.length)html+=empty('No supplier records yet.');
    }
    if(section==='audit') {
      html=heading('Audit history','Latest 100 changes. Open the related record or export the full audit report for older history.')+
        snapshot.audit.map(row=>`<details class="control-disclosure"><summary><strong>${escape(row.actor)}</strong><span>${escape(row.action)} · ${escape(row.entity_type)}</span><small>${date(row.date)}</small></summary><div>${recordKinds[row.entity_type]?recordButton(recordKinds[row.entity_type],row.entity_id,"Open retained history"):""}<div class="control-audit-snapshots"><div><strong>Before</strong><pre>${escape(JSON.stringify(row.before||{},null,2))}</pre></div><div><strong>After</strong><pre>${escape(JSON.stringify(row.after||{},null,2))}</pre></div></div></div></details>`).join('');
      if(!snapshot.audit.length)html+=empty('No revisions recorded yet. New important changes retain before/after snapshots.');
    }
    if(section==='insights') {
      html=heading('Additional business insights','Calculated from saved records. Missing inputs stay unknown; estimates are not presented as money already received or spent.')+
        `<div class="control-insight-grid"><article><span>Receipt completeness</span><strong>${insight.evidence_coverage===null?'No completed purchases':insight.evidence_coverage+'%'}</strong><p>Completed purchases with recorded receipts.</p></article><article><span>Average completed purchase cycle</span><strong>${insight.purchase_cycle_days===null?'Not enough completed history':insight.purchase_cycle_days+' days'}</strong><p>Submitted request to verified acquisition.</p></article><article><span>Recorded cash coverage</span><strong>${insight.cash_coverage_days===null?'Not enough account/spending data':insight.cash_coverage_days+' days'}</strong><p>Recorded available cash divided by average daily cash paid over the last 30 days. A ratio, not a prediction.</p></article></div>`;
      for(const [title,rows,labels] of [
        ['Balances due in the next 7 days',insight.due_soon,['Name','Amount / shortage','Due']],
        ['Reorder shortages',insight.reorder,['Item','Amount / shortage','Current stock']],
        ['Warranties expiring in 30 days',insight.warranties,['Asset','Amount / shortage','Expiry']],
        ['Approvals older than 48 hours',insight.stale_requests,['Request','Amount / shortage','Created']],
        ['Recover saved drafts',insight.drafts,['Draft','Amount / shortage','Saved']],
        ['Approved purchases awaiting a budget choice',insight.unbudgeted_requests,['Purchase','Amount / shortage','Created']]
      ])html+=`<details class="control-disclosure"><summary><strong>${escape(title)}</strong><b>${rows.length}</b></summary><div>${table(labels,rows.map(row=>[recordButton(row.type,row.id,row.name||row.reference||row.title),row.deficit!==undefined?escape(row.deficit+' '+row.unit):row.balance!==undefined?money(row.balance):row.amount!==undefined?money(row.amount):'—',escape(row.due_date||row.date||row.quantity||'—')]))}</div></details>`;
      html+=heading('Recorded net margin by department','A margin requires positive recorded revenue.')+table(['Department','Income','Net','Margin'],snapshot.departments.map(row=>[escape(row.name),money(row.income),money(row.net),row.margin_percent===null?'No revenue recorded':escape(row.margin_percent+'%')]))+
        heading('Supplier concentration','Share of actual recorded supplier purchase/expense value.')+table(['Supplier','Spend','Share'],snapshot.suppliers.map(row=>[escape(row.name),money(row.spend),escape(row.share_percent+'%')]));
    }
    if(section==='tasks') {
      html=heading('Assigned management follow-ups','Named responsibility, due dates, snoozing, progress and permanent comments.')+
        noteForm('/api/management/tasks',`<label>Action title<input name="title" required maxlength="180"></label><div class="control-form-grid"><label>Assign to<select name="assigned_to_id"><option value="">Unassigned</option>${options(snapshot.users)}</select></label><label>Priority<select name="priority"><option value="attention">Attention Required</option><option value="urgent">Urgent</option><option value="normal">Normal</option></select></label><label>Due date<input name="due_date" type="date"></label><label>Snooze until<input name="snoozed_until" type="date"></label></div><label>Notes<textarea name="notes"></textarea></label>`,'Create follow-up')+renderTasks(snapshot.tasks,true,snapshot.users);
    }
    if(section==='reports') {
      const reports=[['summary','Business summary'],['income','Income'],['expenses','Expenses'],['profit-loss','Profit / loss'],['cash-flow','Actual cash flow'],['departments','Departments'],['procurement','Procurement'],['inventory','Inventory'],['assets','Assets'],['staff','Staff activity'],['audit','Audit history'],['receivables','Accounts receivable'],['payables','Accounts payable'],['suppliers','Suppliers'],['branches','Branches']];
      html=heading('Report exports','Choose Today, Week, Month, Quarter, Year or All records above. The same saved dataset powers CSV, Excel and PDF.')+`<div class="control-export-list">${reports.map(([key,label])=>`<div><strong>${escape(label)}</strong><span>${['csv','xlsx','pdf'].map(format=>`<a href="/api/reports/export/${key}.${format}?period=${snapshot.period}" class="btn tiny secondary">${format==='xlsx'?'Excel':format.toUpperCase()}</a>`).join('')}</span></div>`).join('')}</div>`;
    }
    if(section==='approvals') {
      html=heading('Configurable approval limits','Self-approval is blocked. A configured range without a matching rule requires owner approval.')+
        table(['Rule','From','Through','Required role','Priority'],snapshot.approval_rules.map(row=>[escape(row.name),money(row.minimum),row.maximum===null?'No ceiling':money(row.maximum),escape(row.role.replaceAll('_',' ')),escape(row.priority)]));
      if(['owner','admin'].includes(managerRole))html+=noteForm('/api/management/approval-rules',`<label>Rule name<input name="name" required></label><div class="control-form-grid"><label>Minimum<input name="min_amount" type="number" min="0" step="0.01" required value="0"></label><label>Maximum (optional)<input name="max_amount" type="number" min="0" step="0.01"></label><label>Approver<select name="required_role"><option value="department_head">Department head</option><option value="finance">Finance</option><option value="admin">Senior manager / admin</option><option value="owner">Owner</option></select></label><label>Rule priority<input type="number" min="1" name="priority" value="100"></label></div>`,'Save approval rule');
    }
    root.querySelector('[data-control-content]').innerHTML=html;
    syncPrivacy();
    bindForms(root);
    filterReconciliation(root);
  }

  function renderTasks(tasks,management=false,users=[]) {
    if(!tasks.length)return empty('No assigned follow-ups yet.');
    return tasks.map(task=>`<details class="control-disclosure"><summary><strong>${escape(task.title)}</strong><span>${escape(task.assignee)} · ${escape(task.status.replaceAll('_',' '))}</span><small>${task.due_date?'Due '+escape(task.due_date):'No due date'}${task.snoozed_until?' · snoozed until '+escape(task.snoozed_until):''}</small></summary><div><p>${escape(task.notes||'')}</p>${task.comments.map(comment=>`<p class="control-comment"><b>${escape(comment.actor)}</b> · ${date(comment.date)}<br>${escape(comment.body)}</p>`).join('')}${noteForm('/api/management/tasks/'+task.id,`<label>Progress<select name="status"><option value="open" ${task.status==='open'?'selected':''}>Open</option><option value="in_progress" ${task.status==='in_progress'?'selected':''}>In progress</option><option value="completed" ${task.status==='completed'?'selected':''}>Completed</option></select></label>${management?`<div class="control-form-grid"><label>Assigned person<select name="assigned_to_id"><option value="">Unassigned</option>${users.map(row=>`<option value="${row.id}" ${row.id===task.assigned_to_id?'selected':''}>${escape(row.name)}</option>`).join('')}</select></label><label>Snooze until<input name="snoozed_until" type="date" value="${escape(task.snoozed_until||'')}"></label></div>`:''}<label>Add a permanent comment<textarea name="comment"></textarea></label>`,'Update follow-up','PATCH')}</div></details>`).join('');
  }
  function filterReconciliation(root) {
    const form=root.querySelector('[data-control-form="/api/finance/reconciliations"]'); if(!form)return;
    const account=form.querySelector('[data-reconcile-account]');
    const filter=()=>form.querySelectorAll('[name="ledger_ids"]').forEach(input=>{const visible=input.dataset.ledgerAccount===account.value;input.closest('label').hidden=!visible;input.disabled=!visible;if(!visible)input.checked=false;});
    account.addEventListener('change',filter);filter();
  }
  function bindForms(root) {
    root.querySelectorAll('[data-control-form]').forEach(form=>{
      if(form.dataset.bound)return;form.dataset.bound='1';
      form.addEventListener('submit',async event=>{
        event.preventDefault();const button=form.querySelector('[type="submit"]'),message=form.querySelector('.control-form-message');
        button.disabled=true;message.textContent='Saving…';
        try{
          const data=new FormData(form);let response;
          if(form.hasAttribute('data-file-form'))response=await api(form.dataset.controlForm,{method:'POST',body:data});
          else {const payload=Object.fromEntries(data);if(form.querySelector('[name="ledger_ids"]'))payload.ledger_ids=data.getAll('ledger_ids');response=await jsonPost(form.dataset.controlForm,payload,form.dataset.method||'POST');}
          message.textContent=response.message||'Saved.';
          if(drawerSource&&drawer.contains(form))await openRecord(drawerSource.kind,drawerSource.id,false);
          else if(activeWorkspace?.root.isConnected)await activeWorkspace.load();
          else if(root.matches('[data-staff-followups]'))await loadStaffTasks(root);
        }catch(error){message.textContent=error.message;message.classList.add('error');}
        finally{button.disabled=false;}
      });
    });
    root.querySelectorAll('[data-record-picker]:not([data-picker-bound])').forEach(form=>{
      form.dataset.pickerBound='1';const type=form.querySelector('[name="target_type"]'),search=form.querySelector('[data-record-search]'),select=form.querySelector('[name="target_id"]');let timer,sequence=0;
      const load=async()=>{const id=++sequence;select.innerHTML='<option value="">Loading records…</option>';try{const data=await api('/api/management/record-options?kind='+encodeURIComponent(type.value)+'&q='+encodeURIComponent(search.value));if(id!==sequence||!form.isConnected)return;select.innerHTML='<option value="">Choose a saved record</option>'+data.records.map(row=>`<option value="${escape(row.id)}">${escape((row.reference?row.reference+' · ':'')+row.title)}</option>`).join('');}catch(error){select.innerHTML='<option value="">'+escape(error.message)+'</option>';}};
      type.addEventListener('change',load);search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,250);});load();
    });
  }

  async function openRecord(kind,id,rememberOpener=true) {
    if(!drawer)return;
    if(rememberOpener&&!drawer.contains(document.activeElement))opener=document.activeElement;
    drawerSource={kind,id};drawer.hidden=false;backdrop.hidden=false;document.body.classList.add('control-record-open');
    const content=drawer.querySelector('[data-control-record-content]');content.innerHTML=empty('Loading the connected record…');
    try {
      const result=await api(`/api/management/records/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`);
      if(drawerSource?.kind!==kind||drawerSource?.id!==id)return;
      drawerData=result.data;renderRecord();drawer.querySelector('[data-close-control-record]').focus();
    }catch(error){content.innerHTML=empty(error.message);}
  }
  function renderRecord() {
    const data=drawerData,record=data.record;document.getElementById('controlRecordTitle').textContent=record.reference||record.title;
    const content=drawer.querySelector('[data-control-record-content]');
    if(document.querySelector('[data-dashboard].dashboard-amounts-hidden')) { content.innerHTML='<div class="dashboard-empty"><strong>Screen privacy is on.</strong><p>Close this drawer and show amounts to review the financial details.</p></div>';return; }
    let html=heading(record.title,'Connected people, documents and the saved transaction history.')+
      `<div class="control-record-meta"><span>Status <b>${escape(record.status||'Recorded')}</b></span><span>Recorded by <b>${escape(record.actor||'Not recorded')}</b></span><span>Department <b>${escape(record.department||'Business-wide')}</b></span><span>Amount <b>${money(record.amount)}</b></span>${record.custodian?`<span>Custodian <b>${escape(record.custodian)}</b></span>`:''}${record.location?`<span>Location <b>${escape(record.location)}</b></span>`:''}</div>`;
    if(data.stages.length)html+=`<div class="control-stage-list">${data.stages.map(stage=>`<div class="${stage.done?'done':''}"><span>${stage.done?'✓':'○'}</span><strong>${escape(stage.label)}</strong><small>${escape(stage.actor||'Person not recorded')}</small><time>${stage.date?date(stage.date):'Pending'}</time></div>`).join('')}</div>`;
    html+=heading('Supporting documents','Stored evidence remains attached to the saved record.')+
      (data.evidence.length?data.evidence.map(item=>`<a class="control-evidence" href="${escape(item.url)}" target="_blank" rel="noopener"><svg aria-hidden="true"><use href="#i-document"/></svg><span><b>${escape(item.name)}</b><small>${escape(item.kind)} · uploaded by ${escape(item.uploaded_by||'Former user')}</small></span></a>`).join(''):empty('No supporting documents recorded.'))+
      heading('Connected records','Open a related item, payment, request or posting without leaving the dashboard.')+
      table(['Record','Type','Amount','Responsible person'],data.records.map(row=>[recordButton(row.type,row.id,row.reference||row.title),escape(row.type.replaceAll('_',' ')),row.amount!==null?money(row.amount):'—',escape(row.actor||row.custodian||'Not recorded')]))+
      heading('Complete saved history',`${data.history_total} recorded events and revisions.`)+
      `<div class="control-history">${renderHistory(data.history)}</div>`+(data.next_history_offset!==null?'<button type="button" class="btn secondary compact" data-control-more-history>Load older history</button>':'')+
      `<div class="control-history-exports">${['csv','xlsx','pdf'].map(format=>`<a class="btn tiny secondary" href="/api/management/records/${record.type}/${record.id}/export.${format}">History ${format==='xlsx'?'Excel':format.toUpperCase()}</a>`).join('')}</div>`;
    if(!record.archived&&['financial_record','finance_ledger','department_operation','request','receivable','payable','asset','inventory_item'].includes(record.type))html+=`<details class="control-disclosure"><summary><strong>Attach supporting evidence</strong></summary><div><form class="control-form" data-control-form="/api/management/records/${record.type}/${record.id}/evidence" data-file-form><label>Receipt / document<input name="evidence" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" required></label><p class="control-form-message" role="status"></p><button type="submit" class="btn primary compact">Attach document</button></form></div></details>`;
    if(!record.archived&&['owner','admin','finance'].includes(document.body.dataset.userRole)) {
      if(['financial_record','finance_ledger'].includes(record.type))html+=`<details class="control-disclosure"><summary><strong>Review expense evidence</strong></summary><div>${noteForm(`/api/management/records/${record.type}/${record.id}/verify`,'<label>What did you verify?<textarea name="notes" required></textarea></label>','Record evidence review')}</div></details>`;
      html+=`<details class="control-disclosure"><summary><strong>Connect another supporting record</strong></summary><div><p>Choose the actual supporting record. Each connection retains the responsible person and audit history.</p>${noteForm(`/api/management/records/${record.type}/${record.id}/links`,'<label>Record type<select name="target_type"><option value="request">Purchase request</option><option value="finance_ledger">Payment / ledger</option><option value="financial_record">Financial record</option><option value="inventory_item">Inventory item</option><option value="asset">Asset</option><option value="receivable">Receivable</option><option value="payable">Payable</option><option value="department_operation">Staff operation</option></select></label><label>Find a supporting record<input type="search" data-record-search placeholder="Name, description or reference"></label><label>Saved record<select name="target_id" required><option value="">Choose a saved record</option></select></label><label>Relationship<input name="relation" value="related" required></label>','Connect records')}</div></details>`;
    }
    if(!record.archived&&['request','stock_movement','asset'].includes(record.type))html+=`<details class="control-disclosure"><summary><strong>Acknowledge your own receipt or usage</strong></summary><div>${noteForm(`/api/management/records/${record.type}/${record.id}/acknowledge`,'<label>Action<select name="action"><option value="received">I received it</option><option value="used">I used it</option><option value="returned">I returned it</option></select></label><label>What did you receive/use/return?<textarea name="notes" required></textarea></label>','Save my acknowledgment')}</div></details>`;
    if(!record.archived&&['receivable','payable'].includes(record.type)&&['owner','admin','finance'].includes(document.body.dataset.userRole))html+=`<details class="control-disclosure"><summary><strong>Record the actual invoice issue date</strong></summary><div>${noteForm(`/api/management/obligations/${record.type}/${record.id}/terms`,'<label>Actual invoice date<input name="invoice_date" type="date" required></label>','Save invoice date','PATCH')}</div></details>`;
    if(data.purchase_lines?.length)html+=heading('Actual purchased items','Saved quantities and unit prices, without an owner-to-self request.')+table(['Item','Quantity','Unit cost'],data.purchase_lines.map(line=>[escape(line.item),escape(line.quantity+' '+line.unit),money(line.unit_cost)]));
    content.innerHTML=html;content.querySelectorAll('[data-control-form$="/links"]').forEach(form=>form.setAttribute("data-record-picker",""));bindForms(drawer);
    content.querySelector('[data-control-more-history]')?.addEventListener('click',async event=>{
      const button=event.currentTarget;button.disabled=true;
      try {const result=await api(`/api/management/records/${record.type}/${record.id}?offset=${data.next_history_offset}`);content.querySelector('.control-history').insertAdjacentHTML('beforeend',renderHistory(result.data.history));data.next_history_offset=result.data.next_history_offset;button.hidden=data.next_history_offset===null;}catch(error){button.textContent=error.message;}finally{button.disabled=false;}
    });
  }
  function renderHistory(rows) {return rows.map(row=>`<article><span class="control-history-dot"></span><div><strong>${escape(row.title)}</strong><small>${escape(row.actor)} · ${date(row.date)}</small>${row.description?`<p>${escape(row.description)}</p>`:''}${row.before||row.after?`<details><summary>What changed</summary><div class="control-audit-snapshots"><pre>${escape(JSON.stringify(row.before||{},null,2))}</pre><pre>${escape(JSON.stringify(row.after||{},null,2))}</pre></div></details>`:''}</div></article>`).join('')||'<p>No prior events saved for this record.</p>';}
  function closeRecord() {drawer.hidden=true;backdrop.hidden=true;document.body.classList.remove('control-record-open');drawerSource=null;drawerData=null;opener?.isConnected&&opener.focus();}

  async function loadStaffTasks(root) {
    try{const data=await api('/api/management/staff-finance');if(!root.isConnected)return;root.querySelector('[data-staff-task-list]').innerHTML=renderTasks(data.tasks);const custody=root.querySelector('[data-staff-custody-list]');if(custody)custody.innerHTML=heading('My assigned assets and stock issues','Open a record to acknowledge your own receipt, use or return.')+(data.custody.length?data.custody.map(row=>'<div class="control-list-row">'+recordButton(row.type,row.id,row.title)+'</div>').join(''):empty('No recorded custody assignments.'));bindForms(root);}catch(error){root.querySelector('[data-staff-task-list]').innerHTML=empty(error.message);}
  }
  function init({refresh}={}) {
    refreshPage=refresh;
    if(document.body.dataset.page==='dashboard'&&changeToken===undefined)api('/api/management/change-token').then(data=>{if(changeToken===undefined)changeToken=data.token;}).catch(()=>{});
    const root=document.querySelector('[data-owner-control]');
    if(root&&!root.dataset.bound) {
      root.dataset.bound='1';const key='sage-control-v1:'+root.dataset.controlKey;let saved={};
      try{saved=JSON.parse(localStorage.getItem(key)||'{}');}catch{}
      let section=saved.section||'actions',snapshot=null,sequence=0;
      const selector=root.querySelector('[data-control-section]'),period=root.querySelector('[data-control-period]');
      if([...selector.options].some(option=>option.value===section))selector.value=section;else section='actions';
      if([...period.options].some(option=>option.value===saved.period))period.value=saved.period;
      const persist=()=>{try{localStorage.setItem(key,JSON.stringify({section,period:period.value,open:root.open}));}catch{}};
      const select=value=>{section=value;selector.value=value;root.querySelectorAll('[data-control-tab]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.controlTab===value)));if(snapshot)render(snapshot,section,root);persist();};
      const load=async()=>{
        const id=++sequence;root.setAttribute('aria-busy','true');const status=root.querySelector('[data-control-updated]');status.textContent='Loading saved records…';
        try{const data=await api('/api/management/workspace?period='+encodeURIComponent(period.value));if(id!==sequence||!root.isConnected)return;snapshot=data.data;render(snapshot,section,root);status.textContent='Updated '+new Date(snapshot.generated_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});}
        catch(error){if(root.isConnected&&id===sequence){status.textContent='Could not load records';root.querySelector('[data-control-content]').innerHTML=empty(error.message);}}
        finally{if(id===sequence)root.removeAttribute('aria-busy');}
      };
      activeWorkspace={root,load};
      root.querySelectorAll('[data-control-tab]').forEach(button=>button.addEventListener('click',()=>select(button.dataset.controlTab)));
      selector.addEventListener('change',()=>select(selector.value));period.addEventListener('change',()=>{persist();load();});
      root.querySelector('[data-control-reload]').addEventListener('click',load);
      root.addEventListener('toggle',()=>{persist();if(root.open&&!snapshot)load();});
      select(section);if(saved.open)root.open=true;if(root.open)load();
    }
    document.querySelectorAll('[data-staff-followups]:not([data-bound])').forEach(element=>{element.dataset.bound='1';loadStaffTasks(element);});
    document.querySelectorAll('[data-direct-purchase-mode]:not([data-bound])').forEach(select=>{
      select.dataset.bound='1';const form=select.closest('form'),fields=form.querySelector('[data-direct-purchase-fields]');
      const sync=()=>{const physical=select.value!=='finance';fields.hidden=!physical;form.querySelectorAll('[data-direct-item]').forEach(input=>input.required=physical);};select.addEventListener('change',sync);sync();
    });
  }
  document.addEventListener('click',event=>{
    const jump=event.target.closest('[data-control-jump]');if(jump){event.preventDefault();const root=document.querySelector('[data-owner-control]');if(root){root.open=true;const select=root.querySelector('[data-control-section]');select.value=jump.dataset.controlJump;select.dispatchEvent(new Event('change'));root.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});}return;}
    const button=event.target.closest('[data-open-record]');
    if(button){event.preventDefault();event.stopPropagation();const [kind,id]=button.dataset.openRecord.split(':');openRecord(kind,id);}
    if(event.target.closest('[data-close-control-record]'))closeRecord();
  });
  backdrop?.addEventListener('click',closeRecord);
  document.addEventListener('keydown',event=>{
    if(!drawer||drawer.hidden)return;
    if(event.key==='Escape'){event.preventDefault();closeRecord();return;}
    if(event.key==='Tab'){const targets=[...drawer.querySelectorAll('button,a,input,select,textarea,summary')].filter(node=>!node.disabled&&node.getClientRects().length);const first=targets[0],last=targets.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
  });
  setInterval(async()=>{
    if(document.hidden||document.body.dataset.page!=='dashboard'||checkingChanges||!drawer?.hidden)return;
    checkingChanges=true;
    try{const data=await api('/api/management/change-token');if(changeToken===undefined)changeToken=data.token;else if(changeToken!==data.token&&!document.activeElement?.matches('input,select,textarea')&&!document.querySelector('.modal-backdrop.open')){await refreshPage?.();changeToken=data.token;}}catch{}finally{checkingChanges=false;}
  },10000);
  window.SAGEControl={init,openRecord};
})();
