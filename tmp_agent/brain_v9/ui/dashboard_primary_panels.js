/* Extracted primary panel renderers from dashboard.html */

/* ─────────────────────────────────────────────
   OVERVIEW PANEL
───────────────────────────────────────────── */
async function refreshOverview() {
  const [health, utility, platformSummary, ranking, accumulator, autonomy, governance, operating, maintenance] = await Promise.all([
    api('/brain/health'),
    api('/brain/utility/v2'),
    api('/trading/platforms/summary'),
    api('/brain/strategy-engine/ranking-v2'),
    api('/brain/autonomy/sample-accumulator'),
    api('/autonomy/status'),
    api('/brain/governance/health'),
    api('/brain/operating-context'),
    api('/brain/maintenance/status'),
  ]);

  const u = safe(()=>utility.u_score);
  const governanceU = safe(()=>utility.governance_u_score);
  const realVenueU = safe(()=>utility.real_venue_u_score);
  const uAlignmentMode = safe(()=>utility.u_score_components?.alignment_mode,'--');
  const verdict = safe(()=>utility.verdict,'--');
  const brainOk = safe(()=>health.overall_status,'unknown');
  const healthySvc = safe(()=>health.summary?.healthy, 0);
  const totalSvc = safe(()=>health.summary?.total, 0);
  const topStrat = safe(()=>ranking.top_strategy?.strategy_id,'--');
  const rankedLeader = safe(()=>ranking.ranked?.[0]?.strategy_id,'--');
  const rankedLeaderEdgeState = safe(()=>ranking.ranked?.[0]?.edge_state, '--');
  const edgeSummary = safe(()=>ranking.edge_validation_summary,{});
  const validatedEdgeCount = safe(()=>edgeSummary.validated_count, 0);
  const promotableEdgeCount = safe(()=>edgeSummary.promotable_count, 0);
  const probationEdgeCount = safe(()=>edgeSummary.probation_count, 0);
  const topEdgeState = safe(()=>ranking.top_strategy?.edge_state || ranking.ranked?.[0]?.edge_state, '--');
  const autonomyRunning = safe(()=>autonomy.running, false);
  const progress = operating?.progress || {};
  const capture = operating?.closed_trades_capture || {};
  const mainBlocker = safe(()=>operating.main_blocker || operating.blockers?.[0], '--');
  const nextAction = safe(()=>operating.next_actions?.[0] || utility.next_actions?.[0], '--');
  const accStatus = accumulator?.status || accumulator || {};
  const sessionTrades = safe(()=>accStatus.session_trades_count, 0);

  let totalTrades = 0;
  if (platformSummary?.platforms) {
    Object.values(platformSummary.platforms).forEach(p => { totalTrades += (p.metrics?.total_trades || 0); });
  }
  const venueAnchorRow = deriveVenueAnchor(platformSummary);
  const venueAnchor = venueAnchorRow.current;
  const venueAnchorSource = venueAnchorRow.platform || '--';
  const phase = safe(()=>utility.current_phase, '--');

  renderOverviewDecisionStrip('overview-decision-strip', operating, maintenance, utility, platformSummary);
  renderOperatingContext('overview-operating', operating);
  renderMaintenanceSummary('overview-maintenance', maintenance);

  document.getElementById('overview-kpis').innerHTML = [
    renderKpiCard('Utility U (Effective)', n(u,4), `${esc(verdict)} | mode ${esc(uAlignmentMode)} | gov ${n(governanceU,4)} | venue guardrail ${realVenueU == null ? '--' : n(realVenueU,4)}`, uColor(u)),
    renderKpiCard('Venue Anchor', venueAnchor == null ? '--' : n(venueAnchor,4), venueAnchor == null ? 'no numeric real-venue U yet' : `worst numeric real-venue U | ${esc(venueAnchorSource)}`, venueAnchor == null ? 'accent' : uColor(venueAnchor)),
    renderKpiCard('Governance U', n(governanceU,4), 'governance component only', uColor(governanceU)),
    renderKpiCard('Brain Health', esc(brainOk), `${healthySvc}/${totalSvc} services`, brainOk==='healthy'?'ok':brainOk==='degraded'?'warn':'err'),
    renderKpiCard('Autonomy', autonomyRunning?'Running':'Stopped', `${safe(()=>autonomy.active_tasks,0)} tasks`, autonomyRunning?'ok':'err'),
    renderKpiCard('Fair Test Trades', `${progress.resolved_trades ?? sessionTrades}/${safe(()=>operating.decision_framework.target_trades,50)}`, `remaining ${progress.remaining_to_target ?? '--'}`, 'accent'),
    renderKpiCard('Win Rate', pct(progress.win_rate), `breakeven ${pct(progress.breakeven_win_rate)}`, (progress.win_rate||0)>=0.521?'ok':(progress.win_rate||0)>0?'warn':'accent'),
    renderKpiCard('Closed Trades', `${capture.captured_trades ?? 0}`, `${esc(capture.status || '--')}`, 'accent'),
    renderKpiCard('Phase', esc(phase), '', 'text-accent', 'font-size:14px'),
    renderKpiCard('Canonical Top', esc(topStrat === '--' ? 'none_selected' : topStrat), topStrat === '--' ? `ranked leader ${esc(rankedLeader)} | edge ${esc(rankedLeaderEdgeState)}` : `edge ${esc(topEdgeState)}`, 'text-accent text-sm', 'font-size:12px;word-break:break-all'),
    renderKpiCard('Next Action', esc(nextAction), 'baseline operating step', 'text-accent text-sm', 'font-size:12px;word-break:break-all'),
    renderKpiCard('Main Blocker', esc(mainBlocker), `${safe(()=>utility.blockers?.length,0)} blockers total`, mainBlocker && mainBlocker!=='--'?'err text-sm':'ok text-sm', 'font-size:12px;word-break:break-all'),
    renderKpiCard('Edge Validation', `${validatedEdgeCount + promotableEdgeCount}`, `${promotableEdgeCount} promotable | ${validatedEdgeCount} validated | ${probationEdgeCount} probation`, 'accent'),
  ].join('');
  document.getElementById('overview-kpi-note').innerHTML = noteBlock('Utility U (Effective) is the global control-layer score. Venue Anchor is the raw real-venue severity reference. Read them together, not as interchangeable metrics.', 'info');

  if (platformSummary?.platforms) {
    const ps = platformSummary.platforms;
    document.getElementById('overview-platform-u').innerHTML = Object.entries(ps).map(([pname, p]) => {
      const row = deriveOverviewPlatformRow(pname, p);
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)">
        <div>
          <div style="font-weight:600">${esc(row.platform)}</div>
          <div class="text-xs text-muted">${esc(row.uVerdict)} | ${esc(row.contextLabel)}</div>
        </div>
        <div class="mono ${row.uVal == null ? 'text-muted' : uColor(row.uVal)}" style="font-size:20px;font-weight:700">${row.uVal == null ? '--' : n(row.uVal,4)}</div>
      </div>`;
    }).join('');
  } else {
    document.getElementById('overview-platform-u').innerHTML = emptyState('No platform data', 'Platform-level U scores were not available in this refresh cycle.');
  }

  if (ranking?.ranked?.length) {
    document.getElementById('overview-top-strategies').innerHTML = ranking.ranked.slice(0,5).map((s,i) =>
      `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <span class="text-muted">#${i+1}</span>
          <span style="font-weight:600;margin-left:8px">${esc(s.strategy_id)}</span>
          <span class="text-xs text-muted" style="margin-left:8px">${esc(s.venue||'')}</span>
          <span class="text-xs text-muted" style="margin-left:8px">edge ${esc(s.edge_state||'--')}</span>
        </div>
        <div class="mono text-sm">${n(s.priority_score,4)}</div>
      </div>`
    ).join('');
  } else {
    document.getElementById('overview-top-strategies').innerHTML = emptyState('No ranking data', 'The strategy ranking endpoint did not return ranked candidates.');
  }

  if (governance) {
    const layers = governance.layers || {};
    const improvement = governance.improvement_summary || {};
    const layerRow = ['V3','V4','V5','V6','V7','V8'].map(k => {
      const layer = layers[k] || {};
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <div style="font-weight:600">${esc(k)} · ${esc(layer.name || '--')}</div>
          <div class="text-xs text-muted">${esc(layer.reason || '--')}</div>
        </div>
        <div>${statusBadge(layer.state || 'unknown')}</div>
      </div>`;
    }).join('');
    document.getElementById('overview-governance-health').innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:12px">
        <div>${kvBlock([
          ['Overall', governance.overall_status || '--'],
          ['Operating Mode', governance.current_operating_mode || '--'],
          ['Kill Switch', safe(()=>governance.kill_switch.mode,'--')],
          ['Rollbacks 7d', governance.rollbacks_last_7d ?? '--'],
        ])}</div>
        <div>${kvBlock([
          ['Last Validation', ago(safe(()=>governance.change_validation.last_run_utc,''))],
          ['Validation State', safe(()=>governance.change_validation.last_pipeline_state,'--')],
          ['Implemented', improvement.implemented_count ?? 0],
          ['Pending', improvement.pending_count ?? 0],
        ])}</div>
      </div>
      <div>${layerRow}</div>
    `;
  } else {
    document.getElementById('overview-governance-health').innerHTML = emptyState('No governance data', 'Governance health could not be derived for this refresh cycle.');
  }

  await refreshOverviewTrades(platformSummary);

  document.getElementById('topbar-phase').textContent = phase;
  const dot = document.getElementById('dot-brain');
  dot.className = 'health-dot ' + (brainOk==='healthy'?'ok':brainOk==='degraded'?'warn':'err');
}

async function refreshOverviewTrades(platformSummary) {
  const platforms = platformSummary?.platforms ? Object.keys(platformSummary.platforms) : ['pocket_option','ibkr','internal_paper'];
  const allTrades = [];
  await Promise.all(platforms.map(async pname => {
    const data = await api(`/trading/platforms/${pname}/trades?limit=10`);
    const arr = platformTradeArray(data);
    arr.forEach(t => { t._platform = pname; allTrades.push(t); });
  }));
  allTrades.sort((a,b) => new Date(b.timestamp||b.opened_at||0) - new Date(a.timestamp||a.opened_at||0));
  const el = document.getElementById('overview-recent-trades');
  if (!allTrades.length) {
    el.innerHTML = emptyState('No activity yet', 'No canonical broker or browser activity has been captured for the current overview window.');
    return;
  }
  el.innerHTML = tableWrap(`<table><thead><tr><th>Time</th><th>Platform</th><th>Strategy</th><th>Symbol</th><th>Dir</th><th>PnL</th><th>Status</th></tr></thead><tbody>` +
    allTrades.slice(0,20).map(t => {
      const profit = t.profit ?? t.pnl ?? null;
      const profitCls = profit > 0 ? 'text-green' : profit < 0 ? 'text-red' : '';
      const strategyLabel = t.strategy_id||t.strategy||'--';
      const statusHtml = t.execution_type==='broker_position'
        ? badge('open-position','blue')
        : (t.execution_type==='browser_click_unverified'
          ? badge('click-only','amber')
          : (t.execution_type==='browser_ui_confirmed' || strategyLabel === 'browser_activity'
            ? badge('ui-confirmed','green')
            : (t.resolved ? badge('resolved','green') : badge('open','amber'))));
      return `<tr>
        <td class="nowrap text-muted">${ago(t.timestamp||t.opened_at)}</td>
        <td>${esc(t._platform)}</td>
        <td class="mono text-xs">${esc(strategyLabel)}${t.quantity!=null ? ` <span class="text-muted">x${esc(t.quantity)}</span>` : ''}</td>
        <td>${esc(t.symbol||'--')}</td>
        <td>${esc(t.direction||'--')}</td>
        <td class="mono ${profitCls}">${profit!=null?n(profit,4):'--'}</td>
        <td>${statusHtml}</td>
      </tr>`;
    }).join('') + '</tbody></table>', 760);
}

/* ─────────────────────────────────────────────
   PLATFORMS PANEL
───────────────────────────────────────────── */
let activePlatform = null;
let lastPlatformSummary = null;
let lastPlatformOperating = null;

async function refreshPlatforms() {
  const [summary, compare, operating] = await Promise.all([
    api('/trading/platforms/summary'),
    api('/trading/platforms/compare'),
    api('/brain/operating-context'),
  ]);
  lastPlatformSummary = summary || null;
  lastPlatformOperating = operating || null;

  if (!summary?.platforms) {
    document.getElementById('platform-tabs').innerHTML = emptyState('No platform data', 'Platform tabs cannot be built because the summary payload is missing.');
    document.getElementById('platform-views').innerHTML = emptyState('No platform views', 'No canonical platform payload was returned for inspection.');
    document.getElementById('platform-compare').innerHTML = emptyState('No comparison data', 'Comparison requires canonical platform summary plus ranking data.');
    return;
  }

  const platforms = Object.keys(summary.platforms);
  const focusPlatform = safe(()=>operating.lane?.platform, null);
  if (!activePlatform || !platforms.includes(activePlatform)) {
    activePlatform = focusPlatform && platforms.includes(focusPlatform) ? focusPlatform : platforms[0];
  }

  renderPlatformFocus('platform-focus', operating, summary || {});

  document.getElementById('platform-tabs').innerHTML = platforms.map(pname =>
    `<div class="platform-tab ${pname===activePlatform?'active':''}" data-platform="${esc(pname)}" onclick="switchPlatform('${pname}')" tabindex="0" role="tab" aria-selected="${pname===activePlatform?'true':'false'}" aria-label="platform ${esc(pname)}">${esc(pname)} ${platformMatchesOperatingLane(pname, operating) ? '<span class="text-accent">[focus]</span>' : ''}</div>`
  ).join('');

  document.getElementById('platform-views').innerHTML = platforms.map(pname =>
    `<div class="platform-view ${pname===activePlatform?'active':''}" id="pview-${pname}"></div>`
  ).join('');

  for (const pname of platforms) {
    await renderPlatformView(pname, summary.platforms[pname]);
  }

  if (compare?.ranking?.length) {
    document.getElementById('platform-compare').innerHTML = `${noteBlock('Reference metrics follow the same basis as displayed U. Resolved sample stays explicit inside each platform card; live broker activity stays separate.')}` +
      tableWrap(`<table><thead><tr>
      <th>Rank</th><th>Platform</th><th>Focus</th><th>U Score</th><th>Reference WR</th><th>Reference PnL</th><th>Reference Trades</th><th>Status</th>
    </tr></thead><tbody>` +
      compare.ranking.map(r => `<tr>
        <td class="text-muted">${r.rank}</td>
        <td style="font-weight:600">${esc(r.platform)}</td>
        <td>${platformMatchesOperatingLane(r.platform, operating) ? badge('focus','blue') : '<span class="text-muted">--</span>'}</td>
        <td class="mono ${r.u_score == null ? 'text-muted' : uColor(r.u_score)}">${r.u_score == null ? 'N/A' : n(r.u_score,4)}</td>
        <td class="mono">${r.win_rate == null ? 'N/A' : pct(r.win_rate)}</td>
        <td class="mono ${r.profit == null ? 'text-muted' : (r.profit>=0?'text-green':'text-red')}">${r.profit == null ? 'N/A' : n(r.profit,2)}</td>
        <td class="mono">${r.trades == null ? 'N/A' : r.trades}</td>
        <td>${statusBadge(r.status)}</td>
      </tr>`).join('') + '</tbody></table>', 780);
    if (compare.summary) {
      document.getElementById('platform-compare').innerHTML += `<div style="padding:12px" class="text-sm text-muted">
        Ranked Leader: <span class="text-green">${esc(compare.ranking?.[0]?.platform || '--')}</span> |
        Last By Ranking: <span class="text-red">${esc(compare.ranking?.[compare.ranking.length-1]?.platform || '--')}</span> |
        Avg U: <span class="mono">${compare.summary.average_u == null ? 'N/A' : n(compare.summary.average_u,4)}</span> |
        Focus: <span class="text-accent">${esc(safe(()=>operating.lane?.platform,'--'))}</span>
      </div>`;
    }
    if (summary.recommendations?.length) {
      document.getElementById('platform-compare').innerHTML += '<div style="padding:0 12px 12px">' +
        summary.recommendations.map(r => `<div style="padding:6px 0;border-bottom:1px solid var(--border)">
          <span class="text-accent">${esc(r.platform)}</span> [${esc(r.priority)}]: ${esc(r.action)} <span class="text-muted">- ${esc(r.reason)}</span>
        </div>`).join('') + '</div>';
    }
  } else {
    document.getElementById('platform-compare').innerHTML = emptyState('No comparison data', 'The comparison endpoint did not return a canonical ranking payload.');
  }
}

async function renderPlatformView(pname, data) {
  const el = document.getElementById('pview-'+pname);
  if (!el) return;

  const u = safe(()=>data.u_score?.current);
  const uV = safe(()=>data.u_score?.verdict,'--');
  const uTrend = safe(()=>data.u_score?.trend_24h,'--');
  const uBlockers = safe(()=>data.u_score?.blockers, []);
  const runtimeU = safe(()=>data.u_score?.runtime_current);
  const performanceU = safe(()=>data.u_score?.performance_current);
  const uBasis = safe(()=>data.u_score?.display_basis, '--');
  const m = data.metrics || {};
  const acc = data.accumulator || {};

  const [signals, trades, uHistory] = await Promise.all([
    api(`/trading/platforms/${pname}/signals`).catch(()=>null),
    api(`/trading/platforms/${pname}/trades?limit=20`).catch(()=>null),
    api(`/trading/platforms/${pname}/u-history?limit=20`).catch(()=>null),
  ]);

  const tradeArr = platformTradeArray(trades);
  const uHistArr = platformHistoryArray(uHistory);
  const execution = data.execution || {};
  const sigTotal = safe(()=>signals?.total_signals, 0);
  const sigValid = safe(()=>signals?.valid_signals, 0);
  const sigProblems = signals?.problems || [];
  const livePositions = execution.live_positions || [];
  const platformContextNote = derivePlatformContextNote(uBasis);

  el.innerHTML = `
    <div class="col-3" style="margin-bottom:16px">
      <div class="section-card">
        <div class="section-body u-display">
          <div class="u-value ${u == null ? '' : uColor(u)}">${u == null ? 'N/A' : n(u,4)}</div>
          <div class="u-label">U Score - ${esc(pname)}</div>
          <div class="u-verdict ${u == null ? '' : uColor(u)}">${esc(uV)}</div>
          <div class="text-xs text-muted mt-8">Basis: ${esc(uBasis)}</div>
          <div class="text-xs text-muted mt-8">Trend 24h: ${esc(uTrend)}</div>
          <div class="text-xs text-muted mt-8">Runtime U: ${runtimeU == null ? '--' : n(runtimeU,4)} | Performance U: ${performanceU == null ? '--' : n(performanceU,4)}</div>
          <div class="text-xs text-muted mt-8">${esc(platformContextNote)}</div>
          ${uBlockers.length ? `<div class="text-xs text-red mt-8">${uBlockers.join(', ')}</div>` : ''}
        </div>
      </div>
      <div class="section-card">
        <div class="section-header">Metrics</div>
        <div class="section-body">
          ${kvBlock([
            ['Resolved Trades', m.total_trades ?? '--'],
            ['Open Entries', m.entries_open ?? '--'],
            ['Wins / Losses', `${m.winning_trades??'--'} / ${m.losing_trades??'--'}`],
            ['Resolved Sample WR', pctRaw(m.win_rate)],
            ['Resolved Sample PnL', n(m.total_profit,2), (m.total_profit||0)>=0?'text-green':'text-red'],
            ['Expectancy', n(m.expectancy,4)],
            ['Sample Quality', n(m.sample_quality,2)],
            ['Reference Basis', m.reference_basis_label ?? '--'],
            ['Reference Trades', m.reference_total_trades ?? '--'],
            ['Reference Win Rate', m.reference_win_rate == null ? '--' : pctRaw(m.reference_win_rate)],
            ['Reference PnL', m.reference_total_profit == null ? '--' : n(m.reference_total_profit,2), m.reference_total_profit == null ? '' : (m.reference_total_profit>=0?'text-green':'text-red')],
            ['Max Drawdown', n(m.max_drawdown,2)],
            ['Sharpe', n(m.sharpe_ratio,2)],
          ])}
        </div>
      </div>
      <div class="section-card">
        <div class="section-header">Execution</div>
        <div class="section-body">
          ${kvBlock([
            ['Last Trade (canonical)', ago(execution.last_trade_time)],
            ['Last Browser Order', ago(execution.last_browser_command_utc)],
            ['Browser Order Status', execution.last_browser_command_status ?? '--'],
            ['Browser Order Confirmed', execution.last_browser_command_confirmed ? 'Yes' : (execution.last_browser_command_utc ? 'No' : '--'), execution.last_browser_command_confirmed ? 'text-green' : (execution.last_browser_command_utc ? 'text-amber' : '')],
            ['Execution Type', execution.last_execution_type ?? '--'],
            ['Executor', execution.last_executor_platform ?? '--'],
            ['IBKR Live Positions', execution.live_positions_count ?? '--'],
            ['IBKR Open Trades', execution.live_open_trades_count ?? '--'],
            ['Accounts Visible', (execution.managed_accounts || []).join(', ') || '--'],
            ['Running', acc.running ? 'Yes' : 'No', acc.running ? 'text-green' : 'text-red'],
            ['Session Trades', acc.session_trades ?? '--'],
            ['Consecutive Skips', acc.consecutive_skips ?? '--'],
            ['Last Execution Attempt', ago(acc.last_trade)],
          ])}
        </div>
      </div>
    </div>
    <div class="col-3" style="margin-bottom:16px">
      <div class="section-card">
        <div class="section-header">U History (last 10)</div>
        <div class="section-body scroll-y">
          ${uHistArr.length ? uHistArr.slice(-10).reverse().map(h =>
            `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
              <span class="text-xs text-muted">${ago(h.timestamp)}</span>
              <span class="mono ${uColor(h.u_score)}">${n(h.u_score,4)}</span>
              <span class="text-xs text-muted" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">${esc(h.reason||'')}</span>
            </div>`
          ).join('') : emptyState('No history', 'No recent canonical U samples were stored for this platform.')}
        </div>
      </div>
      <div class="section-card">
        <div class="section-header">Live Broker State</div>
        <div class="section-body scroll-y">
          ${livePositions.length ? livePositions.map(pos =>
            `<div style="padding:6px 0;border-bottom:1px solid var(--border)">
              <div class="mono text-sm">${esc(pos.symbol || '--')} <span class="text-muted">${esc(pos.secType || '--')}</span></div>
              <div class="text-xs text-muted">qty=${esc(pos.position)} | avgCost=${esc(pos.avgCost)}</div>
            </div>`
          ).join('') : emptyState('No live broker positions', 'This platform is not currently exposing live broker position state.')}
        </div>
      </div>
      <div class="section-card">
        <div class="section-header">Signals (${sigValid}/${sigTotal} valid)</div>
        <div class="section-body scroll-y">
          ${sigProblems.length ? sigProblems.map(p =>
            `<div style="padding:6px 0;border-bottom:1px solid var(--border)">
              <div class="mono text-sm">${esc(p.strategy)}</div>
              <div class="text-xs text-red">${(p.blockers||[]).join(', ')}</div>
            </div>`
          ).join('') : infoState(`Avg confidence: ${n(signals?.avg_confidence,2)}`, 'No blocking signal problems were reported for this platform in the current snapshot.')}
        </div>
      </div>
      <div class="section-card">
        <div class="section-header">Recent Activity</div>
        <div class="section-body no-pad scroll-y">
          ${tradeArr.length ? tableWrap(`<table><thead><tr><th>Time</th><th>Strategy</th><th>Symbol</th><th>Dir</th><th>Profit</th><th>Status</th></tr></thead><tbody>` +
            tradeArr.slice(0,15).map(t => {
              const p = t.profit??t.pnl??null;
              const strategyLabel = t.strategy_id||t.strategy||'--';
              return `<tr>
                <td class="nowrap text-muted text-xs">${ago(t.timestamp||t.opened_at)}</td>
                <td class="mono text-xs">${esc(strategyLabel)}${t.quantity!=null ? ` <span class="text-muted">x${esc(t.quantity)}</span>` : ''}</td>
                <td>${esc(t.symbol||t.sec_type||'--')}</td>
                <td>${esc(t.direction||'--')}</td>
                <td class="mono ${p>0?'text-green':p<0?'text-red':''}">${p!=null?n(p,4):'--'}</td>
                <td>${t.execution_type==='broker_position'
                    ? badge('open-position','blue')
                    : (t.execution_type==='browser_click_unverified'
                    ? badge('click-only','amber')
                    : (t.execution_type==='browser_ui_confirmed'
                      ? badge('ui-confirmed','green')
                      : (t.resolved?badge('resolved','green'):badge('open','amber'))))}</td>
              </tr>`;
            }).join('') + '</tbody></table>', 760) : emptyState('No activity', 'No canonical platform activity was returned for this platform.')}
        </div>
      </div>
    </div>
  `;
}

function switchPlatform(pname) {
  activePlatform = pname;
  document.querySelectorAll('.platform-tab').forEach(t => t.classList.toggle('active', t.dataset.platform===pname));
  document.querySelectorAll('.platform-view').forEach(v => v.classList.toggle('active', v.id==='pview-'+pname));
  renderPlatformFocus('platform-focus', lastPlatformOperating, lastPlatformSummary || {});
}

/* ─────────────────────────────────────────────
   STRATEGY ENGINE PANEL
───────────────────────────────────────────── */
async function refreshStrategy() {
  const [ranking, edgeValidation, contextEdgeValidation, scorecards, expectancy, hypotheses, activeCatalog, learningLoop, operating] = await Promise.all([
    api('/brain/strategy-engine/ranking-v2'),
    api('/brain/strategy-engine/edge-validation'),
    api('/brain/strategy-engine/context-edge-validation'),
    api('/brain/strategy-engine/scorecards'),
    api('/brain/strategy-engine/expectancy'),
    api('/brain/strategy-engine/hypotheses'),
    api('/brain/strategy-engine/active-catalog'),
    api('/brain/strategy-engine/learning-loop'),
    api('/brain/operating-context'),
  ]);

  const totalStrategies = safe(()=>ranking.ranked?.length, 0);
  const topState = deriveCanonicalTopState(ranking);
  const canonicalTop = topState.canonicalTop;
  const rankedLeader = topState.rankedLeader;
  const topId = topState.topId;
  const topGovState = topState.topGovState;
  const validatedCount = safe(()=>edgeValidation?.summary?.validated_count, 0);
  const promotableCount = safe(()=>edgeValidation?.summary?.promotable_count, 0);
  const probationCount = safe(()=>edgeValidation?.summary?.probation_count, 0);
  const blockedCount = safe(()=>edgeValidation?.summary?.blocked_count, 0);
  const topExp = safe(()=>expectancy?.summary?.top_strategy?.expectancy);
  const posStratCount = safe(()=>expectancy?.summary?.positive_expectancy_strategies_count, 0);
  const hypoResults = asArray(hypotheses, 'results');
  const hypothesesTotal = hypoResults.length;
  const hypothesesTesting = hypoResults.filter(h=>h.status==='in_test').length;
  const hypothesesQueued = hypoResults.filter(h=>h.status==='queued').length;

  renderStrategyDecisionStrip('strategy-decision-strip', ranking, edgeValidation, operating);
  renderStrategySemantics('strategy-semantics', ranking, operating);
  renderStrategyOperatingSummary('strategy-operating-summary', ranking, edgeValidation, operating);
  renderStrategyFocus('strategy-focus', operating, ranking);
  const focusStrategies = deriveFocusStrategies(ranking, operating);

  if (!ranking && !edgeValidation && !contextEdgeValidation && !scorecards && !expectancy && !hypotheses) {
    document.getElementById('strategy-kpis').innerHTML = errorState('Failed to load strategy engine data', 'The entire strategy engine panel failed to receive canonical data.');
    document.getElementById('strategy-edge-validation').innerHTML = errorState('API unreachable', 'Edge validation data is unavailable.');
    document.getElementById('strategy-focus-candidates').innerHTML = errorState('API unreachable', 'Focus lane candidates could not be computed.');
    document.getElementById('strategy-ranking').innerHTML = errorState('API unreachable', 'Strategy ranking data is unavailable.');
    document.getElementById('strategy-scorecards').innerHTML = errorState('API unreachable', 'Scorecard data is unavailable.');
    document.getElementById('strategy-expectancy').innerHTML = errorState('API unreachable', 'Expectancy summary is unavailable.');
    document.getElementById('strategy-hypotheses').innerHTML = errorState('API unreachable', 'Hypothesis tracking is unavailable.');
    return;
  }

  if (focusStrategies.length) {
    document.getElementById('strategy-focus-candidates').innerHTML = tableWrap(`<table><thead><tr>
      <th>Strategy</th><th>Venue</th><th>Signal</th><th>Edge</th><th>Context</th><th>Resolved</th><th>Blockers</th>
    </tr></thead><tbody>` +
      focusStrategies.map(s => `<tr>
        <td class="mono text-xs" style="font-weight:600">${esc(s.strategy_id)}</td>
        <td>${esc(s.venue || '--')}</td>
        <td>${s.execution_ready_now ? badge('ready','green') : badge('not-ready','amber')}</td>
        <td>${statusBadge(s.edge_state || '--')}</td>
        <td>${statusBadge(s.current_context_edge_state || '--')}</td>
        <td class="mono">${s.entries_resolved ?? '--'}</td>
        <td class="text-xs text-muted">${esc((s.blockers || []).slice(0,4).join(', ') || '--')}</td>
      </tr>`).join('') + '</tbody></table>', 860);
  } else {
    document.getElementById('strategy-focus-candidates').innerHTML = emptyState('No focus-lane strategies', 'No ranked strategies currently match the active operating lane.');
  }

  document.getElementById('strategy-kpis').innerHTML = [
    renderKpiCard('Total Strategies', ranking==null?'N/A':`${totalStrategies}`, '', ranking==null?'warn':'accent'),
    renderKpiCard('Canonical Top', esc(topId === '--' ? 'none_selected' : topId), topId === '--' ? `ranked leader ${esc(rankedLeader?.strategy_id || '--')}` : esc(topGovState), 'text-accent', 'font-size:12px;word-break:break-all'),
    renderKpiCard('Top Expectancy', n(topExp,4), `${posStratCount} positive`, (topExp||0)>0?'ok':'err'),
    renderKpiCard('Hypotheses', hypotheses==null?'N/A':`${hypothesesTesting} testing / ${hypothesesQueued} queued / ${hypothesesTotal}`, '', hypotheses==null?'warn':'accent'),
    renderKpiCard('Validated Edge', edgeValidation==null?'N/A':`${validatedCount}/${promotableCount}`, 'validated / promotable', edgeValidation==null?'warn':(validatedCount||promotableCount)?'ok':'err'),
    renderKpiCard('Probation', edgeValidation==null?'N/A':`${probationCount}`, `${blockedCount} blocked`, edgeValidation==null?'warn':probationCount?'warn':'accent'),
  ].join('');

  if (edgeValidation?.summary) {
    const s = edgeValidation.summary;
    const topExec = s.top_execution_edge || {};
    const bestProb = s.best_probation || {};
    const cs = contextEdgeValidation?.summary || {};
    document.getElementById('strategy-edge-validation').innerHTML = kvBlock([
      ['Promotable', s.promotable_count ?? 0],
      ['Validated', s.validated_count ?? 0],
      ['Forward Validation', s.forward_validation_count ?? 0],
      ['Probation', s.probation_count ?? 0],
      ['Blocked', s.blocked_count ?? 0],
      ['Refuted', s.refuted_count ?? 0],
      ['Context Validated', cs.validated_count ?? 0],
      ['Context Supportive', cs.supportive_count ?? 0],
      ['Context Contradicted', cs.contradicted_count ?? 0],
      ['Top Execution Edge', esc(topExec.strategy_id || '--')],
      ['Execution Lane', esc(topExec.execution_lane || '--')],
      ['Execution Ready Now', topExec.execution_ready_now ? 'true' : 'false', topExec.execution_ready_now ? 'text-green' : 'text-red'],
      ['Best Probation', esc(bestProb.strategy_id || '--')],
      ['Probation Blockers', esc((bestProb.blockers || []).slice(0,3).join(', ') || '--')],
    ]) + noteBlock('Validation state explains whether a strategy is merely ranked, genuinely promotable, or still blocked by governance and context gates.', 'info');
  } else {
    document.getElementById('strategy-edge-validation').innerHTML = emptyState('No edge validation data', 'No edge validation summary was returned for this refresh cycle.');
  }

  if (ranking?.ranked?.length) {
    document.getElementById('strategy-ranking').innerHTML = tableWrap(`<table><thead><tr>
      <th>#</th><th>Strategy</th><th>Focus</th><th>Venue</th><th>Family</th><th>Score</th><th>Exp</th><th>WR</th><th>Resolved</th><th>Governance</th><th>Edge</th><th>Context Edge</th><th>Signal Ready</th>
    </tr></thead><tbody>` +
      ranking.ranked.map((s,i) => `<tr>
        <td class="text-muted">${i+1}</td>
        <td class="mono text-xs" style="font-weight:600">${esc(s.strategy_id)}</td>
        <td>${strategyMatchesOperatingLane(s, operating) ? badge('focus','blue') : '<span class="text-muted">--</span>'}</td>
        <td>${esc(s.venue||'--')}</td>
        <td class="text-muted">${esc(s.family||'--')}</td>
        <td class="mono">${n(s.priority_score,4)}</td>
        <td class="mono ${(s.expectancy||0)>0?'text-green':(s.expectancy||0)<0?'text-red':''}">${n(s.expectancy,2)}</td>
        <td class="mono">${pct(s.win_rate)}</td>
        <td class="mono">${s.entries_resolved??'--'}</td>
        <td>${statusBadge(s.governance_state||'--')}</td>
        <td>${statusBadge(s.edge_state||'--')}</td>
        <td>${statusBadge(s.current_context_edge_state||'--')}</td>
        <td>${s.execution_ready_now ? badge('yes','green') : badge('no','amber')}</td>
      </tr>`).join('') + '</tbody></table>', 1200);
    document.getElementById('strategy-ranking').innerHTML = noteBlock('This is the global technical ranking. High rank does not mean selected for operation; use Canonical Top and Focus Lane Candidates for operating decisions.', 'warn') + document.getElementById('strategy-ranking').innerHTML;
  } else {
    document.getElementById('strategy-ranking').innerHTML = emptyState('No ranking data', 'The ranking endpoint did not return ranked strategies.');
  }

  if (scorecards?.scorecards) {
    const cards = scorecards.scorecards;
    const entries = Object.entries(cards);
    if (entries.length) {
      document.getElementById('strategy-scorecards').innerHTML = tableWrap(`<table><thead><tr>
        <th>Strategy</th><th>Venue</th><th>Taken</th><th>Resolved</th><th>Open</th><th>Wins</th><th>Losses</th><th>WR</th><th>Expectancy</th><th>PnL</th><th>Sample Q</th><th>Governance</th>
      </tr></thead><tbody>` +
        entries.map(([id, sc]) => `<tr>
          <td class="mono text-xs" style="font-weight:600">${esc(id)}</td>
          <td>${esc(sc.venue||'--')}</td>
          <td class="mono">${sc.entries_taken??0}</td>
          <td class="mono">${sc.entries_resolved??0}</td>
          <td class="mono">${sc.entries_open??0}</td>
          <td class="mono text-green">${sc.wins??0}</td>
          <td class="mono text-red">${sc.losses??0}</td>
          <td class="mono">${pct(sc.win_rate)}</td>
          <td class="mono ${(sc.expectancy||0)>0?'text-green':(sc.expectancy||0)<0?'text-red':''}">${n(sc.expectancy,4)}</td>
          <td class="mono ${(sc.net_pnl||0)>=0?'text-green':'text-red'}">${n(sc.net_pnl,2)}</td>
          <td class="mono">${n(sc.sample_quality,2)}</td>
          <td>${statusBadge(sc.governance_state||sc.status||'--')}</td>
        </tr>`).join('') + '</tbody></table>', 1100);
    } else {
      document.getElementById('strategy-scorecards').innerHTML = emptyState('No scorecards', 'The scorecards payload was empty.');
    }
  } else {
    document.getElementById('strategy-scorecards').innerHTML = emptyState('No scorecards', 'The scorecards endpoint did not return data.');
  }

  if (expectancy?.summary) {
    const s = expectancy.summary;
    const ts = s.top_strategy || {};
    document.getElementById('strategy-expectancy').innerHTML = kvBlock([
      ['Strategies Analyzed', s.strategies_count ?? '--'],
      ['Positive Expectancy', s.positive_expectancy_strategies_count ?? 0],
      ['Top Strategy', esc(ts.strategy_id || '--')],
      ['Top Expectancy', n(ts.expectancy, 4), (ts.expectancy||0)>0?'text-green':'text-red'],
      ['Top Win Rate', pct(ts.win_rate)],
      ['Top PnL', n(ts.net_pnl, 2)],
      ['Top Sample Quality', n(ts.sample_quality, 2)],
      ['Top Governance', esc(ts.governance_state || '--')],
      ['Symbol Combos', s.strategy_symbols_count ?? '--'],
      ['Context Combos', s.strategy_contexts_count ?? '--'],
    ]);
  } else {
    document.getElementById('strategy-expectancy').innerHTML = emptyState('No expectancy data', 'The expectancy summary endpoint did not return data.');
  }

  if (hypoResults.length) {
    document.getElementById('strategy-hypotheses').innerHTML = tableWrap(`<table><thead><tr>
      <th>Hypothesis</th><th>Strategy</th><th>Status</th><th>Result</th><th>Resolved</th><th>Expectancy</th>
    </tr></thead><tbody>` +
      hypoResults.map(h => `<tr>
        <td class="mono text-xs">${esc(h.hypothesis_id||'--')}</td>
        <td class="mono text-xs">${esc(h.strategy_id||'--')}</td>
        <td>${statusBadge(h.status||'--')}</td>
        <td>${esc(h.result||'--')}</td>
        <td class="mono">${h.entries_resolved??'--'}</td>
        <td class="mono ${(h.expectancy||0)>0?'text-green':(h.expectancy||0)<0?'text-red':''}">${n(h.expectancy,4)}</td>
      </tr>`).join('') + '</tbody></table>', 860);
  } else {
    document.getElementById('strategy-hypotheses').innerHTML = emptyState('No hypotheses', 'No hypothesis results were returned for this refresh cycle.');
  }

  if (activeCatalog?.items?.length) {
    document.getElementById('strategy-active-catalog').innerHTML = `<table><thead><tr>
      <th>Strategy</th><th>Venue</th><th>Lane</th><th>State</th><th>Reason</th><th>Entries</th><th>Expectancy</th><th>Sample Q</th><th>Scope</th>
    </tr></thead><tbody>` +
      activeCatalog.items.map(c => `<tr>
        <td class="mono text-xs" style="font-weight:600">${esc(c.strategy_id||'--')}</td>
        <td>${esc(c.venue||'--')}</td>
        <td class="mono text-xs text-muted">${esc(c.lane_key||'--')}</td>
        <td>${statusBadge(c.catalog_state||'--')}</td>
        <td class="text-muted text-xs">${esc(c.catalog_reason||'--')}</td>
        <td class="mono">${c.entries_resolved??'--'}</td>
        <td class="mono ${(c.expectancy||0)>0?'text-green':(c.expectancy||0)<0?'text-red':''}">${n(c.expectancy,4)}</td>
        <td class="mono">${n(c.sample_quality,2)}</td>
        <td>${statusBadge(c.decision_scope||c.catalog_state||'--')}</td>
      </tr>`).join('') + '</tbody></table>';
  } else {
    document.getElementById('strategy-active-catalog').innerHTML = emptyState('No active catalog data', 'Active catalog data was not returned by the runtime.');
  }

  if (learningLoop?.summary) {
    const ll = learningLoop.summary;
    document.getElementById('strategy-learning-loop').innerHTML = kvBlock([
      ['Top Learning Action', esc(ll.top_learning_action || '--')],
      ['Operational Count', ll.operational_count ?? 0],
      ['Audit Required', ll.audit_count ?? 0, (ll.audit_count||0)>0?'text-red':''],
      ['Probation Continue', ll.probation_continue_count ?? 0],
      ['Forward Validation', ll.forward_validation_count ?? 0, (ll.forward_validation_count||0)>0?'text-green':''],
      ['Variant Candidates', ll.variant_generation_candidate_count ?? 0],
      ['Allow Variant Gen', ll.allow_variant_generation ? 'true' : 'false', ll.allow_variant_generation?'text-green':'text-muted'],
      ['Top Hypothesis', esc(ll.top_hypothesis_id || '--')],
      ['Validated Edge Count', ll.validated_edge_count ?? 0],
    ]);
  } else {
    document.getElementById('strategy-learning-loop').innerHTML = emptyState('No learning loop data', 'Learning loop state is unavailable for this refresh cycle.');
  }
}
