from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[4]
SEM = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
IDS = ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json"
IDX = ROOT / "memory" / "semantic" / "semantic_memory_faiss.index"


class MemoryGatewayV2:
    read_only_default = True

    def _records(self):
        if not SEM.exists():
            return []
        return [json.loads(line) for line in SEM.read_text(encoding="utf-8").splitlines() if line.strip()]

    def semantic_retrieve(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        try:
            import sys
            sys.path.insert(0, str(ROOT / "tmp_agent"))
            from brain_v9.core.semantic_memory_faiss import SemanticMemoryFAISS
            hits = SemanticMemoryFAISS(root=ROOT / "memory" / "semantic").search(query, top_k=top_k, min_score=0.0)
            return {"ok": True, "degraded": False, "backend": "faiss", "hits": hits[:top_k], "write_performed": False}
        except Exception as exc:
            q = (query or "").lower()
            scored = []
            for r in self._records():
                text = (r.get("text") or "").lower()
                score = sum(1 for term in q.split() if len(term) > 3 and term in text)
                if score:
                    scored.append({"id": r.get("id"), "score": score, "text": r.get("text", "")[:500], "metadata": r.get("metadata", {})})
            scored.sort(key=lambda x: x["score"], reverse=True)
            return {"ok": True, "degraded": True, "backend": "jsonl_keyword", "error": str(exc)[:200], "hits": scored[:top_k], "write_performed": False}

    def retrieve_by_domain(self, domain: str) -> Dict[str, Any]:
        hits = []
        for r in self._records():
            m = r.get("metadata") or {}
            if domain in {m.get("domain"), m.get("canonical_domain")}:
                hits.append({"id": r.get("id"), "text": r.get("text", "")[:500], "metadata": m})
        return {"ok": True, "domain": domain, "hits": hits, "write_performed": False}

    def retrieve_recent_agent_lessons(self) -> Dict[str, Any]:
        hits = [r for r in self._records() if (r.get("metadata") or {}).get("front") or "agent" in (r.get("text", "").lower())]
        return {"ok": True, "hits": hits[-10:], "write_performed": False}

    def explain_retrieval(self, query: str) -> Dict[str, Any]:
        result = self.semantic_retrieve(query, top_k=3)
        return {"query": query, "backend": result.get("backend"), "degraded": result.get("degraded"), "hit_count": len(result.get("hits", [])), "write_performed": False}

    def integrity_check(self) -> Dict[str, Any]:
        ids = json.loads(IDS.read_text(encoding="utf-8")) if IDS.exists() else []
        ntotal = None
        try:
            import faiss
            ntotal = int(faiss.read_index(str(IDX)).ntotal)
        except Exception:
            pass
        lines = len(self._records())
        return {"ok": True, "semantic_lines": lines, "faiss_ids": len(ids), "faiss_ntotal": ntotal, "ids_equals_ntotal": ntotal == len(ids), "read_only": True}
