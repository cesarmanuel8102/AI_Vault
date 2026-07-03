// Brain Operator Console — SPA controller (v3)
// Front: FRONT-BRAIN-UI-DASHBOARD-CHAT-MODERNIZATION-01
// Frontend-only. No tokens. No dangerous controls. Existing read-only endpoints only.

'use strict';

const REFRESH_MS = 10000;
const VIEWS = ['overview', 'agent', 'chat', 'tools', 'memory', 'traces', 'safety', 'ops', 'roadmap'];

// ── Cached state ──
const S = {
  status: null,      // /brain-dashboard/status
  activity: null,    // /brain-dashboard/activity
  scheduler: null,   // /brain-dashboard/scheduler
  safety: null,      // /brain-dashboard/safety
  queue: null,       // /brain-dashboard/promotion-queue
  agentV2: null,     // /brain-dashboard/agent-v2/status
  lastRefresh: null,
  online: true,
  currentView: 'overview',
  chat: { mode: 'read_only', messages: [], busy: false, lastMeta: null },
};

// ── Helpers ──
const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
function esc(s) { if (s == null) return ''; const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }
function ago(ts) { if (!ts) return '—'; const m = (Date.now() - new Date(ts).getTime()) / 60000; if (m < 1) return 'just now'; if (m < 60) return Math.round(m) + 'm ago'; return Math.round(m / 60) + 'h ago'; }
function stateBool(b) { return b ? 'green' : 'red'; }

async function getJSON(url, timeoutMs) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs || 8000);
  try {
    const r = await fetch(url, { signal: ctrl.signal, headers: { 'Accept': 'application/json' } });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}

// ── Polling refresh ──
async function refresh() {
  try {
    const [status, activity, scheduler, safety, queue, agentV2] = await Promise.all([
      getJSON('/brain-dashboard/status'),
      getJSON('/brain-dashboard/activity'),
      getJSON('/brain-dashboard/scheduler'),
      getJSON('/brain-dashboard/safety'),
      getJSON('/brain-dashboard/promotion-queue'),
      getJSON('/brain-dashboard/agent-v2/status'),
    ]);
    S.status = status; S.activity = activity; S.scheduler = scheduler;
    S.safety = safety; S.queue = queue; S.agentV2 = agentV2;
    S.lastRefresh = new Date(); S.online = true;
    renderTopbar();
    if (S.currentView !== 'chat') renderCurrentView();
    else renderChatSidebarStatus();
  } catch (e) {
    S.online = false;
    renderTopbar();
    console.warn('refresh error', e);
  }
}

// ── Topbar ──
function renderTopbar() {
  const st = S.status || {};
  const brain = st.brain || {};
  const dash = st.dashboard || {};
  const ag = st.agent_v2 || {};
  const wd = st.watchdog || {};
  const sf = S.safety || {};
  const mem = st.memory || {};

  const setChip = (id, text, state) => { const c = $(id); if (!c) return; c.textContent = text; c.dataset.state = state; };

  setChip('ts-brain', brain.ok ? 'Brain API ●' : 'Brain API ✕', brain.ok ? 'green' : 'red');
  setChip('ts-dash', dash.ok ? 'Dashboard ●' : 'Dashboard ✕', dash.ok ? 'green' : 'red');
  setChip('ts-backend', ag.ok ? ('Backend: ' + (ag.backend || '—')) : 'Backend: —', ag.ok ? 'green' : 'unknown');
  const prov = ag.latest_provider_used || (st.kimi && st.kimi.ok ? 'kimi' : '—');
  const degraded = ag.latest_provider_degraded;
  setChip('ts-provider', degraded ? 'Provider DEGRADED' : ('Provider: ' + prov), degraded ? 'yellow' : (prov !== '—' ? 'green' : 'unknown'));

  // Locks default LOCKED unless endpoint proves otherwise
  const memMutated = sf.canonical_semantic_mutated === true || sf.faiss_mutated === true;
  setChip('ts-memory', memMutated ? 'MEM MUTATED ⚠' : 'MEM LOCKED', memMutated ? 'yellow' : 'locked');
  setChip('ts-trading', 'TRADING LOCKED', 'locked');
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

// ── Router ──
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
  const fn = { overview: viewOverview, agent: viewAgent, chat: viewChat, tools: viewTools,
               memory: viewMemory, traces: viewTraces, safety: viewSafety, ops: viewOps, roadmap: viewRoadmap }[S.currentView];
  if (fn) c.innerHTML = fn(); else c.innerHTML = viewOverview();
  if (S.currentView === 'chat') initChat();
}

