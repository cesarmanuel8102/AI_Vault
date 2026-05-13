"""C-Sprint: Health Gate for post-mutation monitoring.

After a code mutation is applied, monitors brain health and triggers
automatic rollback if the brain becomes unhealthy.

Flow:
  1. Mutation applied
  2. HealthGate.start_monitoring(mutation_id, duration=60s)
  3. Polls /health every 5s
  4. If unhealthy -> rollback mutation + log
  5. If healthy for full duration -> mark mutation as stable
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Callable, Awaitable

from brain_v9.core import validator_metrics as _vmetrics

# Default monitoring settings
_DEFAULT_MONITOR_DURATION = 60.0  # seconds
_POLL_INTERVAL = 5.0  # seconds
_MAX_CONSECUTIVE_FAILURES = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class MonitoringSession:
    mutation_id: str
    start_time: float
    duration: float
    status: str  # "monitoring", "stable", "rolled_back", "cancelled"
    failures: int = 0
    checks: int = 0
    last_check: Optional[str] = None
    rollback_reason: Optional[str] = None


class HealthGate:
    """Monitors brain health after mutations and triggers rollback if needed."""

    _instance: Optional["HealthGate"] = None

    def __init__(self) -> None:
        self.logger = logging.getLogger("HealthGate")
        self._active_sessions: Dict[str, MonitoringSession] = {}
        self._rollback_callback: Optional[Callable[[str, str], Any]] = None
        self._health_check: Optional[Callable[[], Awaitable[bool]]] = None

    @classmethod
    def get(cls) -> "HealthGate":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_rollback_callback(self, callback: Callable[[str, str], Any]) -> None:
        """Set callback for rollback: callback(mutation_id, reason)."""
        self._rollback_callback = callback

    def set_health_check(self, check: Callable[[], Awaitable[bool]]) -> None:
        """Set async health check function. Returns True if healthy."""
        self._health_check = check

    async def start_monitoring(
        self,
        mutation_id: str,
        duration: float = _DEFAULT_MONITOR_DURATION,
    ) -> None:
        """Start monitoring health after a mutation.

        This runs in the background and will trigger rollback if health degrades.
        """
        if mutation_id in self._active_sessions:
            self.logger.warning("Already monitoring mutation %s", mutation_id)
            return

        session = MonitoringSession(
            mutation_id=mutation_id,
            start_time=time.time(),
            duration=duration,
            status="monitoring",
        )
        self._active_sessions[mutation_id] = session

        self.logger.info("Started health monitoring for mutation %s (%.0fs)", mutation_id, duration)
        _vmetrics.record("health_gate_monitor_started")

        # Run monitoring loop
        asyncio.create_task(self._monitor_loop(session))

    async def _monitor_loop(self, session: MonitoringSession) -> None:
        """Background monitoring loop."""
        try:
            while session.status == "monitoring":
                elapsed = time.time() - session.start_time
                if elapsed >= session.duration:
                    # Monitoring complete, mutation is stable
                    session.status = "stable"
                    self.logger.info(
                        "Mutation %s stable after %.0fs (%d checks, %d failures)",
                        session.mutation_id, elapsed, session.checks, session.failures,
                    )
                    _vmetrics.record("health_gate_stable")
                    break

                # Check health
                healthy = await self._check_health()
                session.checks += 1
                session.last_check = _now_iso()

                if healthy:
                    session.failures = 0  # Reset consecutive failures
                else:
                    session.failures += 1
                    self.logger.warning(
                        "Health check failed for mutation %s (failure %d/%d)",
                        session.mutation_id, session.failures, _MAX_CONSECUTIVE_FAILURES,
                    )

                    if session.failures >= _MAX_CONSECUTIVE_FAILURES:
                        # Trigger rollback
                        reason = f"Health check failed {session.failures} consecutive times"
                        await self._trigger_rollback(session, reason)
                        break

                await asyncio.sleep(_POLL_INTERVAL)

        except asyncio.CancelledError:
            session.status = "cancelled"
            self.logger.info("Monitoring cancelled for mutation %s", session.mutation_id)
        except Exception as e:
            self.logger.error("Monitoring error for %s: %s", session.mutation_id, e)
            session.status = "error"
        finally:
            # Cleanup
            self._active_sessions.pop(session.mutation_id, None)

    async def _check_health(self) -> bool:
        """Check if brain is healthy."""
        if self._health_check:
            try:
                return await self._health_check()
            except Exception as e:
                self.logger.warning("Health check error: %s", e)
                return False

        # Default: try to hit /health endpoint locally
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://127.0.0.1:8090/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("status") == "healthy"
                    return False
        except Exception:
            # If we can't check, assume healthy (avoid false rollbacks)
            return True

    async def _trigger_rollback(self, session: MonitoringSession, reason: str) -> None:
        """Trigger rollback for a mutation."""
        session.status = "rolled_back"
        session.rollback_reason = reason

        self.logger.error(
            "TRIGGERING ROLLBACK for mutation %s: %s",
            session.mutation_id, reason,
        )
        _vmetrics.record("health_gate_rollback_triggered")

        if self._rollback_callback:
            try:
                result = self._rollback_callback(session.mutation_id, reason)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.logger.error("Rollback callback failed: %s", e)

    def cancel_monitoring(self, mutation_id: str) -> bool:
        """Cancel monitoring for a mutation."""
        session = self._active_sessions.get(mutation_id)
        if session and session.status == "monitoring":
            session.status = "cancelled"
            return True
        return False

    def get_status(self, mutation_id: str) -> Optional[Dict[str, Any]]:
        """Get monitoring status for a mutation."""
        session = self._active_sessions.get(mutation_id)
        if not session:
            return None
        return {
            "mutation_id": session.mutation_id,
            "status": session.status,
            "elapsed": time.time() - session.start_time,
            "duration": session.duration,
            "checks": session.checks,
            "failures": session.failures,
            "last_check": session.last_check,
        }

    def list_active(self) -> list:
        """List all active monitoring sessions."""
        return [self.get_status(mid) for mid in self._active_sessions]
