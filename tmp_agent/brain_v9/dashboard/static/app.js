// Brain Operator Console — SPA controller (v5)
// Front: FRONT-BRAIN-UI-CHAT-LIVE-EXECUTION-TIMELINE-03
// Frontend-only. No tokens. No dangerous controls. Existing read-only endpoints only.

'use strict';

const REFRESH_MS = 10000;
const CHAT_TIMEOUT_MS = 60000;
const VIEWS = ['overview', 'agent', 'chat', 'trading', 'tools', 'memory', 'traces', 'safety', 'ops', 'roadmap'];

const S = {
  status: null,
  activity: null,
  scheduler: null,
  safety: null,
  queue: null,
  agentV2: null,
  tradingLive: null,
  lastRefresh: null,
  online: true,
  currentView: 'overview',
  chat: {
    mode: 'read_only',
    messages: [],
    busy: false,
    lastMeta: null,
    timeline: [],
    liveStatus: 'idle',
    currentRunId: null,
    requestStartedAt: null,
    elapsedTimer: null,
    elapsedText: '00:00',
    lastTrace: null,
    lastTraceStatus: 'not_loaded'
  }
};

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
function esc(s) { if (s == null) return ''; const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }
function nowIso() { return new Date().toISOString(); }
function fmtClock(ts) { if (!ts) return '—'; try { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); } catch { return '—'; } }
function ago(ts) { if (!ts) return '—'; const m = (Date.now() - new Date(ts).getTime()) / 60000; if (m < 1) return 'just now'; if (m < 60) return Math.round(m) + 'm ago'; return Math.round(m / 60) + 'h ago'; }
function safeArray(x) { return Array.isArray(x) ? x : []; }

async function getJSON(url, timeoutMs) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs || 8000);
  try {
    const r = await fetch(url, { signal: ctrl.signal, headers: { 'Accept': 'application/json' } });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}

async function refresh() {
  try {
    const [status, activity, scheduler, safety, queue, agentV2, tradingLive] = await Promise.all([
      getJSON('/brain-dashboard/status'),
      getJSON('/brain-dashboard/activity'),
      getJSON('/brain-dashboard/scheduler'),
      getJSON('/brain-dashboard/safety'),
      getJSON('/brain-dashboard/promotion-queue'),
      getJSON('/brain-dashboard/agent-v2/status'),
      getJSON('/brain-dashboard/trading-live', 12000)
    ]);
    S.status = status; S.activity = activity; S.scheduler = scheduler;
    S.safety = safety; S.queue = queue; S.agentV2 = agentV2; S.tradingLive = tradingLive;
    S.lastRefresh = new Date(); S.online = true;
    renderTopbar();
    if (S.currentView !== 'chat') renderCurrentView();
    else renderChatSidePanels();
  } catch (e) {
    S.online = false;
    renderTopbar();
    console.warn('refresh error', e);
  }
}

function renderTopbar() {
  const st = S.status || {};
  const brain = st.brain || {};
  const dash = st.dashboard || {};
  const ag = st.agent_v2 || {};
  const wd = st.watchdog || {};
  const sf = S.safety || {};
  const setChip = (id, text, state) => { const c = $(id); if (!c) return; c.textContent = text; c.dataset.state = state; };

  setChip('ts-brain', brain.ok ? 'Brain API ●' : 'Brain API ✕', brain.ok ? 'green' : 'red');
  setChip('ts-dash', dash.ok ? 'Dashboard ●' : 'Dashboard ✕', dash.ok ? 'green' : 'red');
  setChip('ts-backend', ag.ok ? ('Backend: ' + (ag.backend || '—')) : 'Backend: —', ag.ok ? 'green' : 'unknown');

  const prov = ag.latest_provider_used || (st.kimi && st.kimi.ok ? 'kimi' : '—');
  const degraded = ag.latest_provider_degraded;
  setChip('ts-provider', degraded ? 'Provider DEGRADED' : ('Provider: ' + prov), degraded ? 'yellow' : (prov !== '—' ? 'green' : 'unknown'));

  const memMutated = sf.canonical_semantic_mutated === true || sf.faiss_mutated === true;
  setChip('ts-memory', memMutated ? 'MEM MUTATED ⚠' : 'MEM LOCKED', memMutated ? 'yellow' : 'locked');
  const tl = S.tradingLive || {}; const qc = tl.qc || {}; const ib = tl.ibkr || {};
  setChip('ts-trading', 'TRADING LOCKED', 'locked');
  setChip('ts-qc', qc.ok ? ('QC: ' + (qc.activity_status || qc.overall_status || 'LIVE')) : 'QC: —', qc.ok && !qc.stale ? 'green' : (qc.ok ? 'yellow' : 'unknown'));
  setChip('ts-ibkr', ib.ok ? 'IBKR: connected' : (ib.port_open ? 'IBKR: port open' : 'IBKR: offline'), ib.ok ? 'green' : (ib.port_open ? 'yellow' : 'unknown'));
  setChip('ts-readonly', 'READ-ONLY', 'locked');

  const aut = st.autonomy || {};
  let aState = 'unknown', aText = 'Autonomy …';
  if (wd.stopped) { aState = 'red'; aText = 'Autonomy STOPPED'; }
  else if (wd.paused) { aState = 'yellow'; aText = 'Autonomy PAUSED'; }
  else if (aut.state) { aState = aut.state === 'running' ? 'green' : 'unknown'; aText = 'Autonomy: ' + aut.state; }
  setChip('ts-autonomy', aText, aState);

  const rf = $('ts-refresh');
  if (rf) rf.textContent = S.online ? ('↻ ' + ago(S.lastRefresh && S.lastRefresh.toISOString())) : '✕ offline';
}

function router() {
  const h = location.hash.replace('#/', '') || 'overview';
  const view = VIEWS.includes(h) ? h : 'overview';
  S.currentView = view;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === view));
  renderCurrentView();
}

function renderCurrentView() {
  const c = $('content');
  if (!S.status && S.currentView !== 'roadmap') {
    c.innerHTML = '<div class="loading-screen"><div class="spinner"></div><p>Connecting to Brain…</p></div>';
    return;
  }
  const fn = { overview: viewOverview, agent: viewAgent, chat: viewChat, trading: viewTrading, tools: viewTools,
               memory: viewMemory, traces: viewTraces, safety: viewSafety, ops: viewOps, roadmap: viewRoadmap }[S.currentView];
  c.innerHTML = fn ? fn() : viewOverview();
  if (S.currentView === 'chat') initChat();
}

function card(title, body, accent) {
  const ac = accent ? `<span class="tag ${accent}" style="float:right">●</span>` : '';
  return `<div class="card"><h3>${esc(title)}${ac}</h3>${body}</div>`;
}

