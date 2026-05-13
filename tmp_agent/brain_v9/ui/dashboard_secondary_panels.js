/* ─────────────────────────────────────────────
   AUTONOMY LOOP PANEL
   API: /autonomy/status → {running, active_tasks, reports_count, ibkr_ingester:{running,interval_seconds,consecutive_failures,last_checked_utc,last_connected,last_symbol_count,last_error_count}}
   API: /brain/autonomy/sample-accumulator → {ok, status:{running,last_trade_time,session_trades_count,check_interval_minutes,cooldown_minutes,max_trades_per_session,...}, running}
   API: /brain/autonomy/ibkr-ingester → {ok,running,interval_seconds,consecutive_failures,last_checked_utc,last_connected,last_symbol_count,last_error_count}
   API: /autonomy/reports?limit=20 → [{timestamp,type,errors_found?,errors?,cpu?,memory?,u_score?,verdict?,...},...]
───────────────────────────────────────────── */
async function refreshAutonomy() {
  const [autonomy, accumulator, ibkr, reports] = await Promise.all([
    api('/autonomy/status'),
    api('/brain/autonomy/sample-accumulator'),
    api('/brain/autonomy/ibkr-ingester'),
    api('/autonomy/reports?limit=20'),
  ]);

  // KPIs
  const running = safe(()=>autonomy.running, false);
  const taskCount = safe(()=>autonomy.active_tasks, 0);
  const reportsCount = safe(()=>autonomy.reports_count, 0);
  // accumulator: nested under .status
  const accStatus = accumulator?.status || accumulator || {};
  const accRunning = safe(()=>accStatus.running || accumulator?.running, false);
  const accTrades = safe(()=>accStatus.session_trades_count, 0);
  const ibkrRunning = safe(()=>ibkr?.running, false);
  const rpts = normalizeReports(reports);

  renderAutonomyDecisionStrip('autonomy-decision-strip', autonomy, accumulator, ibkr, reports);
  document.getElementById('autonomy-kpis').innerHTML = `
    <div class="kpi"><div class="label">Loop Status</div><div class="value ${autonomy==null?'warn':running?'ok':'err'}">${autonomy==null?'N/A':running?'Running':'Stopped'}</div></div>
    <div class="kpi"><div class="label">Active Tasks</div><div class="value accent">${autonomy==null?'--':taskCount}</div></div>
    <div class="kpi"><div class="label">Reports</div><div class="value accent">${autonomy==null?'--':reportsCount}</div></div>
    <div class="kpi"><div class="label">Accumulator</div><div class="value ${accumulator==null?'warn':accRunning?'ok':'err'}">${accumulator==null?'N/A':accRunning?'Running':'Stopped'}</div><div class="sub">${accumulator==null?'--':accTrades} trades</div></div>
    <div class="kpi"><div class="label">IBKR Ingester</div><div class="value ${ibkr==null?'warn':ibkrRunning?'ok':'err'}">${ibkr==null?'N/A':ibkrRunning?'Running':'Stopped'}</div></div>
  `;
  document.getElementById('autonomy-note').innerHTML = noteBlock(`Autonomy separates orchestration health, sample accumulation, ingester freshness, and reports. ${rpts.length} recent reports help diagnose the loop; they do not replace operating context.`, 'info');

  // Loop status detail
  if (autonomy) {
    // ibkr_ingester is embedded in /autonomy/status
    const ibkrEmbed = autonomy.ibkr_ingester || {};
    document.getElementById('autonomy-loop').innerHTML = kvBlock([
      ['Running', running ? 'Yes' : 'No', running ? 'text-green' : 'text-red'],
      ['Active Tasks', taskCount],
      ['Reports Count', reportsCount],
      ['IBKR Ingester', ibkrEmbed.running ? 'Running' : 'Stopped', ibkrEmbed.running ? 'text-green' : 'text-red'],
      ['IBKR Consecutive Failures', ibkrEmbed.consecutive_failures ?? '--'],
      ['IBKR Last Connected', ibkrEmbed.last_connected ? 'Yes' : 'No'],
      ['IBKR Symbols', ibkrEmbed.last_symbol_count ?? '--'],
      ['IBKR Errors', ibkrEmbed.last_error_count ?? '--'],
    ]);
  } else {
    document.getElementById('autonomy-loop').innerHTML = '<div class="err-msg">Failed to load autonomy status</div>';
  }

  // Sample accumulator — fields under .status
  if (accumulator) {
    const a = accStatus;
    const perPlatform = a.per_platform || {};
    const platformRows = Object.entries(perPlatform).map(([name, row]) => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <div style="font-weight:600">${esc(name)}</div>
          <div class="text-xs text-muted">
            trades=${row.session_trades_count ?? '--'} | skips=${row.consecutive_skips ?? '--'} | last=${ago(row.last_trade_time)}
          </div>
        </div>
        <div>${statusBadge(row.running ? 'running' : 'stopped')}</div>
      </div>
    `).join('');
    document.getElementById('autonomy-accumulator').innerHTML = `
      ${kvBlock([
        ['Running', accRunning ? 'Yes' : 'No', accRunning ? 'text-green' : 'text-red'],
        ['Mode', a.mode ?? '--'],
        ['Session Trades (total)', a.session_trades_count ?? '--'],
        ['Active Platforms', a.active_platforms ?? '--'],
        ['Consecutive Skips (total)', a.consecutive_skips ?? '--'],
        ['Aggregation', a.aggregation ?? '--'],
        ['Target Entries', a.target_entries ?? '--'],
        ['Last Trade', ago(a.last_trade_time)],
      ])}
      <div class="mt-12">
        <div class="label">Per Platform</div>
        ${platformRows || '<div class="text-muted">No per-platform accumulator data</div>'}
      </div>
    `;
  } else {
    document.getElementById('autonomy-accumulator').innerHTML = '<div class="err-msg">Failed to load accumulator</div>';
  }

  // IBKR ingester — dedicated endpoint
  if (ibkr) {
    document.getElementById('autonomy-ibkr').innerHTML = kvBlock([
      ['Running', ibkr.running ? 'Yes' : 'No', ibkr.running ? 'text-green' : 'text-red'],
      ['Interval (s)', ibkr.interval_seconds ?? '--'],
      ['Consecutive Failures', ibkr.consecutive_failures ?? 0],
      ['Last Checked', ago(ibkr.last_checked_utc)],
      ['Last Connected', ibkr.last_connected ? 'Yes' : 'No', ibkr.last_connected ? 'text-green' : 'text-red'],
      ['Symbols Tracked', ibkr.last_symbol_count ?? '--'],
      ['Error Count', ibkr.last_error_count ?? 0],
    ]);
  } else {
    document.getElementById('autonomy-ibkr').innerHTML = '<div class="text-muted">No IBKR ingester data</div>';
  }

  // Reports — array directly [{timestamp,type,...},...]
  if (rpts.length) {
    document.getElementById('autonomy-reports').innerHTML = tableWrap(`<table><thead><tr><th>Time</th><th>Type</th><th>Detail</th></tr></thead><tbody>` +
      rpts.slice(0,15).map(r => {
        let detail = '';
        if (r.type === 'utility_refresh') detail = `U=${n(r.u_score,4)} ${esc(r.verdict)} blockers=${(r.blockers||[]).length}`;
        else if (r.type === 'resource_check') detail = `CPU=${n(r.cpu,1)}% MEM=${n(r.memory,1)}% DISK=${n(r.disk,1)}% ${(r.alerts||[]).join(', ')}`;
        else if (r.type === 'debug_scan') detail = `${r.errors_found||0} errors found`;
        else detail = esc(r.detail || r.summary || JSON.stringify(r).slice(0,80));
        return `<tr>
          <td class="nowrap text-muted text-xs">${ago(r.timestamp)}</td>
          <td>${statusBadge(r.type||'--')}</td>
          <td class="text-sm">${detail}</td>
        </tr>`;
      }).join('') + '</tbody></table>', 760);
  } else {
    document.getElementById('autonomy-reports').innerHTML = '<div class="loading">No reports</div>';
  }
}

/* ─────────────────────────────────────────────
   ROADMAP PANEL
   API: /brain/roadmap/governance → {canonical:{roadmap_id,current_phase,current_stage,active_title,next_item,counts:{total,done,...}}, promotion:{...}}
   API: /brain/roadmap/development-status → {roadmap_id,phase_id,phase_title,phase_objective,work_status,promotion_state,blocker_count,blockers[],...}
   API: /brain/post-bl-roadmap/status → {roadmap_id,enabled,work_status,title,mission,current_focus:{item_id,title,...},items:[{item_id,title,status,...},...]}
───────────────────────────────────────────── */
async function refreshRoadmap() {
  const [governance, devStatus, postBL] = await Promise.all([
    api('/brain/roadmap/governance'),
    api('/brain/roadmap/development-status'),
    api('/brain/post-bl-roadmap/status'),
  ]);

  renderRoadmapDecisionStrip('roadmap-decision-strip', governance, devStatus, postBL);
  document.getElementById('roadmap-note').innerHTML = noteBlock('Roadmap separates canonical governance acceptance, current development execution, and post-BL continuation. Progress counts are not the same thing as readiness to promote.', 'info');

  // Governance — nested under .canonical and .promotion
  if (governance) {
    const c = governance.canonical || {};
    const p = governance.promotion || {};
    const acc = p.acceptance || {};
    document.getElementById('roadmap-governance').innerHTML = kvBlock([
      ['Roadmap ID', esc(c.roadmap_id)],
      ['Phase', esc(c.current_phase)],
      ['Stage', esc(c.current_stage)],
      ['Title', esc(c.active_title)],
      ['Next Item', esc(c.next_item || 'none')],
      ['Done / Total', `${c.counts?.done??0} / ${c.counts?.total??0}`],
      ['In Progress', c.counts?.in_progress ?? 0],
      ['Blocked', c.counts?.blocked ?? 0],
      ['Accepted', acc.accepted ? 'Yes' : 'No', acc.accepted ? 'text-green' : 'text-red'],
    ]);
    // Acceptance checks
    const checks = acc.checks || [];
    if (checks.length) {
      document.getElementById('roadmap-governance').innerHTML += '<div class="mt-12"><div class="text-xs text-muted mb-8">Acceptance Checks:</div>' +
        checks.map(ch => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
          <span class="text-sm">${esc(ch.id)}</span>
          ${ch.passed ? badge('pass','green') : badge('fail','red')}
        </div>`).join('') + '</div>';
    }
  } else {
    document.getElementById('roadmap-governance').innerHTML = '<div class="err-msg">Failed to load governance</div>';
  }

  // Development status — flat top-level fields
  if (devStatus) {
    const d = devStatus;
    document.getElementById('roadmap-development').innerHTML = kvBlock([
      ['Work Status', esc(d.work_status)],
      ['Phase', esc(d.phase_id)],
      ['Title', esc(d.phase_title)],
      ['Objective', esc(d.phase_objective)],
      ['Deliverable', esc(d.phase_deliverable)],
      ['Room', esc(d.room_id)],
      ['Promotion', esc(d.promotion_state)],
      ['Evaluator', esc(d.evaluator_status)],
      ['Accepted', d.accepted ? 'Yes' : 'No', d.accepted ? 'text-green' : 'text-red'],
      ['Blockers', d.blocker_count ?? 0],
    ]);
    const workItems = (d.current_work_items || []).map(item => String(item));
    const blockerItems = (d.blockers || []).map(b => {
      const checkId = b.check_id || b.id || '';
      const detail = b.detail || b.message || '';
      return checkId ? `${checkId}: ${detail}` : detail;
    });
    document.getElementById('roadmap-development').innerHTML += compactListSection('Current Work', workItems, workItems.length ? 'info' : 'neutral', 5, 'none');
    document.getElementById('roadmap-development').innerHTML += compactListSection('Execution Blockers', blockerItems, blockerItems.length ? 'warn' : 'neutral', 5, 'none');
  } else {
    document.getElementById('roadmap-development').innerHTML = '<div class="err-msg">Failed to load dev status</div>';
  }

  // Post-BL Roadmap
  if (postBL) {
    const p = postBL;
    document.getElementById('roadmap-postbl').innerHTML = kvBlock([
      ['Roadmap ID', esc(p.roadmap_id)],
      ['Title', esc(p.title)],
      ['Mission', esc(p.mission)],
      ['Enabled', p.enabled ? 'Yes' : 'No', p.enabled ? 'text-green' : 'text-red'],
      ['Work Status', esc(p.work_status)],
      ['Focus Item', esc(p.current_focus?.item_id)],
      ['Focus Title', esc(p.current_focus?.title)],
      ['Progress', `${p.summary?.done??0} done / ${p.summary?.active??0} active / ${p.summary?.queued??0} queued`],
    ]);
    // Items list
    const items = p.items || [];
    if (items.length) {
      document.getElementById('roadmap-postbl').innerHTML += '<div class="mt-12 scroll-y">' + tableWrap('<table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Detail</th></tr></thead><tbody>' +
        items.map(it => `<tr>
          <td class="mono">${esc(it.item_id)}</td>
          <td>${esc(it.title)}</td>
          <td>${statusBadge(it.status||'--')}</td>
          <td class="text-xs text-muted">${esc(it.detail||'')}</td>
        </tr>`).join('') + '</tbody></table>', 760) + '</div>';
    }
  } else {
    document.getElementById('roadmap-postbl').innerHTML = '<div class="err-msg">Failed to load post-BL roadmap</div>';
  }
}

