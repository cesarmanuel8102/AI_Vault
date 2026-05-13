function safe(fn, fallback='') { try { return fn() } catch { return fallback } }
function n(v, d=2) { return v != null && !isNaN(v) ? Number(v).toFixed(d) : '--' }
function pct(v) { return v != null && !isNaN(v) ? (Number(v)*100).toFixed(1)+'%' : '--' }
function pctRaw(v) { return v != null && !isNaN(v) ? Number(v).toFixed(1)+'%' : '--' }
function badge(text, cls) { return `<span class="topbar-badge badge-${cls}">${esc(text)}</span>` }
function esc(s) { if(s==null) return '--'; const d=document.createElement('div'); d.textContent=String(s); return d.innerHTML; }
function ago(ts) {
  if (!ts) return '--';
  const d = new Date(ts);
  if (isNaN(d)) return '--';
  const sec = Math.floor((Date.now() - d.getTime())/1000);
  if (sec < 0) return 'just now';
  if (sec < 60) return sec+'s ago';
  if (sec < 3600) return Math.floor(sec/60)+'m ago';
  if (sec < 86400) return Math.floor(sec/3600)+'h ago';
  return Math.floor(sec/86400)+'d ago';
}
function uColor(u) {
  if (u == null || isNaN(u)) return '';
  if (u >= 0.3) return 'ok';
  if (u >= 0) return 'warn';
  return 'err';
}
function statusBadge(s) {
  if (!s) return badge('unknown','blue');
  const sl = String(s).toLowerCase();
  if (['running','active','healthy','ok','passing','completed','done','passed','promoted','ready','true'].some(k=>sl.includes(k))) return badge(s,'green');
  if (['error','failed','critical','stopped','crashed','rolled_back','frozen'].some(k=>sl.includes(k))) return badge(s,'red');
  if (['warning','paused','pending','waiting','stale','queued','in_test','testing','idle','paper_candidate'].some(k=>sl.includes(k))) return badge(s,'amber');
  return badge(s,'blue');
}
function kv(label, value, cls='') {
  return `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
    <span class="text-muted">${esc(label)}</span>
    <span class="mono ${cls}">${value != null ? value : '--'}</span>
  </div>`;
}
function kvBlock(pairs) { return pairs.map(p => kv(p[0], p[1], p[2]||'')).join(''); }
function boolBadge(v) { return v ? badge('Yes','green') : badge('No','red'); }
function renderKpiCard(label, value, sub='', valueClass='', valueStyle='') {
  return `<div class="kpi"><div class="label">${esc(label)}</div><div class="value ${valueClass}"${valueStyle ? ` style="${valueStyle}"` : ''}>${value}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
}
function renderUiState(kind, title, detail='') {
  const safeKind = ['loading','empty','error','info'].includes(kind) ? kind : 'info';
  const role = safeKind === 'error' ? 'alert' : 'status';
  const ariaLive = safeKind === 'error' ? 'assertive' : 'polite';
  return `<div class="ui-state ${safeKind}" data-state-kind="${safeKind}" role="${role}" aria-live="${ariaLive}">
    <div class="ui-state-title">${esc(title)}</div>
    ${detail ? `<div class="ui-state-detail">${esc(detail)}</div>` : ''}
  </div>`;
}
function loadingState(title='Loading data', detail='') { return renderUiState('loading', title, detail); }
function emptyState(title='No data', detail='') { return renderUiState('empty', title, detail); }
function infoState(title='No context', detail='') { return renderUiState('info', title, detail); }
function errorState(title='API unreachable', detail='') { return renderUiState('error', title, detail); }
function renderTargetHtml(targetId, html) {
  const el = document.getElementById(targetId);
  if (!el) return null;
  el.innerHTML = html;
  return el;
}
function noteBlock(text, tone='info') {
  return `<div class="ui-note ${tone}">${esc(text)}</div>`;
}
function tableWrap(inner, minWidth=720) {
  return `<div class="table-wrap" style="--table-min-width:${Number(minWidth) || 720}px">${inner}</div>`;
}
function toneChipClass(tone='neutral') {
  const safeTone = ['info', 'warn', 'err', 'ok', 'neutral'].includes(tone) ? tone : 'neutral';
  return safeTone;
}
function humanizeToken(value) {
  if (value == null) return '--';
  const raw = String(value).trim();
  if (!raw) return '--';
  if (/\s/.test(raw)) return raw;
  const replacements = {
    ibkr: 'IBKR',
    otc: 'OTC',
    po: 'PO',
    qc: 'QC',
    bl: 'BL',
    eod: 'EOD',
    pnl: 'PnL',
    wr: 'WR',
    u: 'U',
    ui: 'UI',
  };
  return raw
    .split(/[_-]+/)
    .filter(Boolean)
    .map(part => {
      const lower = part.toLowerCase();
      if (replacements[lower]) return replacements[lower];
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(' ');
}
function pill(text, tone='neutral', title='') {
  const titleAttr = title ? ` title="${esc(title)}"` : '';
  return `<span class="pill ${toneChipClass(tone)}"${titleAttr}>${esc(text)}</span>`;
}
function compactListSection(title, items, tone='neutral', maxVisible=4, emptyLabel='none') {
  const rows = Array.isArray(items) ? items.filter(Boolean).map(v => String(v)) : [];
  if (!rows.length) {
    return `<div class="compact-list-section">
      <div class="compact-list-head">
        <span class="text-xs text-muted">${esc(title)}</span>
        ${pill(emptyLabel, 'neutral')}
      </div>
    </div>`;
  }
  const visible = rows.slice(0, Math.max(1, maxVisible));
  const remaining = rows.length - visible.length;
  return `<div class="compact-list-section">
    <div class="compact-list-head">
      <span class="text-xs text-muted">${esc(title)}</span>
      ${pill(`${rows.length} items`, tone)}
    </div>
    <div class="pill-row">
      ${visible.map(item => pill(humanizeToken(item), tone, item)).join('')}
      ${remaining > 0 ? pill(`+${remaining} more`, 'neutral') : ''}
    </div>
  </div>`;
}
function executiveCard(eyebrow, title, detail='', tone='info') {
  return `<div class="exec-card ${tone}">
    <div class="exec-eyebrow">${esc(eyebrow)}</div>
    <div class="exec-title">${title}</div>
    ${detail ? `<div class="exec-detail">${detail}</div>` : ''}
  </div>`;
}
function renderOverviewDecisionStrip(targetId, operating, maintenance, utility, platformSummary) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!operating) {
    renderTargetHtml(targetId, emptyState('No overview decision frame', 'Executive overview cannot be built without canonical operating context.'));
    return;
  }
  const progress = operating.progress || {};
  const capture = operating.closed_trades_capture || {};
  const lane = operating.lane || {};
  const blockers = operating.blockers || [];
  const nextAction = safe(()=>operating.next_actions?.[0] || utility?.next_actions?.[0], '--');
  const components = maintenance?.components || {};
  const tracked = ['brain_v9', 'pocket_option_bridge', 'edge_browser', 'ibkr_gateway'];
  const healthyCount = tracked.filter(name => String(components?.[name]?.status || '').toLowerCase() === 'healthy').length;
  const focusSummary = safe(()=>platformSummary.platforms?.[lane.platform], {});
  const readySignals = safe(()=>focusSummary.ready_signals, 0);
  const sampleTone = (progress.resolved_trades || 0) > 0 ? 'warn' : 'err';
  const infraTone = healthyCount === tracked.length ? 'ok' : healthyCount >= tracked.length - 1 ? 'warn' : 'err';
  target.innerHTML = [
    executiveCard(
      'Decision Frame',
      esc(operating.status || operating.mode || '--'),
      `${esc(operating.focus || '--')}<br>next action: <span class="mono">${esc(nextAction)}</span>`,
      blockers.length ? 'warn' : 'ok'
    ),
    executiveCard(
      'Focus Lane',
      `${esc(lane.platform || '--')} | ${esc(lane.symbol || '--')} | ${esc(lane.timeframe || '--')}`,
      `connector ${esc(focusSummary.status || '--')} | ready signals ${esc(readySignals ?? 0)}`,
      'info'
    ),
    executiveCard(
      'Sample Pressure',
      `${esc(progress.resolved_trades ?? 0)}/${esc(safe(()=>operating.decision_framework.target_trades, 50))} resolved`,
      `remaining ${esc(progress.remaining_to_target ?? '--')} | closed trades ${esc(capture.captured_trades ?? 0)} (${esc(capture.status || '--')})`,
      sampleTone
    ),
    executiveCard(
      'Infrastructure',
      `${healthyCount}/${tracked.length} core services healthy`,
      `brain ${esc(components?.brain_v9?.status || '--')} | bridge ${esc(components?.pocket_option_bridge?.status || '--')} | edge ${esc(components?.edge_browser?.status || '--')} | ibkr ${esc(components?.ibkr_gateway?.status || '--')}`,
      infraTone
    ),
  ].join('');
}
function renderStrategyDecisionStrip(targetId, ranking, edgeValidation, operating) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!ranking && !edgeValidation) {
    renderTargetHtml(targetId, emptyState('No strategy decision frame', 'No ranking or edge validation payload was available.'));
    return;
  }
  const canonicalTop = ranking?.top_strategy || null;
  const rankedLeader = ranking?.ranked?.[0] || null;
  const summary = edgeValidation?.summary || {};
  const focusStrategies = (ranking?.ranked || []).filter(s => strategyMatchesOperatingLane(s, operating));
  const topExec = summary.top_execution_edge || {};
  target.innerHTML = [
    executiveCard(
      'Canonical Selection',
      esc(canonicalTop?.strategy_id || 'none_selected'),
      canonicalTop ? `edge ${esc(canonicalTop.edge_state || '--')} | governance ${esc(canonicalTop.governance_state || '--')}` : `ranked leader ${esc(rankedLeader?.strategy_id || '--')} is still a candidate, not a selected top`,
      canonicalTop ? 'ok' : 'warn'
    ),
    executiveCard(
      'Focus Lane Candidates',
      `${focusStrategies.length} matching strategies`,
      focusStrategies.length ? `best focus candidate ${esc(focusStrategies[0]?.strategy_id || '--')}` : 'no ranked strategy currently matches the operating lane',
      focusStrategies.length ? 'info' : 'warn'
    ),
    executiveCard(
      'Validation State',
      `${esc(summary.validated_count ?? 0)} validated | ${esc(summary.promotable_count ?? 0)} promotable`,
      `${esc(summary.probation_count ?? 0)} probation | ${esc(summary.blocked_count ?? 0)} blocked`,
      (summary.validated_count || summary.promotable_count) ? 'ok' : 'warn'
    ),
    executiveCard(
      'Execution Posture',
      esc(topExec.strategy_id || 'none_ready'),
      `execution ready now: ${topExec.execution_ready_now ? 'yes' : 'no'} | main blocker ${esc(operating?.main_blocker || '--')}`,
      topExec.execution_ready_now ? 'ok' : 'err'
    ),
  ].join('');
}
function renderStrategySemantics(targetId, ranking, operating) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!ranking) {
    renderTargetHtml(targetId, emptyState('No ranking semantics', 'Strategy semantics require the ranking payload.'));
    return;
  }
  const canonicalTop = ranking?.top_strategy || null;
  const rankedLeader = ranking?.ranked?.[0] || null;
  const whyDifferent = canonicalTop
    ? 'Canonical top exists, so ranking and governance can converge on the same selection.'
    : 'No canonical top is selected. Ranked leader is diagnostic only until validation and governance gates are satisfied.';
  target.innerHTML = kvBlock([
    ['Canonical Top', esc(canonicalTop?.strategy_id || 'none_selected')],
    ['Ranked Leader', esc(rankedLeader?.strategy_id || '--')],
    ['Leader Edge', statusBadge(rankedLeader?.edge_state || '--')],
    ['Leader Governance', statusBadge(rankedLeader?.governance_state || '--')],
    ['Lane Focus', `${esc(safe(()=>operating.lane?.platform,'--'))} | ${esc(safe(()=>operating.lane?.symbol,'--'))}`],
  ]) + noteBlock(whyDifferent, canonicalTop ? 'info' : 'warn');
}
function renderStrategyOperatingSummary(targetId, ranking, edgeValidation, operating) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!operating) {
    renderTargetHtml(targetId, emptyState('No operating summary', 'Operating summary requires canonical operating context.'));
    return;
  }
  const focusStrategies = (ranking?.ranked || []).filter(s => strategyMatchesOperatingLane(s, operating));
  const summary = edgeValidation?.summary || {};
  target.innerHTML = kvBlock([
    ['Main Blocker', esc(operating.main_blocker || '--')],
    ['Next Action', esc(safe(()=>operating.next_actions?.[0], '--'))],
    ['Focus Strategies', `${focusStrategies.length}`],
    ['Validated Edge', `${summary.validated_count ?? 0}`],
    ['Promotable Edge', `${summary.promotable_count ?? 0}`],
    ['Probation Edge', `${summary.probation_count ?? 0}`],
  ]) + noteBlock('Global ranking is diagnostic. Focus-lane candidates are the only strategies aligned with the current operating experiment.', 'info');
}
function actionButton(service, action) {
  const cls = action === 'stop' ? 'action-btn danger' : action === 'restart' ? 'action-btn warn' : 'action-btn';
  return `<button class="${cls}" onclick="maintenanceAction('${service}','${action}')" aria-label="${esc(`${service} ${action}`)}">${esc(action)}</button>`;
}
function setMaintenanceFeedback(message) {
  const el = document.getElementById('system-maintenance-feedback');
  if (el) el.innerHTML = renderUiState('info', 'Maintenance feedback', message);
}
function renderOperatingContext(targetId, operating) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!operating) {
    renderTargetHtml(targetId, emptyState('No operating context', 'The dashboard did not receive canonical operating context from the runtime.'));
    return;
  }
  const progress = operating.progress || {};
  const lane = operating.lane || {};
  const filters = operating.filters || {};
  const capture = operating.closed_trades_capture || {};
  const decision = operating.decision_framework || {};
  const blockers = operating.blockers || [];
  const nextActions = operating.next_actions || [];
  target.innerHTML = kvBlock([
    ['Modo', esc(operating.mode)],
    ['Estado', statusBadge(operating.status || '--')],
    ['Focus', esc(operating.focus || '--')],
    ['Lane', `${esc(lane.platform)} | ${esc(lane.symbol)} | ${esc(lane.timeframe)}`],
    ['Resueltos', `${progress.resolved_trades ?? 0}/${decision.target_trades ?? 50}`],
    ['Win Rate', pct(progress.win_rate)],
    ['Breakeven', pct(progress.breakeven_win_rate)],
    ['Expectancy', n(progress.expectancy_per_trade, 2)],
    ['Net Profit', n(progress.net_profit, 2), (progress.net_profit||0) >= 0 ? 'text-green' : 'text-red'],
    ['Filtro horario', statusBadge(filters.hour_filter?.status || '--')],
    ['Closed Trades', `${capture.captured_trades ?? 0} | ${esc(capture.status || '--')}`],
    ['Paper Only', boolBadge(operating.paper_only === true)],
  ]);
  target.innerHTML += compactListSection('Blockers', blockers, blockers.length ? 'err' : 'neutral', 4, 'none');
  target.innerHTML += compactListSection('Next Actions', nextActions, nextActions.length ? 'info' : 'neutral', 4, 'none');
}
function renderMaintenanceSummary(targetId, maintenance) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!maintenance?.components) {
    renderTargetHtml(targetId, emptyState('No maintenance data', 'Service health and restart controls are unavailable for this refresh cycle.'));
    return;
  }
  target.innerHTML = '<div class="service-stack">' + Object.entries(maintenance.components).map(([key, item]) => `
    <div class="service-item">
      <div class="service-head">
        <div>
          <div class="service-title">${esc(item.label || key)}</div>
          <div class="service-detail">${esc(item.detail || '--')}</div>
        </div>
        <div>${statusBadge(item.status || '--')}</div>
      </div>
      <div class="service-notes">pid=${esc(item.pid ?? '--')} | port=${esc(item.port ?? 'n/a')}</div>
    </div>
  `).join('') + '</div>';
}
function renderMaintenanceControls(targetId, maintenance) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!maintenance?.components) {
    renderTargetHtml(targetId, emptyState('No maintenance data', 'No actionable maintenance payload was received from the runtime.'));
    return;
  }
  target.innerHTML = '<div class="service-stack">' + Object.entries(maintenance.components).map(([key, item]) => `
    <div class="service-item">
      <div class="service-head">
        <div>
          <div class="service-title">${esc(item.label || key)}</div>
          <div class="service-detail">${esc(item.detail || '--')}</div>
        </div>
        <div>${statusBadge(item.status || '--')}</div>
      </div>
      <div class="service-notes">${(item.notes || []).map(note => esc(note)).join('<br>') || 'sin_notas'}</div>
      <div class="action-row">${(item.actions || []).map(action => actionButton(key, action)).join('') || '<span class="text-xs text-muted">sin acciones remotas</span>'}</div>
    </div>
  `).join('') + '</div>';
}
function platformMatchesOperatingLane(platformName, operating) {
  const lanePlatform = safe(()=>operating.lane?.platform, '');
  return lanePlatform && String(lanePlatform) === String(platformName);
}
function strategyMatchesOperatingLane(strategy, operating) {
  if (!strategy || !operating) return false;
  const lanePlatform = safe(()=>operating.lane?.platform, '');
  const platformToVenue = {
    pocket_option: 'pocket_option',
    ibkr: 'ibkr',
    internal_paper: 'internal',
  };
  const expectedVenue = String(platformToVenue[lanePlatform] || lanePlatform || '').toLowerCase();
  const strategyVenue = String(strategy.venue || '').toLowerCase();
  if (expectedVenue && strategyVenue !== expectedVenue) return false;
  const laneSymbol = String(safe(()=>operating.lane?.symbol, '')).toLowerCase();
  if (!laneSymbol) return true;
  const strategySymbol = String(
    strategy.current_context_symbol
    || strategy.preferred_symbol
    || strategy.signal_symbol
    || strategy.catalog_symbol
    || ''
  ).toLowerCase();
  return !strategySymbol || strategySymbol === laneSymbol;
}
function renderPlatformFocus(targetId, operating, platformSummary) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!operating) {
    renderTargetHtml(targetId, emptyState('No operating context', 'Focus platform cannot be derived without canonical operating context.'));
    return;
  }
  const lane = operating.lane || {};
  const progress = operating.progress || {};
  const focusPlatform = lane.platform || '--';
  const focusSummary = safe(()=>platformSummary.platforms?.[focusPlatform], {});
  target.innerHTML = kvBlock([
    ['Focus Platform', esc(focusPlatform)],
    ['Selected Platform', esc(activePlatform || focusPlatform || '--')],
    ['Pair', esc(lane.pair || lane.symbol || '--')],
    ['Timeframe', esc(lane.timeframe || '--')],
    ['Mode', esc(operating.mode || '--')],
    ['Status', statusBadge(operating.status || '--')],
    ['Resolved', `${progress.resolved_trades ?? 0}/${safe(()=>operating.decision_framework.target_trades, 50)}`],
    ['Focus Connector', statusBadge(focusSummary?.status || '--')],
    ['Focus Ready Signals', focusSummary?.ready_signals ?? 0],
  ]);
}
function renderStrategyFocus(targetId, operating, ranking) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!operating) {
    renderTargetHtml(targetId, emptyState('No operating context', 'Strategy focus cannot be computed without canonical operating context.'));
    return;
  }
  const canonicalTop = ranking?.top_strategy || null;
  const rankedLeader = ranking?.ranked?.[0] || null;
  target.innerHTML = kvBlock([
    ['Mode', esc(operating.mode || '--')],
    ['Focus Lane', `${esc(safe(()=>operating.lane?.platform,'--'))} | ${esc(safe(()=>operating.lane?.symbol,'--'))} | ${esc(safe(()=>operating.lane?.timeframe,'--'))}`],
    ['Canonical Top', esc(canonicalTop?.strategy_id || 'none_selected')],
    ['Ranked Leader', esc(rankedLeader?.strategy_id || '--')],
    ['Leader Venue', esc(rankedLeader?.venue || '--')],
    ['Leader Edge', statusBadge(rankedLeader?.edge_state || '--')],
    ['Leader Signal Ready', rankedLeader?.execution_ready_now ? badge('yes','green') : badge('no','amber')],
    ['Main Blocker', esc(operating.main_blocker || '--')],
  ]);
}
async function maintenanceAction(service, action) {
  setMaintenanceFeedback(`Ejecutando ${service}.${action}...`);
  try {
    const res = await fetch('/brain/maintenance/action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
      body: JSON.stringify({service, action}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    const message = data.message || data.result?.stdout || data.result?.message || 'acción completada';
    setMaintenanceFeedback(`${service}.${action}: ${message}`);
    renderMaintenanceSummary('overview-maintenance', data.maintenance || {});
    renderMaintenanceControls('system-maintenance', data.maintenance || {});
    setTimeout(() => refreshCurrentPanel(), 1200);
  } catch (error) {
    setMaintenanceFeedback(`${service}.${action}: ${error.message}`);
  }
}
