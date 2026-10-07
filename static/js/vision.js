(() => {
  const root = document.documentElement;
  const body = document.body;
  const appContent = document.getElementById('appContent');
  const progress = document.getElementById('pageProgress');
  const sidebar = document.getElementById('sidebar');
  const mobileBackdrop = document.getElementById('mobileBackdrop');
  const commandPalette = document.getElementById('commandPalette');
  const commandInput = document.getElementById('commandInput');
  const requestModal = document.getElementById('requestModal');
  const toastStack = document.getElementById('toastStack');
  const notificationTray = document.getElementById('notificationTray');
  const notificationList = document.getElementById('notificationList');
  const notificationDot = document.getElementById('notificationDot');
  const notificationCount = document.getElementById('notificationCount');
  const aiDrawer = document.getElementById('aiDrawer');
  const aiBackdrop = document.getElementById('aiBackdrop');
  const aiForm = document.getElementById('aiForm');
  const aiInput = document.getElementById('aiInput');
  const aiMessages = document.getElementById('aiMessages');
  const aiHistory = [];

  const pageMeta = {
    dashboard: 'Dashboard', workspace: 'Department Workspace', catalog: 'Department Catalogue', analytics: 'Analytics', finance: 'Finance', requests: 'Requests & Approvals', fulfillment: 'Acquisition Hub',
    procurement: 'Procurement', inventory: 'Inventory', assets: 'Assets', departments: 'Departments',
    staff: 'Staff', reports: 'Reports', audit: 'Audit Trail', settings: 'Settings'
  };

  const colors = {
    blue: '#2457ff', green: '#00c78a', orange: '#ffa400', violet: '#a63cff', pink: '#ff3a67'
  };
  const accentOptions = [
    {blue:'#2457ff', softDark:'#0d1b46', softLight:'#eef2ff'},
    {blue:'#6d5dfc', softDark:'#1c1746', softLight:'#f0edff'},
    {blue:'#0ea5a8', softDark:'#062f31', softLight:'#e8fbfb'}
  ];

  const themeNames = {dark:'Dark', light:'Light', sky:'Sky Blue', sage:'Sage Green', sand:'Warm Sand', slate:'Slate'};
  const themeColors = {dark:'#050505', light:'#f6f7f9', sky:'#edf7ff', sage:'#f0f5f1', sand:'#f7f3eb', slate:'#111720'};
  function theme() { return root.dataset.theme || 'dark'; }
  function cssVar(name) { return getComputedStyle(root).getPropertyValue(name).trim(); }
  function setTheme(next) {
    next = themeNames[next] ? next : 'dark'; root.dataset.theme = next; localStorage.setItem('sage-theme', next); localStorage.setItem('vision-theme', next);
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', themeColors[next] || '#050505');
    const label = document.getElementById('themeLabel'); if (label) label.textContent = themeNames[next];
    document.querySelectorAll('[data-theme-choice]').forEach(button => button.classList.toggle('active', button.dataset.themeChoice === next)); requestAnimationFrame(initCharts);
  }
  setTheme(localStorage.getItem('sage-theme') || localStorage.getItem('vision-theme') || 'dark');

  const themeToggle = document.getElementById('themeToggle'), themeMenu = document.getElementById('themeMenu');
  function closeThemeMenu() { themeMenu?.classList.remove('open'); themeMenu?.setAttribute('aria-hidden','true'); themeToggle?.setAttribute('aria-expanded','false'); }
  themeToggle?.addEventListener('click', event => { event.stopPropagation(); const open = !themeMenu?.classList.contains('open'); closeThemeMenu(); if (open) { themeMenu?.classList.add('open'); themeMenu?.setAttribute('aria-hidden','false'); themeToggle.setAttribute('aria-expanded','true'); } });
  themeMenu?.addEventListener('click', event => { const button = event.target.closest('[data-theme-choice]'); if (!button) return; setTheme(button.dataset.themeChoice); applyAccent(); closeThemeMenu(); showToast('Theme updated', `${themeNames[theme()]} is now active.`); });
  document.addEventListener('click', event => { if (!event.target.closest('.theme-switcher')) closeThemeMenu(); });

  const storedAccent = localStorage.getItem('vision-accent'); let accentIndex = storedAccent === null ? -1 : Number(storedAccent);
  function applyAccent() {
    if (accentIndex < 0) { root.style.removeProperty('--blue'); root.style.removeProperty('--blue-soft'); return; }
    const a = accentOptions[accentIndex % accentOptions.length], darkTheme = ['dark','slate'].includes(theme()); root.style.setProperty('--blue', a.blue); root.style.setProperty('--blue-soft', darkTheme ? a.softDark : a.softLight);
  }
  applyAccent();
  document.getElementById('accentToggle')?.addEventListener('click', () => {
    accentIndex = (accentIndex + 1) % accentOptions.length;
    localStorage.setItem('vision-accent', accentIndex);
    applyAccent();
    showToast('Accent updated', 'SAGE will remember this color preference.');
    initCharts();
  });

  // Sidebar state
  const savedCollapse = localStorage.getItem('vision-sidebar-collapsed') === 'true';
  if (savedCollapse && innerWidth > 820) body.classList.add('sidebar-collapsed');
  document.getElementById('sidebarCollapse')?.addEventListener('click', () => {
    body.classList.toggle('sidebar-collapsed');
    localStorage.setItem('vision-sidebar-collapsed', body.classList.contains('sidebar-collapsed'));
    setTimeout(initCharts, 220);
  });
  function setMobileNav(open) { body.classList.toggle('mobile-nav-open', open); }
  document.getElementById('mobileMenu')?.addEventListener('click', () => setMobileNav(true));
  document.getElementById('mobileClose')?.addEventListener('click', () => setMobileNav(false));
  mobileBackdrop?.addEventListener('click', () => setMobileNav(false));

  // SPA-style Flask partial navigation
  async function navigate(page, push = true) {
    if (!page || !pageMeta[page]) return;
    if (body.dataset.page === page && push) { setMobileNav(false); return; }
    setMobileNav(false);
    progress?.classList.remove('done'); progress?.classList.add('loading');
    try {
      const res = await fetch(`/partial/${page}`, { headers: { 'X-Sage-Partial': '1' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const html = await res.text();
      const swap = () => {
        appContent.innerHTML = html;
        body.dataset.page = page;
        document.title = `${pageMeta[page]} · SAGE`;
        updateActiveNav(page);
        if (push) history.pushState({page}, '', `/${page}`);
        appContent.focus({preventScroll:true});
        window.scrollTo({top:0, behavior:'auto'});
        initDynamicUI(); trackPageView(page);
      };
      if (document.startViewTransition) document.startViewTransition(swap); else swap();
      progress?.classList.remove('loading'); progress?.classList.add('done');
      setTimeout(() => progress?.classList.remove('done'), 250);
    } catch (err) {
      console.error(err);
      location.href = `/${page}`;
    }
  }

  function updateActiveNav(page) {
    document.querySelectorAll('.nav-link').forEach(link => link.classList.toggle('active', link.dataset.route === page));
  }

  document.addEventListener('click', (e) => {
    const routeLink = e.target.closest('[data-route]');
    if (routeLink && !e.metaKey && !e.ctrlKey && !e.shiftKey && routeLink.dataset.route) {
      e.preventDefault(); navigate(routeLink.dataset.route);
      return;
    }
    const cmd = e.target.closest('[data-command-route]');
    if (cmd) { closeCommand(); navigate(cmd.dataset.commandRoute); return; }
    if (e.target.closest('[data-open-request]')) openModal('requestModal');
    if (e.target.closest('[data-open-department]')) openModal('departmentModal');
    if (e.target.closest('[data-open-staff-invite]')) openModal('staffInviteModal');
    if (e.target.closest('[data-open-inventory]')) openModal('inventoryModal');
    if (e.target.closest('[data-open-asset]')) openModal('assetModal');
    if (e.target.closest('[data-open-catalog-item]')) openModal('catalogItemModal');
    const catalogRequest=e.target.closest('[data-catalog-request]'); if(catalogRequest){ const form=document.getElementById('requestForm'); if(form){ form.elements.item_name.value=catalogRequest.dataset.itemName||''; form.elements.category.value=catalogRequest.dataset.itemCategory||''; form.elements.unit.value=catalogRequest.dataset.itemUnit||'unit'; } openModal('requestModal'); }
    if (e.target.closest('[data-open-finance]')) openModal('financeLedgerModal');
    const financeModalButton=e.target.closest('[data-finance-modal]'); if(financeModalButton) openModal(financeModalButton.dataset.financeModal);
    const closer = e.target.closest('[data-close-modal]');
    if (closer) closeModal(closer.dataset.closeModal);
    if (e.target.closest('[data-save-settings]')) showToast('Settings saved', 'Prototype settings updated for this session.');
  });
  window.addEventListener('popstate', () => {
    const page = location.pathname.replace(/^\//,'') || 'dashboard';
    if (pageMeta[page]) navigate(page, false);
  });

  // Command palette
  function openCommand() {
    commandPalette?.classList.add('open'); commandPalette?.setAttribute('aria-hidden','false');
    setTimeout(() => { commandInput?.focus(); commandInput?.select(); }, 50);
  }
  function closeCommand() { commandPalette?.classList.remove('open'); commandPalette?.setAttribute('aria-hidden','true'); }
  document.getElementById('commandOpen')?.addEventListener('click', openCommand);
  commandPalette?.addEventListener('click', e => { if (e.target === commandPalette) closeCommand(); });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openCommand(); }
    if (e.key === 'Escape') { closeCommand(); ['requestModal','departmentModal','staffInviteModal','staffEditModal','staffActivityModal','staffDeleteModal','requestFundingModal','purchaseRecordModal','inventoryModal','stockMoveModal','assetModal','assetMoveModal','financeModal','financeAccountModal','financeLedgerModal','financeBudgetModal','financeReceivableModal','financePayableModal','financeReconcileModal','financePayrollModal','financeTaxModal','financeForecastModal','catalogItemModal'].forEach(closeModal); closeAI(); notificationTray?.classList.remove('open'); closeAI(); setMobileNav(false); }
  });
  commandInput?.addEventListener('input', () => {
    const q = commandInput.value.toLowerCase().trim();
    document.querySelectorAll('.command-item').forEach(item => item.classList.toggle('hidden', q && !item.dataset.commandText.includes(q)));
  });
  commandInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const first = document.querySelector('.command-item:not(.hidden)');
      if (first) { closeCommand(); navigate(first.dataset.commandRoute); }
    }
  });

  // Modals / quick add
  function openModal(id) {
    const el = document.getElementById(id); if (!el) return;
    el.classList.add('open'); el.setAttribute('aria-hidden','false');
    setTimeout(() => el.querySelector('input,select,textarea')?.focus(), 60);
  }
  function closeModal(id) { const el = document.getElementById(id); if (el) { el.classList.remove('open'); el.setAttribute('aria-hidden','true'); } }
  document.getElementById('newRequestOpen')?.addEventListener('click', () => openModal('requestModal'));
  document.getElementById('floatingQuick')?.addEventListener('click', () => openModal('requestModal'));
  requestModal?.addEventListener('click', e => { if (e.target === requestModal) closeModal('requestModal'); });
  const requestForm = document.getElementById('requestForm');
  async function submitRequest(saveAsDraft = false) {
    if (!requestForm) return; const message = requestForm.querySelector('[data-request-message]');
    const data = Object.fromEntries(new FormData(requestForm).entries()); data.save_as_draft = saveAsDraft; delete data.estimated_total_display;
    if (!data.department_id && (window.SAGE_USER || window.VISION_USER)?.department) delete data.department_id;
    try {
      if (message) { message.textContent = ''; message.className = 'form-message'; }
      const res = await fetch('/api/requests', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}); const result = await res.json();
      if (!res.ok || !result.ok) throw new Error(result.message || 'Could not save request.');
      closeModal('requestModal'); requestForm.reset(); updateRequestTotal(); showToast(saveAsDraft ? 'Draft saved' : 'Request submitted', `${result.request.reference} · ${result.message}`);
      if (['dashboard','requests','procurement','workspace'].includes(body.dataset.page)) navigate(body.dataset.page, false);
    } catch (error) { if (message) { message.textContent = error.message; message.className = 'form-message show error'; } }
  }
  requestForm?.addEventListener('submit', e => { e.preventDefault(); submitRequest(false); });
  requestForm?.querySelector('[data-request-draft]')?.addEventListener('click', () => submitRequest(true));
  function updateRequestTotal() { if (!requestForm) return; const q=Number(requestForm.querySelector('[name="quantity"]')?.value||0), u=Number(requestForm.querySelector('[name="unit_cost"]')?.value||0), out=requestForm.querySelector('[data-request-total]'); if(out) out.value=(q*u).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}); }
  requestForm?.querySelector('[name="quantity"]')?.addEventListener('input', updateRequestTotal); requestForm?.querySelector('[name="unit_cost"]')?.addEventListener('input', updateRequestTotal); updateRequestTotal();

  // SAGE AI drawer
  function openAI() { aiDrawer?.classList.add('open'); aiBackdrop?.classList.add('open'); aiDrawer?.setAttribute('aria-hidden','false'); setTimeout(() => aiInput?.focus(), 180); }
  function closeAI() { aiDrawer?.classList.remove('open'); aiBackdrop?.classList.remove('open'); aiDrawer?.setAttribute('aria-hidden','true'); }
  document.getElementById('aiOpen')?.addEventListener('click', openAI);
  document.getElementById('floatingAI')?.addEventListener('click', openAI);
  document.getElementById('aiClose')?.addEventListener('click', closeAI);
  aiBackdrop?.addEventListener('click', closeAI);
  document.querySelectorAll('[data-ai-prompt]').forEach(button => button.addEventListener('click', () => { openAI(); if (aiInput) aiInput.value = button.dataset.aiPrompt || ''; aiForm?.requestSubmit(); }));

  function escapeHTML(value) { return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])); }
  function appendAIMessage(role, content, meta = '') {
    if (!aiMessages) return;
    const message = document.createElement('div'); message.className = `ai-message ${role}`;
    message.innerHTML = role === 'assistant' ? `<span class="ai-avatar"><svg><use href="#i-sparkles"></use></svg></span><div><p>${escapeHTML(content).replace(/\n/g,'<br>')}</p><small>${escapeHTML(meta || 'SAGE AI')}</small></div>` : `<div><p>${escapeHTML(content)}</p><small>You</small></div>`;
    aiMessages.appendChild(message); aiMessages.scrollTop = aiMessages.scrollHeight;
  }
  aiForm?.addEventListener('submit', async e => {
    e.preventDefault(); const message = aiInput?.value.trim(); if (!message) return;
    appendAIMessage('user', message); aiHistory.push({role:'user', content:message}); aiInput.value = '';
    const button = aiForm.querySelector('button[type="submit"]'); button.disabled = true; appendAIMessage('assistant', 'Thinking...', 'SAGE AI'); const thinking = aiMessages.lastElementChild;
    try {
      const res = await fetch('/api/ai/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message, history:aiHistory.slice(-8,-1)})});
      const data = await res.json(); thinking?.remove(); if (!res.ok || !data.ok) throw new Error(data.message || 'SAGE AI could not answer.');
      appendAIMessage('assistant', data.answer, data.model || 'SAGE AI'); aiHistory.push({role:'assistant', content:data.answer});
    } catch (error) { thinking?.remove(); appendAIMessage('assistant', error.message, 'Configuration'); } finally { button.disabled = false; aiInput?.focus(); }
  });

  function showToast(title, message) {
    if (!toastStack) return;
    const toast = document.createElement('div'); toast.className = 'toast';
    toast.innerHTML = `<span><svg><use href="#i-check"></use></svg></span><div><strong>${title}</strong><small>${message}</small></div>`;
    toastStack.appendChild(toast); setTimeout(() => toast.remove(), 3300);
  }

  // ========================================================
  // SAGE PULSE — REAL-TIME NOTIFICATIONS + SHARED EDGE CARD
  // The bell drawer stores history; this compact card is the visible live layer. Initial history never flashes, but every later DB/SSE event does.
  // ========================================================
  async function trackPageView(page) { try { await fetch('/api/activity/page-view', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({page})}); } catch (_) {} }
  const knownNotificationIds=new Set(); let notificationPollTimer=null,liveNotificationTimer=null,liveNotificationQueue=[],briefingRunning=false,notificationBootstrapped=false,periodicPulseTimer=null,periodicPulseIndex=0,periodicPulseRetry=null;
  const liveCard=document.getElementById('sageLiveNotification'),liveIcon=document.getElementById('sageLiveIcon'),liveTitle=document.getElementById('sageLiveTitle'),liveMessage=document.getElementById('sageLiveMessage'),liveTime=document.getElementById('sageLiveTime'),liveType=document.getElementById('sageLiveType'),liveMetric=document.getElementById('sageLiveMetric'),liveBriefMeta=document.getElementById('sageLiveBriefMeta'),liveScope=document.getElementById('sageLiveScope'),livePosition=document.getElementById('sageLivePosition'),liveActions=document.getElementById('sageLiveActions'),liveOpen=document.getElementById('sageLiveOpen'),liveProgress=document.getElementById('sageLiveProgress');
  function notificationHTML(note){return `<article class="notification-item ${escapeHTML(note.level||'info')} ${note.read?'':'unread'}" data-notification-id="${escapeHTML(note.id||'')}"><span class="notification-item-icon"><svg><use href="#i-bell"></use></svg></span><div><strong>${escapeHTML(note.title)}</strong><p>${escapeHTML(note.message)}</p><small>${note.created_at?new Date(note.created_at).toLocaleString():'Just now'}</small></div></article>`;}
  function liveLevelFromTone(tone){return ({green:'success',orange:'warning',red:'danger',violet:'violet',blue:'info'})[tone]||'info';}
  function liveIconName(name){return ['wallet','requests','inventory','briefcase','finance','bell','sparkles'].includes(name)?name:'bell';}
  function resetLiveProgress(duration=6200){if(!liveProgress)return;liveProgress.style.animation='none';liveProgress.style.setProperty('--sage-pulse-duration',`${duration}ms`);void liveProgress.offsetWidth;liveProgress.style.animation='sagePulseProgress var(--sage-pulse-duration) linear forwards';}
  function updatePulseCard(payload,{mode='live',animate=true}={}){if(!liveCard)return false;const apply=()=>{liveCard.dataset.mode=mode;liveCard.dataset.level=payload.level||'info';liveType.textContent=payload.type||'LIVE ACTIVITY';liveTime.textContent=payload.time||'Now';liveTitle.textContent=payload.title||'SAGE update';liveMessage.textContent=payload.message||'';liveIcon.innerHTML=`<svg><use href="#i-${liveIconName(payload.icon)}"></use></svg>`;if(liveMetric){liveMetric.hidden=!payload.metric;liveMetric.textContent=payload.metric||'';}if(liveBriefMeta)liveBriefMeta.hidden=mode!=='briefing';if(liveScope)liveScope.textContent=payload.scope||'';if(livePosition)livePosition.textContent=payload.position||'';if(liveActions)liveActions.hidden=mode!=='briefing';if(liveOpen){liveOpen.textContent=payload.actionLabel||'Open section';liveOpen.dataset.route=payload.route||'dashboard';}liveCard.classList.add('show');document.body.classList.add('sage-pulse-visible');resetLiveProgress(payload.duration||6200);};if(!animate){apply();return true;}liveCard.classList.add('is-switching');setTimeout(()=>{apply();liveCard.classList.remove('is-switching');liveCard.classList.add('is-entering');setTimeout(()=>liveCard.classList.remove('is-entering'),340);},150);return true;}
  function hidePulseCard(){clearTimeout(liveNotificationTimer);liveCard?.classList.remove('show','is-switching','is-entering');document.body.classList.remove('sage-pulse-visible');}
  function flushLiveNotificationQueue(){if(briefingRunning||!liveNotificationQueue.length)return;showLiveNotification(liveNotificationQueue.shift());}
  function showLiveNotification(note){if(!liveCard)return;if(briefingRunning){liveNotificationQueue.push(note);return;}clearTimeout(liveNotificationTimer);updatePulseCard({level:note.level||'info',type:(note.entity_type||'LIVE ACTIVITY').replaceAll('_',' ').toUpperCase(),title:note.title||'Live activity',message:note.message||'',metric:note.metric||'',time:note.created_at?new Date(note.created_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'Now',icon:note.icon||'bell',duration:note.duration||6800},{mode:'live'});liveNotificationTimer=setTimeout(()=>{hidePulseCard();setTimeout(flushLiveNotificationQueue,260);},note.duration||6800);}
  document.getElementById('sageLiveClose')?.addEventListener('click',()=>{if(briefingRunning)closeBriefing();else{hidePulseCard();setTimeout(flushLiveNotificationQueue,250);}});
  function handleNewNotification(note,notify=true){if(!note?.id||knownNotificationIds.has(note.id))return false;knownNotificationIds.add(note.id);if(notificationList){notificationList.querySelector('.empty-notifications')?.remove();notificationList.insertAdjacentHTML('afterbegin',notificationHTML({...note,read:false}));}if(notify)showLiveNotification(note);return true;}
  async function refreshNotifications(markRead=false,notifyNew=false){try{if(markRead)await fetch('/api/notifications/read',{method:'POST'});const res=await fetch('/api/notifications',{cache:'no-store'}),data=await res.json();if(!res.ok||!data.ok)return null;const incoming=[...data.notifications].reverse();incoming.forEach(note=>{if(notifyNew&&notificationBootstrapped)handleNewNotification(note,true);else knownNotificationIds.add(note.id);});if(notificationList)notificationList.innerHTML=data.notifications.length?data.notifications.map(notificationHTML).join(''):'<div class="empty-notifications">No notifications yet.</div>';if(notificationCount){notificationCount.textContent=data.unread;notificationCount.hidden=!data.unread;}if(notificationDot)notificationDot.hidden=!data.unread;return data;}catch(error){console.debug('SAGE notification refresh skipped',error);return null;}}
  function liveRefreshPage(){const page=body.dataset.page;if(['dashboard','audit','requests','fulfillment','inventory','assets','staff','finance'].includes(page)&&!document.querySelector('.modal-backdrop.open'))setTimeout(()=>navigate(page,false),220);}
  function startNotificationFallback(){if(notificationPollTimer)return;notificationPollTimer=setInterval(()=>refreshNotifications(false,true),2800);}
  function startNotificationStream(){if(!window.EventSource)return;const stream=new EventSource('/api/notifications/stream');stream.addEventListener('notification',event=>{try{const note=JSON.parse(event.data);if(handleNewNotification(note,true)){refreshNotifications(false,false);liveRefreshPage();}}catch(error){console.debug('SAGE live event parse failed',error);}});stream.addEventListener('ready',()=>document.body.classList.add('live-stream-connected'));stream.onerror=()=>document.body.classList.remove('live-stream-connected');}
  async function bootstrapNotifications(){await refreshNotifications(false,false);notificationBootstrapped=true;startNotificationFallback();startNotificationStream();}
  document.getElementById('notificationToggle')?.addEventListener('click',()=>{notificationTray?.classList.toggle('open');notificationTray?.setAttribute('aria-hidden',notificationTray?.classList.contains('open')?'false':'true');refreshNotifications(false,false);});
  document.getElementById('markNotificationsRead')?.addEventListener('click',()=>refreshNotifications(true,false));
  bootstrapNotifications();

  // ========================================================
  // SAGE GUIDE — CONTEXTUAL EXPLANATIONS / ACCESSIBLE HELP
  // Desktop: hover or keyboard focus shows a large contextual pointer. Mobile: the Guide drawer explains the current page without relying on hover.
  // ========================================================
  const PAGE_HELP = {
    dashboard:{title:'Dashboard',copy:'Your live business pulse: money, approvals, stock, assets and recent accountable activity in one place.',tips:['Start here for the current position','Use cards to spot exceptions quickly','Open Today’s Brief when you want a fast recap']},
    workspace:{title:'Department Workspace',copy:'Role-specific tools, responsibilities and KPIs for the signed-in staff member and department.',tips:['Use job tools for your daily work','Review department KPIs','Open the catalogue for role-relevant items']},
    catalog:{title:'Department Catalogue',copy:'Suggested equipment, stock, materials and consumables for this department, plus your organization’s custom items.',tips:['Search by item or category','Create requests from catalogue items','Add custom items when something is missing']},
    analytics:{title:'Analytics',copy:'Trends and comparisons from real SAGE transactions, requests and department activity.',tips:['Compare income and expenses','Review spend categories','Check department performance']},
    finance:{title:'Finance',copy:'Income, expenses, cash, budgets, receivables, payables, payroll, tax and financial control records.',tips:['Post only real transactions','Attach evidence where required','Use reconciliation and reports for control']},
    requests:{title:'Requests & Approvals',copy:'Tracks staff needs from request through approval, funding, acquisition evidence and final accountability.',tips:['Owners review by department/requester','Staff track approval status','Approved requests continue in Acquisition Hub']},
    operations:{title:'Department Operations',copy:'Record job-specific work, usage, incidents, movements and other accountable departmental activity.',tips:['Choose the operation that matches the work','Record quantity/value when relevant','Submitted activity is visible to management']},
    fulfillment:{title:'Acquisition Hub',copy:'Stage 2 of procurement: convert approved or funded requests into actual purchases, receipts, item images, stock or assets.',tips:['Use Save Draft until details are certain','Receipt is required for final submission','Actual quantity/cost updates stock and expense records']},
    procurement:{title:'Procurement',copy:'Management view of sourcing, commitments, purchase activity and fulfillment connected to requests.',tips:['Follow request-to-purchase status','Review supplier/purchase evidence','Track commitments before final expense']},
    inventory:{title:'Inventory',copy:'Live stock balances, values, reorder alerts, issues, transfers, returns and write-offs.',tips:['Keep quantities current','Use movement history for accountability','Review low-stock alerts before shortages']},
    assets:{title:'Assets',copy:'Equipment register with values, custodians, locations, condition and movement history.',tips:['Register real assets','Assign custodians and locations','Record transfers, maintenance and write-offs']},
    departments:{title:'Departments',copy:'Organization structure used to scope staff, requests, budgets, inventory, assets and reporting.',tips:['Add custom departments when needed','Keep names aligned with real operations','Use departments as accountability/cost centres']},
    staff:{title:'Staff',copy:'Manage people, department assignments, roles, access and individual accountability.',tips:['Invite staff with controlled links','Review activity before changing access','Suspend instead of deleting when access may return']},
    reports:{title:'Reports',copy:'Management-ready financial, operational, inventory, procurement, department and accountability reporting.',tips:['Use exceptions to prioritize review','Export records when needed','Drill down to source transactions']},
    audit:{title:'Live Activity & Audit',copy:'Time-stamped history of meaningful staff and owner actions across your permitted SAGE scope.',tips:['Use this for accountability','Search before investigating an event','Source records remain linked where available']},
    settings:{title:'Settings',copy:'Workspace, security, notification and organization preferences for SAGE.',tips:['Review notification delivery','Keep organization details current','Use production settings carefully']}
  };
  const CONTROL_HELP = [
    [/sage ai/i,'SAGE AI','Ask permission-aware questions about your live SAGE records and business position.'],[/quick record/i,'Quick Record','Record owner-side financial or business information without creating a request to yourself.'],[/quick add/i,'Quick Add','Create the staff-side request or record supported by your current role.'],[/notification/i,'Notifications','Open real-time alerts for approvals, evidence uploads, staff activity and other important changes.'],[/theme|appearance/i,'Appearance','Switch SAGE between Dark, Light, Sky Blue, Sage Green, Warm Sand and Slate themes.'],[/search/i,'Search','Find pages and actions quickly without leaving your current workflow.'],[/approve/i,'Approve','Confirm the request or record at the current approval stage.'],[/reject/i,'Reject','Reject the current request and keep the decision traceable.'],[/money sent|fund/i,'Funding','Record that management approved/released money; SAGE does not transfer money itself.'],[/export/i,'Export','Download the visible management data for review outside SAGE.'],[/add asset/i,'Add Asset','Register equipment or other capital items with custody, value and location information.'],[/add item|add stock/i,'Add Stock','Create or increase a tracked inventory item in the permitted department.'],[/new request/i,'New Request','Submit a staff need for approval before acquisition.']
  ];
  const contextHint=document.getElementById('sageContextHint'),contextTitle=document.getElementById('sageContextTitle'),contextCopy=document.getElementById('sageContextCopy'),guideDrawer=document.getElementById('sageGuideDrawer'),guideBackdrop=document.getElementById('sageGuideBackdrop'),guideToggle=document.getElementById('sageGuideToggle'),mobileGuideLaunch=document.getElementById('sageMobileGuideLaunch'),guideHintsToggle=document.getElementById('sageGuideHintsToggle'),guideMasterToggle=document.getElementById('sageGuideMasterToggle'),guideMasterLabel=document.getElementById('sageGuideMasterLabel'),guidePageSwitch=document.getElementById('sageGuidePageSwitch'),guidePageLabel=document.getElementById('sageGuidePageLabel'); let contextTimer=null;
  function hintsEnabled(){return localStorage.getItem('sage-guide-hints')!=='off';}
  function syncGuideControls(){const on=hintsEnabled();document.body.classList.toggle('sage-guide-off',!on);[guideMasterToggle,guidePageSwitch].forEach(button=>button?.setAttribute('aria-pressed',on?'true':'false'));if(guideMasterLabel)guideMasterLabel.textContent=on?'On':'Off';if(guidePageLabel)guidePageLabel.textContent=on?'On':'Off';if(guideHintsToggle)guideHintsToggle.checked=on;if(!on)hideContextHint();}
  function setGuideEnabled(enabled,notify=true){localStorage.setItem('sage-guide-hints',enabled?'on':'off');syncGuideControls();if(notify)showToast('SAGE Guide',enabled?'Automatic page hints are on.':'Automatic page hints are off. You can still open Guide manually.');}
  function pageHelp(page=body.dataset.page){return PAGE_HELP[page]||{title:pageMeta[page]||'SAGE',copy:'This section is part of your permission-aware SAGE workspace.',tips:['Review the information shown','Use available actions as needed','SAGE records important changes automatically']};}
  function helpForTarget(target){if(!target)return null;const route=target.dataset.route||target.dataset.commandRoute;if(route&&PAGE_HELP[route])return PAGE_HELP[route];const text=(target.getAttribute('aria-label')||target.dataset.label||target.querySelector?.('.panel-head strong,h1,h2,h3')?.textContent||target.textContent||'').replace(/\s+/g,' ').trim();for(const [pattern,title,copy] of CONTROL_HELP)if(pattern.test(text))return{title,copy};if(target.matches('.mini-stat,.finance-kpi,.individual-period-card'))return{title:text.slice(0,70)||'Live metric',copy:'A live SAGE metric calculated from records you are allowed to see. Open the related page for its source details.'};if(target.matches('.panel,.catalogue-item-card,.department-card,.job-tool-card,.operation-action-card,.acquisition-card'))return{title:text.slice(0,72)||pageHelp().title,copy:`A ${pageHelp().title.toLowerCase()} section. ${pageHelp().copy}`};return null;}
  function guideTarget(node){return node?.closest?.('.nav-link,[data-route],.panel,.mini-stat,.finance-kpi,.individual-period-card,.catalogue-item-card,.department-card,.job-tool-card,.operation-action-card,.acquisition-card,button:not(.icon-button),.theme-control,.notification-button,.guide-control')||null;}
  function positionHint(target){if(!contextHint||!target)return;const rect=target.getBoundingClientRect(),width=Math.min(360,innerWidth-24),left=rect.right+12+width<innerWidth?rect.right+12:Math.max(12,rect.left-width-12),top=Math.min(innerHeight-contextHint.offsetHeight-12,Math.max(12,rect.top+rect.height/2-contextHint.offsetHeight/2));contextHint.style.left=`${left}px`;contextHint.style.top=`${top}px`;}
  function showContextHint(target){if(!contextHint||!hintsEnabled()||innerWidth<=820)return;const help=helpForTarget(target);if(!help)return;clearTimeout(contextTimer);contextTitle.textContent=help.title;contextCopy.textContent=help.copy;contextHint.classList.add('show');contextHint.setAttribute('aria-hidden','false');requestAnimationFrame(()=>positionHint(target));}
  function hideContextHint(){clearTimeout(contextTimer);contextTimer=setTimeout(()=>{contextHint?.classList.remove('show');contextHint?.setAttribute('aria-hidden','true');},90);}
  document.addEventListener('pointerover',event=>{const target=guideTarget(event.target);if(target&&!target.contains(event.relatedTarget))showContextHint(target);});document.addEventListener('pointerout',event=>{const target=guideTarget(event.target);if(target&&!target.contains(event.relatedTarget))hideContextHint();});document.addEventListener('focusin',event=>showContextHint(guideTarget(event.target)));document.addEventListener('focusout',hideContextHint);
  function openGuide(){const help=pageHelp(),title=document.getElementById('sageGuidePageTitle'),copy=document.getElementById('sageGuidePageCopy'),primaryTitle=document.getElementById('sageGuidePrimaryTitle'),primaryCopy=document.getElementById('sageGuidePrimaryCopy'),links=document.getElementById('sageGuideLinks');if(title)title.textContent=help.title;if(copy)copy.textContent=help.copy;if(primaryTitle)primaryTitle.textContent=`Using ${help.title}`;if(primaryCopy)primaryCopy.textContent=help.tips.join(' · ');if(links)links.innerHTML=Object.entries(PAGE_HELP).filter(([page])=>document.querySelector(`.nav-link[data-route="${page}"]`)).slice(0,8).map(([page,item])=>`<button type="button" data-guide-route="${page}"><strong>${escapeHTML(item.title)}</strong><small>${escapeHTML(item.copy)}</small></button>`).join('');guideDrawer?.classList.add('open');guideBackdrop?.classList.add('open');guideDrawer?.setAttribute('aria-hidden','false');guideBackdrop?.setAttribute('aria-hidden','false');guideToggle?.setAttribute('aria-expanded','true');}
  function closeGuide(){guideDrawer?.classList.remove('open');guideBackdrop?.classList.remove('open');guideDrawer?.setAttribute('aria-hidden','true');guideBackdrop?.setAttribute('aria-hidden','true');guideToggle?.setAttribute('aria-expanded','false');}
  guideToggle?.addEventListener('click',()=>guideDrawer?.classList.contains('open')?closeGuide():openGuide());mobileGuideLaunch?.addEventListener('click',openGuide);document.getElementById('sageGuideClose')?.addEventListener('click',closeGuide);guideBackdrop?.addEventListener('click',closeGuide);guideHintsToggle?.addEventListener('change',()=>setGuideEnabled(guideHintsToggle.checked));guideMasterToggle?.addEventListener('click',()=>setGuideEnabled(!hintsEnabled()));guidePageSwitch?.addEventListener('click',()=>setGuideEnabled(!hintsEnabled()));syncGuideControls();document.addEventListener('click',event=>{const button=event.target.closest('[data-guide-route]');if(button){closeGuide();navigate(button.dataset.guideRoute);}});document.addEventListener('keydown',event=>{if(event.key==='?'&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName||'')){event.preventDefault();openGuide();}if(event.key==='Escape'&&guideDrawer?.classList.contains('open'))closeGuide();});

  // ========================================================
  // SAGE DAILY BRIEF — COMPACT POWERPOINT-LIKE LOGIN RECAP
  // The card appears once per successful login, stays pinned to the screen edge and transitions through tenant-scoped status slides without blocking work.
  // ========================================================
  let briefingSlides=[],briefingIndex=0,briefingTimer=null,currentBriefingToken='',briefingLaunchAttempted=false;
  function closeBriefing(){clearTimeout(briefingTimer);briefingRunning=false;hidePulseCard();setTimeout(flushLiveNotificationQueue,320);}
  function renderBriefing(index,animate=true){if(!briefingSlides.length||!liveCard)return false;briefingIndex=(index+briefingSlides.length)%briefingSlides.length;const slide=briefingSlides[briefingIndex],duration=5600;briefingRunning=true;updatePulseCard({level:liveLevelFromTone(slide.tone),type:slide.kicker||'YOUR SAGE BRIEF',title:slide.title||'',message:slide.message||'',metric:slide.metric||'',scope:`${window.SAGE_USER?.role||'SAGE'} workspace`,position:`${briefingIndex+1} / ${briefingSlides.length}`,time:'Today',icon:slide.icon||'sparkles',route:slide.route||'dashboard',actionLabel:slide.action_label||'Open section',duration},{mode:'briefing',animate});clearTimeout(briefingTimer);briefingTimer=setTimeout(()=>{if(briefingIndex===briefingSlides.length-1){closeBriefing();return;}renderBriefing(briefingIndex+1,true);},duration);return true;}
  async function acknowledgeBriefing(){if(!currentBriefingToken)return;try{await fetch('/api/daily-briefing/ack',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({briefing_token:currentBriefingToken})});}catch(error){console.debug('SAGE briefing acknowledgement skipped',error);}}
  function fallbackBriefing(){const unread=Number(notificationCount?.textContent||0),role=window.SAGE_USER?.role||'SAGE';return{show:true,briefing_token:'',slides:[{tone:'blue',icon:'bell',kicker:'SAGE LIVE PULSE',title:'Live tracking is active',message:'SAGE is monitoring your permitted finance, requests, stock, assets and accountable activity. New team actions will appear here automatically.',metric:`${unread} unread alert${unread===1?'':'s'} · ${role} workspace`,route:'dashboard',action_label:'Open dashboard'}]};}
  function useBriefingPayload(data){if(!data?.show||!data.slides?.length)return false;briefingSlides=data.slides;briefingIndex=0;currentBriefingToken=data.briefing_token||'';if(renderBriefing(0,false)){document.body.classList.add('sage-pulse-visible');setTimeout(acknowledgeBriefing,180);return true;}return false;}
  async function launchDailyBriefing(force=false){if(!force&&briefingLaunchAttempted)return;briefingLaunchAttempted=!force;try{if(!force&&window.SAGE_BOOT_BRIEFING?.show&&window.SAGE_BOOT_BRIEFING?.slides?.length){const boot=window.SAGE_BOOT_BRIEFING;window.SAGE_BOOT_BRIEFING=null;if(useBriefingPayload(boot))return;}const response=await fetch(`/api/daily-briefing${force?'?force=1':''}`,{cache:'no-store'}),data=await response.json();if(response.ok&&data.ok){if(data.show&&useBriefingPayload(data))return;if(!data.show)return;}console.debug('SAGE daily briefing returned no usable slides',data);}catch(error){console.debug('SAGE daily briefing unavailable',error);}useBriefingPayload(fallbackBriefing());}
  document.getElementById('sageLivePrev')?.addEventListener('click',event=>{event.stopPropagation();if(briefingRunning)renderBriefing(briefingIndex-1,true);});
  document.getElementById('sageLiveNext')?.addEventListener('click',event=>{event.stopPropagation();if(briefingRunning){if(briefingIndex===briefingSlides.length-1)closeBriefing();else renderBriefing(briefingIndex+1,true);}});
  document.getElementById('sageLiveOpen')?.addEventListener('click',event=>{event.stopPropagation();const route=event.currentTarget.dataset.route;closeBriefing();if(route&&pageMeta[route])navigate(route);});
  document.getElementById('sageBriefingReplay')?.addEventListener('click',()=>{closeGuide();closeBriefing();launchDailyBriefing(true);});

  // ========================================================
  // FIVE-MINUTE SAGE PULSE — PERIODIC STATUS RECAP
  // The full briefing still runs once after login. Afterwards one fresh summary card appears every five minutes, while true live staff events continue to flash instantly.
  // ========================================================
  async function showFiveMinutePulse(){clearTimeout(periodicPulseRetry);if(briefingRunning||liveCard?.classList.contains('show')){periodicPulseRetry=setTimeout(showFiveMinutePulse,12000);return;}try{const response=await fetch('/api/daily-briefing?force=1',{cache:'no-store'}),data=await response.json(),slides=data?.slides||[];if(response.ok&&data.ok&&slides.length){const slide=slides[periodicPulseIndex%slides.length];periodicPulseIndex=(periodicPulseIndex+1)%slides.length;showLiveNotification({level:liveLevelFromTone(slide.tone),entity_type:'5_MINUTE_SAGE_PULSE',title:slide.title||'Your SAGE status',message:slide.message||'',metric:slide.metric||'',icon:slide.icon||'sparkles',duration:7200});return;}}catch(error){console.debug('SAGE five-minute pulse refresh skipped',error);}showLiveNotification({level:'info',entity_type:'5_MINUTE_SAGE_PULSE',title:'Live tracking is active',message:'SAGE is continuing to monitor your permitted finance, requests, stock, assets and accountable activity.',icon:'sparkles',duration:7200});}
  function startFiveMinutePulse(){if(periodicPulseTimer)return;periodicPulseTimer=setInterval(showFiveMinutePulse,300000);}
  startFiveMinutePulse();

  // Charts
  function hexToRgba(hex, alpha) {
    if (!hex || !hex.startsWith('#')) return `rgba(36,87,255,${alpha})`;
    const h = hex.replace('#',''); const n = parseInt(h.length === 3 ? h.split('').map(x=>x+x).join('') : h,16);
    return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${alpha})`;
  }
  function setupCanvas(canvas) {
    const rect = canvas.getBoundingClientRect(); const dpr = Math.min(devicePixelRatio || 1, 2);
    const w = Math.max(1, rect.width), h = Math.max(1, rect.height);
    canvas.width = Math.round(w*dpr); canvas.height = Math.round(h*dpr);
    const ctx = canvas.getContext('2d'); ctx.setTransform(dpr,0,0,dpr,0,0); return {ctx,w,h};
  }
  function drawSmoothLine(ctx, points, color, width = 2) {
    if (points.length < 2) return;
    ctx.beginPath(); ctx.moveTo(points[0][0],points[0][1]);
    for (let i=0;i<points.length-1;i++) {
      const p=points[i], n=points[i+1], mx=(p[0]+n[0])/2;
      ctx.bezierCurveTo(mx,p[1],mx,n[1],n[0],n[1]);
    }
    ctx.strokeStyle=color; ctx.lineWidth=width; ctx.stroke();
  }
  function drawSparkline(canvas) {
    const {ctx,w,h}=setupCanvas(canvas); const vals=(canvas.dataset.values||'').split(',').map(Number); if(!vals.length)return;
    const baseColor = canvas.dataset.color === 'green' ? colors.green : canvas.dataset.color === 'orange' ? colors.orange : canvas.dataset.color === 'violet' ? colors.violet : cssVar('--blue') || colors.blue;
    const min=Math.min(...vals), max=Math.max(...vals), range=max-min||1; const pad=3;
    const points=vals.map((v,i)=>[i*(w/(vals.length-1)), h-pad-((v-min)/range)*(h-14)]);
    const grad=ctx.createLinearGradient(0,0,0,h); grad.addColorStop(0,hexToRgba(baseColor,.18)); grad.addColorStop(1,hexToRgba(baseColor,0));
    ctx.beginPath(); ctx.moveTo(points[0][0],h); ctx.lineTo(points[0][0],points[0][1]);
    for(let i=0;i<points.length-1;i++){const p=points[i],n=points[i+1],mx=(p[0]+n[0])/2;ctx.bezierCurveTo(mx,p[1],mx,n[1],n[0],n[1]);}
    ctx.lineTo(points.at(-1)[0],h); ctx.closePath(); ctx.fillStyle=grad;ctx.fill(); drawSmoothLine(ctx,points,baseColor,1.8);
  }
  const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function numberSeries(value){return String(value||'').split(',').map(v=>Number(v)||0);}
  function drawMainChart(canvas, kind, forcedSeries) {
    const {ctx,w,h}=setupCanvas(canvas); const dark=theme()==='dark'; const grid=dark?'#202226':'#e9ecf0'; const label=dark?'#626873':'#858b95';
    const pad={l:52,r:12,t:18,b:34}; const pw=w-pad.l-pad.r, ph=h-pad.t-pad.b; let entries=[];
    const income=numberSeries(canvas.dataset.income), expenses=numberSeries(canvas.dataset.expenses), net=numberSeries(canvas.dataset.net);
    if(kind==='overview'){const chosen=forcedSeries||canvas.dataset.series||'income', map={income,expenses,net};entries=[[chosen,map[chosen]||income,chosen==='expenses'?colors.orange:chosen==='net'?colors.green:(cssVar('--blue')||colors.blue)]];}
    else if(kind==='compare'||kind==='finance')entries=[['Income',income,cssVar('--blue')||colors.blue],['Expenses',expenses,colors.orange]];
    if(!entries.length)entries=[['Income',income,cssVar('--blue')||colors.blue]];
    const all=entries.flatMap(x=>x[1]); const rawMax=Math.max(0,...all); const max=rawMax>0?rawMax*1.12:1; const min=0;
    ctx.clearRect(0,0,w,h); ctx.font='10px Inter, sans-serif'; ctx.textBaseline='middle';
    for(let i=0;i<5;i++){const y=pad.t+(ph/4)*i;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.strokeStyle=grid;ctx.lineWidth=1;ctx.setLineDash([3,5]);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=label;const value=max-(max/4)*i;const prefix=kind==='finance'?'₦':'';const suffix='';ctx.fillText(`${prefix}${value.toLocaleString(undefined,{maximumFractionDigits:0})}${suffix}`,4,y);}
    months.forEach((m,i)=>{const x=pad.l+(pw/(months.length-1))*i;ctx.fillStyle=label;ctx.textAlign='center';ctx.fillText(m,x,h-12);});ctx.textAlign='left';
    entries.forEach(([name,vals,color],entryIndex)=>{
      const pts=vals.map((v,i)=>[pad.l+(pw/(vals.length-1))*i,pad.t+ph-((v-min)/(max-min))*ph]);
      if(entries.length===1){const grad=ctx.createLinearGradient(0,pad.t,0,pad.t+ph);grad.addColorStop(0,hexToRgba(color,.16));grad.addColorStop(1,hexToRgba(color,0));ctx.beginPath();ctx.moveTo(pts[0][0],pad.t+ph);ctx.lineTo(pts[0][0],pts[0][1]);for(let i=0;i<pts.length-1;i++){const p=pts[i],n=pts[i+1],mx=(p[0]+n[0])/2;ctx.bezierCurveTo(mx,p[1],mx,n[1],n[0],n[1]);}ctx.lineTo(pts.at(-1)[0],pad.t+ph);ctx.closePath();ctx.fillStyle=grad;ctx.fill();}
      drawSmoothLine(ctx,pts,color,2.2);
      if(entries.length>1){ctx.fillStyle=color;ctx.fillRect(pad.l+entryIndex*100,pad.t-6,8,3);ctx.fillStyle=label;ctx.font='10px Inter';ctx.fillText(name,pad.l+13+entryIndex*100,pad.t-4);}
    });
  }
  // Phase 6 management intelligence charts use only real server-provided tenant data.
  function chartJSON(canvas) { try { return JSON.parse(canvas.dataset.biValues || '[]'); } catch (_) { return []; } }
  function compactNumber(value) { const n=Number(value||0); return Math.abs(n)>=1e9?`${(n/1e9).toFixed(1)}B`:Math.abs(n)>=1e6?`${(n/1e6).toFixed(1)}M`:Math.abs(n)>=1e3?`${(n/1e3).toFixed(1)}K`:Math.round(n).toLocaleString(); }
  function attachChartTooltip(canvas, points) {
    canvas._sageHitPoints = points || []; if (canvas.dataset.tooltipBound) return; canvas.dataset.tooltipBound='1';
    canvas.addEventListener('mousemove', event => { const hits=canvas._sageHitPoints||[]; if(!hits.length)return hideBIChartTooltip(); const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top; let hit=null,distance=Infinity; hits.forEach(point=>{const d=Math.hypot(point.x-x,point.y-y);if(d<distance){distance=d;hit=point;}}); if(hit&&distance<28)showBIChartTooltip(event.clientX,event.clientY,hit.label,hit.value,hit.color);else hideBIChartTooltip(); });
    canvas.addEventListener('mouseleave',hideBIChartTooltip);
  }
  let biTooltip=null; function showBIChartTooltip(x,y,label,value,color){if(!biTooltip){biTooltip=document.createElement('div');biTooltip.className='bi-chart-tooltip';document.body.appendChild(biTooltip);}biTooltip.innerHTML=`<i style="background:${color}"></i><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong>`;biTooltip.style.left=`${Math.min(innerWidth-190,x+12)}px`;biTooltip.style.top=`${Math.max(8,y-52)}px`;biTooltip.classList.add('show');} function hideBIChartTooltip(){biTooltip?.classList.remove('show');}
  function drawBITrend(canvas) {
    const rows=chartJSON(canvas),{ctx,w,h}=setupCanvas(canvas); if(!rows.length)return; const pad={l:48,r:14,t:22,b:36},pw=w-pad.l-pad.r,ph=h-pad.t-pad.b,grid=cssVar('--border-soft')||'#252525',muted=cssVar('--muted')||'#858b98',incomeColor=cssVar('--blue')||colors.blue,expenseColor=cssVar('--orange')||colors.orange; const values=rows.flatMap(row=>[Number(row.income||0),Number(row.expenses||0)]),max=Math.max(1,...values)*1.12; ctx.clearRect(0,0,w,h);ctx.font='9px Inter';ctx.textBaseline='middle';ctx.fillStyle=muted;
    for(let i=0;i<5;i++){const y=pad.t+(ph/4)*i;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.strokeStyle=grid;ctx.setLineDash([3,5]);ctx.stroke();ctx.setLineDash([]);ctx.fillText(compactNumber(max-(max/4)*i),4,y);}
    const mapPoints=(key,color)=>rows.map((row,index)=>({x:pad.l+(pw/Math.max(1,rows.length-1))*index,y:pad.t+ph-(Number(row[key]||0)/max)*ph,label:`${row.month} · ${key==='income'?'Income':'Expenses'}`,value:`${canvas.dataset.currency||''} ${Number(row[key]||0).toLocaleString(undefined,{maximumFractionDigits:2})}`,color})); const income=mapPoints('income',incomeColor),expenses=mapPoints('expenses',expenseColor);
    [income,expenses].forEach((points,index)=>{const color=index?expenseColor:incomeColor;drawSmoothLine(ctx,points.map(p=>[p.x,p.y]),color,2.2);points.forEach(point=>{ctx.beginPath();ctx.arc(point.x,point.y,3,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();});}); rows.forEach((row,index)=>{const x=pad.l+(pw/Math.max(1,rows.length-1))*index;ctx.fillStyle=muted;ctx.textAlign='center';ctx.fillText(row.month.split(' ')[0],x,h-13);});ctx.textAlign='left';attachChartTooltip(canvas,[...income,...expenses]);
  }
  function drawBIDepartments(canvas) {
    const rows=chartJSON(canvas).slice(0,7),{ctx,w,h}=setupCanvas(canvas); if(!rows.length)return; const pad={l:Math.min(130,Math.max(88,w*.26)),r:18,t:12,b:18},pw=w-pad.l-pad.r,rowH=(h-pad.t-pad.b)/rows.length,muted=cssVar('--muted')||'#858b98',incomeColor=cssVar('--green')||colors.green,expenseColor=cssVar('--blue')||colors.blue,max=Math.max(1,...rows.flatMap(row=>[Number(row.income||0),Number(row.expenses||0)])); const hits=[];ctx.clearRect(0,0,w,h);ctx.font='9px Inter';
    rows.forEach((row,index)=>{const y=pad.t+index*rowH;ctx.fillStyle=muted;ctx.textBaseline='middle';ctx.fillText(String(row.name).slice(0,19),4,y+rowH*.5);const expenseW=(Number(row.expenses||0)/max)*pw,incomeW=(Number(row.income||0)/max)*pw,barH=Math.min(8,rowH*.24);ctx.fillStyle=hexToRgba(expenseColor,.82);ctx.fillRect(pad.l,y+rowH*.30,expenseW,barH);ctx.fillStyle=hexToRgba(incomeColor,.82);ctx.fillRect(pad.l,y+rowH*.58,incomeW,barH);hits.push({x:pad.l+expenseW,y:y+rowH*.30+barH/2,label:`${row.name} · Expenses`,value:`${canvas.dataset.currency||''} ${Number(row.expenses||0).toLocaleString()}`,color:expenseColor},{x:pad.l+incomeW,y:y+rowH*.58+barH/2,label:`${row.name} · Income`,value:`${canvas.dataset.currency||''} ${Number(row.income||0).toLocaleString()}`,color:incomeColor});});attachChartTooltip(canvas,hits);
  }
  function initBusinessIntelligenceCharts(){document.querySelectorAll('canvas[data-bi-chart="trend"]').forEach(drawBITrend);document.querySelectorAll('canvas[data-bi-chart="departments"]').forEach(drawBIDepartments);}

  function initCharts() {
    document.querySelectorAll('.sparkline').forEach(drawSparkline);
    document.querySelectorAll('canvas[data-chart]').forEach(c=>drawMainChart(c,c.dataset.chart,c.dataset.series));
    initBusinessIntelligenceCharts();
  }

  let resizeTimer;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer=setTimeout(initCharts,130); if(innerWidth>820)setMobileNav(false); });

  // ========================================================
  // PHASE 7 WEB PUSH — optional production device delivery
  // ========================================================
  function base64UrlToUint8Array(base64String){const padding='='.repeat((4-base64String.length%4)%4),base64=(base64String+padding).replace(/-/g,'+').replace(/_/g,'/'),raw=atob(base64);return Uint8Array.from([...raw].map(char=>char.charCodeAt(0)));}
  async function enableDevicePush(button){
    if(!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window))throw new Error('This browser does not support Web Push.');
    const configRes=await fetch('/api/push/config',{cache:'no-store'}),config=await configRes.json();if(!configRes.ok||!config.ok||!config.enabled)throw new Error('Web Push is not configured on this SAGE deployment.');
    const permission=await Notification.requestPermission();if(permission!=='granted')throw new Error('Browser notification permission was not granted.');
    const registration=await navigator.serviceWorker.register('/sw.js',{scope:'/'});await navigator.serviceWorker.ready;let subscription=await registration.pushManager.getSubscription();if(!subscription)subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:base64UrlToUint8Array(config.public_key)});
    const save=await fetch('/api/push/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({subscription:subscription.toJSON()})}),data=await save.json();if(!save.ok||!data.ok)throw new Error(data.message||'Could not enable browser notifications.');if(button){button.classList.add('enabled');button.querySelector('span').textContent='Enabled on this device';}showToast('Device notifications enabled','Important SAGE alerts can now reach this browser.');
  }
  if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js',{scope:'/'}).catch(()=>{});}

  function initDynamicUI() {
    initCharts();
    if (guideDrawer?.classList.contains('open')) { const help=pageHelp(),title=document.getElementById('sageGuidePageTitle'),copy=document.getElementById('sageGuidePageCopy'); if(title)title.textContent=help.title;if(copy)copy.textContent=help.copy; }
    const exportButton=document.querySelector('[data-report-export-menu]'),exportPopover=document.querySelector('[data-report-export-popover]');if(exportButton&&!exportButton.dataset.bound){exportButton.dataset.bound='1';exportButton.addEventListener('click',event=>{event.stopPropagation();exportPopover?.classList.toggle('open');});document.addEventListener('click',event=>{if(!event.target.closest('.report-export-actions'))exportPopover?.classList.remove('open');});}
    const pushButton=document.getElementById('enablePushButton');if(pushButton&&!pushButton.dataset.bound){pushButton.dataset.bound='1';if('Notification' in window && Notification.permission==='granted')pushButton.querySelector('span').textContent='Enabled / reconnect';pushButton.addEventListener('click',async()=>{pushButton.disabled=true;try{await enableDevicePush(pushButton);}catch(error){showToast('Push setup',error.message);}finally{pushButton.disabled=false;}});}
    document.querySelectorAll('[data-chart-tabs] button').forEach(btn => btn.addEventListener('click', () => {
      btn.parentElement.querySelectorAll('button').forEach(b=>b.classList.remove('active')); btn.classList.add('active');
      const canvas=btn.closest('.panel').querySelector('canvas[data-chart="overview"]'); if(canvas){canvas.dataset.series=btn.dataset.series;drawMainChart(canvas,'overview',btn.dataset.series);}
    }));
    const depModal=document.getElementById('departmentModal'); if(depModal && !depModal.dataset.bound){depModal.dataset.bound='1';depModal.addEventListener('click',e=>{if(e.target===depModal)closeModal('departmentModal');});}
    const depForm=document.getElementById('departmentForm'); if(depForm && !depForm.dataset.bound){depForm.dataset.bound='1';depForm.addEventListener('submit',async e=>{e.preventDefault();const message=depForm.querySelector('[data-department-message]'),button=depForm.querySelector('button[type="submit"]'),payload=Object.fromEntries(new FormData(depForm).entries());button.disabled=true;if(message){message.textContent='';message.className='form-message';}try{const res=await fetch('/api/departments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not create department.');closeModal('departmentModal');showToast('Department created',`${data.department.name} is now available in SAGE.`);navigate('departments',false);}catch(error){if(message){message.textContent=error.message;message.className='form-message show error';}}finally{button.disabled=false;}});}
    const inviteModal=document.getElementById('staffInviteModal'); if(inviteModal && !inviteModal.dataset.bound){inviteModal.dataset.bound='1';inviteModal.addEventListener('click',e=>{if(e.target===inviteModal)closeModal('staffInviteModal');});}
    const inviteForm=document.getElementById('staffInviteForm'); if(inviteForm && !inviteForm.dataset.bound){inviteForm.dataset.bound='1';inviteForm.addEventListener('submit',async e=>{e.preventDefault();const message=inviteForm.querySelector('[data-invite-message]'),button=inviteForm.querySelector('button[type="submit"]'),payload=Object.fromEntries(new FormData(inviteForm).entries());button.disabled=true;if(message){message.textContent='';message.className='form-message';}try{const res=await fetch('/api/staff/invite',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not create invitation.');const result=inviteForm.querySelector('#inviteResult'),link=inviteForm.querySelector('#inviteLink');if(link)link.value=data.invite_url;if(result)result.hidden=false;showToast('Invitation created','Copy the private registration link and send it to the staff member.');}catch(error){if(message){message.textContent=error.message;message.className='form-message show error';}}finally{button.disabled=false;}});}
    const copyInvite=document.getElementById('copyInviteLink'); if(copyInvite && !copyInvite.dataset.bound){copyInvite.dataset.bound='1';copyInvite.addEventListener('click',async()=>{const input=document.getElementById('inviteLink');if(!input?.value)return;try{await navigator.clipboard.writeText(input.value);showToast('Copied','Staff registration link copied to clipboard.');}catch{input.select();document.execCommand('copy');}});}
    // Staff management: combined filters, profile editing, department transfer, role changes, activity drill-down, suspend/restore/remove and bulk actions.
    const staffSearch=document.querySelector('[data-staff-search]'), staffDepartment=document.querySelector('[data-staff-filter-department]'), staffRole=document.querySelector('[data-staff-filter-role]'), staffStatus=document.querySelector('[data-staff-filter-status]');
    const applyStaffFilters=()=>{const q=(staffSearch?.value||'').toLowerCase().trim(),dep=staffDepartment?.value||'',role=staffRole?.value||'',status=staffStatus?.value||'';document.querySelectorAll('[data-staff-row]').forEach(row=>{row.hidden=Boolean((q&&!row.dataset.staffText.includes(q))||(dep&&row.dataset.departmentId!==dep)||(role&&row.dataset.role!==role)||(status&&row.dataset.status!==status));});updateStaffSelection();};
    [staffSearch,staffDepartment,staffRole,staffStatus].forEach(control=>{if(control&&!control.dataset.bound){control.dataset.bound='1';control.addEventListener(control.tagName==='INPUT'?'input':'change',applyStaffFilters);}});
    ['staffEditModal','staffActivityModal','staffDeleteModal'].forEach(id=>{const modal=document.getElementById(id);if(modal&&!modal.dataset.bound){modal.dataset.bound='1';modal.addEventListener('click',e=>{if(e.target===modal)closeModal(id);});}});

    function selectedStaffIds(){return [...document.querySelectorAll('[data-staff-select]:checked')].filter(box=>!box.closest('[data-staff-row]')?.hidden).map(box=>box.value);}
    function updateStaffSelection(){const ids=selectedStaffIds(),count=document.querySelector('[data-staff-selected-count]');if(count)count.textContent=`${ids.length} selected`;document.querySelectorAll('[data-staff-bulk]').forEach(button=>button.disabled=!ids.length);const selectAll=document.querySelector('[data-staff-select-all]'),visible=[...document.querySelectorAll('[data-staff-row]:not([hidden]) [data-staff-select]')];if(selectAll){selectAll.checked=Boolean(visible.length)&&visible.every(box=>box.checked);selectAll.indeterminate=visible.some(box=>box.checked)&&!selectAll.checked;}}
    document.querySelectorAll('[data-staff-select]').forEach(box=>{if(!box.dataset.bound){box.dataset.bound='1';box.addEventListener('change',updateStaffSelection);}});
    const selectAllStaff=document.querySelector('[data-staff-select-all]');if(selectAllStaff&&!selectAllStaff.dataset.bound){selectAllStaff.dataset.bound='1';selectAllStaff.addEventListener('change',()=>{document.querySelectorAll('[data-staff-row]:not([hidden]) [data-staff-select]').forEach(box=>box.checked=selectAllStaff.checked);updateStaffSelection();});}

    document.querySelectorAll('[data-staff-edit]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>{const row=button.closest('[data-staff-row]'),form=document.getElementById('staffEditForm');if(!row||!form)return;['firstName','middleName','lastName','phone','position','employeeId','address','sex','departmentId','role'].forEach(key=>{const name=key.replace(/[A-Z]/g,m=>'_'+m.toLowerCase()),field=form.elements[name];if(field)field.value=row.dataset[key]||'';});form.elements.user_id.value=row.dataset.userId;openModal('staffEditModal');});});
    const staffEditForm=document.getElementById('staffEditForm');if(staffEditForm&&!staffEditForm.dataset.bound){staffEditForm.dataset.bound='1';staffEditForm.addEventListener('submit',async e=>{e.preventDefault();const id=staffEditForm.elements.user_id.value,msg=staffEditForm.querySelector('[data-staff-edit-message]'),payload=Object.fromEntries(new FormData(staffEditForm).entries());delete payload.user_id;try{const res=await fetch(`/api/staff/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not update staff.');closeModal('staffEditModal');showToast('Staff updated',data.message);navigate('staff',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}});}

    document.querySelectorAll('[data-staff-status]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',async()=>{const action=button.dataset.action;if(!confirm(`${action==='suspend'?'Suspend':'Activate'} this staff account?`))return;button.disabled=true;try{const res=await fetch(`/api/staff/${button.dataset.staffStatus}/status`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not update staff status.');showToast('Staff access updated',data.message);navigate('staff',false);}catch(error){showToast('Could not update',error.message);}finally{button.disabled=false;}});});

    document.querySelectorAll('[data-staff-activity]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',async()=>{const title=document.getElementById('staffActivityTitle'),summary=document.querySelector('[data-staff-activity-summary]'),feed=document.querySelector('[data-staff-activity-feed]');if(title)title.textContent=`${button.dataset.staffName} · Activity`;if(summary)summary.innerHTML='<div class="loading-inline">Loading staff accountability…</div>';if(feed)feed.innerHTML='';openModal('staffActivityModal');try{const res=await fetch(`/api/staff/${button.dataset.staffActivity}/activity`),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not load activity.');if(summary)summary.innerHTML=`<article><span>Requests</span><strong>${data.counts.requests}</strong></article><article><span>Evidence uploads</span><strong>${data.counts.uploads}</strong></article><article><span>Finance records</span><strong>${data.counts.financial_records}</strong></article><article><span>Inventory entries</span><strong>${data.counts.inventory_items}</strong></article><article><span>Tracked events</span><strong>${data.counts.activity_events}</strong></article>`;if(feed)feed.innerHTML=data.events.length?data.events.map(event=>`<div class="staff-activity-event"><span class="audit-dot info"><svg><use href="#i-audit"/></svg></span><div><strong>${escapeHTML(event.title)}</strong><p>${escapeHTML(event.description||'')}</p><small>${new Date(event.created_at).toLocaleString()}${event.ip?` · IP ${escapeHTML(event.ip)}`:''}</small></div><span class="status info">${escapeHTML(event.action.replaceAll('_',' '))}</span></div>`).join(''):'<div class="empty-state-inline">No tracked activity yet.</div>';}catch(error){if(summary)summary.innerHTML=`<div class="empty-state-inline">${escapeHTML(error.message)}</div>`;}});});

    document.querySelectorAll('[data-staff-delete]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>{const form=document.getElementById('staffDeleteForm');if(!form)return;form.reset();form.elements.user_id.value=button.dataset.staffDelete;const label=form.querySelector('[data-delete-staff-name]');if(label)label.textContent=button.dataset.staffName||'Staff member';openModal('staffDeleteModal');});});
    const staffDeleteForm=document.getElementById('staffDeleteForm');if(staffDeleteForm&&!staffDeleteForm.dataset.bound){staffDeleteForm.dataset.bound='1';staffDeleteForm.addEventListener('submit',async e=>{e.preventDefault();const id=staffDeleteForm.elements.user_id.value,msg=staffDeleteForm.querySelector('[data-staff-delete-message]'),payload={reason:staffDeleteForm.elements.reason.value};try{const res=await fetch(`/api/staff/${id}`,{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not remove staff.');closeModal('staffDeleteModal');showToast('Staff removed',data.message);navigate('staff',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}});}

    document.querySelectorAll('[data-staff-restore]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',async()=>{button.disabled=true;try{const res=await fetch(`/api/staff/${button.dataset.staffRestore}/restore`,{method:'POST'}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not restore staff.');showToast('Staff restored',data.message);navigate('staff',false);}catch(error){showToast('Could not restore',error.message);}finally{button.disabled=false;}});});

    document.querySelectorAll('[data-staff-bulk]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',async()=>{const ids=selectedStaffIds(),action=button.dataset.staffBulk;if(!ids.length)return;if(!confirm(`${action==='delete'?'Remove':action==='suspend'?'Suspend':'Activate'} ${ids.length} selected staff account(s)?`))return;try{const res=await fetch('/api/staff/bulk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,user_ids:ids})}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Bulk update failed.');showToast('Bulk update complete',data.message);navigate('staff',false);}catch(error){showToast('Bulk update failed',error.message);}});});
    updateStaffSelection();

    // Request owner/finance decisions
    document.querySelectorAll('[data-request-action]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',async()=>{const action=button.dataset.requestAction,id=button.dataset.requestId,note=action==='reject'?prompt('Reason for rejection (optional):',''):'';if(action==='reject'&&note===null)return;button.disabled=true;try{const res=await fetch(`/api/requests/${id}/action`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,note})});const data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not update request.');showToast('Request updated',data.message);navigate('requests',false);}catch(error){showToast('Could not update',error.message);}finally{button.disabled=false;}});});

    // ======================================================
    // PHASE 8: REQUEST FUNDING + STAGE 2 ACQUISITION LOG
    // Approved requests can be opened immediately; final submission records actual quantities/costs, receipt, optional item image, stock/assets and expense.
    // ======================================================
    document.querySelectorAll('[data-open-funding]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>{const form=document.getElementById('requestFundingForm');if(!form)return;form.reset();form.elements.request_id.value=button.dataset.requestId;form.elements.approved_budget.value=button.dataset.budget||button.dataset.requestAmount||0;form.elements.amount_sent.value=button.dataset.sent||0;const context=document.getElementById('fundingContext');if(context)context.textContent=`${button.dataset.requestRef} · ${button.dataset.requestTitle}`;openModal('requestFundingModal');});});
    const fundingForm=document.getElementById('requestFundingForm');if(fundingForm&&!fundingForm.dataset.bound){fundingForm.dataset.bound='1';fundingForm.addEventListener('submit',async e=>{e.preventDefault();const msg=fundingForm.querySelector('[data-funding-message]'),id=fundingForm.elements.request_id.value,payload=Object.fromEntries(new FormData(fundingForm).entries());payload.mark_money_sent=Boolean(fundingForm.elements.mark_money_sent?.checked);try{const res=await fetch(`/api/requests/${id}/funding`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not save funding.');closeModal('requestFundingModal');showToast('Funding updated',data.message);navigate('requests',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}});}

    const purchaseForm=document.getElementById('purchaseRecordForm'),stage2Lines=document.getElementById('stage2LineItems'),stage2Total=document.getElementById('stage2ActualTotal'),stage2Summary=document.getElementById('stage2RequestSummary');
    const currency=value=>(window.SAGE_USER?.currency||window.VISION_USER?.currency||'NGN')+' '+Number(value||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
    const updateStage2Total=()=>{if(!purchaseForm)return 0;let total=0;purchaseForm.querySelectorAll('[data-stage2-line]').forEach(row=>{const qty=Number(row.querySelector('[data-actual-qty]')?.value||0),cost=Number(row.querySelector('[data-actual-cost]')?.value||0),value=qty*cost;total+=value;const out=row.querySelector('[data-actual-line-total]');if(out)out.textContent=currency(value);});if(stage2Total)stage2Total.textContent=currency(total);return total;};
    function syncStage2Source(){if(!purchaseForm)return;const other=purchaseForm.elements.source_type?.value==='received_from_other';purchaseForm.querySelector('[data-other-source]')?.toggleAttribute('hidden',!other);purchaseForm.querySelector('[data-self-source]')?.toggleAttribute('hidden',other);}
    async function openStage2(button){if(!purchaseForm)return;purchaseForm.reset();const id=button.dataset.requestId,msg=purchaseForm.querySelector('[data-purchase-message]');if(msg){msg.textContent='Loading approved request…';msg.className='form-message show';}try{const res=await fetch(`/api/requests/${id}/fulfillment`,{cache:'no-store'}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not load request.');purchaseForm.querySelector('#purchaseRequestId').value=id;const context=document.getElementById('purchaseRecordContext');if(context)context.textContent=`${data.request.reference} · ${data.request.title}`;purchaseForm.elements.source_type.value=data.fulfillment?.source_type||'self_purchase';purchaseForm.elements.supplied_by.value=data.fulfillment?.supplied_by||'';purchaseForm.elements.supplier_name.value=data.fulfillment?.supplier_name||'';purchaseForm.elements.purchase_date.value=data.fulfillment?.purchase_date||new Date().toISOString().slice(0,10);purchaseForm.elements.notes.value=data.fulfillment?.notes||'';const now=new Date(),local=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,16);purchaseForm.elements.delivered_at.value=data.items.find(x=>x.delivery_at)?.delivery_at?.slice(0,16)||local;stage2Summary.innerHTML=`<div><span>Request</span><strong>${escapeHTML(data.request.reference)}</strong></div><div><span>Requested</span><strong>${currency(data.request.estimated_total)}</strong></div><div><span>Approved budget</span><strong>${currency(data.funding?.approved_budget??data.request.estimated_total)}</strong></div><div><span>Money sent</span><strong>${currency(data.funding?.amount_sent||0)}</strong></div><div><span>Status</span><strong>${escapeHTML(data.request.status.replaceAll('_',' '))}</strong></div>`;stage2Lines.innerHTML=data.items.map(item=>`<tr data-stage2-line><td><b>${escapeHTML(item.name)}</b><small class="table-sub">${escapeHTML(item.category||'')}</small><input type="hidden" name="line_note_${item.id}" value="${escapeHTML(item.note||'')}"></td><td>${Number(item.requested_quantity).toLocaleString()} ${escapeHTML(item.unit)}</td><td><input class="compact-input" data-actual-qty name="actual_quantity_${item.id}" type="number" min="0" step="0.001" value="${item.actual_quantity}"></td><td>${currency(item.requested_unit_cost)}</td><td><input class="compact-input" data-actual-cost name="actual_unit_cost_${item.id}" type="number" min="0" step="0.01" value="${item.actual_unit_cost}"></td><td><b data-actual-line-total>${currency(item.actual_quantity*item.actual_unit_cost)}</b></td></tr>`).join('');purchaseForm.querySelectorAll('[data-actual-qty],[data-actual-cost]').forEach(input=>input.addEventListener('input',updateStage2Total));syncStage2Source();updateStage2Total();if(msg){msg.textContent='';msg.className='form-message';}openModal('purchaseRecordModal');}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}showToast('Stage 2',error.message);}}
    document.querySelectorAll('[data-record-purchase]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>openStage2(button));});
    if(purchaseForm&&!purchaseForm.dataset.bound){purchaseForm.dataset.bound='1';purchaseForm.elements.source_type?.addEventListener('change',syncStage2Source);purchaseForm.querySelector('[data-source-staff]')?.addEventListener('change',e=>{if(e.target.value&&!purchaseForm.elements.supplied_by.value)purchaseForm.elements.supplied_by.value=e.target.options[e.target.selectedIndex]?.textContent||'';});const save=async(finalize)=>{const msg=purchaseForm.querySelector('[data-purchase-message]'),id=purchaseForm.querySelector('#purchaseRequestId').value,data=new FormData(purchaseForm);data.set('finalize',finalize?'true':'false');try{if(msg){msg.textContent='';msg.className='form-message';}const res=await fetch(`/api/requests/${id}/fulfillment`,{method:'POST',body:data}),result=await res.json();if(!res.ok||!result.ok)throw new Error(result.message||'Could not save acquisition record.');closeModal('purchaseRecordModal');showToast(finalize?'Stage 2 submitted':'Draft saved',result.message);navigate(body.dataset.page==='fulfillment'?'fulfillment':'requests',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}};purchaseForm.addEventListener('submit',e=>{e.preventDefault();save(true);});purchaseForm.querySelector('[data-purchase-draft]')?.addEventListener('click',()=>save(false));}

    // Phase 2 department catalogue: custom additions, live filtering and one-click request prefill.
    const catalogModal=document.getElementById('catalogItemModal'); if(catalogModal&&!catalogModal.dataset.bound){catalogModal.dataset.bound='1';catalogModal.addEventListener('click',e=>{if(e.target===catalogModal)closeModal('catalogItemModal');});}
    const catalogForm=document.getElementById('catalogItemForm'); if(catalogForm&&!catalogForm.dataset.bound){catalogForm.dataset.bound='1';catalogForm.addEventListener('submit',async e=>{e.preventDefault();const msg=catalogForm.querySelector('[data-catalog-message]'),payload=Object.fromEntries(new FormData(catalogForm).entries());try{const res=await fetch('/api/catalog/items',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not add catalogue item.');closeModal('catalogItemModal');showToast('Catalogue updated',data.message);navigate('catalog',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}});}
    const catalogSearch=document.querySelector('[data-catalog-search]'); const categoryButtons=[...document.querySelectorAll('[data-catalog-category]')]; let activeCatalogCategory='all'; const applyCatalogFilters=()=>{const q=(catalogSearch?.value||'').trim().toLowerCase();document.querySelectorAll('[data-catalog-item]').forEach(card=>{const category=card.dataset.catalogCategoryValue||'',matchesText=!q||(card.dataset.catalogText||'').includes(q),matchesCategory=activeCatalogCategory==='all'||category===activeCatalogCategory;card.hidden=!(matchesText&&matchesCategory);});document.querySelectorAll('[data-catalog-group]').forEach(group=>{group.hidden=![...group.querySelectorAll('[data-catalog-item]')].some(card=>!card.hidden);});}; if(catalogSearch&&!catalogSearch.dataset.bound){catalogSearch.dataset.bound='1';catalogSearch.addEventListener('input',applyCatalogFilters);} categoryButtons.forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>{activeCatalogCategory=button.dataset.catalogCategory||'all';categoryButtons.forEach(row=>row.classList.toggle('active',row===button));applyCatalogFilters();});});

    // Inventory manual entry
    const invModal=document.getElementById('inventoryModal'); if(invModal&&!invModal.dataset.bound){invModal.dataset.bound='1';invModal.addEventListener('click',e=>{if(e.target===invModal)closeModal('inventoryModal');});}
    const invForm=document.getElementById('inventoryForm'); if(invForm&&!invForm.dataset.bound){invForm.dataset.bound='1';invForm.addEventListener('submit',async e=>{e.preventDefault();const msg=invForm.querySelector('[data-inventory-message]'),payload=Object.fromEntries(new FormData(invForm).entries());try{const res=await fetch('/api/inventory/items',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not add item.');closeModal('inventoryModal');showToast('Inventory updated',data.message);navigate('inventory',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}});}

    // Phase 3 stock movements: issue/use, transfer, return, write-off and positive adjustment.
    document.querySelectorAll('[data-move-stock]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>{const form=document.getElementById('stockMoveForm');if(!form)return;form.reset();form.elements.item_id.value=button.dataset.itemId;const title=document.getElementById('stockMoveTitle');if(title)title.textContent=`${button.dataset.itemName} · Available ${button.dataset.itemQty} ${button.dataset.itemUnit}`;openModal('stockMoveModal');});});
    const stockMoveForm=document.getElementById('stockMoveForm');if(stockMoveForm&&!stockMoveForm.dataset.bound){stockMoveForm.dataset.bound='1';stockMoveForm.addEventListener('submit',async e=>{e.preventDefault();const msg=stockMoveForm.querySelector('[data-stock-move-message]'),payload=Object.fromEntries(new FormData(stockMoveForm).entries()),id=payload.item_id;delete payload.item_id;try{const res=await fetch(`/api/inventory/items/${id}/move`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not record stock movement.');closeModal('stockMoveModal');showToast('Stock movement recorded',data.message);navigate('inventory',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}});}

    // Phase 3 asset register + custody/movement engine.
    const assetForm=document.getElementById('assetForm');if(assetForm&&!assetForm.dataset.bound){assetForm.dataset.bound='1';assetForm.addEventListener('submit',async e=>{e.preventDefault();const msg=assetForm.querySelector('[data-asset-message]'),payload=Object.fromEntries(new FormData(assetForm).entries());try{const res=await fetch('/api/assets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not add asset.');closeModal('assetModal');showToast('Asset registered',data.message);navigate('assets',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}});}
    document.querySelectorAll('[data-move-asset]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>{const form=document.getElementById('assetMoveForm');if(!form)return;form.reset();form.elements.asset_id.value=button.dataset.assetId;form.elements.location.value=button.dataset.assetLocation||'';const title=document.getElementById('assetMoveTitle');if(title)title.textContent=button.dataset.assetName||'Asset';openModal('assetMoveModal');});});
    const assetMoveForm=document.getElementById('assetMoveForm');if(assetMoveForm&&!assetMoveForm.dataset.bound){assetMoveForm.dataset.bound='1';assetMoveForm.addEventListener('submit',async e=>{e.preventDefault();const msg=assetMoveForm.querySelector('[data-asset-move-message]'),payload=Object.fromEntries(new FormData(assetMoveForm).entries()),id=payload.asset_id;delete payload.asset_id;try{const res=await fetch(`/api/assets/${id}/move`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not move asset.');closeModal('assetMoveModal');showToast('Asset updated',data.message);navigate('assets',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}});}

    // Phase 4 department operations: job-specific actions are written to the database and instantly enter owner live tracking.
    document.querySelectorAll('[data-open-operation]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>{const form=document.getElementById('operationForm');if(!form)return;form.reset();form.elements.operation_type.value=button.dataset.operationType||'';form.elements.title.value=button.dataset.operationLabel||'';const title=document.getElementById('operationModalTitle');if(title)title.textContent=button.dataset.operationLabel||'Record Department Activity';const now=new Date(),local=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,16);if(form.elements.occurred_at)form.elements.occurred_at.value=local;openModal('operationModal');});});
    const operationForm=document.getElementById('operationForm');if(operationForm&&!operationForm.dataset.bound){operationForm.dataset.bound='1';operationForm.addEventListener('submit',async e=>{e.preventDefault();const msg=operationForm.querySelector('[data-operation-message]'),payload=Object.fromEntries(new FormData(operationForm).entries()),button=operationForm.querySelector('button[type="submit"]');button.disabled=true;try{const res=await fetch('/api/operations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not record department operation.');closeModal('operationModal');showToast('Operation recorded',`${data.reference} · Management tracking updated.`);navigate('operations',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}finally{button.disabled=false;}});}

    // Phase 4 staff reports: daily/weekly reports compile real activity and can be submitted/acknowledged without manual report typing.
    const reportModal=document.getElementById('reportModal'),reportForm=document.getElementById('reportForm');document.querySelectorAll('[data-generate-report]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>{if(!reportForm)return;reportForm.reset();reportForm.elements.period_type.value=button.dataset.generateReport||'daily';const title=document.getElementById('reportModalTitle');if(title)title.textContent=`Generate ${(button.dataset.generateReport||'daily').replace(/^./,c=>c.toUpperCase())} Activity Report`;openModal('reportModal');});});
    const sendStaffReport=async(action,periodType,staffNote='')=>{const res=await fetch('/api/staff-reports',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,period_type:periodType,staff_note:staffNote})}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not generate report.');showToast(action==='submit'?'Report submitted':'Report generated',data.message);navigate('reports',false);};
    if(reportForm&&!reportForm.dataset.bound){reportForm.dataset.bound='1';reportForm.addEventListener('submit',async e=>{e.preventDefault();const msg=reportForm.querySelector('[data-report-message]');try{await sendStaffReport('submit',reportForm.elements.period_type.value,reportForm.elements.staff_note.value);closeModal('reportModal');}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}});reportForm.querySelector('[data-report-action="draft"]')?.addEventListener('click',async()=>{const msg=reportForm.querySelector('[data-report-message]');try{await sendStaffReport('draft',reportForm.elements.period_type.value,reportForm.elements.staff_note.value);closeModal('reportModal');}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}});}
    document.querySelectorAll('[data-submit-report]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',async()=>{button.disabled=true;try{await sendStaffReport('submit',button.dataset.reportPeriod||'daily','');}catch(error){showToast('Could not submit report',error.message);}finally{button.disabled=false;}});});
    document.querySelectorAll('[data-ack-report]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',async()=>{button.disabled=true;try{const res=await fetch(`/api/staff-reports/${button.dataset.ackReport}/acknowledge`,{method:'POST'}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Could not acknowledge report.');showToast('Report acknowledged',data.message);navigate('reports',false);}catch(error){showToast('Could not acknowledge',error.message);}finally{button.disabled=false;}});});

    // ======================================================
    // PHASE 5: FINANCE & ACCOUNTS CONTROL CENTRE
    // Handles tabs, account/ledger/budget/AR/AP/payroll/tax/reconciliation/forecast forms and live refresh.
    // ======================================================
    document.querySelectorAll('[data-finance-tab]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>{document.querySelectorAll('[data-finance-tab]').forEach(tab=>tab.classList.toggle('active',tab===button));document.querySelectorAll('[data-finance-panel]').forEach(panel=>panel.classList.toggle('active',panel.dataset.financePanel===button.dataset.financeTab));});});
    ['financeAccountModal','financeLedgerModal','financeBudgetModal','financeReceivableModal','financePayableModal','financeReconcileModal','financePayrollModal','financeTaxModal','financeForecastModal'].forEach(id=>{const modal=document.getElementById(id);if(modal&&!modal.dataset.bound){modal.dataset.bound='1';modal.addEventListener('click',e=>{if(e.target===modal)closeModal(id);});}});
    document.querySelectorAll('.finance-api-form').forEach(form=>{if(form.dataset.bound)return;form.dataset.bound='1';form.addEventListener('submit',async e=>{e.preventDefault();const msg=form.querySelector('.form-message'),button=form.querySelector('button[type="submit"]'),payload=Object.fromEntries(new FormData(form).entries()),endpoint=form.dataset.financeEndpoint;button.disabled=true;try{const res=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Finance record could not be saved.');const modal=form.closest('.modal-backdrop');if(modal)closeModal(modal.id);showToast('Finance updated',data.message||'Record saved.');navigate('finance',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}finally{button.disabled=false;}});});
    const ledgerForm=document.querySelector('.finance-ledger-form');if(ledgerForm&&!ledgerForm.dataset.bound){ledgerForm.dataset.bound='1';ledgerForm.addEventListener('submit',async e=>{e.preventDefault();const msg=ledgerForm.querySelector('.form-message'),button=ledgerForm.querySelector('button[type="submit"]'),payload=new FormData(ledgerForm);button.disabled=true;try{const res=await fetch('/api/finance/ledger',{method:'POST',body:payload}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Transaction could not be posted.');closeModal('financeLedgerModal');showToast('Finance transaction saved',`${data.reference||''} ${data.message||''}`.trim());navigate('finance',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}finally{button.disabled=false;}});}
    document.querySelectorAll('[data-settle-receivable],[data-settle-payable]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',async()=>{const type=button.hasAttribute('data-settle-receivable')?'receivables':'payables',id=button.dataset.settleReceivable||button.dataset.settlePayable,balance=Number(button.dataset.balance||0),entered=prompt(`Amount to record (maximum ${balance.toLocaleString()}):`,balance.toString());if(entered===null)return;button.disabled=true;try{const res=await fetch(`/api/finance/${type}/${id}/payment`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({amount:entered})}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Payment could not be recorded.');showToast('Payment recorded',data.message);navigate('finance',false);}catch(error){showToast('Finance update failed',error.message);}finally{button.disabled=false;}});});

    // CEO Upgrade Phase 3: branch/location and configurable approval-control forms.
    document.querySelectorAll('[data-management-form]').forEach(form=>{if(form.dataset.bound)return;form.dataset.bound='1';form.addEventListener('submit',async e=>{e.preventDefault();const msg=form.querySelector('.form-message'),button=form.querySelector('button[type="submit"]'),payload=Object.fromEntries(new FormData(form).entries());button.disabled=true;try{const res=await fetch(form.dataset.endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),data=await res.json();if(!res.ok||!data.ok)throw new Error(data.message||'Management setting could not be saved.');showToast('Management control updated',data.message);navigate('settings',false);}catch(error){if(msg){msg.textContent=error.message;msg.className='form-message show error';}}finally{button.disabled=false;}});});

    // CEO UPGRADE PHASE 4: management verification closes Request → Approval → Purchase → Receipt → Delivery → Verification → Payment.
    document.querySelectorAll('[data-verify-acquisition]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',async()=>{const requestId=button.dataset.verifyAcquisition;if(!requestId||button.disabled)return;button.disabled=true;const original=button.innerHTML;button.textContent='Verifying…';try{const response=await fetch(`/api/requests/${requestId}/verify`,{method:'POST',headers:{'Accept':'application/json'}}),data=await response.json();if(!response.ok||!data.ok)throw new Error(data.message||'Verification failed.');showToast('Purchase verified',data.message||'Acquisition verified.');navigate('procurement',false);}catch(error){showToast('Verification failed',error.message||'Could not verify acquisition.');button.disabled=false;button.innerHTML=original;}});});

    // Owner request command centre: combined search/status/department filtering, summary chips, relative age and sortable Excel-like ledger columns.
    const requestSearch=document.querySelector('[data-request-search]'),requestDepartment=document.querySelector('[data-request-department-filter]'),requestStatus=document.querySelector('[data-request-status-filter]');let requestChip='';
    const applyRequestFilters=()=>{const q=(requestSearch?.value||'').toLowerCase().trim(),department=requestDepartment?.value||'',status=requestStatus?.value||requestChip;document.querySelectorAll('[data-request-row]').forEach(row=>{const completed=status==='completed'&&['fulfilled','verified'].includes(row.dataset.requestStatus),statusMatch=!status||completed||row.dataset.requestStatus===status;row.hidden=Boolean((q&&!row.dataset.requestText.includes(q))||(department&&row.dataset.requestDepartment!==department)||!statusMatch);});document.querySelectorAll('[data-owner-request-card]').forEach(card=>{const statusMatch=!status||(status==='completed'?['fulfilled','verified'].includes(card.dataset.status):card.dataset.status===status);card.hidden=Boolean((department&&card.dataset.department!==department)||!statusMatch);});};
    [requestSearch,requestDepartment,requestStatus].forEach(control=>{if(control&&!control.dataset.bound){control.dataset.bound='1';control.addEventListener(control.tagName==='INPUT'?'input':'change',applyRequestFilters);}});document.querySelectorAll('[data-request-chip]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.addEventListener('click',()=>{requestChip=button.dataset.requestChip||'';if(requestStatus)requestStatus.value=requestChip==='completed'?'':requestChip;document.querySelectorAll('[data-request-chip]').forEach(item=>item.classList.toggle('active',item===button));applyRequestFilters();});});
    document.querySelectorAll('[data-relative-time]').forEach(node=>{const value=new Date(node.dataset.relativeTime),seconds=Math.max(0,(Date.now()-value.getTime())/1000);node.textContent=seconds<60?'just now':seconds<3600?`${Math.floor(seconds/60)}m ago`:seconds<86400?`${Math.floor(seconds/3600)}h ago`:`${Math.floor(seconds/86400)}d ago`;});
    document.querySelectorAll('[data-request-sort]').forEach(button=>{if(button.dataset.bound)return;button.dataset.bound='1';button.dataset.direction='desc';button.addEventListener('click',()=>{const key=button.dataset.requestSort,body=document.querySelector('[data-request-ledger-body]');if(!body)return;const direction=button.dataset.direction==='asc'?'desc':'asc';document.querySelectorAll('[data-request-sort]').forEach(item=>item.dataset.direction='');button.dataset.direction=direction;const rows=[...body.querySelectorAll('[data-request-row]')];rows.sort((a,b)=>{let av=a.dataset[`request${key[0].toUpperCase()+key.slice(1)}`]||'',bv=b.dataset[`request${key[0].toUpperCase()+key.slice(1)}`]||'';if(key==='amount'){av=Number(av);bv=Number(bv);}else if(key==='date'){av=new Date(av).getTime();bv=new Date(bv).getTime();}else{av=av.toLowerCase();bv=bv.toLowerCase();}return(av>bv?1:av<bv?-1:0)*(direction==='asc'?1:-1);});rows.forEach(row=>body.appendChild(row));});});

    [['[data-inventory-search]','[data-inventory-row]','inventoryText'],['[data-asset-search]','[data-asset-row]','assetText'],['[data-audit-search]','[data-audit-row]','auditText']].forEach(([inputSel,rowSel,key])=>{const input=document.querySelector(inputSel);if(input&&!input.dataset.bound){input.dataset.bound='1';input.addEventListener('input',()=>{const q=input.value.toLowerCase().trim();document.querySelectorAll(rowSel).forEach(row=>row.hidden=Boolean(q&&!row.dataset[key].includes(q)));});}});
  }

  trackPageView(body.dataset.page || window.SAGE_INITIAL_PAGE || window.VISION_INITIAL_PAGE || 'dashboard');
  initDynamicUI();
  setTimeout(()=>launchDailyBriefing(false),700);
})();
