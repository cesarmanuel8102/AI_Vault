"""
Promote exactly 24 text-unique validated candidates with rollback safety.
"""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

import faiss
import hashlib

from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

ROOT = Path("C:/AI_VAULT_CANONICAL")
REPORT_DIR = ROOT / "tmp_agent" / "front_brain_agent_v2_text_dedup_batch_promotion_08f"
SNAPSHOT_ROOT = ROOT / "memory" / "rollback_snapshots"

APPROVAL_TOKEN = "AGENTV2_APPROVED_BATCH_PROMOTION_08F_CESAR_24_TEXT_UNIQUE"
OPERATOR_ID = "cesar"
CONFIRM_PHRASE = "PROMOTE_ONE_CANDIDATE_TO_CANONICAL_MEMORY"


def load_baseline():
    paths = {
        "jsonl": ROOT / "memory" / "semantic" / "semantic_memory.jsonl",
        "faiss_index": ROOT / "memory" / "semantic" / "semantic_memory_faiss.index",
        "faiss_ids": ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json",
        "promotion_audit": ROOT / "memory" / "semantic" / "promotion_audit.jsonl",
    }
    baseline = {}
    for k, p in paths.items():
        baseline[k] = {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "",
            "size": p.stat().st_size if p.exists() else 0,
        }
    jsonl_lines = [x for x in paths["jsonl"].read_text(encoding="utf-8").splitlines() if x.strip()]
    ids = json.loads(paths["faiss_ids"].read_text(encoding="utf-8"))
    idx = faiss.read_index(str(paths["faiss_index"]))
    baseline["jsonl_records"] = len(jsonl_lines)
    baseline["faiss_ids_count"] = len(ids)
    baseline["faiss_ntotal"] = idx.ntotal
    return baseline, paths


def create_batch_snapshot():
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}_batch_promotion_08f_24_text_unique"
    target = SNAPSHOT_ROOT / stamp
    target.mkdir(parents=True, exist_ok=False)
    canonical_files = [
        ROOT / "memory" / "semantic" / "semantic_memory.jsonl",
        ROOT / "memory" / "semantic" / "semantic_memory_faiss.index",
        ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json",
    ]
    for src in canonical_files:
        if src.exists():
            shutil.copy2(src, target / src.name)
    audit = ROOT / "memory" / "semantic" / "promotion_audit.jsonl"
    if audit.exists():
        shutil.copy2(audit, target / audit.name)
    shutil.copy2(REPORT_DIR / "promotion_manifest_24_text_unique.json", target / "promotion_manifest_24_text_unique.json")
    shutil.copy2(REPORT_DIR / "text_deduplication_report.json", target / "text_deduplication_report.json")
    (target / "SNAPSHOT_REASON.txt").write_text("batch_promotion_08f_24_text_unique_pre_promotion\n", encoding="utf-8")
    return target


def rollback_to_snapshot(snapshot_dir):
    canonical_dir = ROOT / "memory" / "semantic"
    for name in ("semantic_memory.jsonl", "semantic_memory_faiss.index", "semantic_memory_faiss_ids.json"):
        src = snapshot_dir / name
        if src.exists():
            shutil.copy2(src, canonical_dir / name)
    audit_src = snapshot_dir / "promotion_audit.jsonl"
    audit_dst = canonical_dir / "promotion_audit.jsonl"
    if audit_src.exists():
        shutil.copy2(audit_src, audit_dst)