/* ─────────────────────────────────────────────
   META SYSTEMS PANEL
   API: /brain/meta-improvement/status → {mission:{goal,...}, self_model:{overall_score,domains:[{domain_id,title,score,status},...]},...}
   API: /brain/utility-governance/status → {current_state,work_status,accepted_baseline,acceptance_checks:[{check_id,passed,detail}],u_proxy_score,effective_signal_score,verdict,allow_promote,blockers[],next_actions[],pending_improvement_items[],effective_reference_strategy:{...}}
   API: /brain/chat-product/status → {title,current_state,work_status,accepted_baseline,acceptance_checks[],quality_checks[],quality_score,pending_improvement_items[],next_actions[]}
───────────────────────────────────────────── */
async function refreshMeta() {
  const [metaImprove, utilGov, chatProduct] = await Promise.all([
    api('/brain/meta-improvement/status'),
    api('/brain/utility-governance/status'),
    api('/brain/chat-product/status'),
  ]);

  // Meta Improvement — mission.goal, self_model.overall_score, self_model.domains[]
  if (metaImprove) {
    const m = metaImprove;
    const sm = m.self_model || {};
    const domains = sm.domains || [];
    document.getElementById('meta-improvement').innerHTML = kvBlock([
      ['Mission', esc(m.mission?.goal)],
      ['Continuation', esc(m.mission?.continuation_rule)],
      ['Overall Score', n(sm.overall_score, 4)],
      ['Identity Mode', esc(sm.identity?.current_mode)],
    ]);
    // Domains table
    if (domains.length) {
      document.getElementById('meta-improvement').innerHTML += '<div class="mt-12"><div class="text-xs text-muted mb-8">Domains:</div>' + tableWrap('<table><thead><tr><th>Domain</th><th>Score</th><th>Status</th></tr></thead><tbody>' +
        domains.map(d => `<tr>
          <td>${esc(d.title || d.domain_id)}</td>
          <td class="mono ${d.score>=0.7?'text-green':d.score>=0.4?'text-amber':'text-red'}">${n(d.score,2)}</td>
          <td>${statusBadge(d.status)}</td>
        </tr>`).join('') + '</tbody></table>', 720) + '</div>';
    }
  } else {
    document.getElementById('meta-improvement').innerHTML = '<div class="err-msg">Failed to load</div>';
  }

  // Utility Governance — u_proxy_score, effective_signal_score, acceptance_checks[], effective_reference_strategy
  if (utilGov) {
    const u = utilGov;
    const refStrat = u.effective_reference_strategy || {};
    document.getElementById('meta-utility-gov').innerHTML = kvBlock([
      ['State', esc(u.current_state)],
      ['Work Status', esc(u.work_status)],
      ['Accepted Baseline', u.accepted_baseline ? 'Yes' : 'No', u.accepted_baseline ? 'text-green' : 'text-red'],
      ['U Proxy Score', n(u.u_proxy_score, 4), uColor(u.u_proxy_score)],
      ['Signal Score', n(u.effective_signal_score, 4)],
      ['Verdict', esc(u.verdict)],
      ['Allow Promote', u.allow_promote ? 'Yes' : 'No', u.allow_promote ? 'text-green' : 'text-red'],
      ['Blockers', (u.blockers||[]).length, (u.blockers||[]).length ? 'text-red' : 'text-green'],
      ['Ref Strategy', esc(refStrat.strategy_id)],
      ['Ref Expectancy', n(refStrat.expectancy, 4)],
    ]);
    // Blockers detail
    if (u.blockers?.length) {
      document.getElementById('meta-utility-gov').innerHTML += '<div class="mt-8">' +
        u.blockers.map(b => `<div class="text-xs text-red" style="padding:2px 0">- ${esc(b)}</div>`).join('') + '</div>';
    }
    // Acceptance checks
    const checks = u.acceptance_checks || [];
    if (checks.length) {
      document.getElementById('meta-utility-gov').innerHTML += '<div class="mt-12"><div class="text-xs text-muted mb-8">Acceptance Checks:</div>' +
        checks.map(c => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
          <span class="text-sm">${esc(c.check_id)}</span>
          ${c.passed ? badge('pass','green') : badge('fail','red')}
        </div>`).join('') + '</div>';
    }
    // Next actions
    if (u.next_actions?.length) {
      document.getElementById('meta-utility-gov').innerHTML += '<div class="mt-8"><div class="text-xs text-muted">Next: ' + u.next_actions.map(a=>esc(a)).join(', ') + '</div></div>';
    }
  } else {
    document.getElementById('meta-utility-gov').innerHTML = '<div class="err-msg">Failed to load</div>';
  }

  // Chat Product — title, current_state, quality_score, acceptance_checks[], quality_checks[]
  if (chatProduct) {
    const c = chatProduct;
    document.getElementById('meta-chat-product').innerHTML = kvBlock([
      ['Product', esc(c.title)],
      ['State', esc(c.current_state)],
      ['Work Status', esc(c.work_status)],
      ['Accepted Baseline', c.accepted_baseline ? 'Yes' : 'No', c.accepted_baseline ? 'text-green' : 'text-red'],
      ['Quality Score', n(c.quality_score, 2), c.quality_score >= 0.8 ? 'text-green' : 'text-amber'],
      ['Failed Checks', c.failed_check_count ?? 0],
    ]);
    // Acceptance checks
    const aChecks = c.acceptance_checks || [];
    const qChecks = c.quality_checks || [];
    const allChecks = [...aChecks, ...qChecks];
    if (allChecks.length) {
      document.getElementById('meta-chat-product').innerHTML += '<div class="mt-12"><div class="text-xs text-muted mb-8">Checks:</div>' +
        allChecks.map(ch => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
          <span class="text-sm">${esc(ch.check_id)}</span>
          ${ch.passed ? badge('pass','green') : badge('fail','red')}
        </div>`).join('') + '</div>';
    }
    // Pending items
    if (c.pending_improvement_items?.length) {
      document.getElementById('meta-chat-product').innerHTML += '<div class="mt-8"><div class="text-xs text-muted mb-8">Pending:</div>' +
        c.pending_improvement_items.map(it => `<div class="text-sm" style="padding:2px 0 2px 12px">- ${esc(it)}</div>`).join('') + '</div>';
    }
  } else {
    document.getElementById('meta-chat-product').innerHTML = '<div class="err-msg">Failed to load</div>';
  }
}

