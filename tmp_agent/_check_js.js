
/* ─────────────────────────────────────────────
   API helper & globals
───────────────────────────────────────────── */
const BASE = '';
let currentPanel = 'overview';
let refreshTimer = null;

async function api(path) {
  try {
    const r = await fetch(BASE + path, {headers: {'Accept': 'application/json'}});
    if (!r.ok) throw new Error(`${r.status}`);
    return await r.json();
  } catch(e) {
    console.warn('API error:', path, e);
    return null;
  }
}

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

/* ─────────────────────────────────────────────
   Navigation
───────────────────────────────────────────── */
const panelNames = {
  overview: 'Overview',
  platforms: 'Trading Platforms',
  strategy: 'Strategy Engine',
  autonomy: 'Autonomy Loop',
  roadmap: 'Roadmap & Governance',
  meta: 'Meta Systems',
  selfimprove: 'Self-Improvement',
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

/* ─────────────────────────────────────────────
   OVERVIEW PANEL
   API: /brain/health → {overall_status, services:{brain_v9:{healthy,latency_ms},...}, summary:{total,healthy,unhealthy}}
   API: /brain/utility/v2 → {u_score, verdict, blockers[], current_phase, capital:{...}, components:{...}, sample:{...}}
   API: /trading/platforms/summary → {platforms:{pocket_option:{u_score:{current,verdict,blockers,trend_24h},metrics:{total_trades,...},accumulator:{running,...},...},...}}
   API: /brain/strategy-engine/ranking-v2 → {top_strategy:{strategy_id,...}, ranked:[{strategy_id,venue,priority_score,...},...]}
   API: /brain/autonomy/sample-accumulator → {ok, status:{running,last_trade_time,session_trades_count,...}, running}
   API: /autonomy/status → {running, active_tasks, reports_count, ibkr_ingester:{...}}
───────────────────────────────────────────── */
async function refreshOverview() {
  const [health, utility, platformSummary, ranking, accumulator, autonomy] = await Promise.all([
    api('/brain/health'),
    api('/brain/utility/v2'),
    api('/trading/platforms/summary'),
    api('/brain/strategy-engine/ranking-v2'),
    api('/brain/autonomy/sample-accumulator'),
    api('/autonomy/status'),
  ]);

  // KPIs — utility.u_score (NOT u_proxy_score)
  const u = safe(()=>utility.u_score);
  const verdict = safe(()=>utility.verdict,'--');
  const brainOk = safe(()=>health.overall_status,'unknown');
  const healthySvc = safe(()=>health.summary?.healthy, 0);
  const totalSvc = safe(()=>health.summary?.total, 0);
  // ranking-v2: top_strategy.strategy_id (NOT top_candidate)
  const topStrat = safe(()=>ranking.top_strategy?.strategy_id || ranking.ranked?.[0]?.strategy_id,'--');
  const autonomyRunning = safe(()=>autonomy.running, false);
  // sample-accumulator: status.session_trades_count (nested under status)
  const accStatus = accumulator?.status || accumulator || {};
  const sessionTrades = safe(()=>accStatus.session_trades_count, 0);

  // count total trades across platforms
  let totalTrades = 0;
  if (platformSummary?.platforms) {
    Object.values(platformSummary.platforms).forEach(p => { totalTrades += (p.metrics?.total_trades || 0); });
  }

  const phase = safe(()=>utility.current_phase, '--');

  document.getElementById('overview-kpis').innerHTML = `
    <div class="kpi"><div class="label">Utility U</div><div class="value ${uColor(u)}">${n(u,4)}</div><div class="sub">${esc(verdict)}</div></div>
    <div class="kpi"><div class="label">Brain Health</div><div class="value ${brainOk==='healthy'?'ok':brainOk==='degraded'?'warn':'err'}">${esc(brainOk)}</div><div class="sub">${healthySvc}/${totalSvc} services</div></div>
    <div class="kpi"><div class="label">Autonomy</div><div class="value ${autonomyRunning?'ok':'err'}">${autonomyRunning?'Running':'Stopped'}</div><div class="sub">${safe(()=>autonomy.active_tasks,0)} tasks</div></div>
    <div class="kpi"><div class="label">Session Trades</div><div class="value accent">${sessionTrades}</div><div class="sub">max ${safe(()=>accStatus.max_trades_per_session,'--')}</div></div>
    <div class="kpi"><div class="label">Total Trades</div><div class="value accent">${totalTrades}</div></div>
    <div class="kpi"><div class="label">Phase</div><div class="value text-accent" style="font-size:14px">${esc(phase)}</div></div>
    <div class="kpi"><div class="label">Top Strategy</div><div class="value text-accent text-sm" style="font-size:12px;word-break:break-all">${esc(topStrat)}</div></div>
    <div class="kpi"><div class="label">Blockers</div><div class="value ${utility?.blockers?.length?'err':'ok'}">${safe(()=>utility.blockers?.length,0)}</div><div class="sub">${safe(()=>utility.blockers?.slice(0,2).join(', '),'none')}</div></div>
  `;

  // Platform U scores mini display — u_score.current (NOT u_score.u_proxy_score)
  if (platformSummary?.platforms) {
    const ps = platformSummary.platforms;
    document.getElementById('overview-platform-u').innerHTML = Object.entries(ps).map(([pname, p]) => {
      const uVal = safe(()=>p.u_score?.current);
      const uVerdict = safe(()=>p.u_score?.verdict,'--');
      const trades = safe(()=>p.metrics?.total_trades, 0);
      const trend = safe(()=>p.u_score?.trend_24h,'--');
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)">
        <div>
          <div style="font-weight:600">${esc(pname)}</div>
          <div class="text-xs text-muted">${esc(uVerdict)} | ${trades} trades | trend: ${esc(trend)}</div>
        </div>
        <div class="mono ${uColor(uVal)}" style="font-size:20px;font-weight:700">${n(uVal,4)}</div>
      </div>`;
    }).join('');
  } else {
    document.getElementById('overview-platform-u').innerHTML = '<div class="loading">No platform data</div>';
  }

  // Top strategies — ranking.ranked[]
  if (ranking?.ranked?.length) {
    document.getElementById('overview-top-strategies').innerHTML = ranking.ranked.slice(0,5).map((s,i) => 
      `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <span class="text-muted">#${i+1}</span>
          <span style="font-weight:600;margin-left:8px">${esc(s.strategy_id)}</span>
          <span class="text-xs text-muted" style="margin-left:8px">${esc(s.venue||'')}</span>
        </div>
        <div class="mono text-sm">${n(s.priority_score,4)}</div>
      </div>`
    ).join('');
  } else {
    document.getElementById('overview-top-strategies').innerHTML = '<div class="loading">No ranking data</div>';
  }

  // Recent trades — /trading/platforms/{name}/trades returns array [] directly (NOT {trades:[...]})
  await refreshOverviewTrades(platformSummary);

  // Update topbar
  document.getElementById('topbar-phase').textContent = phase;
  const dot = document.getElementById('dot-brain');
  dot.className = 'health-dot ' + (brainOk==='healthy'?'ok':brainOk==='degraded'?'warn':'err');
}

async function refreshOverviewTrades(platformSummary) {
  const platforms = platformSummary?.platforms ? Object.keys(platformSummary.platforms) : ['pocket_option','ibkr','internal_paper'];
  const allTrades = [];
  await Promise.all(platforms.map(async pname => {
    const data = await api(`/trading/platforms/${pname}/trades?limit=10`);
    // API returns array directly [] or {trades:[]}
    const arr = Array.isArray(data) ? data : (data?.trades || []);
    arr.forEach(t => { t._platform = pname; allTrades.push(t); });
  }));
  allTrades.sort((a,b) => new Date(b.timestamp||b.opened_at||0) - new Date(a.timestamp||a.opened_at||0));
  const el = document.getElementById('overview-recent-trades');
  if (!allTrades.length) { el.innerHTML = '<div class="loading">No trades yet</div>'; return; }
  el.innerHTML = `<table><thead><tr><th>Time</th><th>Platform</th><th>Strategy</th><th>Symbol</th><th>Dir</th><th>Profit</th><th>Status</th></tr></thead><tbody>` +
    allTrades.slice(0,20).map(t => {
      const profit = t.profit ?? t.pnl ?? null;
      const profitCls = profit > 0 ? 'text-green' : profit < 0 ? 'text-red' : '';
      return `<tr>
        <td class="nowrap text-muted">${ago(t.timestamp||t.opened_at)}</td>
        <td>${esc(t._platform)}</td>
        <td class="mono text-xs">${esc(t.strategy_id||t.strategy||'--')}</td>
        <td>${esc(t.symbol||'--')}</td>
        <td>${esc(t.direction||'--')}</td>
        <td class="mono ${profitCls}">${profit!=null?n(profit,4):'--'}</td>
        <td>${t.resolved ? badge('resolved','green') : badge('open','amber')}</td>
      </tr>`;
    }).join('') + '</tbody></table>';
}

/* ─────────────────────────────────────────────
   PLATFORMS PANEL
   API: /trading/platforms/summary → {platforms:{...}, comparison:{...}, recommendations:[...]}
   API: /trading/platforms/compare → {ranking:[{rank,platform,u_score,win_rate,profit,trades,status},...], best_performer, worst_performer, summary:{...}}
   API: /trading/platforms/{name}/signals → {platform,total_signals,valid_signals,execution_ready,avg_confidence,problems:[{strategy,blockers}],recommendations:[]}
   API: /trading/platforms/{name}/trades → [] (array directly)
   API: /trading/platforms/{name}/u-history → [{timestamp,u_score,reason},...] (array directly)
───────────────────────────────────────────── */
let activePlatform = null;

async function refreshPlatforms() {
  const [summary, compare] = await Promise.all([
    api('/trading/platforms/summary'),
    api('/trading/platforms/compare'),
  ]);

  if (!summary?.platforms) {
    document.getElementById('platform-tabs').innerHTML = '<div class="loading">No platform data</div>';
    return;
  }

  const platforms = Object.keys(summary.platforms);
  if (!activePlatform || !platforms.includes(activePlatform)) activePlatform = platforms[0];

  // Render tabs
  document.getElementById('platform-tabs').innerHTML = platforms.map(pname =>
    `<div class="platform-tab ${pname===activePlatform?'active':''}" onclick="switchPlatform('${pname}')">${esc(pname)}</div>`
  ).join('');

  // Render views
  document.getElementById('platform-views').innerHTML = platforms.map(pname =>
    `<div class="platform-view ${pname===activePlatform?'active':''}" id="pview-${pname}"></div>`
  ).join('');

  // Fill each platform view
  for (const pname of platforms) {
    await renderPlatformView(pname, summary.platforms[pname]);
  }

  // Comparison table — /trading/platforms/compare returns {ranking:[{rank,platform,u_score,win_rate,profit,trades,status},...]}
  if (compare?.ranking?.length) {
    document.getElementById('platform-compare').innerHTML = `<table><thead><tr>
      <th>Rank</th><th>Platform</th><th>U Score</th><th>Win Rate</th><th>Profit</th><th>Trades</th><th>Status</th>
    </tr></thead><tbody>` +
      compare.ranking.map(r => `<tr>
        <td class="text-muted">${r.rank}</td>
        <td style="font-weight:600">${esc(r.platform)}</td>
        <td class="mono ${uColor(r.u_score)}">${n(r.u_score,4)}</td>
        <td class="mono">${pct(r.win_rate)}</td>
        <td class="mono ${(r.profit||0)>=0?'text-green':'text-red'}">${n(r.profit,2)}</td>
        <td class="mono">${r.trades ?? '--'}</td>
        <td>${statusBadge(r.status)}</td>
      </tr>`).join('') + '</tbody></table>';
    // Summary
    if (compare.summary) {
      document.getElementById('platform-compare').innerHTML += `<div style="padding:12px" class="text-sm text-muted">
        Best: <span class="text-green">${esc(compare.best_performer)}</span> |
        Worst: <span class="text-red">${esc(compare.worst_performer)}</span> |
        Avg U: <span class="mono">${n(compare.summary.average_u,4)}</span>
      </div>`;
    }
    // Recommendations from /trading/platforms/summary
    if (summary.recommendations?.length) {
      document.getElementById('platform-compare').innerHTML += '<div style="padding:0 12px 12px">' +
        summary.recommendations.map(r => `<div style="padding:6px 0;border-bottom:1px solid var(--border)">
          <span class="text-accent">${esc(r.platform)}</span> [${esc(r.priority)}]: ${esc(r.action)} <span class="text-muted">- ${esc(r.reason)}</span>
        </div>`).join('') + '</div>';
    }
  } else {
    document.getElementById('platform-compare').innerHTML = '<div class="loading">No comparison data</div>';
  }
}

async function renderPlatformView(pname, data) {
  const el = document.getElementById('pview-'+pname);
  if (!el) return;

  // u_score.current (NOT u_score.u_proxy_score)
  const u = safe(()=>data.u_score?.current);
  const uV = safe(()=>data.u_score?.verdict,'--');
  const uTrend = safe(()=>data.u_score?.trend_24h,'--');
  const uBlockers = safe(()=>data.u_score?.blockers, []);
  const m = data.metrics || {};
  const acc = data.accumulator || {};

  // Fetch detailed data in parallel
  const [signals, trades, uHistory] = await Promise.all([
    api(`/trading/platforms/${pname}/signals`).catch(()=>null),
    api(`/trading/platforms/${pname}/trades?limit=20`).catch(()=>null),
    api(`/trading/platforms/${pname}/u-history?limit=20`).catch(()=>null),
  ]);

  // trades: array directly. u-history: array directly [{timestamp,u_score,reason}]
  const tradeArr = Array.isArray(trades) ? trades : (trades?.trades || []);
  const uHistArr = Array.isArray(uHistory) ? uHistory : (uHistory?.history || []);

  // signals: {total_signals, valid_signals, problems:[{strategy,blockers}]}
  const sigTotal = safe(()=>signals?.total_signals, 0);
  const sigValid = safe(()=>signals?.valid_signals, 0);
  const sigProblems = signals?.problems || [];

  el.innerHTML = `
    <div class="col-3" style="margin-bottom:16px">
      <div class="section-card">
        <div class="section-body u-display">
          <div class="u-value ${uColor(u)}">${n(u,4)}</div>
          <div class="u-label">U Score - ${esc(pname)}</div>
          <div class="u-verdict ${uColor(u)}">${esc(uV)}</div>
          <div class="text-xs text-muted mt-8">Trend 24h: ${esc(uTrend)}</div>
          ${uBlockers.length ? `<div class="text-xs text-red mt-8">${uBlockers.join(', ')}</div>` : ''}
        </div>
      </div>
      <div class="section-card">
        <div class="section-header">Metrics</div>
        <div class="section-body">
          ${kvBlock([
            ['Total Trades', m.total_trades ?? '--'],
            ['Wins / Losses', `${m.winning_trades??'--'} / ${m.losing_trades??'--'}`],
            ['Win Rate', pctRaw(m.win_rate)],
            ['Total Profit', n(m.total_profit,2), (m.total_profit||0)>=0?'text-green':'text-red'],
            ['Expectancy', n(m.expectancy,4)],
            ['Sample Quality', n(m.sample_quality,2)],
            ['Max Drawdown', n(m.max_drawdown,2)],
            ['Sharpe', n(m.sharpe_ratio,2)],
          ])}
        </div>
      </div>
      <div class="section-card">
        <div class="section-header">Accumulator</div>
        <div class="section-body">
          ${kvBlock([
            ['Running', acc.running ? 'Yes' : 'No', acc.running ? 'text-green' : 'text-red'],
            ['Session Trades', acc.session_trades ?? '--'],
            ['Consecutive Skips', acc.consecutive_skips ?? '--'],
            ['Last Trade', ago(acc.last_trade)],
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
          ).join('') : '<div class="text-muted text-sm">No history</div>'}
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
          ).join('') : `<div class="text-muted text-sm">Avg confidence: ${n(signals?.avg_confidence,2)}</div>`}
        </div>
      </div>
      <div class="section-card">
        <div class="section-header">Recent Trades</div>
        <div class="section-body no-pad scroll-y">
          ${tradeArr.length ? `<table><thead><tr><th>Time</th><th>Strategy</th><th>Symbol</th><th>Dir</th><th>Profit</th><th>Status</th></tr></thead><tbody>` +
            tradeArr.slice(0,15).map(t => {
              const p = t.profit??t.pnl??null;
              return `<tr>
                <td class="nowrap text-muted text-xs">${ago(t.timestamp||t.opened_at)}</td>
                <td class="mono text-xs">${esc(t.strategy_id||t.strategy||'--')}</td>
                <td>${esc(t.symbol||'--')}</td>
                <td>${esc(t.direction||'--')}</td>
                <td class="mono ${p>0?'text-green':p<0?'text-red':''}">${p!=null?n(p,4):'--'}</td>
                <td>${t.resolved?badge('resolved','green'):badge('open','amber')}</td>
              </tr>`;
            }).join('') + '</tbody></table>' : '<div class="loading">No trades</div>'}
        </div>
      </div>
    </div>
  `;
}

function switchPlatform(pname) {
  activePlatform = pname;
  document.querySelectorAll('.platform-tab').forEach(t => t.classList.toggle('active', t.textContent.trim()===pname));
  document.querySelectorAll('.platform-view').forEach(v => v.classList.toggle('active', v.id==='pview-'+pname));
}

/* ─────────────────────────────────────────────
   STRATEGY ENGINE PANEL
   API: /brain/strategy-engine/ranking-v2 → {top_strategy:{strategy_id,...}, ranked:[...]}
   API: /brain/strategy-engine/scorecards → {scorecards:{id:{strategy_id,entries_taken,entries_resolved,wins,losses,...},...}}
   API: /brain/strategy-engine/expectancy → {summary:{strategies_count,top_strategy:{...},top_symbol:{...},...}}
   API: /brain/strategy-engine/hypotheses → {results:[{hypothesis_id,strategy_id,statement,status,result,...},...]}
───────────────────────────────────────────── */
async function refreshStrategy() {
  const [ranking, scorecards, expectancy, hypotheses] = await Promise.all([
    api('/brain/strategy-engine/ranking-v2'),
    api('/brain/strategy-engine/scorecards'),
    api('/brain/strategy-engine/expectancy'),
    api('/brain/strategy-engine/hypotheses'),
  ]);

  // KPIs
  const totalStrategies = safe(()=>ranking.ranked?.length, 0);
  // ranking-v2: top_strategy (NOT top_candidate)
  const topId = safe(()=>ranking.top_strategy?.strategy_id || ranking.ranked?.[0]?.strategy_id, '--');
  const topGovState = safe(()=>ranking.top_strategy?.governance_state, '--');
  // expectancy: summary.top_strategy.expectancy (NOT by_strategy array)
  const topExp = safe(()=>expectancy?.summary?.top_strategy?.expectancy);
  const posStratCount = safe(()=>expectancy?.summary?.positive_expectancy_strategies_count, 0);
  // hypotheses: results[] (NOT hypotheses[])
  const hypoResults = hypotheses?.results || [];
  const hypothesesTotal = hypoResults.length;
  const hypothesesTesting = hypoResults.filter(h=>h.status==='in_test').length;
  const hypothesesQueued = hypoResults.filter(h=>h.status==='queued').length;

  // If all APIs failed, show error
  if (!ranking && !scorecards && !expectancy && !hypotheses) {
    document.getElementById('strategy-kpis').innerHTML = '<div class="err-msg" style="grid-column:1/-1">Failed to load strategy engine data</div>';
    document.getElementById('strategy-ranking').innerHTML = '<div class="err-msg">API unreachable</div>';
    document.getElementById('strategy-scorecards').innerHTML = '<div class="err-msg">API unreachable</div>';
    document.getElementById('strategy-expectancy').innerHTML = '<div class="err-msg">API unreachable</div>';
    document.getElementById('strategy-hypotheses').innerHTML = '<div class="err-msg">API unreachable</div>';
    return;
  }

  document.getElementById('strategy-kpis').innerHTML = `
    <div class="kpi"><div class="label">Total Strategies</div><div class="value ${ranking==null?'warn':'accent'}">${ranking==null?'N/A':totalStrategies}</div></div>
    <div class="kpi"><div class="label">Top Candidate</div><div class="value text-accent" style="font-size:12px;word-break:break-all">${esc(topId)}</div><div class="sub">${esc(topGovState)}</div></div>
    <div class="kpi"><div class="label">Top Expectancy</div><div class="value ${(topExp||0)>0?'ok':'err'}">${n(topExp,4)}</div><div class="sub">${posStratCount} positive</div></div>
    <div class="kpi"><div class="label">Hypotheses</div><div class="value ${hypotheses==null?'warn':'accent'}">${hypotheses==null?'N/A':`${hypothesesTesting} testing / ${hypothesesQueued} queued / ${hypothesesTotal}`}</div></div>
  `;

  // Ranking table
  if (ranking?.ranked?.length) {
    document.getElementById('strategy-ranking').innerHTML = `<table><thead><tr>
      <th>#</th><th>Strategy</th><th>Venue</th><th>Family</th><th>Score</th><th>Exp</th><th>WR</th><th>Resolved</th><th>Governance</th><th>Ready</th>
    </tr></thead><tbody>` +
      ranking.ranked.map((s,i) => `<tr>
        <td class="text-muted">${i+1}</td>
        <td class="mono text-xs" style="font-weight:600">${esc(s.strategy_id)}</td>
        <td>${esc(s.venue||'--')}</td>
        <td class="text-muted">${esc(s.family||'--')}</td>
        <td class="mono">${n(s.priority_score,4)}</td>
        <td class="mono ${(s.expectancy||0)>0?'text-green':(s.expectancy||0)<0?'text-red':''}">${n(s.expectancy,2)}</td>
        <td class="mono">${pct(s.win_rate)}</td>
        <td class="mono">${s.entries_resolved??'--'}</td>
        <td>${statusBadge(s.governance_state||'--')}</td>
        <td>${s.execution_ready ? badge('ready','green') : badge('not ready','amber')}</td>
      </tr>`).join('') + '</tbody></table>';
  } else {
    document.getElementById('strategy-ranking').innerHTML = '<div class="loading">No ranking data</div>';
  }

  // Scorecards — scorecards.scorecards is dict of dicts
  if (scorecards?.scorecards) {
    const cards = scorecards.scorecards;
    const entries = Object.entries(cards);
    if (entries.length) {
      document.getElementById('strategy-scorecards').innerHTML = `<table><thead><tr>
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
        </tr>`).join('') + '</tbody></table>';
    } else {
      document.getElementById('strategy-scorecards').innerHTML = '<div class="loading">No scorecards</div>';
    }
  } else {
    document.getElementById('strategy-scorecards').innerHTML = '<div class="loading">No scorecards</div>';
  }

  // Expectancy — show summary.top_strategy and summary stats
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
    document.getElementById('strategy-expectancy').innerHTML = '<div class="loading">No expectancy data</div>';
  }

  // Hypotheses — results[] (NOT hypotheses[])
  if (hypoResults.length) {
    document.getElementById('strategy-hypotheses').innerHTML = `<table><thead><tr>
      <th>Hypothesis</th><th>Strategy</th><th>Status</th><th>Result</th><th>Resolved</th><th>Expectancy</th>
    </tr></thead><tbody>` +
      hypoResults.map(h => `<tr>
        <td class="mono text-xs">${esc(h.hypothesis_id||'--')}</td>
        <td class="mono text-xs">${esc(h.strategy_id||'--')}</td>
        <td>${statusBadge(h.status||'--')}</td>
        <td>${esc(h.result||'--')}</td>
        <td class="mono">${h.entries_resolved??'--'}</td>
        <td class="mono ${(h.expectancy||0)>0?'text-green':(h.expectancy||0)<0?'text-red':''}">${n(h.expectancy,4)}</td>
      </tr>`).join('') + '</tbody></table>';
  } else {
    document.getElementById('strategy-hypotheses').innerHTML = '<div class="loading">No hypotheses</div>';
  }
}

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

  document.getElementById('autonomy-kpis').innerHTML = `
    <div class="kpi"><div class="label">Loop Status</div><div class="value ${autonomy==null?'warn':running?'ok':'err'}">${autonomy==null?'N/A':running?'Running':'Stopped'}</div></div>
    <div class="kpi"><div class="label">Active Tasks</div><div class="value accent">${autonomy==null?'--':taskCount}</div></div>
    <div class="kpi"><div class="label">Reports</div><div class="value accent">${autonomy==null?'--':reportsCount}</div></div>
    <div class="kpi"><div class="label">Accumulator</div><div class="value ${accumulator==null?'warn':accRunning?'ok':'err'}">${accumulator==null?'N/A':accRunning?'Running':'Stopped'}</div><div class="sub">${accumulator==null?'--':accTrades} trades</div></div>
    <div class="kpi"><div class="label">IBKR Ingester</div><div class="value ${ibkr==null?'warn':ibkrRunning?'ok':'err'}">${ibkr==null?'N/A':ibkrRunning?'Running':'Stopped'}</div></div>
  `;

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
    document.getElementById('autonomy-accumulator').innerHTML = kvBlock([
      ['Running', accRunning ? 'Yes' : 'No', accRunning ? 'text-green' : 'text-red'],
      ['Session Trades', a.session_trades_count ?? '--'],
      ['Max Trades/Session', a.max_trades_per_session ?? '--'],
      ['Check Interval (min)', a.check_interval_minutes ?? '--'],
      ['Cooldown (min)', a.cooldown_minutes ?? '--'],
      ['Min Sample Quality', a.min_sample_quality ?? '--'],
      ['Min Entries Resolved', a.min_entries_resolved ?? '--'],
      ['Target Entries', a.target_entries ?? '--'],
      ['Last Trade', ago(a.last_trade_time)],
    ]);
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
  const rpts = Array.isArray(reports) ? reports : (reports?.reports || []);
  if (rpts.length) {
    document.getElementById('autonomy-reports').innerHTML = `<table><thead><tr><th>Time</th><th>Type</th><th>Detail</th></tr></thead><tbody>` +
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
      }).join('') + '</tbody></table>';
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
    // Current work
    if (d.current_work_items?.length) {
      document.getElementById('roadmap-development').innerHTML += '<div class="mt-12"><div class="text-xs text-muted mb-8">Current Work:</div>' +
        d.current_work_items.map(w => `<div class="text-sm" style="padding:2px 0 2px 12px">- ${esc(w)}</div>`).join('') + '</div>';
    }
    if (d.blockers?.length) {
      document.getElementById('roadmap-development').innerHTML += '<div class="mt-12"><strong class="text-amber">Blockers:</strong>' +
        d.blockers.map(b => `<div style="padding:4px 0;margin-left:12px" class="text-sm">
          <span class="mono text-red">${esc(b.check_id||b.id||'')}</span>: ${esc(b.detail||b.message||'')}
        </div>`).join('') + '</div>';
    }
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
      document.getElementById('roadmap-postbl').innerHTML += '<div class="mt-12 scroll-y"><table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Detail</th></tr></thead><tbody>' +
        items.map(it => `<tr>
          <td class="mono">${esc(it.item_id)}</td>
          <td>${esc(it.title)}</td>
          <td>${statusBadge(it.status||'--')}</td>
          <td class="text-xs text-muted">${esc(it.detail||'')}</td>
        </tr>`).join('') + '</tbody></table></div>';
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
      document.getElementById('meta-improvement').innerHTML += '<div class="mt-12"><div class="text-xs text-muted mb-8">Domains:</div><table><thead><tr><th>Domain</th><th>Score</th><th>Status</th></tr></thead><tbody>' +
        domains.map(d => `<tr>
          <td>${esc(d.title || d.domain_id)}</td>
          <td class="mono ${d.score>=0.7?'text-green':d.score>=0.4?'text-amber':'text-red'}">${n(d.score,2)}</td>
          <td>${statusBadge(d.status)}</td>
        </tr>`).join('') + '</tbody></table></div>';
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
  const [health, pipeline, policy] = await Promise.all([
    api('/brain/health'),
    api('/brain/pipeline-health'),
    api('/trading/policy'),
  ]);

  // KPIs
  const overall = safe(()=>health.overall_status, 'unknown');
  // pipeline: total_tests and failures (NOT tests_passing)
  const testsTotal = safe(()=>pipeline.total_tests, '--');
  const testsFailed = safe(()=>pipeline.failures, 0);
  const testsPassing = testsTotal !== '--' ? testsTotal - testsFailed : '--';
  const pipelineOk = safe(()=>pipeline.ok, false);
  const paperOnly = safe(()=>policy.global_rules?.paper_only, '--');

  document.getElementById('system-kpis').innerHTML = `
    <div class="kpi"><div class="label">Overall Health</div><div class="value ${overall==='healthy'?'ok':overall==='degraded'?'warn':'err'}">${esc(overall)}</div><div class="sub">${safe(()=>health.summary?.healthy,0)}/${safe(()=>health.summary?.total,0)} services</div></div>
    <div class="kpi"><div class="label">Tests</div><div class="value ${testsFailed===0?'ok':'err'}">${testsPassing} / ${testsTotal}</div><div class="sub">${testsFailed} failures</div></div>
    <div class="kpi"><div class="label">Pipeline</div><div class="value ${pipeline==null?'warn':pipelineOk?'ok':'err'}">${pipeline==null?'N/A':pipelineOk?'All Passing':'Issues'}</div></div>
    <div class="kpi"><div class="label">Trading Mode</div><div class="value">${paperOnly===true ? badge('paper_only','green') : paperOnly===false ? badge('LIVE','red') : badge('unknown','amber')}</div></div>
  `;

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
      document.getElementById('system-pipeline').innerHTML += '<div class="mt-12 scroll-y"><table><thead><tr><th>Test</th><th>Description</th><th>Status</th></tr></thead><tbody>' +
        pv.tests.map(t => `<tr>
          <td class="mono text-xs">${esc(t.id)}</td>
          <td class="text-sm">${esc(t.desc)}</td>
          <td>${t.verified ? badge('pass','green') : badge('fail','red')}</td>
        </tr>`).join('') + '</tbody></table></div>';
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
      document.getElementById('system-policy').innerHTML += '<div class="mt-12"><table><thead><tr><th>Platform</th><th>Paper</th><th>Live</th><th>Mode</th></tr></thead><tbody>' +
        Object.entries(pr).map(([pname, rules]) => `<tr>
          <td style="font-weight:600">${esc(pname)}</td>
          <td>${rules.paper_allowed ? badge('yes','green') : badge('no','red')}</td>
          <td>${rules.live_allowed ? badge('yes','red') : badge('no','green')}</td>
          <td class="mono text-xs">${esc(rules.mode)}</td>
        </tr>`).join('') + '</tbody></table></div>';
    }
  } else {
    document.getElementById('system-policy').innerHTML = '<div class="err-msg">Failed to load policy</div>';
  }
}

/* ─────────────────────────────────────────────
   Refresh dispatcher & auto-refresh
───────────────────────────────────────────── */
let _refreshing = false;
async function refreshCurrentPanel() {
  if (_refreshing) return;
  _refreshing = true;
  // Clear any previous refresh-level error
  const panel = document.getElementById('panel-'+currentPanel);
  if (panel) { const oldErr = panel.querySelector(':scope > .err-msg'); if (oldErr) oldErr.remove(); }
  try {
    switch(currentPanel) {
      case 'overview': await refreshOverview(); break;
      case 'platforms': await refreshPlatforms(); break;
      case 'strategy': await refreshStrategy(); break;
      case 'autonomy': await refreshAutonomy(); break;
      case 'roadmap': await refreshRoadmap(); break;
      case 'meta': await refreshMeta(); break;
      case 'selfimprove': await refreshSelfImprove(); break;
      case 'system': await refreshSystem(); break;
    }
  } catch(e) {
    console.error('Refresh error:', e);
    const panel = document.getElementById('panel-'+currentPanel);
    if (panel && !panel.querySelector('.err-msg')) {
      panel.insertAdjacentHTML('afterbegin', `<div class="err-msg" style="margin-bottom:12px">Refresh error: ${esc(e.message||String(e))}</div>`);
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

// Boot
document.addEventListener('DOMContentLoaded', () => {
  refreshCurrentPanel();
  startAutoRefresh();
});
