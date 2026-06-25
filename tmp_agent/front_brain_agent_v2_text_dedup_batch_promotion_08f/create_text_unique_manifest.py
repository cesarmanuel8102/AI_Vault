import json
import hashlib
import re
import sys
from pathlib import Path
from collections import OrderedDict, defaultdict

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from tmp_agent.brain_v9.memory.promotion_pipeline_adapter import PromotionPipelineAdapter

ROOT = Path("C:/AI_VAULT_CANONICAL")
SRC = ROOT / "tmp_agent" / "front_brain_agent_v2_candidate_normalization_review_08d"
DST = ROOT / "tmp_agent" / "front_brain_agent_v2_text_dedup_batch_promotion_08f"
DST.mkdir(parents=True, exist_ok=True)


def normalize_text(text):
    t = str(text or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t


adapter = PromotionPipelineAdapter()
candidates = adapter.load_candidates("all")

# Load canonical texts for pre-check
jsonl_path = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
canonical_texts = set()
for line in jsonl_path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    rec = json.loads(line)
    canonical_texts.add(normalize_text(rec.get("text", "")))

# First deduplicate by candidate_id, preferring promotion_queue
by_id = OrderedDict()
for c in candidates:
    cid = c.get("candidate_id")
    if not cid:
        continue
    if cid in by_id:
        # Prefer promotion_queue
        if c.get("source_bucket") == "promotion_queue" and by_id[cid].get("source_bucket") != "promotion_queue":
            by_id[cid] = c
    else:
        by_id[cid] = c

# Then deduplicate by exact normalized text
by_text = OrderedDict()
duplicate_text_groups = defaultdict(list)
dropped_duplicate_text_entries = []
for cid, c in by_id.items():
    norm = normalize_text(c.get("text", ""))
    if not norm:
        continue
    if norm in by_text:
        duplicate_text_groups[norm].append(cid)
        dropped_duplicate_text_entries.append({"candidate_id": cid, "source": c.get("source_bucket")})
        continue
    # Check against canonical memory
    if norm in canonical_texts:
        duplicate_text_groups[norm].append(cid)
        dropped_duplicate_text_entries.append({"candidate_id": cid, "source": c.get("source_bucket"), "reason": "already_in_canonical"})
        continue
    by_text[norm] = c

# Filter only promotable candidates and apply full validation
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
manifest = []
for norm, c in by_text.items():
    validation = adapter.validate_candidate(c)
    valid = (
        validation["valid"] is True
        and c.get("domain_review_required") is False
        and c.get("domain") in KNOWN_DOMAINS
        and c.get("text")
        and not c.get("raw_cot_exposed")
        and not c.get("secrets_exposed")
        and not c.get("trading_execution_detected")
    )
    if not valid:
        continue
    manifest.append({
        "candidate_id": c["candidate_id"],
        "source": c.get("source_bucket", "unknown"),
        "source_path": c.get("source_path", ""),
        "domain": c.get("domain", "unknown"),
        "canonical_domain": c.get("canonical_domain", "unknown"),
        "category": c.get("category", "unknown"),
        "text": norm,
        "normalized_text": norm,
        "normalized_text_sha256": hashlib.sha256(norm.encode("utf-8")).hexdigest(),
        "text_length": len(norm),
    })

original_promotable = [r for r in json.loads((SRC / "normalized_batch_validation_results.json").read_text(encoding="utf-8")) if r.get("decision") == "promotable_candidate"]

report = {
    "original_promotable_entries": len(original_promotable),
    "unique_candidate_id_count": len(by_id),
    "unique_text_count": len(by_text),
    "dropped_duplicate_id_entries": len(original_promotable) - len(by_id),
    "dropped_duplicate_text_entries": len(dropped_duplicate_text_entries),
    "duplicate_text_groups": {hashlib.sha256(k.encode("utf-8")).hexdigest()[:16]: v for k, v in duplicate_text_groups.items()},
    "final_manifest_count": len(manifest),
    "final_candidate_ids": [m["candidate_id"] for m in manifest],
}

(DST / "promotion_manifest_24_text_unique.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
(DST / "text_deduplication_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

print(json.dumps(report, indent=2))
assert len(manifest) == 24, f"expected 24 text-unique candidates, got {len(manifest)}"
print("PASS: text-unique manifest == 24")
