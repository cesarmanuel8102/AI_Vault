"""
AUTO_TICK_LOOP.PY — Loop cognitivo automático con notificaciones al chat

Ejecuta BrainOrchestrator.tick() periódicamente en background, generando
notificaciones que el chat consume para informar al usuario de hallazgos
importantes sin intervención.

El tick es el "latido" del cerebro — sin él, el sistema duerme entre
interacciones humanas. Con auto-tick, el agente:
  - Detecta problemas proactivamente
  - Genera goals automáticos
  - Detecta sesgos
  - Notifica al usuario

Endpoints añadidos:
  GET /tick/status        — Estado del loop
  GET /tick/notifications — Notificaciones pendientes
  POST /tick/pause        — Pausar loop
  POST /tick/resume       — Reanudar loop
  POST /tick/force        — Forzar un tick ahora
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from enum import Enum

log = logging.getLogger("auto_tick_loop")


class NotificationType(str, Enum):
    NEW_GOAL = "new_goal"
    BIAS_DETECTED = "bias_detected"
    CAPABILITY_FAILED = "capability_failed"
    STRESS_HIGH = "stress_high"
    GAP_DISCOVERED = "gap_discovered"
    TICK_COMPLETE = "tick_complete"


@dataclass
class TickNotification:
    """Notificación generada por un tick cognitivo."""
    notification_type: NotificationType
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    read: bool = False


class AutoTickLoop:
    """
    Loop cognitivo automático que ejecuta tick() periódicamente.

    Genera notificaciones que el chat consume para mantener
    al usuario informado de la actividad interna del brain.
    """

    DEFAULT_INTERVAL = 60.0  # segundos entre ticks
    MAX_NOTIFICATIONS = 100   # máximo de notificaciones en buffer

    def __init__(self, interval: float = None):
        self.interval = interval or self.DEFAULT_INTERVAL
        self.notifications: List[TickNotification] = []
        self.running = False
        self.paused = False
        self.last_tick_time: Optional[float] = None
        self.tick_count = 0
        self._task: Optional[asyncio.Task] = None
        self._orchestrator = None

    def set_orchestrator(self, orchestrator):
        """Inyecta el BrainOrchestrator."""
        self._orchestrator = orchestrator

    async def start(self):
        """Inicia el loop de tick automático."""
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        log.info(f"[AutoTick] Iniciado (intervalo: {self.interval}s)")

    async def stop(self):
        """Detiene el loop."""
        self.running = False
        self.paused = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("[AutoTick] Detenido")

    async def pause(self):
        """Pausa el loop sin detenerlo."""
        self.paused = True
        log.info("[AutoTick] Pausado")

    async def resume(self):
        """Reanuda el loop pausado."""
        self.paused = False
        log.info("[AutoTick] Reanudado")

    async def force_tick(self) -> Dict[str, Any]:
        """Fuerza un tick inmediato."""
        return await self._execute_tick()

    def get_status(self) -> Dict[str, Any]:
        """Retorna estado del loop."""
        return {
            "running": self.running,
            "paused": self.paused,
            "interval": self.interval,
            "tick_count": self.tick_count,
            "last_tick_time": self.last_tick_time,
            "notifications_count": len(self.notifications),
            "unread_count": sum(1 for n in self.notifications if not n.read),
        }

    def get_notifications(self, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Retorna notificaciones pendientes."""
        notifs = self.notifications
        if unread_only:
            notifs = [n for n in notifs if not n.read]

        # Marcar como leídas
        for n in notifs:
            n.read = True

        return [asdict(n) for n in notifs[-50:]]  # Últimas 50

    async def _loop(self):
        """Loop principal."""
        while self.running:
            try:
                if not self.paused:
                    await self._execute_tick()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[AutoTick] Error en loop: {e}")
                await asyncio.sleep(self.interval)

    async def _execute_tick(self) -> Dict[str, Any]:
        """Ejecuta un tick completo y genera notificaciones."""
        if not self._orchestrator:
            return {"error": "orchestrator_not_set"}

        try:
            result = await self._orchestrator.tick()
            self.tick_count += 1
            self.last_tick_time = time.time()

            # Procesar resultados y generar notificaciones
            self._process_tick_result(result)

            return result
        except Exception as e:
            log.error(f"[AutoTick] Error en tick: {e}")
            self._add_notification(
                NotificationType.TICK_COMPLETE,
                f"Tick falló: {str(e)[:100]}",
                {"error": str(e)},
            )
            return {"error": str(e)}

    def _process_tick_result(self, result: Dict[str, Any]):
        """Analiza el resultado del tick y genera notificaciones."""
        # Nuevos goals
        new_goals = result.get("new_goals", [])
        if new_goals:
            self._add_notification(
                NotificationType.NEW_GOAL,
                f"Se generaron {len(new_goals)} objetivos nuevos: {', '.join(str(g) for g in new_goals[:3])}",
                {"goal_ids": new_goals},
            )

        # Sesgos detectados
        biases = result.get("biases_detected", {})
        if isinstance(biases, dict) and biases.get("biases"):
            bias_list = biases["biases"]
            self._add_notification(
                NotificationType.BIAS_DETECTED,
                f"Detectados {len(bias_list)} sesgos: {', '.join(str(b) for b in bias_list[:3])}",
                {"biases": bias_list},
            )

        # Señales de stress
        signals = result.get("signals", {})
        stress = signals.get("stress_level", 0.0)
        if stress > 0.6:
            self._add_notification(
                NotificationType.STRESS_HIGH,
                f"Nivel de stress alto: {stress:.2f}. Modo: {signals.get('resilience_mode', 'unknown')}",
                {"stress_level": stress},
            )

        # Gaps de conocimiento
        gap_count = signals.get("knowledge_gap_count", 0)
        if gap_count > 5:
            self._add_notification(
                NotificationType.GAP_DISCOVERED,
                f"Se detectaron {gap_count} brechas de conocimiento abiertas",
                {"gap_count": gap_count},
            )

        # Capacidades no confiables
        unreliable_pct = signals.get("capability_unreliable_pct", 0.0)
        if unreliable_pct > 0.5:
            self._add_notification(
                NotificationType.CAPABILITY_FAILED,
                f"{unreliable_pct:.0%} de capacidades son no confiables",
                {"unreliable_pct": unreliable_pct},
            )

    def _add_notification(self, ntype: NotificationType, message: str,
                          data: Dict[str, Any] = None):
        """Añade una notificación al buffer."""
        notif = TickNotification(
            notification_type=ntype,
            message=message,
            data=data or {},
        )
        self.notifications.append(notif)

        # Limitar buffer
        if len(self.notifications) > self.MAX_NOTIFICATIONS:
            self.notifications = self.notifications[-self.MAX_NOTIFICATIONS:]


# ─── Singleton ─────────────────────────────────────────────────────────────────

_loop: Optional[AutoTickLoop] = None

def get_auto_tick_loop(interval: float = None) -> AutoTickLoop:
    global _loop
    if _loop is None:
        _loop = AutoTickLoop(interval)
    return _loop
