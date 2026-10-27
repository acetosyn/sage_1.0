(()=>{'use strict';
  // ========================================================
  // SAGE 6.0 MOBILE RUNTIME
  // Adds mobile-safe table metadata after every full load / SPA swap.
  // No framework rewrite required; this stays native to SAGE's Flask UI.
  // ========================================================
  const mq=matchMedia('(max-width:820px)'),q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const wideCell=/description|category|request|item|evidence|receipt|action|note|purpose|source|customer|vendor|payee|staff|recorded by|department & requester/i;
  const moneyCell=/amount|money|total|cost|spend|income|revenue|budget|balance|received|outstanding|cash|returned|payable|receivable|committed/i;
  const actionCell=/action|evidence|receipt|document|photo|proof/i;
  function normalizeHeader(th){const clone=th.cloneNode(true);clone.querySelectorAll('svg,i').forEach(n=>n.remove());return (clone.textContent||'').replace(/\s+/g,' ').trim();}
  function decorateTable(table){
    if(table.closest('.calendar-grid,.calendar-table')||table.dataset.mobileLayout==='desktop')return;
    table.classList.add('sage6-mobile-table');
    const heads=qa('thead th',table).map(normalizeHeader);
    qa('tbody tr',table).forEach(row=>{
      const cells=qa(':scope > td',row);if(!cells.length)return;
      cells.forEach((cell,i)=>{
        const label=cell.dataset.label||heads[i]||'';if(label&&!cell.dataset.label)cell.dataset.label=label;
        cell.classList.toggle('sage6-wide-cell',wideCell.test(label));
        cell.classList.toggle('sage6-money-cell',moneyCell.test(label));
        cell.classList.toggle('sage6-action-cell',actionCell.test(label));
      });
    });
    const wrap=table.parentElement;if(wrap&&/table-(scroll|wrap|scroller)|finance-workbook-scroll|history-ledger-scroll|money-table-scroll/.test(wrap.className))wrap.classList.add('sage6-mobile-table-wrap');
  }
  function decorate(root=document){
    document.body.classList.toggle('sage6-mobile',mq.matches);
    if(!mq.matches)return;
    qa('.main-content table,.platform-v2-main table',root).forEach(decorateTable);
    qa('.modal-card',document).forEach(card=>{card.classList.add('sage6-modal-ready');card.querySelectorAll('input,select,textarea').forEach(el=>{if(el.autofocus)el.removeAttribute('autofocus');});});
  }
  let raf=0;function schedule(root=document){cancelAnimationFrame(raf);raf=requestAnimationFrame(()=>decorate(root));}
  mq.addEventListener?.('change',()=>schedule(document));
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',()=>schedule(document),{once:true}):schedule(document);
  const app=q('#appContent');if(app)new MutationObserver(()=>schedule(app)).observe(app,{childList:true,subtree:true});
  new MutationObserver(()=>schedule(document)).observe(document.body,{attributes:true,attributeFilter:['data-page']});
  window.SAGE6Refresh=()=>schedule(document);
})();
