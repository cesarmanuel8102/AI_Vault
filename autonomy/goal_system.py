"""
AUTONOMY/GOAL_SYSTEM.PY - Sistema de Objetivos Autonomos (AOS)
Reemplaza autonomia reactiva por planificacion proactiva basada en utilidad esperada.

Jerarquia: Mision > Objetivos Estrategicos > Tacticos > Operacionales
Decision: Utility = (Impact * UrgencyDecay) / (Cost * RiskFactor)
"""
import json
import asyncio
import logging
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

STATE_DIR = Path("C:/AI_VAULT/tmp_agent/state/aos")
STATE_DIR.mkdir(parents=True, exist_ok=True)
GOALS_FILE = STATE_DIR / "goals.json"
DECISIONS_FILE = STATE_DIR / "decisions.jsonl"

log = logging.getLogger("AOS")


class GoalLevel(str, Enum):
    MISSION = "mission"
    STRATEGIC = "strategic"
    TACTICAL = "tactical"
    OPERATIONAL = "operational"


class GoalStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    BLOCKED = "blocked"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"


@dataclass
class Goal:
    goal_id: str
    description: str
    level: str
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    impact: float = 0.5            # 0..1 valor esperado si se logra
    cost: float = 0.5              # 0..1 recursos necesarios
    risk: float = 0.3              # 0..1 probabilidad/severidad de fallo
    urgency: float = 0.5           # 0..1 urgencia base
    deadline: Optional[str] = None # ISO; activa decay temporal
    status: str = GoalStatus.PROPOSED.value
    progress: float = 0.0
    success_criteria: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)  # action ids ejecutables
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    attempts: int = 0
    last_failure: Optional[str] = None

    def utility(self, now: Optional[datetime] = None) -> float:
        """Utilidad esperada con decay temporal si hay deadline."""
        now = now or datetime.now()
        u = self.urgency
        if self.deadline:
            try:
                dl = datetime.fromisoformat(self.deadline)
                seconds_left = (dl - now).total_seconds()
                if seconds_left <= 0:
                    u = 1.0
                else:
                    # decay exponencial: mas cerca del deadline -> mas urgente
                    half_life_h = 24
                    u = min(1.0, self.urgency + math.exp(-seconds_left / (3600 * half_life_h)))
            except Exception:
                pass
        denom = max(0.05, self.cost * (1 + self.risk))
        return (self.impact * u) / denom