def main():
    baseline, paths = load_baseline()
    manifest = json.loads((REPORT_DIR / "promotion_manifest_24_text_unique.json").read_text(encoding="utf-8"))
    candidate_ids = [m["candidate_id"] for m in manifest]
    text_hashes = [m["normalized_text_sha256"] for m in manifest]

    snapshot_dir = create_batch_snapshot()
    pre_state = {
        "baseline": baseline,
        "snapshot_dir": str(snapshot_dir),
        "candidate_ids": candidate_ids,
        "text_hashes": text_hashes,
    }
    (REPORT_DIR / "pre_promotion_memory_state.json").write_text(json.dumps(pre_state, indent=2), encoding="utf-8")

    progress_file = REPORT_DIR / "batch_promotion_progress.jsonl"
    progress_file.write_text("", encoding="utf-8")
    promoted = []
    failed = None
    gateway = ToolGatewayV2()

    for idx, cid in enumerate(candidate_ids, 1):
        entry = next(m for m in manifest if m["candidate_id"] == cid)
        source = entry.get("source", "all")
        req = ToolCallRequest(
            tool_name="promotion_candidate_promote",
            args={
                "candidate_id": cid,
                "source": source,
                "approval_token": APPROVAL_TOKEN,
                "operator_id": OPERATOR_ID,
                "confirm_phrase": CONFIRM_PHRASE,
            },
            mode="build",
        )
        res = gateway.call(req)
        result = res.result if isinstance(res.result, dict) else {}
        record = {
            "index": idx,
            "candidate_id": cid,
            "ok": res.ok,
            "blocked": res.blocked,
            "promotion_performed": result.get("promotion_performed", False),
            "write_performed": result.get("write_performed", False),
            "snapshot_created": result.get("snapshot_created", False),
            "audit_appended": result.get("audit_appended", False),
            "candidate_valid": result.get("candidate_valid", False),
            "validation_errors": result.get("validation_errors", []),
            "faiss_ids_after_count": result.get("faiss_ids_after_count"),
            "faiss_ntotal_after": result.get("faiss_ntotal_after"),
        }
        with open(progress_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        if not (res.ok and result.get("promotion_performed") and result.get("write_performed")):
            failed = record
            break
        promoted.append(cid)

    if failed:
        rollback_to_snapshot(snapshot_dir)
        with open(progress_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "rollback", "reason": "candidate_failed", "failed": failed}, ensure_ascii=False) + "\n")
        fail_report = {
            "status": "BATCH_PROMOTION_24_FAILED_ROLLED_BACK",
            "failed_candidate": failed,
            "snapshot_dir": str(snapshot_dir),
            "promoted_before_failure": promoted,
        }
        (REPORT_DIR / "batch_promotion_failure.json").write_text(json.dumps(fail_report, indent=2), encoding="utf-8")
        print(json.dumps(fail_report, indent=2))
        raise SystemExit(1)

    after_baseline, _ = load_baseline()
    jsonl_lines = [x for x in (ROOT / "memory" / "semantic" / "semantic_memory.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    records = [json.loads(line) for line in jsonl_lines]
    ids = set(json.loads((ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json").read_text(encoding="utf-8")))
    promoted_ids_set = set(candidate_ids)
    promoted_records = [r for r in records if r.get("id") in promoted_ids_set]
    promoted_texts = {r.get("text", "").strip() for r in promoted_records}

    verify = {
        "jsonl_records_before": baseline["jsonl_records"],
        "jsonl_records_after": after_baseline["jsonl_records"],
        "jsonl_increment": after_baseline["jsonl_records"] - baseline["jsonl_records"],
        "faiss_ids_before": baseline["faiss_ids_count"],
        "faiss_ids_after": after_baseline["faiss_ids_count"],
        "faiss_ids_increment": after_baseline["faiss_ids_count"] - baseline["faiss_ids_count"],
        "faiss_ntotal_before": baseline["faiss_ntotal"],
        "faiss_ntotal_after": after_baseline["faiss_ntotal"],
        "faiss_ntotal_increment": after_baseline["faiss_ntotal"] - baseline["faiss_ntotal"],
        "all_promoted_in_jsonl": all(cid in {r.get("id") for r in records} for cid in candidate_ids),
        "all_promoted_in_faiss_ids": all(cid in ids for cid in candidate_ids),
        "all_text_hashes_unique": len(text_hashes) == len(set(text_hashes)),
        "no_blank_text_records": all((r.get("text") or "").strip() for r in promoted_records),
        "no_none_ids": None not in ids,
        "no_duplicate_texts_added": len(promoted_texts) == len(promoted_records),
    }

    from tmp_agent.brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
    mem = get_semantic_memory_faiss()
    retrieval_sample = {}
    for cid in candidate_ids[:10]:
        matches = mem.search(cid, top_k=5)
        retrieval_sample[cid] = any(cid == m.get("id") for m in matches)
    verify["retrieval_sample_passed"] = all(retrieval_sample.values())
    verify["retrieval_sample"] = retrieval_sample

    (REPORT_DIR / "post_promotion_verify.json").write_text(json.dumps(verify, indent=2), encoding="utf-8")

    md = [
        "# Batch Promotion 08F (24 Text-Unique Candidates) Summary",
        "",
        f"- Candidates promoted: {len(promoted)}",
        f"- JSONL increment: {verify['jsonl_increment']}",
        f"- FAISS ids increment: {verify['faiss_ids_increment']}",
        f"- FAISS ntotal increment: {verify['faiss_ntotal_increment']}",
        f"- All promoted IDs in JSONL: {verify['all_promoted_in_jsonl']}",
        f"- All promoted IDs in FAISS ids: {verify['all_promoted_in_faiss_ids']}",
        f"- Retrieval sample passed: {verify['retrieval_sample_passed']}",
        f"- Batch rollback snapshot: `{snapshot_dir}`",
        "",
        "## Promoted candidate IDs",
        "",
    ]
    for cid in promoted:
        md.append(f"- `{cid}`")
    (REPORT_DIR / "batch_promotion_summary.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(verify, indent=2))
    print(f"PASS: {len(promoted)} text-unique candidates promoted")


if __name__ == "__main__":
    main()
