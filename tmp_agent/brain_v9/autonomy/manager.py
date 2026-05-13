"""
Brain Chat V9 — autonomy/manager.py
Sistema de autonomía proactiva.
Extraído de V8.0 líneas 7038-8900.
Corrección principal: eliminados globales, toda la lógica en AutonomyManager.
"""
import asyncio
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain_v9.config import (
    ACTION_COOLDOWN_SECONDS,
    AGENT_EVENTS_LOG_PATH,
    AUTONOMY_CONFIG,
    AUTONOMY_CYCLE_LATEST_PATH,
    CPU_THRESHOLD_PCT,
    DISK_THRESHOLD_PCT,
    LOGS_PATH,
    MEMORY_THRESHOLD_PCT,
    PO_BRIDGE_LATEST_ARTIFACT,
    STATE_PATH,
    STRATEGY_ENGINE_PATH,
)
from brain_v9.brain.utility import write_utility_snapshots
from brain_v9.brain.roadmap_governance import promote_roadmap_if_ready
from brain_v9.brain.meta_improvement import refresh_meta_improvement_status
from brain_v9.brain.post_bl_roadmap import refresh_post_bl_roadmap_status
from brain_v9.brain.control_layer import get_control_layer_status_latest
from brain_v9.brain.meta_governance import get_meta_governance_status_latest
from brain_v9.autonomy.action_executor import execute_action
from brain_v9.autonomy.sample_accumulator_agent import SampleAccumulatorAgent, get_sample_accumulator
from brain_v9.autonomy.platform_accumulators import MultiPlatformAccumulator, get_multi_platform_accumulator
from brain_v9.trading.ibkr_data_ingester import IBKRDataIngester, get_ibkr_data_ingester
from brain_v9.core.state_io import append_ndjson, read_json, read_text, write_json


AUTONOMY_SKIP_STATE_PATH = STATE_PATH / "autonomy_skip_state.json"
AUTONOMY_ACTION_LEDGER_PATH = STATE_PATH / "autonomy_action_ledger.json"
UTILITY_LATEST_PATH = STATE_PATH / "utility_u_latest.json"
EDGE_VALIDATION_LATEST_PATH = STRATEGY_ENGINE_PATH / "edge_validation_latest.json"
RANKING_V2_LATEST_PATH = STRATEGY_ENGINE_PATH / "strategy_ranking_v2_latest.json"
POST_TRADE_ANALYSIS_LATEST_PATH = STRATEGY_ENGINE_PATH / "post_trade_analysis_latest.json"
POST_TRADE_HYPOTHESES_LATEST_PATH = STRATEGY_ENGINE_PATH / "post_trade_hypotheses_latest.json"


