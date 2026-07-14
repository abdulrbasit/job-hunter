// ── State ──
let allApps = [];
let filteredApps = [];
let appPage = 1;
let appPageData = { total: 0, page: 1, page_size: 50, pages: 1 };
let activeStatus = '';
let activeSlug = null;
let selectedAppSlugs = new Set();
let sortCol = 'date';
let sortDir = -1; // -1 = desc
let insightsLoaded = false;
let analyticsLoaded = false;
let activeArtifact = null;
let artifactObjectUrl = null;
let candidateData = { items: [], counts: { active: 0, discarded: 0, total: 0 }, page: 1, page_size: 50, pages: 1 };
let candidatePage = 1;
let candidateScope = 'active';
let selectedCandidateIds = new Set();
let activeCandidateId = null;
let settingsLoaded = false;
let cfgRevision = null;
let cfgRawRevision = null;
let careerContextRevision = null;
let cfgDirty = false;
let cfgRawDirty = false;
let careerContextDirty = false;
let loadingGuidedForm = false;
let loadingRaw = false;
let loadingCareerContext = false;
let regionRowSeq = 0;
let overrideRowSeq = 0;
let companiesLoaded = false;
let companiesData = [];
let companiesRevision = null;
let companyEnabledFilter = '';
let selectedCompanyUrls = new Set();
let editingCompanyUrl = null;
const COMPANY_RENDER_STEP = 500;
let companyRenderLimit = COMPANY_RENDER_STEP;
let catalogIndustriesLoaded = false;
let catalogPage = 1;
let catalogPageData = { items: [], total: 0, page: 1, page_size: 300, pages: 1, revision: null };
let catalogIndustry = '';
let catalogEnabledFilter = '';
let selectedCatalogIds = new Set();
let activeCatalogId = null;

function debounce(fn, delay=250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
const debouncedLoadApplications = debounce(() => { appPage = 1; loadApplications(); });
const debouncedLoadCandidates = debounce(() => { candidatePage = 1; loadUnprocessed(); });
const debouncedLoadCatalog = debounce(() => { catalogPage = 1; loadCatalogPage(); });

function loadingHtml(label='Loading…') {
  return `<div class="loading-wrap"><span class="spinner"></span> ${esc(label)}</div>`;
}
function emptyHtml(message) {
  return `<div class="no-data">${esc(message)}</div>`;
}
function errorHtml(message, nextAction='Retry, then run job-hunter doctor if the problem continues.') {
  return `<div class="no-data">${esc(message)} ${esc(nextAction)}</div>`;
}
function reportFailure(message, nextAction='Reload this view and retry.') {
  alert(`${message} ${nextAction}`);
}

function showToast(message) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

const MILESTONES = [
  { id: 'app_1', check: c => c.applications >= 1, message: '🎉 First application logged — nice start!' },
  { id: 'app_5', check: c => c.applications >= 5, message: '🎉 5 applications in — building momentum!' },
  { id: 'app_10', check: c => c.applications >= 10, message: '🎉 10 applications — great consistency!' },
  { id: 'app_25', check: c => c.applications >= 25, message: '🎉 25 applications — that is real persistence!' },
  { id: 'interview_1', check: c => c.interviews >= 1, message: '🎉 First interview scheduled — congratulations!' },
  { id: 'offer_1', check: c => c.offers >= 1, message: '🎉 First offer — huge milestone!' },
];

async function checkMilestones() {
  try {
    const [insights, seenResult] = await Promise.all([
      window.pywebview.api.get_insights(),
      window.pywebview.api.get_seen_milestones(),
    ]);
    const byStatus = insights.by_status || {};
    const counts = {
      applications: insights.total || 0,
      interviews: (byStatus.interview || 0) + (byStatus.offer || 0),
      offers: byStatus.offer || 0,
    };
    const seen = new Set(seenResult.seen || []);
    for (const m of MILESTONES) {
      if (!seen.has(m.id) && m.check(counts)) {
        showToast(m.message);
        await window.pywebview.api.mark_milestone_seen(m.id);
        seen.add(m.id);
      }
    }
  } catch(_) { /* milestones are a nice-to-have — never block the save flow */ }
}

// ── Init ──
window.addEventListener('pywebviewready', () => { initAll(); });
// fallback if event already fired
if (window.pywebview) setTimeout(initAll, 100);

async function initAll() {
  try {
    const name = await window.pywebview.api.get_user_name();
    if (name) document.getElementById('sidebar-name').textContent = name;
  } catch(_) {}
  const setup = await loadOnboarding();
  if (setupIncomplete(setup)) {
    document.querySelector('.nav-btn[data-view="get-started"]').click();
  }
  await loadApplicationStreak();
  await refreshAll();
  runSync({ silent: true }); // auto-sync on open — merge is lossless by construction, safe unattended
}

// Schedule and permissions are optional polish — they never force the Get Started landing.
const OPTIONAL_SETUP_IDS = new Set(['workflow_schedule', 'outputs_writable']);

function setupIncomplete(checklist) {
  if (!checklist || !checklist.ok) return false;
  return (checklist.items || []).some(item => !item.done && !OPTIONAL_SETUP_IDS.has(item.id));
}

async function loadApplicationStreak() {
  const badge = document.getElementById('streak-badge');
  try {
    const result = await window.pywebview.api.get_application_streak();
    if (!result.ok || result.current_streak < 1) { badge.style.display = 'none'; return; }
    badge.textContent = `🔥 ${result.current_streak}-day streak`;
    badge.title = `Longest streak: ${result.longest_streak} day(s)`;
    badge.style.display = '';
  } catch(_) {
    badge.style.display = 'none';
  }
}

let todayHuntPolling = false;

function renderTodayHuntStatus(result) {
  const label = { idle: 'Idle', running: 'Running…', succeeded: 'Done', failed: 'Failed' }[result.status] || result.status;
  document.getElementById('today-hunt-status-value').textContent = label;
  document.getElementById('find-jobs-btn').disabled = result.status === 'running';
  document.getElementById('today-hunt-fetched').textContent = result.fetched ?? '—';
  document.getElementById('today-hunt-candidates').textContent = result.candidates ?? '—';
  document.getElementById('today-hunt-tailored').textContent = result.tailored ?? '—';
  const messageEl = document.getElementById('today-hunt-message');
  if (result.status === 'succeeded' || result.status === 'failed') {
    messageEl.textContent = `${result.message || ''} ${result.next_action || ''}`.trim();
    messageEl.style.display = '';
  } else {
    messageEl.style.display = 'none';
  }
}

async function loadTodayHuntStatus() {
  const result = await window.pywebview.api.get_hunt_status();
  renderTodayHuntStatus(result);
  if (result.status === 'running') pollTodayHuntStatus();
}

async function pollTodayHuntStatus() {
  if (todayHuntPolling) return;
  todayHuntPolling = true;
  try {
    while (true) {
      const result = await window.pywebview.api.get_hunt_status();
      renderTodayHuntStatus(result);
      if (result.status !== 'running') {
        if (result.status === 'succeeded') refreshAll();
        break;
      }
      await new Promise(r => setTimeout(r, 2000));
    }
  } finally {
    todayHuntPolling = false;
  }
}

async function findJobs() {
  const result = await window.pywebview.api.start_hunt();
  if (!result.ok) { reportFailure(result.error || 'Could not start the hunt.'); return; }
  pollTodayHuntStatus();
}

// ── Sync — merges and pushes outputs/state/jobs.db without the user ever touching git ──
let syncPolling = false;

async function runSync({ silent } = {}) {
  const result = await window.pywebview.api.start_sync();
  if (!result.ok) {
    // A hunt or another sync is already running — try again once it finishes.
    if (!silent) showToast(result.error || 'Could not start sync.');
    return;
  }
  pollSyncStatus(silent);
}

async function pollSyncStatus(silent) {
  if (syncPolling) return;
  syncPolling = true;
  const btn = document.getElementById('sync-btn');
  btn.disabled = true;
  btn.textContent = '⇅ Syncing…';
  try {
    while (true) {
      const result = await window.pywebview.api.get_sync_status();
      if (result.status !== 'running') {
        if (result.status === 'succeeded') {
          const inserted = result.inserted || 0;
          const updated = result.updated || 0;
          const deleted = result.deleted || 0;
          const changed = inserted + updated + deleted;
          const parts = [];
          if (inserted) parts.push(`${inserted} new`);
          if (updated) parts.push(`${updated} updated`);
          if (deleted) parts.push(`${deleted} removed`);
          if (!silent || changed > 0) showToast(changed ? `Synced — ${parts.join(', ')}` : 'Synced');
          if (changed) refreshAll();
        } else if (result.status === 'failed' && !silent) {
          showToast(result.error || 'Sync failed.');
        }
        break;
      }
      await new Promise(r => setTimeout(r, 2000));
    }
  } finally {
    syncPolling = false;
    btn.disabled = false;
    btn.textContent = '⇅ Sync';
  }
}

function checklistItemsHtml(items) {
  return items.map(item => `
    <li class="onboarding-item ${item.done ? 'done' : ''}">
      <span class="oi-mark">${item.done ? '✓' : '○'}</span>
      <span>${esc(item.label)}</span>
      <span class="oi-hint">— ${esc(item.action_hint)}</span>
    </li>
  `).join('');
}

// One fetch feeds both setup surfaces: the slim topbar pill and the Get Started checklist.
async function loadOnboarding() {
  const banner = document.getElementById('onboarding-banner');
  const checklistEl = document.getElementById('gs-checklist');
  try {
    const result = await window.pywebview.api.get_onboarding_checklist();
    if (!result.ok) {
      banner.textContent = `${result.error || 'Setup status is unavailable.'} ${result.next_action || ''}`;
      banner.style.display = '';
      return result;
    }
    checklistEl.innerHTML = checklistItemsHtml(result.items) || '<li class="no-data">All setup checks pass.</li>';
    if (result.done_count >= result.total_count) {
      banner.style.display = 'none';
      return result;
    }
    banner.innerHTML = `<div class="onboarding-progress">Setup: ${result.done_count} of ${result.total_count} done — <a href="#" id="finish-setup-link">Finish setup →</a></div>`;
    document.getElementById('finish-setup-link').addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelector('.nav-btn[data-view="get-started"]').click();
    });
    banner.style.display = '';
    return result;
  } catch(_) {
    banner.textContent = 'Setup status is unavailable. Run job-hunter doctor in the workspace.';
    banner.style.display = '';
    return null;
  }
}

async function loadDiagnosticsChecklist() {
  const el = document.getElementById('diag-checklist');
  try {
    const result = await window.pywebview.api.get_onboarding_checklist();
    if (!result.ok) {
      el.innerHTML = errorHtml(result.error || 'Setup status is unavailable.', result.next_action || '');
      return;
    }
    el.innerHTML = checklistItemsHtml(result.items) || '<li class="no-data">All setup checks pass.</li>';
  } catch(_) {
    el.innerHTML = errorHtml('Setup status is unavailable.', 'Run job-hunter doctor in the workspace.');
  }
}

// ── Navigation ──
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const view = btn.dataset.view;
    const currentView = document.querySelector('.nav-btn.active')?.dataset.view;
    // Get Started's quick fill writes into the Settings editors, so both views share the guard.
    const editViews = ['settings', 'get-started'];
    if (editViews.includes(currentView) && !editViews.includes(view) && settingsHasUnsavedChanges() &&
        !confirm('You have unsaved Settings changes. Leave without saving?')) {
      return;
    }
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-' + view).classList.add('active');
    document.getElementById('view-title').textContent = btn.querySelector('.nav-label').textContent;
    if (view === 'unprocessed') loadUnprocessed();
    if (view === 'company-hunt') refreshCompanyHuntPanel();
    if (view === 'insights' && !insightsLoaded) loadInsights();
    if (view === 'settings' && !settingsLoaded) loadSettings();
    if (view === 'get-started') loadGetStarted();
  });
});

// Company enabled/disabled filter tabs
document.querySelectorAll('#company-filter-tabs .status-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('#company-filter-tabs .status-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    companyEnabledFilter = tab.dataset.companyFilter;
    renderCompanies();
  });
});

// Shared Catalog enabled/disabled filter tabs
document.querySelectorAll('#catalog-filter-tabs .status-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('#catalog-filter-tabs .status-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    catalogEnabledFilter = tab.dataset.catalogFilter;
    catalogPage = 1;
    loadCatalogPage();
  });
});

document.getElementById('companies-tbody').addEventListener('click', (e) => {
  const editBtn = e.target.closest('[data-edit-url]');
  const deleteBtn = e.target.closest('[data-delete-url]');
  const openLink = e.target.closest('[data-open-url]');
  const showMoreBtn = e.target.closest('[data-show-more-companies]');
  if (editBtn) startEditCompany(editBtn.dataset.editUrl);
  if (deleteBtn) deleteCompanyByUrl(deleteBtn.dataset.deleteUrl);
  if (openLink) { e.preventDefault(); openCareerPage(openLink.dataset.openUrl); }
  if (showMoreBtn) showMoreCompanies();
});

