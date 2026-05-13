"""
ProactiveScheduler — Phase II: Background task scheduler for Brain V9 agent.

Instead of only responding to user queries, the agent can now run
periodic checks autonomously: service health, portfolio status,
anomaly detection, etc.

Architecture:
    ProactiveScheduler.start()
      -> while running:
           -> for each scheduled task whose interval has elapsed:
                -> BrainSession.chat(task_prompt) via dedicated "scheduler" session
                -> Log result + persist to state/scheduler_history.json
           -> sleep(check_interval)

Design decisions:
    - Uses BrainSession.chat() — full ORAV agent with governance gate
    - Dedicated session_id="scheduler" to avoid polluting user's default session
    - Tasks are P0 by default (read-only checks); any P2+ action still requires /approve
    - Configurable via state/scheduler_config.json (persisted across restarts)
    - /schedule slash command for user control (enable/disable/list/add/remove)
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from brain_v9.config import BASE_PATH

log = logging.getLogger("ProactiveScheduler")

_STATE_DIR = BASE_PATH / "tmp_agent" / "state"
_CONFIG_PATH = _STATE_DIR / "scheduler_config.json"
_HISTORY_PATH = _STATE_DIR / "scheduler_history.json"

# ── Default scheduled tasks ──────────────────────────────────────────────────
# Each task: {id, prompt, interval_minutes, enabled, description}
DEFAULT_TASKS: List[Dict] = [
    {
        "id": "services_health",
        "prompt": "revisa el estado de todos los servicios del ecosistema AI_VAULT",
        "interval_minutes": 30,
        "enabled": True,
        "description": "Health check de todos los servicios (puertos, procesos)",
    },
    {
        "id": "disk_space",
        "prompt": "revisa el espacio en disco de todas las unidades",
        "interval_minutes": 120,
        "enabled": True,
        "description": "Monitoreo de espacio en disco",
    },
    {
        "id": "error_scan",
        "prompt": "busca errores criticos en los logs mas recientes del sistema",
        "interval_minutes": 60,
        "enabled": True,
        "description": "Escaneo de errores en logs",
    },
    {
        "id": "portfolio_check",
        "prompt": "revisa el estado actual del portfolio de trading y posiciones abiertas",
        "interval_minutes": 60,
        "enabled": False,
        "description": "Revisión de portfolio/posiciones (requiere IBKR activo)",
    },
    {
        # R9.1: Chat Excellence Self-Improvement Loop
        # Brain analyzes its own recent chat interactions, detects weaknesses,
        # formulates hypothesis + concrete improvement, and persists to
        # state/chat_excellence_history.json (structured iterations).
        "id": "chat_excellence",
        # NOTE: prompt deliberately AVOIDS trigger words ("automejora",
        # "autoconstruccion", "playbook", "plan de accion", "self improvement",
        # "resuelvelo") that route to BrainSession's templated governance
        # interceptors (_is_self_build_resolution_query, _is_deep_brain_analysis_query).
        # Phrasing focuses on telemetry/diagnostics, which routes to the LLM.
        "prompt": (
            "Diagnostico de calidad de interaccion via chat. Output: JSON estricto.\n\n"
            "Lee los siguientes ficheros de telemetria (paths absolutos):\n"
            "  - C:/AI_VAULT/tmp_agent/state/brain_metrics/chat_metrics_latest.json\n"
            "  - C:/AI_VAULT/tmp_agent/state/brain_metrics/llm_metrics_latest.json\n\n"
            "El segundo fichero ya incluye (R9.8) las claves circuit_breaker, "
            "chain_health y latency_per_model con percentiles p50/p95/p99 por modelo. "
            "USALAS para evitar proponer mejoras que ya existen (e.g., NO propongas "
            "implementar un circuit breaker porque ya hay uno; en su lugar refina sus "
            "thresholds, agrega telemetria, mejora routing entre cadenas, etc.).\n\n"
            "Analisis solicitado:\n"
            "1) Detecta los 3 patrones de telemetria mas problematicos en las "
            "ultimas interacciones (ejemplos validos: latencia p95 alta, "
            "ratio de fallback elevado, baja confianza de intent classification, "
            "respuestas truncadas, tools mal formateados, mojibake/encoding, "
            "num_predict capped, chain validator failures).\n"
            "2) Selecciona el patron #1 con mayor impact score (0-10) y "
            "formula UNA explicacion candidata (causa raiz) que sea verificable "
            "con metricas observables.\n"
            "3) Indica UN cambio concreto (archivo + lineas o nueva funcion) "
            "que mitigaria el patron. NO ejecutes nada, solo describe.\n"
            "   IMPORTANTE: 'affected_files' debe contener SOLO rutas que existan "
            "realmente en C:/AI_VAULT/tmp_agent/brain_v9/ (verifica con list_directory "
            "o read_file antes). Modulos canonicos relevantes:\n"
            "     - core/llm.py            (CHAINS, MODELS, _CB_FAIL_THRESHOLD, _CB_COOLDOWN_S, _ollama, _openai, _anthropic, _GLOBAL_CB_STATE, _persist_metrics)\n"
            "     - core/session.py        (chat dispatcher, _route_to_agent, _route_to_llm, fastpath)\n"
            "     - core/intent.py         (intent classification + confidence)\n"
            "     - core/chat_metrics.py   (chat_metrics recorder)\n"
            "     - agent/loop.py          (AgentLoop, MetaPlanner, ORAV cycle)\n"
            "     - agent/tools.py         (tool registry, ~150 tools)\n"
            "     - autonomy/proactive_scheduler.py (this scheduler)\n"
            "   NO inventes nombres como 'brain_chat_server.py' o 'llm_chain_config.json' (no existen).\n"
            "4) Define UNA medicion observable que validaria la mejora "
            "(ej: 'p95 latency de kimi_cloud baja de X a Y').\n\n"
            "Formato de respuesta OBLIGATORIO (JSON unico, sin texto adicional, "
            "sin markdown fences):\n"
            "{\"weakness\": \"...\", \"impact_score\": 7, "
            "\"root_cause_guess\": \"...\", \"proposed_change\": \"...\", "
            "\"test_plan\": \"...\", \"expected_improvement\": \"...\", "
            "\"affected_files\": [\"...\"], \"status\": \"documented\"}"
        ),
        "interval_minutes": 60,
        "enabled": True,
        "timeout_s": 600,
        "description": "R9.1: Diagnostico iterativo de calidad de chat (analiza, propone, mide)",
    },
]

# ── Max history entries to keep ──────────────────────────────────────────────
MAX_HISTORY = 200


class ProactiveScheduler:
    """Background scheduler that runs ORAV agent tasks on a timer."""

    CHECK_INTERVAL = 30  # seconds between checking if any task is due

    def __init__(self):
        self.running = False
        self.tasks: List[Dict] = []
        self._last_run: Dict[str, float] = {}  # task_id -> last_run_timestamp
        self._history: List[Dict] = []
        self._session = None  # lazy BrainSession
        self._load_config()
        self._load_history()

    def _load_config(self):
        """Load task config from disk, or initialize with defaults."""
        try:
            if _CONFIG_PATH.exists():
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.tasks = data.get("tasks", DEFAULT_TASKS)
                self._last_run = data.get("last_run", {})
                self.running = data.get("enabled", True)
                # R9.1: Migration — auto-add any new DEFAULT_TASKS not yet in saved config.
                # Lets us ship new scheduled loops via code without hand-editing JSON.
                existing_ids = {t.get("id") for t in self.tasks}
                added = []
                for default_t in DEFAULT_TASKS:
                    if default_t["id"] not in existing_ids:
                        self.tasks.append(dict(default_t))
                        added.append(default_t["id"])
                # R9.1.1: Code-managed tasks (chat_excellence) — always refresh
                # prompt/description from DEFAULT_TASKS so prompt evolution
                # in code propagates to runtime without hand-editing JSON.
                CODE_MANAGED = {"chat_excellence"}
                refreshed = []
                for default_t in DEFAULT_TASKS:
                    if default_t["id"] not in CODE_MANAGED:
                        continue
                    for i, t in enumerate(self.tasks):
                        if t.get("id") == default_t["id"]:
                            if (t.get("prompt") != default_t["prompt"]
                                    or t.get("description") != default_t["description"]
                                    or t.get("timeout_s") != default_t.get("timeout_s")):
                                self.tasks[i]["prompt"] = default_t["prompt"]
                                self.tasks[i]["description"] = default_t["description"]
                                self.tasks[i]["interval_minutes"] = default_t["interval_minutes"]
                                if "timeout_s" in default_t:
                                    self.tasks[i]["timeout_s"] = default_t["timeout_s"]
                                refreshed.append(default_t["id"])
                                # Also reset last_run so the refreshed task fires soon
                                self._last_run.pop(default_t["id"], None)
                            break
                if added or refreshed:
                    log.info("Scheduler migration: added=%s, refreshed=%s",
                             added, refreshed)
                    self._save_config()
                log.info("Scheduler config loaded: %d tasks, enabled=%s", len(self.tasks), self.running)
            else:
                self.tasks = [dict(t) for t in DEFAULT_TASKS]
                self.running = True
                self._save_config()
                log.info("Scheduler config initialized with %d default tasks", len(self.tasks))
        except Exception as e:
            log.warning("Failed to load scheduler config: %s, using defaults", e)
            self.tasks = [dict(t) for t in DEFAULT_TASKS]
            self.running = True

    def _save_config(self):
        """Persist config to disk."""
        try:
            _STATE_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "enabled": self.running,
                "tasks": self.tasks,
                "last_run": self._last_run,
                "updated_at": datetime.now().isoformat(),
            }
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("Failed to save scheduler config: %s", e)

    def _load_history(self):
        """Load execution history from disk."""
        try:
            if _HISTORY_PATH.exists():
                with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
        except Exception:
            self._history = []

    def _save_history(self):
        """Persist execution history to disk (capped at MAX_HISTORY)."""
        try:
            self._history = self._history[-MAX_HISTORY:]
            with open(_HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(self._history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("Failed to save scheduler history: %s", e)

    def _get_session(self):
        """Lazy-create a dedicated BrainSession for scheduler tasks."""
        if self._session is None:
            from brain_v9.core.session import BrainSession
            self._session = BrainSession("scheduler")
        return self._session

    def _is_due(self, task: Dict) -> bool:
        """Check if a task is due to run based on its interval."""
        if not task.get("enabled", True):
            return False
        task_id = task["id"]
        last = self._last_run.get(task_id, 0)
        interval_secs = task.get("interval_minutes", 60) * 60
        return (time.time() - last) >= interval_secs

    async def start(self):
        """Main scheduler loop — runs until self.running is set to False."""
        log.info("ProactiveScheduler starting (%d tasks configured)", len(self.tasks))

        # Initial delay — let the system fully boot before first checks
        await asyncio.sleep(60)

        while self.running:
            try:
                for task in self.tasks:
                    if not self.running:
                        break
                    if self._is_due(task):
                        await self._execute_task(task)
            except Exception as e:
                log.error("Scheduler loop error: %s", e, exc_info=True)

            await asyncio.sleep(self.CHECK_INTERVAL)

        log.info("ProactiveScheduler stopped")

    async def _execute_task(self, task: Dict):
        """Execute a single scheduled task via the agent."""
        task_id = task["id"]
        prompt = task["prompt"]
        log.info("Scheduler executing: [%s] %s", task_id, prompt[:60])

        start_time = time.time()
        # R9.1.2: per-task configurable timeout (seconds). Default 120s
        # for short check tasks; chat_excellence and other heavy LLM tasks
        # set this higher because the agent path explores 100+ tools.
        timeout_s = int(task.get("timeout_s", 120))
        # R10.0: Hard wall-clock guard. asyncio.wait_for() alone proved
        # insufficient — observed an 11766s "TIMEOUT" iter (chat_excellence
        # 2026-05-04 01:44) where the inner AgentLoop swallowed the
        # CancelledError and kept running. Now we issue an explicit
        # task.cancel() and wait at most `_CANCEL_GRACE_S` for it to die;
        # if it doesn't, we abandon the task object and continue. The
        # scheduler MUST never block more than (timeout_s + grace).
        _CANCEL_GRACE_S = 30
        try:
            session = self._get_session()
            inner = asyncio.create_task(
                session.chat(prompt, model_priority="agent_frontier"),
                name=f"sched-{task_id}",
            )
            try:
                result = await asyncio.wait_for(asyncio.shield(inner), timeout=timeout_s)
            except asyncio.TimeoutError:
                inner.cancel()
                try:
                    await asyncio.wait_for(inner, timeout=_CANCEL_GRACE_S)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                if not inner.done():
                    log.error(
                        "Scheduler [%s] inner task IGNORED cancel after %ds grace; abandoning (zombie)",
                        task_id, _CANCEL_GRACE_S,
                    )
                raise asyncio.TimeoutError()

            elapsed = time.time() - start_time
            success = result.get("success", False)
            response = result.get("response", "")[:500]

            log.info(
                "Scheduler [%s] done: success=%s, %.1fs, %d chars",
                task_id, success, elapsed, len(response),
            )

            # Record execution
            self._last_run[task_id] = time.time()
            self._history.append({
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
                "success": success,
                "elapsed_s": round(elapsed, 1),
                "response_preview": response[:200],
                "model_used": result.get("model_used", "unknown"),
            })

            self._save_config()
            self._save_history()

            # Check for anomalies in the response and flag if needed
            self._check_anomalies(task_id, result)

            # R9.1: Persist structured iteration for chat_excellence loop
            if task_id == "chat_excellence":
                self._persist_chat_excellence_iteration(result, elapsed, success)

        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            log.warning("Scheduler [%s] timed out after %.1fs", task_id, elapsed)
            self._last_run[task_id] = time.time()
            self._history.append({
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
                "success": False,
                "elapsed_s": round(elapsed, 1),
                "response_preview": "TIMEOUT",
                "model_used": "timeout",
            })
            self._save_config()
            self._save_history()

        except Exception as e:
            elapsed = time.time() - start_time
            log.error("Scheduler [%s] error: %s (%.1fs)", task_id, e, elapsed)
            self._last_run[task_id] = time.time()

    def _check_anomalies(self, task_id: str, result: Dict):
        """Flag anomalies found during scheduled checks.

        Writes to state/scheduler_alerts.json for the dashboard/user to review.
        """
        response = (result.get("response") or "").lower()

        alerts = []
        # Disk space alerts
        if task_id == "disk_space":
            if "90%" in response or "95%" in response or "99%" in response:
                alerts.append({"type": "disk_space_critical", "detail": "Disco usado >90%"})

        # Service down alerts
        if task_id == "services_health":
            if any(w in response for w in ["no responde", "caido", "fallo", "down", "error", "no está"]):
                alerts.append({"type": "service_down", "detail": "Servicio reportado como caído"})

        # Error alerts
        if task_id == "error_scan":
            if any(w in response for w in ["critical", "critico", "exception", "traceback"]):
                alerts.append({"type": "critical_error", "detail": "Errores críticos detectados en logs"})

        if alerts:
            self._persist_alerts(task_id, alerts)

    def _persist_alerts(self, task_id: str, alerts: List[Dict]):
        """Append alerts to the scheduler alerts file."""
        alerts_path = _STATE_DIR / "scheduler_alerts.json"
        try:
            existing = []
            if alerts_path.exists():
                with open(alerts_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)

            for alert in alerts:
                existing.append({
                    **alert,
                    "task_id": task_id,
                    "timestamp": datetime.now().isoformat(),
                    "acknowledged": False,
                })

            # Keep only last 50 alerts
            existing = existing[-50:]
            with open(alerts_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

            log.warning("Scheduler ALERT from [%s]: %s", task_id, alerts)

        except Exception as e:
            log.warning("Failed to persist scheduler alerts: %s", e)

    # ── R9.6: Alert acknowledgement ──────────────────────────────────────────

    def acknowledge_alerts(self,
                           indices: Optional[List[int]] = None,
                           alert_type: Optional[str] = None,
                           task_id: Optional[str] = None,
                           ack_all: bool = False,
                           actor: str = "dashboard") -> int:
        """Mark scheduler alerts as acknowledged.

        Filters (any combination, AND-composed):
          - indices: explicit positions in the persisted list
          - alert_type: only alerts whose 'type' matches
          - task_id: only alerts emitted by this task
          - ack_all: when True, ignore other filters and ack everything

        Returns the number of alerts newly acknowledged.
        """
        alerts_path = _STATE_DIR / "scheduler_alerts.json"
        if not alerts_path.exists():
            return 0
        try:
            with open(alerts_path, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception as e:
            log.warning("acknowledge_alerts: failed to read alerts: %s", e)
            return 0

        if not isinstance(items, list):
            return 0

        ts = datetime.now().isoformat()
        acked = 0
        idx_set = set(indices or [])
        for i, alert in enumerate(items):
            if alert.get("acknowledged"):
                continue
            if not ack_all:
                if indices is not None and i not in idx_set:
                    continue
                if alert_type is not None and alert.get("type") != alert_type:
                    continue
                if task_id is not None and alert.get("task_id") != task_id:
                    continue
            alert["acknowledged"] = True
            alert["acknowledged_at"] = ts
            alert["acknowledged_by"] = actor
            acked += 1

        if acked == 0:
            return 0

        try:
            with open(alerts_path, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
            log.info("acknowledge_alerts: %d alert(s) acked by %s", acked, actor)
        except Exception as e:
            log.warning("acknowledge_alerts: failed to persist: %s", e)
            return 0
        return acked

    # ── R9.1: Chat Excellence iteration persistence ──────────────────────────

    def _persist_chat_excellence_iteration(self, result: Dict, elapsed: float, success: bool):
        """Extract structured fields from chat_excellence response and append
        to state/chat_excellence_history.json. Robust to non-JSON responses
        (falls back to free-text capture)."""
        ce_path = _STATE_DIR / "chat_excellence_history.json"
        try:
            existing: List[Dict] = []
            if ce_path.exists():
                with open(ce_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)

            response_text = result.get("response", "") or ""
            parsed: Optional[Dict] = None

            # Try to extract JSON object from response (may be wrapped in ```json fences)
            import re
            json_match = re.search(r"\{[\s\S]*?\"weakness\"[\s\S]*?\}", response_text)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    # Try cleaning common issues (trailing commas, unescaped quotes)
                    cleaned = re.sub(r",(\s*[}\]])", r"\1", json_match.group(0))
                    try:
                        parsed = json.loads(cleaned)
                    except Exception:
                        parsed = None

            iteration = {
                "iter": len(existing) + 1,
                "timestamp": datetime.now().isoformat(),
                "elapsed_s": round(elapsed, 1),
                "success": success,
                "model_used": result.get("model_used", "unknown"),
                "parsed_ok": parsed is not None,
            }
            if parsed:
                # Accept both "root_cause_guess" (current prompt schema) and
                # legacy "root_cause_hypothesis" for backward compat with any
                # historical iteration that used the old key.
                root_cause = (parsed.get("root_cause_guess")
                              or parsed.get("root_cause_hypothesis", ""))
                # R10.0b: Validate affected_files against actual filesystem to
                # catch hallucinated paths (e.g., "brain_chat_server.py",
                # "config/circuit_breaker.py" — the LLM tends to invent
                # plausible-sounding names). We resolve relative paths against
                # brain_v9/ and check existence; entries that don't exist are
                # logged in `affected_files_invalid`. Note: this does NOT block
                # the iteration; it just surfaces the warning so a future
                # executor (R10.2) can refuse to act on bad paths.
                raw_files = parsed.get("affected_files") or []
                if not isinstance(raw_files, list):
                    raw_files = [str(raw_files)]
                _BRAIN_ROOT = Path(__file__).resolve().parent.parent  # brain_v9/
                _AI_VAULT = _BRAIN_ROOT.parent.parent  # C:/AI_VAULT
                af_valid: List[str] = []
                af_invalid: List[str] = []
                for raw in raw_files:
                    s = str(raw).strip().strip('"').strip("'")
                    if not s:
                        continue
                    candidates = [
                        Path(s),
                        _BRAIN_ROOT / s,
                        _AI_VAULT / s,
                        _AI_VAULT / "tmp_agent" / s,
                    ]
                    if any(c.exists() for c in candidates):
                        af_valid.append(s)
                    else:
                        af_invalid.append(s)
                iteration.update({
                    "weakness": parsed.get("weakness", ""),
                    "impact_score": parsed.get("impact_score"),
                    "root_cause_guess": root_cause,
                    "proposed_change": parsed.get("proposed_change", ""),
                    "test_plan": parsed.get("test_plan", ""),
                    "expected_improvement": parsed.get("expected_improvement", ""),
                    "affected_files": af_valid,
                    "affected_files_invalid": af_invalid,
                    "affected_files_validated": True,
                    "status": parsed.get("status", "documented"),
                })
                if af_invalid:
                    log.warning(
                        "ChatExcellence iter affected_files_invalid (hallucinated): %s",
                        af_invalid,
                    )
            else:
                iteration["raw_response"] = response_text[:1500]
                iteration["status"] = "unparsed"

            existing.append(iteration)
            existing = existing[-100:]  # cap at 100 iterations

            with open(ce_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

            log.info("ChatExcellence iter #%d persisted (parsed=%s, weakness=%s)",
                     iteration["iter"], iteration["parsed_ok"],
                     (iteration.get("weakness") or "")[:60])

            # R10.2: Forward to executor (gate evaluation + proposal file).
            # Executor is import-isolated so any failure there doesn't break
            # iteration persistence.
            try:
                from brain_v9.autonomy.chat_excellence_executor import evaluate_iteration
                evaluate_iteration(iteration)
            except Exception as ex:
                log.warning("ChatExcellence executor failed (non-fatal): %s", ex)

        except Exception as e:
            log.warning("Failed to persist chat_excellence iteration: %s", e)

    # ── Public API (for slash commands) ──────────────────────────────────────

    def get_status(self) -> str:
        """Return human-readable scheduler status."""
        lines = [f"Scheduler: {'ACTIVO' if self.running else 'PAUSADO'}"]
        lines.append(f"Tasks: {len(self.tasks)} configuradas\n")

        for t in self.tasks:
            status = "ON" if t.get("enabled") else "OFF"
            last = self._last_run.get(t["id"])
            if last:
                ago = int(time.time() - last)
                mins = ago // 60
                last_str = f"hace {mins}m" if mins > 0 else "hace <1m"
            else:
                last_str = "nunca"
            lines.append(
                f"  [{status}] {t['id']} — cada {t.get('interval_minutes', '?')}m — "
                f"última: {last_str} — {t.get('description', '')}"
            )

        # Recent history
        if self._history:
            lines.append(f"\nÚltimas {min(5, len(self._history))} ejecuciones:")
            for h in self._history[-5:]:
                ok = "OK" if h.get("success") else "FALLO"
                lines.append(
                    f"  [{ok}] {h['task_id']} @ {h.get('timestamp', '?')[:16]} "
                    f"({h.get('elapsed_s', '?')}s)"
                )

        # Alerts
        alerts_path = _STATE_DIR / "scheduler_alerts.json"
        if alerts_path.exists():
            try:
                with open(alerts_path, "r", encoding="utf-8") as f:
                    alerts = json.load(f)
                unack = [a for a in alerts if not a.get("acknowledged")]
                if unack:
                    lines.append(f"\nALERTAS sin reconocer: {len(unack)}")
                    for a in unack[-3:]:
                        lines.append(f"  [{a['type']}] {a.get('detail', '')} @ {a.get('timestamp', '')[:16]}")
            except Exception:
                pass

        return "\n".join(lines)

    def enable(self):
        """Enable the scheduler."""
        self.running = True
        self._save_config()
        return "Scheduler activado"

    def disable(self):
        """Disable the scheduler (pause)."""
        self.running = False
        self._save_config()
        return "Scheduler pausado"

    def enable_task(self, task_id: str) -> str:
        """Enable a specific task."""
        for t in self.tasks:
            if t["id"] == task_id:
                t["enabled"] = True
                self._save_config()
                return f"Task '{task_id}' activada"
        return f"Task '{task_id}' no encontrada"

    def disable_task(self, task_id: str) -> str:
        """Disable a specific task."""
        for t in self.tasks:
            if t["id"] == task_id:
                t["enabled"] = False
                self._save_config()
                return f"Task '{task_id}' desactivada"
        return f"Task '{task_id}' no encontrada"

    def add_task(self, task_id: str, prompt: str, interval_minutes: int = 60,
                 description: str = "") -> str:
        """Add a new scheduled task."""
        # Check for duplicate
        for t in self.tasks:
            if t["id"] == task_id:
                return f"Task '{task_id}' ya existe. Usa otro ID."

        self.tasks.append({
            "id": task_id,
            "prompt": prompt,
            "interval_minutes": interval_minutes,
            "enabled": True,
            "description": description or prompt[:60],
        })
        self._save_config()
        return f"Task '{task_id}' agregada (cada {interval_minutes}m)"

    def remove_task(self, task_id: str) -> str:
        """Remove a scheduled task."""
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks if t["id"] != task_id]
        if len(self.tasks) < before:
            self._last_run.pop(task_id, None)
            self._save_config()
            return f"Task '{task_id}' eliminada"
        return f"Task '{task_id}' no encontrada"

    def run_now(self, task_id: str) -> Optional[Dict]:
        """Force-run a task immediately (returns the task dict or None)."""
        for t in self.tasks:
            if t["id"] == task_id:
                # Reset last_run to force execution on next check
                self._last_run.pop(task_id, None)
                return t
        return None


# ── Module-level singleton ───────────────────────────────────────────────────

_instance: Optional[ProactiveScheduler] = None


def get_proactive_scheduler() -> ProactiveScheduler:
    """Get or create the global ProactiveScheduler instance."""
    global _instance
    if _instance is None:
        _instance = ProactiveScheduler()
    return _instance