/* ─────────────────────────────────────────────
   SELF-IMPROVEMENT PANEL
   API: /brain/self-improvement/ledger → {entries:[{change_id,timestamp,objective,status,validation,health,rollback,impact_after,impact_delta,...},...]}
───────────────────────────────────────────── */
async function refreshSelfImprove() {
  const ledger = await api('/brain/self-improvement/ledger');

  if (!ledger) {
    document.getElementById('selfimprove-kpis').innerHTML = '<div class="err-msg" style="grid-column:1/-1">Failed to load self-improvement data</div>';
    document.getElementById('selfimprove-ledger').innerHTML = '<div class="err-msg">Failed to load ledger</div>';
    return;
  }

  // entries[] (NOT changes[])
  const entries = ledger.entries || [];
  const latest = entries.length ? entries[entries.length-1] : null;
  const promoted = entries.filter(c => c.status==='promoted').length;
  const rolledBack = entries.filter(c => c.status==='rolled_back' || c.rollback===true).length;

  document.getElementById('selfimprove-kpis').innerHTML = `
    <div class="kpi"><div class="label">Total Changes</div><div class="value accent">${entries.length}</div></div>
    <div class="kpi"><div class="label">Promoted</div><div class="value ok">${promoted}</div></div>
    <div class="kpi"><div class="label">Rolled Back</div><div class="value ${rolledBack?'err':'ok'}">${rolledBack}</div></div>
    <div class="kpi"><div class="label">Latest Status</div><div class="value">${latest ? statusBadge(latest.status||'--') : '--'}</div></div>
  `;

  if (entries.length) {
    document.getElementById('selfimprove-ledger').innerHTML = `<table><thead><tr>
      <th>Change ID</th><th>Objective</th><th>Status</th><th>Validation</th><th>Health</th><th>Rollback</th><th>Time</th>
    </tr></thead><tbody>` +
      entries.slice().reverse().map(c => `<tr>
        <td class="mono text-xs">${esc(c.change_id)}</td>
        <td class="text-sm">${esc(c.objective)}</td>
        <td>${statusBadge(c.status||'--')}</td>
        <td>${statusBadge(c.validation||'--')}</td>
        <td>${statusBadge(c.health||'--')}</td>
        <td>${c.rollback ? badge('yes','red') : badge('no','green')}</td>
        <td class="text-muted text-xs nowrap">${ago(c.timestamp)}</td>
      </tr>`).join('') + '</tbody></table>';
  } else {
    document.getElementById('selfimprove-ledger').innerHTML = '<div class="loading">No changes recorded</div>';
  }
}

