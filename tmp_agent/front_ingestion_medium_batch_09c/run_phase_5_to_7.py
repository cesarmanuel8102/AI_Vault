"""
Phases 5-7 for 09C: Source setup, snapshot, and promotion of 24 candidates.
"""
import json
import sys
import shutil
import hashlib
import faiss
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from tmp_agent.brain_v9.memory.promotion_candidate_promoter import promote_candidate

ROOT = Path("C:/AI_VAULT_CANONICAL")
REPORT_DIR = ROOT / "tmp_agent" / "front_ingestion_medium_batch_09c"
CANDIDATES_PATH = REPORT_DIR / "curated_candidates_09c.json"
SNAPSHOT_ROOT = ROOT / "memory" / "rollback_snapshots"

APPROVAL_TOKEN = "AGENTV2_APPROVED_INGESTION_09C_CESAR_24"
OPERATOR_ID = "cesar"
CONFIRM_PHRASE = "PROMOTE_ONE_CANDIDATE_TO_CANONICAL_MEMORY"
ALLOWED_DOMAINS = {
    "governance",
    "semantic_memory",
    "tools_capabilities",
    "production_operations",
    "brain_architecture",
    "operator_readiness",
    "runtime_operations",
    "test_infrastructure",
    "retrieval_quality",
    "security_hardening",
}

# Load candidates
with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
    candidates = json.load(f)

# Phase 5: Create queue_dir
queue_dir = REPORT_DIR / "promotion_queue_09c"
queue_dir.mkdir(parents=True, exist_ok=True)
for c in candidates:
    (queue_dir / f"{c['candidate_id']}.json").write_text(json.dumps(c, indent=2), encoding="utf-8")

source_confirmation = {
    "method": "temporary_queue_dir",
    "queue_dir": str(queue_dir),
    "candidate_count": len(candidates),
    "notes": "Reuses 09A/09B narrow validated path. Does not mutate memory/promotion_queue or memory/semantic_staging.",
}
(REPORT_DIR / "source_path_confirmation.json").write_text(json.dumps(source_confirmation, indent=2), encoding="utf-8")
print(f"Phase 5: Created queue_dir with {len(candidates)} candidates at {queue_dir}")

# Phase 6: Pre-promotion snapshot
jsonl_path = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
faiss_index_path = ROOT / "memory" / "semantic" / "semantic_memory_faiss.index"
faiss_ids_path = ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json"
audit_path = ROOT / "memory" / "semantic" / "promotion_audit.jsonl"

now = datetime.now(timezone.utc)
stamp = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}_ingestion_medium_batch_09c_24"
snapshot_dir = SNAPSHOT_ROOT / stamp
snapshot_dir.mkdir(parents=True, exist_ok=False)

for src in (jsonl_path, faiss_index_path, faiss_ids_path):
    if src.exists():
        shutil.copy2(src, snapshot_dir / src.name)
if audit_path.exists():
    shutil.copy2(audit_path, snapshot_dir / audit_path.name)
shutil.copy2(CANDIDATES_PATH, snapshot_dir / "curated_candidates_09c.json")
shutil.copy2(REPORT_DIR / "validation_summary.json", snapshot_dir / "validation_summary.json")
(snapshot_dir / "SNAPSHOT_REASON.txt").write_text("pre_promotion_09c_24_candidates\n", encoding="utf-8")

snapshot_report = {
    "snapshot_dir": str(snapshot_dir),
    "timestamp": now.isoformat(),
    "candidates_included": [c["candidate_id"] for c in candidates],
    "files_copied": ["semantic_memory.jsonl", "semantic_memory_faiss.index", "semantic_memory_faiss_ids.json", "promotion_audit.jsonl", "curated_candidates_09c.json", "validation_summary.json"],
}
(REPORT_DIR / "pre_promotion_snapshot_report.json").write_text(json.dumps(snapshot_report, indent=2), encoding="utf-8")
print(f"Phase 6: Snapshot created at {snapshot_dir}")

# Baseline
baseline = {
    "jsonl_records": len([x for x in jsonl_path.read_text(encoding="utf-8").splitlines() if x.strip()]),
    "faiss_ids_count": len(json.loads(faiss_ids_path.read_text(encoding="utf-8"))),
    "faiss_ntotal": faiss.read_index(str(faiss_index_path)).ntotal,
}
print(f"Baseline: {json.dumps(baseline, indent=2)}")

# Phase 7: Promote exactly 24 candidates
promoted = []
failed = None
progress = []
for idx, c in enumerate(candidates, 1):
    result = promote_candidate(
        candidate_id=c["candidate_id"],
        source="promotion_queue",
        mode="build",
        approval_token=APPROVAL_TOKEN,
        operator_id=OPERATOR_ID,
        confirm_phrase=CONFIRM_PHRASE,
        queue_dir=queue_dir,
        allowed_domains=ALLOWED_DOMAINS,
    )
    record = {
        "index": idx,
        "candidate_id": c["candidate_id"],
        "ok": result.get("ok", False),
        "blocked": not result.get("ok", False),
        "promotion_performed": result.get("promotion_performed", False),
        "write_performed": result.get("write_performed", False),
        "snapshot_created": result.get("snapshot_created", False),
        "audit_appended": result.get("audit_appended", False),
        "rollback_possible": result.get("rollback_possible", False),
        "validation_errors": result.get("validation_errors", []),
        "safety_flags": result.get("safety_flags", []),
        "faiss_ids_after_count": result.get("faiss_ids_after_count"),
        "faiss_ntotal_after": result.get("faiss_ntotal_after"),
    }
    progress.append(record)
    if not result.get("promotion_performed"):
        failed = record
        break
    promoted.append(c["candidate_id"])

(REPORT_DIR / "promotion_progress.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in progress) + "\n", encoding="utf-8")

print("=== Phase 7: Promotion Progress ===")
for r in progress:
    print(f"  {r['candidate_id']}: ok={r['ok']} promotion_performed={r['promotion_performed']} write_performed={r['write_performed']}")

if failed:
    print(f"FAILED: {json.dumps(failed, indent=2)}")
    sys.exit(1)

print(f"Phase 7: All {len(promoted)} candidates promoted successfully")
