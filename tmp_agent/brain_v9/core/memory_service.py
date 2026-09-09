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

    @staticmethod
    def _isolated_artifact_hashes(root: Path) -> Dict[str, str]:
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(root).glob("semantic_memory_*"))
        }

    @staticmethod
    def _verify_promotion_receipt(receipt: Dict[str, Any]) -> bool:
        expected = {
            "schema_version",
            "candidate_id",
            "candidate_sha256",
            "room_id",
            "decision_id",
            "approver_principal",
            "staging_root",
            "receipt_sha256",
        }
        return (
            isinstance(receipt, dict)
            and set(receipt) == expected
            and receipt.get("schema_version") == 1
            and isinstance(receipt.get("receipt_sha256"), str)
            and receipt["receipt_sha256"] == _canonical_sha256(receipt, omit={"receipt_sha256"})
        )

    @staticmethod
    def _isolated_storage_write(receipt: Dict[str, Any], isolated_root: Path) -> Dict[str, Any]:
        """No runtime writer is enabled; contracts inject an isolated fake writer."""
        del receipt, isolated_root
        return {"ok": False, "reason": "isolated_storage_writer_not_configured"}

    def execute_isolated_governed_promotion(
        self, receipt: Dict[str, Any], isolated_root: Path
    ) -> Dict[str, Any]:
        """Execute only a sealed receipt in a marker-bound temporary root."""
        root = Path(isolated_root).resolve()
        if root == self.semantic_root.resolve() or root.name.lower() == "memory":
            return {"ok": False, "reason": "canonical_promotion_not_enabled", "write_performed": False}
        if not self._verify_promotion_receipt(receipt):
            return {"ok": False, "reason": "promotion_receipt_invalid", "write_performed": False}
        from tmp_agent.brain_v9.memory.memory_rollback import rollback_isolated_snapshot
        from tmp_agent.brain_v9.memory.memory_snapshot import create_isolated_memory_snapshot

        snapshot = create_isolated_memory_snapshot(root, receipt["receipt_sha256"])
        if not snapshot.get("ok"):
            return {"ok": False, "reason": snapshot.get("reason", "isolated_snapshot_failed"), "write_performed": False}
        before = self._isolated_artifact_hashes(root)
        try:
            write_result = self._isolated_storage_write(receipt, root)
            if not isinstance(write_result, dict) or write_result.get("ok") is not True:
                raise RuntimeError("isolated_storage_write_rejected")
            after = self._isolated_artifact_hashes(root)
            if set(after) != set(before):
                raise RuntimeError("isolated_storage_write_artifact_topology_changed")
            if after == before:
                raise RuntimeError("isolated_storage_write_no_effect")
        except Exception:
            rollback = rollback_isolated_snapshot(root, snapshot, receipt["receipt_sha256"])
            return {
                "ok": False,
                "reason": "isolated_promotion_failed",
                "write_performed": False,
                "rollback": rollback,
            }
        execution = {
            "ok": True,
            "schema_version": 1,
            "promotion_receipt_sha256": receipt["receipt_sha256"],
            "candidate_id": receipt["candidate_id"],
            "isolated_root": str(root),
            "before_artifact_sha256": before,
            "after_artifact_sha256": after,
            "snapshot": snapshot,
            "write_performed": True,
        }
        execution["execution_receipt_sha256"] = _canonical_sha256(execution)
        return execution

    def rollback_isolated_governed_promotion(
        self, execution_receipt: Dict[str, Any], isolated_root: Path
    ) -> Dict[str, Any]:
        """Rollback only the matching isolated execution receipt."""
        from tmp_agent.brain_v9.memory.memory_rollback import rollback_isolated_snapshot

        root = Path(isolated_root).resolve()
        if (
            not isinstance(execution_receipt, dict)
            or execution_receipt.get("isolated_root") != str(root)
            or execution_receipt.get("execution_receipt_sha256")
            != _canonical_sha256(execution_receipt, omit={"execution_receipt_sha256"})
        ):
            return {"ok": False, "reason": "execution_receipt_invalid"}
        result = rollback_isolated_snapshot(
            root,
            execution_receipt.get("snapshot", {}),
            str(execution_receipt.get("promotion_receipt_sha256") or ""),
        )
        if result.get("ok"):
            restored = self._isolated_artifact_hashes(root)
            if restored != execution_receipt.get("before_artifact_sha256"):
                return {"ok": False, "reason": "rollback_verification_failed"}
        return result

    @staticmethod
    def _r6_3_snapshot_receipt(snapshot_root: Path) -> tuple[Dict[str, Any] | None, str]:
        """Parse an attributable snapshot without accepting an opaque memory source."""
        from tmp_agent.brain_v9.memory.memory_snapshot import R6_3_ISOLATED_SNAPSHOT_MARKER

        root = Path(snapshot_root).resolve()
        if not root.is_dir() or not (root / R6_3_ISOLATED_SNAPSHOT_MARKER).is_file():
            return None, "snapshot_root_invalid"
        artifacts = (
            "semantic_memory.jsonl",
            "semantic_memory_faiss.index",
            "semantic_memory_faiss_ids.json",
        )
        try:
            manifest = json.loads((root / "hydration_manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, "snapshot_manifest_invalid"
        if set(manifest) != {"schema_version", "snapshot_id", "artifact_sha256"}:
            return None, "snapshot_manifest_invalid"
        if manifest.get("schema_version") != 1 or not isinstance(manifest.get("snapshot_id"), str) or not manifest["snapshot_id"].strip():
            return None, "snapshot_manifest_invalid"
        hashes = manifest.get("artifact_sha256")
        if not isinstance(hashes, dict) or set(hashes) != set(artifacts):
            return None, "snapshot_manifest_invalid"
        actual: Dict[str, str] = {}
        try:
            for name in artifacts:
                content = (root / name).read_bytes()
                actual[name] = hashlib.sha256(content).hexdigest()
                if not isinstance(hashes[name], str) or hashes[name] != actual[name]:
                    return None, "snapshot_artifact_hash_mismatch"
            records = [
                json.loads(line)
                for line in (root / "semantic_memory.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            ids = json.loads((root / "semantic_memory_faiss_ids.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, "snapshot_records_invalid"
        provenance: List[Dict[str, str]] = []
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"].strip():
                return None, "snapshot_record_id_invalid"
            if not isinstance(record.get("source"), str) or not record["source"].strip():
                return None, "snapshot_record_source_invalid"
            provenance.append({"id": record["id"], "source": record["source"]})
        record_ids = [record["id"] for record in provenance]
        if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids) or ids != record_ids or len(set(ids)) != len(ids):
            return None, "snapshot_faiss_topology_inconsistent"
        receipt: Dict[str, Any] = {
            "schema_version": 1,
            "snapshot_id": manifest["snapshot_id"],
            "snapshot_root": str(root),
            "artifact_sha256": actual,
            "record_provenance": provenance,
        }
        receipt["rebuild_identity_sha256"] = _canonical_sha256(receipt)
        receipt["receipt_sha256"] = _canonical_sha256(receipt)
        return receipt, ""

    @staticmethod
    def _verify_r6_3_snapshot_receipt(receipt: Dict[str, Any]) -> bool:
        expected = {
            "schema_version", "snapshot_id", "snapshot_root", "artifact_sha256", "record_provenance",
            "rebuild_identity_sha256", "receipt_sha256",
        }
        if not isinstance(receipt, dict) or set(receipt) != expected or receipt.get("schema_version") != 1:
            return False
        unsigned = {key: value for key, value in receipt.items() if key not in {"receipt_sha256"}}
        identity_input = {key: value for key, value in unsigned.items() if key != "rebuild_identity_sha256"}
        if receipt.get("rebuild_identity_sha256") != _canonical_sha256(identity_input):
            return False
        if receipt.get("receipt_sha256") != _canonical_sha256(unsigned):
            return False
        parsed, error = MemoryService._r6_3_snapshot_receipt(Path(str(receipt.get("snapshot_root") or "")))
        return error == "" and parsed == receipt

    def prepare_isolated_retrieval_hydration(self, snapshot_root: Path) -> Dict[str, Any]:
        """Validate explicit isolated snapshot provenance before any hydration write."""
        receipt, error = self._r6_3_snapshot_receipt(snapshot_root)
        if receipt is None:
            return {"ok": False, "reason": error, "write_performed": False}
        return {"ok": True, "write_performed": False, "receipt": receipt}

    @staticmethod
    def _isolated_retrieval_rebuild(receipt: Dict[str, Any], isolated_root: Path) -> Dict[str, Any]:
        """Production rebuild remains disabled until a separately governed runtime integration."""
        del receipt, isolated_root
        return {"ok": False, "reason": "isolated_retrieval_rebuilder_not_configured"}

    def hydrate_isolated_retrieval(self, receipt: Dict[str, Any], isolated_root: Path) -> Dict[str, Any]:
        """Copy only a sealed, attributable snapshot into a marker-bound temporary root."""
        root = Path(isolated_root).resolve()
        if root == self.semantic_root.resolve():
            return {"ok": False, "reason": "canonical_hydration_not_enabled", "write_performed": False}
        if not self._verify_r6_3_snapshot_receipt(receipt):
            return {"ok": False, "reason": "hydration_receipt_invalid", "write_performed": False}
        from tmp_agent.brain_v9.memory.memory_snapshot import (
            ISOLATED_ARTIFACTS,
            create_isolated_retrieval_snapshot,
            isolated_retrieval_artifact_hashes,
            isolated_retrieval_root_or_error,
        )
        from tmp_agent.brain_v9.memory.memory_rollback import rollback_isolated_retrieval_snapshot

        root, error = isolated_retrieval_root_or_error(root)
        if root is None:
            return {"ok": False, "reason": error, "write_performed": False}
        snapshot = create_isolated_retrieval_snapshot(root, receipt["receipt_sha256"])
        if not snapshot.get("ok"):
            return {"ok": False, "reason": snapshot.get("reason", "isolated_snapshot_failed"), "write_performed": False}
        try:
            source = Path(receipt["snapshot_root"])
            staged = []
            for name in ISOLATED_ARTIFACTS:
                temporary = root / f".{name}.r6_3_hydrate"
                temporary.write_bytes((source / name).read_bytes())
                staged.append((temporary, root / name))
            for temporary, destination in staged:
                temporary.replace(destination)
        except OSError:
            rollback = rollback_isolated_retrieval_snapshot(root, snapshot, receipt["receipt_sha256"])
            return {"ok": False, "reason": "isolated_hydration_failed", "write_performed": False, "rollback": rollback}
        hydrated_hashes = isolated_retrieval_artifact_hashes(root)
        if hydrated_hashes != receipt["artifact_sha256"]:
            rollback = rollback_isolated_retrieval_snapshot(root, snapshot, receipt["receipt_sha256"])
            return {"ok": False, "reason": "isolated_hydration_verification_failed", "write_performed": False, "rollback": rollback}
        hydration_receipt = {
            "schema_version": 1,
            "source_snapshot_id": receipt["snapshot_id"],
            "source_receipt_sha256": receipt["receipt_sha256"],
            "isolated_root": str(root),
            "artifact_sha256": hydrated_hashes,
            "record_provenance": receipt["record_provenance"],
            "rebuild_identity_sha256": receipt["rebuild_identity_sha256"],
        }
        hydration_receipt["hydration_receipt_sha256"] = _canonical_sha256(hydration_receipt)
        return {
            "ok": True,
            "write_performed": True,
            "source_snapshot_id": receipt["snapshot_id"],
            "hydration_receipt": hydration_receipt,
        }

    @staticmethod
    def _verify_hydration_receipt(receipt: Dict[str, Any], root: Path) -> bool:
        expected = {
            "schema_version", "source_snapshot_id", "source_receipt_sha256", "isolated_root",
            "artifact_sha256", "record_provenance", "rebuild_identity_sha256", "hydration_receipt_sha256",
        }
        return (
            isinstance(receipt, dict)
            and set(receipt) == expected
            and receipt.get("schema_version") == 1
            and receipt.get("isolated_root") == str(Path(root).resolve())
            and receipt.get("hydration_receipt_sha256")
            == _canonical_sha256(receipt, omit={"hydration_receipt_sha256"})
        )

    def rebuild_isolated_retrieval(self, hydration_receipt: Dict[str, Any], isolated_root: Path) -> Dict[str, Any]:
        """Run a receipt-bound testable rebuild and rollback every invalid isolated result."""
        root = Path(isolated_root).resolve()
        if root == self.semantic_root.resolve():
            return {"ok": False, "reason": "canonical_hydration_not_enabled", "write_performed": False}
        if not self._verify_hydration_receipt(hydration_receipt, root):
            return {"ok": False, "reason": "hydration_receipt_invalid", "write_performed": False}
        from tmp_agent.brain_v9.memory.memory_snapshot import (
            create_isolated_retrieval_snapshot,
            isolated_retrieval_artifact_hashes,
            isolated_retrieval_root_or_error,
        )
        from tmp_agent.brain_v9.memory.memory_rollback import rollback_isolated_retrieval_snapshot

        root, error = isolated_retrieval_root_or_error(root)
        if root is None:
            return {"ok": False, "reason": error, "write_performed": False}
        before = isolated_retrieval_artifact_hashes(root)
        if before != hydration_receipt["artifact_sha256"]:
            return {"ok": False, "reason": "hydrated_artifact_hash_mismatch", "write_performed": False}
        snapshot = create_isolated_retrieval_snapshot(root, hydration_receipt["hydration_receipt_sha256"])
        if not snapshot.get("ok"):
            return {"ok": False, "reason": snapshot.get("reason", "isolated_snapshot_failed"), "write_performed": False}
        try:
            rebuilt = self._isolated_retrieval_rebuild(hydration_receipt, root)
            if not isinstance(rebuilt, dict) or rebuilt.get("ok") is not True:
                raise RuntimeError("isolated_retrieval_rebuild_rejected")
            if rebuilt.get("rebuild_identity_sha256") != hydration_receipt["rebuild_identity_sha256"]:
                raise RuntimeError("isolated_retrieval_rebuild_identity_mismatch")
            verified, error = self._r6_3_snapshot_receipt_from_hydrated_root(root, hydration_receipt)
            if verified is None or error:
                raise RuntimeError(error or "isolated_retrieval_rebuild_invalid")
            after = isolated_retrieval_artifact_hashes(root)
            if after == before:
                raise RuntimeError("isolated_retrieval_rebuild_no_effect")
        except Exception:
            rollback = rollback_isolated_retrieval_snapshot(root, snapshot, hydration_receipt["hydration_receipt_sha256"])
            return {"ok": False, "reason": "isolated_rebuild_failed", "write_performed": False, "rollback": rollback}
        return {
            "ok": True,
            "write_performed": True,
            "rebuild_identity_sha256": hydration_receipt["rebuild_identity_sha256"],
            "before_artifact_sha256": before,
            "after_artifact_sha256": after,
        }

    @staticmethod
    def _r6_3_snapshot_receipt_from_hydrated_root(
        root: Path, hydration_receipt: Dict[str, Any]
    ) -> tuple[Dict[str, Any] | None, str]:
        """Validate records/IDs after a rebuild without treating the index bytes as provenance."""
        try:
            records = [
                json.loads(line)
                for line in (root / "semantic_memory.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            ids = json.loads((root / "semantic_memory_faiss_ids.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, "isolated_rebuild_records_invalid"
        provenance = []
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not isinstance(record.get("source"), str) or not record["id"].strip() or not record["source"].strip():
                return None, "isolated_rebuild_record_provenance_invalid"
            provenance.append({"id": record["id"], "source": record["source"]})
        if not isinstance(ids, list) or ids != [item["id"] for item in provenance] or len(set(ids)) != len(ids):
            return None, "isolated_rebuild_topology_inconsistent"
        if provenance != hydration_receipt["record_provenance"]:
            return None, "isolated_rebuild_provenance_changed"
        return {"record_provenance": provenance}, ""

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
