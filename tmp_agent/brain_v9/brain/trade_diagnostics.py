"""
Brain V9 — Trade Diagnostics
=============================
Scans the paper execution ledger and browser evidence to detect
recurring failure patterns. Produces structured issues that the
AutoSurgeon can turn into code patches.

Runs on every autonomy cycle (~120s) via the fast local model
(llama3.1:8b) for pattern classification, or purely rule-based
when the patterns are unambiguous.
"""
from __future__ import annotations

import json
import logging
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("TradeDiagnostics")

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
DIAGNOSTICS_PATH = STATE_PATH / "trade_diagnostics"
DIAGNOSTICS_PATH.mkdir(parents=True, exist_ok=True)

LEDGER_PATH = ENGINE_PATH / "signal_paper_execution_ledger.json"
ISSUES_PATH = DIAGNOSTICS_PATH / "open_issues.json"
HISTORY_PATH = DIAGNOSTICS_PATH / "issue_history.json"
LAST_SCAN_PATH = DIAGNOSTICS_PATH / "last_scan.json"

# Minimum trades to analyze before generating issues
MIN_TRADES_FOR_ANALYSIS = 2
# How often to scan (seconds) — aligned with autonomy cycle
SCAN_COOLDOWN_SECONDS = 300


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_ledger() -> List[Dict]:
    """Read all trades from the paper execution ledger."""
    data = read_json(LEDGER_PATH, {"entries": []})
    return data.get("entries", [])


def _read_open_issues() -> List[Dict]:
    return read_json(ISSUES_PATH, [])


def _save_open_issues(issues: List[Dict]) -> None:
    write_json(ISSUES_PATH, issues)


def _append_history(entry: Dict) -> None:
    history = read_json(HISTORY_PATH, [])
    history.append(entry)
    # Keep last 200 history entries
    if len(history) > 200:
        history = history[-200:]
    write_json(HISTORY_PATH, history)


def _should_scan() -> bool:
    """Check cooldown to avoid redundant scans."""
    last = read_json(LAST_SCAN_PATH, {})
    last_time = last.get("scanned_utc")
    if not last_time:
        return True
    try:
        last_dt = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
        return elapsed >= SCAN_COOLDOWN_SECONDS
    except Exception:
        return True