// ── View: Overview ──
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
    alertsHtml += `<div class="tag ${cls}">${esc(a.severity)}</div> ${esc(a.message || a.code)}<br>`;
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

function card(title, body, accent) {
  const ac = accent ? `<span class="tag ${accent}" style="float:right">●</span>` : '';
  return `<div class="card"><h3>${esc(title)}${ac}</h3>${body}</div>`;
}

// ── View: Agent ──
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

// ── View: Chat ──
function viewChat() {
  return `
    <div class="chat-workspace">
      <aside class="chat-side">
        <button class="new-chat" id="chat-new">✎ New chat</button>
        <div class="conv-list">
          <div class="conv-item placeholder">
            <div style="font-weight:600;color:var(--text-dim);font-style:normal;margin-bottom:2px">Session</div>
            <div style="font-size:11px">In-memory only · not persisted</div>
          </div>
        </div>
        <div class="side-status" id="chat-side-status"></div>
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
  renderChatSidebarStatus();
  syncModeUI();
  const ta = $('chat-input');
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
  ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'; });
  $('chat-send').addEventListener('click', sendChat);
  $('chat-new').addEventListener('click', () => { S.chat.messages = []; renderChatMsgs(); $('chat-input').focus(); });
  document.querySelectorAll('#chat-mode-segment .mode-btn').forEach(btn => {
    btn.addEventListener('click', () => setMode(btn.dataset.mode));
  });
}

const MODE_LABELS = { read_only: 'READ', build: 'BUILD', auto: 'AUTO' };
const MODE_BADGE = { read_only: 'READ_ONLY', build: 'BUILD', auto: 'AUTO' };

function setMode(mode) {
  if (!['read_only', 'build', 'auto'].includes(mode)) return;
  S.chat.mode = mode;
  syncModeUI();
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

function renderChatMsgs() {
  const box = $('chat-msgs');
  if (!box) return;
  if (!S.chat.messages.length) {
    box.innerHTML = `<div class="empty-state"><div class="ico">✎</div><div style="font-size:15px;font-weight:600">Start a conversation</div>
      <div>Ask Brain anything. Responses render with markdown. Select a mode below — READ is the safe default. Governance is enforced regardless of mode.</div></div>`;
    return;
  }
  box.innerHTML = '';
  S.chat.messages.forEach(m => {
    const av = m.role === 'user' ? 'You' : '◆';
    const bubble = m.role === 'assistant' ? renderMarkdown(m.content) : esc(m.content);
    const warn = m.warnings ? m.warnings.map(w => `<div class="msg-warn ${w.type}">${esc(w.text)}</div>`).join('') : '';
    let modeTag = '';
    if (m.role === 'user' && m.mode) {
      modeTag = `<div class="msg-mode-tag"><span class="tag gray" style="font-size:9px">${esc((MODE_LABELS[m.mode] || m.mode.toUpperCase()))}</span></div>`;
    }
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

function renderChatSidebarStatus() {
  const ss = $('chat-side-status');
  if (!ss) return;
  const st = S.status || {}; const ag = st.agent_v2 || {};
  ss.innerHTML = `
    <div style="font-weight:700;margin-bottom:6px">System Status</div>
    <div>Backend: ${esc(ag.backend || '—')}</div>
    <div>Provider: ${ag.latest_provider_degraded ? '<span style="color:var(--yellow)">DEGRADED</span>' : 'OK'}</div>
    <div>Mode: <span class="tag blue" style="font-size:9px">READ-ONLY</span></div>
    <div>Refreshed: ${ago(S.lastRefresh && S.lastRefresh.toISOString())}</div>`;
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
  $('chat-send').disabled = true; $('chat-status').textContent = 'Thinking…';
  S.chat.messages.push({ role: 'assistant', content: '…', loading: true });
  renderChatMsgs();
  try {
    const r = await fetch('/brain-dashboard/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, mode: sentMode, user_id: 'dashboard_operator' })
    });
    const j = await r.json();
    S.chat.messages.pop();
    const warnings = [];
    if (!j.ok) {
      S.chat.messages.push({ role: 'assistant', content: '⚠ **Error:** ' + (j.content || j.error || 'Brain API unreachable. Ensure Agent V2 is running on 8091.') });
    } else {
      if (j.provider_degraded) warnings.push({ type: 'degraded', text: '⚠ Provider degraded. Fallback: ' + (j.fallback_reason || 'unknown') });
      if (j.raw_cot_exposed) warnings.push({ type: 'cot', text: '🚨 RAW CHAIN-OF-THOUGHT EXPOSED' });
      // FIX-6: only show fallback warning when reason is truthy and not the literal 'none'/''
      if (j.fallback_reason && !j.provider_degraded && j.fallback_reason !== 'none' && j.fallback_reason !== '') {
        warnings.push({ type: 'fallback', text: 'Fallback used: ' + j.fallback_reason });
      }
      const escalation = (j.mode_escalation_required === true) ? {
        required: true,
        reason: j.mode_escalation_reason || '',
        permission: j.required_permission || '',
        scope: (j.expected_write_scope && j.expected_write_scope.length) ? j.expected_write_scope.join(', ') : '',
        confirmation_id: j.confirmation_id || '',
      } : null;
      S.chat.messages.push({ role: 'assistant', content: j.content || '(no response)', warnings, escalation });
    }
    updateInspector(j);
    S.chat.lastMeta = j;
  } catch (e) {
    S.chat.messages.pop();
    S.chat.messages.push({ role: 'assistant', content: '⚠ **Connection error:** ' + e.message + '\n\nEnsure the Brain API is running on 8091.' });
  } finally {
    S.chat.busy = false;
    $('chat-send').disabled = false; $('chat-status').textContent = 'Ready';
    renderChatMsgs();
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
  set('insp-blocked', (j.blocked_tools && j.blocked_tools.length) ? j.blocked_tools.join(', ') : 'none');
  const tr = $('insp-trace');
  if (tr) {
    if (j.trace_url) {
      const proxy = j.trace_url.replace('/v2/agent/runs/', '/brain-dashboard/agent-v2/runs/');
      tr.innerHTML = `<a href="${esc(proxy)}" target="_blank" style="color:var(--accent)">Open trace →</a>`;
    } else { tr.textContent = '—'; }
  }
  // Escalation card
  const escCard = $('insp-escalation-card');
  if (escCard) {
    const req = j.mode_escalation_required === true;
    escCard.style.display = req ? '' : 'none';
    if (req) {
      set('insp-esc-req', 'YES — approval required');
      set('insp-esc-reason', j.mode_escalation_reason || '—');
      set('insp-perm', j.required_permission || '—');
      set('insp-scope', (j.expected_write_scope && j.expected_write_scope.length) ? j.expected_write_scope.join(', ') : '—');
      set('insp-conf', j.confirmation_id || '—');
    }
  }
}

// ── Minimal safe Markdown renderer (escapes HTML first, then applies inline formatting) ──
function renderMarkdown(md) {
  if (!md) return '';
  let s = String(md);
  // Extract fenced code blocks first to protect them
  const blocks = [];
  s = s.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const i = blocks.length;
    blocks.push({ lang, code });
    return `\u0000CODE${i}\u0000`;
  });
  // Escape HTML
  s = esc(s);
  // Inline code
  s = s.replace(/`([^`]+)`/g, '<code class="inline">$1</code>');
  // Bold / italic
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
  // Headers
  s = s.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  s = s.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  s = s.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Links
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Blockquote
  s = s.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
  // Lists
  s = s.replace(/^(\s*)[-*] (.+)$/gm, '<li>$2</li>');
  s = s.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
  // Paragraphs / line breaks
  s = s.split(/\n{2,}/).map(p => {
    if (/^<(h\d|ul|ol|blockquote|pre)/.test(p.trim())) return p;
    return '<p>' + p.replace(/\n/g, '<br>') + '</p>';
  }).join('');
  // Restore code blocks
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

// ── View: Tools ──
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
        • Trace events (<code style="font-family:var(--mono);color:var(--accent)">tool_call_*</code>) are visible in the full trace link.
      </div>
    </div>`;
}

// ── View: Memory ──
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

// ── View: Traces ──
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

// ── View: Safety ──
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
      <div style="font-size:13px">Current effective mode: <span class="tag blue">READ-ONLY</span><br>
      All write operations require explicit operator approval. No auto-write, no auto-promotion, no auto-trading.</div>
    </div>`;
}

// ── View: Ops ──
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

// ── View: Roadmap ──
function viewRoadmap() {
  return `
    <div class="page-head"><div><h1>Roadmap</h1><div class="sub">Modernization progress & next fronts</div></div></div>
    <div class="panel"><h2>UI Modernization — Front 01 (this)</h2>
      <div style="font-size:13px;line-height:1.8">
        <span class="tag green">DONE</span> SPA shell with hash-routed views<br>
        <span class="tag green">DONE</span> Top status bar with service + lock indicators<br>
        <span class="tag green">DONE</span> Left navigation (9 views)<br>
        <span class="tag green">DONE</span> Overview cards grid<br>
        <span class="tag green">DONE</span> Chat workspace (sidebar + bubbles + composer + inspector)<br>
        <span class="tag green">DONE</span> Markdown rendering + code blocks with copy<br>
        <span class="tag green">DONE</span> Safety locks panel (defaults LOCKED)<br>
        <span class="tag green">DONE</span> Ops panel with runbook links<br>
        <span class="tag green">DONE</span> Provider-degraded / fallback / CoT warnings<br>
        <span class="tag yellow">DEFERRED</span> Conversation persistence (backend required)<br>
        <span class="tag yellow">DEFERRED</span> Live tool registry (endpoint required)<br>
        <span class="tag yellow">DEFERRED</span> Live service controls (approved backend front required)
      </div>
    </div>
    <div class="panel"><h2>Recommended Next Fronts</h2>
      <div style="font-size:13px;line-height:1.9">
        • <strong>FRONT-BRAIN-UI-DASHBOARD-CHAT-MODERNIZATION-REVIEW-AND-POLISH-02</strong> — review, polish, fix gaps<br>
        • <strong>FRONT-BRAIN-AGENT-V2-TRADING-REFUSAL-EXPLICITNESS-HARDENING-01</strong> — harden refusal explicitness<br>
        • <strong>FRONT-BRAIN-AGENT-V2-CAPABILITY-REGISTRY-RUNTIME-TYPE-REPAIR-01</strong> — if runtime metadata issue remains
      </div>
    </div>`;
}

function panelErr(msg, detail) {
  return `<div class="page-head"><div><h1>—</h1></div></div>
    <div class="error-state"><div class="ico">⚠</div><div style="font-size:15px;font-weight:600">${esc(msg)}</div>
    ${detail ? '<div style="font-size:12px;color:var(--text-mute)">' + esc(detail) + '</div>' : ''}</div>`;
}

// ── Boot ──
window.addEventListener('hashchange', router);
document.addEventListener('DOMContentLoaded', () => {
  $('nav-refresh').addEventListener('click', refresh);
  router();
  refresh();
  setInterval(refresh, REFRESH_MS);
});
