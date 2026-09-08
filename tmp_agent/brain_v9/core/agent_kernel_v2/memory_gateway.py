from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional

from ..memory_service import MemoryService

ROOT = Path(__file__).resolve().parents[4]
SEM = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
IDS = ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json"
IDX = ROOT / "memory" / "semantic" / "semantic_memory_faiss.index"


class MemoryGatewayV2:
    read_only_default = True

    def __init__(self, memory_service: Optional[MemoryService] = None):
        self.memory_service = memory_service or MemoryService(ROOT / "memory" / "semantic")

    def _filter_usable_hits(self, hits):
        usable = []
        filtered_empty = 0
        for h in hits:
            raw_text = h.get("text") or h.get("snippet") or ""
            if raw_text and raw_text.strip():
                normalized = dict(h)
                normalized["text"] = normalized.get("text") or raw_text
                normalized["snippet"] = normalized.get("snippet") or raw_text
                usable.append(normalized)
            else:
                filtered_empty += 1
        return usable, filtered_empty

    def semantic_retrieve(self, query: str, top_k: int = 5, domain_gate: Optional[str] = None) -> Dict[str, Any]:
        result = self.memory_service.retrieve(query, top_k=top_k * 3)
        raw_hits = result.get("hits", [])
        usable_hits, filtered_empty = self._filter_usable_hits(raw_hits)
        if domain_gate:
            usable_hits = [
                hit
                for hit in usable_hits
                if domain_gate.lower()
                in (str(hit.get("source", "")) + " " + str(hit.get("kind", ""))).lower()
            ]
        final_hits = usable_hits[:top_k]
        return {
            **result,
            "hits": final_hits,
            "raw_hit_count": len(raw_hits),
            "usable_hit_count": len(final_hits),
            "filtered_empty_count": filtered_empty,
            "write_performed": False,
        }

    def retrieve_by_domain(self, domain: str) -> Dict[str, Any]:
        hits = []
        for r in self.memory_service.records_for_domain(domain):
            m = r.get("metadata") or {}
            if domain in {m.get("domain"), m.get("canonical_domain")}:
                hits.append({"id": r.get("id"), "text": r.get("text", "")[:500], "metadata": m})
        return {"ok": True, "domain": domain, "hits": hits, "write_performed": False}

    def retrieve_recent_agent_lessons(self) -> Dict[str, Any]:
        return {"ok": True, "hits": self.memory_service.recent_agent_lessons(), "write_performed": False}

    def explain_retrieval(self, query: str) -> Dict[str, Any]:
        result = self.semantic_retrieve(query, top_k=3)
        return {"query": query, "backend": result.get("backend"), "degraded": result.get("degraded"), "hit_count": len(result.get("hits", [])), "write_performed": False}

    def integrity_check(self) -> Dict[str, Any]:
        return self.memory_service.integrity_check()
