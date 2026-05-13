"""
Brain Chat V9 — MemoryManager
Extraído de V8.0 sin cambios en la lógica.
Memoria de 3 niveles: corto plazo, largo plazo, sistema.
"""
import asyncio
import json
import logging
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from brain_v9.config import MEMORY_PATH


class MemoryManager:
    def __init__(self, session_id: str = "default"):
        self.session_id  = session_id
        self.memory_dir  = MEMORY_PATH / session_id
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.logger      = logging.getLogger(f"MemoryManager.{session_id}")

        self.short_term: deque = deque(maxlen=50)
        self.long_term:  List  = []
        self.message_count     = 0
        self.messages_since_summary = 0
        self.system_state: Dict = {
            "session_start": datetime.now().isoformat(),
            "active_tools":  [],
        }
        self._load()

    # ── Pública ───────────────────────────────────────────────────────────────
    def save(self, message: Dict):
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()
        self.short_term.append(message)
        self.message_count += 1
        self.messages_since_summary += 1
        self._save_short_term()
        if self.messages_since_summary >= 5:
            asyncio.create_task(self._summarize())

    def get_context(self) -> List[Dict]:
        """Retorna historial reciente como lista de mensajes."""
        return [{"role": m["role"], "content": m["content"]}
                for m in self.short_term]

    def clear(self, memory_type: str = "all"):
        if memory_type in ("short", "all"):
            self.short_term.clear()
            self._save_short_term()
        if memory_type in ("long", "all"):
            self.long_term = []
            self._save_long_term()

    # ── Persistencia ──────────────────────────────────────────────────────────
    def _path(self, kind: str) -> Path:
        return self.memory_dir / f"{kind}.json"

    def _load(self):
        try:
            p = self._path("short_term")
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                self.short_term.extend(d.get("messages", []))
                self.message_count = d.get("count", 0)
            p = self._path("long_term")
            if p.exists():
                self.long_term = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            self.logger.error("Error cargando memoria: %s", e)

    def _save_short_term(self):
        try:
            self._path("short_term").write_text(
                json.dumps({
                    "messages":     list(self.short_term),
                    "count":        self.message_count,
                    "last_updated": datetime.now().isoformat(),
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            self.logger.error("Error guardando memoria corto plazo: %s", e)

    def _save_long_term(self):
        try:
            self._path("long_term").write_text(
                json.dumps(self.long_term, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            self.logger.error("Error guardando memoria largo plazo: %s", e)

    async def _summarize(self):
        """Genera un resumen cada 5 mensajes (placeholder — conectar LLM si se desea)."""
        self.messages_since_summary = 0
        summary = {
            "timestamp": datetime.now().isoformat(),
            "messages":  list(self.short_term),
        }
        self.long_term.append(summary)
        self._save_long_term()
