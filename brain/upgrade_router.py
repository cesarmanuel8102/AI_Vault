"""
UPGRADE_ROUTER.PY - Endpoints FastAPI para los nuevos subsistemas
Monta /upgrade/* exponiendo AOS, L2, Sandbox, Bus, Orchestrator.
"""
import os
import sys
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

_BRAIN_DIR = os.path.dirname(__file__)
_ROOT_DIR = os.path.dirname(_BRAIN_DIR)

for p in (_ROOT_DIR, _BRAIN_DIR, os.path.join(_ROOT_DIR, "core"), os.path.join(_ROOT_DIR, "autonomy")):
    if p not in sys.path:
        sys.path.insert(0, p)

router = APIRouter(prefix="/upgrade", tags=["upgrade"])


# ========== Orchestrator ==========
@router.get("/status")
async def upgrade_status():
    from brain.brain_orchestrator import get_orchestrator
    return get_orchestrator().status()


@router.post("/tick")
async def upgrade_tick():
    from brain.brain_orchestrator import get_orchestrator
    return await get_orchestrator().tick()


# ========== AOS ==========
class GoalIn(BaseModel):
    description: str
    level: str = "operational"
    impact: float = 0.5
    cost: float = 0.5
    risk: float = 0.3
    urgency: float = 0.5
    actions: list = []


@router.get("/aos/status")
async def aos_status():
    from autonomy.goal_system import get_aos
    return get_aos().status()


@router.post("/aos/goal")
async def aos_add_goal(g: GoalIn):
    from autonomy.goal_system import get_aos
    goal = get_aos().add_goal(**g.dict())
    return {"goal_id": goal.goal_id, "utility": goal.utility()}


@router.post("/aos/execute")
async def aos_execute(n: int = 1):
    from autonomy.goal_system import get_aos
    return await get_aos().execute_top(n=n)


# ========== Metacognicion L2 ==========
@router.get("/l2/report")
async def l2_report():
    from brain.meta_cognition_l2 import get_l2
    return get_l2().report()


class CalibIn(BaseModel):
    declared_confidence: float
    was_correct: bool


@router.post("/l2/calibrate")
async def l2_calibrate(c: CalibIn):
    from brain.meta_cognition_l2 import get_l2
    get_l2().record_prediction(c.declared_confidence, c.was_correct)
    return {"ok": True, "ece": get_l2().calibration_error()}


# ========== Sandbox de auto-desarrollo ==========
class ProposalIn(BaseModel):
    target_file: str
    new_content: str
    rationale: str


@router.post("/sandbox/propose")
async def sandbox_propose(p: ProposalIn):
    from brain.self_dev_sandbox import get_sandbox
    proposal = get_sandbox().propose(p.target_file, p.new_content, p.rationale)
    return {
        "proposal_id": proposal.proposal_id,
        "risk_score": proposal.risk_score,
        "static_findings": proposal.static_findings,
        "requires_human_approval": proposal.requires_human_approval,
    }


@router.post("/sandbox/test/{pid}")
async def sandbox_test(pid: str):
    from brain.self_dev_sandbox import get_sandbox
    return get_sandbox().sandbox_test(pid)


@router.post("/sandbox/apply/{pid}")
async def sandbox_apply(pid: str, approver: Optional[str] = None):
    from brain.self_dev_sandbox import get_sandbox
    return get_sandbox().apply(pid, approver=approver)


@router.post("/sandbox/revert/{pid}")
async def sandbox_revert(pid: str):
    from brain.self_dev_sandbox import get_sandbox
    return get_sandbox().revert(pid)


@router.get("/sandbox/status")
async def sandbox_status():
    from brain.self_dev_sandbox import get_sandbox
    return get_sandbox().status()


# ========== Event Bus ==========
@router.get("/events/replay")
async def events_replay(limit: int = 100):
    from core.event_bus import get_bus
    events = get_bus().replay(limit=limit)
    return [{"name": e.name, "ts": e.ts, "source": e.source,
             "payload": e.payload} for e in events]


class EventIn(BaseModel):
    name: str
    payload: Dict[str, Any] = {}
    source: str = "api"