function viewOverview() {
  const st = S.status || {}; const ag = st.agent_v2 || {}; const sf = S.safety || {};
  const mem = st.memory || {}; const wd = st.watchdog || {}; const aut = st.autonomy || {};
  const q = S.queue || {}; const sch = S.scheduler || {};
  const brain = st.brain || {}; const dash = st.dashboard || {}; const kimi = st.kimi || {};
  const capCount = ag.ok ? (ag.runtime_type ? '✓' : '—') : '—';
  const runs = ag.runs != null ? ag.runs : '—';
  const memMutated = sf.canonical_semantic_mutated === true || sf.faiss_mutated === true;

  let cards = '';
  cards += card('Service Health', `<div class="big">${brain.ok && dash.ok ? '●' : '✕'}</div><div class="label">Brain ${brain.ok ? 'OK' : 'DOWN'} · Dash ${dash.ok ? 'OK' : 'DOWN'}</div>`, brain.ok && dash.ok ? 'green' : 'red');
  cards += card('Agent V2', `<div class="big">${ag.canonical_for_new_agent_runs ? 'CANONICAL' : '—'}</div><div class="label">${esc(ag.backend || '—')}</div>`, ag.ok ? 'green' : 'yellow');
  cards += card('Capabilities', `<div class="big">${esc(capCount)}</div><div class="label">${esc(ag.runtime_type || '—')}</div>`, 'blue');
  cards += card('Recent Runs', `<div class="big">${esc(runs)}</div><div class="label">${esc(ag.latest_run_id ? ag.latest_run_id.slice(0, 8) : 'no runs')}</div>`, 'blue');
  cards += card('Provider', `<div class="big">${kimi.ok ? '●' : '✕'}</div><div class="label">${esc(kimi.status || '—')}</div>`, kimi.ok ? 'green' : 'yellow');
  cards += card('Safety Locks', `<div class="big">${memMutated ? '⚠' : '⛨'}</div><div class="label">${memMutated ? 'mutation detected' : 'all locked'}</div>`, memMutated ? 'yellow' : 'green');
  cards += card('Memory', `<div class="big">${esc(mem.journal_count != null ? mem.journal_count : '—')}</div><div class="label">journal events</div>`, 'blue');
  cards += card('Promotion Queue', `<div class="big">${esc(q.count != null ? q.count : '—')}</div><div class="label">${esc(mem.promotion_queue_active_review_required_count || 0)} need review</div>`, (mem.promotion_queue_active_review_required_count || 0) > 0 ? 'yellow' : 'gray');
  cards += card('Dashboard EPs', `<div class="big">●</div><div class="label">LIVE on 8092</div>`, 'green');

  let alertsHtml = '';
  (st.alerts || []).forEach(a => {
    const cls = a.severity === 'BLOCKED' ? 'red' : (a.severity === 'LOW' ? 'yellow' : 'green');
    alertsHtml += `<span class="tag ${cls}">${esc(a.severity)}</span> ${esc(a.message || a.code)}<br>`;
  });
  if (!alertsHtml) alertsHtml = '<span class="tag gray">NOMINAL</span> No active alerts.';

  return `
    <div class="page-head"><div><h1>Overview</h1><div class="sub">Live operational snapshot · refreshed ${ago(S.lastRefresh && S.lastRefresh.toISOString())}</div></div></div>
    <div class="grid g-4" style="margin-bottom:18px">${cards}</div>
    <div class="grid g-2">
      <div class="panel"><h2>What Brain is Doing Now</h2><div class="kv">
        <div class="item"><div class="k">State</div><div class="v">${esc(wd.stopped ? 'Stopped' : (wd.paused ? 'Paused' : (aut.state || 'idle')))}</div></div>
        <div class="item"><div class="k">Cycle</div><div class="v">${esc(aut.cycle || '—')}</div></div>
        <div class="item"><div class="k">Last Run</div><div class="v">${esc(ago(aut.last_run_time))}</div></div>
        <div class="item"><div class="k">Last Result</div><div class="v">${esc(aut.last_run_result || '—')}</div></div>
        <div class="item"><div class="k">Scheduler</div><div class="v">${esc(sch.enabled ? 'Enabled' : 'Disabled')}</div></div>
        <div class="item"><div class="k">Next Run</div><div class="v">${esc(sch.next_run_time || '—')}</div></div>
      </div></div>
      <div class="panel"><h2>Alerts & Recommendations</h2><div style="font-size:13px;line-height:1.9">${alertsHtml}</div>
      <div style="margin-top:10px;font-size:12px;color:var(--text-mute)">Recommendation: ${esc(st.recommendation || '—')}</div></div>
    </div>`;
}

function viewAgent() {
  const ag = (S.agentV2 && S.agentV2.agent_v2) || (S.status && S.status.agent_v2) || {};
  if (!ag.ok) return panelErr('Agent V2 status unavailable.', ag.error);
  return `
    <div class="page-head"><div><h1>Agent V2</h1><div class="sub">Canonical agent runtime details</div></div>
      <span class="tag ${ag.canonical_for_new_agent_runs ? 'green' : 'yellow'}">${ag.canonical_for_new_agent_runs ? 'CANONICAL' : 'NON-CANONICAL'}</span></div>
    <div class="grid g-2">
      <div class="panel"><h2>Backend</h2><div class="kv">
        <div class="item"><div class="k">Backend</div><div class="v">${esc(ag.backend || '—')}</div></div>
        <div class="item"><div class="k">Backend Default</div><div class="v">${esc(ag.backend_default || '—')}</div></div>
        <div class="item"><div class="k">Runtime Type</div><div class="v">${esc(ag.runtime_type || '—')}</div></div>
        <div class="item"><div class="k">Rollback Backend</div><div class="v">${esc(ag.rollback_backend || '—')}</div></div>
        <div class="item"><div class="k">LangGraph Default</div><div class="v">${ag.langgraph_default_active ? '✓ Active' : '✕'}</div></div>
        <div class="item"><div class="k">Fallback Used</div><div class="v">${ag.backend_fallback_used ? '⚠ ' + esc(ag.backend_fallback_reason || '') : 'No'}</div></div>
      </div></div>
      <div class="panel"><h2>Provider & Runs</h2><div class="kv">
        <div class="item"><div class="k">Finalizer Model</div><div class="v">${esc(ag.primary_finalizer_model || '—')}</div></div>
        <div class="item"><div class="k">Latest Provider</div><div class="v">${esc(ag.latest_provider_used || '—')}</div></div>
        <div class="item"><div class="k">Latest Model</div><div class="v">${esc(ag.latest_model_used || '—')}</div></div>
        <div class="item"><div class="k">Provider Degraded</div><div class="v">${ag.latest_provider_degraded ? '⚠ YES' : '✓ No'}</div></div>
        <div class="item"><div class="k">Run Count</div><div class="v">${esc(ag.runs != null ? ag.runs : '—')}</div></div>
        <div class="item"><div class="k">Latest Run ID</div><div class="v">${esc(ag.latest_run_id || '—')}</div></div>
      </div></div>
      <div class="panel"><h2>Capability Registry</h2><div class="kv">
        <div class="item"><div class="k">Capabilities Version</div><div class="v">08F8-R1</div></div>
        <div class="item"><div class="k">Read-Only Mode</div><div class="v"><span class="tag blue">READ-ONLY</span></div></div>
        <div class="item"><div class="k">Tools Available</div><div class="v">PLACEHOLDER — endpoint not exposed</div></div>
        <div class="item"><div class="k">Tools Blocked</div><div class="v">PLACEHOLDER — endpoint not exposed</div></div>
      </div></div>
      <div class="panel"><h2>Known Caveats</h2><div style="font-size:12.5px;color:var(--text-dim);line-height:1.7">
        • 6 trading/refusal prompts scored 4/5 (minor refusal explicitness).<br>
        • Autonomy R2 not active. Broker/trading locked.<br>
        • Memory/semantic/FAISS writes locked.<br>
        • Dashboard endpoint analysis incomplete (no route probe) — planner observation.
      </div></div>
    </div>`;
}

const MODE_LABELS = { read_only: 'READ', build: 'BUILD', auto: 'AUTO' };
const MODE_BADGE = { read_only: 'READ_ONLY', build: 'BUILD', auto: 'AUTO' };
const MODE_HINTS = {
  read_only: 'Safe read-only diagnosis',
  build: 'Draft/build mode — approval-gated',
  auto: 'Auto routing — governance still enforced'
};

function viewChat() {
  return `
    <div class="chat-workspace">
      <aside class="chat-side">
        <button class="new-chat" id="chat-new">✎ New chat</button>
        <div id="chat-session-card">${renderSessionCard()}</div>
        <div id="chat-live-exec">${renderLiveExecutionPanel()}</div>
        <div id="chat-agent-signals">${renderAgentSignals()}</div>
      </aside>
      <section class="chat-main">
        <div class="chat-msgs" id="chat-msgs"></div>
        <div class="chat-composer">
          <div class="mode-segment" id="chat-mode-segment" role="tablist" aria-label="Chat mode">
            <button class="mode-btn active" data-mode="read_only" role="tab" aria-selected="true" title="Safe read-only diagnosis">
              <span class="mode-ico">📖</span> READ <span class="mode-sub">read-only</span>
            </button>
            <button class="mode-btn" data-mode="build" role="tab" aria-selected="false" title="Draft/build mode — approval-gated">
              <span class="mode-ico">🔨</span> BUILD <span class="mode-sub">approval-gated</span>
            </button>
            <button class="mode-btn" data-mode="auto" role="tab" aria-selected="false" title="Auto routing — governance still enforced">
              <span class="mode-ico">⚙</span> AUTO <span class="mode-sub">governance-enforced</span>
            </button>
          </div>
          <div class="composer-wrap">
            <textarea class="composer-ta" id="chat-input" placeholder="Ask Brain something…  (Enter to send, Shift+Enter for newline)" rows="1"></textarea>
            <div class="composer-actions">
              <span class="mode-badge" style="font-size:10px;padding:2px 7px" id="chat-mode-badge">READ_ONLY</span>
              <button class="btn primary sm" id="chat-send">Send</button>
            </div>
          </div>
          <div class="composer-meta">
            <span id="chat-mode-help">Mode selection does not bypass governance. Writes, memory mutation, trading and commits remain locked unless backend explicitly requires and receives approval.</span>
            <span id="chat-status">Ready</span>
          </div>
        </div>
      </section>
      <aside class="chat-inspector" id="chat-inspector">
        <div class="insp-card"><h4>Run Inspector</h4>
          <div class="ik">Run ID</div><div class="iv" id="insp-runid">—</div>
          <div class="ik">Classification</div><div class="iv" id="insp-class">—</div>
          <div class="ik">Model / Provider</div><div class="iv" id="insp-model">—</div>
          <div class="ik">Mode Requested</div><div class="iv" id="insp-mode-req">—</div>
          <div class="ik">Mode Effective</div><div class="iv" id="insp-mode-eff">—</div>
          <div class="ik">Auto Decision</div><div class="iv" id="insp-auto-dec">—</div>
        </div>
        <div class="insp-card" id="insp-escalation-card" style="display:none"><h4>Escalation / Approval</h4>
          <div class="ik">Escalation Required</div><div class="iv" id="insp-esc-req">—</div>
          <div class="ik">Reason</div><div class="iv" id="insp-esc-reason">—</div>
          <div class="ik">Required Permission</div><div class="iv" id="insp-perm">—</div>
          <div class="ik">Expected Write Scope</div><div class="iv" id="insp-scope">—</div>
          <div class="ik">Confirmation ID</div><div class="iv" id="insp-conf">—</div>
        </div>
        <div class="insp-card"><h4>Tools & Evidence</h4>
          <div class="ik">Blocked Tools</div><div class="iv" id="insp-blocked">—</div>
          <div class="ik">Trace</div><div class="iv" id="insp-trace">—</div>
        </div>
        <div class="insp-card"><h4>Safety Locks</h4>
          <div class="iv"><span class="tag blue">MEM LOCKED</span> <span class="tag blue">TRADING LOCKED</span></div>
        </div>
      </aside>
    </div>`;
}

