"""
Brain Chat V9 — MemoryManager v3 (LLM Summarisation)
=====================================================
Changes from v2:
  - save() is now async to support LLM-based summarisation
  - _snapshot_summary() calls LLM to produce a real conversation summary
  - Accepts optional LLMManager via set_llm() (no LLM = metadata-only fallback)
  - _build_summary_prompt() formats recent messages into a compact prompt
  - Graceful degradation: if LLM fails, stores metadata-only summary

Preserved from v2:
  - state_io persistence (file locking, atomic writes, corruption recovery)
  - long_term capped at MAX_LONG_TERM_ENTRIES
  - short_term capped at MAX_SHORT_TERM via deque
"""
import logging
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

import brain_v9.config as _cfg
from brain_v9.core.state_io import read_json, write_json

if TYPE_CHECKING:
    from brain_v9.core.llm import LLMManager

MAX_SHORT_TERM = 100       # max messages in the deque
MAX_LONG_TERM_ENTRIES = 50  # max summary snapshots kept on disk

# How many recent messages to feed the summariser (keeps prompt small)
_SUMMARY_WINDOW = 20

# Max characters per message fed to summariser (tail-truncate long ones)
_SUMMARY_MSG_MAX_CHARS = 400


class MemoryManager:
    def __init__(self, session_id: str = "default"):
        self.session_id  = session_id
        self.memory_dir  = _cfg.MEMORY_PATH / session_id
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.logger      = logging.getLogger(f"MemoryManager.{session_id}")

        self.short_term: deque = deque(maxlen=MAX_SHORT_TERM)
        self.long_term:  List  = []
        self.message_count     = 0
        self.messages_since_summary = 0
        self._llm: Optional["LLMManager"] = None
        self.system_state: Dict = {
            "session_start": datetime.now().isoformat(),
            "active_tools":  [],
        }
        self._load()

    def set_llm(self, llm: "LLMManager"):
        """Inject the LLMManager after construction (avoids circular imports)."""
        self._llm = llm

    # ── Public API ────────────────────────────────────────────────────────────

    async def save(self, message: Dict):
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()
        self.short_term.append(message)
        self.message_count += 1
        self.messages_since_summary += 1
        self._save_short_term()
        if self.messages_since_summary >= 20:
            await self._snapshot_summary()

    def get_context(self) -> List[Dict]:
        """Return recent history as a list of {role, content} dicts."""
        return [{"role": m["role"], "content": m["content"]}
                for m in self.short_term
                if "role" in m and "content" in m]

    def clear(self, memory_type: str = "all"):
        if memory_type in ("short", "all"):
            self.short_term.clear()
            self.message_count = 0
            self.messages_since_summary = 0
            self._save_short_term()
        if memory_type in ("long", "all"):
            self.long_term = []
            self._save_long_term()

    # ── Persistence (via state_io) ────────────────────────────────────────────

    def _path(self, kind: str) -> Path:
        return self.memory_dir / f"{kind}.json"

    def _load(self):
        # Short-term
        st_data = read_json(self._path("short_term"), default={})
        if isinstance(st_data, dict):
            msgs = st_data.get("messages", [])
            if isinstance(msgs, list):
                self.short_term.extend(msgs)
            self.message_count = st_data.get("count", len(self.short_term))
        # Long-term
        lt_data = read_json(self._path("long_term"), default=[])
        if isinstance(lt_data, list):
            self.long_term = lt_data[-MAX_LONG_TERM_ENTRIES:]

    def _save_short_term(self):
        payload = {
            "messages":     list(self.short_term),
            "count":        self.message_count,
            "last_updated": datetime.now().isoformat(),
        }
        ok = write_json(self._path("short_term"), payload)
        if not ok:
            self.logger.error("Failed to save short-term memory for session '%s'", self.session_id)

    def _save_long_term(self):
        ok = write_json(self._path("long_term"), self.long_term)
        if not ok:
            self.logger.error("Failed to save long-term memory for session '%s'", self.session_id)

    # ── LLM-Based Summarisation ───────────────────────────────────────────────

    @staticmethod
    def _build_summary_prompt(messages: List[Dict]) -> str:
        """Build a compact prompt for the LLM to summarise recent messages.

        Takes the last _SUMMARY_WINDOW messages, truncates long ones, and
        asks for a 2-3 sentence summary covering topics discussed, decisions
        made, and any unresolved questions.
        """
        window = messages[-_SUMMARY_WINDOW:]
        lines = []
        for m in window:
            role = m.get("role", "?")
            content = m.get("content", "")
            if len(content) > _SUMMARY_MSG_MAX_CHARS:
                content = content[:_SUMMARY_MSG_MAX_CHARS] + "..."
            lines.append(f"[{role}] {content}")

        conversation = "\n".join(lines)
        return (
            "Summarise the following conversation in 2-3 sentences. "
            "Cover: topics discussed, decisions made, and any unresolved questions. "
            "Be concise and factual.\n\n"
            f"{conversation}\n\n"
            "SUMMARY:"
        )

    async def _snapshot_summary(self):
        """
        Generate a conversation summary and store it in long_term memory.

        If an LLMManager is available, sends recent messages to the LLM
        for a real summary.  On failure (or no LLM), falls back to a
        metadata-only snapshot.
        """
        self.messages_since_summary = 0

        summary_text = None
        if self._llm is not None:
            try:
                messages_list = list(self.short_term)
                if messages_list:
                    prompt = self._build_summary_prompt(messages_list)
                    result = await self._llm.query(
                        [{"role": "user", "content": prompt}],
                        model_priority="chat",
                    )
                    if result.get("success") and result.get("content"):
                        summary_text = result["content"].strip()
                        # Guard against empty or very short responses
                        if len(summary_text) < 10:
                            summary_text = None
            except Exception as e:
                self.logger.warning(
                    "LLM summarisation failed for session '%s': %s",
                    self.session_id, e,
                )

        summary = {
            "timestamp":     datetime.now().isoformat(),
            "message_count": self.message_count,
            "turn_count":    len(self.short_term),
        }

        if summary_text:
            summary["summary"] = summary_text
            summary["source"] = "llm"
        else:
            summary["note"] = "metadata-only (LLM unavailable)"
            summary["source"] = "fallback"

        self.long_term.append(summary)
        # Cap long-term
        if len(self.long_term) > MAX_LONG_TERM_ENTRIES:
            self.long_term = self.long_term[-MAX_LONG_TERM_ENTRIES:]
        self._save_long_term()
