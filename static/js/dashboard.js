/* Account-scoped dashboard preferences; works after full loads and Flask partial swaps. */
(() => {
  const privateContent = new WeakMap();
  let resizeObserver;
  let layoutFrame;
  const defaults = () => ({
    density: 'comfortable', private: false, focus: false, tab: 'today',
    sections: {metrics: false, departments: false}, priority: 'all',
    departmentSearch: '', departmentSort: 'activity', departmentScope: 'all',
    allDepartments: false, allAttention: false, openDepartments: {}
  });

  function init({refresh, redraw} = {}) {
    const dashboard = document.querySelector('[data-dashboard]');
    if (!dashboard) { resizeObserver?.disconnect(); return; }
    if (dashboard.dataset.dashboardBound) return;
    resizeObserver?.disconnect();
    dashboard.dataset.dashboardBound = '1';
    const key = `sage-dashboard-v1:${dashboard.dataset.dashboardKey}`;
    let saved;
    try { saved = JSON.parse(localStorage.getItem(key) || '{}'); } catch { saved = {}; }
    const state = {...defaults(), ...saved, sections: {...defaults().sections, ...saved?.sections}, openDepartments: saved?.openDepartments || {}};
    const $ = selector => dashboard.querySelector(selector);
    const $$ = selector => [...dashboard.querySelectorAll(selector)];
    const announce = text => { $('[data-dashboard-announcement]').textContent = text; };
    const save = () => { try { localStorage.setItem(key, JSON.stringify(state)); } catch { /* Preferences remain usable if storage is disabled. */ } };
    const layout = () => { cancelAnimationFrame(layoutFrame); layoutFrame = requestAnimationFrame(() => redraw?.()); };
    let lastWidth = dashboard.getBoundingClientRect().width;
    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(entries => {
        const width = entries[0].contentRect.width;
        if (Math.abs(width - lastWidth) > 1) { lastWidth = width; layout(); }
      });
      resizeObserver.observe(dashboard);
    }

    function applyPrivacy() {
      dashboard.classList.toggle('dashboard-amounts-hidden', Boolean(state.private));
      $$('[data-private-value], [data-private-activity]').forEach(element => {
        if (!privateContent.has(element)) privateContent.set(element, element.innerHTML);
        if (state.private) element.textContent = element.hasAttribute('data-private-value') ? '••••' : 'Details hidden while amounts are private.';
        else element.innerHTML = privateContent.get(element);
      });
      $$('canvas[role="img"]').forEach(canvas => canvas.setAttribute('aria-hidden', String(Boolean(state.private))));
      $$('.dashboard-chart-privacy').forEach(notice => notice.hidden = !state.private);
      const button = $('[data-dashboard-privacy]');
      button.setAttribute('aria-pressed', String(Boolean(state.private)));
      button.querySelector('span').textContent = state.private ? 'Show amounts' : 'Hide amounts';
    }
    window.SAGEDashboard.syncPrivacy = applyPrivacy;
    function applyFocus() {
      dashboard.classList.toggle('dashboard-focus', Boolean(state.focus));
      $('[data-dashboard-focus]').setAttribute('aria-pressed', String(Boolean(state.focus)));
      $('[data-dashboard-focus-notice]').hidden = !state.focus;
      layout();
    }
    function applyDensity() {
      state.density = state.density === 'compact' ? 'compact' : 'comfortable';
      dashboard.classList.toggle('dashboard-compact', state.density === 'compact');
      $$('[data-dashboard-density]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.dashboardDensity === state.density)));
      layout();
    }
    function activateTab(tab, focus = false) {
      if (!['today', 'position', 'control'].includes(tab)) tab = 'today';
      state.tab = tab;
      $$('[data-dashboard-tab]').forEach(button => {
        const selected = button.dataset.dashboardTab === tab;
        button.setAttribute('aria-selected', String(selected));
        button.tabIndex = selected ? 0 : -1;
        if (selected && focus) button.focus();
      });
      $$('[data-dashboard-tab-panel]').forEach(panel => panel.hidden = panel.dataset.dashboardTabPanel !== tab);
      save(); layout();
    }
    $$('[data-dashboard-section]').forEach(section => {
      section.open = Boolean(state.sections[section.dataset.dashboardSection]);
      const syncLabel = () => section.querySelector('[data-dashboard-section-label]').textContent = section.open ? 'Collapse' : 'Expand';
      syncLabel();
      section.addEventListener('toggle', () => {
        if (!dashboard.isConnected) return;
        state.sections[section.dataset.dashboardSection] = section.open;
        syncLabel(); save(); layout();
      });
    });
    $$('[data-dashboard-tab]').forEach((button, index, tabs) => {
      button.addEventListener('click', () => activateTab(button.dataset.dashboardTab));
      button.addEventListener('keydown', event => {
        let target;
        if (event.key === 'ArrowRight') target = (index + 1) % tabs.length;
        if (event.key === 'ArrowLeft') target = (index + tabs.length - 1) % tabs.length;
        if (event.key === 'Home') target = 0;
        if (event.key === 'End') target = tabs.length - 1;
        if (target !== undefined) { event.preventDefault(); activateTab(tabs[target].dataset.dashboardTab, true); }
      });
    });

    const departments = $$('[data-dashboard-department]');
    const search = $('[data-dashboard-department-search]');
    const sort = $('[data-dashboard-department-sort]');
    function filterDepartments() {
      if (!search || !sort) return;
      const query = String(state.departmentSearch || '').trim().toLocaleLowerCase();
      departments.sort((a, b) => {
        const field = {spend: 'spend', pending: 'pending', activity: 'activity'}[state.departmentSort];
        const difference = field ? Number(b.dataset[field]) - Number(a.dataset[field]) : 0;
        return difference || a.dataset.name.localeCompare(b.dataset.name);
      });
      const matches = departments.filter(row => row.dataset.name.toLocaleLowerCase().includes(query) && (state.departmentScope !== 'active' || Number(row.dataset.activity) > 0));
      const matched = new Set(matches);
      let shown = 0;
      departments.forEach(row => {
        row.hidden = !matched.has(row) || (!state.allDepartments && shown >= 4);
        if (!row.hidden) shown++;
        $('.dashboard-department-list').appendChild(row);
      });
      $('[data-dashboard-department-empty]').hidden = matches.length > 0;
      $('[data-dashboard-department-count]').textContent = `${matches.length} of ${departments.length} departments`;
      const more = $('[data-dashboard-department-more]');
      more.hidden = matches.length <= 4;
      more.textContent = state.allDepartments ? 'Show fewer departments' : `Show all ${matches.length} departments`;
      $$('[data-dashboard-department-scope]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.dashboardDepartmentScope === state.departmentScope)));
    }
    departments.forEach(row => {
      row.open = Boolean(state.openDepartments[row.dataset.dashboardDepartment]);
      row.addEventListener('toggle', () => {
        if (!dashboard.isConnected) return;
        state.openDepartments[row.dataset.dashboardDepartment] = row.open;
        save();
      });
    });
    if (search && sort) {
      search.value = state.departmentSearch;
      sort.value = ['activity', 'spend', 'pending', 'name'].includes(state.departmentSort) ? state.departmentSort : 'activity';
      state.departmentSort = sort.value;
      search.addEventListener('input', () => { state.departmentSearch = search.value; state.allDepartments = false; filterDepartments(); save(); });
      sort.addEventListener('change', () => { state.departmentSort = sort.value; filterDepartments(); save(); });
      $$('[data-dashboard-department-scope]').forEach(button => button.addEventListener('click', () => { state.departmentScope = button.dataset.dashboardDepartmentScope; state.allDepartments = false; filterDepartments(); save(); }));
      $('[data-dashboard-department-more]').addEventListener('click', () => { state.allDepartments = !state.allDepartments; filterDepartments(); save(); });
    }

    const attention = $$('[data-dashboard-attention-item]');
    function filterAttention() {
      if (!$('[data-dashboard-attention-empty]')) return;
      const matches = attention.filter(row => state.priority === 'all' || row.dataset.priority === state.priority);
      attention.forEach(row => row.hidden = !matches.includes(row) || (!state.allAttention && matches.indexOf(row) >= 3));
      $('[data-dashboard-attention-empty]').hidden = matches.length > 0;
      $$('[data-dashboard-priority]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.dashboardPriority === state.priority)));
      const more = $('[data-dashboard-attention-more]');
      more.hidden = matches.length <= 3;
      more.textContent = state.allAttention ? 'Show fewer items' : `Show all ${matches.length} items`;
    }
    $$('[data-dashboard-priority]').forEach(button => button.addEventListener('click', () => { state.priority = button.dataset.dashboardPriority; state.allAttention = false; filterAttention(); save(); }));
    $('[data-dashboard-attention-more]')?.addEventListener('click', () => { state.allAttention = !state.allAttention; filterAttention(); save(); });

    $('[data-dashboard-privacy]').addEventListener('click', () => { state.private = !state.private; applyPrivacy(); save(); announce(state.private ? 'Dashboard amounts hidden.' : 'Dashboard amounts visible.'); });
    $('[data-dashboard-focus]').addEventListener('click', () => { state.focus = !state.focus; applyFocus(); save(); announce(state.focus ? 'Focus view enabled.' : 'All dashboard sections visible.'); });
    $('[data-dashboard-exit-focus]').addEventListener('click', () => { state.focus = false; applyFocus(); save(); });
    $$('[data-dashboard-density]').forEach(button => button.addEventListener('click', () => { state.density = button.dataset.dashboardDensity; applyDensity(); save(); }));
    $$('[data-dashboard-jump]').forEach(button => button.addEventListener('click', () => {
      const section = document.getElementById(button.dataset.dashboardJump);
      if (!section) return;
      if (state.focus && (section.classList.contains('dashboard-secondary') || section.id === 'dashboard-activity')) { state.focus = false; applyFocus(); save(); }
      if (section.tagName === 'DETAILS') section.open = true;
      section.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
      const target = section.querySelector('summary, h2');
      if (target) { if (target.tagName !== 'SUMMARY') target.tabIndex = -1; target.focus({preventScroll: true}); }
    }));
    $('[data-dashboard-reset]').addEventListener('click', () => {
      Object.assign(state, defaults());
      $$('[data-dashboard-section]').forEach(section => section.open = state.sections[section.dataset.dashboardSection]);
      departments.forEach(row => row.open = false);
      if (search) search.value = '';
      if (sort) sort.value = 'activity';
      activateTab('today'); applyPrivacy(); applyFocus(); applyDensity(); filterDepartments(); filterAttention(); save();
      $('.dashboard-display-menu').open = false;
      announce('Dashboard view reset.');
    });
    $('[data-dashboard-refresh]').addEventListener('click', async event => {
      const button = event.currentTarget;
      if (button.disabled || !refresh) return;
      button.disabled = true; button.setAttribute('aria-busy', 'true');
      $('[data-dashboard-freshness]').textContent = 'Refreshing…';
      announce('Refreshing dashboard.');
      try {
        const updated = await refresh();
        if (updated !== false) document.querySelector('[data-dashboard-announcement]')?.replaceChildren(document.createTextNode('Dashboard refreshed.'));
      } catch {
        if (dashboard.isConnected) { $('[data-dashboard-freshness]').textContent = 'Refresh unavailable'; announce('Could not refresh. Try again.'); }
      } finally { button.disabled = false; button.removeAttribute('aria-busy'); }
    });

    const updated = new Date();
    $('[data-dashboard-freshness]').textContent = `Updated ${updated.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
    $('[data-dashboard-freshness]').title = updated.toLocaleString();
    activateTab(state.tab); applyPrivacy(); applyFocus(); applyDensity(); filterDepartments(); filterAttention();
  }

  document.addEventListener('click', event => {
    document.querySelectorAll('.dashboard-display-menu[open]').forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') document.querySelectorAll('.dashboard-display-menu[open]').forEach(menu => { menu.open = false; menu.querySelector('summary').focus(); });
  });
  window.SAGEDashboard = {init};
})();