function initChat() {
  renderChatMsgs();
  renderChatSidePanels();
  syncModeUI();
  const ta = $('chat-input');
  if (ta) {
    ta.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
    ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'; });
  }
  const send = $('chat-send');
  if (send) send.addEventListener('click', sendChat);
  const nw = $('chat-new');
  if (nw) nw.addEventListener('click', () => {
    S.chat.messages = [];
    S.chat.lastMeta = null;
    S.chat.currentRunId = null;
    S.chat.lastTrace = null;
    resetTimeline();
    renderChatMsgs();
    renderChatSidePanels();
    if ($('chat-input')) $('chat-input').focus();
  });
  document.querySelectorAll('#chat-mode-segment .mode-btn').forEach(btn => {
    btn.addEventListener('click', () => setMode(btn.dataset.mode));
  });
  if (!S.chat.timeline.length) resetTimeline();
}

function setMode(mode) {
  if (!['read_only', 'build', 'auto'].includes(mode)) return;
  S.chat.mode = mode;
  syncModeUI();
  renderChatSidePanels();
}

function syncModeUI() {
  const m = S.chat.mode;
  document.querySelectorAll('#chat-mode-segment .mode-btn').forEach(btn => {
    const active = btn.dataset.mode === m;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  const badge = $('chat-mode-badge');
  if (badge) badge.textContent = MODE_BADGE[m] || m.toUpperCase();
  const navMode = $('nav-mode');
  if (navMode) navMode.textContent = MODE_BADGE[m] || m.toUpperCase();
  const statusLine = $('chat-status');
  if (statusLine && !S.chat.busy) statusLine.textContent = 'Mode: ' + (MODE_LABELS[m] || m);
}

function resetTimeline() {
  S.chat.timeline = [];
  S.chat.liveStatus = 'idle';
  S.chat.requestStartedAt = null;
  S.chat.elapsedText = '00:00';
  S.chat.lastTraceStatus = 'not_loaded';
  addTimelineEvent('idle', 'Waiting for request', 'pending', 'Select READ, BUILD, or AUTO and send a prompt.');
}

function addTimelineEvent(id, label, status, detail) {
  const existing = S.chat.timeline.find(x => x.id === id);
  const item = { id, label, status: status || 'pending', detail: detail || '', time: nowIso() };
  if (existing) Object.assign(existing, item);
  else S.chat.timeline.push(item);
  renderChatSidePanels();
}

function updateTimelineEvent(id, status, detail) {
  const item = S.chat.timeline.find(x => x.id === id);
  if (!item) return addTimelineEvent(id, id, status, detail);
  item.status = status || item.status;
  if (detail != null) item.detail = detail;
  item.time = nowIso();
  renderChatSidePanels();
}

function startElapsedTimer() {
  stopElapsedTimer();
  S.chat.requestStartedAt = Date.now();
  S.chat.elapsedTimer = setInterval(() => {
    const sec = Math.floor((Date.now() - S.chat.requestStartedAt) / 1000);
    S.chat.elapsedText = String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0');
    renderChatSidePanels();
  }, 1000);
}

function stopElapsedTimer() {
  if (S.chat.elapsedTimer) clearInterval(S.chat.elapsedTimer);
  S.chat.elapsedTimer = null;
}

function renderSessionCard() {
  const meta = S.chat.lastMeta || {};
  const mode = MODE_LABELS[S.chat.mode] || S.chat.mode.toUpperCase();
  const shortRun = (S.chat.currentRunId || meta.run_id || '—');
  const runShort = shortRun && shortRun !== '—' ? String(shortRun).slice(0, 12) + '…' : '—';
  return `
    <div class="live-card session-card">
      <div class="live-card-title">Current Session</div>
      <div class="signal-row"><span>Persistence</span><strong>In-memory only</strong></div>
      <div class="signal-row"><span>Selected mode</span><strong>${esc(mode)}</strong></div>
      <div class="signal-row"><span>Safety</span><strong>Mem/trading locked</strong></div>
      <div class="signal-row"><span>Last run</span><code>${esc(runShort)}</code></div>
    </div>`;
}

function renderLiveExecutionPanel() {
  const status = S.chat.liveStatus || 'idle';
  const items = S.chat.timeline.length ? S.chat.timeline : [{ id:'idle', label:'Waiting for request', status:'pending', detail:'No active request.', time:null }];
  return `
    <div class="live-card live-exec">
      <div class="live-header">
        <div>
          <div class="live-card-title">Live Execution</div>
          <div class="live-sub">Server-driven events · trace-enriched after response</div>
        </div>
        <div class="live-header-right">
          <span class="live-status-pill ${esc(status)}">${esc(status.toUpperCase())}</span>
          <span class="live-timer">${esc(S.chat.elapsedText || '00:00')}</span>
        </div>
      </div>
      <div class="timeline-list">
        ${items.map(renderTimelineItem).join('')}
      </div>
    </div>`;
}

function renderTimelineItem(item) {
  const cls = item.status || 'pending';
  return `
    <div class="timeline-item ${esc(cls)}">
      <div class="timeline-dot"></div>
      <div class="timeline-body">
        <div class="timeline-label">${esc(item.label)}</div>
        <div class="timeline-detail">${esc(item.detail || '—')}</div>
        <div class="timeline-time">${esc(item.time ? fmtClock(item.time) : '—')}</div>
      </div>
    </div>`;
}

function renderAgentSignals() {
  const meta = S.chat.lastMeta || {};
  const degraded = meta.provider_degraded === true;
  const traceStatus = S.chat.lastTraceStatus || 'not_loaded';
  const tools = traceToolsCount(S.chat.lastTrace);
  const evidence = traceEvidenceCount(S.chat.lastTrace);
  return `
    <div class="live-card agent-signals">
      <div class="live-card-title">Agent Signals</div>
      <div class="signal-row"><span>Provider</span><strong>${esc((meta.provider_used || 'NOT EXPOSED'))}</strong></div>
      <div class="signal-row"><span>Model</span><strong>${esc((meta.model_used || 'NOT EXPOSED'))}</strong></div>
      <div class="signal-row"><span>Class</span><strong>${esc(meta.classification || 'NOT EXPOSED')}</strong></div>
      <div class="signal-row"><span>Trace</span><strong>${esc(traceStatus.toUpperCase())}</strong></div>
      <div class="signal-row"><span>Tools</span><strong>${tools == null ? 'NOT EXPOSED' : tools}</strong></div>
      <div class="signal-row"><span>Evidence</span><strong>${evidence == null ? 'NOT EXPOSED' : evidence}</strong></div>
      <div class="signal-row"><span>Fallback</span><strong>${degraded ? 'DEGRADED' : (fallbackReasonActive(meta) ? meta.fallback_reason : 'none')}</strong></div>
      <div class="signal-row"><span>Blocked</span><strong>${safeArray(meta.blocked_tools).length ? safeArray(meta.blocked_tools).join(', ') : 'none'}</strong></div>
    </div>`;
}

function renderChatSidePanels() {
  const session = $('chat-session-card'); if (session) session.innerHTML = renderSessionCard();
  const live = $('chat-live-exec'); if (live) live.innerHTML = renderLiveExecutionPanel();
  const sig = $('chat-agent-signals'); if (sig) sig.innerHTML = renderAgentSignals();
}

function traceToolsCount(trace) {
  if (!trace) return null;
  if (Array.isArray(trace.tools)) return trace.tools.length;
  if (Array.isArray(trace.executed_tools)) return trace.executed_tools.length;
  if (Array.isArray(trace.tool_calls)) return trace.tool_calls.length;
  const s = JSON.stringify(trace);
  const matches = s.match(/tool[_-]?(call|executed|execution|result)/gi);
  return matches ? matches.length : null;
}

function traceEvidenceCount(trace) {
  if (!trace) return null;
  if (Array.isArray(trace.evidence)) return trace.evidence.length;
  if (Array.isArray(trace.evidence_used)) return trace.evidence_used.length;
  if (Array.isArray(trace.memory_hits)) return trace.memory_hits.length;
  const s = JSON.stringify(trace);
  const matches = s.match(/evidence|memory_hit|semantic_retrieve/gi);
  return matches ? matches.length : null;
}

function fallbackReasonActive(j) {
  return !!(j && j.fallback_reason && j.fallback_reason !== 'none' && j.fallback_reason !== '');
}

async function loadTraceForRun(runId) {
  if (!runId) return;
  S.chat.lastTraceStatus = 'loading';
  addTimelineEvent('trace_loading', 'Trace loading', 'running', 'Fetching trace after response completion.');
  try {
    const trace = await getJSON('/brain-dashboard/agent-v2/runs/' + encodeURIComponent(runId) + '/trace', 12000);
    S.chat.lastTrace = trace;
    S.chat.lastTraceStatus = 'loaded';
    updateTimelineEvent('trace_loading', 'done', 'Trace loaded.');
    enrichTimelineFromTrace(trace);
  } catch (e) {
    S.chat.lastTraceStatus = 'unavailable';
    updateTimelineEvent('trace_loading', 'failed', 'Trace unavailable: ' + e.message);
  }
  renderChatSidePanels();
}

function enrichTimelineFromTrace(trace) {
  if (!trace) return;
  const tools = traceToolsCount(trace);
  const evidence = traceEvidenceCount(trace);
  if (tools == null) addTimelineEvent('trace_tools', 'Tools / plan', 'skipped', 'NOT EXPOSED by current trace payload.');
  else addTimelineEvent('trace_tools', 'Tools inspected', 'done', tools + ' trace tool signal(s) detected.');
  if (evidence == null) addTimelineEvent('trace_evidence', 'Evidence', 'skipped', 'NOT EXPOSED by current trace payload.');
  else addTimelineEvent('trace_evidence', 'Evidence collected', 'done', evidence + ' evidence signal(s) detected.');
  const s = JSON.stringify(trace);
  if (/governance|blocked|approval/i.test(s)) addTimelineEvent('trace_governance', 'Governance checked', 'done', 'Governance / block / approval signals present in trace.');
  else addTimelineEvent('trace_governance', 'Governance checked', 'skipped', 'NOT EXPOSED by current trace payload.');
  if (/provider|model|finalizer|fallback/i.test(s)) addTimelineEvent('trace_provider', 'Provider/finalizer metadata', 'done', 'Provider/finalizer signals present in trace.');
  else addTimelineEvent('trace_provider', 'Provider/finalizer metadata', 'skipped', 'NOT EXPOSED by current trace payload.');
}

function renderChatMsgs() {
  const box = $('chat-msgs');
  if (!box) return;
  if (!S.chat.messages.length) {
    box.innerHTML = `<div class="empty-state"><div class="ico">✎</div><div style="font-size:15px;font-weight:600">Start a conversation</div>
      <div>Ask Brain anything. The left panel shows live execution events during the request and trace metadata after the response.</div></div>`;
    return;
  }
  box.innerHTML = '';
  S.chat.messages.forEach(m => {
    const av = m.role === 'user' ? 'You' : '◆';
    const bubble = m.role === 'assistant' ? renderMarkdown(m.content) : esc(m.content);
    const warn = m.warnings ? m.warnings.map(w => `<div class="msg-warn ${w.type}">${esc(w.text)}</div>`).join('') : '';
    let modeTag = '';
    if (m.role === 'user' && m.mode) modeTag = `<div class="msg-mode-tag"><span class="tag gray" style="font-size:9px">${esc((MODE_LABELS[m.mode] || m.mode.toUpperCase()))}</span></div>`;
    let escCard = '';
    if (m.role === 'assistant' && m.escalation && m.escalation.required) {
      escCard = `<div class="msg-escalation"><div class="esc-head">⚠ Approval Required</div>` +
        (m.escalation.reason ? `<div class="esc-row"><span class="esc-k">Reason:</span> ${esc(m.escalation.reason)}</div>` : '') +
        (m.escalation.permission ? `<div class="esc-row"><span class="esc-k">Permission:</span> ${esc(m.escalation.permission)}</div>` : '') +
        (m.escalation.scope ? `<div class="esc-row"><span class="esc-k">Write scope:</span> ${esc(m.escalation.scope)}</div>` : '') +
        (m.escalation.confirmation_id ? `<div class="esc-row"><span class="esc-k">Confirmation ID:</span> <code style="font-family:var(--mono);font-size:11px">${esc(m.escalation.confirmation_id)}</code></div>` : '') +
        `<div class="esc-note">No write was executed. Operator approval is required to proceed.</div></div>`;
    }
    const wrap = el('div', 'msg ' + m.role);
    wrap.innerHTML = `<div class="msg-avatar">${av}</div><div class="msg-bubble">${bubble}${modeTag}${warn}${escCard}</div>`;
    box.appendChild(wrap);
  });
  box.scrollTop = box.scrollHeight;
}

async function sendChat() {
  if (S.chat.busy) return;
  const ta = $('chat-input');
  const text = ta.value.trim();
  if (!text) return;
  const sentMode = S.chat.mode;

  S.chat.messages.push({ role: 'user', content: text, mode: sentMode });
  ta.value = ''; ta.style.height = 'auto';
  S.chat.busy = true;
  S.chat.currentRunId = null;
  S.chat.lastTrace = null;
  S.chat.lastTraceStatus = 'trace_pending';
  S.chat.liveStatus = 'running';
  $('chat-send').disabled = true; $('chat-status').textContent = 'Thinking…';

  S.chat.timeline = [];
  startElapsedTimer();

  S.chat.messages.push({ role: 'assistant', content: '…', loading: true });
  renderChatMsgs();
  renderChatSidePanels();

  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), CHAT_TIMEOUT_MS);
  try {
    const streamOk = await sendChatStream(text, sentMode, ctrl);
    clearTimeout(to);
    if (!streamOk) {
      // Fallback to legacy non-streaming endpoint
      await sendChatLegacy(text, sentMode);
    }
  } catch (e) {
    clearTimeout(to);
    S.chat.messages.pop();
    const isTimeout = e && e.name === 'AbortError';
    S.chat.liveStatus = isTimeout ? 'timeout' : 'failed';
    addTimelineEvent(isTimeout ? 'timeout' : 'request_failed', isTimeout ? 'Timeout' : 'Request failed', 'failed', isTimeout ? 'UI request timeout; no write action was attempted.' : e.message);
    S.chat.messages.push({ role: 'assistant', content: '⚠ **Connection error:** ' + (isTimeout ? 'Request timed out after 60s.' : e.message) + '\n\nThe live timeline keeps this as a failed/timeout request. No write action was attempted.' });
  } finally {
    stopElapsedTimer();
    S.chat.busy = false;
    if ($('chat-send')) $('chat-send').disabled = false;
    if ($('chat-status')) $('chat-status').textContent = 'Ready';
    renderChatMsgs();
    renderChatSidePanels();
    syncModeUI();
  }
}

