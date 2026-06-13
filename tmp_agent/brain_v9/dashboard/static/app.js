// Brain Operator Dashboard UI Controller
// Calls /brain-dashboard/* endpoints and renders operator-friendly views

const REFRESH_MS = 10000;
let lastActivity = [];

async function refresh() {
  try {
    const [statusRes, activityRes, schedRes, safetyRes, queueRes] = await Promise.all([
      fetch('/brain-dashboard/status'),
      fetch('/brain-dashboard/activity'),
      fetch('/brain-dashboard/scheduler'),
      fetch('/brain-dashboard/safety'),
      fetch('/brain-dashboard/promotion-queue'),
    ]);
    const status = await statusRes.json();
    const activity = await activityRes.json();
    const sched = await schedRes.json();
    const safety = await safetyRes.json();
    const queue = await queueRes.json();

    renderHeader(status);
    renderStatusCards(status);
    renderDoingNow(status);
    renderActivity(activity);
    renderMemory(status, safety);
    renderPromotionQueue(queue);
    renderScheduler(sched);
    renderRecommendations(status, safety, queue);
  } catch (e) {
    console.error('Refresh error', e);
    setMode('error', 'Connection Error');
  }
}

function setMode(cls, text) {
  const el = document.getElementById('mode-badge');
  el.className = 'badge ' + cls;
  el.textContent = text;
}

function renderHeader(data) {
  const wd = data.watchdog || {};
  const sch = data.scheduler || {};
  const mem = data.memory || {};

  if (wd.stopped) setMode('red', 'Stopped');
  else if (wd.paused) setMode('yellow', 'Paused');
  else if (data.safe_mode) setMode('yellow', 'Safe Mode');
  else setMode('green', 'Running');

  const hb = document.getElementById('heartbeat-badge');
  const hbTime = wd.heartbeat ? timeAgo(wd.heartbeat.updated_utc) : 'unknown';
  hb.className = 'badge ' + (wd.heartbeat_present ? 'green' : 'red');
  hb.textContent = 'Heartbeat: ' + hbTime;

  const schBadge = document.getElementById('scheduler-badge');
  schBadge.className = 'badge ' + (sch.enabled ? 'green' : 'gray');
  schBadge.textContent = 'Scheduler: ' + (sch.enabled ? 'Enabled' : 'Disabled');

  const next = document.getElementById('next-run-badge');
  next.textContent = 'Next run: ' + (sch.next_run_time || '—');
}

function renderStatusCards(data) {
  const brain = data.brain || {};
  const kimi = data.kimi || {};
  const dash = data.dashboard || {};
  const sch = data.scheduler || {};
  const aut = data.autonomy || {};
  const mem = data.memory || {};

  setCard('brain-api-status', brain.ok ? 'Healthy' : 'Unhealthy', brain.ok ? 'green' : 'red');
  setCard('kimi-status', (kimi.status || 'unknown'), (kimi.ok ? 'green' : 'yellow'));
  setCard('dashboard-status', dash.ok ? 'Online' : 'Offline', dash.ok ? 'green' : 'red');
  setCard('scheduler-status', sch.enabled ? 'Enabled' : 'Disabled', sch.enabled ? 'green' : 'gray');
  setCard('autonomy-status', aut.state || 'idle', aut.state === 'running' ? 'green' : (aut.paused ? 'yellow' : 'blue'));
  setCard('memory-status', (mem.journal_count || 0) + ' events', 'blue');
}

function setCard(id, text, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = '<span class="badge ' + cls + '">' + text + '</span>';
}

function renderDoingNow(data) {
  const wd = data.watchdog || {};
  const aut = data.autonomy || {};
  document.getElementById('now-state').textContent = wd.stopped ? 'Stopped' : (wd.paused ? 'Paused' : (aut.state || 'Idle'));
  document.getElementById('now-cycle').textContent = aut.cycle || '—';
  document.getElementById('now-last-run').textContent = aut.last_run_time || '—';
  document.getElementById('now-last-result').textContent = aut.last_run_result || '—';
  document.getElementById('now-next-run').textContent = data.scheduler?.next_run_time || '—';
  document.getElementById('now-last-error').textContent = aut.last_error || '—';
}

function renderActivity(data) {
  const events = data.events || [];
  const container = document.getElementById('activity-timeline');
  if (!events.length) { container.innerHTML = '<p>No recent activity.</p>'; return; }
  container.innerHTML = events.map(ev => {
    const cls = ev.severity === 'error' ? 'red' : (ev.severity === 'warning' ? 'yellow' : 'green');
    const t = ev.timestamp ? new Date(ev.timestamp).toLocaleString() : '—';
    return '<div class="timeline-item"><div class="dot ' + cls + '"></div><div class="info"><div class="time">' + t + '</div><div class="title">' + (ev.category || 'Event') + ' — ' + (ev.source_cycle || '') + '</div><div class="detail">' + (ev.summary || '') + (ev.confidence ? ' (confidence: ' + ev.confidence + ')' : '') + '</div></div></div>';
  }).join('');
}

