# sandbox_logger.py
# Logger NDJSON para Dev Sandbox (C:\AI_VAULT\tmp_agent)
# - Append-only
# - Eventos con ts ISO8601 UTC
# - No depende de libs externas

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class SandboxLogger:
    log_path: str
    run_id: str

    def __post_init__(self) -> None:
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    def emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        evt = {
            "ts": utc_now_iso(),
            "type": event_type,
            "run_id": self.run_id,
            "data": data or {},
        }
        line = json.dumps(evt, ensure_ascii=False)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def span(self, name: str, data: Optional[Dict[str, Any]] = None) -> "Span":
        return Span(logger=self, name=name, data=data or {})


@dataclass
class Span:
    logger: SandboxLogger
    name: str
    data: Dict[str, Any]
    t0: float = 0.0

    def __enter__(self) -> "Span":
        self.t0 = time.time()
        self.logger.emit("span_start", {"name": self.name, **self.data})
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        dt_ms = int((time.time() - self.t0) * 1000)
        payload = {"name": self.name, "dt_ms": dt_ms, **self.data}
        if exc is not None:
            payload["ok"] = False
            payload["error"] = f"{exc_type.__name__}: {exc}"
            self.logger.emit("span_end", payload)
            return False
        payload["ok"] = True
        self.logger.emit("span_end", payload)
        return False
