(()=>{'use strict';
  // ========================================================
  // SAGE 7.0 MOBILE RUNTIME
  // Mobile-first ledger preservation + compact workspace adapter.
  // Tables remain tables on phones; this layer never converts rows to cards.
  // ========================================================
  const mq=matchMedia('(max-width:900px)'),q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const normalize=v=>(v||'').replace(/\s+/g,' ').trim();
  const kindFor=label=>{const s=normalize(label).toLowerCase();if(/date|reference/.test(s))return'date';if(/description|category|request|item|purpose|note/.test(s))return'description';if(/amount|total|cost|spend|income|revenue|budget|balance|received|outstanding|cash|returned|payable|receivable|committed|actual/.test(s))return'amount';if(/department|account|branch/.test(s))return'department';if(/counterparty|customer|vendor|payee|requester|recorded by|staff|owner|source/.test(s))return'person';if(/payment|method|external ref/.test(s))return'payment';if(/status|stage|direction|type|urgency/.test(s))return'status';if(/evidence|receipt|document|photo|proof/.test(s))return'evidence';if(/action|control/.test(s))return'action';return'generic';};
  const widthFor=kind=>({date:150,description:285,amount:125,department:180,person:155,payment:175,status:115,evidence:120,action:135,generic:140}[kind]||140);
  function unwrapHeader(th){const clone=th.cloneNode(true);clone.querySelectorAll('svg,i').forEach(n=>n.remove());return normalize(clone.textContent);}
  function tableWrap(table){return table.closest('.table-scroll,.table-scroller,.table-wrap,.finance-workbook-scroll,.history-ledger-scroll,.money-table-scroll,.settings-role-table-wrap,.settings-approval-table-wrap')||table.parentElement;}
  function decorateTable(table){
    if(!mq.matches||table.closest('.calendar-grid,.calendar-table')||table.dataset.mobileLayout==='desktop')return;
    table.classList.add('sage7-mini-ledger');
    const heads=qa('thead th',table),labels=heads.map(unwrapHeader),cols=Math.max(heads.length,qa('tbody tr:first-child>td',table).length),firstIsIndex=/^#|^no\.?$|^number$/i.test(labels[0]||'');
    table.classList.toggle('sage7-sticky-two',firstIsIndex&&cols>4);table.classList.toggle('sage7-sticky-one',!firstIsIndex&&cols>4);
    let min=0;heads.forEach((th,i)=>{const kind=kindFor(labels[i]);th.dataset.s7Kind=kind;const w=widthFor(kind);th.style.setProperty('--s7-col-w',`${w}px`);min+=w;});
    if(!heads.length)min=Math.max(560,cols*140);table.style.setProperty('--s7-table-min',`${Math.max(min,cols<=4?520:cols<=6?720:cols<=8?940:1120)}px`);
    qa('tbody tr',table).forEach(row=>qa(':scope > td',row).forEach((cell,i)=>{const label=cell.dataset.label||labels[i]||'';const kind=kindFor(label);cell.dataset.s7Kind=kind;if(label&&!cell.dataset.label)cell.dataset.label=label;const w=widthFor(kind);cell.style.setProperty('--s7-col-w',`${w}px`);}));
    const wrap=tableWrap(table);if(wrap){wrap.classList.add('sage7-ledger-scroll');wrap.setAttribute('tabindex','0');wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Scrollable data table. Swipe left or right to view more columns.');bindScrollState(wrap);}
  }
  function bindScrollState(wrap){if(wrap.dataset.s7ScrollBound)return;wrap.dataset.s7ScrollBound='1';const sync=()=>{const max=Math.max(0,wrap.scrollWidth-wrap.clientWidth);wrap.classList.toggle('s7-can-left',wrap.scrollLeft>6);wrap.classList.toggle('s7-can-right',wrap.scrollLeft<max-6);};wrap.addEventListener('scroll',sync,{passive:true});requestAnimationFrame(sync);}
  function decorateShelves(root=document){
    qa('.income-kpi-grid,.expense-kpi-grid,.income-insight-grid,.expense-insight-grid,.finance-workbook-summary,.money-filter-summary,.finance-kpi-grid,.control-metrics,.owner-request-kpis,.staff-request-wallet-premium',root).forEach(el=>el.classList.add('sage7-mobile-shelf'));
    qa('.money-filter-shell,.finance-workbook-filters',root).forEach(el=>el.classList.add('sage7-filter-shelf'));
  }
  function decorateModals(){qa('.modal-card,.v4-dialog-live,.phase8-acquisition-modal',document).forEach(card=>{card.classList.add('sage7-mobile-modal');card.querySelectorAll('[autofocus]').forEach(el=>el.removeAttribute('autofocus'));});}
  function decorate(root=document){document.body.classList.toggle('sage7-mobile',mq.matches);if(!mq.matches)return;qa('.main-content table,.platform-v2-main table',root).forEach(decorateTable);decorateShelves(root);decorateModals();}
  let raf=0;function schedule(root=document){cancelAnimationFrame(raf);raf=requestAnimationFrame(()=>decorate(root));}
  mq.addEventListener?.('change',()=>schedule(document));
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',()=>schedule(document),{once:true}):schedule(document);
  const app=q('#appContent');if(app)new MutationObserver(()=>schedule(app)).observe(app,{childList:true,subtree:true});
  new MutationObserver(()=>schedule(document)).observe(document.body,{attributes:true,attributeFilter:['data-page','class']});
  window.SAGE7Refresh=()=>schedule(document);
})();
