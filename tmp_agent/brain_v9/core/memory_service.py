"""Governed read boundary for Brain semantic memory.

R6.1 centralizes access here so Agent V2 callers do not select or mutate
storage backends directly.  Write capability is intentionally not exposed by
this baseline.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


_CANDIDATE_FIELDS = {
    "schema_version",
    "candidate_id",
    "room_id",
    "source_id",
    "evidence_id",
    "retention_class",
    "text",
    "candidate_sha256",
}
_DECISION_FIELDS = {
    "schema_version",
    "decision_id",
    "approver_principal",
    "approval_source",
    "action",
    "candidate_id",
    "candidate_sha256",
    "room_id",
    "expires_utc",
}
_ROOM_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")


def _canonical_sha256(value: Dict[str, Any], *, omit: set[str] | None = None) -> str:
    payload = {key: item for key, item in value.items() if key not in (omit or set())}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_governed_candidate_v1(candidate: Dict[str, Any]) -> tuple[Dict[str, Any], List[str]]:
    if not isinstance(candidate, dict):
        return {}, ["candidate_not_object"]
    errors: List[str] = []
    unknown = sorted(set(candidate) - _CANDIDATE_FIELDS)
    if unknown:
        errors.append("candidate_unknown_fields")
    for field in _CANDIDATE_FIELDS:
        if field not in candidate:
            errors.append(f"candidate_missing_{field}")
    if candidate.get("schema_version") != 1:
        errors.append("candidate_schema_version_invalid")
    parsed = {field: candidate.get(field) for field in _CANDIDATE_FIELDS}
    for field in ("candidate_id", "source_id", "evidence_id", "retention_class", "text"):
        if not isinstance(parsed.get(field), str) or not parsed[field].strip():
            errors.append(f"candidate_{field}_invalid")
    room_id = parsed.get("room_id")
    if not isinstance(room_id, str) or not _ROOM_ID_PATTERN.fullmatch(room_id):
        errors.append("candidate_room_id_invalid")
    text = str(parsed.get("text") or "").lower()
    if any(term in text for term in ("live trading", "real money", "place order")):
        errors.append("candidate_prohibited_content")
    candidate_hash = parsed.get("candidate_sha256")
    if not isinstance(candidate_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", candidate_hash):
        errors.append("candidate_sha256_invalid")
    elif candidate_hash != _canonical_sha256(parsed, omit={"candidate_sha256"}):
        errors.append("candidate_sha256_mismatch")
    return parsed, errors


def _parse_manual_promotion_decision_v1(decision: Dict[str, Any]) -> tuple[Dict[str, Any], List[str]]:
    if not isinstance(decision, dict):
        return {}, ["manual_decision_not_object"]
    errors: List[str] = []
    unknown = sorted(set(decision) - _DECISION_FIELDS)
    if unknown:
        errors.append("manual_decision_unknown_fields")
    for field in _DECISION_FIELDS:
        if field not in decision:
            errors.append(f"manual_decision_missing_{field}")
    if decision.get("schema_version") != 1:
        errors.append("manual_decision_schema_version_invalid")
    parsed = {field: decision.get(field) for field in _DECISION_FIELDS}
    for field in ("decision_id", "approver_principal", "candidate_id", "candidate_sha256", "room_id"):
        if not isinstance(parsed.get(field), str) or not parsed[field].strip():
            errors.append(f"manual_decision_{field}_invalid")
    if parsed.get("approval_source") != "human_owner":
        errors.append("manual_decision_not_human")
    if parsed.get("action") != "APPROVE_SINGLE_CANDIDATE":
        errors.append("manual_decision_action_invalid")
    if not isinstance(parsed.get("candidate_sha256"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", parsed["candidate_sha256"]
    ):
        errors.append("manual_decision_candidate_sha256_invalid")
    try:
        expires = datetime.fromisoformat(str(parsed.get("expires_utc") or "").replace("Z", "+00:00"))
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            errors.append("manual_decision_expired")
    except ValueError:
        errors.append("manual_decision_expiry_invalid")
    return parsed, errors


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

    def validate_governed_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Validate one typed candidate without reading or writing semantic storage."""
        parsed, errors = _parse_governed_candidate_v1(candidate)
        return {
            "ok": not errors,
            "candidate_id": parsed.get("candidate_id", ""),
            "candidate_sha256": parsed.get("candidate_sha256", "") if not errors else "",
            "errors": errors,
        }

    def prepare_governed_promotion(
        self,
        candidate: Dict[str, Any],
        decision: Dict[str, Any],
        staging_root: Path,
    ) -> Dict[str, Any]:
        """Bind a validated candidate to one manual decision without any write effect."""
        parsed_candidate, candidate_errors = _parse_governed_candidate_v1(candidate)
        if candidate_errors:
            return {"ok": False, "reason": "invalid_governed_candidate", "write_performed": False}
        parsed_decision, decision_errors = _parse_manual_promotion_decision_v1(decision)
        if decision_errors:
            return {"ok": False, "reason": "invalid_manual_decision", "write_performed": False}
        if any(
            parsed_decision[field] != parsed_candidate[field]
            for field in ("candidate_id", "candidate_sha256", "room_id")
        ):
            return {
                "ok": False,
                "reason": "manual_decision_candidate_mismatch",
                "write_performed": False,
            }
        receipt = {
            "schema_version": 1,
            "candidate_id": parsed_candidate["candidate_id"],
            "candidate_sha256": parsed_candidate["candidate_sha256"],
            "room_id": parsed_candidate["room_id"],
            "decision_id": parsed_decision["decision_id"],
            "approver_principal": parsed_decision["approver_principal"],
            "staging_root": str(Path(staging_root)),
        }
        receipt["receipt_sha256"] = _canonical_sha256(receipt)
        return {"ok": True, "write_performed": False, "receipt": receipt}

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
