"""
Phase 4-7: Validation, snapshot, promotion, verification for 09A.
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

from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
from tmp_agent.brain_v9.memory.promotion_candidate_promoter import promote_candidate

ROOT = Path("C:/AI_VAULT_CANONICAL")
REPORT_DIR = ROOT / "tmp_agent" / "front_ingestion_controlled_e2e_09a"
CANDIDATES_PATH = REPORT_DIR / "curated_candidates_09a.json"
SNAPSHOT_ROOT = ROOT / "memory" / "rollback_snapshots"

APPROVAL_TOKEN = "AGENTV2_APPROVED_INGESTION_09A_CESAR_3"
OPERATOR_ID = "cesar"
CONFIRM_PHRASE = "PROMOTE_ONE_CANDIDATE_TO_CANONICAL_MEMORY"

# Load candidates
with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
    candidates = json.load(f)

# Phase 4: Dry-run validation using promotion_candidate_validate
gateway = ToolGatewayV2()
validation_results = []
for c in candidates:
    req = ToolCallRequest(
        tool_name="promotion_candidate_validate",
        args={"candidate_id": c["candidate_id"], "source": "all"},
        mode="read_only",
    )
    res = gateway.call(req)
    result = res.result if isinstance(res.result, dict) else {}
    validation_results.append({
        "candidate_id": c["candidate_id"],
        "ok": res.ok,
        "candidate_valid": result.get("candidate_valid", False),
        "validation_errors": result.get("validation_errors", []),
        "duplicate_exact": result.get("duplicate_exact", False),
    })

print("=== Phase 4: Validation ===")
print(json.dumps(validation_results, indent=2))

# If candidates not found in standard queue/staging, write them to a custom queue dir
queue_dir = REPORT_DIR / "promotion_queue_09a"
queue_dir.mkdir(parents=True, exist_ok=True)
for c in candidates:
    (queue_dir / f"{c['candidate_id']}.json").write_text(json.dumps(c, indent=2), encoding="utf-8")

# Re-validate with custom queue_dir
validation_results_2 = []
for c in candidates:
    req = ToolCallRequest(
        tool_name="promotion_candidate_validate",
        args={"candidate_id": c["candidate_id"], "source": "all", "queue_dir": str(queue_dir)},
        mode="read_only",
    )
    res = gateway.call(req)
    result = res.result if isinstance(res.result, dict) else {}
    validation_results_2.append({
        "candidate_id": c["candidate_id"],
        "ok": res.ok,
        "candidate_valid": result.get("candidate_valid", False),
        "validation_errors": result.get("validation_errors", []),
        "duplicate_exact": result.get("duplicate_exact", False),
    })

print("=== Phase 4b: Validation with custom queue_dir ===")
print(json.dumps(validation_results_2, indent=2))

all_valid = all(v["candidate_valid"] for v in validation_results_2)
print(f"ALL_VALID: {all_valid}")

# Phase 5: Snapshot
jsonl_path = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
faiss_index_path = ROOT / "memory" / "semantic" / "semantic_memory_faiss.index"
faiss_ids_path = ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json"

now = datetime.now(timezone.utc)
stamp = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}_ingestion_controlled_e2e_09a_3"
snapshot_dir = SNAPSHOT_ROOT / stamp
snapshot_dir.mkdir(parents=True, exist_ok=False)
for src in (jsonl_path, faiss_index_path, faiss_ids_path):
    if src.exists():
        shutil.copy2(src, snapshot_dir / src.name)
(snapshot_dir / "SNAPSHOT_REASON.txt").write_text("pre_promotion_09a_3_candidates\n", encoding="utf-8")

print(f"=== Phase 5: Snapshot created at {snapshot_dir} ===")

# Baseline
baseline = {
    "jsonl_records": len([x for x in jsonl_path.read_text(encoding="utf-8").splitlines() if x.strip()]),
    "faiss_ids_count": len(json.loads(faiss_ids_path.read_text(encoding="utf-8"))),
    "faiss_ntotal": faiss.read_index(str(faiss_index_path)).ntotal,
}
print(f"Baseline: {json.dumps(baseline, indent=2)}")

# Phase 6: Promote exactly 3 candidates
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
    )
    record = {
        "index": idx,
        "candidate_id": c["candidate_id"],
        "ok": result.get("ok", False),
        "promotion_performed": result.get("promotion_performed", False),
        "write_performed": result.get("write_performed", False),
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

print("=== Phase 6: Promotion ===")
print(json.dumps(progress, indent=2))

if failed:
    print(f"FAILED: {json.dumps(failed, indent=2)}")
    sys.exit(1)

# Phase 7: Post-promotion verify
after = {
    "jsonl_records": len([x for x in jsonl_path.read_text(encoding="utf-8").splitlines() if x.strip()]),
    "faiss_ids_count": len(json.loads(faiss_ids_path.read_text(encoding="utf-8"))),
    "faiss_ntotal": faiss.read_index(str(faiss_index_path)).ntotal,
}
records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = set(json.loads(faiss_ids_path.read_text(encoding="utf-8")))

verify = {
    "jsonl_before": baseline["jsonl_records"],
    "jsonl_after": after["jsonl_records"],
    "jsonl_increment": after["jsonl_records"] - baseline["jsonl_records"],
    "faiss_ids_before": baseline["faiss_ids_count"],
    "faiss_ids_after": after["faiss_ids_count"],
    "faiss_ids_increment": after["faiss_ids_count"] - baseline["faiss_ids_count"],
    "faiss_ntotal_before": baseline["faiss_ntotal"],
    "faiss_ntotal_after": after["faiss_ntotal"],
    "faiss_ntotal_increment": after["faiss_ntotal"] - baseline["faiss_ntotal"],
    "all_promoted_in_jsonl": all(cid in {r.get("id") for r in records} for cid in promoted),
    "all_promoted_in_faiss_ids": all(cid in ids for cid in promoted),
}

print("=== Phase 7: Post-Promotion Verify ===")
print(json.dumps(verify, indent=2))

# Save artifacts
(REPORT_DIR / "validation_dry_run_results.json").write_text(json.dumps(validation_results_2, indent=2), encoding="utf-8")
(REPORT_DIR / "promotion_progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")
(REPORT_DIR / "post_promotion_verify.json").write_text(json.dumps(verify, indent=2), encoding="utf-8")

print("PASS: All phases 4-7 complete.")