function renderMemory(data, safety) {
  const mem = data.memory || {};
  document.getElementById('mem-journal').textContent = mem.journal_count || 0;
  document.getElementById('mem-queue').textContent = mem.promotion_queue_count || 0;
  document.getElementById('mem-staging').textContent = mem.semantic_staging_count || 0;
  document.getElementById('mem-audit').textContent = mem.promotion_audit_count || 0;
  document.getElementById('mem-lines').textContent = safety.semantic_memory_lines || '—';
  document.getElementById('mem-faiss').textContent = safety.faiss_ids || '—';

  const msg = document.getElementById('safety-msg');
  const safe = safety.canonical_semantic_mutated === false && safety.faiss_mutated === false;
  msg.className = 'safety-msg ' + (safe ? 'green' : 'red');
  msg.textContent = safe
    ? 'Canonical semantic memory and FAISS are not being modified automatically.'
    : 'WARNING: canonical memory or FAISS may have changed.';
}

function renderPromotionQueue(data) {
  const items = data.items || [];
  const container = document.getElementById('promotion-list');
  if (!items.length) { container.innerHTML = '<p>No pending candidates.</p>'; return; }
  let html = '<table><thead><tr><th>ID</th><th>Category</th><th>Confidence</th><th>Status</th></tr></thead><tbody>';
  items.forEach(it => {
    html += '<tr><td>' + (it.id || it.file || '—') + '</td><td>' + (it.category || '—') + '</td><td>' + (it.confidence || '—') + '</td><td><span class="badge yellow">Pending human review</span></td></tr>';
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

function renderScheduler(data) {
  const sch = data.scheduler || data;
  document.getElementById('sch-exists').textContent = sch.exists ? 'Yes' : 'No';
  document.getElementById('sch-enabled').textContent = sch.enabled ? 'Yes' : 'No';
  document.getElementById('sch-state').textContent = sch.state || '—';
  document.getElementById('sch-last-run').textContent = sch.last_run_time || '—';
  document.getElementById('sch-next-run').textContent = sch.next_run_time || '—';
  document.getElementById('sch-last-result').textContent = sch.last_task_result || '—';
  document.getElementById('sch-action').textContent = sch.action || '—';
}

function renderRecommendations(data, safety, queue) {
  const rec = document.getElementById('recommendation');
  const alerts = document.getElementById('alerts');
  const mem = data.memory || {};
  const wd = data.watchdog || {};
  const aut = data.autonomy || {};

  let recs = [];
  if (mem.promotion_queue_count > 0) recs.push('Review promotion queue before autonomous promotion.');
  if (wd.heartbeat_present && heartbeatStale(wd.heartbeat?.updated_utc)) recs.push('Heartbeat is stale — verify autonomy process.');
  if (aut.fallback_rate > 0.3) recs.push('High fallback rate detected — check provider health.');
  if (!recs.length) recs.push('All systems nominal. No immediate operator action required.');
  rec.innerHTML = recs.map(r => '<div>• ' + r + '</div>').join('');

  const alertList = data.alerts || [];
  alerts.innerHTML = alertList.map(a => {
    const cls = a.severity === 'BLOCKED' ? 'red' : (a.severity === 'LOW' ? 'yellow' : 'green');
    return '<div class="alert ' + cls + '"><strong>' + a.severity + ':</strong> ' + (a.message || a.code) + '</div>';
  }).join('');
}

function heartbeatStale(ts) {
  if (!ts) return true;
  const min = (Date.now() - new Date(ts).getTime()) / 60000;
  return min > 10;
}

function timeAgo(ts) {
  if (!ts) return 'unknown';
  const min = (Date.now() - new Date(ts).getTime()) / 60000;
  if (min < 1) return 'just now';
  if (min < 60) return Math.round(min) + ' min ago';
  return Math.round(min / 60) + ' h ago';
}

async function control(action) {
  if ((action === 'stop' || action === 'pause') && !confirm('Are you sure you want to ' + action + ' autonomy?')) return;
  try {
    const r = await fetch('/brain-dashboard/control/' + action, { method: 'POST' });
    const j = await r.json();
    const el = document.getElementById('control-result');
    el.textContent = (j.action || j.message || 'OK') + ' at ' + new Date().toLocaleTimeString();
    el.className = 'control-result green';
    setTimeout(refresh, 500);
  } catch (e) {
    document.getElementById('control-result').textContent = 'Error: ' + e.message;
  }
}

async function chat() {
  const msg = document.getElementById('msg').value.trim();
  if (!msg) return;
  const out = document.getElementById('chat-output');
  const meta = document.getElementById('chat-meta');
  out.textContent = 'Thinking…';
  meta.innerHTML = '';
  try {
    const r = await fetch('/brain-dashboard/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg })
    });
    const j = await r.json();
    out.textContent = j.content || '(no response)';
    meta.innerHTML = 'Provider: ' + (j.provider_selected || '—') +
      ' | Model: ' + (j.model_selected || '—') +
      ' | Fallback: ' + (j.fallback_used ? 'Yes' : 'No') +
      ' | CoT leak: ' + (j.no_cot_leak ? 'Blocked' : 'Risk');
  } catch (e) {
    out.textContent = 'Error: ' + e.message;
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