document.getElementById('companies-tbody').addEventListener('change', (e) => {
  if (e.target.classList.contains('company-checkbox')) {
    toggleCompanySelected(e.target.dataset.url, e.target.checked);
  }
});

document.getElementById('catalog-tbody').addEventListener('change', (e) => {
  if (e.target.classList.contains('catalog-checkbox')) {
    toggleCatalogSelected(e.target.dataset.id, e.target.checked);
  }
});

document.getElementById('catalog-tbody').addEventListener('click', (e) => {
  const row = e.target.closest('tr[data-id]');
  if (!row) return;
  const openLink = e.target.closest('[data-open-url]');
  if (openLink) { e.preventDefault(); openCatalogCompany(row.dataset.id); return; }
  if (e.target.closest('.catalog-checkbox')) return;
  openCatalogDetail(row.dataset.id);
});

document.getElementById('catalog-pager').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-page-delta]');
  if (btn && !btn.disabled) changeCatalogPage(Number(btn.dataset.pageDelta));
});

document.getElementById('catdp-link').addEventListener('click', (e) => {
  e.preventDefault();
  if (activeCatalogId != null) openCatalogCompany(activeCatalogId);
});

// Settings sub-tabs
document.querySelectorAll('#settings-tabs .status-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('#settings-tabs .status-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`settings-panel-${tab.dataset.settingsTab}`).classList.add('active');
    clearSettingsMessages();
    if (tab.dataset.settingsTab === 'diagnostics') {
      loadDiagnosticsChecklist();
      loadTodayHuntStatus();
      if (!analyticsLoaded) loadAnalytics();
    }
  });
});

// Status tab filter
document.querySelectorAll('#status-tabs .status-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('#status-tabs .status-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    activeStatus = tab.dataset.status;
    applyFilters();
  });
});

document.querySelectorAll('[data-candidate-scope]').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('[data-candidate-scope]').forEach(button => button.classList.remove('active'));
    tab.classList.add('active');
    candidateScope = tab.dataset.candidateScope;
    selectedCandidateIds.clear();
    candidatePage = 1;
    loadUnprocessed();
  });
});

// Company Hunt sub-tabs: Run Hunt / Manage Companies — split so each view has one job
// instead of stacking the run panel, results table, and full company CRUD list together.
document.querySelectorAll('#company-hunt-subtabs .status-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('#company-hunt-subtabs .status-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const isManage = tab.dataset.companyHuntView === 'manage';
    document.getElementById('company-hunt-run-view').style.display = isManage ? 'none' : 'flex';
    document.getElementById('company-hunt-manage-view').style.display = isManage ? 'flex' : 'none';
    if (isManage && !companiesLoaded) loadCompanies();
  });
});

// My Companies / Shared Catalog sub-tabs within Manage Companies
document.querySelectorAll('#companies-view-tabs .status-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('#companies-view-tabs .status-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const isCatalog = tab.dataset.companiesView === 'catalog';
    document.getElementById('companies-mine-view').style.display = isCatalog ? 'none' : '';
    document.getElementById('companies-catalog-view').style.display = isCatalog ? '' : 'none';
    if (isCatalog) {
      if (!catalogIndustriesLoaded) loadCatalogIndustries();
      loadCatalogPage();
    }
  });
});

// Delegated row/button handlers (tbody markup is untrusted scrape data — no
// per-row inline onclick/onchange string interpolation; identifiers travel via
// data-* attributes read here instead).
document.getElementById('app-tbody').addEventListener('click', (e) => {
  if (e.target.classList.contains('app-checkbox')) return;
  const row = e.target.closest('tr[data-slug]');
  if (row) selectApp(row.dataset.slug);
});

document.getElementById('app-tbody').addEventListener('change', (e) => {
  if (e.target.classList.contains('app-checkbox')) {
    toggleAppSelected(e.target.dataset.slug, e.target.checked);
  }
});

document.getElementById('unprocessed-tbody').addEventListener('click', (e) => {
  const deleteBtn = e.target.closest('[data-delete-id]');
  if (deleteBtn) { deleteUnprocessed(Number(deleteBtn.dataset.deleteId)); return; }
  if (e.target.closest('.candidate-checkbox') || e.target.closest('a')) return;
  const row = e.target.closest('tr[data-id]');
  if (row) openCandidateDetail(Number(row.dataset.id));
});

document.getElementById('unprocessed-tbody').addEventListener('change', (e) => {
  if (e.target.classList.contains('candidate-checkbox')) {
    toggleCandidateSelected(Number(e.target.dataset.id), e.target.checked);
  }
});

// Static button/control wiring — was inline onclick=/oninput=/onchange= before
// CSP script-src dropped 'unsafe-inline'; ids below are 1:1 with the removed attributes.
[
  ['refresh-btn', refreshAll],
  ['sync-btn', () => runSync({ silent: false })],
  ['find-jobs-btn', findJobs],
  ['app-bulk-delete-btn', bulkDeleteApplications],
  ['dp-close-btn', closeDetail],
  ['cdp-close-btn', closeCandidateDetail],
  ['cdp-delete-btn', deleteCandidateDetail],
  ['dp-save-status-btn', saveStatus],
  ['dp-copy-artifact', copyArtifact],
  ['dp-open-artifact', openArtifact],
  ['dp-open-folder-btn', openJobFolder],
  ['dp-delete-btn', deleteApp],
  ['discard-selected-btn', discardSelected],
  ['run-company-hunt-btn', runCompanyHunt],
  ['company-form-submit', submitCompanyForm],
  ['company-form-cancel', cancelCompanyForm],
  ['company-bulk-delete-btn', bulkDeleteCompanies],
  ['company-bulk-enable-btn', () => bulkSetCompaniesEnabled(true)],
  ['company-bulk-disable-btn', () => bulkSetCompaniesEnabled(false)],
  ['catalog-bulk-enable-btn', () => bulkSetCatalogEnabled(true)],
  ['catalog-bulk-disable-btn', () => bulkSetCatalogEnabled(false)],
  ['catalog-enable-shown-btn', () => setCatalogShownEnabled(true)],
  ['catalog-disable-shown-btn', () => setCatalogShownEnabled(false)],
  ['catdp-close-btn', closeCatalogDetail],
  ['catdp-toggle-btn', toggleCatalogDetailEnabled],
  ['open-career-pages-btn', openCareerPagesFile],
  ['open-config-folder-btn', openConfigFolder],
  ['undo-career-pages-btn', undoCareerPages],
  ['add-region-btn', () => addRegionRow()],
  ['add-override-btn', () => addOverrideRow()],
  ['settings-save-guided', saveGuidedConfig],
  ['undo-guided-config-btn', undoJobHunterConfig],
  ['save-raw-config-btn', saveRawConfig],
  ['undo-raw-config-btn', undoJobHunterConfig],
  ['save-career-context-btn', saveCareerContext],
  ['undo-career-context-btn', undoCareerContext],
  ['save-search-setup-btn', saveSearchSetup],
  ['copy-onboarding-prompt-btn', copyOnboardingPrompt],
  ['import-chatbot-bundle-btn', importChatbotBundle],
  ['apply-quick-career-context-btn', applyQuickCareerContext],
  ['save-api-key-btn', saveApiKey],
  ['gs-recheck-btn', loadGetStartedActionsGuide],
].forEach(([id, handler]) => document.getElementById(id).addEventListener('click', handler));

document.querySelectorAll('th[data-col]').forEach(th => {
  th.addEventListener('click', () => sortBy(th.dataset.col));
});

document.getElementById('dp-artifact-tabs').addEventListener('click', (e) => {
  const tab = e.target.closest('[data-artifact]');
  if (tab) selectArtifact(tab.dataset.artifact);
});

document.getElementById('search-input').addEventListener('input', debouncedLoadApplications);
document.getElementById('candidate-search').addEventListener('input', debouncedLoadCandidates);
document.getElementById('company-search').addEventListener('input', renderCompanies);
document.getElementById('catalog-search').addEventListener('input', debouncedLoadCatalog);
document.getElementById('catalog-industry-filter').addEventListener('change', () => {
  catalogIndustry = document.getElementById('catalog-industry-filter').value;
  catalogPage = 1;
  loadCatalogPage();
});

['cfg-mode', 'cfg-llm-provider'].forEach(id => {
  document.getElementById(id).addEventListener('change', markConfigDirty);
});
[
  'cfg-resume-tex', 'cfg-story-bank', 'cfg-career-context-path', 'cfg-latex-class',
  'cfg-profile-image', 'cfg-job-titles', 'cfg-excl-companies', 'cfg-excl-titles',
  'cfg-excl-languages', 'cfg-excl-industries', 'cfg-min-fit-score', 'cfg-max-years',
  'cfg-batch-size',
].forEach(id => {
  document.getElementById(id).addEventListener('input', markConfigDirty);
});
document.getElementById('settings-raw-yaml').addEventListener('input', markRawDirty);
document.getElementById('settings-career-context').addEventListener('input', markCareerContextDirty);

document.getElementById('app-select-all').addEventListener('change', (e) => toggleSelectAllApps(e.target.checked));
document.getElementById('candidate-select-all').addEventListener('change', (e) => toggleSelectAll(e.target.checked));
document.getElementById('company-select-all').addEventListener('change', (e) => toggleSelectAllCompanies(e.target.checked));
document.getElementById('catalog-select-all').addEventListener('change', (e) => toggleSelectAllCatalog(e.target.checked));

document.getElementById('candidate-pager').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-page-delta]');
  if (btn && !btn.disabled) changeCandidatePage(Number(btn.dataset.pageDelta));
});
document.getElementById('app-pager').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-page-delta]');
  if (btn && !btn.disabled) changeAppPage(Number(btn.dataset.pageDelta));
});

// ── Data loading ──
async function refreshAll() {
  if (settingsHasUnsavedChanges() && !confirm('You have unsaved Settings changes. Refreshing will discard them. Continue?')) {
    return;
  }
  insightsLoaded = false;
  analyticsLoaded = false;
  settingsLoaded = false;
  companiesLoaded = false;
  await loadApplications();
  const activeView = document.querySelector('.nav-btn.active')?.dataset.view;
  if (activeView === 'insights') await loadInsights();
  if (activeView === 'unprocessed') await loadUnprocessed();
  if (activeView === 'company-hunt') {
    await refreshCompanyHuntPanel();
    const manageActive = document.querySelector('#company-hunt-subtabs .status-tab.active')?.dataset.companyHuntView === 'manage';
    if (manageActive) await loadCompanies();
  }
  if (activeView === 'settings') {
    await loadSettings();
    if (document.querySelector('#settings-tabs .status-tab.active')?.dataset.settingsTab === 'diagnostics') {
      loadDiagnosticsChecklist();
      await loadTodayHuntStatus();
      await loadAnalytics();
    }
  }
  if (activeView === 'get-started') await loadGetStarted();
}

async function loadApplications() {
  try {
    const query = document.getElementById('search-input').value;
    const direction = sortDir === -1 ? 'desc' : 'asc';
    appPageData = await window.pywebview.api.get_applications(appPage, 50, query, activeStatus, sortCol, direction);
    // A delete can leave appPage past the new last page — step back once rather
    // than rendering an empty page while later pages still have rows.
    if (appPageData.total > 0 && appPage > appPageData.pages) {
      appPage = appPageData.pages;
      return loadApplications();
    }
    allApps = appPageData.items || [];
    filteredApps = allApps;
    appPage = appPageData.page;
    document.getElementById('total-count').textContent = appPageData.total;
    renderTable();
    renderAppPager();
  } catch(e) {
    document.getElementById('app-tbody').innerHTML = `<tr><td colspan="8">${errorHtml('Applications could not be loaded.')}</td></tr>`;
  }
}

let companyHuntPolling = false;
let companyHuntRunId = null;
let companyHuntCursor = 0;

function companyHuntRowHtml(task) {
  const statusLabel = { ok: 'Found', failed: "Couldn't check", skipped: 'Skipped', running: 'Checking…' }[task.status] || task.status;
  const detail = task.status === 'ok' ? String(task.jobs_inserted ?? 0)
    : task.status === 'skipped' ? 'recently checked'
    : esc(task.failure_reason || '');
  return `<tr><td>${esc(task.company_name || '')}</td><td>${statusLabel}</td><td>${detail}</td></tr>`;
}