async function sendChatStream(text, sentMode, ctrl) {
  const SSE_EVENT_MAP = {
    'request.accepted': { label: 'Request accepted', icon: 'done' },
    'mode.selected': { label: 'Mode selected', icon: 'done' },
    'backend.call.started': { label: 'Backend call started', icon: 'running' },
    'backend.call.completed': { label: 'Backend completed', icon: 'done' },
    'response.metadata': { label: 'Run metadata received', icon: 'done' },
    'response.final': { label: 'Response received', icon: 'done' },
    'trace.fetch.started': { label: 'Trace loading', icon: 'running' },
    'trace.fetch.completed': { label: 'Trace loaded', icon: 'done' },
    'trace.enriched': { label: 'Trace enriched', icon: 'done' },
    'trace.limit': { label: 'Runtime limitation', icon: 'skipped' },
    'stream.completed': { label: 'Complete', icon: 'done' },
    'stream.error': { label: 'Stream error', icon: 'failed' },
  };

  let firstEventReceived = false;
  let metadata = {};
  const content = { value: '' };

  try {
    const r = await fetch('/brain-dashboard/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: ctrl.signal,
      body: JSON.stringify({ message: text, mode: sentMode, user_id: 'dashboard_operator' })
    });

    if (!r.ok || !r.body) {
      return false; // signal fallback
    }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Parse complete SSE messages (separated by \n\n)
      let idx;
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const rawEvent = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        let eventName = '';
        let eventData = {};
        for (const line of rawEvent.split('\n')) {
          if (line.startsWith('event: ')) eventName = line.slice(7).trim();
          else if (line.startsWith('data: ')) {
            try { eventData = JSON.parse(line.slice(6)); } catch { eventData = {}; }
          }
        }

        if (!eventName) continue;
        firstEventReceived = true;
        handleSSEEvent(eventName, eventData, SSE_EVENT_MAP, metadata, content);
      }
    }

    // Process any remaining buffer
    if (buffer.trim()) {
      let eventName = '';
      let eventData = {};
      for (const line of buffer.split('\n')) {
        if (line.startsWith('event: ')) eventName = line.slice(7).trim();
        else if (line.startsWith('data: ')) {
          try { eventData = JSON.parse(line.slice(6)); } catch { eventData = {}; }
        }
      }
      if (eventName) {
        firstEventReceived = true;
        handleSSEEvent(eventName, eventData, SSE_EVENT_MAP, metadata, content);
      }
    }

    return firstEventReceived;
  } catch (e) {
    if (!firstEventReceived) return false; // fallback
    throw e;
  }
}

