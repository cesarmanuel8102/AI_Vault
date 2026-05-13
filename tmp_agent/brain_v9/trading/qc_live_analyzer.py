"""
Brain Chat V9 — trading/qc_live_analyzer.py
QC Live Degradation Analyzer — reads monitor snapshots, detects degradation
patterns, proposes auto-adjustments within permitted bounds, and documents
every action visibly for César.

RULES (from approved plan):
- Brain CAN auto-adjust if: change < 20%, clear evidence, fully documented.
- Brain CANNOT: change version, modify entry/exit logic, change tickers,
  increase sizing above max, disable stops.
- Every action gets logged with APLICADO/PENDIENTE/RECHAZADO status.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from brain_v9.trading.qc_live_monitor import (
    BACKTEST_REFERENCE,
    get_live_state,
    get_all_snapshots,
    record_brain_action,
)

log = logging.getLogger("qc_live_analyzer")

# ── Analysis thresholds ──────────────────────────────────────────────────────
# Minimum snapshots before analysis kicks in (avoid noise from first few polls)
MIN_SNAPSHOTS_FOR_ANALYSIS = 12  # ~1 hour at 5-min intervals
# Minimum trading days before declaring degradation
MIN_TRADING_DAYS = 3

# Degradation detection windows
WINDOWS = {
    "short": 12,    # 1 hour
    "medium": 72,   # 6 hours
    "long": 288,    # 24 hours
}


def analyze_live_performance(days: int = 7) -> Dict:
    """Run full analysis on QC Live performance.

    Returns analysis report with:
    - trend detection (equity direction)
    - degradation signals
    - suggested actions (if any)
    - overall health assessment
    """
    state = get_live_state()
    if not state.get("deployed"):
        return {"status": "not_deployed", "analysis": None}

    snapshots = get_all_snapshots(days=days)
    if len(snapshots) < MIN_SNAPSHOTS_FOR_ANALYSIS:
        return {
            "status": "insufficient_data",
            "snapshots_count": len(snapshots),
            "required": MIN_SNAPSHOTS_FOR_ANALYSIS,
            "message": f"Need at least {MIN_SNAPSHOTS_FOR_ANALYSIS} snapshots for analysis",
        }

    ref = BACKTEST_REFERENCE
    latest = snapshots[-1]

    # Run all analysis modules
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "snapshots_analyzed": len(snapshots),
        "latest_snapshot": latest,
        "backtest_reference": ref,
    }

    report["equity_trend"] = _analyze_equity_trend(snapshots)
    report["drawdown_analysis"] = _analyze_drawdown(snapshots, ref)
    report["win_rate_analysis"] = _analyze_win_rate(snapshots, ref)
    report["sharpe_analysis"] = _analyze_sharpe(snapshots, ref)
    report["volatility_analysis"] = _analyze_volatility(snapshots)

    # Aggregate health score
    health = _compute_health_score(report)
    report["health"] = health

    # Generate suggestions
    suggestions = _generate_suggestions(report)
    report["suggestions"] = suggestions

    return {"status": "ok", "analysis": report}


def _analyze_equity_trend(snapshots: List[Dict]) -> Dict:
    """Detect equity trend direction and momentum."""
    equities = [
        (s.get("timestamp_utc", ""), s.get("equity"))
        for s in snapshots
        if s.get("equity") is not None
    ]
    if len(equities) < 2:
        return {"direction": "unknown", "data_points": len(equities)}

    values = [e[1] for e in equities]
    first = values[0]
    last = values[-1]
    change_pct = (last - first) / first if first != 0 else 0

    # Simple trend: compare short window average vs long window average
    short_window = min(12, len(values))
    long_window = min(72, len(values))
    short_avg = sum(values[-short_window:]) / short_window
    long_avg = sum(values[-long_window:]) / long_window

    if short_avg > long_avg * 1.005:
        direction = "up"
    elif short_avg < long_avg * 0.995:
        direction = "down"
    else:
        direction = "flat"

    # High/low
    high = max(values)
    low = min(values)
    current_vs_high = (last - high) / high if high != 0 else 0

    return {
        "direction": direction,
        "change_pct": round(change_pct, 4),
        "first_equity": first,
        "last_equity": last,
        "high": high,
        "low": low,
        "current_vs_high_pct": round(current_vs_high, 4),
        "short_avg": round(short_avg, 2),
        "long_avg": round(long_avg, 2),
        "data_points": len(values),
    }


def _analyze_drawdown(snapshots: List[Dict], ref: Dict) -> Dict:
    """Analyze drawdown relative to backtest reference."""
    drawdowns = [
        s.get("drawdown") for s in snapshots
        if s.get("drawdown") is not None
    ]
    if not drawdowns:
        return {"status": "no_data"}

    max_dd = max(abs(d) for d in drawdowns)
    current_dd = abs(drawdowns[-1])
    ref_dd = ref.get("max_drawdown", 0.166)

    ratio = max_dd / ref_dd if ref_dd > 0 else 0
    current_ratio = current_dd / ref_dd if ref_dd > 0 else 0

    if ratio >= 1.0:
        status = "critical"
    elif ratio >= 0.8:
        status = "warn"
    else:
        status = "ok"

    return {
        "max_live_dd": round(max_dd, 4),
        "current_dd": round(current_dd, 4),
        "backtest_max_dd": ref_dd,
        "max_dd_ratio": round(ratio, 3),
        "current_dd_ratio": round(current_ratio, 3),
        "status": status,
    }


def _analyze_win_rate(snapshots: List[Dict], ref: Dict) -> Dict:
    """Analyze win rate trend and compare to backtest."""
    win_rates = [
        s.get("win_rate") for s in snapshots
        if s.get("win_rate") is not None
    ]
    if not win_rates:
        return {"status": "no_data"}

    current_wr = win_rates[-1]
    ref_wr = ref.get("win_rate", 0.69)
    delta = ref_wr - current_wr

    # Trend: is WR improving or degrading?
    if len(win_rates) >= 12:
        recent = sum(win_rates[-12:]) / 12
        older = sum(win_rates[:12]) / 12
        wr_trend = "improving" if recent > older + 0.02 else ("degrading" if recent < older - 0.02 else "stable")
    else:
        wr_trend = "insufficient_data"

    if delta >= 0.25:
        status = "critical"
    elif delta >= 0.15:
        status = "warn"
    else:
        status = "ok"

    return {
        "current": round(current_wr, 3),
        "backtest": ref_wr,
        "delta": round(delta, 3),
        "trend": wr_trend,
        "status": status,
    }


def _analyze_sharpe(snapshots: List[Dict], ref: Dict) -> Dict:
    """Analyze Sharpe ratio degradation."""
    sharpes = [
        s.get("sharpe_ratio") for s in snapshots
        if s.get("sharpe_ratio") is not None
    ]
    if not sharpes:
        return {"status": "no_data"}

    current = sharpes[-1]
    ref_sharpe = ref.get("sharpe_ratio", 0.899)
    ratio = current / ref_sharpe if ref_sharpe != 0 else 0

    if ratio < 0.5:
        status = "critical"
    elif ratio < 0.7:
        status = "warn"
    else:
        status = "ok"

    return {
        "current": round(current, 3),
        "backtest": ref_sharpe,
        "ratio": round(ratio, 3),
        "status": status,
    }


def _analyze_volatility(snapshots: List[Dict]) -> Dict:
    """Analyze equity volatility (useful for position sizing decisions)."""
    equities = [
        s.get("equity") for s in snapshots
        if s.get("equity") is not None
    ]
    if len(equities) < 10:
        return {"status": "insufficient_data"}

    # Calculate returns between consecutive snapshots
    returns = []
    for i in range(1, len(equities)):
        if equities[i - 1] != 0:
            returns.append((equities[i] - equities[i - 1]) / equities[i - 1])

    if not returns:
        return {"status": "no_returns"}

    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_dev = variance ** 0.5

    return {
        "mean_return_per_interval": round(mean_return, 6),
        "std_dev_per_interval": round(std_dev, 6),
        "annualized_vol_approx": round(std_dev * (252 * 78) ** 0.5, 4),  # ~78 intervals/day at 5min
        "max_single_interval_loss": round(min(returns), 6) if returns else 0,
        "max_single_interval_gain": round(max(returns), 6) if returns else 0,
        "data_points": len(returns),
        "status": "ok",
    }


def _compute_health_score(report: Dict) -> Dict:
    """Compute overall health score from individual analyses."""
    scores = {
        "drawdown": report.get("drawdown_analysis", {}).get("status", "unknown"),
        "win_rate": report.get("win_rate_analysis", {}).get("status", "unknown"),
        "sharpe": report.get("sharpe_analysis", {}).get("status", "unknown"),
    }

    severity_values = {"ok": 0, "warn": 1, "critical": 2, "no_data": -1, "unknown": -1}
    valid_scores = [severity_values.get(s, -1) for s in scores.values() if severity_values.get(s, -1) >= 0]

    if not valid_scores:
        return {"overall": "unknown", "components": scores}

    max_severity = max(valid_scores)
    overall = {0: "healthy", 1: "degraded", 2: "critical"}[max_severity]

    trend = report.get("equity_trend", {}).get("direction", "unknown")
    if trend == "down" and overall == "healthy":
        overall = "caution"

    return {
        "overall": overall,
        "components": scores,
        "equity_trend": trend,
    }


def _generate_suggestions(report: Dict) -> List[Dict]:
    """Generate actionable suggestions based on analysis.

    These are DOCUMENTED suggestions — they don't auto-execute.
    Brain V9 can auto-apply only the "minor" ones within the permitted bounds.
    """
    suggestions = []
    health = report.get("health", {})
    overall = health.get("overall", "unknown")

    # Drawdown approaching max
    dd = report.get("drawdown_analysis", {})
    if dd.get("status") == "critical":
        suggestions.append({
            "type": "sizing_reduction",
            "severity": "high",
            "auto_applicable": True,
            "description": f"Drawdown ({dd.get('max_live_dd', 0):.1%}) exceeds backtest max ({dd.get('backtest_max_dd', 0):.1%}). Consider reducing position sizing by 20%.",
            "evidence": f"Max DD ratio: {dd.get('max_dd_ratio', 0):.2f}x backtest reference",
            "change": {"parameter": "position_size_pct", "direction": "reduce", "amount": 0.20},
        })
    elif dd.get("status") == "warn":
        suggestions.append({
            "type": "sizing_review",
            "severity": "medium",
            "auto_applicable": False,
            "description": f"Drawdown ({dd.get('current_dd', 0):.1%}) approaching backtest max. Monitor closely.",
            "evidence": f"Current DD ratio: {dd.get('current_dd_ratio', 0):.2f}x backtest reference",
        })

    # Win rate degradation
    wr = report.get("win_rate_analysis", {})
    if wr.get("status") == "critical":
        suggestions.append({
            "type": "strategy_review",
            "severity": "high",
            "auto_applicable": False,
            "description": f"Win rate ({wr.get('current', 0):.1%}) severely below backtest ({wr.get('backtest', 0):.1%}). Manual review needed.",
            "evidence": f"Delta: {wr.get('delta', 0):.1%}, Trend: {wr.get('trend', 'unknown')}",
        })
    elif wr.get("status") == "warn" and wr.get("trend") == "degrading":
        suggestions.append({
            "type": "threshold_review",
            "severity": "medium",
            "auto_applicable": False,
            "description": f"Win rate declining ({wr.get('current', 0):.1%} vs {wr.get('backtest', 0):.1%}). Consider tightening entry conditions.",
            "evidence": f"Win rate trend: {wr.get('trend', 'unknown')}",
        })

    # Sharpe degradation
    sharpe = report.get("sharpe_analysis", {})
    if sharpe.get("status") == "critical":
        suggestions.append({
            "type": "performance_alert",
            "severity": "high",
            "auto_applicable": False,
            "description": f"Sharpe ratio ({sharpe.get('current', 0):.3f}) is less than half of backtest ({sharpe.get('backtest', 0):.3f}). Strategy may need fundamental review.",
            "evidence": f"Sharpe ratio: {sharpe.get('ratio', 0):.1%} of backtest",
        })

    # Equity trend down + healthy metrics = possible regime change
    eq_trend = report.get("equity_trend", {})
    if eq_trend.get("direction") == "down" and overall in ("healthy", "caution"):
        suggestions.append({
            "type": "regime_monitor",
            "severity": "low",
            "auto_applicable": False,
            "description": "Equity trending down despite acceptable metrics. May indicate regime change. Continue monitoring.",
            "evidence": f"Equity change: {eq_trend.get('change_pct', 0):.2%}, trend: {eq_trend.get('direction')}",
        })

    return suggestions


def run_analysis_cycle() -> Dict:
    """Run a full analysis cycle and log any auto-applicable actions.

    This is meant to be called periodically (e.g., every 6 hours)
    by the scheduler.
    """
    result = analyze_live_performance(days=7)
    if result.get("status") != "ok":
        return result

    analysis = result.get("analysis", {})
    suggestions = analysis.get("suggestions", [])

    for s in suggestions:
        if s.get("auto_applicable") and s.get("change"):
            change = s["change"]
            # Auto-apply within permitted bounds (< 20% change)
            if change.get("amount", 1.0) <= 0.20:
                record_brain_action(
                    action_type=s["type"],
                    description=s["description"],
                    evidence=s["evidence"],
                    change_detail=change,
                    status="PENDIENTE",  # Mark as PENDIENTE — actual application needs QC API
                )
                log.info("Brain suggestion logged as PENDIENTE: %s", s["type"])
            else:
                record_brain_action(
                    action_type=s["type"],
                    description=s["description"],
                    evidence=s["evidence"],
                    change_detail=change,
                    status="RECHAZADO",
                )
                log.info("Brain suggestion REJECTED (exceeds 20%% bound): %s", s["type"])
        elif s.get("severity") in ("high", "medium"):
            # Log non-auto suggestions for visibility
            record_brain_action(
                action_type=s["type"],
                description=s["description"],
                evidence=s.get("evidence", ""),
                change_detail={},
                status="PENDIENTE",
            )

    return result