/* ─────────────────────────────────────────────
   SYSTEM HEALTH PANEL
   API: /brain/health → {overall_status, services:{name:{healthy,latency_ms?,error?},...}, summary:{total,healthy,unhealthy}}
   API: /brain/pipeline-health → {ok, test_files, total_tests, failures, pipeline_verification:{tests:[{id,desc,verified},...],all_passing,count}, http_endpoint_tests:{count,all_passing}}
   API: /trading/policy → {global_rules:{paper_only,live_trading_forbidden,...}, platform_rules:{name:{paper_allowed,live_allowed,mode},...}}
───────────────────────────────────────────── */
async function refreshSystem() {
  const [health, pipeline, policy, operating, maintenance] = await Promise.all([
    api('/brain/health'),
    api('/brain/pipeline-health'),
    api('/trading/policy'),
    api('/brain/operating-context'),
    api('/brain/maintenance/status'),
  ]);

  // KPIs
  const overall = safe(()=>health.overall_status, 'unknown');
  // pipeline: total_tests and failures (NOT tests_passing)
  const testsTotal = safe(()=>pipeline.total_tests, '--');
  const testsFailed = safe(()=>pipeline.failures, 0);
  const testsPassing = testsTotal !== '--' ? testsTotal - testsFailed : '--';
  const pipelineOk = safe(()=>pipeline.ok, false);
  const paperOnly = safe(()=>policy.global_rules?.paper_only, '--');
  const maintenanceSummary = maintenance?.summary || {};
  const mComponents = maintenance?.components || {};

  renderSystemDecisionStrip('system-decision-strip', health, pipeline, policy, maintenance, operating);
  renderOperatingContext('system-operating', operating);
  renderMaintenanceControls('system-maintenance', maintenance);

  document.getElementById('system-kpis').innerHTML = `
    <div class="kpi"><div class="label">Overall Health</div><div class="value ${overall==='healthy'?'ok':overall==='degraded'?'warn':'err'}">${esc(overall)}</div><div class="sub">${safe(()=>health.summary?.healthy,0)}/${safe(()=>health.summary?.total,0)} services</div></div>
    <div class="kpi"><div class="label">Tests</div><div class="value ${testsFailed===0?'ok':'err'}">${testsPassing} / ${testsTotal}</div><div class="sub">${testsFailed} failures</div></div>
    <div class="kpi"><div class="label">Pipeline</div><div class="value ${pipeline==null?'warn':pipelineOk?'ok':'err'}">${pipeline==null?'N/A':pipelineOk?'All Passing':'Issues'}</div></div>
    <div class="kpi"><div class="label">Trading Mode</div><div class="value">${paperOnly===true ? badge('paper_only','green') : paperOnly===false ? badge('LIVE','red') : badge('unknown','amber')}</div></div>
    <div class="kpi"><div class="label">Maintenance</div><div class="value ${maintenanceSummary.degraded_or_down>0?'warn':'ok'}">${maintenanceSummary.healthy_or_running ?? '--'}/${maintenanceSummary.components ?? '--'}</div><div class="sub">${maintenanceSummary.degraded_or_down ?? '--'} degraded/down</div></div>
    <div class="kpi"><div class="label">PO Bridge</div><div class="value">${statusBadge(mComponents.pocket_option_bridge?.status || '--')}</div><div class="sub">port 8765</div></div>
    <div class="kpi"><div class="label">Edge</div><div class="value">${statusBadge(mComponents.edge_browser?.status || '--')}</div><div class="sub">bridge + extension</div></div>
    <div class="kpi"><div class="label">IBKR</div><div class="value">${statusBadge(mComponents.ibkr_gateway?.status || '--')}</div><div class="sub">gateway 4002</div></div>
  `;
  document.getElementById('system-note').innerHTML = noteBlock('System separates operating context, maintenance controls, service health, pipeline checks, and policy. Maintenance status is not the same thing as trading readiness.', 'info');

  // Service health — services is {name: {healthy, latency_ms?, error?}}
  if (health?.services) {
    const services = health.services;
    document.getElementById('system-health').innerHTML = Object.entries(services).map(([sname, svc]) => {
      const isHealthy = svc.healthy;
      const latency = svc.latency_ms != null ? `${svc.latency_ms}ms` : '';
      const error = svc.error || '';
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <span style="font-weight:600">${esc(sname)}</span>
          ${latency ? `<span class="text-xs text-muted" style="margin-left:8px">${latency}</span>` : ''}
          ${error ? `<div class="text-xs text-red">${esc(error)}</div>` : ''}
        </div>
        ${isHealthy ? badge('healthy','green') : badge('unhealthy','red')}
      </div>`;
    }).join('');
  } else {
    document.getElementById('system-health').innerHTML = '<div class="err-msg">Failed to load health</div>';
  }

  // Pipeline — pipeline_verification.tests[], http_endpoint_tests
  if (pipeline) {
    const pv = pipeline.pipeline_verification || {};
    const http = pipeline.http_endpoint_tests || {};
    document.getElementById('system-pipeline').innerHTML = kvBlock([
      ['Test Files', pipeline.test_files ?? '--'],
      ['Total Tests', pipeline.total_tests ?? '--'],
      ['Failures', pipeline.failures ?? 0, (pipeline.failures||0) > 0 ? 'text-red' : 'text-green'],
      ['Pipeline Checks', `${pv.count??0} (${pv.all_passing ? 'all passing' : 'issues'})`],
      ['HTTP Endpoint Tests', `${http.count??0} (${http.all_passing ? 'all passing' : 'issues'})`],
    ]);
    // Pipeline verification tests detail
    if (pv.tests?.length) {
      document.getElementById('system-pipeline').innerHTML += '<div class="mt-12 scroll-y">' + tableWrap('<table><thead><tr><th>Test</th><th>Description</th><th>Status</th></tr></thead><tbody>' +
        pv.tests.map(t => `<tr>
          <td class="mono text-xs">${esc(t.id)}</td>
          <td class="text-sm">${esc(t.desc)}</td>
          <td>${t.verified ? badge('pass','green') : badge('fail','red')}</td>
        </tr>`).join('') + '</tbody></table>', 760) + '</div>';
    }
  } else {
    document.getElementById('system-pipeline').innerHTML = '<div class="err-msg">Failed to load pipeline</div>';
  }

  // Trading policy — global_rules + platform_rules
  if (policy) {
    const gr = policy.global_rules || {};
    document.getElementById('system-policy').innerHTML = kvBlock([
      ['Paper Only', gr.paper_only ? 'Yes' : 'No', gr.paper_only ? 'text-green' : 'text-red'],
      ['Live Trading Forbidden', gr.live_trading_forbidden ? 'Yes' : 'No', gr.live_trading_forbidden ? 'text-green' : 'text-red'],
      ['Capital Mutation Forbidden', gr.capital_mutation_forbidden ? 'Yes' : 'No', gr.capital_mutation_forbidden ? 'text-green' : 'text-red'],
      ['Credentials Mutation Forbidden', gr.credentials_mutation_forbidden ? 'Yes' : 'No', gr.credentials_mutation_forbidden ? 'text-green' : 'text-red'],
    ]);
    // Platform rules
    const pr = policy.platform_rules || {};
    if (Object.keys(pr).length) {
      document.getElementById('system-policy').innerHTML += '<div class="mt-12">' + tableWrap('<table><thead><tr><th>Platform</th><th>Paper</th><th>Live</th><th>Mode</th></tr></thead><tbody>' +
        Object.entries(pr).map(([pname, rules]) => `<tr>
          <td style="font-weight:600">${esc(pname)}</td>
          <td>${rules.paper_allowed ? badge('yes','green') : badge('no','red')}</td>
          <td>${rules.live_allowed ? badge('yes','red') : badge('no','green')}</td>
          <td class="mono text-xs">${esc(rules.mode)}</td>
        </tr>`).join('') + '</tbody></table>', 720) + '</div>';
    }
  } else {
    document.getElementById('system-policy').innerHTML = '<div class="err-msg">Failed to load policy</div>';
  }
}

/* ─────────────────────────────────────────────
   LEARNING & ADAPTATION PANEL
   API: /brain/strategy-engine/adaptation-state → {items:[...], adapted_count, total_strategies}
   API: /brain/strategy-engine/session-performance → {mode, sessions:{name:{resolved,wins,losses,win_rate,net_pnl}}, windows:{...}}
   API: /brain/strategy-engine/post-trade-analysis → {summary, by_setup_variant, by_duration, by_payout}
   API: /brain/strategy-engine/execution-audit → {total, states:{...}, verification_stats:{...}}
   API: /brain/ops/adn-quality → {modules:[{module,score,issues},...], weighted_score}
   API: /brain/ops/ethics → {rules:[{id,name,status,detail},...], all_passing}
───────────────────────────────────────────── */
let _chartSessionWR = null;
let _chartConfDist = null;

async function refreshLearning() {
  const [adaptState, sessionPerf, postTrade, execAudit, adnQuality, ethics, learningStatus] = await Promise.all([
    api('/brain/strategy-engine/adaptation-state'),
    api('/brain/strategy-engine/session-performance'),
    api('/brain/strategy-engine/post-trade-analysis'),
    api('/brain/strategy-engine/execution-audit'),
    api('/brain/ops/adn-quality'),
    api('/brain/ops/ethics'),
    api('/brain/learning/status'),
  ]);

  // ── KPIs ──
  const adaptedCount = safe(()=>adaptState.adapted_count, 0);
  const totalStrats = safe(()=>adaptState.total_strategies, 0);
  const sessionMode = safe(()=>sessionPerf.mode, '--');
  const sessionCount = safe(()=>sessionPerf.session_count, 0);
  const totalResolved = adaptState?.items ? adaptState.items.reduce((s,i)=>s+(i.resolved||0),0) : 0;
  const ethicsOk = safe(()=>ethics.all_passing, false);
  const adnScore = safe(()=>adnQuality.weighted_score);
  const auditTotal = safe(()=>execAudit.total, 0);
  const postTradeTotal = safe(()=>postTrade.summary?.total_trades, 0);
  const verificationStats = execAudit?.verification_stats || {};

  renderLearningDecisionStrip('learning-decision-strip', adaptState, sessionPerf, postTrade, execAudit, adnQuality, ethics);
  document.getElementById('learning-kpis').innerHTML = `
    <div class="kpi"><div class="label">Adapted Strategies</div><div class="value ${adaptedCount>0?'ok':'accent'}">${adaptedCount}/${totalStrats}</div><div class="sub">min 10 resolved to adapt</div></div>
    <div class="kpi"><div class="label">Session Mode</div><div class="value">${statusBadge(sessionMode)}</div><div class="sub">${sessionCount} sessions with data</div></div>
    <div class="kpi"><div class="label">Total Resolved (all)</div><div class="value accent">${totalResolved}</div></div>
    <div class="kpi"><div class="label">Execution Audit</div><div class="value accent">${auditTotal}</div><div class="sub">trades audited</div></div>
    <div class="kpi"><div class="label">ADN Quality</div><div class="value ${(adnScore||0)>=0.7?'ok':(adnScore||0)>=0.4?'warn':'err'}">${n(adnScore,2)}</div></div>
    <div class="kpi"><div class="label">Ethics Kernel</div><div class="value ${ethicsOk?'ok':'err'}">${ethicsOk?'All Pass':'Issues'}</div></div>
  `;
  document.getElementById('learning-note').innerHTML = noteBlock(`Learning distinguishes exploration evidence, adaptation coverage, and audit quality. Verified match ${verificationStats.verified_match ?? 0}/${auditTotal || 0} is diagnostic integrity, not trading edge.`, 'info');
  document.getElementById('learning-session-mode').textContent = sessionMode;

  // ── Session Performance ──
  if (sessionPerf?.sessions) {
    const rows = normalizeSessionRows(sessionPerf).map(row => {
      if (row.empty) {
        return `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
          <div>
            <span style="font-weight:600">${esc(row.label)}</span>
            <span class="text-xs text-muted" style="margin-left:8px">${esc(row.quality)}</span>
          </div>
          <div class="text-muted text-sm">No data</div>
        </div>`;
      }
      const quality = row.quality;
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <span style="font-weight:600">${esc(row.label)}</span>
          <span class="text-xs badge-${quality==='very_high'||quality==='high'?'green':quality==='medium'?'amber':'red'}" style="margin-left:8px;padding:1px 6px;border-radius:10px">${esc(quality)}</span>
        </div>
        <div style="display:flex;gap:16px;align-items:center">
          <span class="mono text-sm">${row.wins}W / ${row.losses}L</span>
          <span class="mono ${(row.winRate||0)>=0.5?'text-green':'text-red'}">${pct(row.winRate)}</span>
          <span class="mono ${(row.netPnl||0)>=0?'text-green':'text-red'}">${n(row.netPnl,2)}</span>
        </div>
      </div>`;
    });
    document.getElementById('learning-session-perf').innerHTML = rows.join('') || '<div class="loading">No session data</div>';
  } else {
    document.getElementById('learning-session-perf').innerHTML = '<div class="loading">No session performance data</div>';
  }

  // ── Adaptation Summary ──
  if (adaptState) {
    const adaptItems = normalizeAdaptationItems(adaptState);
    const adapted = adaptItems.filter(i=>i.adapted_signal_thresholds);
    const unadapted = adaptItems.filter(i=>!i.adapted_signal_thresholds);
    const topAdapted = adapted.slice(0,5);
    let html = kvBlock([
      ['Total Strategies', adaptState.total_strategies],
      ['Adapted (thresholds)', adaptedCount],
      ['Unadapted', unadapted.length],
    ]);
    if (topAdapted.length) {
      html += '<div class="mt-8 text-xs text-muted">Top adapted strategies:</div>';
      topAdapted.forEach(i => {
        html += `<div style="padding:4px 0;border-bottom:1px solid var(--border)">
          <span class="mono text-sm">${esc(i.strategy_id)}</span>
          <span class="text-xs text-muted" style="margin-left:8px">shift ${pctRaw(i.signal_shift_pct ? i.signal_shift_pct*100 : 0)}</span>
          <span class="text-xs text-muted" style="margin-left:8px">WR ${pct(i.win_rate)}</span>
          <span class="mono text-xs" style="margin-left:8px">${i.resolved||0} resolved</span>
        </div>`;
      });
    }
    document.getElementById('learning-adaptation-summary').innerHTML = html;
  } else {
    document.getElementById('learning-adaptation-summary').innerHTML = '<div class="loading">No adaptation data</div>';
  }

  // ── Signal Threshold Adaptation Table ──
  if (normalizeAdaptationItems(adaptState).length) {
    const items = normalizeAdaptationItems(adaptState).filter(i => i.venue === 'pocket_option' || i.resolved > 0).slice(0, 40);
    document.getElementById('learning-thresholds').innerHTML = tableWrap(`<table><thead><tr>
      <th>Strategy</th><th>Venue</th><th>Resolved</th><th>WR</th><th>Conf Threshold</th><th>Signal Shift</th><th>Perf Factor</th><th>Adapted</th>
    </tr></thead><tbody>` +
      items.map(i => {
        const hasAdapt = !!i.adapted_signal_thresholds;
        return `<tr>
          <td class="mono text-xs" style="font-weight:600">${esc(i.strategy_id)}</td>
          <td>${esc(i.venue||'--')}</td>
          <td class="mono">${i.resolved||0}</td>
          <td class="mono ${(i.win_rate||0)>=0.5?'text-green':'text-red'}">${pct(i.win_rate)}</td>
          <td class="mono">${n(i.confidence_threshold,2)}</td>
          <td class="mono ${hasAdapt?'text-accent':''}">${i.signal_shift_pct!=null ? pctRaw(i.signal_shift_pct*100) : '--'}</td>
          <td class="mono">${i.signal_perf_factor!=null ? n(i.signal_perf_factor,3) : '--'}</td>
          <td>${hasAdapt ? badge('yes','green') : badge('no','amber')}</td>
        </tr>`;
      }).join('') + '</tbody></table>', 920);
  } else {
    document.getElementById('learning-thresholds').innerHTML = '<div class="loading">No threshold data</div>';
  }

  // ── Post-Trade Analysis ──
  if (postTrade?.summary) {
    const s = postTrade.summary;
    const byVariant = postTrade.by_setup_variant || {};
    const byDuration = postTrade.by_duration || {};
    const byPayout = postTrade.by_payout || {};
    let html = kvBlock([
      ['Total Trades Analyzed', s.total_trades ?? '--'],
      ['Overall Win Rate', pct(s.win_rate)],
      ['Overall Expectancy', n(s.expectancy, 4), (s.expectancy||0)>0?'text-green':'text-red'],
    ]);
    html += '<div class="mt-12 text-xs text-muted mb-8">By Setup Variant:</div>';
    Object.entries(byVariant).forEach(([k, v]) => {
      html += `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
        <span class="text-sm">${esc(k)}</span>
        <span class="mono text-sm">${v.count||0} trades | WR ${pct(v.win_rate)} | exp ${n(v.expectancy,4)}</span>
      </div>`;
    });
    html += '<div class="mt-12 text-xs text-muted mb-8">By Duration:</div>';
    Object.entries(byDuration).forEach(([k, v]) => {
      html += `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
        <span class="text-sm">${esc(k)}</span>
        <span class="mono text-sm">${v.count||0} trades | WR ${pct(v.win_rate)}</span>
      </div>`;
    });
    html += '<div class="mt-12 text-xs text-muted mb-8">By Payout:</div>';
    Object.entries(byPayout).forEach(([k, v]) => {
      html += `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
        <span class="text-sm">${esc(k)}</span>
        <span class="mono text-sm">${v.count||0} trades | WR ${pct(v.win_rate)}</span>
      </div>`;
    });
    document.getElementById('learning-post-trade').innerHTML = html;
  } else {
    document.getElementById('learning-post-trade').innerHTML = '<div class="loading">No post-trade data</div>';
  }

  // ── Execution Audit ──
  if (execAudit) {
    const states = execAudit.states || {};
    const vStats = execAudit.verification_stats || {};
    document.getElementById('learning-execution-audit').innerHTML = kvBlock([
      ['Total Entries', execAudit.total ?? '--'],
      ['With Gate Audit', vStats.gate_audit_present ?? 0],
      ['With Decision Context', vStats.decision_context_present ?? 0],
      ['Verified Match', vStats.verified_match ?? 0],
      ['Fase5 Coverage', pct(vStats.fase5_coverage)],
    ]) + '<div class="mt-12 text-xs text-muted mb-8">By Execution State:</div>' +
      Object.entries(states).map(([k, v]) =>
        `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
          <span class="text-sm">${esc(k)}</span>
          <span class="mono text-sm">${v}</span>
        </div>`
      ).join('');
  } else {
    document.getElementById('learning-execution-audit').innerHTML = '<div class="loading">No execution audit data</div>';
  }

  // ── ADN Quality ──
  if (adnQuality?.modules?.length) {
    const modules = adnQuality.modules.slice().sort((a,b)=>(a.score||0)-(b.score||0));
    document.getElementById('learning-adn-quality').innerHTML = tableWrap(`<table><thead><tr>
      <th>Module</th><th>Score</th><th>Issues</th>
    </tr></thead><tbody>` +
      modules.slice(0,20).map(m => `<tr>
        <td class="mono text-xs">${esc(m.module||m.name||'--')}</td>
        <td class="mono ${(m.score||0)>=0.8?'text-green':(m.score||0)>=0.5?'text-amber':'text-red'}">${n(m.score,2)}</td>
        <td class="text-xs text-muted">${esc((m.issues||[]).slice(0,3).join(', ') || 'none')}</td>
      </tr>`).join('') + '</tbody></table>', 760) +
      `<div style="padding:8px 12px" class="text-xs text-muted">Weighted avg: <span class="mono">${n(adnQuality.weighted_score,2)}</span> | ${adnQuality.modules.length} modules scanned</div>`;
  } else {
    document.getElementById('learning-adn-quality').innerHTML = '<div class="loading">No ADN quality data</div>';
  }

  // ── Ethics Kernel ──
  if (ethics?.rules?.length) {
    document.getElementById('learning-ethics').innerHTML = ethics.rules.map(r =>
      `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <span class="mono text-sm" style="font-weight:600">${esc(r.id)}</span>
          <span class="text-sm" style="margin-left:8px">${esc(r.name)}</span>
          <div class="text-xs text-muted">${esc(r.detail||'')}</div>
        </div>
        ${r.status==='passing'||r.status==='pass' ? badge('pass','green') : badge(r.status||'fail','red')}
      </div>`
    ).join('') +
    `<div class="mt-8 text-sm" style="padding:4px 0">${ethics.all_passing ? '<span class="text-green">All rules passing</span>' : '<span class="text-red">Some rules failing</span>'}</div>`;
  } else {
    document.getElementById('learning-ethics').innerHTML = '<div class="loading">No ethics data</div>';
  }

  renderExternalLearningMonitor(learningStatus);

  // ── Chart: Win Rate by Session Window ──
  renderSessionWRChart(sessionPerf);

  // ── Chart: Confidence Threshold Distribution ──
  renderConfidenceChart(adaptState);
}

