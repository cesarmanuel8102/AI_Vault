"""
Brain V9 — trading/qc_iteration_engine.py
QC Strategy Iteration Engine: Closes the QC research loop.

The engine:
1. Reads strategy scorecard + backtest metrics for underperforming strategies
2. Uses LLM to analyze root causes of poor performance
3. Proposes parameter adjustments (or structural changes)
4. Applies adjustments to QC project files via QC API
5. Triggers re-backtest via QC orchestrator
6. Tracks iteration history for learning

This closes Gap: "QC loop is one-shot, not iterative"

Usage:
    # Analyze a single strategy
    analysis = await analyze_strategy_performance("S1_covered_call")

    # Full iteration cycle
    result = await iterate_strategy("S1_covered_call")

    # Scan all underperformers and iterate
    result = await auto_iterate_underperformers()
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("QCIterationEngine")

# ── Paths ─────────────────────────────────────────────────────────────────────
_STATE_DIR = BASE_PATH / "tmp_agent" / "state" / "qc_iterations"
_STATE_DIR.mkdir(parents=True, exist_ok=True)
_ITERATION_HISTORY_PATH = _STATE_DIR / "iteration_history.json"
_SCORECARD_PATH = BASE_PATH / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"

# ── Classification thresholds (from qc_strategy_bridge) ──────────────────────
PERFORMANCE_THRESHOLDS = {
    "min_sharpe": 0.8,
    "min_win_rate": 0.45,
    "max_drawdown": 0.20,
    "min_trades": 30,
    "min_profit_factor": 1.3,
    "min_expectancy": 0.10,
}

# ── Max iterations per strategy before manual review ─────────────────────────
MAX_ITERATIONS = 5
# ── QC project for options strategies ────────────────────────────────────────
OPTIONS_PROJECT_ID = 29490680


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_iteration_history() -> Dict:
    if _ITERATION_HISTORY_PATH.exists():
        return read_json(_ITERATION_HISTORY_PATH)
    return {"iterations": {}, "updated_utc": _now_utc()}


def _save_iteration_history(data: Dict):
    data["updated_utc"] = _now_utc()
    write_json(_ITERATION_HISTORY_PATH, data)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Analyze strategy performance (LLM-powered root cause analysis)
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_strategy_performance(strategy_id: str) -> Dict[str, Any]:
    """
    Analyze a strategy's backtest performance to identify root causes of
    underperformance. Uses LLM for reasoning about metrics.

    Returns:
        Dict with analysis including identified_issues, root_causes,
        suggested_adjustments.
    """
    # Load scorecard
    if not _SCORECARD_PATH.exists():
        return {"success": False, "error": "No scorecards found"}

    sc_data = read_json(_SCORECARD_PATH)
    card = sc_data.get("scorecards", {}).get(strategy_id)
    if not card:
        return {"success": False, "error": f"Strategy {strategy_id} not found in scorecards"}

    # Load strategy spec
    from brain_v9.trading.qc_strategy_bridge import BRAIN_OPTIONS_V1_STRATEGIES
    spec = BRAIN_OPTIONS_V1_STRATEGIES.get(strategy_id, {})

    # Build analysis context
    metrics = {
        "governance_state": card.get("governance_state"),
        "win_rate": card.get("win_rate", 0),
        "expectancy": card.get("expectancy", 0),
        "net_pnl": card.get("net_pnl", 0),
        "profit_factor": card.get("profit_factor", 0),
        "sharpe_ratio": card.get("sharpe_ratio", 0),
        "max_drawdown": card.get("max_drawdown", 0),
        "entries_resolved": card.get("entries_resolved", 0),
        "wins": card.get("wins", 0),
        "losses": card.get("losses", 0),
        "avg_win": card.get("avg_win", 0),
        "avg_loss": card.get("avg_loss", 0),
        "ibkr_net_pnl": card.get("ibkr_net_pnl"),
        "ibkr_unrealized_pnl": card.get("ibkr_unrealized_pnl"),
    }

    thresholds = PERFORMANCE_THRESHOLDS.copy()
    sc_criteria = card.get("success_criteria", {})
    for key in thresholds:
        short_key = key.replace("min_", "").replace("max_", "")
        if short_key in sc_criteria:
            thresholds[key] = sc_criteria[short_key]

    # Identify issues vs thresholds
    issues = []
    if metrics["win_rate"] < thresholds["min_win_rate"]:
        issues.append({
            "metric": "win_rate",
            "value": metrics["win_rate"],
            "threshold": thresholds["min_win_rate"],
            "gap": thresholds["min_win_rate"] - metrics["win_rate"],
            "severity": "high" if metrics["win_rate"] < thresholds["min_win_rate"] * 0.7 else "medium",
        })
    if metrics["expectancy"] < thresholds["min_expectancy"]:
        issues.append({
            "metric": "expectancy",
            "value": metrics["expectancy"],
            "threshold": thresholds["min_expectancy"],
            "gap": thresholds["min_expectancy"] - metrics["expectancy"],
            "severity": "high" if metrics["expectancy"] < 0 else "medium",
        })
    if metrics["sharpe_ratio"] < thresholds["min_sharpe"]:
        issues.append({
            "metric": "sharpe_ratio",
            "value": metrics["sharpe_ratio"],
            "threshold": thresholds["min_sharpe"],
            "gap": thresholds["min_sharpe"] - metrics["sharpe_ratio"],
            "severity": "medium",
        })
    if metrics["max_drawdown"] > thresholds["max_drawdown"]:
        issues.append({
            "metric": "max_drawdown",
            "value": metrics["max_drawdown"],
            "threshold": thresholds["max_drawdown"],
            "gap": metrics["max_drawdown"] - thresholds["max_drawdown"],
            "severity": "high" if metrics["max_drawdown"] > 0.30 else "medium",
        })
    if metrics["profit_factor"] < thresholds["min_profit_factor"]:
        issues.append({
            "metric": "profit_factor",
            "value": metrics["profit_factor"],
            "threshold": thresholds["min_profit_factor"],
            "gap": thresholds["min_profit_factor"] - metrics["profit_factor"],
            "severity": "medium",
        })

    # Generate LLM analysis prompt
    analysis_prompt = _build_analysis_prompt(strategy_id, spec, metrics, issues)

    # Call LLM for root cause analysis
    try:
        llm_analysis = await _call_llm_for_analysis(analysis_prompt)
    except Exception as e:
        log.error("LLM analysis failed for %s: %s", strategy_id, e)
        llm_analysis = {
            "root_causes": [f"LLM analysis unavailable: {e}"],
            "suggested_adjustments": [],
            "confidence": "low",
        }

    result = {
        "success": True,
        "strategy_id": strategy_id,
        "timestamp": _now_utc(),
        "current_metrics": metrics,
        "thresholds": thresholds,
        "issues_found": len(issues),
        "issues": issues,
        "llm_analysis": llm_analysis,
        "strategy_spec_summary": {
            "name": spec.get("name", strategy_id),
            "strategy_type": spec.get("strategy_type"),
            "underlying": spec.get("underlying"),
            "entry_conditions": list(spec.get("entry_conditions", {}).keys()) if spec else [],
        },
    }

    return result


def _build_analysis_prompt(
    strategy_id: str, spec: Dict, metrics: Dict, issues: List[Dict]
) -> str:
    """Build the LLM prompt for root cause analysis."""
    issues_text = "\n".join(
        f"  - {i['metric']}: actual={i['value']:.4f}, target={i['threshold']:.4f}, "
        f"gap={i['gap']:.4f}, severity={i['severity']}"
        for i in issues
    ) or "  Ninguna (todas las métricas dentro de umbrales)"

    spec_text = json.dumps(spec, indent=2, default=str)[:2000] if spec else "No spec available"

    return f"""Analiza la estrategia de trading '{strategy_id}' y sus resultados de backtest.

