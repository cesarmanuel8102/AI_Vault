"""
Brain Chat V9 — core/knowledge.py
==================================
Phase C: CodebaseRAG — lightweight keyword/TF-IDF retrieval over brain_v9/ .py files.
Phase D: EpisodicMemory — persistent key-value memory with keyword recall.

Zero external dependencies — uses only Python stdlib (Counter, math, re, json).
"""
import json
import logging
import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from brain_v9.config import BASE_PATH

log = logging.getLogger("knowledge")

# ═══════════════════════════════════════════════════════════════════════════════
# Phase C — CodebaseRAG
# ═══════════════════════════════════════════════════════════════════════════════

_STOP_WORDS = frozenset({
    "self", "none", "true", "false", "import", "from", "return", "def", "class",
    "async", "await", "for", "while", "with", "try", "except", "finally",
    "if", "elif", "else", "and", "or", "not", "in", "is", "as", "pass",
    "raise", "yield", "lambda", "continue", "break", "del", "global",
    "nonlocal", "assert", "the", "a", "an", "of", "to", "str", "int",
    "float", "dict", "list", "bool", "any", "all", "set", "type",
    "optional", "typing", "callable", "tuple",
})

# Regex: split on non-alphanumeric, underscore-separated, camelCase
_TOKEN_RE = re.compile(r"[a-z][a-z0-9]*|[A-Z][a-z0-9]*|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[a-z0-9]+", re.ASCII)


def _tokenize(text: str) -> List[str]:
    """Extract lowercase tokens from source code, splitting camelCase and snake_case."""
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) > 2 and t.lower() not in _STOP_WORDS]