function renderExternalLearningMonitor(learningStatus) {
  const overviewEl = document.getElementById('learning-external-overview');
  const sourcesEl = document.getElementById('learning-external-sources');
  const hypothesesEl = document.getElementById('learning-external-hypotheses');
  const proposalsEl = document.getElementById('learning-external-proposals');
  const evaluationEl = document.getElementById('learning-external-evaluation');
  const curvesEl = document.getElementById('learning-external-curves');
  const eventsEl = document.getElementById('learning-external-events');
  if (!overviewEl || !sourcesEl || !hypothesesEl || !proposalsEl || !evaluationEl || !curvesEl || !eventsEl) return;
  if (!learningStatus) {
    overviewEl.innerHTML = errorState('Learning pipeline unavailable', 'No se pudo cargar /brain/learning/status.');
    sourcesEl.innerHTML = '<div class="loading">No source data</div>';
    hypothesesEl.innerHTML = '<div class="loading">No hypothesis data</div>';
    proposalsEl.innerHTML = '<div class="loading">No proposal data</div>';
    evaluationEl.innerHTML = '<div class="loading">No evaluation data</div>';
    curvesEl.innerHTML = '<div class="loading">No curve data</div>';
    eventsEl.innerHTML = '<div class="loading">No events</div>';
    return;
  }
  const panels = learningStatus.panels || {};
  const ingestion = panels.ingestion || {};
  const registry = panels.source_registry || {};
  const sources = panels.sources || [];
  const failures = panels.source_failures || [];
  const semantic = panels.semantic_dedup || [];
  const proposals = panels.proposals || [];
  const sandbox = panels.sandbox || {};
  const evaluation = panels.evaluation || {};
  const events = panels.recent_events || [];
  const candidateCount = proposals.filter(p => p.current_state === 'candidate_promote').length;
  const activation = learningStatus.activation || {};
  const curve = panels.learning_curve || {};
  const curvePoints = curve.points || [];
  const latestPoint = curvePoints.length ? curvePoints[curvePoints.length - 1] : null;
  const capabilityCurves = curve.capability_curves || {};

  overviewEl.innerHTML = kvBlock([
    ['Milestone', esc(learningStatus.milestone)],
    ['Catalog', `${ingestion.active_sources ?? 0}/${ingestion.catalog_size ?? 0} active`],
    ['Ingested / Failed', `${ingestion.ingested_sources ?? 0} / ${ingestion.failed_sources ?? 0}`],
    ['Patterns', (panels.patterns || []).length],
    ['Hypotheses', (panels.hypotheses || []).length],
    ['Semantic Clusters', semantic.length],
    ['Proposals', proposals.length],
    ['Candidates', candidateCount, candidateCount ? 'text-green' : ''],
    ['Learning Active', activation.externally_informed_learning_active ? 'Yes' : 'No', activation.externally_informed_learning_active ? 'text-green' : 'text-amber'],
    ['Activation Stage', esc(activation.activation_stage || '--')],
    ['Latest Refresh', ago(ingestion.last_run_utc)],
    ['Mode', esc(ingestion.mode || '--')],
  ]) + noteBlock(`Curated external learning is now observable: source -> pattern -> hypothesis -> ranked proposal -> sandbox -> evaluation. Trigger: ${activation.trigger_condition || '--'}`, 'info');

  sourcesEl.innerHTML = tableWrap(`<table><thead><tr><th>Source</th><th>Category</th><th>Cur.</th><th>Risk</th><th>Action</th></tr></thead><tbody>` +
    sources.slice(0, 18).map(src => `<tr>
      <td><div class="mono text-xs">${esc(`${src.owner}/${src.repo}`)}</div><div class="text-xs text-muted">${esc(src.rationale || '')}</div><div class="text-xs text-muted">tree ${esc(safe(() => src.repo_signals.tree_entries, '--'))} | priority ${esc(safe(() => src.repo_signals.priority_files_scanned, '--'))}</div></td>
      <td>${statusBadge(src.category || '--')}</td>
      <td class="mono">${n(src.curation_score, 1)}</td>
      <td class="mono ${(src.risk_score || 0) <= 3 ? 'text-green' : (src.risk_score || 0) <= 6 ? 'text-amber' : 'text-red'}">${n(src.risk_score, 1)}</td>
      <td>${statusBadge(src.recommended_action || '--')}</td>
    </tr>`).join('') + '</tbody></table>', 860);
  if (failures.length) {
    sourcesEl.innerHTML += `<div style="padding:10px 12px" class="text-xs text-red">Failures: ${failures.map(row => `${row.owner}/${row.repo}: ${row.error}`).join(' | ')}</div>`;
  }

  hypothesesEl.innerHTML = tableWrap(`<table><thead><tr><th>Capability</th><th>Semantic Key</th><th>Evidence</th></tr></thead><tbody>` +
    semantic.slice(0, 12).map(row => `<tr>
      <td>${esc(row.target_capability || '--')}</td>
      <td class="mono text-xs">${esc(row.semantic_key || '--')}</td>
      <td class="text-xs text-muted">${esc((row.evidence_refs || []).slice(0, 2).map(ref => ref.source_file || ref.reason || '--').join(' | ') || '--')}</td>
    </tr>`).join('') + '</tbody></table>', 860) +
    `<div style="padding:10px 12px" class="text-xs text-muted">Registry size: ${(registry.sources || []).length}. Active categories: ${Object.keys(ingestion.categories || {}).join(', ') || 'none'}.</div>`;

  proposalsEl.innerHTML = tableWrap(`<table><thead><tr><th>ID</th><th>Capability</th><th>State</th><th>Priority</th><th>Evidence</th></tr></thead><tbody>` +
    proposals.slice(0, 12).map(p => `<tr>
      <td class="mono text-xs">${esc(p.proposal_id)}</td>
      <td>${esc(p.target_capability || '--')}</td>
      <td>${statusBadge(p.current_state || '--')}</td>
      <td class="mono ${(p.proposal_priority_score || 0) >= 0.45 ? 'text-green' : (p.proposal_priority_score || 0) >= 0.3 ? 'text-amber' : 'text-red'}">${n(p.proposal_priority_score, 4)}</td>
      <td class="mono">${n(p.evidence_strength_score, 2)}</td>
    </tr>`).join('') + '</tbody></table>', 860);

  evaluationEl.innerHTML = kvBlock([
    ['Sandbox Runs', sandbox.total_runs ?? 0],
    ['Evaluation Runs', evaluation.total_evaluations ?? 0],
    ['Passed Candidate', safe(() => evaluation.by_verdict.evaluation_passed_candidate, 0)],
    ['Needs More Tests', safe(() => evaluation.by_verdict.needs_more_tests, 0)],
    ['Evaluation Failed', safe(() => evaluation.by_verdict.evaluation_failed, 0)],
    ['Evidence-backed Caps', (activation.evidence_backed_capabilities || []).length],
    ['Latest Proposal', safe(() => evaluation.latest[0].proposal_id, '--')],
    ['Latest Verdict', safe(() => evaluation.latest[0].verdict, '--')],
    ['Latest Evaluated', ago(safe(() => evaluation.latest[0].evaluated_at_utc, null))],
  ]) + noteBlock(`candidate_promote is only a next-gate marker. Curve points: ${curvePoints.length}. Latest stage: ${esc(safe(() => latestPoint.activation_stage, '--'))}.`, 'warn');

  const curveRows = Object.entries(capabilityCurves).map(([cap, points]) => {
    const recent = (points || []).slice(-5);
    const latest = recent.length ? recent[recent.length - 1] : null;
    const scores = recent.map(p => n(p.score, 2)).join(' → ');
    const stages = Array.from(new Set(recent.map(p => p.activation_stage).filter(Boolean))).join(' → ') || '--';
    return `<tr>
      <td>${esc(cap)}</td>
      <td class="mono">${scores || '--'}</td>
      <td>${statusBadge(latest?.status || '--')}</td>
      <td class="text-xs text-muted">${esc(stages)}</td>
    </tr>`;
  }).join('');
  curvesEl.innerHTML = tableWrap(
    `<table><thead><tr><th>Capability</th><th>Recent Scores</th><th>Latest Status</th><th>Stages</th></tr></thead><tbody>${
      curveRows || '<tr><td colspan="4" class="text-muted">No capability curve data</td></tr>'
    }</tbody></table>`,
    860
  ) + `<div style="padding:10px 12px" class="text-xs text-muted">Latest point: ${esc(latestPoint?.activation_stage || '--')} | sources ${esc(latestPoint?.sources ?? '--')} | patterns ${esc(latestPoint?.patterns ?? '--')} | proposals ${esc(latestPoint?.proposals ?? '--')} | evaluations ${esc(latestPoint?.evaluations ?? '--')}</div>`;

  eventsEl.innerHTML = tableWrap(`<table><thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead><tbody>` +
    events.slice(0, 20).map(row => `<tr>
      <td class="nowrap text-muted text-xs">${ago(row.ts_utc)}</td>
      <td>${statusBadge(row.event || '--')}</td>
      <td class="text-xs text-muted">${esc(row.proposal_id || row.source_id || row.reason || row.url || row.to_state || '--')}</td>
    </tr>`).join('') + '</tbody></table>', 860);
}