function renderCompanyHuntSummary(summary) {
  const btn = document.getElementById('run-company-hunt-btn');
  const messageEl = document.getElementById('company-hunt-message');
  const run = summary.run;

  document.getElementById('ch-checked').textContent = run ? `${(run.succeeded || 0) + (run.failed || 0)} / ${run.total || 0}` : '—';
  document.getElementById('ch-found').textContent = run ? (run.jobs_inserted ?? 0) : '—';
  document.getElementById('ch-issues').textContent = run ? (run.failed ?? 0) : '—';

  if (summary.running) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> Checking…`;
  } else {
    btn.disabled = false;
    btn.textContent = 'Run Company Hunt';
  }

  if (run && (run.status === 'error' || (run.status === 'done' && summary.message))) {
    messageEl.textContent = summary.message || 'Something went wrong.';
    messageEl.style.display = '';
  } else {
    messageEl.style.display = 'none';
  }
}

// Appends only tasks finished since companyHuntCursor — never re-renders the whole
// table, so a 2,000-company run doesn't repaint 2,000 rows on every 2s poll.
async function appendCompanyHuntUpdates() {
  if (!companyHuntRunId) return;
  const result = await window.pywebview.api.get_company_hunt_updates(companyHuntRunId, companyHuntCursor);
  if (!result.tasks.length) return;
  companyHuntCursor = result.cursor;
  const tbody = document.getElementById('company-hunt-tbody');
  if (tbody.querySelector('.no-data')) tbody.innerHTML = '';
  tbody.insertAdjacentHTML('beforeend', result.tasks.map(companyHuntRowHtml).join(''));
}

async function refreshCompanyHuntPanel() {
  try {
    const summary = await window.pywebview.api.get_company_hunt_summary();
    renderCompanyHuntSummary(summary);
    companyHuntRunId = summary.run ? summary.run.id : null;
    companyHuntCursor = 0;
    if (summary.run) {
      document.getElementById('company-hunt-tbody').innerHTML = '';
      await appendCompanyHuntUpdates();
    } else {
      document.getElementById('company-hunt-tbody').innerHTML = '<tr><td colspan="3"><div class="no-data">Click "Run Company Hunt" to check your configured career pages.</div></td></tr>';
    }
    if (summary.running) pollCompanyHuntStatus();
  } catch(e) {
    document.getElementById('company-hunt-tbody').innerHTML = `<tr><td colspan="3">${errorHtml('Company Hunt could not be loaded.')}</td></tr>`;
  }
}

async function runCompanyHunt() {
  // "resume" continues an interrupted run if one exists, otherwise behaves like the
  // normal new/changed check — one button, no mode picker to reason about.
  const result = await window.pywebview.api.run_company_hunt('resume');
  if (result.already_running) return;
  document.getElementById('company-hunt-tbody').innerHTML = '';
  companyHuntRunId = null;
  companyHuntCursor = 0;
  pollCompanyHuntStatus();
}

async function pollCompanyHuntStatus() {
  if (companyHuntPolling) return;
  companyHuntPolling = true;
  try {
    while (true) {
      const summary = await window.pywebview.api.get_company_hunt_summary();
      renderCompanyHuntSummary(summary);
      if (summary.run) {
        companyHuntRunId = summary.run.id;
        await appendCompanyHuntUpdates();
      }
      if (!summary.running) {
        if (summary.run && summary.run.status === 'done') await loadUnprocessed();
        break;
      }
      await new Promise(r => setTimeout(r, 2000));
    }
  } finally {
    companyHuntPolling = false;
  }
}

async function loadUnprocessed() {
  const tbody = document.getElementById('unprocessed-tbody');
  try {
    candidateData = await window.pywebview.api.get_unprocessed(
      candidateScope,
      candidatePage,
      50,
      document.getElementById('candidate-search').value
    );
    candidatePage = candidateData.page;
    document.getElementById('candidate-active-count').textContent = candidateData.counts.active;
    document.getElementById('candidate-discarded-count').textContent = candidateData.counts.discarded;
    document.getElementById('candidate-total-count').textContent = `${candidateData.counts.total} candidates`;
    renderCandidates();
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="7">${errorHtml('Candidates could not be loaded.')}</td></tr>`;
  }
}

function renderCandidates() {
  const tbody = document.getElementById('unprocessed-tbody');
  const jobs = candidateData.items || [];
  document.getElementById('candidate-select-all').style.visibility = candidateScope === 'active' ? 'visible' : 'hidden';
  if (!jobs.length) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="no-data">No ${candidateScope} candidates</div></td></tr>`;
    updateDiscardButton();
    renderCandidatePager();
    return;
  }
  tbody.innerHTML = jobs.map((job, i) => `<tr data-id="${job.id}">
      <td class="td-num">${candidateScope === 'active' ? `<input type="checkbox" class="candidate-checkbox" data-id="${job.id}" ${selectedCandidateIds.has(job.id) ? 'checked' : ''}>` : i + 1}</td>
      <td class="td-company">${esc(job.company || '—')}</td>
      <td class="td-title">${job.url ? `<a href="${safeUrl(job.url)}" target="_blank" rel="noopener">${esc(job.title || '—')}</a>` : esc(job.title || '—')}</td>
      <td>${esc(job.location || '—')}</td>
      <td><span class="badge badge-${candidateScope === 'discarded' ? 'discarded' : 'candidate'}">${candidateScope === 'discarded' ? 'Discarded' : 'Candidate'}</span></td>
      <td class="td-date">${esc(job.date || '')}</td>
      <td>${candidateScope === 'active' ? `<button class="btn btn-danger" data-delete-id="${job.id}">🗑</button>` : ''}</td>
    </tr>`).join('');
  updateDiscardButton();
  renderCandidatePager();
}

function renderCandidatePager() {
  const el = document.getElementById('candidate-pager');
  el.innerHTML = `<button class="btn" data-page-delta="-1" ${candidatePage <= 1 ? 'disabled' : ''}>Previous</button>
    <span>Page ${candidateData.page || 1} of ${candidateData.pages || 1} · ${candidateData.total || 0} results</span>
    <button class="btn" data-page-delta="1" ${candidatePage >= (candidateData.pages || 1) ? 'disabled' : ''}>Next</button>`;
}

function changeCandidatePage(delta) {
  const next = candidatePage + delta;
  if (next < 1 || next > (candidateData.pages || 1)) return;
  candidatePage = next;
  loadUnprocessed();
}

function toggleCandidateSelected(id, checked) {
  if (checked) selectedCandidateIds.add(id); else selectedCandidateIds.delete(id);
  updateDiscardButton();
}

function toggleSelectAll(checked) {
  document.querySelectorAll('.candidate-checkbox').forEach(box => {
    box.checked = checked;
    const id = Number(box.dataset.id);
    if (checked) selectedCandidateIds.add(id); else selectedCandidateIds.delete(id);
  });
  updateDiscardButton();
}

function updateDiscardButton() {
  const btn = document.getElementById('discard-selected-btn');
  btn.style.display = (candidateScope === 'active' && selectedCandidateIds.size) ? '' : 'none';
  btn.textContent = `Discard selected (${selectedCandidateIds.size})`;
}

async function discardSelected() {
  const ids = [...selectedCandidateIds];
  if (!ids.length || !confirm(`Move ${ids.length} candidate(s) to Discarded?`)) return;
  try {
    const result = await window.pywebview.api.discard_unprocessed_batch(ids);
    if (!result.ok) { alert('Discard failed: ' + result.error); return; }
    if (result.skipped && result.skipped.length) {
      alert(`${result.skipped.length} of ${ids.length} candidate(s) could not be discarded (already moved past candidate stage).`);
    }
    selectedCandidateIds.clear();
    loadUnprocessed();
  } catch(e) {
    reportFailure('Candidates could not be discarded.');
  }
}

async function deleteUnprocessed(id) {
  if (!confirm('Delete 1 candidate from the database? This cannot be undone.')) return;
  try {
    const result = await window.pywebview.api.delete_unprocessed(id);
    if (!result.ok) { alert('Delete failed: ' + result.error); return; }
    loadUnprocessed();
  } catch(e) {
    reportFailure('Candidate could not be deleted.');
  }
}

// ── Candidate preview panel — click a row to see it and open/delete without leaving the app ──
function openCandidateDetail(id) {
  const job = (candidateData.items || []).find(j => j.id === id);
  if (!job) return;
  activeCandidateId = id;
  document.getElementById('candidate-detail-panel').classList.add('open');
  document.getElementById('cdp-title').textContent = `${job.title || '—'} @ ${job.company || '—'}`;
  const chips = [];
  if (job.location) chips.push(`<span class="meta-chip">📍 ${esc(job.location)}</span>`);
  if (job.date) chips.push(`<span class="meta-chip">${esc(job.date)}</span>`);
  document.getElementById('cdp-meta').innerHTML = chips.join('');
  const linkEl = document.getElementById('cdp-link');
  if (job.url) {
    linkEl.href = safeUrl(job.url);
    linkEl.style.display = '';
  } else {
    linkEl.style.display = 'none';
  }
}

function closeCandidateDetail() {
  activeCandidateId = null;
  document.getElementById('candidate-detail-panel').classList.remove('open');
}

async function deleteCandidateDetail() {
  if (activeCandidateId == null) return;
  if (!confirm('Delete this candidate from the database? This cannot be undone.')) return;
  try {
    const result = await window.pywebview.api.delete_unprocessed(activeCandidateId);
    if (!result.ok) { alert('Delete failed: ' + result.error); return; }
    closeCandidateDetail();
    loadUnprocessed();
  } catch(e) {
    reportFailure('Candidate could not be deleted.');
  }
}

async function loadInsights() {
  insightsLoaded = true;
  const section = document.getElementById('view-insights');
  section.innerHTML = `<div class="loading-wrap"><span class="spinner"></span> Loading…</div>`;
  try {
    const data = await window.pywebview.api.get_insights();
    renderInsights(data, section);
  } catch(e) {
    section.innerHTML = errorHtml('Insights could not be loaded.');
  }
}

async function loadAnalytics() {
  analyticsLoaded = true;
  const section = document.getElementById('analytics-header');
  section.innerHTML = `<div class="loading-wrap"><span class="spinner"></span> Loading…</div>`;
  try {
    const data = await window.pywebview.api.get_analytics();
    renderAnalytics(data, section);
  } catch(e) {
    section.innerHTML = errorHtml('Analytics could not be loaded.');
  }
}

// ── Filters & sort ──
function applyFilters() {
  appPage = 1;
  loadApplications();
}

function sortBy(col) {
  if (sortCol === col) sortDir *= -1;
  else { sortCol = col; sortDir = -1; }
  document.querySelectorAll('thead th').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.col === col) th.classList.add(sortDir === -1 ? 'sort-desc' : 'sort-asc');
  });
  appPage = 1;
  loadApplications();
}

// ── Render table ──
function renderTable() {
  const tbody = document.getElementById('app-tbody');
  if (!filteredApps.length) {
    tbody.innerHTML = `<tr><td colspan="8"><div class="no-data">No applications found</div></td></tr>`;
    updateAppBulkDeleteButton();
    return;
  }
  tbody.innerHTML = filteredApps.map((app, i) => {
    const score = app.score != null ? app.score : '';
    const scoreClass = score >= 80 ? 'score-high' : score >= 60 ? 'score-mid' : score ? 'score-low' : '';
    const scorePill = score !== '' ? `<span class="score-pill ${scoreClass}">${score}</span>` : '—';
    const date = (app.date || '').substring(0, 10);
    const sel = app.slug === activeSlug ? ' selected' : '';
    const checked = selectedAppSlugs.has(app.slug) ? 'checked' : '';
    return `<tr data-slug="${esc(app.slug)}"${sel}>
      <td class="td-num"><input type="checkbox" class="app-checkbox" data-slug="${esc(app.slug)}" ${checked}></td>
      <td class="td-num">${(appPage - 1) * (appPageData.page_size || 50) + i + 1}</td>
      <td class="td-company">${esc(app.company || '—')}</td>
      <td class="td-title">${esc(app.title || '—')}</td>
      <td>${esc(app.location || app.region || '—')}</td>
      <td><span class="badge badge-${app.status || 'unknown'}">${app.status || '—'}</span></td>
      <td class="td-score">${scorePill}</td>
      <td class="td-date">${date}</td>
    </tr>`;
  }).join('');
  updateAppBulkDeleteButton();
}

function renderAppPager() {
  const el = document.getElementById('app-pager');
  el.innerHTML = `<button class="btn" data-page-delta="-1" ${appPage <= 1 ? 'disabled' : ''}>Previous</button>
    <span>Page ${appPageData.page || 1} of ${appPageData.pages || 1} · ${appPageData.total || 0} results</span>
    <button class="btn" data-page-delta="1" ${appPage >= (appPageData.pages || 1) ? 'disabled' : ''}>Next</button>`;
}

function changeAppPage(delta) {
  const next = appPage + delta;
  if (next < 1 || next > (appPageData.pages || 1)) return;
  appPage = next;
  loadApplications();
}

// ── Detail panel ──
async function selectApp(slug) {
  activeSlug = slug;
  document.querySelectorAll('tbody tr').forEach(r => r.classList.toggle('selected', r.dataset.slug === slug));
  openDetail();
  try {
    const detail = await window.pywebview.api.get_job_detail(slug);
    populateDetail(slug, detail);
  } catch(e) {
    document.getElementById('dp-jd').textContent = 'Job details could not be loaded. Retry, then run job-hunter doctor if the problem continues.';
  }
}

function openDetail() {
  document.getElementById('detail-panel').classList.add('open');
  // find app
  const app = allApps.find(a => a.slug === activeSlug);
  if (!app) return;
  document.getElementById('dp-title').textContent = `${app.title || '—'} @ ${app.company || '—'}`;
  document.getElementById('dp-status').value = app.status || 'tailored';
  document.getElementById('dp-save-msg').textContent = '';
  document.getElementById('dp-note').value = '';
}

function closeDetail() {
  clearArtifactPreview();
  activeSlug = null;
  document.getElementById('detail-panel').classList.remove('open');
  document.querySelectorAll('tbody tr').forEach(r => r.classList.remove('selected'));
}

function populateDetail(slug, detail) {
  const meta = detail.meta || {};
  const score = detail.score || {};

  // meta chips
  const chips = [];
  if (score.score != null) chips.push(`<span class="meta-chip"><strong>${score.score}</strong> score</span>`);
  if (meta.region) chips.push(`<span class="meta-chip">📍 ${esc(meta.region)}</span>`);
  if (meta.location) chips.push(`<span class="meta-chip">${esc(meta.location)}</span>`);
  if (score.decision) chips.push(`<span class="meta-chip">${esc(score.decision)}</span>`);
  document.getElementById('dp-meta').innerHTML = chips.join('');

  // link
  const linkEl = document.getElementById('dp-link');
  if (meta.url) {
    linkEl.href = safeUrl(meta.url);
    linkEl.style.display = '';
  } else {
    linkEl.style.display = 'none';
  }

  // JD
  const jd = detail.jd || '';
  document.getElementById('dp-jd').textContent = jd || 'No job description available.';

  const artifacts = detail.artifacts || [];
  document.querySelectorAll('.artifact-tab').forEach(button => {
    const artifact = artifacts.find(item => item.key === button.dataset.artifact);
    const available = Boolean(artifact && artifact.available);
    button.disabled = !available;
    button.classList.remove('active');
    button.querySelector('.artifact-state').textContent = available ? 'Ready' : 'N/A';
  });
  clearArtifactPreview();
  const firstAvailable = artifacts.find(item => item.available);
  if (firstAvailable) selectArtifact(firstAvailable.key);

  // notes from app
  const notes = detail.notes || [];
  const notesEl = document.getElementById('dp-notes');
  if (notes.length) {
    notesEl.innerHTML = notes.map(n => `<div class="note-item">${esc(String(n))}</div>`).join('');
    document.getElementById('dp-notes-section').style.display = '';
  } else {
    notesEl.innerHTML = '';
    document.getElementById('dp-notes-section').style.display = 'none';
  }
}

function clearArtifactPreview() {
  if (artifactObjectUrl) {
    URL.revokeObjectURL(artifactObjectUrl);
    artifactObjectUrl = null;
  }
  activeArtifact = null;
  activeArtifactRawText = '';
  document.querySelectorAll('.artifact-tab').forEach(button => button.classList.remove('active'));
  document.getElementById('dp-artifact-title').textContent = 'Select an artifact';
  document.getElementById('dp-copy-artifact').style.display = 'none';
  document.getElementById('dp-open-artifact').style.display = 'none';
  document.getElementById('dp-artifact-body').innerHTML = '<div class="artifact-empty">Available job files appear here.</div>';
}

// ── Markdown rendering — job artifacts (cover letter, evaluation, research, outreach,
// interview prep) are LLM-authored .md files; show them formatted, not as raw source. ──
function mdInline(escapedText) {
  let out = escapedText;
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  out = out.replace(/\*([^*\s][^*]*)\*/g, '<em>$1</em>');
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return out;
}

function renderMarkdown(raw) {
  const lines = String(raw || '').replace(/\r\n/g, '\n').split('\n');
  const html = [];
  let paragraph = [];
  let listType = null; // 'ul' | 'ol'
  let listItems = [];
  let inCode = false;
  let codeLines = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      html.push(`<p>${mdInline(esc(paragraph.join(' ')))}</p>`);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (listType) {
      const items = listItems.map(item => `<li>${mdInline(esc(item))}</li>`).join('');
      html.push(`<${listType}>${items}</${listType}>`);
      listType = null;
      listItems = [];
    }
  };

  for (const line of lines) {
    if (/^```/.test(line)) {
      if (inCode) {
        html.push(`<pre class="md-code"><code>${esc(codeLines.join('\n'))}</code></pre>`);
        codeLines = [];
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      continue;
    }
    if (inCode) { codeLines.push(line); continue; }
    if (!line.trim()) { flushParagraph(); flushList(); continue; }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushParagraph(); flushList();
      const level = heading[1].length;
      html.push(`<h${level}>${mdInline(esc(heading[2]))}</h${level}>`);
      continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushParagraph(); flushList();
      html.push('<hr>');
      continue;
    }
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    if (bullet) {
      flushParagraph();
      if (listType !== 'ul') { flushList(); listType = 'ul'; }
      listItems.push(bullet[1]);
      continue;
    }
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (numbered) {
      flushParagraph();
      if (listType !== 'ol') { flushList(); listType = 'ol'; }
      listItems.push(numbered[1]);
      continue;
    }
    const quote = line.match(/^>\s?(.*)$/);
    if (quote) {
      flushParagraph(); flushList();
      html.push(`<blockquote>${mdInline(esc(quote[1]))}</blockquote>`);
      continue;
    }
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  if (inCode && codeLines.length) html.push(`<pre class="md-code"><code>${esc(codeLines.join('\n'))}</code></pre>`);

  return html.join('\n') || '<p>Empty file.</p>';
}