def _mark_scanned(result_summary: Dict) -> None:
    write_json(LAST_SCAN_PATH, {
        "scanned_utc": _utc_now(),
        **result_summary,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# DIAGNOSTIC RULES — Pure pattern matching, no LLM needed
# ═══════════════════════════════════════════════════════════════════════════════

def _check_amount_input_failure(trades: List[Dict]) -> Optional[Dict]:
    """Detect: amount_input_found is consistently false."""
    recent = trades[-20:]  # Last 20 trades
    if len(recent) < 2:
        return None

    amount_evidence = []
    for t in recent:
        browser_ev = t.get("browser_evidence", {}) or {}
        evidence = browser_ev.get("evidence", {}) or {}
        found = evidence.get("amount_input_found")
        if found is not None:
            amount_evidence.append(found)

    if not amount_evidence:
        return None

    failure_rate = sum(1 for x in amount_evidence if not x) / len(amount_evidence)

    if failure_rate >= 0.8:  # 80%+ failure rate
        return {
            "issue_id": "DIAG-AMOUNT-INPUT",
            "title": "PO amount input not being set",
            "severity": "critical",
            "category": "browser_bridge",
            "description": (
                f"amount_input_found is false in {failure_rate*100:.0f}% of last "
                f"{len(amount_evidence)} trades. Trades execute at PO default amount ($1) "
                f"instead of the commanded amount. The setTradeAmount() function in "
                f"page_hook.js is failing to locate the amount input element."
            ),
            "affected_file": "C:/AI_VAULT/tmp_agent/ops/pocketoption_bridge_extension/page_hook.js",
            "affected_function": "setTradeAmount",
            "evidence": {
                "failure_rate": round(failure_rate, 3),
                "sample_size": len(amount_evidence),
                "failures": sum(1 for x in amount_evidence if not x),
            },
            "suggested_fix": (
                "Improve DOM selectors in setTradeAmount() to find the PO amount input. "
                "PO uses a custom UI — look for input inside container with 'Trade' text, "
                "or contenteditable elements, or React/Vue controlled inputs. "
                "Also abort the trade if amount cannot be set."
            ),
            "detected_utc": _utc_now(),
        }
    return None


def _check_low_signal_quality(trades: List[Dict]) -> Optional[Dict]:
    """Detect: trades entering with very low signal_score."""
    recent = trades[-20:]
    if len(recent) < 2:
        return None

    low_score_trades = []
    all_scores = []
    for t in recent:
        score = t.get("signal_score")
        if score is not None:
            all_scores.append(float(score))
            if float(score) < 0.30:
                low_score_trades.append({
                    "signal_score": score,
                    "result": t.get("result"),
                    "strategy_id": t.get("strategy_id"),
                })

    if len(all_scores) < 2:
        return None

    low_rate = len(low_score_trades) / len(all_scores)
    avg_score = sum(all_scores) / len(all_scores)

    if low_rate >= 0.5 or avg_score < 0.30:
        return {
            "issue_id": "DIAG-LOW-SIGNAL-SCORE",
            "title": "Trades entering with low signal quality",
            "severity": "high",
            "category": "signal_engine",
            "description": (
                f"{low_rate*100:.0f}% of recent trades have signal_score < 0.30. "
                f"Average signal_score: {avg_score:.3f}. These are noise trades "
                f"with edge indistinguishable from random."
            ),
            "affected_file": "C:/AI_VAULT/tmp_agent/brain_v9/trading/signal_engine.py",
            "affected_function": "evaluate_signal",
            "affected_lines": [906, 907, 908, 909, 910, 911],
            "evidence": {
                "low_rate": round(low_rate, 3),
                "avg_score": round(avg_score, 4),
                "sample_size": len(all_scores),
                "low_score_trades": low_score_trades[:5],
            },
            "suggested_fix": (
                "Add a minimum signal_score gate (>= 0.30) before setting "
                "execution_ready = True in the signal evaluation function."
            ),
            "detected_utc": _utc_now(),
        }
    return None


def _check_timeout_resolution(trades: List[Dict]) -> Optional[Dict]:
    """Detect: trades resolving via timeout_expired (no exit price)."""
    recent = trades[-20:]
    if len(recent) < 2:
        return None

    timeout_trades = [
        t for t in recent
        if t.get("resolution_mode") == "timeout_expired"
    ]

    if len(timeout_trades) < 1:
        return None

    timeout_rate = len(timeout_trades) / len(recent)

    if timeout_rate >= 0.3 or len(timeout_trades) >= 2:
        return {
            "issue_id": "DIAG-TIMEOUT-RESOLUTION",
            "title": "Trades resolving via timeout with no exit price",
            "severity": "high",
            "category": "paper_execution",
            "description": (
                f"{len(timeout_trades)} of last {len(recent)} trades resolved as "
                f"timeout_expired with no exit_price. The feature snapshot was stale "
                f"at binary expiry time, and no fallback price source was used."
            ),
            "affected_file": "C:/AI_VAULT/tmp_agent/brain_v9/trading/paper_execution.py",
            "affected_function": "resolve_pending_paper_trades",
            "affected_lines": list(range(219, 326)),
            "evidence": {
                "timeout_count": len(timeout_trades),
                "total_recent": len(recent),
                "timeout_rate": round(timeout_rate, 3),
            },
            "suggested_fix": (
                "Add a fallback price source using the PO candle buffer "
                "(po_candle_buffer.json) when the feature snapshot is stale at "
                "binary expiry resolution time."
            ),
            "detected_utc": _utc_now(),
        }
    return None


def _check_contradiction_trades(trades: List[Dict]) -> Optional[Dict]:
    """Detect: trades entering with active indicator contradictions."""
    recent = trades[-20:]
    if len(recent) < 2:
        return None

    contradiction_trades = []
    for t in recent:
        reasons = t.get("signal_reasons", []) or []
        reason_str = " ".join(str(r) for r in reasons).lower()
        has_contradiction = any(
            kw in reason_str
            for kw in ["contradicts", "contra_penalty", "penalty"]
        )
        if has_contradiction:
            contradiction_trades.append({
                "strategy_id": t.get("strategy_id"),
                "result": t.get("result"),
                "signal_score": t.get("signal_score"),
                "reasons_preview": reasons[:5],
            })

    if len(contradiction_trades) < 2:
        return None

    contra_rate = len(contradiction_trades) / len(recent)

    if contra_rate >= 0.4:
        return {
            "issue_id": "DIAG-CONTRADICTION-ENTRY",
            "title": "Trades entering with active contradictions",
            "severity": "medium",
            "category": "signal_engine",
            "description": (
                f"{contra_rate*100:.0f}% of recent trades had indicator contradictions "
                f"in their signal_reasons. The contradiction gate is too permissive."
            ),
            "affected_file": "C:/AI_VAULT/tmp_agent/brain_v9/trading/signal_engine.py",
            "affected_function": "evaluate_signal",
            "affected_lines": list(range(889, 905)),
            "evidence": {
                "contra_rate": round(contra_rate, 3),
                "contra_count": len(contradiction_trades),
                "sample_size": len(recent),
                "examples": contradiction_trades[:3],
            },
            "suggested_fix": (
                "Harden the contradiction gate: block trade if any contradiction "
                "exists when signal_score is below 0.40, or if contradictions >= confirmations."
            ),
            "detected_utc": _utc_now(),
        }
    return None


def _check_win_rate_below_breakeven(trades: List[Dict]) -> Optional[Dict]:
    """Detect: overall win rate below breakeven threshold."""
    resolved = [t for t in trades if t.get("resolved") and t.get("result") in ("win", "loss")]
    if len(resolved) < 10:
        return None

    wins = sum(1 for t in resolved if t["result"] == "win")
    wr = wins / len(resolved)

    # At 92% payout, breakeven is 52.1%
    avg_payout = 0.92
    breakeven_wr = 1.0 / (1.0 + avg_payout)

    if wr < breakeven_wr:
        return {
            "issue_id": "DIAG-WIN-RATE-BELOW-BREAKEVEN",
            "title": f"Win rate {wr*100:.1f}% below breakeven {breakeven_wr*100:.1f}%",
            "severity": "critical",
            "category": "strategy_performance",
            "description": (
                f"Win rate is {wr*100:.1f}% across {len(resolved)} resolved trades. "
                f"At {avg_payout*100:.0f}% average payout, breakeven WR is {breakeven_wr*100:.1f}%. "
                f"System is net-losing."
            ),
            "affected_file": "C:/AI_VAULT/tmp_agent/brain_v9/trading/signal_engine.py",
            "evidence": {
                "win_rate": round(wr, 4),
                "wins": wins,
                "losses": len(resolved) - wins,
                "total_resolved": len(resolved),
                "breakeven_wr": round(breakeven_wr, 4),
                "avg_payout": avg_payout,
            },
            "suggested_fix": (
                "Review signal generation logic. Consider: raising signal_score minimum, "
                "adding more confirmation requirements, reducing trade frequency in favor of quality."
            ),
            "detected_utc": _utc_now(),
        }
    return None


def _check_duration_not_set(trades: List[Dict]) -> Optional[Dict]:
    """Detect: duration not being captured in browser evidence."""
    recent = trades[-20:]
    if len(recent) < 2:
        return None

    duration_evidence = []
    for t in recent:
        browser_ev = t.get("browser_evidence", {}) or {}
        evidence = browser_ev.get("evidence", {}) or {}
        captured = evidence.get("duration_captured")
        if captured is not None:
            duration_evidence.append(captured)

    if not duration_evidence:
        return None

    failure_rate = sum(1 for x in duration_evidence if not x) / len(duration_evidence)

    if failure_rate >= 0.8:
        return {
            "issue_id": "DIAG-DURATION-NOT-SET",
            "title": "PO trade duration not being set",
            "severity": "medium",
            "category": "browser_bridge",
            "description": (
                f"duration_captured is false in {failure_rate*100:.0f}% of last "
                f"{len(duration_evidence)} trades. Trades may use PO default duration."
            ),
            "affected_file": "C:/AI_VAULT/tmp_agent/ops/pocketoption_bridge_extension/page_hook.js",
            "affected_function": "setDuration",
            "evidence": {
                "failure_rate": round(failure_rate, 3),
                "sample_size": len(duration_evidence),
            },
            "suggested_fix": (
                "Improve duration selection logic in setDuration(). Check if PO "
                "duration UI has changed or if the selector is stale."
            ),
            "detected_utc": _utc_now(),
        }
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SCAN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

# All diagnostic checks — add new ones here
_DIAGNOSTIC_CHECKS = [
    _check_amount_input_failure,
    _check_low_signal_quality,
    _check_timeout_resolution,
    _check_contradiction_trades,
    _check_win_rate_below_breakeven,
    _check_duration_not_set,
]


def run_diagnostic_scan(force: bool = False) -> Dict[str, Any]:
    """Run all diagnostic checks against the trade ledger.

    Returns a summary of findings. New issues are written to open_issues.json.
    Issues that were previously open and are now resolved are moved to history.
    """
    if not force and not _should_scan():
        return {"status": "cooldown", "scanned": False}

    trades = _read_ledger()
    if len(trades) < MIN_TRADES_FOR_ANALYSIS:
        _mark_scanned({"status": "insufficient_data", "trade_count": len(trades)})
        return {"status": "insufficient_data", "trade_count": len(trades), "scanned": True}

    # Run all checks
    new_findings: List[Dict] = []
    for check_fn in _DIAGNOSTIC_CHECKS:
        try:
            result = check_fn(trades)
            if result:
                new_findings.append(result)
        except Exception as e:
            log.warning("Diagnostic check %s failed: %s", check_fn.__name__, e)

    # Merge with existing open issues
    existing_issues = _read_open_issues()
    existing_ids = {iss["issue_id"] for iss in existing_issues}
    new_ids = {f["issue_id"] for f in new_findings}

    # Issues that were open but are no longer detected → resolved
    resolved = []
    still_open = []
    for iss in existing_issues:
        if iss["issue_id"] not in new_ids:
            iss["resolved_utc"] = _utc_now()
            iss["status"] = "auto_resolved"
            _append_history(iss)
            resolved.append(iss["issue_id"])
        else:
            still_open.append(iss)

    # New issues that weren't previously open
    added = []
    for finding in new_findings:
        if finding["issue_id"] not in existing_ids:
            finding["status"] = "open"
            finding["attempts"] = 0
            finding["last_attempt_utc"] = None
            still_open.append(finding)
            added.append(finding["issue_id"])
        else:
            # Update existing issue with fresh evidence
            for iss in still_open:
                if iss["issue_id"] == finding["issue_id"]:
                    iss["evidence"] = finding["evidence"]
                    iss["detected_utc"] = finding["detected_utc"]
                    break

    _save_open_issues(still_open)

    summary = {
        "status": "scanned",
        "scanned": True,
        "trade_count": len(trades),
        "checks_run": len(_DIAGNOSTIC_CHECKS),
        "open_issues": len(still_open),
        "new_issues": added,
        "resolved_issues": resolved,
        "issue_ids": [iss["issue_id"] for iss in still_open],
    }
    _mark_scanned(summary)
    log.info(
        "Trade diagnostics: %d open issues (%d new, %d resolved)",
        len(still_open), len(added), len(resolved),
    )
    return summary


def get_next_actionable_issue() -> Optional[Dict]:
    """Get the highest-priority open issue that hasn't been attempted recently.

    Returns None if no actionable issues exist.
    Issues are prioritized by severity (critical > high > medium > low)
    and by fewest previous attempts.
    """
    issues = _read_open_issues()
    if not issues:
        return None

    SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    # Filter: don't retry too aggressively
    MAX_ATTEMPTS = 3
    RETRY_COOLDOWN = 3600  # 1 hour between attempts on same issue

    actionable = []
    now = datetime.now(timezone.utc)
    for iss in issues:
        if iss.get("attempts", 0) >= MAX_ATTEMPTS:
            continue
        if iss.get("status") == "fix_promoted":
            continue
        last_attempt = iss.get("last_attempt_utc")
        if last_attempt:
            try:
                last_dt = datetime.fromisoformat(last_attempt.replace("Z", "+00:00"))
                if (now - last_dt).total_seconds() < RETRY_COOLDOWN:
                    continue
            except Exception:
                pass
        actionable.append(iss)

    if not actionable:
        return None

    # Sort by severity (critical first), then by fewest attempts
    actionable.sort(key=lambda x: (
        SEVERITY_ORDER.get(x.get("severity", "low"), 9),
        x.get("attempts", 0),
    ))

    return actionable[0]


def mark_issue_attempted(issue_id: str, result: Dict) -> None:
    """Record that a fix was attempted for an issue."""
    issues = _read_open_issues()
    for iss in issues:
        if iss["issue_id"] == issue_id:
            iss["attempts"] = iss.get("attempts", 0) + 1
            iss["last_attempt_utc"] = _utc_now()
            iss["last_attempt_result"] = {
                "success": result.get("success"),
                "model_used": result.get("model_used"),
                "change_id": result.get("change_id"),
                "error": result.get("error"),
            }
            if result.get("promoted"):
                iss["status"] = "fix_promoted"
            elif result.get("success"):
                iss["status"] = "fix_staged"
            break
    _save_open_issues(issues)


def get_diagnostics_status() -> Dict:
    """Get current diagnostics status for API/dashboard."""
    issues = _read_open_issues()
    last_scan = read_json(LAST_SCAN_PATH, {})
    history = read_json(HISTORY_PATH, [])
    return {
        "open_issues": len(issues),
        "issues": issues,
        "last_scan_utc": last_scan.get("scanned_utc"),
        "last_scan_summary": {
            k: v for k, v in last_scan.items() if k != "scanned_utc"
        },
        "history_count": len(history),
        "recent_history": history[-5:],
    }