function handleSSEEvent(eventName, data, SSE_EVENT_MAP, metadata, content) {
  const mapping = SSE_EVENT_MAP[eventName] || { label: eventName, icon: 'done' };
  const status = mapping.icon === 'running' ? 'running' :
                 mapping.icon === 'failed' ? 'failed' :
                 mapping.icon === 'skipped' ? 'skipped' : 'done';

  let detail = data.message || '';
  switch (eventName) {
    case 'request.accepted':
      addTimelineEvent('request_accepted', mapping.label, 'done', 'Stream opened.');
      break;
    case 'mode.selected':
      addTimelineEvent('mode_selected', mapping.label, 'done', (data.mode_requested || '') + ' (' + (data.message_length || 0) + ' chars)');
      break;
    case 'backend.call.started':
      addTimelineEvent('backend_started', mapping.label, 'running', 'POST /v2/chat/agent via 8092 proxy');
      break;
    case 'backend.call.completed':
      updateTimelineEvent('backend_started', 'done', 'Brain returned a response.');
      addTimelineEvent('backend_completed', mapping.label, 'done',
        'Status: ' + (data.ok ? 'completed' : 'failed') +
        (data.run_id ? ' · Run: ' + String(data.run_id).slice(0, 12) : ''));
      break;
    case 'response.metadata':
      metadata.value = data;
      if (data.run_id) {
        S.chat.currentRunId = data.run_id;
        addTimelineEvent('run_id', 'Run ID received', 'done', String(data.run_id));
      }
      if (data.classification) addTimelineEvent('classification', 'Classification', 'done', data.classification);
      if (data.provider_used || data.model_used)
        addTimelineEvent('provider_model', 'Provider/model', 'done', (data.provider_used || '—') + ' / ' + (data.model_used || '—'));
      addTimelineEvent('mode_effective', 'Mode effective', 'done', (data.mode_requested || '') + ' → ' + (data.mode_effective || '—'));
      if (data.blocked_tools && data.blocked_tools.length)
        addTimelineEvent('blocked_tools', 'Tools blocked', 'skipped', data.blocked_tools.join(', '));
      if (data.provider_degraded)
        addTimelineEvent('provider_degraded', 'Provider degraded', 'failed', data.fallback_reason || 'Provider degradation reported.');
      updateInspector(data);
      S.chat.lastMeta = data;
      break;
    case 'response.final':
      content.value = data.content || '';
      S.chat.messages.pop();
      const warnings = [];
      if (metadata.value && metadata.value.provider_degraded)
        warnings.push({ type: 'degraded', text: '⚠ Provider degraded. Fallback: ' + (metadata.value.fallback_reason || 'unknown') });
      if (metadata.value && metadata.value.raw_cot_exposed)
        warnings.push({ type: 'cot', text: '🚨 RAW CHAIN-OF-THOUGHT EXPOSED' });
      S.chat.liveStatus = 'completed';
      S.chat.messages.push({ role: 'assistant', content: data.content || '(no response)', warnings });
      renderChatMsgs();
      break;
    case 'trace.fetch.started':
      S.chat.lastTraceStatus = 'loading';
      addTimelineEvent('trace_loading', mapping.label, 'running', 'Fetching trace after response.');
      break;
    case 'trace.fetch.completed':
      S.chat.lastTraceStatus = data.ok ? 'loaded' : 'unavailable';
      updateTimelineEvent('trace_loading', data.ok ? 'done' : 'failed', data.ok ? 'Trace loaded.' : 'Trace unavailable.');
      break;
    case 'trace.enriched':
      addTimelineEvent('trace_enriched', mapping.label, 'done',
        'Tools: ' + (data.tools_count != null ? data.tools_count : 'N/A') +
        ' · Evidence: ' + (data.evidence_count != null ? data.evidence_count : 'N/A') +
        (data.governance_signals ? ' · Governance ✓' : '') +
        (data.provider_signals ? ' · Provider ✓' : ''));
      break;
    case 'trace.limit':
      addTimelineEvent('trace_limit', mapping.label, 'skipped', data.message || 'Live tool events not exposed.');
      break;
    case 'stream.completed':
      if (data.run_id && !S.chat.currentRunId) {
        S.chat.currentRunId = data.run_id;
      }
      // Fetch trace if we have run_id but haven't loaded it yet
      if (data.run_id && S.chat.lastTraceStatus === 'trace_pending') {
        S.chat.lastTraceStatus = 'loading';
        renderChatSidePanels();
        loadTraceForRun(data.run_id);
      }
      S.chat.liveStatus = S.chat.liveStatus === 'failed' ? 'failed' : 'completed';
      addTimelineEvent('complete', 'Complete', S.chat.liveStatus === 'failed' ? 'failed' : 'done', 'Stream completed.');
      break;
    case 'stream.error':
      S.chat.liveStatus = 'failed';
      S.chat.messages.pop();
      S.chat.messages.push({ role: 'assistant', content: '⚠ **Error:** ' + (data.error || 'Stream error.') });
      addTimelineEvent('stream_error', mapping.label, 'failed', data.error || 'Stream error.');
      renderChatMsgs();
      break;
  }
  renderChatSidePanels();
}

async function sendChatLegacy(text, sentMode) {
  addTimelineEvent('fallback', 'Fallback to legacy', 'done', 'Streaming failed, using /brain-dashboard/chat');
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), CHAT_TIMEOUT_MS);
  try {
    const r = await fetch('/brain-dashboard/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: ctrl.signal,
      body: JSON.stringify({ message: text, mode: sentMode, user_id: 'dashboard_operator' })
    });
    clearTimeout(to);
    const j = await r.json();
    S.chat.messages.pop();

    addTimelineEvent('response_received', 'Response received', j.ok ? 'done' : 'failed', 'Status: ' + (j.status || (j.ok ? 'completed' : 'failed')));
    if (j.run_id) {
      S.chat.currentRunId = j.run_id;
      addTimelineEvent('run_id', 'Run ID received', 'done', String(j.run_id));
    }
    if (j.classification) addTimelineEvent('classification', 'Classification', 'done', j.classification);
    if (j.provider_used || j.model_used) addTimelineEvent('provider_model', 'Provider/model', 'done', (j.provider_used || '—') + ' / ' + (j.model_used || '—'));
    addTimelineEvent('mode_effective', 'Mode effective', 'done', (j.mode_requested || sentMode) + ' → ' + (j.mode_effective || '—'));
    if (j.provider_degraded) addTimelineEvent('provider_degraded', 'Provider degraded', 'failed', j.fallback_reason || 'Provider degradation reported.');

    if (!j.ok) {
      S.chat.liveStatus = 'failed';
      S.chat.messages.push({ role: 'assistant', content: '⚠ **Error:** ' + (j.content || j.error || 'Brain API unreachable.') });
    } else {
      const warnings = [];
      if (j.provider_degraded) warnings.push({ type: 'degraded', text: '⚠ Provider degraded. Fallback: ' + (j.fallback_reason || 'unknown') });
      if (j.raw_cot_exposed) warnings.push({ type: 'cot', text: '🚨 RAW CHAIN-OF-THOUGHT EXPOSED' });
      S.chat.liveStatus = 'completed';
      S.chat.messages.push({ role: 'assistant', content: j.content || '(no response)', warnings });
    }

    updateInspector(j);
    S.chat.lastMeta = j;
    if (j.run_id) await loadTraceForRun(j.run_id);
    addTimelineEvent('complete', 'Complete', S.chat.liveStatus === 'failed' ? 'failed' : 'done', 'Legacy request finished.');
  } catch (e) {
    clearTimeout(to);
    S.chat.messages.pop();
    S.chat.liveStatus = 'failed';
    addTimelineEvent('request_failed', 'Request failed', 'failed', e.message);
    S.chat.messages.push({ role: 'assistant', content: '⚠ **Error:** ' + e.message });
  }
}