async function refreshLearningPipelineNow() {
  const overviewEl = document.getElementById('learning-external-overview');
  if (overviewEl) overviewEl.innerHTML = infoState('Refreshing curated catalog', 'Launching full external learning refresh...');
  try {
    await apiPost('/brain/learning/refresh', {
      actor: 'dashboard',
      reason: 'dashboard_manual_refresh',
      force_refresh: true,
      max_sources: null,
    });
    await refreshLearning();
  } catch (error) {
    if (overviewEl) overviewEl.innerHTML = errorState('Learning refresh failed', error.message || String(error));
  }
}

function renderAutonomyDecisionStrip(targetId, autonomy, accumulator, ibkr, reports) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!autonomy && !accumulator && !ibkr) {
    renderTargetHtml(targetId, emptyState('No autonomy decision frame', 'Autonomy summary could not be built from canonical runtime payloads.'));
    return;
  }
  const accStatus = accumulator?.status || accumulator || {};
  const reportsRows = normalizeReports(reports);
  target.innerHTML = [
    executiveCard(
      'Loop Posture',
      safe(()=>autonomy.running, false) ? 'running' : 'stopped',
      `${safe(()=>autonomy.active_tasks, 0)} active tasks | ${safe(()=>autonomy.reports_count, 0)} reports`,
      safe(()=>autonomy.running, false) ? 'ok' : 'err'
    ),
    executiveCard(
      'Sample Accumulation',
      safe(()=>accStatus.running || accumulator?.running, false) ? 'active' : 'idle',
      `${safe(()=>accStatus.session_trades_count, 0)} session trades | ${safe(()=>accStatus.active_platforms, 0)} active platforms`,
      safe(()=>accStatus.running || accumulator?.running, false) ? 'ok' : 'warn'
    ),
    executiveCard(
      'IBKR Ingest',
      safe(()=>ibkr.running, false) ? 'running' : 'stopped',
      `connected ${safe(()=>ibkr.last_connected, false) ? 'yes' : 'no'} | symbols ${safe(()=>ibkr.last_symbol_count, 0)}`,
      safe(()=>ibkr.running, false) && safe(()=>ibkr.last_connected, false) ? 'ok' : 'warn'
    ),
    executiveCard(
      'Recent Diagnostics',
      `${reportsRows.length} reports`,
      reportsRows.length ? `latest ${esc(reportsRows[0]?.type || '--')} | ${ago(reportsRows[0]?.timestamp)}` : 'no recent reports',
      reportsRows.length ? 'info' : 'warn'
    ),
  ].join('');
}