class GoalSystem:
    """Sistema de Objetivos Autonomos: planifica, prioriza, ejecuta."""

    def __init__(self):
        self.goals: Dict[str, Goal] = {}
        self.action_registry: Dict[str, Callable] = {}
        self._load()

    # --- persistencia ---
    def _load(self):
        if GOALS_FILE.exists():
            try:
                data = json.loads(GOALS_FILE.read_text(encoding="utf-8"))
                for g in data.get("goals", []):
                    self.goals[g["goal_id"]] = Goal(**g)
            except Exception as e:
                log.error("Error cargando goals: %s", e)

    def _save(self):
        try:
            GOALS_FILE.write_text(
                json.dumps({"goals": [asdict(g) for g in self.goals.values()]},
                           indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            log.error("Error guardando goals: %s", e)

    def _audit(self, event: Dict[str, Any]):
        try:
            with DECISIONS_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": datetime.now().isoformat(), **event}) + "\n")
        except Exception:
            pass

    # --- registro de acciones ---
    def register_action(self, action_id: str, fn: Callable):
        self.action_registry[action_id] = fn

    # --- API objetivos ---
    def add_goal(self, description: str, level: str = "operational",
                 parent_id: Optional[str] = None, **kwargs) -> Goal:
        gid = f"goal_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.goals)}"
        goal = Goal(goal_id=gid, description=description, level=level,
                    parent_id=parent_id, **kwargs)
        self.goals[gid] = goal
        if parent_id and parent_id in self.goals:
            self.goals[parent_id].children_ids.append(gid)
        self._save()
        self._audit({"type": "goal_added", "id": gid, "level": level})
        return goal

    def update_progress(self, gid: str, progress: float, status: Optional[str] = None):
        g = self.goals.get(gid)
        if not g:
            return
        g.progress = max(0.0, min(1.0, progress))
        if status:
            g.status = status
        g.updated_at = datetime.now().isoformat()
        if g.progress >= 1.0:
            g.status = GoalStatus.ACHIEVED.value
        self._save()

    # --- planificacion ---
    def decompose(self, parent_id: str, subgoals: List[Dict[str, Any]]) -> List[Goal]:
        """Descompone objetivo en subobjetivos hijos."""
        children = []
        parent = self.goals.get(parent_id)
        if not parent:
            return children
        next_level = {
            GoalLevel.MISSION.value: GoalLevel.STRATEGIC.value,
            GoalLevel.STRATEGIC.value: GoalLevel.TACTICAL.value,
            GoalLevel.TACTICAL.value: GoalLevel.OPERATIONAL.value,
        }.get(parent.level, GoalLevel.OPERATIONAL.value)
        for sg in subgoals:
            child = self.add_goal(level=next_level, parent_id=parent_id, **sg)
            children.append(child)
        return children

    def rank_goals(self) -> List[Goal]:
        """Prioriza por utilidad esperada los goals activos/propuestos."""
        active = [g for g in self.goals.values()
                  if g.status in (GoalStatus.PROPOSED.value, GoalStatus.ACTIVE.value)]
        return sorted(active, key=lambda g: g.utility(), reverse=True)

    # --- ejecucion ---
    async def execute_top(self, n: int = 1) -> List[Dict[str, Any]]:
        """Ejecuta los top-N goals de mayor utilidad."""
        results = []
        ranked = self.rank_goals()[:n]
        for goal in ranked:
            if not goal.actions:
                continue
            goal.status = GoalStatus.ACTIVE.value
            goal.attempts += 1
            for action_id in goal.actions:
                fn = self.action_registry.get(action_id)
                if not fn:
                    continue
                try:
                    res = fn(goal) if not asyncio.iscoroutinefunction(fn) else await fn(goal)
                    success = bool(res) if not isinstance(res, dict) else res.get("success", True)
                    self._audit({"type": "action_executed", "goal": goal.goal_id,
                                 "action": action_id, "success": success})
                    if success:
                        self.update_progress(goal.goal_id, min(1.0, goal.progress + 0.34))
                    else:
                        goal.last_failure = datetime.now().isoformat()
                    results.append({"goal": goal.goal_id, "action": action_id,
                                    "success": success, "result": res})
                except Exception as e:
                    goal.last_failure = f"{datetime.now().isoformat()}: {e}"
                    self._audit({"type": "action_error", "goal": goal.goal_id,
                                 "action": action_id, "error": str(e)})
        self._save()
        return results

    # --- anticipacion ---
    def detect_predictive_goals(self, signals: Dict[str, float]) -> List[Goal]:
        """Genera goals proactivos a partir de senales del sistema."""
        new_goals = []
        if signals.get("error_rate", 0) > 0.1:
            new_goals.append(self.add_goal(
                description="Reducir tasa de errores detectada",
                level=GoalLevel.TACTICAL.value,
                impact=0.8, cost=0.3, risk=0.2, urgency=0.7,
                actions=["scan_errors", "patch_critical"]))
        if signals.get("knowledge_gap_count", 0) > 3:
            new_goals.append(self.add_goal(
                description="Cerrar brechas de conocimiento criticas",
                level=GoalLevel.TACTICAL.value,
                impact=0.7, cost=0.4, risk=0.3, urgency=0.6,
                actions=["research_gaps"]))
        if signals.get("capability_unreliable_pct", 0) > 0.3:
            new_goals.append(self.add_goal(
                description="Mejorar fiabilidad de capacidades",
                level=GoalLevel.STRATEGIC.value,
                impact=0.9, cost=0.6, risk=0.4, urgency=0.5,
                actions=["train_capabilities"]))
        return new_goals

    def status(self) -> Dict[str, Any]:
        by_level = {lv.value: 0 for lv in GoalLevel}
        by_status = {st.value: 0 for st in GoalStatus}
        for g in self.goals.values():
            by_level[g.level] = by_level.get(g.level, 0) + 1
            by_status[g.status] = by_status.get(g.status, 0) + 1
        top = self.rank_goals()[:5]
        return {
            "total": len(self.goals),
            "by_level": by_level,
            "by_status": by_status,
            "registered_actions": list(self.action_registry.keys()),
            "top_priorities": [
                {"id": g.goal_id, "desc": g.description,
                 "utility": round(g.utility(), 3), "level": g.level}
                for g in top
            ],
        }


# Singleton
_AOS: Optional[GoalSystem] = None

def get_aos() -> GoalSystem:
    global _AOS
    if _AOS is None:
        _AOS = GoalSystem()
    return _AOS