class CodebaseRAG:
    """Lightweight TF-IDF retrieval over Python files in the brain_v9 codebase.

    - Scans brain_v9/**/*.py on first use
    - Caches index for `cache_ttl` seconds (default 3600 = 1 hour)
    - No external dependencies
    """

    def __init__(self, root: Optional[Path] = None, cache_ttl: int = 3600):
        self._root = root or (BASE_PATH / "tmp_agent" / "brain_v9")
        self._cache_ttl = cache_ttl
        self._last_index_time: float = 0.0
        # Per-file data: {rel_path: {"tokens": Counter, "summary": str, "lines": int}}
        self._docs: Dict[str, Dict] = {}
        # IDF values: {token: idf_score}
        self._idf: Dict[str, float] = {}
        self._total_docs: int = 0

    def _needs_reindex(self) -> bool:
        return (time.time() - self._last_index_time) > self._cache_ttl

    def _index(self) -> None:
        """Scan all .py files and build TF-IDF index."""
        t0 = time.time()
        self._docs.clear()
        self._idf.clear()

        py_files = list(self._root.rglob("*.py"))
        # Skip __pycache__, .backup files, test fixtures
        py_files = [
            f for f in py_files
            if "__pycache__" not in str(f) and ".backup" not in f.name
        ]

        doc_freq: Counter = Counter()  # token -> number of docs containing it

        for fpath in py_files:
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel = str(fpath.relative_to(self._root)).replace("\\", "/")
            tokens = _tokenize(text)
            tf = Counter(tokens)

            # Build a compact summary: first docstring or first 3 non-empty lines
            lines = text.splitlines()
            summary_lines = []
            in_docstring = False
            for line in lines[:50]:
                stripped = line.strip()
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    if in_docstring:
                        break
                    in_docstring = True
                    content = stripped[3:]
                    if content.endswith('"""') or content.endswith("'''"):
                        summary_lines.append(content[:-3].strip())
                        break
                    if content:
                        summary_lines.append(content)
                    continue
                if in_docstring:
                    if stripped.endswith('"""') or stripped.endswith("'''"):
                        summary_lines.append(stripped[:-3].strip())
                        break
                    summary_lines.append(stripped)
                elif stripped and not stripped.startswith("#") and not stripped.startswith("import") and not stripped.startswith("from"):
                    if len(summary_lines) < 3:
                        summary_lines.append(stripped)

            self._docs[rel] = {
                "tokens": tf,
                "summary": " ".join(summary_lines)[:200],
                "lines": len(lines),
                "path": str(fpath),
            }

            # Update document frequency
            for token in set(tf.keys()):
                doc_freq[token] += 1

        self._total_docs = len(self._docs)

        # Compute IDF: log(N / df)
        for token, df in doc_freq.items():
            self._idf[token] = math.log((self._total_docs + 1) / (df + 1))

        self._last_index_time = time.time()
        elapsed = time.time() - t0
        log.info("CodebaseRAG indexed %d files in %.2fs", self._total_docs, elapsed)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """Return the top_k most relevant files for a query.

        Returns list of {path, rel_path, score, summary, lines}.
        """
        if self._needs_reindex():
            self._index()

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        query_tf = Counter(query_tokens)
        scores: List[Tuple[str, float]] = []

        for rel, doc in self._docs.items():
            score = 0.0
            doc_tf = doc["tokens"]
            doc_total = sum(doc_tf.values()) or 1
            for token, qtf in query_tf.items():
                if token in doc_tf:
                    tf = doc_tf[token] / doc_total
                    idf = self._idf.get(token, 0.0)
                    score += tf * idf * qtf
            if score > 0:
                scores.append((rel, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for rel, score in scores[:top_k]:
            doc = self._docs[rel]
            results.append({
                "rel_path": rel,
                "path": doc["path"],
                "score": round(score, 4),
                "summary": doc["summary"],
                "lines": doc["lines"],
            })
        return results

    def get_context_for_query(self, query: str, top_k: int = 5) -> str:
        """Return a formatted context string for injection into the agent prompt."""
        results = self.retrieve(query, top_k=top_k)
        if not results:
            return ""

        lines = ["CONTEXTO DEL CODEBASE (archivos relevantes):"]
        for r in results:
            lines.append(f"  - {r['rel_path']} ({r['lines']} lineas, score={r['score']}): {r['summary']}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase D — EpisodicMemory
# ═══════════════════════════════════════════════════════════════════════════════

_MEMORY_PATH = BASE_PATH / "tmp_agent" / "state" / "episodic_memory.json"
_MAX_ENTRIES = 500


class EpisodicMemory:
    """Persistent episodic memory with keyword-based recall.

    Entry types: discovery, decision, error, fact, task_result
    Stored in state/episodic_memory.json.
    """

    def __init__(self, path: Optional[Path] = None, max_entries: int = _MAX_ENTRIES):
        self._path = path or _MEMORY_PATH
        self._max_entries = max_entries
        self._entries: List[Dict] = []
        self._loaded = False

    def _load(self) -> None:
        """Load entries from disk."""
        if self._loaded:
            return
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._entries = data if isinstance(data, list) else data.get("entries", [])
        except Exception as exc:
            log.warning("Failed to load episodic memory: %s", exc)
            self._entries = []
        self._loaded = True

    def _save(self) -> None:
        """Persist entries to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning("Failed to save episodic memory: %s", exc)

    def add(self, entry_type: str, content: str, keywords: Optional[List[str]] = None) -> Dict:
        """Add a memory entry.

        Args:
            entry_type: discovery | decision | error | fact | task_result
            content: The text content of the memory
            keywords: Optional list of keywords for recall matching

        Returns:
            The created entry dict.
        """
        self._load()
        entry = {
            "id": len(self._entries) + 1,
            "type": entry_type,
            "content": content,
            "keywords": keywords or [],
            "timestamp": datetime.now().isoformat(),
        }
        self._entries.append(entry)

        # Auto-trim: remove oldest entries if over limit
        if len(self._entries) > self._max_entries:
            trim_count = len(self._entries) - self._max_entries
            self._entries = self._entries[trim_count:]

        self._save()
        return entry

    def recall(self, query: str, max_results: int = 5, max_age_hours: Optional[float] = None) -> List[Dict]:
        """Recall memories matching a query.

        Uses keyword matching + recency bonus.
        """
        self._load()
        if not self._entries:
            return []

        query_tokens = set(_tokenize(query))
        if not query_tokens:
            # Return most recent entries
            return self._entries[-max_results:]

        scored: List[Tuple[int, float, Dict]] = []
        now = time.time()

        for i, entry in enumerate(self._entries):
            # Keyword match score
            entry_keywords = set(k.lower() for k in entry.get("keywords", []))
            content_tokens = set(_tokenize(entry.get("content", "")))
            all_tokens = entry_keywords | content_tokens

            overlap = query_tokens & all_tokens
            if not overlap:
                continue

            keyword_score = len(overlap) / max(len(query_tokens), 1)

            # Recency bonus: entries from last hour get +0.3, last day +0.1
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"]).timestamp()
                age_hours = (now - entry_time) / 3600
                if max_age_hours is not None and age_hours > max_age_hours:
                    continue
                recency_bonus = 0.3 if age_hours < 1 else (0.1 if age_hours < 24 else 0.0)
            except Exception:
                recency_bonus = 0.0

            # Type bonus: task_result and error are more useful
            type_bonus = 0.1 if entry.get("type") in ("task_result", "error") else 0.0

            total_score = keyword_score + recency_bonus + type_bonus
            scored.append((i, total_score, entry))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [item[2] for item in scored[:max_results]]

    def get_context_for_query(self, query: str, max_results: int = 3, max_age_hours: Optional[float] = None) -> str:
        """Return formatted memory context for injection into agent prompt."""
        memories = self.recall(query, max_results=max_results, max_age_hours=max_age_hours)
        if not memories:
            return ""

        lines = ["MEMORIA EPISODICA HISTORICA (usar como referencia, no como evidencia actual):"]
        for m in memories:
            ts = m.get("timestamp", "?")[:16]
            mtype = m.get("type", "?")
            content = m.get("content", "")[:150]
            lines.append(f"  [{ts}] ({mtype}) {content}")
        return "\n".join(lines)

    def get_stats(self) -> Dict:
        """Return memory statistics."""
        self._load()
        type_counts: Counter = Counter()
        duplicate_keys = set()
        seen_keys = set()
        oldest_ts: Optional[str] = None
        newest_ts: Optional[str] = None
        for entry in self._entries:
            type_counts[entry.get("type", "unknown")] += 1
            key = self._entry_dedupe_key(entry)
            if key in seen_keys:
                duplicate_keys.add(key)
            else:
                seen_keys.add(key)
            ts = self._safe_iso(entry.get("timestamp"))
            if ts:
                oldest_ts = ts if oldest_ts is None or ts < oldest_ts else oldest_ts
                newest_ts = ts if newest_ts is None or ts > newest_ts else newest_ts
        return {
            "total_entries": len(self._entries),
            "max_entries": self._max_entries,
            "by_type": dict(type_counts),
            "path": str(self._path),
            "duplicate_exact_count": len(duplicate_keys),
            "oldest_timestamp": oldest_ts,
            "newest_timestamp": newest_ts,
        }

    def compact(
        self,
        *,
        max_age_hours: Optional[float] = 24.0 * 30.0 * 6.0,
        keep_recent: int = 120,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Compact episodic memory safely.

        Strategy:
        - preserve the most recent `keep_recent` entries regardless of age
        - remove exact duplicates, keeping the newest copy
        - prune older entries past `max_age_hours` outside the recent window
        - rewrite ids sequentially when applying
        """
        self._load()
        before = list(self._entries)
        total_before = len(before)
        keep_recent = max(0, int(keep_recent))
        recent_threshold = max(0, total_before - keep_recent)
        now = time.time()

        keep_flags = [True] * total_before
        removal_reasons: Counter = Counter()
        seen_keys = set()

        for idx in range(total_before - 1, -1, -1):
            entry = before[idx]
            key = self._entry_dedupe_key(entry)
            if key in seen_keys:
                keep_flags[idx] = False
                removal_reasons["duplicate_exact"] += 1
                continue
            seen_keys.add(key)

            if idx >= recent_threshold:
                continue

            age_hours = self._entry_age_hours(entry, now)
            if max_age_hours is not None and age_hours is not None and age_hours > max_age_hours:
                keep_flags[idx] = False
                removal_reasons["stale_age"] += 1

        compacted = [entry for idx, entry in enumerate(before) if keep_flags[idx]]
        repaired: List[Dict[str, Any]] = []
        for new_id, entry in enumerate(compacted, start=1):
            fixed = dict(entry)
            fixed["id"] = new_id
            repaired.append(fixed)

        report = {
            "ok": True,
            "dry_run": dry_run,
            "before": self.get_stats(),
            "after": self._stats_for_entries(repaired),
            "removed_total": total_before - len(repaired),
            "removal_reasons": dict(removal_reasons),
            "keep_recent": keep_recent,
            "max_age_hours": max_age_hours,
        }

        if not dry_run:
            self._entries = repaired
            self._save()
        return report

    @staticmethod
    def _safe_iso(timestamp: Any) -> Optional[str]:
        raw = str(timestamp or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw).isoformat()
        except Exception:
            return None

    @classmethod
    def _entry_age_hours(cls, entry: Dict[str, Any], now_ts: Optional[float] = None) -> Optional[float]:
        try:
            now_ts = now_ts if now_ts is not None else time.time()
            entry_time = datetime.fromisoformat(str(entry.get("timestamp", ""))).timestamp()
            return (now_ts - entry_time) / 3600.0
        except Exception:
            return None

    @staticmethod
    def _entry_dedupe_key(entry: Dict[str, Any]) -> Tuple[str, str]:
        return (
            str(entry.get("type", "")).strip().lower(),
            re.sub(r"\s+", " ", str(entry.get("content", "")).strip().lower()),
        )

    def _stats_for_entries(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        type_counts: Counter = Counter()
        duplicate_keys = set()
        seen_keys = set()
        oldest_ts: Optional[str] = None
        newest_ts: Optional[str] = None
        for entry in entries:
            type_counts[entry.get("type", "unknown")] += 1
            key = self._entry_dedupe_key(entry)
            if key in seen_keys:
                duplicate_keys.add(key)
            else:
                seen_keys.add(key)
            ts = self._safe_iso(entry.get("timestamp"))
            if ts:
                oldest_ts = ts if oldest_ts is None or ts < oldest_ts else oldest_ts
                newest_ts = ts if newest_ts is None or ts > newest_ts else newest_ts
        return {
            "total_entries": len(entries),
            "max_entries": self._max_entries,
            "by_type": dict(type_counts),
            "path": str(self._path),
            "duplicate_exact_count": len(duplicate_keys),
            "oldest_timestamp": oldest_ts,
            "newest_timestamp": newest_ts,
        }
