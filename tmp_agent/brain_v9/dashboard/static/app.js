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

let dashChatMode = 'read_only';

function setChatMode(mode) {
  dashChatMode = mode;
  ['read_only', 'build', 'auto'].forEach(function(m) {
    var btn = document.getElementById('dash-mode-' + m);
    if (btn) btn.classList.toggle('active', m === mode);
  });
  var out = document.getElementById('chat-output');
  out.textContent = 'Mode switched to ' + mode.toUpperCase();
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
      body: JSON.stringify({ message: msg, mode: dashChatMode, user_id: 'dashboard_operator' })
    });
    const j = await r.json();
    if (!j.ok) {
      out.textContent = 'Error: ' + (j.content || j.error || 'Brain API unreachable.');
      meta.innerHTML = '<span style="color:#f06060">❌ Backend unreachable. Ensure Agent V2 is running on 8091.</span>';
      return;
    }
    
    out.textContent = j.content || '(no response)';
    
    // Build metadata line for canonical Agent V2
    let metaHtml = '';
    const isCanary = j.canonical_agent_v2 === true;
    metaHtml += isCanary ? '<span style="color:#3ecf8e;font-weight:700">✓ Canonical Agent V2</span>' : '<span style="color:#f5a623">⚠ Non-canonical</span>';
    metaHtml += ' | Model: ' + (j.model_used || '—');
    metaHtml += ' | Classification: ' + (j.classification || '—');
    metaHtml += ' | Status: ' + (j.status || '—');
    metaHtml += ' | Mode: ' + (j.mode_effective || dashChatMode || '—').toUpperCase();
    if (j.auto_decision && j.auto_decision !== 'n/a') {
      metaHtml += ' (auto=' + j.auto_decision + ')';
    }
    
    if (j.provider_degraded) {
      metaHtml += '<br/><span style="color:#f5a623">⚠ Provider degraded. Fallback: ' + (j.fallback_reason || 'unknown') + '</span>';
    }
    if (j.raw_cot_exposed) {
      metaHtml += '<br/><span style="color:#f06060;font-weight:700">🚨 RAW CHAIN-OF-THOUGHT EXPOSED</span>';
    }
    
    if (j.trace_url) {
      const traceUrl = j.trace_url.replace('/v2/agent/runs/', '/brain-dashboard/agent-v2/runs/');
      metaHtml += '<br/><a href="' + traceUrl + '" target="_blank" style="color:#6c63ff">&#128269; Open Full Trace</a> <small>(' + (j.run_id || '&#8212;') + ')</small>';
    }
    
    meta.innerHTML = metaHtml;
    
    // Auto-append trace link after output
    if (j.trace_url) {
      const traceDiv = document.createElement('div');
      traceDiv.style.marginTop = '8px';
      traceDiv.style.fontSize = '12px';
      traceDiv.style.color = '#8b90b0';
      traceDiv.innerHTML = 'Trace: ' + j.trace_url.replace('/v2/agent/runs/', '/brain-dashboard/agent-v2/runs/') + ' <button onclick="window.open(\'' + j.trace_url.replace('/v2/agent/runs/', '/brain-dashboard/agent-v2/runs/') + '\',\'_blank\')">View</button>';
      out.appendChild(document.createElement('hr'));
      out.appendChild(traceDiv);
    }
    
    // Render Execution Trace panel for canonical Agent V2 responses
    if (isCanary && j.trace_url) {
      renderExecutionTrace(j);
    }
  } catch (e) {
    out.textContent = 'Error: ' + e.message;
    meta.innerHTML = '<span style="color:#f06060">❌ Connection error: ' + e.message + '</span>';
  }
}

