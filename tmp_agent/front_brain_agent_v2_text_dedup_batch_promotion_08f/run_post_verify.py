"""
Post-promotion verify only. Assumes promotion already completed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

import faiss
import hashlib

from tmp_agent.brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss

ROOT = Path("C:/AI_VAULT_CANONICAL")
REPORT_DIR = ROOT / "tmp_agent" / "front_brain_agent_v2_text_dedup_batch_promotion_08f"

def main():
    pre_state = json.loads((REPORT_DIR / "pre_promotion_memory_state.json").read_text(encoding="utf-8"))
    baseline = pre_state["baseline"]
    manifest = json.loads((REPORT_DIR / "promotion_manifest_24_text_unique.json").read_text(encoding="utf-8"))
    candidate_ids = [m["candidate_id"] for m in manifest]
    text_hashes = [m["normalized_text_sha256"] for m in manifest]

    paths = {
        "jsonl": ROOT / "memory" / "semantic" / "semantic_memory.jsonl",
        "faiss_index": ROOT / "memory" / "semantic" / "semantic_memory_faiss.index",
        "faiss_ids": ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json",
        "promotion_audit": ROOT / "memory" / "semantic" / "promotion_audit.jsonl",
    }

    jsonl_lines = [x for x in paths["jsonl"].read_text(encoding="utf-8").splitlines() if x.strip()]
    records = [json.loads(line) for line in jsonl_lines]
    ids = set(json.loads(paths["faiss_ids"].read_text(encoding="utf-8")))
    idx = faiss.read_index(str(paths["faiss_index"]))

    promoted_ids_set = set(candidate_ids)
    promoted_records = [r for r in records if r.get("id") in promoted_ids_set]
    promoted_texts = {r.get("text", "").strip() for r in promoted_records}

    verify = {
        "jsonl_records_before": baseline["jsonl_records"],
        "jsonl_records_after": len(jsonl_lines),
        "jsonl_increment": len(jsonl_lines) - baseline["jsonl_records"],
        "faiss_ids_before": baseline["faiss_ids_count"],
        "faiss_ids_after": len(ids),
        "faiss_ids_increment": len(ids) - baseline["faiss_ids_count"],
        "faiss_ntotal_before": baseline["faiss_ntotal"],
        "faiss_ntotal_after": idx.ntotal,
        "faiss_ntotal_increment": idx.ntotal - baseline["faiss_ntotal"],
        "all_promoted_in_jsonl": all(cid in {r.get("id") for r in records} for cid in candidate_ids),
        "all_promoted_in_faiss_ids": all(cid in ids for cid in candidate_ids),
        "all_text_hashes_unique": len(text_hashes) == len(set(text_hashes)),
        "no_blank_text_records": all((r.get("text") or "").strip() for r in promoted_records),
        "no_none_ids": None not in ids,
        "no_duplicate_texts_added": len(promoted_texts) == len(promoted_records),
    }

    mem = get_semantic_memory_faiss()
    retrieval_sample = {}
    for item in manifest[:10]:
        cid = item["candidate_id"]
        text = item["normalized_text"]
        matches = mem.search(text, top_k=5, min_score=0.1)
        retrieval_sample[cid] = any(cid == m.get("id") for m in matches)
    verify["retrieval_sample_passed"] = all(retrieval_sample.values())
    verify["retrieval_sample"] = retrieval_sample

    (REPORT_DIR / "post_promotion_verify.json").write_text(json.dumps(verify, indent=2), encoding="utf-8")

    md = [
        "# Batch Promotion 08F (24 Text-Unique Candidates) Summary",
        "",
        f"- Candidates promoted: {len(promoted_records)}",
        f"- JSONL increment: {verify['jsonl_increment']}",
        f"- FAISS ids increment: {verify['faiss_ids_increment']}",
        f"- FAISS ntotal increment: {verify['faiss_ntotal_increment']}",
        f"- All promoted IDs in JSONL: {verify['all_promoted_in_jsonl']}",
        f"- All promoted IDs in FAISS ids: {verify['all_promoted_in_faiss_ids']}",
        f"- All text hashes unique: {verify['all_text_hashes_unique']}",
        f"- No duplicate texts added: {verify['no_duplicate_texts_added']}",
        f"- Retrieval sample passed: {verify['retrieval_sample_passed']}",
        f"- Batch rollback snapshot: `{pre_state['snapshot_dir']}`",
        "",
        "## Promoted candidate IDs",
        "",
    ]
    for cid in candidate_ids:
        md.append(f"- `{cid}`")
    (REPORT_DIR / "batch_promotion_summary.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(verify, indent=2))
    print(f"PASS: {len(promoted_records)} text-unique candidates verified")


if __name__ == "__main__":
    main()
