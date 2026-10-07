// MODULE: SAGE Authentication UI
// Handles dark/light mode, multi-step owner registration, controlled staff registration, API submission and the sleek launch transition.

(() => {
  const root = document.documentElement;
  const savedTheme = localStorage.getItem('sage-theme') || localStorage.getItem('vision-theme') || 'dark';
  root.dataset.theme = savedTheme;

  // ========================================================
  // SHARED AUTH UI
  // ========================================================
  document.querySelector('#authTheme')?.addEventListener('click', () => { const next = root.dataset.theme === 'dark' ? 'light' : 'dark'; root.dataset.theme = next; localStorage.setItem('sage-theme', next); });
  document.querySelectorAll('[data-toggle-password]').forEach(button => button.addEventListener('click', () => { const input = button.closest('.password-field')?.querySelector('input'); if (input) input.type = input.type === 'password' ? 'text' : 'password'; }));
  document.querySelectorAll('[data-coming-soon]').forEach(link => link.addEventListener('click', e => { e.preventDefault(); setMessage(document.querySelector('#loginMessage'), 'Password recovery will be connected in the next authentication phase.', 'info'); }));

  function setMessage(target, message = '', tone = 'error') { if (!target) return; target.textContent = message; target.className = `form-message ${message ? `show ${tone}` : ''}`; }
  function formObject(form) { return Object.fromEntries(new FormData(form).entries()); }
  async function postJSON(url, payload) { const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify(payload) }); const data = await response.json().catch(() => ({ ok: false, message: 'Unexpected server response.' })); if (!response.ok || !data.ok) throw new Error(data.message || `Request failed (${response.status})`); return data; }
  function setBusy(button, busy, text = 'Please wait...') { if (!button) return; if (busy) { button.dataset.originalText = button.innerHTML; button.disabled = true; button.innerHTML = `<span class="button-spinner"></span>${text}`; } else { button.disabled = false; button.innerHTML = button.dataset.originalText || button.innerHTML; } }

  // ========================================================
  // LOGIN
  // ========================================================
  const loginForm = document.querySelector('#loginForm');
  loginForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const button = loginForm.querySelector('button[type="submit"]'), message = document.querySelector('#loginMessage'), payload = formObject(loginForm);
    payload.remember = Boolean(loginForm.querySelector('[name="remember"]')?.checked);
    setMessage(message); setBusy(button, true, 'Signing in...');
    try { const data = await postJSON('/api/auth/login', payload); window.location.href = data.redirect || '/dashboard'; }
    catch (error) { setMessage(message, error.message); setBusy(button, false); }
  });

  // ========================================================
  // OWNER REGISTRATION - ADAPTIVE ORGANIZATION / INDIVIDUAL WORKSPACE
  // ========================================================
  const registerForm = document.querySelector('#registerForm'), registerSteps = [...document.querySelectorAll('.register-step')], stepNav = [...document.querySelectorAll('[data-step-nav]')], businessType = document.querySelector('#businessType'), individualBusinessType = document.querySelector('#individualBusinessType'), departmentSelector = document.querySelector('#departmentSelector'), selectionSummary = document.querySelector('#departmentSelectionSummary'), templateSummary = document.querySelector('#departmentTemplateSummary'), businessTypes = window.SAGE_BUSINESS_TYPES || [], individualTypes = window.SAGE_INDIVIDUAL_BUSINESS_TYPES || [];
  let currentStep = 1, selectedDepartments = [];
  function selectedWorkspaceMode() { return registerForm?.querySelector('[name="workspace_mode"]:checked')?.value || 'organization'; }
  function showStep(step) { currentStep=Math.max(1,Math.min(step,registerSteps.length)); registerSteps.forEach(section=>section.classList.toggle('active',Number(section.dataset.step)===currentStep)); stepNav.forEach(button=>{const index=Number(button.dataset.stepNav);button.classList.toggle('active',index===currentStep);button.classList.toggle('complete',index<currentStep);}); document.querySelector('.owner-register-panel')?.scrollTo({top:0,behavior:'smooth'}); }
  function validateCurrentStep() { const section=document.querySelector(`.register-step[data-step="${currentStep}"]`); if(!section)return true; for(const input of [...section.querySelectorAll('[required]')]){if(input.closest('[hidden]')||input.closest('[data-organization-structure][hidden]')||input.closest('[data-individual-structure][hidden]'))continue;if(!input.checkValidity()){input.reportValidity();input.focus();return false;}} return true; }
  document.querySelectorAll('[data-next-step]').forEach(button=>button.addEventListener('click',()=>{if(validateCurrentStep())showStep(currentStep+1);})); document.querySelectorAll('[data-prev-step]').forEach(button=>button.addEventListener('click',()=>showStep(currentStep-1)));

  // Workspace mode determines business fields, department onboarding and launch language.
  function syncWorkspaceMode() {
    const mode=selectedWorkspaceMode(), individual=mode==='individual'; if(registerForm)registerForm.dataset.workspaceMode=mode; document.querySelectorAll('.workspace-mode-card').forEach(card=>card.classList.toggle('selected',card.querySelector('input')?.checked));
    const orgType=document.querySelector('[data-organization-business-type]'), individualType=document.querySelector('[data-individual-business-type]'), orgStructure=document.querySelector('[data-organization-structure]'), individualStructure=document.querySelector('[data-individual-structure]'), branchField=document.querySelector('[data-branch-field]'), sizeField=document.querySelector('[data-size-field]');
    const toggleWorkspaceField=(element,show)=>{if(!element)return;element.hidden=!show;element.classList.toggle('workspace-field-hidden',!show);element.setAttribute('aria-hidden',show?'false':'true');};
    toggleWorkspaceField(orgType,!individual);toggleWorkspaceField(individualType,individual);toggleWorkspaceField(orgStructure,!individual);toggleWorkspaceField(individualStructure,individual);toggleWorkspaceField(branchField,!individual);toggleWorkspaceField(sizeField,!individual);
    if(businessType){businessType.required=!individual;businessType.disabled=individual;}if(individualBusinessType){individualBusinessType.required=individual;individualBusinessType.disabled=!individual;}const branchInput=branchField?.querySelector('input'),sizeSelect=sizeField?.querySelector('select');if(branchInput)branchInput.disabled=individual;if(sizeSelect)sizeSelect.disabled=individual;
    const title=document.querySelector('[data-business-step-title]'),copy=document.querySelector('[data-business-step-copy]'),nameLabel=document.querySelector('[data-business-name-label]'),buttonLabel=document.querySelector('[data-structure-button-label]'),finalLabel=document.querySelector('[data-final-step-label]'),terms=document.querySelector('[data-terms-label]');
    if(title)title.textContent=individual?'Your business information':'Organization information'; if(copy)copy.textContent=individual?'Tell SAGE what kind of owner-operated business you run so your dashboard and tools fit your work.':'This determines your suggested departments and default workspace structure.'; if(nameLabel)nameLabel.textContent=individual?'Business / trading name':'Organization / Business name'; if(buttonLabel)buttonLabel.textContent=individual?'Review business setup':'Choose departments'; if(finalLabel)finalLabel.textContent=individual?'Setup':'Structure'; if(terms)terms.textContent=individual?'I confirm that I am creating this SAGE workspace for my business.':'I confirm that I am authorized to create this organization workspace.';
  }
  registerForm?.querySelectorAll('[name="workspace_mode"]').forEach(input=>input.addEventListener('change',syncWorkspaceMode)); syncWorkspaceMode();

  // Organization workspace: business type instantly seeds a complete, removable department template.
  function activeBusinessTemplate(){return businessTypes.find(entry=>entry.key===businessType?.value)||businessTypes[0]||{label:'Custom organization',departments:[]};}
  function departmentSuggestions(){return [...(activeBusinessTemplate().departments||[])];}
  function updateDepartmentSummary(){const selected=selectedDepartments.filter(item=>item.selected).length,suggested=selectedDepartments.filter(item=>!item.custom).length,custom=selectedDepartments.filter(item=>item.custom).length,template=activeBusinessTemplate();if(selectionSummary)selectionSummary.textContent=`${selected} department${selected===1?'':'s'} selected`;if(templateSummary)templateSummary.textContent=`${template.label||'Organization'} · ${suggested} suggested${custom?` · ${custom} custom`:''}`;}
  function renderDepartments(reset=false){if(!departmentSelector)return;if(reset||!selectedDepartments.length){const custom=reset?selectedDepartments.filter(item=>item.custom):[],customNames=new Set(custom.map(item=>item.name.toLowerCase()));selectedDepartments=departmentSuggestions().filter(name=>!customNames.has(name.toLowerCase())).map(name=>({name,selected:true,custom:false})).concat(custom);}departmentSelector.innerHTML=selectedDepartments.map((item,index)=>`<label class="department-choice ${item.selected?'selected':''}"><input type="checkbox" data-department-index="${index}" ${item.selected?'checked':''}><span class="department-choice-check"><svg><use href="#i-check"></use></svg></span><strong>${escapeHTML(item.name)}</strong>${item.custom?'<small>Custom department</small>':'<small>Suggested</small>'}</label>`).join('');updateDepartmentSummary();}
  businessType?.addEventListener('change',()=>renderDepartments(true)); departmentSelector?.addEventListener('change',event=>{const input=event.target.closest('[data-department-index]');if(!input)return;const index=Number(input.dataset.departmentIndex);selectedDepartments[index].selected=input.checked;input.closest('.department-choice')?.classList.toggle('selected',input.checked);updateDepartmentSummary();}); document.querySelector('#selectAllDepartments')?.addEventListener('click',()=>{selectedDepartments.forEach(item=>item.selected=true);renderDepartments(false);}); document.querySelector('#clearAllDepartments')?.addEventListener('click',()=>{selectedDepartments.forEach(item=>item.selected=false);renderDepartments(false);}); document.querySelector('#addCustomDepartment')?.addEventListener('click',()=>{const input=document.querySelector('#customDepartmentInput'),name=input?.value.trim();if(!name)return input?.focus();const existing=selectedDepartments.find(item=>item.name.toLowerCase()===name.toLowerCase());if(existing)existing.selected=true;else selectedDepartments.push({name,selected:true,custom:true});input.value='';renderDepartments(false);}); document.querySelector('#customDepartmentInput')?.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();document.querySelector('#addCustomDepartment')?.click();}}); renderDepartments(true);

  // App-like launch transition adapts its status copy to the selected workspace type.
  function launchWorkspace(data,staffMode=false){const overlay=document.querySelector('#registrationSuccess'),status=document.querySelector('#launchStatus'),title=document.querySelector('#launchTitle');if(!overlay)return window.location.href=data.redirect||'/dashboard';if(staffMode&&status)status.textContent=`Connecting you to ${data.department||'your department'}...`;if(!staffMode&&title)title.textContent=`Welcome to ${data.organization||'SAGE'}`;overlay.classList.add('open');overlay.setAttribute('aria-hidden','false');const individual=selectedWorkspaceMode()==='individual',messages=staffMode?['Applying department permissions...','Preparing your secure workspace...','Opening SAGE...']:(individual?['Creating your private business workspace...','Preparing finance, stock and reporting tools...','Applying owner controls...','Opening your business dashboard...']:['Creating organization structure...','Adding selected departments...','Applying owner permissions...','Opening your workspace...']);let index=0;const timer=setInterval(()=>{if(status)status.textContent=messages[index++%messages.length];},520);setTimeout(()=>{clearInterval(timer);window.location.href=data.redirect||'/dashboard';},staffMode?1900:2400);}

  registerForm?.addEventListener('submit',async event=>{event.preventDefault();if(!validateCurrentStep())return;const button=registerForm.querySelector('button[type="submit"]'),message=document.querySelector('#registerMessage'),payload=formObject(registerForm),individual=selectedWorkspaceMode()==='individual';payload.workspace_mode=selectedWorkspaceMode();payload.departments=individual?[]:selectedDepartments.filter(item=>item.selected).map(item=>item.name);if(!individual&&!payload.departments.length)return setMessage(message,'Select or add at least one department.');setMessage(message);setBusy(button,true,'Creating workspace...');try{const data=await postJSON('/api/auth/register-owner',payload);launchWorkspace(data,false);}catch(error){setMessage(message,error.message);setBusy(button,false);}});

  // ========================================================
  // STAFF INVITATION REGISTRATION
  // ========================================================
  const staffForm = document.querySelector('#staffRegisterForm');
  staffForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const button = staffForm.querySelector('button[type="submit"]'), message = document.querySelector('#staffRegisterMessage'), token = staffForm.dataset.token;
    setMessage(message); setBusy(button, true, 'Activating account...');
    try { const data = await postJSON(`/api/auth/register-staff/${encodeURIComponent(token)}`, formObject(staffForm)); launchWorkspace(data, true); }
    catch (error) { setMessage(message, error.message); setBusy(button, false); }
  });

  function escapeHTML(value) { return String(value).replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char])); }
})();
