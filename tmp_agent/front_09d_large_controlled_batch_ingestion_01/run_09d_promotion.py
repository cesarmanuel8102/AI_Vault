"""
Governed promotion script for FRONT-09D-LARGE-CONTROLLED-BATCH-INGESTION-01.
Promotes exactly 8 validated unique candidates to canonical semantic memory/FAISS.
"""
import sys, os, json, hashlib, shutil
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, r"C:\AI_VAULT_CANONICAL")
sys.path.insert(0, r"C:\AI_VAULT_CANONICAL\tmp_agent")

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")

from tmp_agent.brain_v9.core.semantic_memory_faiss import SemanticMemoryFAISS

ROOT = Path(r"C:\AI_VAULT_CANONICAL")
REPORT_DIR = ROOT / "tmp_agent" / "front_09d_large_controlled_batch_ingestion_01"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

SNAPSHOT_ROOT = ROOT / "memory" / "rollback_snapshots"


def load_inventory():
    path = REPORT_DIR / "candidate_inventory.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    print("=== 09D Governed Promotion ===")
    
    # Load inventory
    inventory = load_inventory()
    candidates = inventory["candidates"]
    
    print(f"Candidates to promote: {len(candidates)}")
    
    # Initialize semantic memory
    mem = SemanticMemoryFAISS()
    
    # Pre-promotion counts
    records_before = len(mem._read_records())
    mem._ensure_index_loaded()
    ids_before = list(mem._ids)
    ntotal_before = mem._index.ntotal if mem._index else 0
    
    print(f"Before: records={records_before}, ids={len(ids_before)}, ntotal={ntotal_before}")
    
    promoted = []
    skipped = []
    failed = []
    
    for c in candidates:
        cid = c["candidate_id"]
        src_path = Path(c["source_path"])
        
        # Load candidate text
        try:
            data = json.loads(src_path.read_text(encoding="utf-8"))
            text = data.get("text", data.get("summary", "")).strip()
            if not text:
                failed.append({"candidate_id": cid, "reason": "empty_text"})
                continue
        except Exception as e:
            failed.append({"candidate_id": cid, "reason": f"read_error: {e}"})
            continue
        
        # Check if already exists
        digest = hashlib.sha256(
            json.dumps({"source": "09d_batch", "session_id": "09d", "kind": "candidate", "text": text},
                       ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        record_id = digest[:24]
        
        if mem._record_exists(record_id):
            skipped.append({"candidate_id": cid, "reason": "already_exists", "record_id": record_id})
            continue
        
        # Ingest
        try:
            result = mem.ingest_text(
                text=text,
                source="09d_batch_promotion",
                session_id="09d_large_controlled_batch",
                kind="candidate",
                metadata={
                    "candidate_id": cid,
                    "domain": c.get("domain", "unknown"),
                    "category": c.get("category", "unknown"),
                    "front": "FRONT-09D-LARGE-CONTROLLED-BATCH-INGESTION-01",
                    "promoted_utc": datetime.now(timezone.utc).isoformat(),
                },
                rebuild=True,
            )
            if result.get("inserted"):
                promoted.append({
                    "candidate_id": cid,
                    "record_id": result["id"],
                    "text_length": len(text),
                })
                print(f"  PROMOTED: {cid} -> {result['id']}")
            else:
                skipped.append({"candidate_id": cid, "reason": result.get("reason", "unknown"), "record_id": result["id"]})
                print(f"  SKIPPED: {cid} -> {result.get('reason')}")
        except Exception as e:
            failed.append({"candidate_id": cid, "reason": f"ingest_error: {e}"})
            print(f"  FAILED: {cid} -> {e}")
    
    # Post-promotion counts
    records_after = len(mem._read_records())
    mem._ensure_index_loaded()
    ids_after = list(mem._ids)
    ntotal_after = mem._index.ntotal if mem._index else 0
    
    print(f"After: records={records_after}, ids={len(ids_after)}, ntotal={ntotal_after}")
    
    # Write promotion report
    report = {
        "front": "FRONT-09D-LARGE-CONTROLLED-BATCH-INGESTION-01",
        "attempted_count": len(candidates),
        "accepted_count": len(candidates),
        "promoted_count": len(promoted),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "duplicate_count": 0,
        "memory_records_before": records_before,
        "memory_records_after": records_after,
        "faiss_ids_before": len(ids_before),
        "faiss_ids_after": len(ids_after),
        "faiss_ntotal_before": ntotal_before,
        "faiss_ntotal_after": ntotal_after,
        "promoted": promoted,
        "skipped": skipped,
        "failed": failed,
        "snapshot_id": "20260626T094552_806821_09d_batch_8",
        "executed_utc": datetime.now(timezone.utc).isoformat(),
    }
    
    report_path = REPORT_DIR / "promotion_execution.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    
    print(f"\nReport saved: {report_path}")
    print(f"Promoted: {len(promoted)}/{len(candidates)}")
    
    return report


if __name__ == "__main__":
    main()
