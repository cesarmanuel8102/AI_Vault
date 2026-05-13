"""
BRAIN_ORCHESTRATOR.PY - Orquestador unificado del cerebro mejorado
Integra: AOS (autonomia) + L2 (metacognicion) + Sandbox (autodesarrollo) + EventBus
Expone API unica `BrainOrchestrator.status()` y `tick()` para ciclo cognitivo.
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

_BRAIN_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BRAIN_DIR.parent

for p in (_ROOT_DIR, _BRAIN_DIR, _ROOT_DIR / "core", _ROOT_DIR / "autonomy"):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)


class BrainOrchestrator:
    """Hub central que conecta los nuevos subsistemas."""

    def __init__(self):
        self.last_tick: Optional[str] = None
        self._init_subsystems()
        self._wire_events()

    def _init_subsystems(self):
        # Lazy imports con tolerancia a fallos
        self.aos = None
        self.l2 = None
        self.sandbox = None
        self.bus = None
        self.meta = None
        self.settings = None
        self.capabilities = None
        try:
            from core.settings import get_settings
            self.settings = get_settings()
        except Exception as e:
            print(f"[Orchestrator] settings: {e}")
        try:
            from core.event_bus import get_bus
            self.bus = get_bus()
        except Exception as e:
            print(f"[Orchestrator] event_bus: {e}")
        try:
            from autonomy.goal_system import get_aos
            self.aos = get_aos()
        except Exception as e:
            print(f"[Orchestrator] AOS: {e}")
        try:
            from brain.meta_cognition_l2 import get_l2
            self.l2 = get_l2()
        except Exception as e:
            print(f"[Orchestrator] L2: {e}")
        try:
            from brain.self_dev_sandbox import get_sandbox
            self.sandbox = get_sandbox()
        except Exception as e:
            print(f"[Orchestrator] sandbox: {e}")
        try:
            from brain.meta_cognition_core import MetaCognitionCore
            self.meta = MetaCognitionCore()
        except Exception as e:
            print(f"[Orchestrator] meta: {e}")
        try:
            from brain.capability_governor import get_capability_governor
            self.capabilities = get_capability_governor()
        except Exception as e:
            print(f"[Orchestrator] capabilities: {e}")
        self._register_actions()

    def _register_actions(self):
        if not self.aos:
            return

        def _scan_errors(_goal):
            if self.capabilities:
                report = self.capabilities.diagnose_runtime_health()
                return {"success": True, "report": report}
            return {"success": False, "error": "capability_governor_unavailable"}

        def _research_gaps(_goal):
            if self.capabilities:
                return {"success": True, "report": self.capabilities.status()}
            return {"success": False, "error": "capability_governor_unavailable"}

        def _train_capabilities(_goal):
            if self.capabilities:
                report = self.capabilities.diagnose_runtime_health()
                gaps = report.get("runtime_gaps", [])
                return {"success": True, "gaps": gaps, "message": "diagnostico actualizado"}
            return {"success": False, "error": "capability_governor_unavailable"}

        # R27: action that closes the auto-install loop. Extracts capability name
        # from goal description and calls governor.remediate_tool_gap with the
        # live executor. Honors self_dev policy (no install if disabled), so
        # safe-by-default: when policy is OFF this returns 'requires_governed_remediation'
        # instead of 'proposed' forever.
        async def _remediate_capability(goal):
            if not self.capabilities:
                return {"success": False, "error": "capability_governor_unavailable"}
            desc = (goal.description or "")
            cap_name = None
            for prefix in (
                "Recuperar capacidad fallida:",
                "Recuperar capacidad:",
                "Remediate capability:",
            ):
                if prefix in desc:
                    cap_name = desc.split(prefix, 1)[1].strip()
                    break
            if not cap_name:
                return {"success": False, "error": "no_capability_in_description", "desc": desc}

            executor = None
            try:
                import main as _main_mod
                if getattr(_main_mod, "_agent_executor", None) is None:
                    _main_mod._agent_executor = _main_mod.build_standard_executor()
                executor = _main_mod._agent_executor
            except Exception as exc:
                return {"success": False, "error": f"executor_unavailable: {exc}"}

            # Honor self_dev policy: only allow_install when explicitly enabled
            allow = False
            try:
                from core.settings import get_settings
                s = get_settings()
                allow = bool(s.self_dev_enabled and not s.self_dev_require_approval)
            except Exception:
                pass

            try:
                result = await self.capabilities.remediate_tool_gap(
                    cap_name,
                    executor=executor,
                    allow_install=allow,
                    god_override=False,
                )
            except Exception as exc:
                return {"success": False, "error": f"remediate_exception: {exc}", "capability": cap_name}

            status = (result or {}).get("status", "?")
            # success means progressed (installed or resolved or native available);
            # 'requires_governed_remediation' is informational, treat as partial progress
            success = status in ("installed", "resolved", "use_native_capability")
            return {
                "success": success,
                "capability": cap_name,
                "status": status,
                "result": result,
            }

        self.aos.register_action("scan_errors", _scan_errors)
        self.aos.register_action("research_gaps", _research_gaps)
        self.aos.register_action("train_capabilities", _train_capabilities)
        self.aos.register_action("remediate_capability", _remediate_capability)

    def _wire_events(self):
        if not self.bus:
            return
        # Eventos del sistema -> efectos cruzados
        async def on_decision(event):
            decision = event.payload.get("decision", {})
            if self.l2 and decision:
                self.l2.detect_bias([decision])
                if "confidence" in decision and "outcome" in decision:
                    self.l2.record_prediction(
                        decision["confidence"],
                        decision["outcome"] in ("success", True))

        async def on_capability_failure(event):
            cap = (
                event.payload.get("capability")
                or event.payload.get("tool")
                or event.payload.get("requested_tool")
                or "unknown"
            )
            diagnosis = None
            if self.capabilities:
                diagnosis = self.capabilities.record_tool_failure(
                    cap,
                    reason=event.payload.get("reason") or event.payload.get("error") or "capability_failed",
                    error=event.payload.get("error", ""),
                )
            if self.aos:
                self.aos.add_goal(
                    description=f"Recuperar capacidad fallida: {cap}",
                    level="tactical",
                    impact=0.7, cost=0.3, risk=0.3, urgency=0.7,
                    actions=["remediate_capability", "scan_errors", "research_gaps"])
            return diagnosis

        async def on_high_stress(event):
            if self.aos:
                self.aos.add_goal(
                    description="Reducir carga del sistema",
                    level="strategic",
                    impact=0.8, cost=0.2, risk=0.1, urgency=0.9)

        self.bus.subscribe("decision.completed", on_decision)
        self.bus.subscribe("capability.failed", on_capability_failure)
        self.bus.subscribe("system.stress.high", on_high_stress)

    async def tick(self) -> Dict[str, Any]:
        """Ciclo cognitivo: detecta -> planifica -> ejecuta -> reflexiona."""
        result: Dict[str, Any] = {"ts": datetime.now().isoformat()}
        # 1. Senales
        signals = self._collect_signals()
        result["signals"] = signals
        # 2. Generar goals proactivos
        if self.aos:
            new_goals = self.aos.detect_predictive_goals(signals)
            result["new_goals"] = [g.goal_id for g in new_goals]
            # 3. Ejecutar top
            exec_results = await self.aos.execute_top(n=2)
            result["executions"] = len(exec_results)
        # 4. Metacognicion L2: detectar sesgos en decisiones recientes
        if self.l2 and self.meta:
            recent = [
                {
                    "selected_option": d.selected_option,
                    "confidence_at_decision": d.confidence_at_decision,
                    "alternatives_rejected": d.alternatives_rejected,
                    "actual_consequences": d.actual_consequences,
                    "reasoning_chain": d.reasoning_chain,
                }
                for d in (self.meta.self_model.decision_history[-30:] or [])
            ]
            biases = self.l2.detect_bias(recent)
            result["biases_detected"] = biases
        # 5. Publicar evento de tick
        if self.bus:
            await self.bus.publish("orchestrator.tick", result, source="orchestrator")
        self.last_tick = result["ts"]
        return result

    def _collect_signals(self) -> Dict[str, float]:
        signals: Dict[str, float] = {}
        if self.meta:
            try:
                rep = self.meta.get_self_awareness_report()
                signals["knowledge_gap_count"] = float(rep["knowledge_gaps"]["open"])
                caps = rep["capabilities_summary"]
                total = max(1, caps["total"])
                signals["capability_unreliable_pct"] = caps["unreliable"] / total
                signals["stress_level"] = float(rep.get("stress_level", 0.0))
                signals["unknown_unknowns_risk"] = float(rep.get("unknown_unknowns_risk", 0.0))
            except Exception:
                pass
        if self.l2:
            try:
                signals["calibration_error"] = self.l2.calibration_error()
            except Exception:
                pass
        if self.capabilities:
            try:
                capability_report = self.capabilities.diagnose_runtime_health()
                runtime_gaps = capability_report.get("runtime_gaps", [])
                signals["runtime_gap_count"] = float(len(runtime_gaps))
            except Exception:
                pass
        return signals

    def status(self) -> Dict[str, Any]:
        return {
            "last_tick": self.last_tick,
            "subsystems": {
                "aos": self.aos.status() if self.aos else None,
                "l2": self.l2.report() if self.l2 else None,
                "sandbox": self.sandbox.status() if self.sandbox else None,
                "meta": self.meta.get_self_awareness_report() if self.meta else None,
                "settings": self.settings.as_dict() if self.settings else None,
                "capabilities": self.capabilities.status() if self.capabilities else None,
            },
        }


_ORCH: Optional[BrainOrchestrator] = None

def get_orchestrator() -> BrainOrchestrator:
    global _ORCH
    if _ORCH is None:
        _ORCH = BrainOrchestrator()
    return _ORCH