let activeArtifactRawText = '';

async function selectArtifact(key) {
  if (!activeSlug) return;
  const button = document.querySelector(`.artifact-tab[data-artifact="${key}"]`);
  if (!button || button.disabled) return;
  clearArtifactPreview();
  activeArtifact = key;
  button.classList.add('active');
  document.getElementById('dp-artifact-title').textContent = button.childNodes[0].textContent.trim();
  document.getElementById('dp-artifact-body').innerHTML = '<div class="artifact-empty"><span class="spinner"></span></div>';
  try {
    const result = await window.pywebview.api.get_artifact(activeSlug, key);
    if (!result.ok) throw new Error(result.error || 'Preview unavailable.');
    document.getElementById('dp-open-artifact').style.display = '';
    if (result.kind === 'pdf') {
      const bytes = Uint8Array.from(atob(result.content), char => char.charCodeAt(0));
      artifactObjectUrl = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
      document.getElementById('dp-artifact-body').innerHTML = `<iframe class="artifact-pdf" title="${esc(result.filename)}"></iframe>`;
      document.querySelector('.artifact-pdf').src = artifactObjectUrl;
    } else {
      activeArtifactRawText = result.content || '';
      const div = document.createElement('div');
      div.className = 'artifact-markdown';
      div.innerHTML = renderMarkdown(activeArtifactRawText);
      const body = document.getElementById('dp-artifact-body');
      body.innerHTML = '';
      body.appendChild(div);
      document.getElementById('dp-copy-artifact').style.display = '';
    }
  } catch(e) {
    document.getElementById('dp-artifact-body').innerHTML = `<div class="artifact-empty">${esc(e.message || e)}</div>`;
  }
}