@router.post("/events/publish")
async def events_publish(e: EventIn):
    from core.event_bus import get_bus
    results = await get_bus().publish(e.name, e.payload, source=e.source)
    return {"published": True, "handlers": len(results)}


# ========== Settings ==========
@router.get("/settings")
async def settings_get():
    from core.settings import get_settings
    return get_settings().as_dict()


@router.post("/settings/reload")
async def settings_reload():
    from core.settings import reload_settings
    return reload_settings().as_dict()


# ========== Capability Governor ==========
class CapabilityToolIn(BaseModel):
    requested_tool: str
    allow_install: bool = False
    session_id: Optional[str] = None  # Si pertenece a una sesion PAD god, override


class MemoryCompactIn(BaseModel):
    episodic_max_age_hours: Optional[float] = 24.0 * 30.0 * 6.0
    semantic_max_age_hours: Optional[float] = 24.0 * 30.0 * 6.0
    keep_recent_episodic: int = 120
    keep_recent_semantic: int = 250
    dry_run: bool = True


@router.get("/capabilities/status")
async def capabilities_status():
    from brain.capability_governor import get_capability_governor
    return get_capability_governor().status()


@router.get("/capabilities/diagnose")
async def capabilities_diagnose():
    from brain.capability_governor import get_capability_governor
    return get_capability_governor().diagnose_runtime_health()


@router.post("/capabilities/remediate")
async def capabilities_remediate(payload: CapabilityToolIn):
    from brain.capability_governor import get_capability_governor
    # Detecta god mode chequeando el set del ExecutionGate
    god_override = False
    god_token = None
    if payload.session_id:
        try:
            from brain_v9.governance.execution_gate import get_gate, push_god_session
            god_override = get_gate().is_god_mode(payload.session_id)
            if god_override:
                # Activa el contextvar para que el executor's gate.check() detecte god mode
                god_token = push_god_session(payload.session_id)
        except Exception:
            god_override = False
    # Si executor disponible y allow_install solicitado, ejecuta install real
    executor = None
    if payload.allow_install:
        try:
            import main as _main_mod
            if _main_mod._agent_executor is None:
                _main_mod._agent_executor = _main_mod.build_standard_executor()
            executor = _main_mod._agent_executor
        except Exception:
            executor = None
    try:
        return await get_capability_governor().remediate_tool_gap(
            payload.requested_tool,
            executor=executor,
            allow_install=payload.allow_install,
            god_override=god_override,
        )
    finally:
        if god_token is not None:
            try:
                from brain_v9.governance.execution_gate import pop_god_session
                pop_god_session(god_token)
            except Exception:
                pass


# ========== Memory Maintenance ==========
@router.get("/memory/status")
async def memory_status():
    from brain_v9.core.knowledge import EpisodicMemory
    from brain_v9.core.semantic_memory import get_semantic_memory

    episodic = EpisodicMemory().get_stats()
    semantic = get_semantic_memory()
    semantic_records = semantic._read_records() if hasattr(semantic, "_read_records") else []
    semantic_stats = semantic._memory_stats(semantic_records) if hasattr(semantic, "_memory_stats") else semantic.status()
    return {
        "episodic": episodic,
        "semantic": semantic_stats,
    }


@router.post("/memory/compact")
async def memory_compact(payload: MemoryCompactIn):
    from brain_v9.core.knowledge import EpisodicMemory
    from brain_v9.core.semantic_memory import get_semantic_memory

    episodic_report = EpisodicMemory().compact(
        max_age_hours=payload.episodic_max_age_hours,
        keep_recent=payload.keep_recent_episodic,
        dry_run=payload.dry_run,
    )
    semantic = get_semantic_memory()
    if hasattr(semantic, "compact"):
        semantic_report = semantic.compact(
            max_age_hours=payload.semantic_max_age_hours,
            keep_recent=payload.keep_recent_semantic,
            dry_run=payload.dry_run,
        )
    else:
        semantic_report = {
            "ok": False,
            "status": "compact_not_supported",
            "backend": semantic.__class__.__name__,
            "dry_run": payload.dry_run,
        }
    return {
        "ok": True,
        "dry_run": payload.dry_run,
        "episodic": episodic_report,
        "semantic": semantic_report,
    }