function updateInspector(j) {
  const set = (id, v) => { const e = $(id); if (e) e.textContent = (v == null || v === '') ? '—' : v; };
  set('insp-runid', j.run_id);
  set('insp-class', j.classification);
  set('insp-model', (j.model_used || '—') + ' / ' + (j.provider_used || '—'));
  set('insp-mode-req', j.mode_requested || S.chat.mode);
  set('insp-mode-eff', j.mode_effective || j.mode_requested || S.chat.mode);
  set('insp-auto-dec', (j.auto_decision && j.auto_decision !== 'n/a') ? j.auto_decision : '—');
  set('insp-blocked', safeArray(j.blocked_tools).length ? safeArray(j.blocked_tools).join(', ') : 'none');
  const tr = $('insp-trace');
  if (tr) {
    if (j.trace_url) {
      const proxy = j.trace_url.replace('/v2/agent/runs/', '/brain-dashboard/agent-v2/runs/');
      tr.innerHTML = `<a href="${esc(proxy)}" target="_blank" style="color:var(--accent)">Open trace →</a>`;
    } else { tr.textContent = '—'; }
  }
  const escCard = $('insp-escalation-card');
  if (escCard) {
    const req = j.mode_escalation_required === true;
    escCard.style.display = req ? '' : 'none';
    if (req) {
      set('insp-esc-req', 'YES — approval required');
      set('insp-esc-reason', j.mode_escalation_reason || '—');
      set('insp-perm', j.required_permission || '—');
      set('insp-scope', safeArray(j.expected_write_scope).length ? safeArray(j.expected_write_scope).join(', ') : '—');
      set('insp-conf', j.confirmation_id || '—');
    }
  }
}