function renderRoadmapDecisionStrip(targetId, governance, devStatus, postBL) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!governance && !devStatus && !postBL) {
    renderTargetHtml(targetId, emptyState('No roadmap decision frame', 'Roadmap summary could not be built from canonical governance payloads.'));
    return;
  }
  const canonical = governance?.canonical || {};
  const promotion = governance?.promotion || {};
  const acceptance = promotion.acceptance || {};
  const summary = postBL?.summary || {};
  target.innerHTML = [
    executiveCard(
      'Canonical Phase',
      esc(canonical.current_phase || '--'),
      `${esc(canonical.active_title || '--')} | ${esc(canonical.current_stage || '--')}`,
      acceptance.accepted ? 'ok' : 'warn'
    ),
    executiveCard(
      'Development Execution',
      esc(devStatus?.work_status || '--'),
      `${esc(devStatus?.phase_id || '--')} | blockers ${esc(devStatus?.blocker_count ?? 0)}`,
      (devStatus?.blocker_count || 0) === 0 ? 'ok' : 'warn'
    ),
    executiveCard(
      'Acceptance Gate',
      acceptance.accepted ? 'accepted' : 'pending',
      `${esc(devStatus?.promotion_state || '--')} | evaluator ${esc(devStatus?.evaluator_status || '--')}`,
      acceptance.accepted ? 'ok' : 'warn'
    ),
    executiveCard(
      'Post-BL Continuation',
      esc(postBL?.work_status || '--'),
      `${summary.done ?? 0} done | ${summary.active ?? 0} active | ${summary.queued ?? 0} queued`,
      postBL?.enabled ? 'info' : 'warn'
    ),
  ].join('');
}

function renderSystemDecisionStrip(targetId, health, pipeline, policy, maintenance, operating) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!health && !pipeline && !policy && !maintenance) {
    renderTargetHtml(targetId, emptyState('No system decision frame', 'System summary could not be built from canonical runtime data.'));
    return;
  }
  const overall = safe(()=>health.overall_status, 'unknown');
  const summary = health?.summary || {};
  const failures = safe(()=>pipeline.failures, 0);
  const testsTotal = safe(()=>pipeline.total_tests, 0);
  const paperOnly = safe(()=>policy.global_rules?.paper_only, null);
  const liveForbidden = safe(()=>policy.global_rules?.live_trading_forbidden, null);
  const mSummary = maintenance?.summary || {};
  const mComponents = maintenance?.components || {};
  target.innerHTML = [
    executiveCard(
      'Runtime Health',
      esc(overall),
      `${summary.healthy ?? 0}/${summary.total ?? 0} services healthy`,
      overall === 'healthy' ? 'ok' : overall === 'degraded' ? 'warn' : 'err'
    ),
    executiveCard(
      'Safety Policy',
      paperOnly === true ? 'paper_only' : paperOnly === false ? 'mixed' : 'unknown',
      `live forbidden: ${liveForbidden === true ? 'yes' : liveForbidden === false ? 'no' : '--'}`,
      paperOnly === true && liveForbidden === true ? 'ok' : 'warn'
    ),
    executiveCard(
      'Pipeline Confidence',
      testsTotal ? `${testsTotal - failures}/${testsTotal} passing` : 'no test payload',
      `${failures} failures | ${safe(()=>pipeline.ok, false) ? 'pipeline_ok' : 'pipeline_attention'}`,
      failures === 0 && safe(()=>pipeline.ok, false) ? 'ok' : 'warn'
    ),
    executiveCard(
      'Ops Dependencies',
      `${mSummary.healthy_or_running ?? '--'}/${mSummary.components ?? '--'} healthy`,
      `bridge ${esc(mComponents.pocket_option_bridge?.status || '--')} | edge ${esc(mComponents.edge_browser?.status || '--')} | ibkr ${esc(mComponents.ibkr_gateway?.status || '--')}`,
      (mSummary.degraded_or_down || 0) === 0 ? 'ok' : 'warn'
    ),
  ].join('');
}

function renderLearningDecisionStrip(targetId, adaptState, sessionPerf, postTrade, execAudit, adnQuality, ethics) {
  const target = document.getElementById(targetId);
  if (!target) return;
  if (!adaptState && !sessionPerf && !postTrade && !execAudit) {
    renderTargetHtml(targetId, emptyState('No learning decision frame', 'Learning summary could not be built from canonical analytics payloads.'));
    return;
  }
  const adaptedCount = safe(()=>adaptState.adapted_count, 0);
  const totalStrategies = safe(()=>adaptState.total_strategies, 0);
  const totalResolved = adaptState?.items ? adaptState.items.reduce((s, i) => s + (i.resolved || 0), 0) : 0;
  const sessionMode = safe(()=>sessionPerf.mode, '--');
  const sessionCount = safe(()=>sessionPerf.session_count, 0);
  const postSummary = postTrade?.summary || {};
  const verificationStats = execAudit?.verification_stats || {};
  const verifiedMatch = verificationStats.verified_match ?? 0;
  const auditTotal = safe(()=>execAudit.total, 0);
  const adnScore = safe(()=>adnQuality.weighted_score, null);
  const ethicsOk = safe(()=>ethics.all_passing, null);
  target.innerHTML = [
    executiveCard(
      'Learning Posture',
      esc(sessionMode),
      `${sessionCount} sessions with data | ${totalResolved} resolved entries`,
      totalResolved >= 10 ? 'ok' : 'warn'
    ),
    executiveCard(
      'Adaptation Coverage',
      `${adaptedCount}/${totalStrategies}`,
      adaptedCount ? 'threshold adaptation active' : 'no strategy adapted yet',
      adaptedCount ? 'ok' : 'warn'
    ),
    executiveCard(
      'Post-Trade Evidence',
      `${postSummary.total_trades ?? 0} analyzed`,
      `WR ${pct(postSummary.win_rate)} | exp ${n(postSummary.expectancy, 4)}`,
      (postSummary.total_trades || 0) >= 5 ? 'ok' : 'warn'
    ),
    executiveCard(
      'Audit Integrity',
      `${verifiedMatch}/${auditTotal || 0} verified`,
      `ADN ${adnScore == null ? '--' : n(adnScore, 2)} | ethics ${ethicsOk === true ? 'pass' : ethicsOk === false ? 'issues' : '--'}`,
      ethicsOk === true && (adnScore == null || adnScore >= 0.7) ? 'ok' : 'warn'
    ),
  ].join('');
}