MÉTRICAS ACTUALES:
  Win Rate: {metrics['win_rate']:.2%}
  Expectancy: {metrics['expectancy']:.4f}
  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}
  Max Drawdown: {metrics['max_drawdown']:.2%}
  Profit Factor: {metrics['profit_factor']:.2f}
  Trades resueltos: {metrics['entries_resolved']}
  Wins: {metrics['wins']}, Losses: {metrics['losses']}
  Avg Win: {metrics['avg_win']:.4f}, Avg Loss: {metrics['avg_loss']:.4f}
  P&L neto: ${metrics['net_pnl']:.2f}

ISSUES VS UMBRALES:
{issues_text}

ESPECIFICACIÓN DE ESTRATEGIA:
{spec_text}

Responde en JSON con esta estructura exacta:
{{
  "root_causes": ["causa 1", "causa 2", ...],
  "suggested_adjustments": [
    {{"parameter": "nombre", "current_value": "X", "suggested_value": "Y", "rationale": "por qué"}},
    ...
  ],
  "structural_recommendation": "none|minor_tweak|major_overhaul|abandon",
  "confidence": "high|medium|low",
  "priority_action": "descripción corta de la acción más impactante"
}}"""


async def _call_llm_for_analysis(prompt: str) -> Dict:
    """Call the LLM (Ollama or Claude) for strategy analysis."""
    try:
        # Try Ollama first (local, free)
        from aiohttp import ClientSession, ClientTimeout
        async with ClientSession(timeout=ClientTimeout(total=60)) as session:
            payload = {
                "model": "llama3.1:8b",
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 2048, "num_ctx": 4096, "temperature": 0.3},
            }
            async with session.post("http://localhost:11434/api/generate", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("response", "")
                    # Extract JSON from response
                    return _extract_json_from_llm(text)
    except Exception as e:
        log.warning("Ollama analysis failed, using rule-based fallback: %s", e)

    # Fallback: rule-based analysis (no LLM needed)
    return _rule_based_analysis(prompt)


def _extract_json_from_llm(text: str) -> Dict:
    """Extract JSON object from LLM response text."""
    import re
    # Try to find JSON block
    patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
        r'(\{[^{}]*"root_causes"[^{}]*\})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    # Try parsing the whole text as JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Return the raw text as a single root cause
    return {
        "root_causes": [text[:500]],
        "suggested_adjustments": [],
        "structural_recommendation": "unknown",
        "confidence": "low",
        "priority_action": "Manual review needed",
    }


def _rule_based_analysis(prompt: str) -> Dict:
    """Fallback rule-based analysis when LLM is unavailable."""
    adjustments = []
    causes = []

    if "win_rate" in prompt and "gap=" in prompt:
        causes.append("Win rate below threshold — entry conditions may be too loose")
        adjustments.append({
            "parameter": "rsi_entry_threshold",
            "current_value": "50",
            "suggested_value": "55",
            "rationale": "Tighter RSI filter to reduce false entries",
        })

    if "max_drawdown" in prompt:
        causes.append("Drawdown exceeds limit — position sizing or stop-loss too wide")
        adjustments.append({
            "parameter": "max_position_pct",
            "current_value": "20%",
            "suggested_value": "15%",
            "rationale": "Smaller positions to reduce drawdown",
        })

    if "expectancy" in prompt and "gap=" in prompt:
        causes.append("Negative or low expectancy — avg loss larger than avg win * win_rate")
        adjustments.append({
            "parameter": "stop_loss_pct",
            "current_value": "varies",
            "suggested_value": "tighter by 20%",
            "rationale": "Reduce average loss to improve expectancy",
        })

    if "sharpe_ratio" in prompt:
        causes.append("Low risk-adjusted returns — high volatility relative to returns")

    if not causes:
        causes.append("No specific issues detected against thresholds")

    return {
        "root_causes": causes,
        "suggested_adjustments": adjustments,
        "structural_recommendation": "minor_tweak" if adjustments else "none",
        "confidence": "medium",
        "priority_action": adjustments[0]["rationale"] if adjustments else "Monitor and collect more data",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Apply parameter adjustments to QC project
# ═══════════════════════════════════════════════════════════════════════════════

async def apply_adjustments_to_qc(
    strategy_id: str,
    adjustments: List[Dict],
    project_id: int = OPTIONS_PROJECT_ID,
) -> Dict[str, Any]:
    """
    Apply parameter adjustments to a QC project file.

    Reads current QC project files, applies adjustments, re-uploads.
    This is the 'hands' of the iteration loop.
    """
    if not adjustments:
        return {"success": True, "message": "No adjustments to apply", "applied": 0}

    try:
        from brain_v9.trading.connectors import QuantConnectConnector
        qc = QuantConnectConnector()

        # Verify health first
        health = await qc.check_health()
        if not health.get("healthy"):
            return {"success": False, "error": "QC API not healthy", "health": health}

        # Read current project files
        # (QC API: GET /projects/{projectId}/files)
        files_result = await qc._api_request("GET", f"projects/{project_id}/files")
        if not files_result.get("success"):
            return {"success": False, "error": f"Cannot read project files: {files_result}"}

        files = files_result.get("files", [])
        main_file = None
        for f in files:
            name = f.get("name", "")
            if name.endswith(".py") and ("main" in name.lower() or "algorithm" in name.lower()):
                main_file = f
                break

        if not main_file:
            # Use first .py file
            for f in files:
                if f.get("name", "").endswith(".py"):
                    main_file = f
                    break

        if not main_file:
            return {"success": False, "error": "No Python files found in project"}

        file_name = main_file["name"]
        file_content = main_file.get("content", "")

        # Apply each adjustment
        applied = []
        modified_content = file_content

        for adj in adjustments:
            param = adj.get("parameter", "")
            new_val = adj.get("suggested_value", "")
            if not param or not new_val:
                continue

            # Simple parameter replacement (looks for assignments)
            import re
            # Pattern: param_name = value (with optional whitespace)
            pattern = rf'({re.escape(param)}\s*=\s*)([^\n#]+)'
            match = re.search(pattern, modified_content)
            if match:
                old_line = match.group(0)
                new_line = f"{match.group(1)}{new_val}"
                modified_content = modified_content.replace(old_line, new_line, 1)
                applied.append({
                    "parameter": param,
                    "old_line": old_line.strip(),
                    "new_line": new_line.strip(),
                })
            else:
                # Parameter not found as direct assignment — add as comment for manual review
                comment = f"\n# BRAIN_V9_ADJUSTMENT: {param} = {new_val}  # {adj.get('rationale', '')}\n"
                modified_content = comment + modified_content
                applied.append({
                    "parameter": param,
                    "action": "added_as_comment",
                    "comment": comment.strip(),
                })

        if not applied:
            return {"success": True, "message": "No adjustments could be applied", "applied": 0}

        # Upload modified file
        update_result = await qc.update_file(project_id, file_name, modified_content)
        if not update_result.get("success"):
            return {"success": False, "error": f"Failed to update file: {update_result}"}

        return {
            "success": True,
            "project_id": project_id,
            "file_name": file_name,
            "adjustments_applied": len(applied),
            "applied": applied,
            "timestamp": _now_utc(),
        }

    except Exception as e:
        log.error("apply_adjustments_to_qc failed: %s", e)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Full iteration cycle
# ═══════════════════════════════════════════════════════════════════════════════

async def iterate_strategy(strategy_id: str) -> Dict[str, Any]:
    """
    Full iteration cycle for one strategy:
    1. Analyze performance
    2. Apply adjustments to QC
    3. Trigger re-backtest
    4. Record iteration in history

    Returns summary of the iteration.
    """
    history = _load_iteration_history()
    strategy_history = history["iterations"].setdefault(strategy_id, [])

    # Check iteration limit
    if len(strategy_history) >= MAX_ITERATIONS:
        return {
            "success": False,
            "error": f"Strategy {strategy_id} has reached max iterations ({MAX_ITERATIONS}). Needs manual review.",
            "iteration_count": len(strategy_history),
        }

    iteration_num = len(strategy_history) + 1
    log.info("Starting iteration #%d for %s", iteration_num, strategy_id)

    # ── Step 1: Analyze ───────────────────────────────────────────────────
    analysis = await analyze_strategy_performance(strategy_id)
    if not analysis.get("success"):
        return {"success": False, "error": f"Analysis failed: {analysis.get('error')}", "phase": "analyze"}

    llm = analysis.get("llm_analysis", {})
    adjustments = llm.get("suggested_adjustments", [])
    recommendation = llm.get("structural_recommendation", "unknown")

    if recommendation == "abandon":
        # Mark strategy as retired
        _retire_strategy(strategy_id, "LLM recommended abandonment")
        iteration_record = {
            "iteration": iteration_num,
            "timestamp": _now_utc(),
            "analysis": analysis,
            "action": "abandoned",
            "adjustments_applied": 0,
            "backtest_triggered": False,
        }
        strategy_history.append(iteration_record)
        _save_iteration_history(history)
        return {
            "success": True,
            "action": "abandoned",
            "reason": "LLM recommended abandonment after analysis",
            "analysis": analysis,
        }

    if not adjustments:
        iteration_record = {
            "iteration": iteration_num,
            "timestamp": _now_utc(),
            "analysis": analysis,
            "action": "no_adjustments",
            "adjustments_applied": 0,
            "backtest_triggered": False,
        }
        strategy_history.append(iteration_record)
        _save_iteration_history(history)
        return {
            "success": True,
            "action": "no_adjustments",
            "reason": "Analysis found no specific parameter adjustments to apply",
            "analysis": analysis,
        }

    # ── Step 2: Apply adjustments ─────────────────────────────────────────
    apply_result = await apply_adjustments_to_qc(strategy_id, adjustments)

    # ── Step 3: Trigger re-backtest ───────────────────────────────────────
    backtest_triggered = False
    backtest_result = {}
    if apply_result.get("success") and apply_result.get("adjustments_applied", 0) > 0:
        try:
            from brain_v9.trading.qc_orchestrator import QCBacktestOrchestrator
            orchestrator = QCBacktestOrchestrator()
            backtest_result = await orchestrator.run_backtest(OPTIONS_PROJECT_ID)
            backtest_triggered = True
        except Exception as e:
            log.error("Re-backtest trigger failed: %s", e)
            backtest_result = {"error": str(e)}

    # ── Step 4: Record iteration ──────────────────────────────────────────
    iteration_record = {
        "iteration": iteration_num,
        "timestamp": _now_utc(),
        "analysis_summary": {
            "issues": len(analysis.get("issues", [])),
            "root_causes": llm.get("root_causes", []),
            "recommendation": recommendation,
            "confidence": llm.get("confidence", "unknown"),
        },
        "adjustments_applied": apply_result.get("adjustments_applied", 0),
        "adjustments_detail": apply_result.get("applied", []),
        "backtest_triggered": backtest_triggered,
        "backtest_result_summary": {
            k: v for k, v in backtest_result.items()
            if k in ("success", "backtest_id", "status", "error")
        } if backtest_result else {},
        "action": "iterated",
    }
    strategy_history.append(iteration_record)
    _save_iteration_history(history)

    log.info(
        "Iteration #%d for %s: %d adjustments, backtest=%s",
        iteration_num, strategy_id, apply_result.get("adjustments_applied", 0), backtest_triggered,
    )

    return {
        "success": True,
        "strategy_id": strategy_id,
        "iteration": iteration_num,
        "action": "iterated",
        "analysis": analysis,
        "adjustments": apply_result,
        "backtest": backtest_result if backtest_triggered else None,
    }


def _retire_strategy(strategy_id: str, reason: str):
    """Mark a strategy as retired in scorecards."""
    if not _SCORECARD_PATH.exists():
        return
    data = read_json(_SCORECARD_PATH)
    card = data.get("scorecards", {}).get(strategy_id)
    if card:
        card["governance_state"] = "retired"
        card["retired_reason"] = reason
        card["retired_utc"] = _now_utc()
        data["updated_utc"] = _now_utc()
        write_json(_SCORECARD_PATH, data)
        log.info("Strategy %s retired: %s", strategy_id, reason)


# ═══════════════════════════════════════════════════════════════════════════════
# Auto-iterate all underperformers
# ═══════════════════════════════════════════════════════════════════════════════

async def auto_iterate_underperformers() -> Dict[str, Any]:
    """
    Scan all strategies for underperformers and run iteration cycle on each.

    Targets strategies in states: paper_probe, paper_active, paper_watch
    that have issues (metrics below thresholds).
    """
    if not _SCORECARD_PATH.exists():
        return {"success": True, "message": "No scorecards", "iterated": 0}

    sc_data = read_json(_SCORECARD_PATH)
    scorecards = sc_data.get("scorecards", {})
    target_states = {"paper_probe", "paper_active", "paper_watch", "frozen"}

    results = []
    for sid, card in scorecards.items():
        gov = card.get("governance_state", "")
        if gov not in target_states:
            continue

        # Check if this strategy has known issues
        resolved = int(card.get("entries_resolved", 0))
        if resolved < 5:
            continue  # Not enough data to analyze

        win_rate = float(card.get("win_rate", 0))
        expectancy = float(card.get("expectancy", 0))
        sharpe = float(card.get("sharpe_ratio", 0))

        needs_iteration = (
            win_rate < PERFORMANCE_THRESHOLDS["min_win_rate"] or
            expectancy < PERFORMANCE_THRESHOLDS["min_expectancy"] or
            sharpe < PERFORMANCE_THRESHOLDS["min_sharpe"]
        )

        if not needs_iteration:
            continue

        try:
            iter_result = await iterate_strategy(sid)
            results.append({
                "strategy_id": sid,
                "success": iter_result.get("success", False),
                "action": iter_result.get("action", "unknown"),
                "iteration": iter_result.get("iteration", 0),
            })
        except Exception as e:
            results.append({
                "strategy_id": sid,
                "success": False,
                "error": str(e),
            })

    return {
        "success": True,
        "timestamp": _now_utc(),
        "strategies_scanned": len(scorecards),
        "strategies_iterated": len(results),
        "results": results,
    }


def get_iteration_history(strategy_id: Optional[str] = None) -> Dict:
    """Read iteration history for one or all strategies."""
    history = _load_iteration_history()
    if strategy_id:
        return {
            "strategy_id": strategy_id,
            "iterations": history.get("iterations", {}).get(strategy_id, []),
            "count": len(history.get("iterations", {}).get(strategy_id, [])),
        }
    return {
        "strategies": {
            sid: len(iters) for sid, iters in history.get("iterations", {}).items()
        },
        "total_iterations": sum(
            len(iters) for iters in history.get("iterations", {}).values()
        ),
    }
