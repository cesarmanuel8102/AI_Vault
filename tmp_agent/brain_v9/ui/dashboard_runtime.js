const panelNames = {
  overview: 'Overview',
  platforms: 'Trading Platforms',
  strategy: 'Strategy Engine',
  autonomy: 'Autonomy Loop',
  roadmap: 'Roadmap & Governance',
  meta: 'Meta Systems',
  selfimprove: 'Self-Improvement',
  surgeon: 'Auto-Surgeon',
  learning: 'Learning & Adaptation',
  system: 'System Health'
};

function showPanel(id) {
  currentPanel = id;
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.sidebar-link').forEach(l => l.classList.remove('active'));
  const panel = document.getElementById('panel-'+id);
  if (panel) panel.classList.add('active');
  document.querySelectorAll('.sidebar-link').forEach(l => {
    if (l.getAttribute('onclick')?.includes("'"+id+"'")) l.classList.add('active');
  });
  document.getElementById('topbar-title').textContent = panelNames[id] || id;
  refreshCurrentPanel();
}

let _refreshing = false;
async function refreshCurrentPanel() {
  if (_refreshing) return;
  _refreshing = true;
  const panel = document.getElementById('panel-'+currentPanel);
  if (panel) {
    const oldErr = panel.querySelector(':scope > .err-msg');
    if (oldErr) oldErr.remove();
  }
  try {
    switch(currentPanel) {
      case 'overview': await refreshOverview(); break;
      case 'platforms': await refreshPlatforms(); break;
      case 'strategy': await refreshStrategy(); break;
      case 'autonomy': await refreshAutonomy(); break;
      case 'roadmap': await refreshRoadmap(); break;
      case 'meta': await refreshMeta(); break;
      case 'selfimprove': await refreshSelfImprove(); break;
      case 'surgeon': await refreshSurgeon(); break;
      case 'learning': await refreshLearning(); break;
      case 'system': await refreshSystem(); break;
    }
  } catch(e) {
    console.error('Refresh error:', e);
    const panel = document.getElementById('panel-'+currentPanel);
    if (panel && !panel.querySelector('.err-msg')) {
      panel.insertAdjacentHTML('afterbegin', `<div class="err-msg" style="margin-bottom:12px">${errorState('Refresh error', e.message||String(e))}</div>`);
    }
  } finally {
    _refreshing = false;
  }
  document.getElementById('topbar-time').textContent = new Date().toLocaleTimeString();
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(refreshCurrentPanel, 10000);
}

function initDashboardRuntime() {
  document.addEventListener('keydown', (event) => {
    const tab = event.target?.closest?.('.platform-tab');
    if (!tab) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      const pname = tab.getAttribute('data-platform');
      if (pname) switchPlatform(pname);
    }
  });
  refreshCurrentPanel();
  startAutoRefresh();
}