function renderExecutionTrace(data) {
  const out = document.getElementById('chat-output');
  const panel = document.createElement('div');
  panel.className = 'trace-panel';
  const pm = data.provider_metadata || {};
  const isDegraded = data.provider_degraded || false;
  const cotExposed = data.raw_cot_exposed || false;
  const runId = data.run_id || '—';
  const traceUrl = data.trace_url || '';
  const proxyTraceUrl = traceUrl.replace('/v2/agent/runs/', '/brain-dashboard/agent-v2/runs/');
  const fullTraceLink = proxyTraceUrl;
  const safeId = runId.replace(/[^a-z0-9]/gi, '');

  // Build metadata table
  let metaRows = '';
  metaRows += '<tr><td>run_id</td><td>' + escapeHtml(runId) + '</td></tr>';
  metaRows += '<tr><td>classification</td><td>' + escapeHtml(data.classification || '—') + '</td></tr>';
  metaRows += '<tr><td>status</td><td>' + escapeHtml(data.status || '—') + '</td></tr>';
  metaRows += '<tr><td>model_used</td><td>' + escapeHtml(data.model_used || '—') + '</td></tr>';
  metaRows += '<tr><td>provider_used</td><td>' + escapeHtml(data.provider_used || '—') + '</td></tr>';
  metaRows += '<tr><td>provider_degraded</td><td style="color:' + (isDegraded ? '#f0d07a' : '#7af0a8') + '">' + (isDegraded ? '⚠ YES' : '✓ No') + '</td></tr>';
  if (data.fallback_reason) {
    metaRows += '<tr><td>fallback_reason</td><td style="color:#f0d07a">' + escapeHtml(data.fallback_reason) + '</td></tr>';
  }
  metaRows += '<tr><td>raw_cot_exposed</td><td style="color:' + (cotExposed ? '#f07a7a' : '#7af0a8') + ';font-weight:' + (cotExposed ? '700' : 'normal') + '">' + (cotExposed ? '🚨 YES' : '✓ No') + '</td></tr>';

  panel.innerHTML = '<div class="trace-header" onclick="this.nextElementSibling.classList.toggle(\'collapsed\')">' +
    '<span>&#128202;</span> <strong>Execution Trace</strong>' +
    '<span style="margin-left:auto;font-size:11px;color:#8a9aab">' + escapeHtml(runId) + '</span></div>' +
    '<div class="trace-body collapsed">' +
    '<table class="trace-table">' + metaRows + '</table>' +
    '<div class="trace-subsection" id="trace-plan-' + safeId + '"><strong>Plan</strong><div class="trace-loading">Loading...</div></div>' +
    '<div class="trace-subsection" id="trace-tools-' + safeId + '"><strong>Tools</strong><div class="trace-loading">Loading...</div></div>' +
    '<div class="trace-subsection" id="trace-evidence-' + safeId + '"><strong>Evidence</strong><div class="trace-loading">Loading...</div></div>' +
    '<div class="trace-subsection" id="trace-governance-' + safeId + '"><strong>Governance</strong><div class="trace-loading">Loading...</div></div>' +
    '<div class="trace-subsection" id="trace-provider-' + safeId + '"><strong>Provider</strong><div class="trace-loading">Loading...</div></div>' +
    '<div style="margin-top:8px;"><a href="' + fullTraceLink + '" target="_blank" class="trace-btn">&#128269; Open Full Trace</a></div>' +
    '</div>';
  out.appendChild(panel);

  // Async fetch trace events
  if (traceUrl) {
    fetch(fullTraceLink, { headers: { 'Accept': 'application/json' } })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(traceData => {
        const events = traceData.trace || [];
        const eventCount = traceData.event_count || events.length;

        // Plan section: show plan_created event
        const planEvents = events.filter(e => e.event_type === 'plan_created');
        document.getElementById('trace-plan-' + safeId).innerHTML = '<strong>Plan</strong>' +
          (planEvents.length ? '<div>' + planEvents.map(p => '<div>&#183; ' + escapeHtml(p.message || 'plan created') + '</div>').join('') + '</div>' : '<div style="color:#8a9aab">No plan event</div>');

        // Tools section: show tool_call_started/completed
        const toolEvents = events.filter(e => e.event_type && e.event_type.startsWith('tool_call_'));
        let toolsHtml = '';
        if (toolEvents.length) {
          const toolMap = {};
          toolEvents.forEach(e => {
            const name = e.data?.tool || e.message || 'tool';
            if (!toolMap[name]) toolMap[name] = [];
            toolMap[name].push(e);
          });
          Object.keys(toolMap).forEach(name => {
            const evs = toolMap[name];
            const completed = evs.find(e => e.event_type === 'tool_call_completed');
            const status = completed ? (completed.data?.blocked ? '&#128308; BLOCKED' : (completed.data?.ok ? '&#10003; passed' : '&#10007; failed')) : '&#9203; pending';
            toolsHtml += '<div>&#183; <strong>' + escapeHtml(name) + '</strong> ' + status + '</div>';
          });
        }
        document.getElementById('trace-tools-' + safeId).innerHTML = '<strong>Tools</strong>' +
          (toolsHtml ? '<div>' + toolsHtml + '</div>' : '<div style="color:#8a9aab">No tools executed</div>');

        // Evidence section
        document.getElementById('trace-evidence-' + safeId).innerHTML = '<strong>Evidence</strong><div>' +
          'Events: ' + eventCount + ' &#183; run_created &#183; plan_created &#183; final_answer_created &#183; run_completed</div>';

        // Governance section
        document.getElementById('trace-governance-' + safeId).innerHTML = '<strong>Governance</strong><div>' +
          'mode: read_only &#183; CoT: ' + (cotExposed ? 'EXPOSED' : 'safe') + ' &#183; secrets: not checked</div>';

        // Provider section
        document.getElementById('trace-provider-' + safeId).innerHTML = '<strong>Provider</strong><div>' +
          'model: ' + escapeHtml(data.model_used || '—') + ' &#183; degraded: ' + (isDegraded ? 'YES' : 'No') + ' &#183; cot_exposed: ' + (cotExposed ? 'YES' : 'No') + '</div>';
      })
      .catch(err => {
        document.getElementById('trace-plan-' + safeId).innerHTML = '<strong>Plan</strong><div style="color:#f07a7a">Trace fetch failed: ' + escapeHtml(err.message) + '</div>';
        document.getElementById('trace-tools-' + safeId).innerHTML = '<strong>Tools</strong><div style="color:#f07a7a">Unavailable</div>';
        document.getElementById('trace-evidence-' + safeId).innerHTML = '<strong>Evidence</strong><div style="color:#f07a7a">Unavailable</div>';
        document.getElementById('trace-governance-' + safeId).innerHTML = '<strong>Governance</strong><div style="color:#f07a7a">Unavailable</div>';
        document.getElementById('trace-provider-' + safeId).innerHTML = '<strong>Provider</strong><div style="color:#f07a7a">Unavailable</div>';
      });
  }
}

function escapeHtml(text) {
  if (typeof text !== 'string') return text;
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

refresh();
setInterval(refresh, REFRESH_MS);
