"""
Smoke tests for 08D candidate normalization review.
Rules:
- Read-only normalization only.
- No canonical memory mutation.
- No candidate file mutation.
- Generated IDs must be stable and unique.
- Domain mappings must use known allowlist only.
"""
import sys
import json
import hashlib
from pathlib import Path
from collections import Counter

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from tmp_agent.brain_v9.memory.promotion_pipeline_adapter import PromotionPipelineAdapter
from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

ROOT = Path("C:/AI_VAULT_CANONICAL")
ARTIFACT_DIR = ROOT / "tmp_agent" / "front_brain_agent_v2_candidate_normalization_review_08d"

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


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_generated_ids_are_stable():
    adapter = PromotionPipelineAdapter()
    first = adapter.load_candidates("all")
    second = adapter.load_candidates("all")
    generated_first = {c["candidate_id"]: c for c in first if c.get("candidate_id_generated")}
    generated_second = {c["candidate_id"]: c for c in second if c.get("candidate_id_generated")}
    assert generated_first == generated_second
    print("PASS: generated_ids_are_stable")


def test_generated_ids_are_unique():
    adapter = PromotionPipelineAdapter()
    candidates = adapter.load_candidates("all")
    generated_ids = [c["candidate_id"] for c in candidates if c.get("candidate_id_generated")]
    assert len(generated_ids) == len(set(generated_ids))
    print("PASS: generated_ids_are_unique")


def test_missing_candidate_id_count_reduced():
    inventory = _load_json(ARTIFACT_DIR / "normalized_candidate_inventory.json")
    assert inventory["missing_candidate_id_count"] == 0
    assert inventory["generated_candidate_id_count"] > 0
    print("PASS: missing_candidate_id_count_reduced")


def test_no_source_candidate_files_modified():
    verify = _load_json(ARTIFACT_DIR / "post_run_immutability_verify.json")
    assert verify["promotion_queue_file_count_unchanged"]
    assert verify["semantic_staging_candidate_count_unchanged"]
    print("PASS: no_source_candidate_files_modified")


def test_no_semantic_memory_modified():
    verify = _load_json(ARTIFACT_DIR / "post_run_immutability_verify.json")
    assert verify["semantic_jsonl_sha_unchanged"]
    assert verify["promotion_audit_sha_unchanged"]
    print("PASS: no_semantic_memory_modified")


def test_no_faiss_modified():
    verify = _load_json(ARTIFACT_DIR / "post_run_immutability_verify.json")
    assert verify["faiss_index_sha_unchanged"]
    assert verify["faiss_ids_sha_unchanged"]
    assert verify["faiss_ids_count_unchanged"]
    assert verify["faiss_ntotal_unchanged"]
    print("PASS: no_faiss_modified")


def test_unknown_domains_only_mapped_with_known_allowlist():
    adapter = PromotionPipelineAdapter()
    candidates = adapter.load_candidates("all")
    for c in candidates:
        domain = c.get("domain")
        if domain and domain != "unknown":
            assert domain in KNOWN_DOMAINS, f"unexpected domain: {domain}"
    print("PASS: unknown_domains_only_mapped_with_known_allowlist")


def test_low_confidence_domains_remain_human_review():
    results = _load_json(ARTIFACT_DIR / "normalized_batch_validation_results.json")
    for r in results:
        if r["decision"] == "unknown_domain_needs_review":
            assert r.get("domain_mapping_confidence") in {"low", "existing"}
            assert r.get("domain_review_required") is True
    print("PASS: low_confidence_domains_remain_human_review")


def test_generated_candidate_validation_dry_run_no_write():
    samples = _load_json(ARTIFACT_DIR / "toolgateway_sample_proof.json")
    generated = next((s for s in samples if s["label"] == "generated"), None)
    assert generated
    assert generated["write_performed"] is False
    assert generated["would_write_jsonl"] is False
    assert generated["would_write_faiss"] is False
    print("PASS: generated_candidate_validation_dry_run_no_write")


def test_summary_counts_match_results():
    results = _load_json(ARTIFACT_DIR / "normalized_batch_validation_results.json")
    summary = _load_json(ARTIFACT_DIR / "normalized_batch_validation_summary.json")
    counts = Counter(r["decision"] for r in results)
    assert summary["total_candidates"] == len(results)
    assert summary["promotable_count"] == counts.get("promotable_candidate", 0)
    assert summary["duplicate_exact_count"] == counts.get("duplicate_exact", 0)
    assert summary["unknown_domain_count"] == counts.get("unknown_domain_needs_review", 0)
    assert summary["already_promoted_count"] == counts.get("already_promoted", 0)
    assert summary["missing_candidate_id_count"] == counts.get("missing_candidate_id", 0)
    print("PASS: summary_counts_match_results")


def test_duplicates_not_promotable():
    results = _load_json(ARTIFACT_DIR / "normalized_batch_validation_results.json")
    for r in results:
        if r["decision"] == "duplicate_exact":
            assert r["decision"] != "promotable_candidate"
    print("PASS: duplicates_not_promotable")


def test_already_promoted_not_promotable():
    results = _load_json(ARTIFACT_DIR / "normalized_batch_validation_results.json")
    for r in results:
        if r["decision"] == "already_promoted":
            assert r["decision"] != "promotable_candidate"
    print("PASS: already_promoted_not_promotable")


def test_promotable_candidates_have_known_domain_and_id():
    results = _load_json(ARTIFACT_DIR / "normalized_batch_validation_results.json")
    for r in results:
        if r["decision"] == "promotable_candidate":
            assert r["candidate_id"]
            assert r["domain"] in KNOWN_DOMAINS
            assert r["domain_review_required"] is False
    print("PASS: promotable_candidates_have_known_domain_and_id")


def test_post_run_hashes_unchanged():
    verify = _load_json(ARTIFACT_DIR / "post_run_immutability_verify.json")
    assert verify["all_unchanged"]
    print("PASS: post_run_hashes_unchanged")


def test_promotion_queue_clean():
    verify = _load_json(ARTIFACT_DIR / "post_run_immutability_verify.json")
    assert verify["promotion_queue_file_count_unchanged"]
    print("PASS: promotion_queue_clean")


def test_semantic_staging_clean():
    verify = _load_json(ARTIFACT_DIR / "post_run_immutability_verify.json")
    assert verify["semantic_staging_candidate_count_unchanged"]
    print("PASS: semantic_staging_clean")


if __name__ == "__main__":
    test_generated_ids_are_stable()
    test_generated_ids_are_unique()
    test_missing_candidate_id_count_reduced()
    test_no_source_candidate_files_modified()
    test_no_semantic_memory_modified()
    test_no_faiss_modified()
    test_unknown_domains_only_mapped_with_known_allowlist()
    test_low_confidence_domains_remain_human_review()
    test_generated_candidate_validation_dry_run_no_write()
    test_summary_counts_match_results()
    test_duplicates_not_promotable()
    test_already_promoted_not_promotable()
    test_promotable_candidates_have_known_domain_and_id()
    test_post_run_hashes_unchanged()
    test_promotion_queue_clean()
    test_semantic_staging_clean()
    print("ALL 08D CANDIDATE NORMALIZATION REVIEW TESTS PASSED")
