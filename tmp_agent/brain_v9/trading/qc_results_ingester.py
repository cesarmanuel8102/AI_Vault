"""
Brain V9 — trading/qc_results_ingester.py
Phase A: Automatic QC Backtest Results Ingestion

Periodically polls QuantConnect API for new/updated backtests across known
projects, extracts metrics, bridges them into strategy_specs and scorecards.

This closes Gap 1: QC → Brain (automated backtest result flow).

Usage:
    # One-shot (from agent tool or scheduler)
    result = await ingest_qc_results()

    # Background loop (from autonomy manager)
    ingester = QCResultsIngester(interval=1800)
    await ingester.start()
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("QCResultsIngester")

# ── Paths ─────────────────────────────────────────────────────────────────────
_STATE_DIR = BASE_PATH / "tmp_agent" / "state" / "qc_backtests"
_INGESTION_STATE_PATH = _STATE_DIR / "ingestion_state.json"

# ── Known projects to monitor ────────────────────────────────────────────────
# All QC projects that Brain V9 should track for backtest results.
# Add new projects here as they are created.
_MONITORED_PROJECTS: List[Dict[str, Any]] = [
    {"project_id": 29490680, "name": "Brain V9 Options V1", "family": "rule_based_options"},
    # 24654779 (Upgraded Sky Blue Butterfly) REMOVED — 515 ML-ensemble backtests,
    # all yielded 0-trade ghost strategies.  Purged 2026-04-02.
    # 25550271 (Clone of Sleepy Black Buffalo) REMOVED — 0 backtests, inactive.
]


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def ingest_qc_results() -> Dict[str, Any]:
    """
    One-shot ingestion: poll all monitored QC projects for new backtests,
    extract metrics, bridge into strategy_specs, and update scorecards.

    Returns a summary dict with counts of new/updated strategies.
    """
    from brain_v9.trading.connectors import QuantConnectConnector
    from brain_v9.trading.qc_orchestrator import extract_metrics
    from brain_v9.trading.qc_strategy_bridge import (
        backtest_to_strategy_spec,
        merge_qc_strategy,
    )

    _STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Load ingestion state (tracks which backtests we've already processed)
    state = read_json(_INGESTION_STATE_PATH, default={
        "schema_version": "qc_ingestion_state_v1",
        "last_run_utc": None,
        "processed_backtests": {},  # {backtest_id: {project_id, processed_utc, strategy_id}}
    })
    processed = state.get("processed_backtests", {})

    qc = QuantConnectConnector()

    # Verify auth first
    auth = await qc.check_health()
    if not auth.get("success"):
        return {
            "success": False,
            "error": "QC authentication failed",
            "detail": auth.get("response_preview", {}),
        }

    results_summary: List[Dict[str, Any]] = []
    new_count = 0
    updated_count = 0
    errors: List[str] = []

    for proj in _MONITORED_PROJECTS:
        pid = proj["project_id"]
        try:
            # List all backtests for this project
            bt_list = await qc.list_backtests(pid, include_statistics=True)
            if not bt_list.get("success"):
                errors.append(f"project {pid}: list_backtests failed - {bt_list.get('error', 'unknown')}")
                continue

            backtests = bt_list.get("backtests", [])
            log.info("QC ingestion: project %d has %d backtests", pid, len(backtests))

            for bt in backtests:
                bt_id = bt.get("backtestId", "")
                if not bt_id:
                    continue

                # Skip if already processed (unless it wasn't completed before)
                prev = processed.get(bt_id)
                if prev and prev.get("completed"):
                    continue

                # Check if backtest is completed
                if not bt.get("completed", False):
                    continue

                # Read full backtest details
                bt_detail = await qc.read_backtest(pid, bt_id)
                if not bt_detail.get("success"):
                    errors.append(f"backtest {bt_id}: read failed - {bt_detail.get('error', '')}")
                    continue

                # Extract metrics
                metrics = extract_metrics(bt_detail)

                # Bridge to strategy spec
                bt_name = bt.get("name", bt_id[:12])
                spec = backtest_to_strategy_spec(pid, bt_id, metrics, bt_name)

                # Apply pattern enrichment (non-fatal)
                try:
                    from brain_v9.trading.qc_pattern_ingester import apply_patterns_to_spec
                    apply_patterns_to_spec(spec)
                except Exception as e:
                    log.debug("Pattern enrichment skipped: %s", e)

                # Merge into strategy_specs
                merge_result = merge_qc_strategy(spec)
                action = merge_result.get("action", "unknown")

                # Update scorecard for this strategy
                _update_scorecard_from_qc(spec, metrics)

                # Track as processed
                processed[bt_id] = {
                    "project_id": pid,
                    "processed_utc": _now_utc(),
                    "strategy_id": spec["strategy_id"],
                    "completed": True,
                    "action": action,
                }

                if action == "created":
                    new_count += 1
                else:
                    updated_count += 1

                results_summary.append({
                    "project_id": pid,
                    "backtest_id": bt_id,
                    "backtest_name": bt_name,
                    "strategy_id": spec["strategy_id"],
                    "status": spec.get("status", ""),
                    "sharpe": metrics.get("sharpe_ratio"),
                    "win_rate": metrics.get("win_rate"),
                    "drawdown": metrics.get("drawdown"),
                    "total_orders": metrics.get("total_orders"),
                    "action": action,
                })

        except Exception as exc:
            errors.append(f"project {pid}: {exc}")
            log.error("QC ingestion error for project %d: %s", pid, exc)

    # Persist state
    state["last_run_utc"] = _now_utc()
    state["processed_backtests"] = processed
    write_json(_INGESTION_STATE_PATH, state)

    summary_text = (
        f"QC ingestion complete: {new_count} new, {updated_count} updated, "
        f"{len(errors)} errors across {len(_MONITORED_PROJECTS)} projects"
    )
    log.info(summary_text)

    return {
        "success": len(errors) == 0 or (new_count + updated_count) > 0,
        "summary": summary_text,
        "new_strategies": new_count,
        "updated_strategies": updated_count,
        "total_backtests_scanned": sum(1 for r in results_summary),
        "results": results_summary,
        "errors": errors,
    }


def _update_scorecard_from_qc(spec: Dict, metrics: Dict) -> None:
    """
    Create or update a scorecard entry for a QC-bridged strategy.

    QC backtests don't have individual trades in the ledger, so we use
    the aggregate metrics directly to populate the scorecard.
    """
    from brain_v9.trading.strategy_scorecard import read_scorecards, _recompute

    sc_path = BASE_PATH / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
    data = read_scorecards()
    scorecards = data.get("scorecards", {})

    sid = spec["strategy_id"]
    card = scorecards.get(sid, {})

    # Initialize or update
    card["strategy_id"] = sid
    card["family"] = spec.get("family", "unknown")
    card["venue"] = "quantconnect"
    card["status"] = spec.get("status", "qc_backtest_validated")
    card["source"] = "qc_backtest_ingestion"
    card["last_ingested_utc"] = _now_utc()

    # Map QC metrics to scorecard fields
    total_orders = int(metrics.get("total_orders") or 0)
    win_rate = float(metrics.get("win_rate") or 0)
    wins = int(total_orders * win_rate)
    losses = total_orders - wins

    card["entries_taken"] = total_orders
    card["entries_resolved"] = total_orders  # all BT trades are resolved
    card["entries_open"] = 0
    card["wins"] = wins
    card["losses"] = losses
    card["draws"] = 0
    card["win_rate"] = round(win_rate, 4)
    card["expectancy"] = float(metrics.get("expectancy") or 0)
    card["profit_factor"] = float(metrics.get("profit_loss_ratio") or 0)
    card["sharpe_ratio"] = float(metrics.get("sharpe_ratio") or 0)
    card["max_drawdown"] = abs(float(metrics.get("drawdown") or 0))
    card["cagr"] = float(metrics.get("compounding_annual_return") or 0)
    card["alpha"] = float(metrics.get("alpha") or 0)
    card["beta"] = float(metrics.get("beta") or 0)

    # Success criteria from spec (for governance evaluation)
    sc = spec.get("success_criteria", {})
    if sc:
        card["success_criteria"] = sc

    # Recompute governance state
    _recompute(card)

    scorecards[sid] = card
    data["scorecards"] = scorecards
    data["updated_utc"] = _now_utc()
    write_json(sc_path, data)

    log.info(
        "Scorecard updated: %s → governance=%s (trades=%d, WR=%.1f%%, E=%.4f)",
        sid, card.get("governance_state", "?"), total_orders,
        win_rate * 100, card.get("expectancy", 0),
    )


# ── Background Ingester ──────────────────────────────────────────────────────

class QCResultsIngester:
    """Periodic background task that refreshes QC backtest results."""

    DEFAULT_INTERVAL = 1800  # 30 minutes

    def __init__(self, interval: int = DEFAULT_INTERVAL):
        self.interval = interval
        self.running = False
        self._last_result: Optional[Dict[str, Any]] = None
        self._consecutive_failures = 0

    async def start(self) -> None:
        """Run the ingestion loop until stop() is called."""
        self.running = True
        log.info("QCResultsIngester started (interval=%ds)", self.interval)
        while self.running:
            try:
                result = await ingest_qc_results()
                self._last_result = result
                if result.get("success"):
                    self._consecutive_failures = 0
                else:
                    self._consecutive_failures += 1
            except Exception as exc:
                log.error("QCResultsIngester cycle failed: %s", exc)
                self._consecutive_failures += 1

            # Back off if repeated failures (max 2 hours)
            sleep_time = min(
                self.interval * (2 ** min(self._consecutive_failures, 3)),
                7200,
            ) if self._consecutive_failures > 0 else self.interval
            await asyncio.sleep(sleep_time)

    def stop(self) -> None:
        self.running = False
        log.info("QCResultsIngester stopped")

    def get_status(self) -> Dict[str, Any]:
        last = self._last_result or {}
        return {
            "running": self.running,
            "interval_seconds": self.interval,
            "consecutive_failures": self._consecutive_failures,
            "last_run_utc": last.get("summary", "never"),
            "last_new": last.get("new_strategies", 0),
            "last_updated": last.get("updated_strategies", 0),
        }
