"""
P4-09 — QC Backtest Orchestrator

Full async lifecycle: compile → poll → backtest → poll → extract results.
Handles timeouts, error recovery, and persists state to disk so progress
survives restarts.

Usage (from autonomy layer)::

    from brain_v9.trading.qc_orchestrator import QCBacktestOrchestrator
    orch = QCBacktestOrchestrator()
    result = await orch.run_backtest(project_id=24654779, backtest_name="auto-1")
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

logger = logging.getLogger("QCBacktestOrchestrator")

# ─── Defaults ────────────────────────────────────────────────────────────────
_STATE_DIR = BASE_PATH / "tmp_agent" / "state" / "qc_backtests"
_DEFAULT_COMPILE_TIMEOUT = 120          # seconds
_DEFAULT_COMPILE_POLL_INTERVAL = 5      # seconds
_DEFAULT_BACKTEST_TIMEOUT = 600         # seconds (10 min — QC backtests can run long)
_DEFAULT_BACKTEST_POLL_INTERVAL = 10    # seconds


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_pct(value: str) -> Optional[float]:
    """Parse a QC percentage string like '15.2%' → 0.152.  Returns None on failure."""
    if not value:
        return None
    try:
        cleaned = value.strip().replace("%", "").replace(",", "").replace("$", "")
        return float(cleaned) / 100.0 if "%" in value else float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_float(value: str) -> Optional[float]:
    """Parse a QC numeric string like '1.23' → 1.23.  Returns None on failure."""
    if not value:
        return None
    try:
        cleaned = value.strip().replace(",", "").replace("$", "").replace("%", "")
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def extract_metrics(raw_result: Dict) -> Dict[str, Any]:
    """
    Extract and normalize key metrics from a completed ``read_backtest`` result.

    Returns a flat dict with float values (or None when unparseable) ready for
    the strategy bridge (P4-10).
    """
    m = raw_result.get("metrics", {})
    return {
        "sharpe_ratio": _parse_float(m.get("sharpe_ratio", "")),
        "sortino_ratio": _parse_float(m.get("sortino_ratio", "")),
        "compounding_annual_return": _parse_pct(m.get("compounding_annual_return", "")),
        "drawdown": _parse_pct(m.get("drawdown", "")),
        "net_profit": _parse_pct(m.get("net_profit", "")),
        "win_rate": _parse_pct(m.get("win_rate", "")),
        "loss_rate": _parse_pct(m.get("loss_rate", "")),
        "expectancy": _parse_float(m.get("expectancy", "")),
        "total_orders": int(_parse_float(m.get("total_orders", "")) or 0),
        "profit_loss_ratio": _parse_float(m.get("profit_loss_ratio", "")),
        "alpha": _parse_float(m.get("alpha", "")),
        "beta": _parse_float(m.get("beta", "")),
    }


class QCBacktestOrchestrator:
    """Stateful orchestrator that drives compile → backtest → results via the QC API."""

    def __init__(
        self,
        connector=None,
        state_dir: Optional[Path] = None,
        compile_timeout: int = _DEFAULT_COMPILE_TIMEOUT,
        compile_poll: int = _DEFAULT_COMPILE_POLL_INTERVAL,
        backtest_timeout: int = _DEFAULT_BACKTEST_TIMEOUT,
        backtest_poll: int = _DEFAULT_BACKTEST_POLL_INTERVAL,
    ):
        self._connector = connector          # lazy-init if None
        self.state_dir = Path(state_dir or _STATE_DIR)
        self.compile_timeout = compile_timeout
        self.compile_poll = compile_poll
        self.backtest_timeout = backtest_timeout
        self.backtest_poll = backtest_poll

    # ── Connector access ─────────────────────────────────────────────────────

    def _get_connector(self):
        if self._connector is None:
            from brain_v9.trading.connectors import QuantConnectConnector
            self._connector = QuantConnectConnector()
        return self._connector

    # ── State persistence ────────────────────────────────────────────────────

    def _run_state_path(self, project_id: int) -> Path:
        return self.state_dir / f"run_{project_id}_latest.json"

    def _save_run_state(self, project_id: int, state: Dict) -> None:
        state["updated_utc"] = _now_utc()
        write_json(self._run_state_path(project_id), state)

    def load_run_state(self, project_id: int) -> Dict:
        return read_json(self._run_state_path(project_id), default={})

    # ── Compile phase ────────────────────────────────────────────────────────

    async def compile_and_wait(self, project_id: int) -> Dict:
        """Compile *project_id* and poll until BuildSuccess / BuildError / timeout."""
        conn = self._get_connector()
        state = {
            "project_id": project_id,
            "phase": "compile",
            "started_utc": _now_utc(),
        }

        # 1. Trigger compilation
        compile_resp = await conn.compile_project(project_id)
        if not compile_resp.get("success"):
            state.update(phase="compile_failed", error=compile_resp.get("error", str(compile_resp.get("errors", []))))
            self._save_run_state(project_id, state)
            return {"success": False, "phase": "compile_trigger", **state}

        compile_id = compile_resp["compile_id"]
        state["compile_id"] = compile_id

        # 2. Poll until done
        elapsed = 0
        while elapsed < self.compile_timeout:
            poll = await conn.read_compile(project_id, compile_id)
            if poll.get("build_success"):
                state.update(phase="compile_success")
                self._save_run_state(project_id, state)
                return {"success": True, "compile_id": compile_id, **state}
            if poll.get("build_error"):
                state.update(phase="compile_error", errors=poll.get("errors", []))
                self._save_run_state(project_id, state)
                return {"success": False, "compile_id": compile_id, **state}
            await asyncio.sleep(self.compile_poll)
            elapsed += self.compile_poll

        state.update(phase="compile_timeout")
        self._save_run_state(project_id, state)
        return {"success": False, "compile_id": compile_id, **state}

    # ── Backtest phase ───────────────────────────────────────────────────────

    async def launch_and_wait(
        self,
        project_id: int,
        compile_id: str,
        backtest_name: str = "Brain V9 Backtest",
    ) -> Dict:
        """Create a backtest and poll until completed / error / timeout."""
        conn = self._get_connector()
        state = self.load_run_state(project_id) or {}
        state.update(phase="backtest", backtest_name=backtest_name)

        # 1. Create
        create_resp = await conn.create_backtest(project_id, compile_id, backtest_name)
        if not create_resp.get("success"):
            state.update(phase="backtest_create_failed", error=create_resp.get("error", str(create_resp.get("errors", []))))
            self._save_run_state(project_id, state)
            return {"success": False, **state}

        backtest_id = create_resp["backtest_id"]
        state["backtest_id"] = backtest_id

        # 2. Poll
        elapsed = 0
        while elapsed < self.backtest_timeout:
            poll = await conn.read_backtest(project_id, backtest_id)
            if poll.get("completed"):
                if poll.get("error"):
                    state.update(
                        phase="backtest_runtime_error",
                        error=poll["error"],
                        stacktrace=poll.get("stacktrace", ""),
                    )
                    self._save_run_state(project_id, state)
                    return {"success": False, "backtest_id": backtest_id, **state}
                # Successful completion
                metrics = extract_metrics(poll)
                state.update(
                    phase="backtest_complete",
                    backtest_id=backtest_id,
                    metrics=metrics,
                    statistics=poll.get("statistics", {}),
                    runtime_statistics=poll.get("runtime_statistics", {}),
                )
                self._save_run_state(project_id, state)
                return {"success": True, "backtest_id": backtest_id, "metrics": metrics, **state}

            progress = poll.get("progress", 0)
            state["progress"] = progress
            self._save_run_state(project_id, state)

            await asyncio.sleep(self.backtest_poll)
            elapsed += self.backtest_poll

        state.update(phase="backtest_timeout")
        self._save_run_state(project_id, state)
        return {"success": False, "backtest_id": backtest_id, **state}

    # ── Full lifecycle ───────────────────────────────────────────────────────

    async def run_backtest(
        self,
        project_id: int,
        backtest_name: str = "Brain V9 Backtest",
    ) -> Dict:
        """
        End-to-end: compile → wait → backtest → wait → return extracted metrics.

        This is the main entry point called by the autonomy layer (P4-11).
        """
        logger.info("run_backtest: project=%d name=%s", project_id, backtest_name)

        compile_result = await self.compile_and_wait(project_id)
        if not compile_result.get("success"):
            logger.warning("run_backtest compile failed: %s", compile_result.get("phase"))
            return compile_result

        compile_id = compile_result["compile_id"]
        result = await self.launch_and_wait(project_id, compile_id, backtest_name)
        logger.info("run_backtest finished: phase=%s", result.get("phase"))
        return result
