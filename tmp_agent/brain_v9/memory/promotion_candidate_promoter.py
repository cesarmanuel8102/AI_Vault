"""
Write-gated single-candidate promoter for canonical semantic memory (FAISS + JSONL).

Scope:
- Promote exactly one validated candidate from promotion_queue or semantic_staging.
- Multi-factor approval: mode != read_only, approval_token, exact confirm phrase.
- Snapshot before write, audit after write, rollback supported.
- Uses current SemanticMemoryFAISS only; never the legacy npz index backend.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tmp_agent.brain_v9.memory.memory_snapshot import CANONICAL_FILES, SNAPSHOT_ROOT
from tmp_agent.brain_v9.memory.memory_rollback import rollback_from_snapshot, verify_snapshot
from tmp_agent.brain_v9.memory.memory_auditor import append_promotion_audit
from tmp_agent.brain_v9.memory.promotion_pipeline_adapter import PromotionPipelineAdapter
from tmp_agent.brain_v9.config import BASE_PATH

# Also support legacy import path used by tests/server
from tmp_agent.brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss

ROOT = BASE_PATH
SEMANTIC_JSONL = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
FAISS_INDEX = ROOT / "memory" / "semantic" / "semantic_memory_faiss.index"
FAISS_IDS = ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json"

REQUIRED_CONFIRM_PHRASE = "PROMOTE_ONE_CANDIDATE_TO_CANONICAL_MEMORY"
ALLOWED_PROMOTION_MODES = {"build", "write_allowed", "promotion"}
KNOWN_DOMAINS = {
    "autonomy_dashboard_visual_trace_self_improvement_governance",
    "brain_architecture",
    "runtime_operations",
    "learning_external",
    "tools_capabilities",
    "semantic_memory",
    "production_operations",
    "operator_readiness",
    "governance",
    "general",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_optional(path: Path) -> str:
    return _sha256(path) if path.exists() else ""


def _read_json_ids(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


def _faiss_ntotal() -> int:
    try:
        _reset_faiss_singleton()
        from tmp_agent.brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
        mem = get_semantic_memory_faiss()
        mem._ensure_index_loaded()
        return int(mem._index.ntotal) if mem._index is not None else 0
    except Exception:
        return 0


def _reset_faiss_singleton():
    try:
        import tmp_agent.brain_v9.core.semantic_memory_faiss as faiss_mod
        faiss_mod._MEM_FAISS = None
    except Exception:
        pass


def _load_semantic_records() -> List[Dict[str, Any]]:
    if not SEMANTIC_JSONL.exists():
        return []
    records: List[Dict[str, Any]] = []
    for line in SEMANTIC_JSONL.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return records


def _create_unique_snapshot(reason: str) -> Path:
    """Create a snapshot directory with a unique timestamp to avoid second-level collisions."""
    import shutil
    snapshot_root = Path(SNAPSHOT_ROOT)
    snapshot_root.mkdir(parents=True, exist_ok=True)
    for _ in range(100):
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}_{secrets.token_hex(4)}"
        target = snapshot_root / stamp
        if target.exists():
            continue
        target.mkdir(parents=True, exist_ok=False)
        for src in CANONICAL_FILES:
            if src.exists():
                shutil.copy2(src, target / src.name)
        (target / "SNAPSHOT_REASON.txt").write_text(reason + "\n", encoding="utf-8")
        return target
    raise RuntimeError("unable to create unique snapshot directory")


def promote_candidate(
    candidate_id: str,
    source: str,
    mode: str,
    approval_token: str,
    operator_id: str,
    confirm_phrase: str,
    allowed_domains: Optional[set[str]] = None,
    queue_dir: Optional[Path] = None,
    staging_dir: Optional[Path] = None,
    staging_jsonl: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Promote a single validated candidate into canonical semantic memory.
    Returns a full report including before/after SHAs and rollback info.
    """
    errors: List[str] = []
    safety_flags: List[str] = []

    # Governance gates
    effective_mode = str(mode or "").lower()
    if effective_mode in {"read_only", "read-only", "readonly"}:
        errors.append("read_only_mode_blocked")
    if effective_mode not in ALLOWED_PROMOTION_MODES:
        errors.append("mode_not_allowed_for_promotion")
    if not (approval_token and str(approval_token).startswith("AGENTV2_APPROVED_")):
        errors.append("approval_token_invalid")
    if str(confirm_phrase) != REQUIRED_CONFIRM_PHRASE:
        errors.append("confirm_phrase_mismatch")
    if not candidate_id:
        errors.append("candidate_id_missing")

    if errors:
        return _rejected_report(candidate_id, errors, safety_flags)

    # Load candidate
    adapter = PromotionPipelineAdapter()
    candidates = adapter.load_candidates(
        source,
        queue_dir=queue_dir,
        staging_dir=staging_dir,
        staging_jsonl=staging_jsonl,
    )
    candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
    if candidate is None:
        return _rejected_report(candidate_id, ["candidate_not_found"], safety_flags)

    # Validate
    validation = adapter.validate_candidate(candidate)
    if not validation["valid"]:
        errors.extend(validation["validation_errors"])
        if validation.get("duplicate_exact"):
            safety_flags.append("duplicate_exact_text_in_canonical_memory")

    # Safety flag extraction
    if candidate.get("raw_cot_exposed"):
        errors.append("raw_cot_exposed")
        safety_flags.append("raw_cot_exposed")
    if candidate.get("secrets_exposed"):
        errors.append("secrets_exposed")
        safety_flags.append("secrets_exposed")
    if candidate.get("trading_execution_detected"):
        errors.append("trading_execution_detected")
        safety_flags.append("trading_execution_detected")

    # Domain gate
    domains = allowed_domains or KNOWN_DOMAINS
    domain = str(candidate.get("domain") or "unknown").lower()
    canonical_domain = str(candidate.get("canonical_domain") or domain).lower()
    if domain not in domains and canonical_domain not in domains:
        errors.append("unknown_domain_not_approved")
        safety_flags.append("unknown_domain")

    if errors:
        return _rejected_report(candidate_id, errors, safety_flags)

    # Compute before state
    before_shas = {
        "jsonl": _sha_optional(SEMANTIC_JSONL),
        "faiss_index": _sha_optional(FAISS_INDEX),
        "faiss_ids": _sha_optional(FAISS_IDS),
    }
    before_jsonl_count = len(_load_semantic_records())
    before_ids_count = len(_read_json_ids(FAISS_IDS))
    before_ntotal = _faiss_ntotal()

    # Snapshot before write
    snapshot = _create_unique_snapshot(reason=f"promote_candidate:{candidate_id}:operator={operator_id}")
    snapshot_path = str(snapshot)

    try:
        # Build canonical semantic record
        semantic_record = adapter._build_proposed_semantic_record(candidate)
        semantic_record["session_id"] = f"promotion_candidate_promote:{operator_id}"
        semantic_record["kind"] = "canonical_candidate"
        semantic_record["promoted_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        semantic_record["promoted_by"] = operator_id
        semantic_record["source"] = source
        record_id = semantic_record["id"]

        # Write to JSONL and FAISS using the canonical record ID we chose.
        # We do NOT use ingest_text because it generates its own record_id hash;
        # promotion requires the semantic_record id to match the candidate_id.
        _reset_faiss_singleton()
        from tmp_agent.brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
        mem = get_semantic_memory_faiss()

        with mem.records_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(semantic_record, ensure_ascii=False, sort_keys=True) + "\n")

        mem._add_to_index(record_id, semantic_record["text"])

        # Verify FAISS state
        after_ids = _read_json_ids(FAISS_IDS)
        after_ntotal = _faiss_ntotal()
        after_jsonl_count = len(_load_semantic_records())

        jsonl_increment = after_jsonl_count - before_jsonl_count
        ids_increment = len(after_ids) - before_ids_count
        ntotal_increment = after_ntotal - before_ntotal

        if not (jsonl_increment == 1 and ids_increment == 1 and ntotal_increment == 1):
            raise RuntimeError(
                f"canonical memory did not increment by exactly one: "
                f"jsonl +{jsonl_increment}, ids +{ids_increment}, ntotal +{ntotal_increment}"
            )

        if record_id not in after_ids:
            raise RuntimeError(f"promoted record_id {record_id} not found in FAISS ids")

        # Verify retrievable
        retrieval = mem.search(semantic_record["text"], top_k=5, min_score=0.1)
        retrieved_ids = {str(r.get("id")) for r in retrieval}
        if record_id not in retrieved_ids:
            raise RuntimeError(f"promoted record_id {record_id} not retrievable")

        # Append audit
        audit_record = {
            "event": "canonical_promotion",
            "candidate_id": candidate_id,
            "semantic_record_id": record_id,
            "operator_id": operator_id,
            "source": source,
            "mode": effective_mode,
            "snapshot_path": snapshot_path,
            "jsonl_before_sha": before_shas["jsonl"],
            "jsonl_after_sha": _sha_optional(SEMANTIC_JSONL),
            "faiss_index_before_sha": before_shas["faiss_index"],
            "faiss_index_after_sha": _sha_optional(FAISS_INDEX),
            "faiss_ids_before_sha": before_shas["faiss_ids"],
            "faiss_ids_after_sha": _sha_optional(FAISS_IDS),
            "faiss_ids_before_count": before_ids_count,
            "faiss_ids_after_count": len(after_ids),
            "faiss_ntotal_before": before_ntotal,
            "faiss_ntotal_after": after_ntotal,
            "validation_errors": [],
            "safety_flags": safety_flags,
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        append_promotion_audit(audit_record)

        return {
            "ok": True,
            "candidate_id": candidate_id,
            "candidate_valid": True,
            "promotion_performed": True,
            "write_performed": True,
            "snapshot_created": True,
            "snapshot_path": snapshot_path,
            "semantic_record_id": record_id,
            "jsonl_before_sha": before_shas["jsonl"],
            "jsonl_after_sha": _sha_optional(SEMANTIC_JSONL),
            "faiss_index_before_sha": before_shas["faiss_index"],
            "faiss_index_after_sha": _sha_optional(FAISS_INDEX),
            "faiss_ids_before_sha": before_shas["faiss_ids"],
            "faiss_ids_after_sha": _sha_optional(FAISS_IDS),
            "faiss_ids_before_count": before_ids_count,
            "faiss_ids_after_count": len(after_ids),
            "faiss_ntotal_before": before_ntotal,
            "faiss_ntotal_after": after_ntotal,
            "audit_appended": True,
            "rollback_possible": verify_snapshot(snapshot),
            "validation_errors": [],
            "safety_flags": safety_flags,
        }

    except Exception as exc:
        # Best-effort rollback on failure
        rollback_from_snapshot(snapshot, dry_run=False)
        return _rejected_report(
            candidate_id,
            [f"promotion_failed:{str(exc)[:200]}"],
            safety_flags,
            snapshot_path=snapshot_path,
        )


def _rejected_report(
    candidate_id: str,
    errors: List[str],
    safety_flags: List[str],
    snapshot_path: str = "",
) -> Dict[str, Any]:
    return {
        "ok": False,
        "candidate_id": candidate_id,
        "candidate_valid": False,
        "promotion_performed": False,
        "write_performed": False,
        "snapshot_created": bool(snapshot_path),
        "snapshot_path": snapshot_path,
        "semantic_record_id": "",
        "jsonl_before_sha": _sha_optional(SEMANTIC_JSONL),
        "jsonl_after_sha": _sha_optional(SEMANTIC_JSONL),
        "faiss_index_before_sha": _sha_optional(FAISS_INDEX),
        "faiss_index_after_sha": _sha_optional(FAISS_INDEX),
        "faiss_ids_before_sha": _sha_optional(FAISS_IDS),
        "faiss_ids_after_sha": _sha_optional(FAISS_IDS),
        "faiss_ids_before_count": len(_read_json_ids(FAISS_IDS)),
        "faiss_ids_after_count": len(_read_json_ids(FAISS_IDS)),
        "faiss_ntotal_before": _faiss_ntotal(),
        "faiss_ntotal_after": _faiss_ntotal(),
        "audit_appended": False,
        "rollback_possible": bool(snapshot_path) and verify_snapshot(Path(snapshot_path)) if snapshot_path else False,
        "validation_errors": errors,
        "safety_flags": safety_flags,
    }


def rollback_promotion(snapshot_path: str) -> Dict[str, Any]:
    """Restore canonical memory files from a snapshot directory."""
    snapshot = Path(snapshot_path)
    if not verify_snapshot(snapshot):
        return {"ok": False, "reason": "snapshot_incomplete", "snapshot_path": snapshot_path}
    result = rollback_from_snapshot(snapshot, dry_run=False)
    return {**result, "snapshot_path": snapshot_path}