async function copyArtifact() {
  if (!activeArtifactRawText) return;
  try {
    await navigator.clipboard.writeText(activeArtifactRawText);
  } catch(_) {
    const area = document.createElement('textarea');
    area.value = activeArtifactRawText;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  const button = document.getElementById('dp-copy-artifact');
  button.textContent = 'Copied';
  setTimeout(() => { button.textContent = 'Copy'; }, 1200);
}

async function openArtifact() {
  if (!activeSlug || !activeArtifact) return;
  const result = await window.pywebview.api.open_artifact(activeSlug, activeArtifact);
  if (!result.ok) alert(result.error || 'Could not open file.');
}

async function openJobFolder() {
  if (!activeSlug) return;
  const result = await window.pywebview.api.open_job_folder(activeSlug);
  if (!result.ok) alert(result.error || 'Could not open folder.');
}

async function saveStatus() {
  if (!activeSlug) return;
  const status = document.getElementById('dp-status').value;
  const note = document.getElementById('dp-note').value.trim();
  const msg = document.getElementById('dp-save-msg');
  const idx = allApps.findIndex(a => a.slug === activeSlug);
  const previousStatus = idx >= 0 ? allApps[idx].status : null;
  try {
    const result = await window.pywebview.api.update_status(activeSlug, status, note);
    if (result.error) { msg.textContent = '✗ ' + result.error; msg.style.color = '#f85149'; return; }
    // update local cache
    if (idx >= 0) { allApps[idx] = { ...allApps[idx], ...result }; }
    msg.textContent = '✓ Saved'; msg.style.color = '#56d364';
    loadApplications(); // reload the current page in place — a status edit must not bump the user back to page 1
    setTimeout(() => { msg.textContent = ''; }, 2000);
    document.getElementById('dp-note').value = '';
    insightsLoaded = false; // invalidate insights cache
    if (status === 'applied' && previousStatus !== 'applied') {
      showToast('✓ Applied — nice work!');
    }
    loadApplicationStreak();
    checkMilestones();
  } catch(e) {
    msg.textContent = '✗ Status could not be saved. Retry, then run job-hunter doctor if the problem continues.';
    msg.style.color = '#f85149';
  }
}

async function deleteApp() {
  if (!activeSlug) return;
  const app = allApps.find(a => a.slug === activeSlug);
  const name = app ? `${app.company} — ${app.title}` : activeSlug;
  if (!confirm(`Delete "${name}"?\n\nThis removes it from the tracker and deletes the job folder. Cannot be undone.`)) return;
  try {
    const result = await window.pywebview.api.delete_application(activeSlug);
    if (!result.ok) { alert('Delete failed: ' + result.error); return; }
    allApps = allApps.filter(a => a.slug !== activeSlug);
    selectedAppSlugs.delete(activeSlug);
    closeDetail();
    loadApplications(); // reload the current page in place — a delete must not bump the user back to page 1
    insightsLoaded = false;
  } catch(e) {
    reportFailure('Application could not be deleted.');
  }
}

function toggleAppSelected(slug, checked) {
  if (checked) selectedAppSlugs.add(slug); else selectedAppSlugs.delete(slug);
  updateAppBulkDeleteButton();
}

function toggleSelectAllApps(checked) {
  document.querySelectorAll('.app-checkbox').forEach(box => {
    box.checked = checked;
    if (checked) selectedAppSlugs.add(box.dataset.slug); else selectedAppSlugs.delete(box.dataset.slug);
  });
  updateAppBulkDeleteButton();
}

function updateAppBulkDeleteButton() {
  const btn = document.getElementById('app-bulk-delete-btn');
  btn.style.display = selectedAppSlugs.size ? '' : 'none';
  btn.textContent = `Delete selected (${selectedAppSlugs.size})`;
}

async function bulkDeleteApplications() {
  const slugs = [...selectedAppSlugs];
  if (!slugs.length) return;
  if (!confirm(`Delete ${slugs.length} application(s)?\n\nThis removes them from the tracker and deletes their job folders. Cannot be undone.`)) return;
  try {
    const result = await window.pywebview.api.delete_applications_batch(slugs);
    if (!result.ok) { alert('Delete failed: ' + result.error); return; }
    allApps = allApps.filter(a => !slugs.includes(a.slug));
    selectedAppSlugs.clear();
    if (slugs.includes(activeSlug)) closeDetail();
    loadApplications(); // reload the current page in place — a delete must not bump the user back to page 1
    insightsLoaded = false;
    if (result.warnings && result.warnings.length) alert(result.warnings.join('\n'));
  } catch(e) {
    reportFailure('Applications could not be deleted.');
  }
}

// ── Insights rendering ──
const STATUS_COLORS = {
  tailored:  '#1f6feb',
  applied:   '#d29922',
  responded: '#f0883e',
  interview: '#8957e5',
  offer:     '#238636',
  rejected:  '#6e7681',
};

function renderInsights(data, container) {
  const total = data.total || 0;
  const byStatus = data.by_status || {};
  const weekly = data.weekly || {};

  const applied = (byStatus.applied || 0) + (byStatus.responded || 0) + (byStatus.interview || 0) + (byStatus.offer || 0);
  const responded = (byStatus.responded || 0) + (byStatus.interview || 0) + (byStatus.offer || 0);
  const offers = byStatus.offer || 0;
  const respRate = applied ? Math.round(responded / applied * 100) : 0;
  const offerRate = applied ? Math.round(offers / applied * 100) : 0;

  container.innerHTML = `
    <div class="stats-cards">
      <div class="stat-card blue"><div class="stat-label">Total</div><div class="stat-value">${total}</div><div class="stat-sub">applications tracked</div></div>
      <div class="stat-card orange"><div class="stat-label">Applied</div><div class="stat-value">${applied}</div><div class="stat-sub">of ${total} tailored</div></div>
      <div class="stat-card purple"><div class="stat-label">Response Rate</div><div class="stat-value">${respRate}%</div><div class="stat-sub">${responded} responses</div></div>
      <div class="stat-card green"><div class="stat-label">Offers</div><div class="stat-value">${offers}</div><div class="stat-sub">${offerRate}% of applied</div></div>
    </div>

    <div class="charts-row">
      <div class="chart-card">
        <h3>By Status</h3>
        ${renderStatusBreakdown(byStatus, total)}
      </div>
      <div class="chart-card">
        <h3>Weekly Applications</h3>
        ${renderWeeklyBars(weekly)}
      </div>
    </div>

    <div class="funnel-section">
      <h3>Conversion Funnel</h3>
      ${renderFunnel(byStatus, total)}
    </div>
  `;
}

function renderStatusBreakdown(byStatus, total) {
  const labels = Object.keys(byStatus);
  if (!labels.length) return '<div class="no-data">No applications yet</div>';
  return `<div class="bar-summary">${labels.map(status => {
    const count = byStatus[status] || 0;
    const pct = total > 0 ? Math.round(count / total * 100) : 0;
    const color = STATUS_COLORS[status] || '#555';
    return `<div class="bar-summary-row">
      <span class="bar-summary-label">${esc(status)}</span>
      <div class="bar-summary-track"><div class="bar-summary-fill" style="width:${pct}%;background:${color};"></div></div>
      <span class="bar-summary-count">${count}</span>
    </div>`;
  }).join('')}</div>`;
}

function renderWeeklyBars(weekly) {
  const labels = Object.keys(weekly);
  if (!labels.length) return '<div class="no-data">No applications yet</div>';
  const values = Object.values(weekly);
  const max = Math.max(1, ...values);
  return `<div class="bar-summary">${labels.map(week => {
    const count = weekly[week] || 0;
    const pct = Math.round(count / max * 100);
    return `<div class="bar-summary-row">
      <span class="bar-summary-label">${esc(week)}</span>
      <div class="bar-summary-track"><div class="bar-summary-fill" style="width:${pct}%;background:#1f6feb;"></div></div>
      <span class="bar-summary-count">${count}</span>
    </div>`;
  }).join('')}</div>`;
}

function renderFunnel(byStatus, total) {
  const stages = [
    { key: 'tailored', label: 'Tailored', color: STATUS_COLORS.tailored },
    { key: 'applied', label: 'Applied', color: STATUS_COLORS.applied },
    { key: 'responded', label: 'Responded', color: STATUS_COLORS.responded },
    { key: 'interview', label: 'Interview', color: STATUS_COLORS.interview },
    { key: 'offer', label: 'Offer', color: STATUS_COLORS.offer },
  ];
  // Cumulative counts (each stage includes stages beyond it)
  const counts = {
    tailored: total,
    applied: (byStatus.applied||0)+(byStatus.responded||0)+(byStatus.interview||0)+(byStatus.offer||0),
    responded: (byStatus.responded||0)+(byStatus.interview||0)+(byStatus.offer||0),
    interview: (byStatus.interview||0)+(byStatus.offer||0),
    offer: byStatus.offer||0,
  };
  return stages.map(s => {
    const count = counts[s.key] || 0;
    const pct = total > 0 ? Math.round(count / total * 100) : 0;
    const barWidth = total > 0 ? Math.max(2, Math.round(count / total * 100)) : 0;
    return `<div class="funnel-row">
      <span class="funnel-label">${s.label}</span>
      <div class="funnel-bar-wrap">
        <div class="funnel-bar" style="width:${barWidth}%;background:${s.color};"></div>
      </div>
      <span class="funnel-count">${count}</span>
      <span class="funnel-pct">${pct}%</span>
    </div>`;
  }).join('');
}

// ── Analytics rendering ──
function buildHeatmap(daily) {
  const days = [];
  const today = new Date();
  for (let i = 83; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    days.push({ key, ...(daily[key] || { runs: 0, tokens: 0 }) });
  }
  const max = Math.max(1, ...days.map(d => d.tokens || d.runs));
  const level = v => v === 0 ? 0 : Math.min(4, Math.ceil((v / max) * 4));
  // Group into weeks (columns), 7 rows each, aligned to the end.
  const cols = [];
  for (let i = 0; i < days.length; i += 7) cols.push(days.slice(i, i + 7));
  return `<div class="heatmap-wrap">${cols.map(week => `
    <div class="heatmap-col">${week.map(d => {
      const v = d.tokens || d.runs;
      return `<div class="heatmap-cell" data-level="${level(v)}" title="${d.key}: ${d.runs} run(s), ${d.tokens.toLocaleString()} token(s)"></div>`;
    }).join('')}</div>`).join('')}</div>`;
}

function renderAnalytics(data, container) {
  const configMode = data.mode || 'agent';
  const runs = data.runs || [];
  const telemetry = data.telemetry || {};
  const normalizedTotals = telemetry.totals || {};
  const outcomes = telemetry.outcomes || {};
  const operational = telemetry.operational || {};
  const ignored = telemetry.ignored || { events: 0 };
  const tokenStatus = telemetry.token_status || 'unavailable';
  const normalizedTokenCount = (normalizedTotals.input_tokens || 0) + (normalizedTotals.output_tokens || 0);
  const tokensPerTailored = outcomes.tailored ? Math.round(normalizedTokenCount / outcomes.tailored) : 0;
  const latest = runs[0];

  let headerHtml;
  if (latest) {
    const mode = latest.exec_mode || '—';
    const modeClass = mode === 'llm-api' ? 'mode-api' : 'mode-agent';
    const cost = latest.total_cost_usd != null ? `$${Number(latest.total_cost_usd).toFixed(4)}` : '—';
    const ts = (latest.ts || '').replace('T', ' ').substring(0, 16);
    headerHtml = `
      <div class="run-stat"><div class="run-stat-label">Exec Mode</div><div class="run-stat-value ${modeClass}">${mode}</div></div>
      <div class="run-stat"><div class="run-stat-label">Last Run</div><div class="run-stat-value" style="font-size:14px">${ts}</div></div>
      <div class="run-stat"><div class="run-stat-label">Jobs Found</div><div class="run-stat-value">${latest.jobs_found ?? 0}</div></div>
      <div class="run-stat"><div class="run-stat-label">Tailored</div><div class="run-stat-value">${latest.jobs_tailored ?? 0}</div></div>
      <div class="run-stat"><div class="run-stat-label">Duration</div><div class="run-stat-value">${latest.duration_s ? latest.duration_s.toFixed(1) + 's' : '—'}</div></div>
      <div class="run-stat"><div class="run-stat-label">Cost</div><div class="run-stat-value" style="color:#56d364">${cost}</div></div>
    `;
  } else if (configMode === 'agent' && normalizedTokenCount) {
    // Agent mode never writes pipeline_runs (job-hunter hunt only scrapes); token
    // activity below comes entirely from skills run via /job-hunter batch.
    headerHtml = `<span style="color:var(--text-muted)">Agent mode: no scrape pipeline run recorded. Token usage below is from skill activity (/job-hunter batch).</span>`;
  } else if (configMode === 'agent') {
    headerHtml = `<span style="color:var(--text-muted)">No skill token telemetry captured yet. Run <code>/job-hunter batch</code> (or another skill) from Claude Code or Codex first.</span>`;
  } else {
    headerHtml = `<span style="color:var(--text-muted)">No pipeline runs recorded yet. Run <code>job-hunter hunt</code> first.</span>`;
  }

  let tokenNote = '';
  if (outcomes.processed > 0 && tokenStatus === 'unavailable') {
    tokenNote = `<div class="agent-note">Job Hunter outcomes are captured, but Claude/Codex token telemetry has not reached the local collector yet. Run <code>job-hunter internal telemetry-status --json</code> for diagnostics.</div>`;
  } else if (configMode === 'agent' && !normalizedTokenCount) {
    tokenNote = `<div class="agent-note">No agent token telemetry captured yet. Restart Claude Code or Codex after workspace telemetry setup, then run a skill (e.g. /job-hunter batch). Diagnose with <code>job-hunter internal telemetry-status --json</code>.</div>`;
  }

  const skillRows = Object.entries(telemetry.by_skill_backend || {})
    .sort((a, b) => (b[1].total?.total_tokens || 0) - (a[1].total?.total_tokens || 0))
    .map(([name, values]) => {
      const claude = values['claude-code'] || {};
      const codex = values.codex || {};
      const total = values.total || {};
      const cached = (total.cached_tokens || 0) + (total.cache_read_tokens || 0) + (total.cache_creation_tokens || 0);
      return `<tr>
        <td>${esc(name.replaceAll('_', ' '))}</td>
        <td>${(claude.total_tokens || 0).toLocaleString()}</td>
        <td>${(codex.total_tokens || 0).toLocaleString()}</td>
        <td>${(total.total_tokens || 0).toLocaleString()}</td>
        <td>${(total.sessions || 0).toLocaleString()}</td>
        <td>${(total.messages || 0).toLocaleString()}</td>
        <td>${(total.input_tokens || 0).toLocaleString()}</td>
        <td>${(total.output_tokens || 0).toLocaleString()}</td>
        <td>${cached.toLocaleString()}</td>
        <td>${(total.reasoning_tokens || 0).toLocaleString()}</td>
      </tr>`;
    }).join('') || `<tr><td colspan="10" class="no-data">No skill data</td></tr>`;

  const batchPhases = ['screening', 'scoring', 'research', 'tailoring', 'cover_letter', 'pdf'];
  const phaseRows = batchPhases
    .filter(name => telemetry.by_phase && telemetry.by_phase[name])
    .map(name => {
      const value = telemetry.by_phase[name];
      return `<tr><td>${esc(name.replaceAll('_', ' '))}</td>
        <td>${(value.total_tokens || 0).toLocaleString()}</td>
        <td>${(value.input_tokens || 0).toLocaleString()}</td>
        <td>${(value.output_tokens || 0).toLocaleString()}</td></tr>`;
    }).join('');

  const tokenDisplay = v => tokenStatus === 'unavailable' && !v ? 'not observed' : v.toLocaleString();

  container.innerHTML = `
    <div class="run-header">${headerHtml}</div>

    ${tokenNote}

    <div class="section-title">Overview</div>
    <div class="run-header">
      <div class="run-stat"><div class="run-stat-label">Sessions</div><div class="run-stat-value">${operational.sessions ?? 0}</div></div>
      <div class="run-stat"><div class="run-stat-label">Messages</div><div class="run-stat-value">${operational.messages ?? 0}</div></div>
      <div class="run-stat"><div class="run-stat-label">Active Days</div><div class="run-stat-value">${operational.active_days ?? 0}</div></div>
      <div class="run-stat"><div class="run-stat-label">Current Streak</div><div class="run-stat-value">${operational.current_streak ?? 0}</div></div>
      <div class="run-stat"><div class="run-stat-label">Longest Streak</div><div class="run-stat-value">${operational.longest_streak ?? 0}</div></div>
      <div class="run-stat"><div class="run-stat-label">Total Tokens</div><div class="run-stat-value">${tokenDisplay(normalizedTokenCount)}</div></div>
      <div class="run-stat"><div class="run-stat-label">Tokens / Tailored</div><div class="run-stat-value">${tokenDisplay(tokensPerTailored)}</div></div>
    </div>

    <div class="chart-card">
      <h3>Daily Activity (last 12 weeks)</h3>
      ${buildHeatmap(operational.daily || {})}
    </div>

    ${ignored.events ? `<div class="agent-note">Warning: Ignored ${ignored.events} non-Job-Hunter telemetry event(s).</div>` : ''}

    <div class="chart-card">
      <h3>Tokens by Skill</h3>
      <table class="data-table"><thead><tr><th>Skill</th><th>Claude Code Tokens</th><th>Codex Tokens</th><th>Total Tokens</th><th>Sessions</th><th>Messages</th><th>Input</th><th>Output</th><th>Cached</th><th>Reasoning</th></tr></thead>
      <tbody>${skillRows}</tbody></table>
    </div>
    ${phaseRows ? `<div class="chart-card"><h3>Batch breakdown</h3>
      <table class="data-table"><thead><tr><th>Phase</th><th>Total Tokens</th><th>Input</th><th>Output</th></tr></thead>
      <tbody>${phaseRows}</tbody></table></div>` : ''}
  `;
}

// ── Settings ──
function settingsHasUnsavedChanges() {
  return cfgDirty || cfgRawDirty || careerContextDirty;
}

function updateDirtyFlag(scope) {
  const flags = { guided: cfgDirty, raw: cfgRawDirty, 'career-context': careerContextDirty };
  document.getElementById(`settings-${scope}-dirty`).style.display = flags[scope] ? '' : 'none';
}

function clearFieldErrorHighlights() {
  document.querySelectorAll('.settings-section.field-error').forEach(el => el.classList.remove('field-error'));
}

function highlightErrorSections(errors) {
  const sectionKeys = ['mode', 'profile', 'job_titles', 'regions', 'exclusions', 'scoring', 'llm'];
  const joined = errors.join(' ').toLowerCase();
  sectionKeys.forEach(key => {
    if (joined.includes(key.toLowerCase())) {
      document.getElementById(`settings-section-${key}`)?.classList.add('field-error');
    }
  });
}

function showSettingsErrors(errors) {
  const el = document.getElementById('settings-errors');
  clearFieldErrorHighlights();
  if (!errors || !errors.length) { el.style.display = 'none'; el.innerHTML = ''; return; }
  el.innerHTML = errors.map(e => `<div>✗ ${esc(e)}</div>`).join('');
  el.style.display = '';
  highlightErrorSections(errors);
}

function showSettingsWarnings(warnings) {
  const el = document.getElementById('settings-warnings');
  if (!warnings || !warnings.length) { el.style.display = 'none'; el.innerHTML = ''; return; }
  el.innerHTML = warnings.map(w => `<div>⚠ ${esc(w)}</div>`).join('');
  el.style.display = '';
}

function clearSettingsMessages() {
  document.getElementById('settings-errors').style.display = 'none';
  document.getElementById('settings-errors').innerHTML = '';
  document.getElementById('settings-warnings').style.display = 'none';
  document.getElementById('settings-warnings').innerHTML = '';
  clearFieldErrorHighlights();
}

async function loadSettings() {
  settingsLoaded = true;
  await Promise.all([
    loadGuidedConfig(), loadRawConfig(), loadCareerContextSettings(),
    loadApiKeyStatus(), loadGetStartedActionsGuide(),
  ]);
}

async function loadGetStarted() {
  // Settings editors back the quick-fill and import flows, so load them alongside the checklist.
  await loadOnboarding();
  if (!settingsLoaded) await loadSettings();
}

async function saveSearchSetup() {
  const msg = document.getElementById('gs-search-msg');
  msg.textContent = '';
  const bootstrap = await window.pywebview.api.get_bootstrap();
  if (!bootstrap.ok) {
    msg.textContent = 'Could not load current config.';
    msg.style.color = '#f85149';
    return;
  }
  const prefs = {
    mode: document.getElementById('gs-search-mode').value,
    career_stage: document.getElementById('gs-career-stage').value,
    job_titles: document.getElementById('gs-search-job-titles').value.split('\n').map(s => s.trim()).filter(Boolean),
    country: document.getElementById('gs-search-country').value,
    location: document.getElementById('gs-search-location').value,
    search_lang: document.getElementById('gs-search-lang').value,
    excluded_industries: document.getElementById('gs-search-excl-industries').value.split('\n').map(s => s.trim()).filter(Boolean),
  };
  const result = await window.pywebview.api.save_onboarding_preferences(prefs, bootstrap.data.config_revision);
  if (result.ok) {
    msg.textContent = 'Saved.';
    msg.style.color = '#56d364';
    loadOnboarding();
  } else {
    msg.textContent = (result.errors || []).join(' ') || 'Could not save.';
    msg.style.color = '#f85149';
  }
}

async function copyOnboardingPrompt() {
  const btn = document.getElementById('copy-onboarding-prompt-btn');
  const result = await window.pywebview.api.get_onboarding_prompt();
  if (!result.ok) {
    btn.textContent = 'Failed';
    setTimeout(() => { btn.textContent = 'Copy setup prompt'; }, 1200);
    return;
  }
  try {
    await navigator.clipboard.writeText(result.data.prompt);
  } catch(_) {
    const area = document.createElement('textarea');
    area.value = result.data.prompt;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  btn.textContent = 'Copied!';
  setTimeout(() => { btn.textContent = 'Copy setup prompt'; }, 1200);
}

async function importChatbotBundle() {
  const msg = document.getElementById('gs-import-msg');
  const text = document.getElementById('gs-chatbot-response').value;
  const result = await window.pywebview.api.import_onboarding_bundle(text);
  if (result.ok) {
    msg.textContent = 'Imported — career context, story bank, and resume source updated.';
    msg.style.color = '#56d364';
    document.getElementById('gs-chatbot-response').value = '';
    loadOnboarding();
  } else {
    msg.textContent = (result.errors || []).join(' ') || 'Could not import.';
    msg.style.color = '#f85149';
  }
}

function fillCareerContextLine(text, label, value) {
  if (!value) return text;
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp('^(-\\s*' + escaped + ':)\\s*$', 'm');
  return re.test(text) ? text.replace(re, `$1 ${value}`) : text;
}

function applyQuickCareerContext() {
  const msg = document.getElementById('gs-career-msg');
  let text = document.getElementById('settings-career-context').value;
  if (!text) {
    msg.textContent = 'Open Settings → Career Context once first, then come back.';
    msg.style.color = '#ffa657';
    return;
  }
  const fields = [
    ['Current role', document.getElementById('gs-current-role').value.trim()],
    ['Experience summary', document.getElementById('gs-experience-summary').value.trim()],
    ['Target role shapes', document.getElementById('gs-target-roles').value.trim()],
    ['Positioning', document.getElementById('gs-resume-positioning').value.trim()],
    ['Voice', document.getElementById('gs-cover-voice').value.trim()],
    ['Tone', document.getElementById('gs-linkedin-tone').value.trim()],
  ];
  for (const [label, value] of fields) text = fillCareerContextLine(text, label, value);
  document.getElementById('settings-career-context').value = text;
  careerContextDirty = true;
  updateDirtyFlag('career-context');
  msg.textContent = '✓ Applied — review and Save in Settings → Career Context';
  msg.style.color = '#56d364';
  setTimeout(() => { msg.textContent = ''; }, 3000);
}

async function loadApiKeyStatus() {
  const label = document.getElementById('gs-api-key-label');
  try {
    const result = await window.pywebview.api.get_api_key_status();
    if (!result.ok) { label.textContent = 'API key status unavailable.'; return; }
    if (!result.required) { label.textContent = `${result.provider}: no API key needed`; return; }
    label.textContent = `${result.env_var} — ${result.configured ? 'configured ✓' : 'not set'}`;
  } catch(_) {
    label.textContent = 'API key status unavailable.';
  }
}

async function saveApiKey() {
  const input = document.getElementById('gs-api-key-input');
  const msg = document.getElementById('gs-api-key-msg');
  const value = input.value;
  try {
    const result = await window.pywebview.api.save_api_key(value);
    if (!result.ok) { msg.textContent = result.error || 'Could not save the key.'; msg.style.color = '#f85149'; return; }
    input.value = '';
    msg.textContent = '✓ Saved to OS keyring';
    msg.style.color = '#56d364';
    setTimeout(() => { msg.textContent = ''; }, 3000);
    await loadApiKeyStatus();
  } catch(_) {
    msg.textContent = 'Could not save the key.';
    msg.style.color = '#f85149';
  }
}

async function loadGetStartedActionsGuide() {
  const status = document.getElementById('gs-actions-status');
  const requiredEl = document.getElementById('gs-required-secret');
  const optionalEl = document.getElementById('gs-optional-secrets');
  const diffEl = document.getElementById('gs-yaml-diff');
  try {
    const result = await window.pywebview.api.get_github_actions_guide();
    if (!result.ok) { status.textContent = 'GitHub Actions status unavailable.'; return; }
    status.textContent = result.schedule_enabled
      ? '✓ Schedule is enabled — unattended hunting is live.'
      : '○ Schedule not enabled yet — manual runs only.';
    const s = result.required_secret;
    requiredEl.innerHTML = '';
    if (s.name) {
      const label = document.createElement('span');
      label.textContent = `${s.name}: ${s.configured ? 'configured' : '(not set)'} `;
      requiredEl.appendChild(label);
      if (s.configured) {
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn';
        copyBtn.style.cssText = 'padding:2px 8px;font-size:11px;';
        copyBtn.textContent = 'Copy';
        copyBtn.onclick = copySecretValue;
        requiredEl.appendChild(copyBtn);
      }
    } else {
      requiredEl.textContent = 'No secret needed for this provider.';
    }
    optionalEl.textContent = result.optional_secret_names.join(', ');
    diffEl.textContent = result.yaml_diff;
  } catch(_) {
    status.textContent = 'GitHub Actions status unavailable.';
  }
}

async function copySecretValue(event) {
  // The value is copied to the OS clipboard directly by Python — it never
  // crosses the JS bridge, so there's nothing to read from the DOM here.
  const btn = event.target;
  const original = btn.textContent;
  const result = await window.pywebview.api.copy_github_actions_secret();
  btn.textContent = result.ok ? 'Copied!' : 'Failed';
  setTimeout(() => { btn.textContent = original; }, 1500);
}

function renderGuidedForm(form) {
  loadingGuidedForm = true;
  document.getElementById('cfg-mode').value = form.mode || 'agent';
  document.getElementById('cfg-resume-tex').value = form.profile.resume_tex || '';
  document.getElementById('cfg-story-bank').value = form.profile.story_bank || '';
  document.getElementById('cfg-career-context-path').value = form.profile.career_context || '';
  document.getElementById('cfg-latex-class').value = form.profile.latex_class || '';
  document.getElementById('cfg-profile-image').value = form.profile.profile_image || '';
  document.getElementById('cfg-job-titles').value = (form.job_titles || []).join('\n');
  document.getElementById('cfg-excl-companies').value = (form.exclusions.companies || []).join('\n');
  document.getElementById('cfg-excl-titles').value = (form.exclusions.title_terms || []).join('\n');
  document.getElementById('cfg-excl-languages').value = (form.exclusions.languages || []).join('\n');
  document.getElementById('cfg-excl-industries').value = (form.exclusions.industries || []).join('\n');
  document.getElementById('cfg-min-fit-score').value = form.scoring.min_fit_score ?? 70;
  document.getElementById('cfg-max-years').value = form.scoring.max_years_experience_required ?? '';
  document.getElementById('cfg-batch-size').value = form.scoring.batch_size ?? 15;
  document.getElementById('cfg-llm-provider').value = form.llm_default_provider || 'anthropic';

  document.getElementById('cfg-regions-rows').innerHTML = '';
  Object.entries(form.regions || {}).forEach(([key, region]) => addRegionRow(key, region));

  document.getElementById('cfg-overrides-rows').innerHTML = '';
  (form.scoring.strategic_overrides || []).forEach(o => addOverrideRow(o));
  loadingGuidedForm = false;
}

function markConfigDirty() {
  if (loadingGuidedForm) return;
  cfgDirty = true;
  updateDirtyFlag('guided');
}

function addRegionRow(key = '', region = {}) {
  const rowId = `region-row-${regionRowSeq++}`;
  const row = document.createElement('div');
  row.className = 'settings-row';
  row.id = rowId;
  row.innerHTML = `
    <div class="settings-field"><label>Key</label><input type="text" class="region-key" value="${esc(key)}"></div>
    <div class="settings-row-checkbox"><input type="checkbox" class="region-enabled" ${region.enabled !== false ? 'checked' : ''}> Enabled</div>
    <div class="settings-row-checkbox"><input type="checkbox" class="region-primary" ${region.primary ? 'checked' : ''}> Primary</div>
    <div class="settings-field"><label>Country (ISO2)</label><input type="text" class="region-country" maxlength="2" value="${esc(region.country || '')}"></div>
    <div class="settings-field"><label>Location</label><input type="text" class="region-location" value="${esc(region.location || '')}"></div>
    <div class="settings-field"><label>Search lang</label><input type="text" class="region-search-lang" value="${esc(region.search_lang || '')}"></div>
    <div class="settings-field"><label>Description</label><input type="text" class="region-description" value="${esc(region.description || '')}"></div>
    <button class="btn btn-danger" type="button" data-remove-row="${rowId}">Remove</button>
  `;
  row.addEventListener('input', markConfigDirty);
  row.addEventListener('change', markConfigDirty);
  row.querySelector(`[data-remove-row="${rowId}"]`).addEventListener('click', () => { row.remove(); markConfigDirty(); });
  document.getElementById('cfg-regions-rows').appendChild(row);
  markConfigDirty();
}

function addOverrideRow(override = {}) {
  const rowId = `override-row-${overrideRowSeq++}`;
  const row = document.createElement('div');
  row.className = 'settings-row';
  row.id = rowId;
  row.innerHTML = `
    <div class="settings-field"><label>Company</label><input type="text" class="override-company" value="${esc(override.company || '')}"></div>
    <div class="settings-field"><label>Min score override</label><input type="number" min="0" max="100" class="override-min-score" value="${override.min_score_override ?? ''}"></div>
    <div class="settings-row-checkbox"><input type="checkbox" class="override-bypass" ${override.bypass_max_years_experience ? 'checked' : ''}> Bypass max years</div>
    <div class="settings-field"><label>Reason</label><input type="text" class="override-reason" value="${esc(override.reason || '')}"></div>
    <button class="btn btn-danger" type="button" data-remove-row="${rowId}">Remove</button>
  `;
  row.addEventListener('input', markConfigDirty);
  row.addEventListener('change', markConfigDirty);
  row.querySelector(`[data-remove-row="${rowId}"]`).addEventListener('click', () => { row.remove(); markConfigDirty(); });
  document.getElementById('cfg-overrides-rows').appendChild(row);
  markConfigDirty();
}

function collectGuidedForm() {
  const regions = {};
  document.querySelectorAll('#cfg-regions-rows .settings-row').forEach(row => {
    const key = row.querySelector('.region-key').value.trim();
    if (!key) return;
    const entry = {
      enabled: row.querySelector('.region-enabled').checked,
      primary: row.querySelector('.region-primary').checked,
      country: row.querySelector('.region-country').value.trim(),
      location: row.querySelector('.region-location').value.trim(),
    };
    const searchLang = row.querySelector('.region-search-lang').value.trim();
    const description = row.querySelector('.region-description').value.trim();
    if (searchLang) entry.search_lang = searchLang;
    if (description) entry.description = description;
    regions[key] = entry;
  });

  const strategic_overrides = [];
  document.querySelectorAll('#cfg-overrides-rows .settings-row').forEach(row => {
    const company = row.querySelector('.override-company').value.trim();
    if (!company) return;
    const entry = { company };
    const minScore = row.querySelector('.override-min-score').value;
    if (minScore !== '') entry.min_score_override = Number(minScore);
    if (row.querySelector('.override-bypass').checked) entry.bypass_max_years_experience = true;
    const reason = row.querySelector('.override-reason').value.trim();
    if (reason) entry.reason = reason;
    strategic_overrides.push(entry);
  });

  const maxYears = document.getElementById('cfg-max-years').value;
  const splitLines = id => document.getElementById(id).value.split('\n');

  return {
    mode: document.getElementById('cfg-mode').value,
    profile: {
      resume_tex: document.getElementById('cfg-resume-tex').value.trim(),
      story_bank: document.getElementById('cfg-story-bank').value.trim(),
      career_context: document.getElementById('cfg-career-context-path').value.trim(),
      latex_class: document.getElementById('cfg-latex-class').value.trim(),
      profile_image: document.getElementById('cfg-profile-image').value.trim(),
    },
    job_titles: splitLines('cfg-job-titles'),
    regions,
    exclusions: {
      companies: splitLines('cfg-excl-companies'),
      title_terms: splitLines('cfg-excl-titles'),
      languages: splitLines('cfg-excl-languages'),
      industries: splitLines('cfg-excl-industries'),
    },
    scoring: {
      min_fit_score: Number(document.getElementById('cfg-min-fit-score').value || 0),
      max_years_experience_required: maxYears === '' ? null : Number(maxYears),
      batch_size: Number(document.getElementById('cfg-batch-size').value || 1),
      strategic_overrides,
    },
    llm_default_provider: document.getElementById('cfg-llm-provider').value,
  };
}

async function loadGuidedConfig() {
  try {
    const result = await window.pywebview.api.get_job_hunter_config_form();
    if (!result.ok) { showSettingsErrors(result.errors); return; }
    cfgRevision = result.data.revision;
    renderGuidedForm(result.data.form);
    cfgDirty = false;
    updateDirtyFlag('guided');
  } catch(e) {
    showSettingsErrors(['job_hunter.yml could not be loaded. Retry, then run job-hunter doctor if the problem continues.']);
  }
}

async function saveGuidedConfig() {
  const btn = document.getElementById('settings-save-guided');
  const msg = document.getElementById('settings-guided-msg');
  clearSettingsMessages();
  btn.disabled = true;
  try {
    const form = collectGuidedForm();
    const result = await window.pywebview.api.save_job_hunter_config_form(form, cfgRevision);
    if (!result.ok) { showSettingsErrors(result.errors); return; }
    cfgRevision = result.data.revision;
    cfgDirty = false;
    updateDirtyFlag('guided');
    showSettingsWarnings(result.warnings);
    msg.textContent = '✓ Saved'; msg.style.color = '#56d364';
    setTimeout(() => { msg.textContent = ''; }, 2000);
    await loadRawConfig();
  } catch(e) {
    showSettingsErrors(['job_hunter.yml could not be saved. Retry, then run job-hunter doctor if the problem continues.']);
  } finally {
    btn.disabled = false;
  }
}

async function loadRawConfig() {
  try {
    const result = await window.pywebview.api.get_job_hunter_config_raw();
    cfgRawRevision = result.data.revision;
    loadingRaw = true;
    document.getElementById('settings-raw-yaml').value = result.data.text;
    loadingRaw = false;
    cfgRawDirty = false;
    updateDirtyFlag('raw');
  } catch(e) {
    showSettingsErrors(['job_hunter.yml could not be loaded. Retry, then run job-hunter doctor if the problem continues.']);
  }
}

function markRawDirty() {
  if (loadingRaw) return;
  cfgRawDirty = true;
  updateDirtyFlag('raw');
}

async function saveRawConfig() {
  const btn = document.querySelector('#settings-panel-advanced .btn-primary');
  const msg = document.getElementById('settings-raw-msg');
  clearSettingsMessages();
  btn.disabled = true;
  try {
    const text = document.getElementById('settings-raw-yaml').value;
    const result = await window.pywebview.api.save_job_hunter_config_raw(text, cfgRawRevision);
    if (!result.ok) { showSettingsErrors(result.errors); return; }
    cfgRawRevision = result.data.revision;
    cfgRawDirty = false;
    updateDirtyFlag('raw');
    showSettingsWarnings(result.warnings);
    msg.textContent = '✓ Saved'; msg.style.color = '#56d364';
    setTimeout(() => { msg.textContent = ''; }, 2000);
    await loadGuidedConfig();
  } catch(e) {
    showSettingsErrors(['job_hunter.yml could not be saved. Retry, then run job-hunter doctor if the problem continues.']);
  } finally {
    btn.disabled = false;
  }
}

async function undoJobHunterConfig() {
  if (!confirm('Undo the last job_hunter.yml save? This restores the previous version.')) return;
  try {
    const result = await window.pywebview.api.undo_job_hunter_config();
    if (!result.ok) { alert((result.errors && result.errors[0]) || 'Nothing to undo.'); return; }
    await Promise.all([loadGuidedConfig(), loadRawConfig()]);
  } catch(e) {
    reportFailure('Undo could not be completed.');
  }
}

async function loadCareerContextSettings() {
  try {
    const result = await window.pywebview.api.get_career_context();
    careerContextRevision = result.data.revision;
    loadingCareerContext = true;
    document.getElementById('settings-career-context').value = result.data.text;
    loadingCareerContext = false;
    careerContextDirty = false;
    updateDirtyFlag('career-context');
  } catch(e) {
    showSettingsErrors(['career_context.md could not be loaded. Retry, then run job-hunter doctor if the problem continues.']);
  }
}

function markCareerContextDirty() {
  if (loadingCareerContext) return;
  careerContextDirty = true;
  updateDirtyFlag('career-context');
}

async function saveCareerContext() {
  const btn = document.querySelector('#settings-panel-career-context .btn-primary');
  const msg = document.getElementById('settings-career-context-msg');
  clearSettingsMessages();
  btn.disabled = true;
  try {
    const text = document.getElementById('settings-career-context').value;
    const result = await window.pywebview.api.save_career_context(text, careerContextRevision);
    if (!result.ok) { showSettingsErrors(result.errors); return; }
    careerContextRevision = result.data.revision;
    careerContextDirty = false;
    updateDirtyFlag('career-context');
    msg.textContent = '✓ Saved'; msg.style.color = '#56d364';
    setTimeout(() => { msg.textContent = ''; }, 2000);
    loadOnboarding();
  } catch(e) {
    showSettingsErrors(['career_context.md could not be saved. Retry, then run job-hunter doctor if the problem continues.']);
  } finally {
    btn.disabled = false;
  }
}

async function undoCareerContext() {
  if (!confirm('Undo the last career context save? This restores the previous version.')) return;
  try {
    const result = await window.pywebview.api.undo_career_context();
    if (!result.ok) { alert((result.errors && result.errors[0]) || 'Nothing to undo.'); return; }
    await loadCareerContextSettings();
  } catch(e) {
    reportFailure('Undo could not be completed.');
  }
}

// ── Companies ──
async function loadCompanies() {
  companiesLoaded = true;
  const tbody = document.getElementById('companies-tbody');
  try {
    const result = await window.pywebview.api.get_career_pages();
    companiesData = result.data.companies;
    companiesRevision = result.data.revision;
    selectedCompanyUrls.clear();
    companyRenderLimit = COMPANY_RENDER_STEP;
    renderCompanies();
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="7">${errorHtml('Companies could not be loaded.')}</td></tr>`;
  }
}

function companyLatestResultHtml(latest) {
  if (!latest) return '<span style="color:var(--text-muted)">never checked</span>';
  if (latest.status === 'ok') {
    const n = latest.jobs_inserted || 0;
    return `<span class="badge badge-candidate">${n} new</span>`;
  }
  return `<span class="badge badge-rejected" title="${esc(latest.failure_reason || '')}">failed</span>`;
}

function companyRowHtml(company) {
  const url = company.career_url || '';
  const enabled = company.enabled !== false;
  const checked = selectedCompanyUrls.has(url) ? 'checked' : '';
  return `<tr data-url="${esc(url)}">
    <td class="td-num"><input type="checkbox" class="company-checkbox" data-url="${esc(url)}" ${checked}></td>
    <td class="td-company">${esc(company.name || '—')}</td>
    <td class="td-title"><a href="#" data-open-url="${esc(url)}">${esc(url)}</a></td>
    <td>${esc(company.location || '—')}</td>
    <td><span class="badge badge-${enabled ? 'candidate' : 'discarded'}">${enabled ? 'Enabled' : 'Disabled'}</span></td>
    <td>${companyLatestResultHtml(company.latest_result)}</td>
    <td>
      <button class="btn" data-edit-url="${esc(url)}">Edit</button>
      <button class="btn btn-danger" data-delete-url="${esc(url)}">🗑</button>
    </td>
  </tr>`;
}

function renderCompanies() {
  const tbody = document.getElementById('companies-tbody');
  const query = document.getElementById('company-search').value.toLowerCase();
  const filtered = companiesData.filter(c => {
    const enabled = c.enabled !== false;
    if (companyEnabledFilter === 'enabled' && !enabled) return false;
    if (companyEnabledFilter === 'disabled' && enabled) return false;
    if (!query) return true;
    return `${c.name || ''} ${c.career_url || ''} ${c.location || ''}`.toLowerCase().includes(query);
  });
  document.getElementById('company-total-count').textContent = `${companiesData.length} companies`;
  if (!filtered.length) {
    document.getElementById('company-select-all').checked = false;
    tbody.innerHTML = `<tr><td colspan="7"><div class="no-data">No companies found</div></td></tr>`;
    updateCompanyBulkButtons();
    return;
  }
  // Cap the initial DOM render so a 2,000-company career_pages.yml doesn't build one
  // giant innerHTML string up front; "Show more" grows the cap on demand. Rows already
  // carry content-visibility:auto (shared table styling) for off-screen paint/layout cost.
  const visible = filtered.slice(0, companyRenderLimit);
  document.getElementById('company-select-all').checked = visible.every(c => selectedCompanyUrls.has(c.career_url));
  let rowsHtml = visible.map(companyRowHtml).join('');
  const remaining = filtered.length - visible.length;
  if (remaining > 0) {
    rowsHtml += `<tr><td colspan="7" style="text-align:center">
      <button class="btn" data-show-more-companies>Show ${Math.min(COMPANY_RENDER_STEP, remaining)} more (${remaining} not shown)</button>
    </td></tr>`;
  }
  tbody.innerHTML = rowsHtml;
  updateCompanyBulkButtons();
}

function showMoreCompanies() {
  companyRenderLimit += COMPANY_RENDER_STEP;
  renderCompanies();
}

function updateCompanyBulkButtons() {
  const n = selectedCompanyUrls.size;
  const deleteBtn = document.getElementById('company-bulk-delete-btn');
  deleteBtn.style.display = n ? '' : 'none';
  deleteBtn.textContent = `Delete selected (${n})`;
  document.getElementById('company-bulk-enable-btn').style.display = n ? '' : 'none';
  document.getElementById('company-bulk-disable-btn').style.display = n ? '' : 'none';
}

function toggleCompanySelected(url, checked) {
  if (checked) selectedCompanyUrls.add(url); else selectedCompanyUrls.delete(url);
  updateCompanyBulkButtons();
}

function toggleSelectAllCompanies(checked) {
  document.querySelectorAll('.company-checkbox').forEach(box => {
    box.checked = checked;
    if (checked) selectedCompanyUrls.add(box.dataset.url); else selectedCompanyUrls.delete(box.dataset.url);
  });
  updateCompanyBulkButtons();
}

function startEditCompany(url) {
  const company = companiesData.find(c => c.career_url === url);
  if (!company) return;
  editingCompanyUrl = url;
  document.getElementById('company-form-title').textContent = 'Edit Company';
  document.getElementById('company-form-name').value = company.name || '';
  document.getElementById('company-form-url').value = company.career_url || '';
  document.getElementById('company-form-location').value = company.location || '';
  document.getElementById('company-form-enabled').checked = company.enabled !== false;
  document.getElementById('company-form-submit').textContent = 'Save changes';
  document.getElementById('company-form-cancel').style.display = '';
  document.getElementById('company-form-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function cancelCompanyForm() {
  editingCompanyUrl = null;
  document.getElementById('company-form-title').textContent = 'Add Company';
  document.getElementById('company-form-name').value = '';
  document.getElementById('company-form-url').value = '';
  document.getElementById('company-form-location').value = '';
  document.getElementById('company-form-enabled').checked = true;
  document.getElementById('company-form-submit').textContent = 'Add company';
  document.getElementById('company-form-cancel').style.display = 'none';
  document.getElementById('company-form-msg').textContent = '';
}

async function submitCompanyForm() {
  const msg = document.getElementById('company-form-msg');
  const btn = document.getElementById('company-form-submit');
  const name = document.getElementById('company-form-name').value.trim();
  const url = document.getElementById('company-form-url').value.trim();
  const location = document.getElementById('company-form-location').value.trim();
  const enabled = document.getElementById('company-form-enabled').checked;

  const next = editingCompanyUrl
    ? companiesData.map(c => c.career_url === editingCompanyUrl ? { name, career_url: url, location, enabled } : c)
    : [...companiesData, { name, career_url: url, location, enabled }];

  msg.textContent = '';
  btn.disabled = true;
  try {
    const result = await window.pywebview.api.save_career_pages(next, companiesRevision);
    if (!result.ok) {
      msg.textContent = '✗ ' + ((result.errors && result.errors[0]) || 'Save failed.');
      msg.style.color = '#f85149';
      return;
    }
    companiesData = result.data.companies;
    companiesRevision = result.data.revision;
    cancelCompanyForm();
    renderCompanies();
  } catch(e) {
    msg.textContent = '✗ Company could not be saved. Retry, then run job-hunter doctor if the problem continues.';
    msg.style.color = '#f85149';
  } finally {
    btn.disabled = false;
  }
}

async function deleteCompanyByUrl(url) {
  const company = companiesData.find(c => c.career_url === url);
  const name = company ? company.name : url;
  if (!confirm(`Delete 1 company ("${name}") from career_pages.yml? This cannot be undone.`)) return;
  const next = companiesData.filter(c => c.career_url !== url);
  try {
    const result = await window.pywebview.api.save_career_pages(next, companiesRevision);
    if (!result.ok) { alert((result.errors && result.errors[0]) || 'Delete failed.'); return; }
    companiesData = result.data.companies;
    companiesRevision = result.data.revision;
    selectedCompanyUrls.delete(url);
    renderCompanies();
  } catch(e) {
    reportFailure('Company could not be deleted.');
  }
}

async function bulkDeleteCompanies() {
  const urls = [...selectedCompanyUrls];
  if (!urls.length) return;
  if (!confirm(`Delete ${urls.length} compan${urls.length === 1 ? 'y' : 'ies'} from career_pages.yml?`)) return;
  const next = companiesData.filter(c => !urls.includes(c.career_url));
  try {
    const result = await window.pywebview.api.save_career_pages(next, companiesRevision);
    if (!result.ok) { alert((result.errors && result.errors[0]) || 'Delete failed.'); return; }
    companiesData = result.data.companies;
    companiesRevision = result.data.revision;
    selectedCompanyUrls.clear();
    renderCompanies();
  } catch(e) {
    reportFailure('Companies could not be deleted.');
  }
}

async function bulkSetCompaniesEnabled(enabled) {
  const urls = [...selectedCompanyUrls];
  if (!urls.length) return;
  if (!confirm(`${enabled ? 'Enable' : 'Disable'} ${urls.length} compan${urls.length === 1 ? 'y' : 'ies'}?`)) return;
  const next = companiesData.map(c => urls.includes(c.career_url) ? { ...c, enabled } : c);
  try {
    const result = await window.pywebview.api.save_career_pages(next, companiesRevision);
    if (!result.ok) { alert((result.errors && result.errors[0]) || 'Could not update companies.'); return; }
    companiesData = result.data.companies;
    companiesRevision = result.data.revision;
    renderCompanies();
  } catch(e) {
    reportFailure('Companies could not be updated.');
  }
}

async function undoCareerPages() {
  if (!confirm('Undo the last career_pages.yml save? This restores the previous version.')) return;
  try {
    const result = await window.pywebview.api.undo_career_pages();
    if (!result.ok) { alert((result.errors && result.errors[0]) || 'Nothing to undo.'); return; }
    companiesData = result.data.companies;
    companiesRevision = result.data.revision;
    selectedCompanyUrls.clear();
    renderCompanies();
  } catch(e) {
    reportFailure('Undo could not be completed.');
  }
}

async function openCareerPage(url) {
  try {
    const result = await window.pywebview.api.open_career_page(url);
    if (!result.ok) alert(result.error || 'Could not open career page.');
  } catch(e) {
    reportFailure('Career page could not be opened.', 'Check the configured http/https URL and retry.');
  }
}

async function openCareerPagesFile() {
  const result = await window.pywebview.api.open_career_pages_file();
  if (!result.ok) alert(result.error || 'Could not open career_pages.yml.');
}

// ── Shared Catalog (bundled companies, opt-in per company or per sector) ──
async function loadCatalogIndustries() {
  catalogIndustriesLoaded = true;
  const select = document.getElementById('catalog-industry-filter');
  try {
    const result = await window.pywebview.api.get_catalog_industries();
    const options = result.data.industries
      .map(i => `<option value="${esc(i.id)}">${esc(i.label)} (${i.count})</option>`)
      .join('');
    select.insertAdjacentHTML('beforeend', options);
  } catch(e) { /* dropdown just stays at "All industries" */ }
}

function catalogRowHtml(company) {
  const checked = selectedCatalogIds.has(company.id) ? 'checked' : '';
  return `<tr data-id="${esc(company.id)}">
    <td class="td-num"><input type="checkbox" class="catalog-checkbox" data-id="${esc(company.id)}" ${checked}></td>
    <td class="td-company">${esc(company.name || '—')}</td>
    <td class="td-title"><a href="#" data-open-url="${esc(company.career_url)}">${esc(company.career_url)}</a></td>
    <td>${esc((company.country_codes || []).join(', ') || '—')}</td>
    <td><span class="badge badge-${company.enabled ? 'candidate' : 'discarded'}">${company.enabled ? 'Enabled' : 'Disabled'}</span></td>
  </tr>`;
}

async function loadCatalogPage() {
  const tbody = document.getElementById('catalog-tbody');
  tbody.innerHTML = `<tr><td colspan="5">${loadingHtml()}</td></tr>`;
  try {
    const search = document.getElementById('catalog-search').value;
    const result = await window.pywebview.api.get_catalog_page(catalogIndustry, search, catalogPage, 300, catalogEnabledFilter);
    if (!result.ok) throw new Error('not ok');
    catalogPageData = result.data;
    document.getElementById('catalog-total-count').textContent = `${catalogPageData.total} companies`;
    if (!catalogPageData.items.length) {
      tbody.innerHTML = `<tr><td colspan="5"><div class="no-data">No companies found</div></td></tr>`;
      document.getElementById('catalog-select-all').checked = false;
    } else {
      tbody.innerHTML = catalogPageData.items.map(catalogRowHtml).join('');
      document.getElementById('catalog-select-all').checked = catalogPageData.items.every(c => selectedCatalogIds.has(c.id));
    }
    renderCatalogPager();
    updateCatalogBulkButtons();
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="5">${errorHtml('Shared catalog could not be loaded.')}</td></tr>`;
  }
}

function renderCatalogPager() {
  const el = document.getElementById('catalog-pager');
  el.innerHTML = `<button class="btn" data-page-delta="-1" ${catalogPage <= 1 ? 'disabled' : ''}>Previous</button>
    <span>Page ${catalogPageData.page || 1} of ${catalogPageData.pages || 1} · ${catalogPageData.total || 0} results</span>
    <button class="btn" data-page-delta="1" ${catalogPage >= (catalogPageData.pages || 1) ? 'disabled' : ''}>Next</button>`;
}

function changeCatalogPage(delta) {
  const next = catalogPage + delta;
  if (next < 1 || next > (catalogPageData.pages || 1)) return;
  catalogPage = next;
  loadCatalogPage();
}

function updateCatalogBulkButtons() {
  const n = selectedCatalogIds.size;
  const enableBtn = document.getElementById('catalog-bulk-enable-btn');
  const disableBtn = document.getElementById('catalog-bulk-disable-btn');
  enableBtn.style.display = n ? '' : 'none';
  enableBtn.textContent = `Enable selected (${n})`;
  disableBtn.style.display = n ? '' : 'none';
  disableBtn.textContent = `Disable selected (${n})`;
}

function toggleCatalogSelected(id, checked) {
  if (checked) selectedCatalogIds.add(id); else selectedCatalogIds.delete(id);
  updateCatalogBulkButtons();
}

function toggleSelectAllCatalog(checked) {
  document.querySelectorAll('.catalog-checkbox').forEach(box => {
    box.checked = checked;
    if (checked) selectedCatalogIds.add(box.dataset.id); else selectedCatalogIds.delete(box.dataset.id);
  });
  updateCatalogBulkButtons();
}

async function bulkSetCatalogEnabled(enabled) {
  const ids = [...selectedCatalogIds];
  if (!ids.length) return;
  try {
    const result = await window.pywebview.api.save_catalog_enabled_ids(ids, enabled, catalogPageData.revision);
    if (!result.ok) { alert((result.errors && result.errors[0]) || 'Could not update the shared catalog.'); return; }
    selectedCatalogIds.clear();
    loadCatalogPage();
  } catch(e) {
    reportFailure('Shared catalog could not be updated.');
  }
}

async function openCatalogCompany(id) {
  try {
    const result = await window.pywebview.api.open_catalog_company(id);
    if (!result.ok) alert(result.error || 'Could not open career page.');
  } catch(e) {
    reportFailure('Career page could not be opened.');
  }
}

async function setCatalogShownEnabled(enabled) {
  // Works for "All industries" too — enables/disables every company matching the
  // current industry + search + enabled-state filter, not just what fits on one page.
  const label = document.getElementById('catalog-industry-filter').selectedOptions[0]?.textContent || 'All industries';
  const n = catalogPageData.total || 0;
  if (!confirm(`${enabled ? 'Enable' : 'Disable'} all ${n} shown compan${n === 1 ? 'y' : 'ies'} (${label})?`)) return;
  try {
    const search = document.getElementById('catalog-search').value;
    const result = await window.pywebview.api.save_catalog_filter_enabled(
      catalogIndustry, search, catalogEnabledFilter, enabled, catalogPageData.revision
    );
    if (!result.ok) { alert((result.errors && result.errors[0]) || 'Could not update the shared catalog.'); return; }
    loadCatalogPage();
  } catch(e) {
    reportFailure('Shared catalog could not be updated.');
  }
}

function openCatalogDetail(id) {
  const company = (catalogPageData.items || []).find(c => c.id === id);
  if (!company) return;
  activeCatalogId = id;
  document.getElementById('catalog-detail-panel').classList.add('open');
  document.getElementById('catdp-title').textContent = company.name || '—';
  const chips = [];
  if (company.country_codes && company.country_codes.length) {
    chips.push(`<span class="meta-chip">📍 ${esc(company.country_codes.join(', '))}</span>`);
  }
  chips.push(`<span class="meta-chip">${company.enabled ? 'Enabled' : 'Disabled'}</span>`);
  document.getElementById('catdp-meta').innerHTML = chips.join('');
  document.getElementById('catdp-link').textContent = `🔗 ${company.career_url}`;
  updateCatalogToggleButton(company.enabled);
}

function updateCatalogToggleButton(enabled) {
  const btn = document.getElementById('catdp-toggle-btn');
  btn.textContent = enabled ? 'Disable' : 'Enable';
  btn.classList.toggle('btn-danger', enabled);
  btn.classList.toggle('btn-primary', !enabled);
}

function closeCatalogDetail() {
  activeCatalogId = null;
  document.getElementById('catalog-detail-panel').classList.remove('open');
}

async function toggleCatalogDetailEnabled() {
  if (activeCatalogId == null) return;
  const company = (catalogPageData.items || []).find(c => c.id === activeCatalogId);
  if (!company) return;
  const nextEnabled = !company.enabled;
  try {
    const result = await window.pywebview.api.save_catalog_enabled_ids([activeCatalogId], nextEnabled, catalogPageData.revision);
    if (!result.ok) { alert((result.errors && result.errors[0]) || 'Could not update the shared catalog.'); return; }
    company.enabled = nextEnabled;
    updateCatalogToggleButton(nextEnabled);
    loadCatalogPage();
  } catch(e) {
    reportFailure('Shared catalog could not be updated.');
  }
}

async function openConfigFolder() {
  const result = await window.pywebview.api.open_config_folder();
  if (!result.ok) alert(result.error || 'Could not open config folder.');
}

// ── Utils ──
function esc(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Scraped job URLs are untrusted — block javascript:/data: schemes before use in an href.
function safeUrl(url) {
  const value = String(url || '').trim();
  return /^https?:\/\//i.test(value) ? esc(value) : '#';
}
