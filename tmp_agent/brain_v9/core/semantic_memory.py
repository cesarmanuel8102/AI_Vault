"""
Persistent semantic memory for Brain V9.

This module provides a dependency-light vector store under C:\\AI_VAULT\\memory\\semantic.
It uses deterministic hashed lexical embeddings with numpy so it works without
Chroma/FAISS/sentence-transformers. The public API is intentionally small so the
backend can later be replaced by Chroma/FAISS without changing callers.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

from brain_v9.config import BASE_PATH, STATE_PATH


SEMANTIC_ROOT = BASE_PATH / "memory" / "semantic"
RECORDS_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
INDEX_PATH = SEMANTIC_ROOT / "semantic_memory_index.npz"
STATUS_PATH = STATE_PATH / "semantic_memory_status.json"
DEFAULT_DIMS = 1024
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_áéíóúüñÁÉÍÓÚÜÑ]{2,}")


@dataclass
class SemanticRecord:
    id: str
    created_utc: str
    source: str
    session_id: str
    kind: str
    text: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_utc": self.created_utc,
            "source": self.source,
            "session_id": self.session_id,
            "kind": self.kind,
            "text": self.text,
            "metadata": self.metadata,
        }


class SemanticMemory:
    """Small persistent vector store for cross-session recall."""

    def __init__(self, root: Path | None = None, dims: int = DEFAULT_DIMS):
        self.root = Path(root or SEMANTIC_ROOT)
        self.records_path = self.root / RECORDS_PATH.name
        self.index_path = self.root / INDEX_PATH.name
        self.status_path = STATUS_PATH
        self.dims = int(dims)
        self.root.mkdir(parents=True, exist_ok=True)
        self.status_path.parent.mkdir(parents=True, exist_ok=True)

    def status(self) -> Dict[str, Any]:
        records = self._read_records()
        status = {
            "ok": True,
            "backend": "hashing_vector_store_numpy",
            "backend_class": "SemanticMemory",
            "dims": self.dims,
            "records": len(records),
            "root": str(self.root),
            "records_path": str(self.records_path),
            "index_path": str(self.index_path),
            "index_exists": self.index_path.exists(),
            "chromadb_available": False,
            "faiss_available": False,
            "limitations": [
                "Embeddings deterministas por hashing lexical; no son embeddings neuronales.",
                "Suficiente para recall semántico inicial y recuperación por temas.",
                "La interfaz permite migrar a Chroma/FAISS después sin cambiar AgentLoop.",
            ],
            "updated_utc": self._utc_now(),
        }
        self._write_status(status)
        return status

    def ingest_text(
        self,
        text: str,
        source: str = "manual",
        session_id: str = "default",
        kind: str = "note",
        metadata: Optional[Dict[str, Any]] = None,
        rebuild: bool = True,
    ) -> Dict[str, Any]:
        clean = (text or "").strip()
        if not clean:
            return {"ok": False, "error": "empty_text"}

        metadata = dict(metadata or {})
        digest = hashlib.sha256(
            json.dumps({"source": source, "session_id": session_id, "kind": kind, "text": clean}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        record_id = digest[:24]

        if self._record_exists(record_id):
            return {"ok": True, "inserted": False, "id": record_id, "reason": "duplicate"}

        record = SemanticRecord(
            id=record_id,
            created_utc=self._utc_now(),
            source=source,
            session_id=session_id,
            kind=kind,
            text=clean,
            metadata=metadata,
        )
        with self.records_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")

        if rebuild:
            self.rebuild_index()
        return {"ok": True, "inserted": True, "id": record_id, "records": len(self._read_records())}

    def ingest_many(self, items: Iterable[Dict[str, Any]], rebuild: bool = True) -> Dict[str, Any]:
        inserted = 0
        skipped = 0
        errors: List[str] = []
        for item in items:
            try:
                result = self.ingest_text(
                    text=str(item.get("text", "")),
                    source=str(item.get("source", "bulk")),
                    session_id=str(item.get("session_id", "default")),
                    kind=str(item.get("kind", "note")),
                    metadata=dict(item.get("metadata") or {}),
                    rebuild=False,
                )
                if result.get("inserted"):
                    inserted += 1
                else:
                    skipped += 1
            except Exception as exc:
                errors.append(str(exc))
        if rebuild:
            self.rebuild_index()
        return {"ok": not errors, "inserted": inserted, "skipped": skipped, "errors": errors[:10], "records": len(self._read_records())}

    def ingest_session_memory(self, session_id: str = "default", limit: int = 200) -> Dict[str, Any]:
        """Import existing Brain session memory artifacts into semantic memory."""
        session_root = BASE_PATH / "tmp_agent" / "state" / "memory" / session_id
        items: List[Dict[str, Any]] = []
        if not session_root.exists():
            return {"ok": False, "error": "session_memory_not_found", "path": str(session_root)}

        for path in sorted(session_root.rglob("*.json"))[: max(1, int(limit))]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for text in self._extract_text_fragments(data):
                if len(text.strip()) < 20:
                    continue
                items.append({
                    "text": text[:4000],
                    "source": "session_memory_import",
                    "session_id": session_id,
                    "kind": "session_fragment",
                    "metadata": {"path": str(path)},
                })
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break
        return self.ingest_many(items, rebuild=True)

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.05,
        max_age_hours: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        records = self._read_records()
        if not records or not (query or "").strip():
            return []
        ids, vectors = self._load_or_rebuild_index(records)
        if vectors.size == 0:
            return []
        qvec = self.embed_text(query, self.dims)
        scores = vectors @ qvec
        id_to_record = {str(r.get("id")): r for r in records}
        order = np.argsort(-scores)[: max(1, int(top_k))]
        results: List[Dict[str, Any]] = []
        for idx in order:
            score = float(scores[int(idx)])
            if score < min_score:
                continue
            rec = id_to_record.get(str(ids[int(idx)]))
            if not rec:
                continue
            age_hours = self._record_age_hours(rec)
            if max_age_hours is not None and age_hours is not None and age_hours > max_age_hours:
                continue
            text = str(rec.get("text", ""))
            results.append({
                "id": rec.get("id"),
                "score": round(score, 4),
                "source": rec.get("source"),
                "session_id": rec.get("session_id"),
                "kind": rec.get("kind"),
                "created_utc": rec.get("created_utc"),
                "age_hours": round(age_hours, 2) if age_hours is not None else None,
                "snippet": text[:700],
                "metadata": rec.get("metadata", {}),
            })
        return results

    def format_hits_for_prompt(self, hits: List[Dict[str, Any]]) -> str:
        if not hits:
            return ""
        lines = ["MEMORIA SEMANTICA HISTORICA (usar solo como contexto, no como estado actual):"]
        for hit in hits:
            snippet = str(hit.get("snippet", "")).replace("\n", " ")[:500]
            age = hit.get("age_hours")
            age_txt = f", age_h={age}" if age is not None else ""
            lines.append(f"- score={hit.get('score')} source={hit.get('source')} kind={hit.get('kind')}{age_txt}: {snippet}")
        return "\n".join(lines)

    def rebuild_index(self) -> Dict[str, Any]:
        records = self._read_records()
        ids = np.array([str(r.get("id")) for r in records], dtype=object)
        if records:
            vectors = np.vstack([self.embed_text(str(r.get("text", "")), self.dims) for r in records]).astype(np.float32)
        else:
            vectors = np.zeros((0, self.dims), dtype=np.float32)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.index_path, ids=ids, vectors=vectors, dims=np.array([self.dims], dtype=np.int32), built_at=np.array([time.time()]))
        status = self.status()
        return {"ok": True, "records": len(records), "index_path": str(self.index_path), "status": status}

    def compact(
        self,
        *,
        max_age_hours: Optional[float] = 24.0 * 30.0 * 6.0,
        keep_recent: int = 250,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Compact semantic memory without degrading recent context.

        - preserves the newest `keep_recent` records regardless of age
        - removes exact duplicates by (source, kind, text), keeping newest
        - prunes older records past `max_age_hours` outside the recent window
        """
        records = self._read_records()
        total_before = len(records)
        keep_recent = max(0, int(keep_recent))
        recent_threshold = max(0, total_before - keep_recent)
        removal_reasons: Dict[str, int] = {"duplicate_exact": 0, "stale_age": 0}
        seen_keys = set()
        keep_flags = [True] * total_before

        for idx in range(total_before - 1, -1, -1):
            rec = records[idx]
            key = self._record_dedupe_key(rec)
            if key in seen_keys:
                keep_flags[idx] = False
                removal_reasons["duplicate_exact"] += 1
                continue
            seen_keys.add(key)

            if idx >= recent_threshold:
                continue

            age_hours = self._record_age_hours(rec)
            if max_age_hours is not None and age_hours is not None and age_hours > max_age_hours:
                keep_flags[idx] = False
                removal_reasons["stale_age"] += 1

        compacted = [rec for idx, rec in enumerate(records) if keep_flags[idx]]
        report = {
            "ok": True,
            "dry_run": dry_run,
            "before": self._memory_stats(records),
            "after": self._memory_stats(compacted),
            "removed_total": total_before - len(compacted),
            "removal_reasons": removal_reasons,
            "keep_recent": keep_recent,
            "max_age_hours": max_age_hours,
        }

        if not dry_run:
            self.records_path.parent.mkdir(parents=True, exist_ok=True)
            with self.records_path.open("w", encoding="utf-8") as fh:
                for record in compacted:
                    fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            self.rebuild_index()
        return report

    @staticmethod
    def embed_text(text: str, dims: int = DEFAULT_DIMS) -> np.ndarray:
        tokens = SemanticMemory._tokens(text)
        vec = np.zeros(int(dims), dtype=np.float32)
        if not tokens:
            return vec
        for token in tokens:
            weight = 1.0
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % int(dims)
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign * weight
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    @staticmethod
    def _tokens(text: str) -> List[str]:
        raw = [t.lower() for t in _TOKEN_RE.findall(text or "")]
        tokens: List[str] = []
        for t in raw:
            tokens.append(t)
        for a, b in zip(raw, raw[1:]):
            tokens.append(f"{a}_{b}")
        return tokens

    def _read_records(self) -> List[Dict[str, Any]]:
        if not self.records_path.exists():
            return []
        records: List[Dict[str, Any]] = []
        for line in self.records_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
        return records

    def _record_exists(self, record_id: str) -> bool:
        return any(str(r.get("id")) == record_id for r in self._read_records())

    def _load_or_rebuild_index(self, records: List[Dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
        expected_count = len(records)
        try:
            if self.index_path.exists():
                data = np.load(self.index_path, allow_pickle=True)
                ids = data["ids"]
                vectors = data["vectors"].astype(np.float32)
                dims = int(data["dims"][0]) if "dims" in data else self.dims
                if len(ids) == expected_count and vectors.shape[1] == self.dims and dims == self.dims:
                    return ids, vectors
        except Exception:
            pass
        self.rebuild_index()
        data = np.load(self.index_path, allow_pickle=True)
        return data["ids"], data["vectors"].astype(np.float32)

    def _memory_stats(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        duplicate_keys = set()
        seen_keys = set()
        oldest_age: Optional[float] = None
        newest_age: Optional[float] = None
        by_kind: Dict[str, int] = {}
        for rec in records:
            key = self._record_dedupe_key(rec)
            if key in seen_keys:
                duplicate_keys.add(key)
            else:
                seen_keys.add(key)
            kind = str(rec.get("kind", "unknown"))
            by_kind[kind] = by_kind.get(kind, 0) + 1
            age = self._record_age_hours(rec)
            if age is not None:
                oldest_age = age if oldest_age is None or age > oldest_age else oldest_age
                newest_age = age if newest_age is None or age < newest_age else newest_age
        return {
            "records": len(records),
            "duplicate_exact_count": len(duplicate_keys),
            "oldest_age_hours": round(oldest_age, 2) if oldest_age is not None else None,
            "newest_age_hours": round(newest_age, 2) if newest_age is not None else None,
            "by_kind": by_kind,
            "root": str(self.root),
        }

    @staticmethod
    def _record_dedupe_key(record: Dict[str, Any]) -> tuple[str, str, str]:
        text = re.sub(r"\s+", " ", str(record.get("text", "")).strip().lower())
        return (
            str(record.get("source", "")).strip().lower(),
            str(record.get("kind", "")).strip().lower(),
            text,
        )

    @staticmethod
    def _extract_text_fragments(data: Any) -> List[str]:
        fragments: List[str] = []
        if isinstance(data, str):
            fragments.append(data)
        elif isinstance(data, dict):
            for key, value in data.items():
                if key.lower() in {"content", "text", "message", "summary", "result", "task"} and isinstance(value, str):
                    fragments.append(value)
                else:
                    fragments.extend(SemanticMemory._extract_text_fragments(value))
        elif isinstance(data, list):
            for item in data:
                fragments.extend(SemanticMemory._extract_text_fragments(item))
        return fragments

    def _write_status(self, status: Dict[str, Any]) -> None:
        try:
            self.status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _record_age_hours(record: Dict[str, Any]) -> Optional[float]:
        created = record.get("created_utc")
        if not created:
            return None
        try:
            ts = datetime.fromisoformat(str(created).replace("Z", "+00:00")).astimezone(timezone.utc)
            delta = datetime.now(timezone.utc) - ts
            return delta.total_seconds() / 3600.0
        except Exception:
            return None

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_semantic_memory() -> SemanticMemory:
    """
    Retorna la mejor implementación de memoria semántica disponible.
    Prioriza FAISS con embeddings reales si está disponible.
    """
    # Intentar usar FAISS si está disponible y tiene índice
    try:
        from brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
        from pathlib import Path
        faiss_index = Path("C:/AI_VAULT/memory/semantic/semantic_memory_faiss.index")
        if faiss_index.exists():
            mem = get_semantic_memory_faiss()
            if mem._index is not None or faiss_index.stat().st_size > 0:
                return mem  # type: ignore
    except Exception:
        pass
    # Fallback a implementación original con hashing
    return SemanticMemory()