/* ─────────────────────────────────────────────
   AUTO-SURGEON PANEL
   API: /brain/auto-surgeon/status → {last_cycle_utc, last_status, last_issue, last_change_id, daily_count, daily_limit, total_entries, recent_entries:[...], codegen_metrics:{}}
   API: /brain/auto-surgeon/diagnostics → {open_issues, issues:[{issue_id,title,severity,category,affected_file,attempts,status,...}], last_scan_utc, history_count, recent_history:[...]}
───────────────────────────────────────────── */
async function refreshSurgeon() {
  const [surgeon, diagnostics] = await Promise.all([
    api('/brain/auto-surgeon/status'),
    api('/brain/auto-surgeon/diagnostics'),
  ]);

  // KPIs
  const dailyCount = safe(()=>surgeon.daily_count, 0);
  const dailyLimit = safe(()=>surgeon.daily_limit, 10);
  const totalPatches = safe(()=>surgeon.total_entries, 0);
  const lastStatus = safe(()=>surgeon.last_status, '--');
  const openIssues = safe(()=>diagnostics.open_issues, 0);
  const historyCount = safe(()=>diagnostics.history_count, 0);
  const lastScan = safe(()=>diagnostics.last_scan_utc, null);
  const codegenMetrics = surgeon?.codegen_metrics || {};

  document.getElementById('surgeon-kpis').innerHTML = `
    <div class="kpi"><div class="label">Daily Patches</div><div class="value ${dailyCount>=dailyLimit?'err':'ok'}">${dailyCount} / ${dailyLimit}</div><div class="sub">today's limit</div></div>
    <div class="kpi"><div class="label">Total Patches</div><div class="value accent">${totalPatches}</div><div class="sub">all time</div></div>
    <div class="kpi"><div class="label">Last Cycle</div><div class="value">${statusBadge(lastStatus)}</div><div class="sub">${ago(safe(()=>surgeon.last_cycle_utc))}</div></div>
    <div class="kpi"><div class="label">Open Issues</div><div class="value ${openIssues>0?'warn':'ok'}">${openIssues}</div><div class="sub">trade diagnostics</div></div>
    <div class="kpi"><div class="label">Last Scan</div><div class="value accent">${ago(lastScan)}</div></div>
    <div class="kpi"><div class="label">Issue History</div><div class="value accent">${historyCount}</div><div class="sub">total resolved/attempted</div></div>
  `;

  // Surgeon Status detail
  if (surgeon) {
    const cgm = codegenMetrics;
    const lastCodegen = surgeon.last_codegen || {};
    let statusRows = [
      ['Last Cycle', ago(surgeon.last_cycle_utc)],
      ['Last Status', lastStatus],
      ['Last Phase', esc(surgeon.last_phase || '--')],
      ['Last Issue', esc(surgeon.last_issue || 'none')],
      ['Last Change ID', esc(surgeon.last_change_id || 'none')],
      ['Daily Count', `${dailyCount} / ${dailyLimit}`],
      ['CodeGen Calls', cgm.total_requests ?? cgm.total_calls ?? '--'],
      ['CodeGen Successes', cgm.successful ?? '--'],
      ['CodeGen Fallbacks', cgm.fallbacks ?? 0],
      ['CodeGen Avg Latency', cgm.avg_latency_s != null ? n(cgm.avg_latency_s,2)+'s' : '--'],
    ];
    if (surgeon.last_error) {
      statusRows.push(['Last Error', esc(surgeon.last_error), 'text-red']);
    }
    if (lastCodegen.model_used) {
      statusRows.push(['Last Model', esc(lastCodegen.model_used)]);
      statusRows.push(['Last CodeGen Latency', lastCodegen.latency_s != null ? n(lastCodegen.latency_s,2)+'s' : '--']);
    }
    if (lastCodegen.reasoning) {
      statusRows.push(['Last Reasoning', esc(lastCodegen.reasoning)]);
    }
    document.getElementById('surgeon-status').innerHTML = kvBlock(statusRows);
  } else {
    document.getElementById('surgeon-status').innerHTML = '<div class="text-muted">Auto-surgeon has not run yet. First cycle in ~2 min after Brain V9 start.</div>';
  }

  // Diagnostics overview
  if (diagnostics) {
    const scanSummary = diagnostics.last_scan_summary || {};
    document.getElementById('surgeon-diagnostics').innerHTML = kvBlock([
      ['Open Issues', openIssues],
      ['Last Scan', ago(lastScan)],
      ['Issues Found Last Scan', scanSummary.issues_found ?? '--'],
      ['New Issues Last Scan', scanSummary.new_issues ?? '--'],
      ['Resolved Last Scan', scanSummary.resolved_issues ?? '--'],
      ['History Entries', historyCount],
    ]);
  } else {
    document.getElementById('surgeon-diagnostics').innerHTML = '<div class="text-muted">No diagnostic scans yet.</div>';
  }

  // Open Issues table
  const issues = diagnostics?.issues || [];
  if (issues.length) {
    document.getElementById('surgeon-issues').innerHTML = `<table><thead><tr>
      <th>ID</th><th>Title</th><th>Severity</th><th>File</th><th>Attempts</th><th>Status</th><th>Detected</th>
    </tr></thead><tbody>` +
      issues.map(iss => {
        const sev = iss.severity || 'low';
        const sevCls = sev==='critical'?'text-red':sev==='high'?'text-amber':sev==='medium'?'text-accent':'text-muted';
        return `<tr>
          <td class="mono text-xs">${esc(iss.issue_id)}</td>
          <td class="text-sm">${esc(iss.title)}</td>
          <td class="${sevCls}" style="font-weight:600">${esc(sev)}</td>
          <td class="mono text-xs">${esc((iss.affected_file||'').split(/[/\\]/).pop())}</td>
          <td class="mono">${iss.attempts ?? 0}</td>
          <td>${statusBadge(iss.status || 'open')}</td>
          <td class="text-muted text-xs nowrap">${ago(iss.detected_utc)}</td>
        </tr>`;
      }).join('') + '</tbody></table>';
  } else {
    document.getElementById('surgeon-issues').innerHTML = '<div class="loading">No open issues — system is healthy</div>';
  }

  // Recent Patches table
  const patches = surgeon?.recent_entries || [];
  if (patches.length) {
    document.getElementById('surgeon-patches').innerHTML = `<table><thead><tr>
      <th>Time</th><th>Issue</th><th>Title</th><th>Model</th><th>Status</th><th>Duration</th>
    </tr></thead><tbody>` +
      patches.slice().reverse().map(p => `<tr>
        <td class="text-muted text-xs nowrap">${ago(p.timestamp)}</td>
        <td class="mono text-xs">${esc(p.issue_id)}</td>
        <td class="text-sm">${esc(p.title)}</td>
        <td class="mono text-xs">${esc(p.model_used || '--')}</td>
        <td>${statusBadge(p.status || '--')}</td>
        <td class="mono text-xs">${p.duration_s != null ? n(p.duration_s,1)+'s' : '--'}</td>
      </tr>`).join('') + '</tbody></table>';
  } else {
    document.getElementById('surgeon-patches').innerHTML = '<div class="loading">No patches generated yet</div>';
  }

  // Recent history
  const history = diagnostics?.recent_history || [];
  if (history.length) {
    document.getElementById('surgeon-history').innerHTML = `<table><thead><tr>
      <th>Time</th><th>Issue</th><th>Action</th><th>Detail</th>
    </tr></thead><tbody>` +
      history.slice().reverse().map(h => `<tr>
        <td class="text-muted text-xs nowrap">${ago(h.timestamp || h.resolved_utc)}</td>
        <td class="mono text-xs">${esc(h.issue_id)}</td>
        <td>${statusBadge(h.action || h.status || '--')}</td>
        <td class="text-xs text-muted">${esc(h.detail || h.reason || '')}</td>
      </tr>`).join('') + '</tbody></table>';
  } else {
    document.getElementById('surgeon-history').innerHTML = '<div class="loading">No diagnostic history</div>';
  }
}

function renderSessionWRChart(sessionPerf) {
  const canvas = document.getElementById('chart-session-wr');
  if (!canvas || typeof Chart === 'undefined') return;
  const ctx = canvas.getContext('2d');

  // Collect all windows in order, fill with session data
  const windows = sessionPerf?.windows || {};
  const sessions = sessionPerf?.sessions || {};
  const orderedKeys = ['asian_early','asian_late','london_open','london_mid','ny_open','ny_afternoon','ny_close','off_hours'];
  const labels = orderedKeys.map(k => safe(()=>windows[k]?.label, k));
  const wrData = orderedKeys.map(k => sessions[k] ? (sessions[k].win_rate||0)*100 : null);
  const resolvedData = orderedKeys.map(k => sessions[k] ? (sessions[k].resolved||0) : 0);
  const colors = orderedKeys.map(k => {
    const q = safe(()=>windows[k]?.quality,'');
    if (q==='very_high') return '#3ecf8e';
    if (q==='high') return '#4f7cff';
    if (q==='medium') return '#f5a623';
    return '#f06060';
  });

  if (_chartSessionWR) _chartSessionWR.destroy();
  _chartSessionWR = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Win Rate %',
        data: wrData,
        backgroundColor: colors.map(c=>c+'88'),
        borderColor: colors,
        borderWidth: 1,
        borderRadius: 4,
        yAxisID: 'y',
      },{
        label: 'Resolved Trades',
        data: resolvedData,
        type: 'line',
        borderColor: '#a78bfa',
        backgroundColor: '#a78bfa22',
        pointRadius: 4,
        tension: 0.3,
        yAxisID: 'y1',
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#8090b0', font: { size: 11 } } },
      },
      scales: {
        x: { ticks: { color: '#556080', font: { size: 10 } }, grid: { color: '#2a305022' } },
        y: { position: 'left', min: 0, max: 100, ticks: { color: '#8090b0', callback: v=>v+'%' }, grid: { color: '#2a305044' }, title: { display: true, text: 'Win Rate', color: '#556080' } },
        y1: { position: 'right', min: 0, ticks: { color: '#a78bfa' }, grid: { drawOnChartArea: false }, title: { display: true, text: 'Trades', color: '#a78bfa' } },
      }
    }
  });
}

function renderConfidenceChart(adaptState) {
  const canvas = document.getElementById('chart-confidence-dist');
  if (!canvas || typeof Chart === 'undefined') return;
  const ctx = canvas.getContext('2d');

  const items = normalizeAdaptationItems(adaptState).filter(i => i.venue === 'pocket_option');
  if (!items.length) {
    if (_chartConfDist) _chartConfDist.destroy();
    _chartConfDist = null;
    return;
  }

  // Bucket confidence thresholds
  const labels = items.map(i => {
    const id = i.strategy_id || '';
    return id.length > 20 ? id.slice(0,18)+'..' : id;
  });
  const confData = items.map(i => i.confidence_threshold || 0.55);
  const resolvedData = items.map(i => i.resolved || 0);
  const barColors = items.map(i => (i.resolved||0)>=10 ? '#3ecf8e88' : '#4f7cff44');
  const borderColors = items.map(i => (i.resolved||0)>=10 ? '#3ecf8e' : '#4f7cff');

  if (_chartConfDist) _chartConfDist.destroy();
  _chartConfDist = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Confidence Threshold',
        data: confData,
        backgroundColor: barColors,
        borderColor: borderColors,
        borderWidth: 1,
        borderRadius: 3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: {
        legend: { labels: { color: '#8090b0', font: { size: 11 } } },
      },
      scales: {
        x: { min: 0.35, max: 0.75, ticks: { color: '#8090b0' }, grid: { color: '#2a305044' }, title: { display: true, text: 'Threshold', color: '#556080' } },
        y: { ticks: { color: '#556080', font: { size: 9 } }, grid: { color: '#2a305022' } },
      }
    }
  });
}