class AutonomyManager:
    """
    Orquesta los 3 sistemas de autonomía:
    - AutoDebugger:    revisa logs de errores cada N minutos
    - ProactiveMonitor: verifica servicios y recursos
    - (AutoOptimizer se puede agregar igual)
    """

    MAX_REPORTS = 200  # Cap in-memory reports to prevent unbounded growth

    def __init__(self):
        self.logger   = logging.getLogger("AutonomyManager")
        self._tasks:  List[asyncio.Task] = []
        self._running = False
        self.reports: List[Dict] = []
        self.sample_accumulator: Optional[SampleAccumulatorAgent] = None
        self.multi_platform_accumulator: Optional[MultiPlatformAccumulator] = None
        self.ibkr_ingester: Optional[IBKRDataIngester] = None
        self.cycle_count = 0
        self.last_cycle_utc: Optional[str] = None
        self.current_cycle_stage = "idle"
        self.current_cycle_id: Optional[str] = None
        self._load_cycle_state()

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # ------------------------------------------------------------------
    # P-OP21: Bridge watchdog — detect stale/dead bridge and restart it
    # ------------------------------------------------------------------
    _BRIDGE_MAX_STALE_SECONDS = 90.0  # slightly above FEATURE_MAX_AGE_PO (75s)
    _BRIDGE_PORT = 8765
    _BRIDGE_MODULE = "brain_v9.trading.pocketoption_bridge_server"
    _BRIDGE_CWD = str(STATE_PATH.parent)  # C:\AI_VAULT\tmp_agent

    async def _check_bridge_health(self) -> None:
        """Check PocketOption bridge health via HTTP + file freshness; restart if unhealthy.

        P-OP25 upgrade: Previously only checked file mtime (missed zombied bridge
        that was alive on port but returning 404).  Now does:
        1. HTTP GET to bridge /health endpoint — verifies process is responsive
        2. Checks ``is_fresh`` and ``connected`` from the JSON response
        3. Falls back to file-mtime check if HTTP is unavailable
        4. Logs at INFO every cycle so watchdog activity is always visible

        P-OP28e: Converted from sync urllib to async aiohttp to avoid blocking
        the event loop for up to 5 seconds.
        """
        import aiohttp

        bridge_url = f"http://127.0.0.1:{self._BRIDGE_PORT}/health"

        # --- Attempt HTTP health check first ---
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(bridge_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        self.logger.warning(
                            "[BridgeWatchdog] bridge HTTP error %s — process zombied, restarting",
                            resp.status,
                        )
                        self._restart_bridge("http_error_%s" % resp.status)
                        return
                    body = await resp.json()

            is_fresh = body.get("is_fresh", False)
            connected = body.get("connected", False)
            data_age = body.get("data_age_seconds")
            status = body.get("status", "unknown")

            if is_fresh and connected:
                self.logger.info(
                    "[BridgeWatchdog] bridge OK via HTTP (status=%s, age=%.1fs, connected=%s)",
                    status,
                    data_age if data_age is not None else -1,
                    connected,
                )
                return  # healthy

            # Bridge process is responding but data is stale or disconnected.
            # This means the bridge is HEALTHY — the browser extension is just
            # not sending data (tab closed, etc.). Do NOT restart.
            self.logger.info(
                "[BridgeWatchdog] bridge HTTP up, data stale (status=%s, is_fresh=%s, "
                "connected=%s, age=%s) — extension likely offline, NOT restarting",
                status, is_fresh, connected, data_age,
            )
            return

        except (aiohttp.ClientError, OSError, ValueError, asyncio.TimeoutError):
            # Connection refused / timeout — bridge process likely dead.
            # Fall through to file-based check in case bridge is starting up.
            self.logger.info(
                "[BridgeWatchdog] bridge HTTP unreachable, falling back to file check"
            )

        except Exception as exc:
            self.logger.warning("[BridgeWatchdog] HTTP check unexpected error: %s", exc)

        # --- Fallback: file-based freshness check ---
        try:
            path = PO_BRIDGE_LATEST_ARTIFACT
            if not path.exists():
                self.logger.warning("[BridgeWatchdog] bridge file missing: %s", path)
                self._restart_bridge("file_missing")
                return
            mtime_utc = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            age = (datetime.now(timezone.utc) - mtime_utc).total_seconds()
            if age > self._BRIDGE_MAX_STALE_SECONDS:
                self.logger.warning(
                    "[BridgeWatchdog] bridge data stale (%.1fs > %.1fs), restarting",
                    age,
                    self._BRIDGE_MAX_STALE_SECONDS,
                )
                self._restart_bridge("stale_data")
            else:
                self.logger.info(
                    "[BridgeWatchdog] bridge file fresh (age=%.1fs) but HTTP unreachable — monitoring",
                    age,
                )
        except Exception as exc:
            self.logger.error("[BridgeWatchdog] health check failed: %s", exc)

    def _restart_bridge(self, reason: str = "unknown") -> None:
        """Kill any existing bridge process on port 8765 and spawn a new one."""
        try:
            # --- find and kill existing bridge ---
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            killed_pid: Optional[int] = None
            for line in result.stdout.splitlines():
                if ":%d" % self._BRIDGE_PORT in line and "LISTENING" in line:
                    parts = line.split()
                    pid = int(parts[-1])
                    self.logger.info("[BridgeWatchdog] killing bridge PID %d (reason=%s)", pid, reason)
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/F"],
                        capture_output=True,
                        timeout=10,
                    )
                    killed_pid = pid
                    break

            # --- start new bridge ---
            python_exe = sys.executable
            bridge_log = os.path.join(self._BRIDGE_CWD, "brain_v9", "trading", "pocketoption_bridge.stderr.log")
            stderr_file = open(bridge_log, "a", encoding="utf-8")
            proc = subprocess.Popen(
                [python_exe, "-u", "-m", self._BRIDGE_MODULE],
                cwd=self._BRIDGE_CWD,
                stdout=subprocess.DEVNULL,
                stderr=stderr_file,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.logger.info(
                "[BridgeWatchdog] bridge restarted (new PID %d, killed PID %s, reason=%s)",
                proc.pid,
                killed_pid,
                reason,
            )
        except Exception as exc:
            self.logger.error("[BridgeWatchdog] restart failed: %s", exc)

    # ------------------------------------------------------------------
    # P-OP25: Accumulator capacity check — warn before silent stop
    # ------------------------------------------------------------------
    def _check_accumulator_capacity(self) -> None:
        """Log accumulator trade count and warn if near/at session limit."""
        try:
            acc = self.sample_accumulator
            if acc is None:
                return
            count = getattr(acc, "session_trades_count", 0)
            limit = getattr(acc, "MAX_TRADES_PER_SESSION", 1000)
            pct = (100.0 * count / limit) if limit > 0 else 0.0

            if count >= limit:
                self.logger.warning(
                    "[AccumulatorWatch] SATURATED — %d/%d trades (100%%). "
                    "Trading is STOPPED until restart or new day.",
                    count, limit,
                )
            elif pct >= 90:
                self.logger.warning(
                    "[AccumulatorWatch] Near limit — %d/%d trades (%.0f%%)",
                    count, limit, pct,
                )
            else:
                self.logger.info(
                    "[AccumulatorWatch] capacity OK — %d/%d trades (%.0f%%)",
                    count, limit, pct,
                )
        except Exception as exc:
            self.logger.warning("[AccumulatorWatch] check failed: %s", exc)

    def _load_cycle_state(self) -> None:
        payload = read_json(AUTONOMY_CYCLE_LATEST_PATH, {})
        if not isinstance(payload, dict):
            return
        self.cycle_count = int(payload.get("cycle_count", 0) or 0)
        self.last_cycle_utc = payload.get("completed_utc") or payload.get("last_cycle_utc")
        self.current_cycle_stage = str(payload.get("current_stage", "idle") or "idle")
        self.current_cycle_id = payload.get("cycle_id")

    def _read_state_dict(self, path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = read_json(path, default or {})
        return data if isinstance(data, dict) else (default or {})

    def _collect_cycle_metrics(self) -> Dict[str, Any]:
        utility = self._read_state_dict(UTILITY_LATEST_PATH)
        edge = self._read_state_dict(EDGE_VALIDATION_LATEST_PATH)
        ranking = self._read_state_dict(RANKING_V2_LATEST_PATH)
        skips = self._read_state_dict(AUTONOMY_SKIP_STATE_PATH)
        post_trade = self._read_state_dict(POST_TRADE_ANALYSIS_LATEST_PATH)
        hypotheses = self._read_state_dict(POST_TRADE_HYPOTHESES_LATEST_PATH)
        ledger = self._read_state_dict(AUTONOMY_ACTION_LEDGER_PATH)
        summary = edge.get("summary", {}) if isinstance(edge.get("summary"), dict) else {}
        ranking_summary = ranking.get("summary", {}) if isinstance(ranking.get("summary"), dict) else {}
        post_summary = post_trade.get("summary", {}) if isinstance(post_trade.get("summary"), dict) else {}
        hypotheses_summary = hypotheses.get("summary", {}) if isinstance(hypotheses.get("summary"), dict) else {}
        return {
            "u_score": utility.get("u_score", utility.get("u_proxy_score")),
            "governance_u_score": utility.get("governance_u_score"),
            "real_venue_u_score": utility.get("real_venue_u_score"),
            "utility_verdict": utility.get("verdict"),
            "consecutive_skips": skips.get("consecutive_skips", 0),
            "validated_count": summary.get("validated_count", 0),
            "promotable_count": summary.get("promotable_count", 0),
            "probation_count": summary.get("probation_count", 0),
            "blocked_count": summary.get("blocked_count", 0),
            "refuted_count": summary.get("refuted_count", 0),
            "top_strategy_id": ranking_summary.get("top_strategy_id"),
            "top_action": ranking_summary.get("top_action"),
            "exploit_candidate_id": ranking_summary.get("exploit_candidate_id"),
            "probation_candidate_id": ranking_summary.get("probation_candidate_id"),
            "recent_trade_count": post_summary.get("recent_trades_count", 0),
            "recent_hypothesis_count": hypotheses_summary.get("hypotheses_count", 0),
            "pending_actions": len(ledger.get("items", [])) if isinstance(ledger.get("items"), list) else 0,
        }

    def _collect_detect_evidence(self) -> Dict[str, Any]:
        edge = self._read_state_dict(EDGE_VALIDATION_LATEST_PATH)
        ranking = self._read_state_dict(RANKING_V2_LATEST_PATH)
        utility = self._read_state_dict(UTILITY_LATEST_PATH)
        skips = self._read_state_dict(AUTONOMY_SKIP_STATE_PATH)
        return {
            "utility_verdict": utility.get("verdict"),
            "utility_blockers": utility.get("blockers", []),
            "consecutive_skips": skips.get("consecutive_skips", 0),
            "edge_summary": edge.get("summary", {}),
            "ranking_summary": ranking.get("summary", {}),
        }

    def _build_cycle_snapshot(self, gate: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
        next_actions = gate.get("required_next_actions", [])
        normalized_actions = [
            raw.get("action", "unknown") if isinstance(raw, dict) else str(raw)
            for raw in next_actions
        ]
        meta = gate.get("meta_governance") or {}
        cycle_id = f"autocycle_{self.cycle_count + 1:06d}"
        payload = {
            "schema_version": "autonomy_cycle_v1",
            "cycle_id": cycle_id,
            "cycle_count": self.cycle_count + 1,
            "started_utc": self._now_utc(),
            "last_cycle_utc": self.last_cycle_utc,
            "current_stage": "detect",
            "stages": {
                "detect": "done",
                "plan": "done",
                "execute": "pending",
                "verify": "pending",
                "evaluate": "pending",
                "improve": "pending",
                "log": "pending",
            },
            "detect": self._collect_detect_evidence(),
            "plan": {
                "required_next_actions": normalized_actions,
                "top_action": gate.get("top_action"),
                "allow_promote": gate.get("allow_promote"),
                "verdict": gate.get("verdict"),
                "blockers": gate.get("blockers", []),
                "u_score": snapshot.get("u_proxy_score"),
                "current_focus": meta.get("current_focus", {}),
                "allocator": meta.get("allocator", {}),
            },
            "execution": {
                "actions_selected": [],
                "actions_results": [],
            },
            "metrics_before": self._collect_cycle_metrics(),
            "metrics_after": {},
            "room_id": "runtime_global",
            "result": "pending",
        }
        self.current_cycle_id = cycle_id
        self.current_cycle_stage = "plan"
        return payload

    def _persist_cycle_snapshot(self, payload: Dict[str, Any]) -> None:
        write_json(AUTONOMY_CYCLE_LATEST_PATH, payload)

    def _append_agent_event(self, entry: Dict[str, Any]) -> None:
        append_ndjson(AGENT_EVENTS_LOG_PATH, entry, ensure_ascii=False)

    def _finalize_cycle_snapshot(
        self,
        cycle: Dict[str, Any],
        *,
        actions_results: List[Dict[str, Any]],
        result: str,
    ) -> Dict[str, Any]:
        metrics_after = self._collect_cycle_metrics()
        cycle["execution"]["actions_results"] = actions_results
        cycle["metrics_after"] = metrics_after
        cycle["result"] = result
        cycle["completed_utc"] = self._now_utc()
        cycle["current_stage"] = "done"
        cycle["last_cycle_utc"] = cycle["completed_utc"]
        cycle["stages"]["execute"] = "done"
        cycle["stages"]["verify"] = "done"
        cycle["stages"]["evaluate"] = "done"
        cycle["stages"]["improve"] = "done"
        cycle["stages"]["log"] = "done"
        self.cycle_count = int(cycle.get("cycle_count", self.cycle_count))
        self.last_cycle_utc = cycle["completed_utc"]
        self.current_cycle_stage = "idle"
        self._persist_cycle_snapshot(cycle)
        self._append_agent_event({
            "event": "autonomy_cycle_completed",
            "room_id": cycle.get("room_id", "runtime_global"),
            "action": "utility_loop_cycle",
            "result": result,
            "files_changed": [str(AUTONOMY_CYCLE_LATEST_PATH)],
            "metrics_before": cycle.get("metrics_before", {}),
            "metrics_after": metrics_after,
            "timestamp": cycle["completed_utc"],
            "cycle_id": cycle.get("cycle_id"),
            "actions": [row.get("action") for row in actions_results],
        })
        return cycle

    def _add_report(self, report: Dict) -> None:
        """Append a report, pruning oldest if over MAX_REPORTS."""
        self.reports.append(report)
        if len(self.reports) > self.MAX_REPORTS:
            self.reports = self.reports[-self.MAX_REPORTS:]

    # ── Ciclo de vida ─────────────────────────────────────────────────────────
    async def start(self):
        if self._running:
            return
        self._running = True
        if AUTONOMY_CONFIG["auto_debugging_enabled"]:
            self._tasks.append(asyncio.create_task(self._debug_loop()))
        if AUTONOMY_CONFIG["proactive_monitoring_enabled"]:
            self._tasks.append(asyncio.create_task(self._monitor_loop()))
        if AUTONOMY_CONFIG["utility_loop_enabled"]:
            self._tasks.append(asyncio.create_task(self._utility_loop()))
        # Auto-Surgeon: periodic self-healing loop
        self._tasks.append(asyncio.create_task(self._surgeon_loop()))
        # Iniciar SampleAccumulatorAgent para acumulación automática de muestras
        self.sample_accumulator = get_sample_accumulator()
        self._tasks.append(asyncio.create_task(self.sample_accumulator.start()))
        # P7-03: Start IBKR real-time data ingester (skip if IBKR via QC Cloud)
        from brain_v9.config import IBKR_VIA_QC_CLOUD
        if IBKR_VIA_QC_CLOUD:
            self.ibkr_ingester = None
            self.logger.info("IBKR ingester SKIPPED — IBKR_VIA_QC_CLOUD=True (monitoring via QC Live API)")
        else:
            self.ibkr_ingester = get_ibkr_data_ingester()
            self._tasks.append(asyncio.create_task(self.ibkr_ingester.start()))
        # 9X-fix: Start per-platform accumulators so they report running=true
        self.multi_platform_accumulator = get_multi_platform_accumulator()
        self._tasks.append(asyncio.create_task(self.multi_platform_accumulator.start_all()))
        self.logger.info("AutonomyManager iniciado (%d tareas + SampleAccumulator + IBKRIngester + PlatformAccumulators)", len(self._tasks))

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        if self.sample_accumulator:
            self.sample_accumulator.stop()
        if self.ibkr_ingester:
            self.ibkr_ingester.stop()
        if self.multi_platform_accumulator:
            self.multi_platform_accumulator.stop_all()
        self.logger.info("AutonomyManager detenido")

    def get_sample_accumulator_status(self) -> Optional[Dict]:
        """Retorna el estado del SampleAccumulatorAgent."""
        if self.sample_accumulator:
            return self.sample_accumulator.get_status()
        return None

    def get_ibkr_ingester_status(self) -> Optional[Dict]:
        """Retorna el estado del IBKRDataIngester."""
        if self.ibkr_ingester:
            return self.ibkr_ingester.get_status()
        return None

    def get_status(self) -> Dict:
        """Retorna el estado actual del AutonomyManager."""
        control = get_control_layer_status_latest()
        meta = get_meta_governance_status_latest()
        return {
            "running": self._running,
            "active_tasks": len(self._tasks),
            "reports_count": len(self.reports),
            "cycle_count": self.cycle_count,
            "last_cycle_utc": self.last_cycle_utc,
            "current_cycle_stage": self.current_cycle_stage,
            "current_cycle_id": self.current_cycle_id,
            "control_layer_mode": control.get("mode", "ACTIVE"),
            "current_focus": (meta.get("current_focus") or {}).get("action"),
            "top_priority": ((meta.get("top_priority") or {}).get("action")),
            "ibkr_ingester": self.get_ibkr_ingester_status(),
        }

    def get_cycle_snapshot(self) -> Dict[str, Any]:
        control = get_control_layer_status_latest()
        meta = get_meta_governance_status_latest()
        payload = self._read_state_dict(AUTONOMY_CYCLE_LATEST_PATH)
        if payload:
            payload.setdefault("control_layer", {
                "mode": control.get("mode", "ACTIVE"),
                "reason": control.get("reason", "unknown"),
                "execution_allowed": control.get("execution_allowed", True),
            })
            payload.setdefault("meta_governance", {
                "top_action": meta.get("top_action"),
                "current_focus": meta.get("current_focus", {}),
                "allocator": meta.get("allocator", {}),
            })
            return payload
        return {
            "schema_version": "autonomy_cycle_v1",
            "cycle_count": self.cycle_count,
            "last_cycle_utc": self.last_cycle_utc,
            "current_stage": self.current_cycle_stage,
            "cycle_id": self.current_cycle_id,
            "room_id": "runtime_global",
            "result": "idle",
            "control_layer": {
                "mode": control.get("mode", "ACTIVE"),
                "reason": control.get("reason", "unknown"),
                "execution_allowed": control.get("execution_allowed", True),
            },
            "meta_governance": {
                "top_action": meta.get("top_action"),
                "current_focus": meta.get("current_focus", {}),
                "allocator": meta.get("allocator", {}),
            },
        }

    def get_recent_reports(self, limit: int = 20) -> List[Dict]:
        """Retorna los reportes más recientes."""
        return self.reports[-limit:] if self.reports else []

    def clear_reports(self) -> None:
        """Limpia todos los reportes."""
        self.reports.clear()

    # ── Auto-Surgeon loop ─────────────────────────────────────────────────────
    async def _surgeon_loop(self):
        """Periodic autonomous code-healing cycle (every 15 min)."""
        interval = 900  # 15 minutes
        self.logger.info("Surgeon loop: auto-healing cycle cada %ds", interval)
        # initial delay — let other subsystems stabilise first
        await asyncio.sleep(120)
        while self._running:
            try:
                result = await execute_action("auto_surgeon_cycle")
                status = result.get("status", result.get("success", "unknown"))
                self.logger.info("SurgeonLoop: result=%s", status)
            except Exception as e:
                self.logger.error("SurgeonLoop error: %s", e)
            await asyncio.sleep(interval)

    # ── Debug loop ────────────────────────────────────────────────────────────
    async def _debug_loop(self):
        interval = AUTONOMY_CONFIG["check_interval_debugger"]
        self.logger.info("Debug loop: revisará logs cada %ds", interval)
        while self._running:
            try:
                report = await self._scan_error_logs()
                if report["errors_found"] > 0:
                    self._add_report(report)
                    self.logger.warning("AutoDebugger: %d errores encontrados", report["errors_found"])
            except Exception as e:
                self.logger.error("Error en debug loop: %s", e)
            await asyncio.sleep(interval)

    async def _scan_error_logs(self) -> Dict:
        """Escanea logs buscando líneas ERROR."""
        errors: List[str] = []
        try:
            for lf in LOGS_PATH.glob("*.log"):
                for line in read_text(lf, "").splitlines():
                    if "ERROR" in line or "CRITICAL" in line:
                        errors.append(f"{lf.name}: {line.strip()[:120]}")
        except Exception as e:
            self.logger.error("Error escaneando logs: %s", e)
        return {
            "timestamp":    datetime.now().isoformat(),
            "type":         "debug_scan",
            "errors_found": len(errors),
            "errors":       errors[-20:],   # últimos 20
        }

    # ── Monitor loop ──────────────────────────────────────────────────────────
    async def _monitor_loop(self):
        interval = AUTONOMY_CONFIG["check_interval_monitor"]
        self.logger.info("Monitor loop: revisará servicios cada %ds", interval)
        while self._running:
            try:
                report = await self._check_resources()
                if report.get("alerts"):
                    self._add_report(report)
                    for alert in report["alerts"]:
                        self.logger.warning("ProactiveMonitor: %s", alert)
            except Exception as e:
                self.logger.error("Error en monitor loop: %s", e)
            await asyncio.sleep(interval)

    async def _check_resources(self) -> Dict:
        alerts = []
        try:
            import psutil
            # P-OP28e: cpu_percent(interval=1) blocks for 1 second.
            # Run in thread executor to avoid stalling the event loop.
            loop = asyncio.get_running_loop()
            cpu = await loop.run_in_executor(None, psutil.cpu_percent, 1)
            mem = psutil.virtual_memory().percent
            dsk = psutil.disk_usage("/").percent
            if cpu > CPU_THRESHOLD_PCT:
                alerts.append(f"CPU alta: {cpu}%")
            if mem > MEMORY_THRESHOLD_PCT:
                alerts.append(f"Memoria alta: {mem}%")
            if dsk > DISK_THRESHOLD_PCT:
                alerts.append(f"Disco alto: {dsk}%")
            return {
                "timestamp": datetime.now().isoformat(),
                "type":      "resource_check",
                "cpu":       cpu, "memory": mem, "disk": dsk,
                "alerts":    alerts,
            }
        except ImportError:
            return {"type": "resource_check", "alerts": [], "note": "psutil no disponible"}
        except Exception as e:
            return {"type": "resource_check", "alerts": [str(e)]}

    # ── Utility loop ──────────────────────────────────────────────────────────

    # P4-14: Actions classified by lane for multi-action dispatch.
    # Trading actions touch strategy engine / paper execution (venue-bound).
    # Non-trading actions are governance / meta-improvement (no venue state).
    _TRADING_ACTIONS = frozenset({
        "increase_resolved_sample",
        "improve_signal_capture_and_context_window",
        "improve_expectancy_or_reduce_penalties",
        "select_and_compare_strategies",
        "reduce_drawdown_and_capital_at_risk",
        "rebalance_capital_exposure",
        "run_qc_backtest_validation",
        "break_system_deadlock",
    })
    _NON_TRADING_ACTIONS = frozenset({
        "advance_meta_improvement_roadmap",
        "synthesize_chat_product_contract",
        "improve_chat_product_quality",
        "synthesize_utility_governance_contract",
        "auto_surgeon_cycle",
    })

    async def _utility_loop(self):
        interval = AUTONOMY_CONFIG["check_interval_utility"]
        self.logger.info("Utility loop: recalculará U cada %ds", interval)
        _cycle_count = 0
        while self._running:
            _cycle_count += 1
            _cycle_start = time.time()
            self.logger.info("UtilityLoop: cycle #%d START", _cycle_count)
            cycle_snapshot: Optional[Dict[str, Any]] = None
            try:
                # P-OP21: check bridge health before every cycle
                await self._check_bridge_health()
                self.logger.debug("UtilityLoop: bridge_health done (%.1fs)", time.time() - _cycle_start)

                # P-OP25: check accumulator capacity
                self._check_accumulator_capacity()

                result = write_utility_snapshots()
                snapshot = result["snapshot"]
                gate = dict(result["gate"])
                gate["required_next_actions"] = result.get("next_actions", {}).get(
                    "recommended_actions",
                    gate.get("required_next_actions", []),
                )
                gate["top_action"] = result.get("next_actions", {}).get("top_action")
                gate["meta_governance"] = result.get("meta_governance", {})
                cycle_snapshot = self._build_cycle_snapshot(gate, snapshot)
                self._persist_cycle_snapshot(cycle_snapshot)
                report = {
                    "timestamp": snapshot.get("updated_utc"),
                    "type": "utility_refresh",
                    "u_score": snapshot.get("u_proxy_score"),
                    "verdict": gate.get("verdict"),
                    "allow_promote": gate.get("allow_promote"),
                    "blockers": gate.get("blockers", []),
                    "next_actions": gate.get("required_next_actions", []),
                    "top_action": gate.get("top_action"),
                    "focus": ((gate.get("meta_governance") or {}).get("current_focus") or {}).get("action"),
                }
                self._add_report(report)
                self.logger.info("UtilityLoop: U=%s verdict=%s blockers=%s",
                    snapshot.get("u_proxy_score"),
                    gate.get("verdict"),
                    gate.get("blockers", [])
                )
                
                # --- P4-14: Multi-action dispatch across lanes ---
                # Ejecutar acciones si no hay cooldown.
                # NOTA: No gatear por allow_promote — el sistema necesita ejecutar
                # trades (increase_resolved_sample) para mejorar U, aunque U sea negativo.
                # Si sólo se permitiera cuando allow_promote=True, sería un deadlock.
                action_results = await self._dispatch_actions(gate, snapshot, cycle_snapshot)
                self._finalize_cycle_snapshot(
                    cycle_snapshot,
                    actions_results=action_results,
                    result="success",
                )
            except Exception as e:
                self.logger.error("Error en utility loop: %s", e)
                if cycle_snapshot is not None:
                    self._finalize_cycle_snapshot(
                        cycle_snapshot,
                        actions_results=[],
                        result="failure",
                    )
            self.logger.info("UtilityLoop: cycle #%d DONE (%.1fs), sleeping %ds", _cycle_count, time.time() - _cycle_start, interval)
            await asyncio.sleep(interval)

    async def _dispatch_actions(
        self,
        gate: Dict,
        snapshot: Dict,
        cycle_snapshot: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Dispatch up to 2 concurrent actions — one per lane — from the
        ``required_next_actions`` list.

        **Lanes** (P4-14):
        * ``trading`` — actions that touch strategy engine, paper execution,
          or venue state.  Only one trading action at a time.
        * ``non_trading`` — governance / meta-improvement actions that have no
          venue state dependency.  Can run concurrently with a trading action.

        Each lane respects the per-action cooldown already implemented in
        ``execute_action`` (``_cooldown_active``).  The manager-level cooldown
        is now **per-lane** rather than a single global 300 s gate.
        """
        next_actions = gate.get("required_next_actions", [])
        # P-OP15: When utility gate empties next_actions (because real-venue U is
        # positive and no blockers remain), but the strategy engine has a probation
        # candidate with execution_ready_now=True, we must still execute to collect
        # the samples that the probation process requires.  Without this, the system
        # enters an infinite skip loop (212+ consecutive skips observed).
        if not next_actions:
            try:
                from brain_v9.trading.strategy_engine import read_ranking_v2
                _ranking = read_ranking_v2()
                prob_candidate = _ranking.get("probation_candidate")
                if prob_candidate and prob_candidate.get("execution_ready_now") and prob_candidate.get("probation_budget", 0) > 0:
                    next_actions = ["increase_resolved_sample"]
                    gate["required_next_actions"] = next_actions
                    self.logger.info("[P-OP15] Injected increase_resolved_sample: probation candidate %s ready with budget %d",
                                     prob_candidate.get("strategy_id"), prob_candidate.get("probation_budget", 0))
            except Exception as exc:
                self.logger.debug("[P-OP15] Could not check probation candidate: %s", exc)
        if not next_actions:
            if cycle_snapshot is not None:
                cycle_snapshot["current_stage"] = "log"
                cycle_snapshot["stages"]["execute"] = "done"
            return []

        control = get_control_layer_status_latest()
        if control.get("mode") == "FROZEN":
            if cycle_snapshot is not None:
                cycle_snapshot["current_stage"] = "log"
                cycle_snapshot["stages"]["execute"] = "blocked"
                cycle_snapshot["execution"]["actions_selected"] = []
                cycle_snapshot["execution"]["blocked_by_control_layer"] = {
                    "mode": control.get("mode"),
                    "reason": control.get("reason"),
                }
                cycle_snapshot["control_layer"] = {
                    "mode": control.get("mode", "FROZEN"),
                    "reason": control.get("reason", "unknown"),
                    "execution_allowed": control.get("execution_allowed", False),
                }
                self._persist_cycle_snapshot(cycle_snapshot)
            self.logger.warning(
                "ControlLayer: dispatch bloqueado por kill switch (reason=%s)",
                control.get("reason"),
            )
            return [{
                "lane": "control_layer",
                "action": "kill_switch",
                "status": "blocked_control_layer",
                "result": {
                    "status": "blocked_control_layer",
                    "mode": control.get("mode"),
                    "reason": control.get("reason"),
                },
            }]

        # Normalize raw actions to strings
        action_names = []
        for raw in next_actions:
            name = raw.get("action", "unknown") if isinstance(raw, dict) else str(raw)
            action_names.append(name)

        # P-OP27: Prioritize increase_resolved_sample when sample_not_ready
        # blocker is active.  Without trades there is no data to tune
        # expectancy — the system was stuck running
        # improve_expectancy_or_reduce_penalties on every cycle because
        # sorted() placed it alphabetically before increase_resolved_sample.
        blockers = gate.get("blockers", [])
        if "sample_not_ready" in blockers and "increase_resolved_sample" in action_names:
            action_names = ["increase_resolved_sample"] + [
                a for a in action_names if a != "increase_resolved_sample"
            ]

        # Pick one action per lane
        selected_trading: str | None = None
        selected_non_trading: str | None = None

        trading_cooldown = self._lane_cooldown_active("trading")
        non_trading_cooldown = self._lane_cooldown_active("non_trading")
        self.logger.info(
            "DispatchSelect: action_names=%s trading_cooldown=%s non_trading_cooldown=%s",
            action_names, trading_cooldown, non_trading_cooldown,
        )

        for name in action_names:
            if selected_trading is None and name in self._TRADING_ACTIONS:
                if not trading_cooldown:
                    selected_trading = name
                else:
                    self.logger.info("DispatchSelect: skipping %s due to trading cooldown", name)
            elif selected_non_trading is None and name in self._NON_TRADING_ACTIONS:
                if not non_trading_cooldown:
                    selected_non_trading = name
            # If both lanes filled, stop searching
            if selected_trading and selected_non_trading:
                break

        # Fall-through: if action is in neither set, treat it as trading
        if selected_trading is None:
            for name in action_names:
                if name not in self._NON_TRADING_ACTIONS and name not in self._TRADING_ACTIONS:
                    if not self._lane_cooldown_active("trading"):
                        selected_trading = name
                        break

        tasks = []
        lanes_dispatched = []
        if selected_trading:
            tasks.append(self._run_action(selected_trading, "trading", snapshot, cycle_snapshot))
            lanes_dispatched.append(("trading", selected_trading))
        if selected_non_trading:
            tasks.append(self._run_action(selected_non_trading, "non_trading", snapshot, cycle_snapshot))
            lanes_dispatched.append(("non_trading", selected_non_trading))

        self.logger.info(
            "DispatchResult: selected_trading=%s selected_non_trading=%s tasks=%d",
            selected_trading, selected_non_trading, len(tasks),
        )

        if not tasks:
            return []

        if cycle_snapshot is not None:
            cycle_snapshot["current_stage"] = "execute"
            cycle_snapshot["stages"]["execute"] = "in_progress"
            cycle_snapshot["execution"]["actions_selected"] = [
                {"lane": lane, "action": action_name} for lane, action_name in lanes_dispatched
            ]
            self._persist_cycle_snapshot(cycle_snapshot)

        if len(tasks) > 1:
            self.logger.info(
                "MultiActionDispatch: executing %d actions in parallel: %s",
                len(tasks), lanes_dispatched,
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        summarized_results: List[Dict[str, Any]] = []
        for (lane, action_name), result in zip(lanes_dispatched, results):
            if isinstance(result, BaseException):
                self.logger.error(
                    "ActionExecutor: action=%s lane=%s FAILED: %s",
                    action_name, lane, result,
                )
                summarized_results.append({
                    "lane": lane,
                    "action": action_name,
                    "status": "exception",
                    "error": str(result),
                })
            else:
                self.logger.info(
                    "ActionExecutor: action=%s lane=%s status=%s",
                    action_name, lane, result.get("status") if isinstance(result, dict) else "unknown",
                )
                summarized_results.append({
                    "lane": lane,
                    "action": action_name,
                    "status": result.get("status") if isinstance(result, dict) else "unknown",
                    "result": result,
                })
        return summarized_results

    async def _run_action(
        self,
        action_name: str,
        lane: str,
        snapshot: Dict,
        cycle_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """Execute a single action, update per-lane cooldown timestamp."""
        self.logger.info(
            "ActionExecutor: ejecutando action=%s lane=%s (U=%.4f)",
            action_name, lane,
            snapshot.get("u_proxy_score", 0.0) or 0.0,
        )
        metrics_before = self._collect_cycle_metrics()
        result = await execute_action(action_name)
        metrics_after = self._collect_cycle_metrics()
        # Per-lane cooldown tracking
        if not hasattr(self, '_lane_last_action'):
            self._lane_last_action: Dict[str, datetime] = {}
        self._lane_last_action[lane] = datetime.now()
        # Also maintain legacy _last_action_time for backward compat
        self._last_action_time = datetime.now()
        self._append_agent_event({
            "event": "action_executed",
            "room_id": "runtime_global",
            "action": action_name,
            "result": result.get("status", "unknown"),
            "files_changed": [],
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "timestamp": self._now_utc(),
            "cycle_id": cycle_snapshot.get("cycle_id") if isinstance(cycle_snapshot, dict) else None,
            "lane": lane,
        })
        return result

    def _lane_cooldown_active(self, lane: str) -> bool:
        """Check per-lane cooldown (ACTION_COOLDOWN_SECONDS per lane, independent)."""
        if not hasattr(self, '_lane_last_action'):
            return False
        last = self._lane_last_action.get(lane)
        if not last:
            return False
        elapsed = (datetime.now() - last).total_seconds()
        return elapsed < ACTION_COOLDOWN_SECONDS

    def _action_cooldown_active(self) -> bool:
        """Verifica si hay cooldown de acciones."""
        if not hasattr(self, '_last_action_time'):
            return False
        elapsed = (datetime.now() - self._last_action_time).total_seconds()
        return elapsed < ACTION_COOLDOWN_SECONDS


# Instancia global del manager
_autonomy_manager_instance: Optional[AutonomyManager] = None


def get_autonomy_manager() -> AutonomyManager:
    """Obtiene instancia singleton del AutonomyManager."""
    global _autonomy_manager_instance
    if _autonomy_manager_instance is None:
        _autonomy_manager_instance = AutonomyManager()
    return _autonomy_manager_instance
