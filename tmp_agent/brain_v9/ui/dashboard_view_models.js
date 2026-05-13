function asArray(data, key = 'items') {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data[key])) return data[key];
  return [];
}

function platformTradeArray(data) {
  return asArray(data, 'trades');
}

function platformHistoryArray(data) {
  return asArray(data, 'history');
}

function deriveVenueAnchor(platformSummary) {
  const platforms = platformSummary?.platforms || {};
  const rows = Object.entries(platforms)
    .filter(([pname]) => ['pocket_option', 'ibkr'].includes(pname))
    .map(([pname, platform]) => ({
      platform: pname,
      current: safe(() => platform.u_score?.current, null),
      verdict: safe(() => platform.u_score?.verdict, '--'),
    }))
    .filter(row => row.current != null);
  if (!rows.length) {
    return { platform: '--', current: null, verdict: '--' };
  }
  return rows.reduce((worst, row) => (row.current < worst.current ? row : worst), rows[0]);
}

function deriveOverviewPlatformRow(pname, platform) {
  const uVal = safe(() => platform.u_score?.current, null);
  const uVerdict = safe(() => platform.u_score?.verdict, '--');
  const resolvedTrades = safe(() => platform.metrics?.total_trades, 0);
  const trend = safe(() => platform.u_score?.trend_24h, '--');
  const uBasis = safe(() => platform.u_score?.display_basis, '--');
  const livePositions = safe(() => platform.execution?.live_positions_count, 0);
  let contextLabel = `${resolvedTrades} resolved | trend: ${trend}`;
  if (uBasis === 'live_positions_no_resolved_sample') {
    contextLabel = `${livePositions} live positions | no resolved sample`;
  } else if (uBasis === 'inactive') {
    contextLabel = 'inactive | no active sample';
  }
  return {
    platform: pname,
    uVal,
    uVerdict,
    trend,
    uBasis,
    contextLabel,
  };
}

function derivePlatformContextNote(uBasis) {
  if (uBasis === 'live_positions_no_resolved_sample') {
    return 'Live broker positions present. U stays N/A until Brain resolves canonical sample for this platform.';
  }
  if (uBasis === 'inactive') {
    return 'Platform inactive. No canonical runtime or performance sample is being accumulated.';
  }
  return 'Comparison uses canonical resolved sample and stored platform performance, not raw broker activity.';
}

function deriveCanonicalTopState(ranking) {
  const canonicalTop = ranking?.top_strategy || null;
  const rankedLeader = ranking?.ranked?.[0] || null;
  return {
    canonicalTop,
    rankedLeader,
    topId: safe(() => canonicalTop?.strategy_id, '--'),
    topGovState: safe(() => canonicalTop?.governance_state, '--'),
    rankedLeaderId: safe(() => rankedLeader?.strategy_id, '--'),
    rankedLeaderEdgeState: safe(() => rankedLeader?.edge_state, '--'),
  };
}

function deriveFocusStrategies(ranking, operating) {
  return (ranking?.ranked || []).filter(strategy => strategyMatchesOperatingLane(strategy, operating));
}

function normalizeReports(reports) {
  return asArray(reports, 'reports');
}

function normalizeSessionRows(sessionPerf) {
  const windows = sessionPerf?.windows || {};
  const sessions = sessionPerf?.sessions || {};
  const rows = Object.entries(sessions).map(([name, session]) => ({
    key: name,
    label: safe(() => windows[name]?.label, name),
    quality: safe(() => windows[name]?.quality, '--'),
    wins: session.wins || 0,
    losses: session.losses || 0,
    winRate: session.win_rate || 0,
    netPnl: session.net_pnl || 0,
    resolved: session.resolved || 0,
    empty: false,
  }));
  Object.entries(windows).forEach(([name, window]) => {
    if (!sessions[name]) {
      rows.push({
        key: name,
        label: window.label || name,
        quality: window.quality || '--',
        wins: 0,
        losses: 0,
        winRate: null,
        netPnl: null,
        resolved: 0,
        empty: true,
      });
    }
  });
  return rows;
}

function normalizeAdaptationItems(adaptState) {
  return asArray(adaptState, 'items');
}
