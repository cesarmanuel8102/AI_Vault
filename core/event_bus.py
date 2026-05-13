"""
CORE/EVENT_BUS.PY - Bus de Eventos Asincrono
Desacopla componentes mediante pub/sub. Soporta sync y async handlers.
Persistencia opcional para event sourcing.
"""
import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

EVENT_LOG = Path("C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl")
EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("EventBus")
Handler = Union[Callable[..., Any], Callable[..., Awaitable[Any]]]


@dataclass
class Event:
    name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    ts: str = field(default_factory=lambda: datetime.now().isoformat())
    event_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d%H%M%S%f"))


class EventBus:
    """Bus de eventos in-process con persistencia opcional."""

    def __init__(self, persist: bool = True):
        self._subs: Dict[str, List[Handler]] = defaultdict(list)
        self._wildcard: List[Handler] = []
        self.persist = persist
        self._lock = asyncio.Lock()

    def subscribe(self, event_name: str, handler: Handler):
        if event_name == "*":
            self._wildcard.append(handler)
        else:
            self._subs[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: Handler):
        if event_name == "*":
            self._wildcard = [h for h in self._wildcard if h is not handler]
        else:
            self._subs[event_name] = [h for h in self._subs[event_name] if h is not handler]

    def _persist(self, event: Event):
        if not self.persist:
            return
        try:
            with EVENT_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event)) + "\n")
        except Exception as e:
            log.error("persist event failed: %s", e)

    async def publish(self, event_name: str, payload: Optional[Dict[str, Any]] = None,
                      source: str = "unknown") -> List[Any]:
        event = Event(name=event_name, payload=payload or {}, source=source)
        self._persist(event)
        handlers = list(self._subs.get(event_name, [])) + list(self._wildcard)
        results = []
        for h in handlers:
            try:
                if asyncio.iscoroutinefunction(h):
                    results.append(await h(event))
                else:
                    results.append(h(event))
            except Exception as e:
                log.error("handler error in %s: %s", event_name, e)
                results.append({"error": str(e)})
        return results

    def publish_sync(self, event_name: str, payload: Optional[Dict[str, Any]] = None,
                     source: str = "unknown") -> List[Any]:
        """Variante sincrona; ejecuta handlers async en loop nuevo si es necesario."""
        event = Event(name=event_name, payload=payload or {}, source=source)
        self._persist(event)
        handlers = list(self._subs.get(event_name, [])) + list(self._wildcard)
        results = []
        for h in handlers:
            try:
                if asyncio.iscoroutinefunction(h):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(h(event))
                            results.append({"scheduled": True})
                        else:
                            results.append(loop.run_until_complete(h(event)))
                    except RuntimeError:
                        results.append(asyncio.run(h(event)))
                else:
                    results.append(h(event))
            except Exception as e:
                log.error("sync handler error %s: %s", event_name, e)
                results.append({"error": str(e)})
        return results

    def replay(self, since: Optional[str] = None, limit: int = 1000) -> List[Event]:
        """Lee eventos persistidos para event sourcing/auditoria."""
        if not EVENT_LOG.exists():
            return []
        events = []
        try:
            for line in EVENT_LOG.read_text(encoding="utf-8").splitlines()[-limit:]:
                if not line.strip():
                    continue
                d = json.loads(line)
                if since and d.get("ts", "") < since:
                    continue
                events.append(Event(**d))
        except Exception as e:
            log.error("replay error: %s", e)
        return events


_BUS: Optional[EventBus] = None

def get_bus() -> EventBus:
    global _BUS
    if _BUS is None:
        _BUS = EventBus(persist=True)
        log.info(f"[EventBus] Created singleton instance id={id(_BUS)}")
    return _BUS
