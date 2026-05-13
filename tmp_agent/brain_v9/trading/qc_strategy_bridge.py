"""
P4-10 — Backtest-to-Strategy Bridge

Translates QuantConnect backtest results into ``strategy_specs``-compatible
entries so the Brain can rank and reason about QC-validated strategies
alongside PocketOption and IBKR strategies.

Responsibilities:
  1. ``backtest_to_strategy_spec``  – build a single spec dict from metrics
  2. ``merge_qc_strategy``         – upsert a QC spec into the live specs file
  3. ``list_qc_strategies``        – return all QC-sourced specs

The generated entries use ``venue: "quantconnect"`` and
``status: "qc_backtest_validated"`` so the strategy selector can distinguish
them from live-trading candidates.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

logger = logging.getLogger("QCStrategyBridge")

# ─── Paths ───────────────────────────────────────────────────────────────────
_SPECS_PATH = BASE_PATH / "tmp_agent" / "state" / "trading_knowledge_base" / "strategy_specs.json"

# ─── Project metadata (known projects) ───────────────────────────────────────
# Legacy ML projects (not used for BRAIN_OPTIONS_V1 but kept for reference)
QC_PROJECTS: Dict[int, Dict[str, Any]] = {
    24654779: {
        "name": "Upgraded Sky Blue Butterfly",
        "family": "ml_ensemble",
        "universe": ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA"],
        "asset_classes": ["stocks", "etfs", "options"],
        "primary_asset_class": "options",
        "timeframes": ["1d"],
        "summary": "Walk-forward LightGBM ensemble with triple-barrier labeling. "
                   "Trains top-5 models by OOS Sharpe, persists to ObjectStore. "
                   "IBKR brokerage model, options universe.",
        "patterns": ["qc_objectstore_model_contract", "qc_ibkr_execution_lane",
                     "qc_options_ml_stack", "qc_temporal_validation_and_calibration"],
    },
    25550271: {
        "name": "Clone of Sleepy Black Buffalo",
        "family": "ml_ensemble",
        "universe": ["AAPL", "MSFT", "QQQ", "SPY", "NVDA", "TSLA"],
        "asset_classes": ["stocks", "etfs", "options"],
        "primary_asset_class": "options",
        "timeframes": ["1d"],
        "summary": "Options ML smart-exec: 10% base sizing with vol-scaling, "
                   "DTE 14-45, max spread 7%, min OI 700, portfolio beta max 1.0. "
                   "Backtest 2023-01-01 to 2025-10-03, $5k starting cash.",
        "patterns": ["qc_objectstore_model_contract", "qc_options_ml_stack",
                     "qc_temporal_validation_and_calibration"],
    },
}

# ─── Rule-based strategies (BRAIN_OPTIONS_V1) ───────────────────────────────
# Keys are strategy codes (S1-S6). The "project_id" is populated at deploy time.
BRAIN_OPTIONS_V1_STRATEGIES: Dict[str, Dict[str, Any]] = {
    "S1_TREND_BULL_CALL_SPREAD": {
        "family": "rule_based_options",
        "regime": "BULL",
        "instrument": "call_debit_spread",
        "universe": ["SPY"],
        "asset_classes": ["etfs", "options"],
        "primary_asset_class": "options",
        "timeframes": ["1min", "15min"],
        "core_indicators": ["SMA50", "SMA200", "RSI14", "BB20", "ADX14"],
        "entry_conditions": [
            "SMA50 > SMA200 (bull regime)",
            "RSI > 50 (momentum confirmation)",
            "Price above BB middle band",
        ],
        "exit_rules": {
            "take_profit": "50% of max spread value",
            "stop_loss": "30% of debit paid",
            "time_stop": "Close at DTE < 5",
            "regime_exit": "SMA50 crosses below SMA200",
        },
        "summary": "Trend-following bull call debit spread. Activated when SMA50>SMA200 "
                   "with RSI momentum confirmation. IBKR Cash, buying only.",
    },
    "S2_TREND_BEAR_PUT_SPREAD": {
        "family": "rule_based_options",
        "regime": "BEAR",
        "instrument": "put_debit_spread",
        "universe": ["SPY"],
        "asset_classes": ["etfs", "options"],
        "primary_asset_class": "options",
        "timeframes": ["1min", "15min"],
        "core_indicators": ["SMA50", "SMA200", "RSI14", "BB20", "ADX14"],
        "entry_conditions": [
            "SMA50 < SMA200 (bear regime)",
            "RSI < 50 (downward momentum)",
            "Price below BB middle band",
        ],
        "exit_rules": {
            "take_profit": "50% of max spread value",
            "stop_loss": "30% of debit paid",
            "time_stop": "Close at DTE < 5",
            "regime_exit": "SMA50 crosses above SMA200",
        },
        "summary": "Trend-following bear put debit spread. Activated when SMA50<SMA200 "
                   "with RSI downward momentum. IBKR Cash, buying only.",
    },
    "S3_REVERSAL_OVERSOLD_CALL": {
        "family": "rule_based_options",
        "regime": "BULL",
        "instrument": "call_debit_spread_itm",
        "universe": ["SPY"],
        "asset_classes": ["etfs", "options"],
        "primary_asset_class": "options",
        "timeframes": ["1min", "15min"],
        "core_indicators": ["SMA50", "SMA200", "RSI14", "BB20"],
        "entry_conditions": [
            "SMA50 > SMA200 (bull regime)",
            "RSI < 30 (oversold)",
            "Price at or below BB lower band",
        ],
        "exit_rules": {
            "take_profit": "50% of max spread value",
            "stop_loss": "30% of debit paid",
            "time_stop": "Close at DTE < 5",
            "regime_exit": "SMA50 crosses below SMA200",
        },
        "summary": "Mean-reversion oversold call debit spread (ITM bias). Activated in "
                   "bull regime when RSI<30. IBKR Cash, buying only.",
    },
    "S4_REVERSAL_OVERBOUGHT_PUT": {
        "family": "rule_based_options",
        "regime": "BEAR_NEUTRAL",
        "instrument": "put_debit_spread_itm",
        "universe": ["SPY"],
        "asset_classes": ["etfs", "options"],
        "primary_asset_class": "options",
        "timeframes": ["1min", "15min"],
        "core_indicators": ["SMA50", "SMA200", "RSI14", "BB20"],
        "entry_conditions": [
            "SMA50 <= SMA200 (bear/neutral regime)",
            "RSI > 70 (overbought)",
            "Price at or above BB upper band",
        ],
        "exit_rules": {
            "take_profit": "50% of max spread value",
            "stop_loss": "30% of debit paid",
            "time_stop": "Close at DTE < 5",
            "regime_exit": "SMA50 crosses above SMA200",
        },
        "summary": "Mean-reversion overbought put debit spread (ITM bias). Activated in "
                   "bear/neutral regime when RSI>70. IBKR Cash, buying only.",
    },
    "S5_SQUEEZE_STRADDLE": {
        "family": "rule_based_options",
        "regime": "SQUEEZE",
        "instrument": "long_straddle",
        "universe": ["SPY"],
        "asset_classes": ["etfs", "options"],
        "primary_asset_class": "options",
        "timeframes": ["1min", "15min"],
        "core_indicators": ["BB20", "ADX14"],
        "entry_conditions": [
            "BB bandwidth < 0.04 (squeeze)",
            "ADX < 15 (no trend)",
        ],
        "exit_rules": {
            "take_profit": "Combined legs +40%",
            "stop_loss": "Combined legs -25%",
            "time_stop": "Close at DTE < 10",
            "regime_exit": "BB bandwidth expands > 0.06",
        },
        "summary": "Volatility squeeze long straddle. Activated when BB bandwidth<0.04 "
                   "and ADX<15. Profits from expansion. IBKR Cash, buying only.",
    },
    "S6_MOMENTUM_BREAKOUT": {
        "family": "rule_based_options",
        "regime": "ANY",
        "instrument": "directional_debit_spread",
        "universe": ["SPY"],
        "asset_classes": ["etfs", "options"],
        "primary_asset_class": "options",
        "timeframes": ["1min", "15min"],
        "core_indicators": ["SMA50", "SMA200", "ADX14", "BB20", "high_20d", "low_20d"],
        "entry_conditions": [
            "Price breaks 20-day high (call spread) or 20-day low (put spread)",
            "ADX > 20 (trend strength confirmation)",
        ],
        "exit_rules": {
            "take_profit": "50% of max spread value",
            "stop_loss": "30% of debit paid",
            "time_stop": "Close at DTE < 5",
            "regime_exit": "Price re-enters 20-day range",
        },
        "summary": "Momentum breakout directional debit spread. Activated on 20-day "
                   "high/low break with ADX confirmation. IBKR Cash, buying only.",
    },
}

# Runtime registry: maps QC project_id → strategy code once deployed
# Populated by deploy_qc_options_v1.py after project creation
_DEPLOYED_OPTIONS_V1: Dict[int, str] = {}


def register_options_v1_project(project_id: int, strategy_code: str = "BRAIN_OPTIONS_V1") -> None:
    """Register a deployed BRAIN_OPTIONS_V1 project ID for bridge lookups."""
    _DEPLOYED_OPTIONS_V1[project_id] = strategy_code
    # Also add to QC_PROJECTS so backtest_to_strategy_spec can find it
    QC_PROJECTS[project_id] = {
        "name": f"Brain Options V1 - {strategy_code}",
        "family": "rule_based_options",
        "universe": ["SPY"],
        "asset_classes": ["etfs", "options"],
        "primary_asset_class": "options",
        "timeframes": ["1min", "15min"],
        "summary": "BRAIN_OPTIONS_V1: 6 rule-based options strategies (buying only). "
                   "Bull/bear spreads, reversal spreads, squeeze straddle, momentum breakout. "
                   "SPY, IBKR Cash account, $25K starting capital.",
        "patterns": ["qc_ibkr_cash_model", "qc_options_rule_based",
                     "qc_regime_detection", "qc_risk_management"],
    }
    logger.info("Registered BRAIN_OPTIONS_V1 project_id=%d as %s", project_id, strategy_code)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def backtest_to_strategy_spec(
    project_id: int,
    backtest_id: str,
    metrics: Dict[str, Any],
    backtest_name: str = "",
) -> Dict[str, Any]:
    """
    Convert QC backtest metrics into a ``strategy_specs``-compatible dict.

    Parameters
    ----------
    project_id : int
        QuantConnect project ID.
    backtest_id : str
        The backtest ID returned by the QC API.
    metrics : dict
        Extracted metrics from ``extract_metrics()`` (P4-09).
    backtest_name : str, optional
        Human-readable name for the backtest run.

    Returns
    -------
    dict
        A strategy spec entry ready for insertion into ``strategy_specs.json``.
    """
    project_meta = QC_PROJECTS.get(project_id, {})
    strategy_id = f"qc_{project_id}_{backtest_id[:8]}"
    family = project_meta.get("family", "unknown")
    is_rule_based = family == "rule_based_options"

    sharpe = _safe_float(metrics.get("sharpe_ratio"))
    win_rate = _safe_float(metrics.get("win_rate"))
    drawdown = _safe_float(metrics.get("drawdown"))
    expectancy = _safe_float(metrics.get("expectancy"))
    net_profit = _safe_float(metrics.get("net_profit"))
    total_orders = int(_safe_float(metrics.get("total_orders")))
    alpha = _safe_float(metrics.get("alpha"))
    beta = _safe_float(metrics.get("beta"))
    profit_factor = _safe_float(metrics.get("profit_loss_ratio"))

    # ── Status: use BRAIN_OPTIONS_V1 promotion criteria for rule-based ────
    if is_rule_based:
        # Sharpe>=0.8, WR>=45%, MaxDD<=20%, trades>=30, PF>=1.3
        abs_dd = abs(drawdown)
        if (sharpe >= 0.8 and win_rate >= 0.45 and abs_dd <= 0.20
                and total_orders >= 30 and profit_factor >= 1.3):
            status = "qc_backtest_validated"
        elif total_orders < 10:
            status = "qc_backtest_insufficient"
        elif sharpe >= 0.5 and win_rate >= 0.40:
            status = "qc_backtest_marginal"
        else:
            status = "qc_backtest_below_threshold"
    else:
        # Legacy ML criteria
        if sharpe >= 1.0 and win_rate >= 0.50 and total_orders >= 20:
            status = "qc_backtest_validated"
        elif total_orders < 5:
            status = "qc_backtest_insufficient"
        else:
            status = "qc_backtest_marginal"

    # ── Entry / exit / filters: differ by family ─────────────────────────
    if is_rule_based:
        entry = {
            "required_conditions": [
                "Regime detection matches strategy activation zone",
                "Indicator conditions met (RSI, BB, ADX, SMA)",
                "Risk budget available (3% per trade, 6% per underlying)",
            ],
            "trigger": ["regime_indicator_alignment"],
        }
        exit_rules = {
            "take_profit": "50% max spread value (spreads) / 40% combined (straddles)",
            "stop_loss": "30% debit paid (spreads) / 25% combined (straddles)",
            "time_stop_dte": 5,
            "time_stop_dte_straddle": 10,
            "regime_exit": True,
        }
        filters = {
            "spread_pct_max": 0.05,
            "min_open_interest": 500,
            "min_dte": 14,
            "max_dte": 45,
            "market_regime_allowed": ["BULL", "BEAR", "NEUTRAL", "SQUEEZE"],
            "max_concurrent_positions": 4,
            "max_same_direction": 3,
            "daily_loss_circuit_breaker_pct": 0.06,
        }
        success_criteria = {
            "min_resolved_trades": 30,
            "min_expectancy": 0.1,
            "min_win_rate": 0.45,
            "min_sharpe": 0.8,
            "max_drawdown": 0.20,
            "min_profit_factor": 1.3,
        }
        core_indicators = project_meta.get(
            "core_indicators",
            ["SMA50", "SMA200", "RSI14", "BB20", "ADX14"],
        )
        invalidators = ["regime_shift_missed", "risk_budget_exceeded", "circuit_breaker_triggered"]
        exec_mode = "qc_cloud_backtest"
        entry_style = "rule_based_regime"
        holding_secs = 86400 * 7  # ~1 week avg for options
    else:
        entry = {
            "required_conditions": [
                "ML model predicts positive expected value",
                "Confidence above calibrated threshold",
            ],
            "trigger": [],
        }
        exit_rules = {
            "stop_loss": "model-defined or triple-barrier",
            "take_profit": "model-defined or triple-barrier",
            "time_stop_bars": 0,
        }
        filters = {
            "spread_pct_max": 0.07,
            "market_regime_allowed": [],
        }
        success_criteria = {
            "min_resolved_trades": 20,
            "min_expectancy": 0.1,
            "min_win_rate": 0.50,
        }
        core_indicators = ["lightgbm_ensemble", "triple_barrier"]
        invalidators = ["model_degradation", "regime_shift_undetected"]
        exec_mode = "qc_cloud_backtest"
        entry_style = "ml_signal"
        holding_secs = 86400

    return {
        "strategy_id": strategy_id,
        "venue": "quantconnect",
        "family": family,
        "status": status,
        "timeframes": project_meta.get("timeframes", ["1d"]),
        "universe": project_meta.get("universe", []),
        "entry": entry,
        "exit": exit_rules,
        "filters": filters,
        "success_criteria": success_criteria,
        "core_indicators": core_indicators,
        "setup_variants": list(BRAIN_OPTIONS_V1_STRATEGIES.keys()) if is_rule_based else [],
        "summary": project_meta.get("summary", f"QC project {project_id}"),
        "paper_only": True,
        "live_trading_forbidden": True,
        "linked_hypotheses": [],
        "asset_classes": project_meta.get("asset_classes", ["stocks", "options"]),
        "primary_asset_class": project_meta.get("primary_asset_class", "options"),
        "execution_profile": {
            "mode": exec_mode,
            "entry_style": entry_style,
            "supports_live_signal_resolution": False,
            "preferred_holding_seconds": holding_secs,
            "asset_classes": project_meta.get("asset_classes", ["stocks", "options"]),
            "account_type": "cash" if is_rule_based else "margin",
            "buying_only": is_rule_based,
        },
        "invalidators": invalidators,
        # ── QC-specific metadata ──
        "qc_metadata": {
            "project_id": project_id,
            "project_name": project_meta.get("name", ""),
            "backtest_id": backtest_id,
            "backtest_name": backtest_name,
            "patterns": project_meta.get("patterns", []),
            "validated_utc": _now_utc(),
            "is_rule_based": is_rule_based,
        },
        "qc_backtest_metrics": {
            "sharpe_ratio": sharpe,
            "sortino_ratio": _safe_float(metrics.get("sortino_ratio")),
            "win_rate": win_rate,
            "loss_rate": _safe_float(metrics.get("loss_rate")),
            "drawdown": drawdown,
            "net_profit": net_profit,
            "compounding_annual_return": _safe_float(metrics.get("compounding_annual_return")),
            "expectancy": expectancy,
            "total_orders": total_orders,
            "profit_loss_ratio": profit_factor,
            "alpha": alpha,
            "beta": beta,
        },
    }


def merge_qc_strategy(
    spec: Dict[str, Any],
    specs_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Upsert a QC strategy spec into ``strategy_specs.json``.

    If a strategy with the same ``strategy_id`` already exists it is replaced;
    otherwise the new spec is appended.

    Returns a summary dict with ``action`` ("inserted" | "updated") and the
    strategy_id.
    """
    path = Path(specs_path or _SPECS_PATH)
    data = read_json(path, default={"schema_version": "strategy_specs_v1_normalized", "strategies": []})
    strategies: List[Dict] = data.get("strategies", [])
    sid = spec["strategy_id"]

    # Find existing
    idx = None
    for i, s in enumerate(strategies):
        if s.get("strategy_id") == sid:
            idx = i
            break

    if idx is not None:
        strategies[idx] = spec
        action = "updated"
    else:
        strategies.append(spec)
        action = "inserted"

    data["strategies"] = strategies
    data["updated_utc"] = _now_utc()
    write_json(path, data)
    logger.info("merge_qc_strategy: %s strategy_id=%s", action, sid)
    return {"action": action, "strategy_id": sid}


def list_qc_strategies(
    specs_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Return all strategies with ``venue == 'quantconnect'``."""
    path = Path(specs_path or _SPECS_PATH)
    data = read_json(path, default={"strategies": []})
    return [s for s in data.get("strategies", []) if s.get("venue") == "quantconnect"]
