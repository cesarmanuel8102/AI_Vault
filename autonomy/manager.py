"""
Brain Chat V9 — autonomy/manager.py
Sistema de autonomía proactiva.
Extraído de V8.0 líneas 7038-8900.
Corrección principal: eliminados globales, toda la lógica en AutonomyManager.
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from brain_v9.config import AUTONOMY_CONFIG, LOGS_PATH


class AutonomyManager:
    """
    Orquesta los 3 sistemas de autonomía:
    - AutoDebugger:    revisa logs de errores cada N minutos
    - ProactiveMonitor: verifica servicios y recursos
    - (AutoOptimizer se puede agregar igual)
    """

    def __init__(self):
        self.logger   = logging.getLogger("AutonomyManager")
        self._tasks:  List[asyncio.Task] = []
        self._running = False
        self.reports: List[Dict] = []

    # ── Ciclo de vida ─────────────────────────────────────────────────────────
    async def start(self):
        if self._running:
            return
        self._running = True
        if AUTONOMY_CONFIG["auto_debugging_enabled"]:
            self._tasks.append(asyncio.create_task(self._debug_loop()))
        if AUTONOMY_CONFIG["proactive_monitoring_enabled"]:
            self._tasks.append(asyncio.create_task(self._monitor_loop()))
        # AOS: planificacion proactiva basada en utilidad
        try:
            from autonomy.goal_system import get_aos
            self.aos = get_aos()
            self._register_default_actions()
            self._tasks.append(asyncio.create_task(self._aos_loop()))
            self.logger.info("AOS activado (%d goals)", len(self.aos.goals))
        except Exception as e:
            self.logger.warning("AOS no disponible: %s", e)
        self.logger.info("AutonomyManager iniciado (%d tareas)", len(self._tasks))

    def _register_default_actions(self):
        async def scan_errors(goal):
            r = await self._scan_error_logs()
            return {"success": True, "errors_found": r["errors_found"]}
        async def patch_critical(goal):
            return {"success": True, "noop": "requires human approval"}
        async def research_gaps(goal):
            try:
                import sys
                sys.path.insert(0, "C:/AI_VAULT/brain")
                from evolucion_continua import EvolucionContinua
                ev = EvolucionContinua()
                ev.queue_research(goal.description, priority=0.7)
                ev.process_research_queue(max_tasks=1)
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}
        async def train_capabilities(goal):
            return {"success": True, "noop": "scheduled"}
        self.aos.register_action("scan_errors", scan_errors)
        self.aos.register_action("patch_critical", patch_critical)
        self.aos.register_action("research_gaps", research_gaps)
        self.aos.register_action("train_capabilities", train_capabilities)

    async def _aos_loop(self):
        interval = AUTONOMY_CONFIG.get("aos_interval", 120)
        self.logger.info("AOS loop cada %ds", interval)
        while self._running:
            try:
                signals = await self._collect_signals()
                self.aos.detect_predictive_goals(signals)
                results = await self.aos.execute_top(n=2)
                if results:
                    self.reports.append({
                        "timestamp": datetime.now().isoformat(),
                        "type": "aos_cycle",
                        "executed": len(results),
                        "results": results[:5],
                    })
            except Exception as e:
                self.logger.error("AOS loop error: %s", e)
            await asyncio.sleep(interval)

    async def _collect_signals(self) -> Dict[str, float]:
        signals = {}
        try:
            recent_errors = sum(1 for r in self.reports[-20:]
                                if r.get("errors_found", 0) > 0)
            signals["error_rate"] = min(1.0, recent_errors / 20)
        except Exception:
            signals["error_rate"] = 0.0
        try:
            import sys
            sys.path.insert(0, "C:/AI_VAULT/brain")
            from meta_cognition_core import MetaCognitionCore
            mc = MetaCognitionCore()
            rep = mc.get_self_awareness_report()
            signals["knowledge_gap_count"] = rep["knowledge_gaps"]["open"]
            caps = rep["capabilities_summary"]
            total = max(1, caps["total"])
            signals["capability_unreliable_pct"] = caps["unreliable"] / total
        except Exception:
            pass
        return signals

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        self.logger.info("AutonomyManager detenido")

    # ── Debug loop ────────────────────────────────────────────────────────────
    async def _debug_loop(self):
        interval = AUTONOMY_CONFIG["check_interval_debugger"]
        self.logger.info("Debug loop: revisará logs cada %ds", interval)
        while self._running:
            try:
                report = await self._scan_error_logs()
                if report["errors_found"] > 0:
                    self.reports.append(report)
                    self.logger.warning("AutoDebugger: %d errores encontrados", report["errors_found"])
                await self._rotate_logs()
            except Exception as e:
                self.logger.error("Error en debug loop: %s", e)
            await asyncio.sleep(interval)

    async def _scan_error_logs(self) -> Dict:
        """Escanea logs buscando líneas ERROR."""
        errors: List[str] = []
        try:
            for lf in LOGS_PATH.glob("*.log"):
                for line in lf.read_text(encoding="utf-8", errors="ignore").splitlines():
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

    async def _rotate_logs(self):
        """Rota logs si superan el tamaño máximo."""
        max_size = 10 * 1024 * 1024  # 10MB
        try:
            for lf in LOGS_PATH.glob("*.log"):
                if lf.stat().st_size > max_size:
                    # Rota: log -> log.1, log.1 -> log.2, etc.
                    for i in range(4, 0, -1):
                        old = lf.with_suffix(f"{lf.suffix}.{i}")
                        new = lf.with_suffix(f"{lf.suffix}.{i+1}")
                        if old.exists():
                            old.replace(new)
                    rotated = lf.with_suffix(f"{lf.suffix}.1")
                    lf.replace(rotated)
                    # Crear nuevo log vacío
                    lf.touch()
                    self.logger.info("Log rotado: %s", lf.name)
        except Exception as e:
            self.logger.error("Error rotando logs: %s", e)

    # ── Monitor loop ──────────────────────────────────────────────────────────
    async def _monitor_loop(self):
        interval = AUTONOMY_CONFIG["check_interval_monitor"]
        self.logger.info("Monitor loop: revisará servicios cada %ds", interval)
        while self._running:
            try:
                report = await self._check_resources()
                if report.get("alerts"):
                    self.reports.append(report)
                    for alert in report["alerts"]:
                        self.logger.warning("ProactiveMonitor: %s", alert)
            except Exception as e:
                self.logger.error("Error en monitor loop: %s", e)
            await asyncio.sleep(interval)

    async def _check_resources(self) -> Dict:
        alerts = []
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory().percent
            dsk = psutil.disk_usage("/").percent
            if cpu > 85:
                alerts.append(f"CPU alta: {cpu}%")
            if mem > 90:
                alerts.append(f"Memoria alta: {mem}%")
            if dsk > 90:
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

    # ── Estado público ────────────────────────────────────────────────────────
    def get_status(self) -> Dict:
        return {
            "running":       self._running,
            "active_tasks":  len(self._tasks),
            "reports_stored":len(self.reports),
            "config":        AUTONOMY_CONFIG,
        }

    def get_recent_reports(self, limit: int = 20) -> List[Dict]:
        return self.reports[-limit:]

    def clear_reports(self):
        self.reports.clear()
