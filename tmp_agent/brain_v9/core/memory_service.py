"""Governed read boundary for Brain semantic memory.

R6.1 centralizes access here so Agent V2 callers do not select or mutate
storage backends directly.  Write capability is intentionally not exposed by
this baseline.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class MemoryService:
    """Read-only, backend-neutral access to semantic memory."""

    ownership_boundary = "MemoryService"

    def __init__(self, semantic_root: Path):
        self.semantic_root = Path(semantic_root)
        self.records_path = self.semantic_root / "semantic_memory.jsonl"
        self.faiss_ids_path = self.semantic_root / "semantic_memory_faiss_ids.json"
        self.faiss_index_path = self.semantic_root / "semantic_memory_faiss.index"

    def _records(self) -> List[Dict[str, Any]]:
        return self._records_with_invalid_lines()[0]

    def _records_with_invalid_lines(self) -> tuple[List[Dict[str, Any]], List[int]]:
        if not self.records_path.exists():
            return [], []
        records: List[Dict[str, Any]] = []
        invalid_lines: List[int] = []
        for line_number, raw_line in enumerate(
            self.records_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                invalid_lines.append(line_number)
                continue
            if isinstance(record, dict):
                records.append(record)
            else:
                invalid_lines.append(line_number)
        return records, invalid_lines

    def _faiss_retrieve(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """Use the existing FAISS backend only for its read-only search API."""
        from .semantic_memory_faiss import SemanticMemoryFAISS

        return SemanticMemoryFAISS(root=self.semantic_root).search(
            query,
            top_k=top_k,
            min_score=0.0,
        )

    def retrieve(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Prefer read-only FAISS retrieval and degrade explicitly to JSONL."""
        faiss_error = None
        try:
            faiss_hits = self._faiss_retrieve(query, top_k)
            if faiss_hits or not self._records():
                return {
                    "ok": True,
                    "backend": "faiss",
                    "degraded": False,
                    "ownership_boundary": self.ownership_boundary,
                    "hits": faiss_hits,
                    "write_performed": False,
                }
        except Exception as exc:
            faiss_error = str(exc)[:200]
        terms = [term for term in (query or "").lower().split() if term]
        hits = []
        for record in self._records():
            text = str(record.get("text") or "")
            score = sum(term in text.lower() for term in terms)
            if score and text.strip():
                hits.append(
                    {
                        "id": record.get("id"),
                        "score": score,
                        "text": text[:500],
                        "snippet": text[:500],
                        "source": record.get("source", ""),
                        "kind": record.get("kind", ""),
                        "metadata": record.get("metadata", {}),
                    }
                )
        hits.sort(key=lambda hit: hit["score"], reverse=True)
        return {
            "ok": True,
            "backend": "jsonl_keyword",
            "degraded": True,
            "error": faiss_error,
            "ownership_boundary": self.ownership_boundary,
            "hits": hits[: max(0, int(top_k))],
            "write_performed": False,
        }

    def promote(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Reserve the only write entrypoint until governed promotion is implemented."""
        del record
        raise PermissionError("MemoryService promotion is disabled in the R6.1 read-only baseline")

    def records_for_domain(self, domain: str) -> List[Dict[str, Any]]:
        return [
            record
            for record in self._records()
            if domain
            in {
                (record.get("metadata") or {}).get("domain"),
                (record.get("metadata") or {}).get("canonical_domain"),
            }
        ]

    def recent_agent_lessons(self) -> List[Dict[str, Any]]:
        return [
            record
            for record in self._records()
            if (record.get("metadata") or {}).get("front")
            or "agent" in str(record.get("text") or "").lower()
        ][-10:]

    def integrity_check(self) -> Dict[str, Any]:
        records, invalid_lines = self._records_with_invalid_lines()
        ids = []
        ids_error = None
        if self.faiss_ids_path.exists():
            try:
                raw_ids = json.loads(self.faiss_ids_path.read_text(encoding="utf-8"))
                if not isinstance(raw_ids, list):
                    raise ValueError("FAISS ids must be a list")
                ids = raw_ids
            except (json.JSONDecodeError, ValueError) as exc:
                ids_error = str(exc)
        ntotal = None
        try:
            import faiss

            ntotal = int(faiss.read_index(str(self.faiss_index_path)).ntotal)
        except Exception:
            pass
        return {
            "ok": not invalid_lines and ids_error is None,
            "ownership_boundary": self.ownership_boundary,
            "semantic_lines": len(records) + len(invalid_lines),
            "valid_record_count": len(records),
            "invalid_record_lines": invalid_lines,
            "faiss_ids": len(ids),
            "faiss_ntotal": ntotal,
            "ids_equals_ntotal": ntotal == len(ids),
            "faiss_ids_error": ids_error,
            "read_only": True,
            "write_performed": False,
        }