function renderMarkdown(md) {
  if (!md) return '';
  let s = String(md);
  const blocks = [];
  s = s.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const i = blocks.length;
    blocks.push({ lang, code });
    return `\u0000CODE${i}\u0000`;
  });
  s = esc(s);
  s = s.replace(/`([^`]+)`/g, '<code class="inline">$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
  s = s.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  s = s.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  s = s.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
  s = s.replace(/^(\s*)[-*] (.+)$/gm, '<li>$2</li>');
  s = s.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
  s = s.split(/\n{2,}/).map(p => {
    if (/^<(h\d|ul|ol|blockquote|pre)/.test(p.trim())) return p;
    return '<p>' + p.replace(/\n/g, '<br>') + '</p>';
  }).join('');
  s = s.replace(/\u0000CODE(\d+)\u0000/g, (_, i) => {
    const b = blocks[+i];
    const copy = '<button class="code-copy" onclick="copyCode(this)">copy</button>';
    return `<pre>${copy}<code>${esc(b.code)}</code></pre>`;
  });
  return s;
}
window.copyCode = function(btn) {
  const code = btn.parentElement.querySelector('code');
  if (!code) return;
  navigator.clipboard.writeText(code.textContent).then(() => {
    btn.textContent = '✓'; setTimeout(() => btn.textContent = 'copy', 1200);
  });
};

function fmtMoney(x) {
  if (x == null || x === '') return '—';
  const n = Number(x);
  if (Number.isNaN(n)) return esc(x);
  return '$' + n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function fmtNum(x) {
  if (x == null || x === '') return '—';
  const n = Number(x);
  if (Number.isNaN(n)) return esc(x);
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function renderPositionsTable(rows) {
  rows = safeArray(rows);
  if (!rows.length) return '<p class="muted-note">No positions reported.</p>';
  let h = '<table><thead><tr><th>Symbol</th><th>Type</th><th>Qty</th><th>Avg Cost</th><th>Value</th></tr></thead><tbody>';
  rows.forEach(r => {
    h += `<tr><td>${esc(r.symbol || '—')}</td><td>${esc(r.secType || '—')}</td><td>${esc(r.position ?? '—')}</td><td>${fmtMoney(r.avgCost)}</td><td>${fmtMoney(r.marketValue)}</td></tr>`;
  });
  return h + '</tbody></table>';
}

function renderOrdersTable(rows) {
  rows = safeArray(rows);
  if (!rows.length) return '<p class="muted-note">No open orders reported.</p>';
  let h = '<table><thead><tr><th>ID</th><th>Symbol</th><th>Action</th><th>Type</th><th>Qty</th><th>Status</th></tr></thead><tbody>';
  rows.forEach(r => {
    h += `<tr><td>${esc(r.orderId || '—')}</td><td>${esc(r.symbol || '—')}</td><td>${esc(r.action || '—')}</td><td>${esc(r.orderType || '—')}</td><td>${esc(r.totalQuantity ?? '—')}</td><td>${esc(r.status || '—')}</td></tr>`;
  });
  return h + '</tbody></table>';
}

function renderPhase391Table(rows) {
  rows = safeArray(rows);
  if (!rows.length) return '<p class="muted-note">PH391 has no completed rows exposed yet.</p>';
  let h = '<table><thead><tr><th>Variant</th><th>Segment</th><th>Net</th><th>DD</th><th>ON entries</th><th>Halt</th></tr></thead><tbody>';
  rows.forEach(r => {
    h += `<tr><td>${esc(r.variant || '—')}</td><td>${esc(r.segment || '—')}</td><td>${fmtMoney(r.net_profit_usd)}</td><td>${fmtNum(r.drawdown_pct)}%</td><td>${fmtNum(r.on_entries)}</td><td>${esc(r.hive_halt || '—')}</td></tr>`;
  });
  return h + '</tbody></table>';
}

function viewTrading() {
  const tl = S.tradingLive || {};
  const qc = tl.qc || {};
  const ib = tl.ibkr || {};
  const qcState = qc.ok && !qc.stale ? 'green' : (qc.ok ? 'yellow' : 'red');
  const ibState = ib.ok ? 'green' : (ib.port_open ? 'yellow' : 'red');
  const warnings = safeArray(tl.warnings);
  return `
    <div class="page-head"><div><h1>Trading Live</h1><div class="sub">QC live paper + IBKR Gateway read-only observability · refreshed ${ago(S.lastRefresh && S.lastRefresh.toISOString())}</div></div>
      <span class="tag blue">READ ONLY</span></div>
    <div class="grid g-4" style="margin-bottom:18px">
      ${card('QC Live Paper', `<div class="big">${qc.ok ? '●' : '✕'}</div><div class="label">${esc(qc.overall_status || '—')} · ${esc(qc.activity_status || '—')}</div>`, qcState)}
      ${card('IBKR Gateway', `<div class="big">${ib.ok ? '●' : (ib.port_open ? '◐' : '✕')}</div><div class="label">${esc(ib.status || '—')} · port ${esc(ib.port || 4002)}</div>`, ibState)}
      ${card('Equity', `<div class="big">${fmtMoney(qc.equity)}</div><div class="label">Net ${fmtMoney(qc.net_profit)} · holdings ${fmtMoney(qc.holdings_value)}</div>`, 'blue')}
      ${card('Orders', `<div class="big">${esc(qc.orders_invalid ?? 0)}</div><div class="label">invalid · submitted ${esc(qc.orders_submitted ?? '—')} · filled ${esc(qc.orders_filled ?? '—')}</div>`, (Number(qc.orders_invalid || 0) > 0 ? 'yellow' : 'green'))}
    </div>
    <div class="grid g-2">
      <div class="panel"><h2>QuantConnect Hive</h2><div class="kv">
        <div class="item"><div class="k">Project</div><div class="v">${esc(qc.project_id || '—')}</div></div>
        <div class="item"><div class="k">Deploy</div><div class="v">${esc(qc.deploy_id || '—')}</div></div>
        <div class="item"><div class="k">Brokerage</div><div class="v">${esc(qc.brokerage || '—')}</div></div>
        <div class="item"><div class="k">Hive Mode</div><div class="v">${esc(qc.hive_mode || '—')}</div></div>
        <div class="item"><div class="k">Generated</div><div class="v">${esc(qc.generated_at_utc || '—')}</div></div>
        <div class="item"><div class="k">Source Age</div><div class="v">${qc.source_age_seconds == null ? '—' : esc(qc.source_age_seconds + 's')} ${qc.stale ? '⚠ stale' : ''}</div></div>
      </div></div>
      <div class="panel"><h2>IBKR Read-Only</h2><div class="kv">
        <div class="item"><div class="k">Port 4002</div><div class="v">${ib.port_open ? 'open' : 'closed'}</div></div>
        <div class="item"><div class="k">PID</div><div class="v">${esc(ib.pid || '—')}</div></div>
        <div class="item"><div class="k">Accounts</div><div class="v">${esc(ib.managed_accounts_count ?? '—')}</div></div>
        <div class="item"><div class="k">Positions</div><div class="v">${esc(ib.position_count ?? 0)}</div></div>
        <div class="item"><div class="k">Open Orders</div><div class="v">${esc(ib.open_order_count ?? 0)}</div></div>
        <div class="item"><div class="k">Safety</div><div class="v">${ib.order_submission_enabled ? '⚠ orders enabled' : 'orders disabled'}</div></div>
      </div>
      <div class="port-grid">
        <span>GW live 4001: <strong>${(ib.port_scan || {}).gateway_live_4001 ? 'open' : 'closed'}</strong></span>
        <span>GW paper 4002: <strong>${(ib.port_scan || {}).gateway_paper_4002 ? 'open' : 'closed'}</strong></span>
        <span>TWS live 7496: <strong>${(ib.port_scan || {}).tws_live_7496 ? 'open' : 'closed'}</strong></span>
        <span>TWS paper 7497: <strong>${(ib.port_scan || {}).tws_paper_7497 ? 'open' : 'closed'}</strong></span>
      </div>
      ${ib.error ? `<div class="note-warn">IBKR read error: ${esc(ib.error)}</div>` : ''}</div>
    </div>
    <div class="grid g-2" style="margin-top:14px">
      <div class="panel"><h2>IBKR Positions</h2>${renderPositionsTable(ib.positions)}</div>
      <div class="panel"><h2>IBKR Open Orders</h2>${renderOrdersTable(ib.open_orders)}</div>
    </div>
    <div class="grid g-2" style="margin-top:14px">
      <div class="panel"><h2>PH391 Research Running</h2>
        <div class="kv" style="margin-bottom:10px">
          <div class="item"><div class="k">Status</div><div class="v">${esc((qc.phase391 || {}).status || '—')}</div></div>
          <div class="item"><div class="k">Rows</div><div class="v">${esc((qc.phase391 || {}).rows ?? '—')}</div></div>
          <div class="item"><div class="k">Decision</div><div class="v">${esc((qc.phase391 || {}).decision || 'pending')}</div></div>
        </div>
        ${renderPhase391Table((qc.phase391 || {}).tail)}
      </div>
      <div class="panel"><h2>Safety / Warnings</h2>
        <div style="font-size:13px;line-height:1.8">
          <span class="tag blue">READ ONLY</span> No order submission controls exposed.<br>
          <span class="tag blue">PAPER</span> IBKR route is constrained to paper Gateway port 4002.<br>
          <span class="tag blue">NO MEMORY WRITE</span> Dashboard endpoint does not write semantic memory or FAISS.<br>
          ${warnings.length ? warnings.map(w => `<span class="tag yellow">WARN</span> ${esc(w)}<br>`).join('') : '<span class="tag green">NOMINAL</span> No endpoint warnings.'}
        </div>
      </div>
    </div>`;
}

function viewTools() {
  return `
    <div class="page-head"><div><h1>Tools</h1><div class="sub">Agent tool registry — live tool list not exposed by current endpoints</div></div></div>
    <div class="panel"><h2>Tool Registry</h2>
      <div class="empty-state"><div class="ico">⚙</div><div style="font-weight:600">NOT CONNECTED</div>
      <div>The current backend does not expose a live tool list endpoint. This view is a placeholder for a future capability-registry front.</div></div>
    </div>
    <div class="panel"><h2>What we know from chat responses</h2>
      <div style="font-size:12.5px;color:var(--text-dim);line-height:1.8">
        • Blocked tools appear in the chat inspector per-response (<code style="font-family:var(--mono);color:var(--accent)">blocked_tools</code> field).<br>
        • Read-only mode blocks all write tools (memory, FAISS, code, git, broker, trading).<br>
        • Trace events are visible in the full trace link.
      </div>
    </div>`;
}

function viewMemory() {
  const st = S.status || {}; const mem = st.memory || {}; const sf = S.safety || {}; const q = S.queue || {};
  const mutSem = sf.canonical_semantic_mutated === true;
  const mutFais = sf.faiss_mutated === true;
  return `
    <div class="page-head"><div><h1>Memory</h1><div class="sub">Memory & semantic state (read-only view)</div></div>
      <span class="tag ${mutSem || mutFais ? 'yellow' : 'green'}">${mutSem || mutFais ? 'MUTATION DETECTED' : 'NO MUTATION'}</span></div>
    <div class="grid g-2">
      <div class="panel"><h2>Counts</h2><div class="kv">
        <div class="item"><div class="k">Journal Events</div><div class="v">${esc(mem.journal_count != null ? mem.journal_count : '—')}</div></div>
        <div class="item"><div class="k">Promotion Queue</div><div class="v">${esc(mem.promotion_queue_count != null ? mem.promotion_queue_count : '—')}</div></div>
        <div class="item"><div class="k">Active Review Required</div><div class="v">${esc(mem.promotion_queue_active_review_required_count || 0)}</div></div>
        <div class="item"><div class="k">Semantic Staging</div><div class="v">${esc(mem.semantic_staging_count != null ? mem.semantic_staging_count : '—')}</div></div>
        <div class="item"><div class="k">Promotion Audits</div><div class="v">${esc(mem.promotion_audit_count != null ? mem.promotion_audit_count : '—')}</div></div>
        <div class="item"><div class="k">Canonical Lines</div><div class="v">${esc(sf.semantic_memory_lines != null ? sf.semantic_memory_lines : '—')}</div></div>
        <div class="item"><div class="k">FAISS IDs</div><div class="v">${esc(sf.faiss_ids != null ? sf.faiss_ids : '—')}</div></div>
      </div></div>
      <div class="panel"><h2>Promotion Queue</h2><div class="table-wrap">${queueTable(q)}</div></div>
    </div>
    <div class="panel"><h2>Recent Activity</h2>${timeline(S.activity)}</div>`;
}

function queueTable(q) {
  const items = (q && q.items) || [];
  if (!items.length) return '<p style="color:var(--text-mute)">No pending candidates.</p>';
  let h = '<table><thead><tr><th>ID</th><th>Category</th><th>Confidence</th><th>Status</th></tr></thead><tbody>';
  items.forEach(it => {
    const st = it.review_required === true ? 'Pending review' : (it.terminal_status || 'Resolved');
    const cls = it.review_required === true ? 'yellow' : 'green';
    h += `<tr><td>${esc(it.id)}</td><td>${esc(it.category || '—')}</td><td>${esc(it.confidence || '—')}</td><td><span class="tag ${cls}">${esc(st)}</span></td></tr>`;
  });
  return h + '</tbody></table>';
}

function timeline(act) {
  const evs = (act && act.events) || [];
  if (!evs.length) return '<p style="color:var(--text-mute)">No recent activity.</p>';
  return '<div class="timeline">' + evs.map(e => {
    const cls = e.severity === 'error' ? 'red' : (e.severity === 'warning' ? 'yellow' : 'green');
    return `<div class="tl-item"><div class="tdot ${cls}"></div><div><div class="ttime">${esc(ago(e.timestamp))}</div><div class="ttitle">${esc(e.category || 'Event')} — ${esc(e.source_cycle || '')}</div><div class="tdetail">${esc(e.summary || '')}${e.confidence ? ' (conf: ' + esc(e.confidence) + ')' : ''}</div></div></div>`;
  }).join('') + '</div>';
}

function viewTraces() {
  const ag = (S.status && S.status.agent_v2) || {};
  return `
    <div class="page-head"><div><h1>Traces & Runs</h1><div class="sub">Recent run inspection</div></div></div>
    <div class="panel"><h2>Latest Run</h2><div class="kv">
      <div class="item"><div class="k">Run ID</div><div class="v">${esc(ag.latest_run_id || '—')}</div></div>
      <div class="item"><div class="k">Trace Available</div><div class="v">${ag.trace_available ? '✓' : '✕'}</div></div>
      <div class="item"><div class="k">Total Runs</div><div class="v">${esc(ag.runs != null ? ag.runs : '—')}</div></div>
      <div class="item"><div class="k">Chat Route</div><div class="v">${esc(ag.chat_agent_route || '/v2/chat/agent')}</div></div>
    </div></div>
    <div class="panel"><h2>Open Trace</h2>
      <div style="font-size:13px;color:var(--text-dim)">Trace details are shown inline in the <a href="#/chat" style="color:var(--accent)">Chat</a> inspector after each response. ${ag.latest_run_id ? `Open the latest trace directly: <a href="/brain-dashboard/agent-v2/runs/${esc(ag.latest_run_id)}/trace" target="_blank" style="color:var(--accent)">${esc(ag.latest_run_id.slice(0, 12))}… →</a>` : ''}</div>
    </div>`;
}

function viewSafety() {
  const sf = S.safety || {};
  const lockRow = (name, desc, state, tagCls) => `
    <div class="lockrow"><div><div class="lk-name">${esc(name)}</div><div class="lk-desc">${esc(desc)}</div></div>
    <span class="tag ${tagCls}">${state}</span></div>`;
  const semMut = sf.canonical_semantic_mutated === true;
  const faisMut = sf.faiss_mutated === true;
  return `
    <div class="page-head"><div><h1>Safety</h1><div class="sub">Lock status — defaults to LOCKED unless endpoint proves otherwise</div></div></div>
    <div class="panel"><h2>Memory & FAISS Locks</h2>
      ${lockRow('Memory Writes', 'Canonical semantic memory writes', semMut ? 'MUTATED ⚠' : 'LOCKED', semMut ? 'yellow' : 'blue')}
      ${lockRow('FAISS Writes', 'FAISS index mutations', faisMut ? 'MUTATED ⚠' : 'LOCKED', faisMut ? 'yellow' : 'blue')}
      ${lockRow('Semantic Staging Promotion', 'Auto-promotion of staged candidates', 'LOCKED', 'blue')}
    </div>
    <div class="panel"><h2>Trading & Broker Locks</h2>
      ${lockRow('Broker / IBKR', 'Interactive Brokers connectivity', 'LOCKED', 'blue')}
      ${lockRow('Trading', 'Order placement / execution', 'LOCKED', 'blue')}
      ${lockRow('Real Money', 'Real capital operations', 'LOCKED', 'red')}
    </div>
    <div class="panel"><h2>Code & Git Locks</h2>
      ${lockRow('Code Write', 'Source file modifications', 'APPROVAL REQUIRED', 'yellow')}
      ${lockRow('Git Commit', 'Commit creation', 'APPROVAL REQUIRED', 'yellow')}
      ${lockRow('Autonomy R2', 'Autonomy level 2 escalation', 'NOT ACTIVE', 'blue')}
    </div>
    <div class="panel"><h2>Run Mode</h2>
      <div style="font-size:13px">Current selected chat mode: <span class="tag blue">${esc(MODE_BADGE[S.chat.mode])}</span><br>
      All write operations require explicit operator approval. No auto-write, no auto-promotion, no auto-trading.</div>
    </div>`;
}

function viewOps() {
  const st = S.status || {}; const brain = st.brain || {}; const dash = st.dashboard || {};
  return `
    <div class="page-head"><div><h1>Ops</h1><div class="sub">Local service operations — read-only status</div></div></div>
    <div class="grid g-3">
      <div class="card"><h3>Brain API (8091)</h3><div class="row"><span class="big">${brain.ok ? '●' : '✕'}</span><span class="tag ${brain.ok ? 'green' : 'red'}">${brain.ok ? 'LIVE' : 'UNAVAILABLE'}</span></div><div class="label">${esc(brain.api || 'http://127.0.0.1:8091')}</div></div>
      <div class="card"><h3>Dashboard (8092)</h3><div class="row"><span class="big">${dash.ok ? '●' : '✕'}</span><span class="tag ${dash.ok ? 'green' : 'red'}">${dash.ok ? 'LIVE' : 'UNAVAILABLE'}</span></div><div class="label">latency ${esc(dash.status_latency_ms != null ? dash.status_latency_ms + 'ms' : '—')}</div></div>
      <div class="card"><h3>Legacy (8070)</h3><div class="row"><span class="big">✕</span><span class="tag gray">INACTIVE</span></div><div class="label">legacy dashboard — do not use</div></div>
    </div>
    <div class="panel"><h2>PID Status</h2><div style="font-size:12.5px;color:var(--text-dim)">UNKNOWN / NOT EXPOSED — the dashboard backend does not expose process PID information. Use <code style="font-family:var(--mono);color:var(--accent)">status_brain_local.ps1</code> from the runbook.</div></div>
    <div class="panel"><h2>Runbook</h2><div style="font-size:13px;line-height:1.8">
      Local operations runbook: <code style="font-family:var(--mono);color:var(--accent)">tmp_agent/brain_v9/ops/runbook_local_operations.md</code><br>
      Helper scripts: <code style="font-family:var(--mono);color:var(--accent)">status_brain_local.ps1</code>, <code style="font-family:var(--mono);color:var(--accent)">start_brain_local.ps1</code>, <code style="font-family:var(--mono);color:var(--accent)">stop_brain_local.ps1</code>, <code style="font-family:var(--mono);color:var(--accent)">restart_brain_local.ps1</code>
    </div></div>
    <div class="panel"><h2>Service Controls</h2>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">
        <button class="btn" disabled title="requires future approved backend front">Start 8091</button>
        <button class="btn" disabled title="requires future approved backend front">Stop 8091</button>
        <button class="btn" disabled title="requires future approved backend front">Restart</button>
      </div>
      <div style="font-size:11.5px;color:var(--text-mute)">⚠ Controls are disabled placeholders. Start/stop/restart require operator action via the runbook scripts in a terminal. No live service controls are enabled in this front.</div>
    </div>`;
}

function viewRoadmap() {
  return `
    <div class="page-head"><div><h1>Roadmap</h1><div class="sub">Modernization progress & next fronts</div></div></div>
    <div class="panel"><h2>UI Modernization</h2>
      <div style="font-size:13px;line-height:1.8">
        <span class="tag green">DONE</span> SPA shell with hash-routed views<br>
        <span class="tag green">DONE</span> Top status bar with service + lock indicators<br>
        <span class="tag green">DONE</span> READ / BUILD / AUTO mode controls<br>
        <span class="tag green">DONE</span> Chat workspace with inspector<br>
        <span class="tag green">DONE</span> Live Execution panel in the left column<br>
        <span class="tag green">DONE</span> Trace enrichment after response where exposed<br>
        <span class="tag yellow">DEFERRED</span> True backend streaming/SSE/WebSocket event stream<br>
        <span class="tag yellow">DEFERRED</span> Conversation persistence (backend required)<br>
        <span class="tag yellow">DEFERRED</span> Live service controls (approved backend front required)
      </div>
    </div>
    <div class="panel"><h2>Recommended Next Fronts</h2>
      <div style="font-size:13px;line-height:1.9">
        • <strong>FRONT-BRAIN-UI-DASHBOARD-CHAT-MANUAL-REVIEW-AND-COMMIT-04</strong> — manual browser review and controlled commit closeout<br>
        • <strong>FRONT-BRAIN-UI-CHAT-BACKEND-STREAMING-EVENTS-04</strong> — true streaming/SSE/WebSocket events if desired<br>
        • <strong>FRONT-BRAIN-AGENT-V2-TRADING-REFUSAL-EXPLICITNESS-HARDENING-01</strong> — later safety hardening
      </div>
    </div>`;
}

function panelErr(msg, detail) {
  return `<div class="page-head"><div><h1>—</h1></div></div>
    <div class="error-state"><div class="ico">⚠</div><div style="font-size:15px;font-weight:600">${esc(msg)}</div>
    ${detail ? '<div style="font-size:12px;color:var(--text-mute)">' + esc(detail) + '</div>' : ''}</div>`;
}

window.addEventListener('hashchange', router);
document.addEventListener('DOMContentLoaded', () => {
  const refreshBtn = $('nav-refresh');
  if (refreshBtn) refreshBtn.addEventListener('click', refresh);
  router();
  refresh();
  setInterval(refresh, REFRESH_MS);
});
