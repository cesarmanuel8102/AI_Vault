import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tmp_agent" / "front_brain_provider_reliability_rootcause_01"


def load_json(name: str):
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def test_required_reports_exist():
    for name in [
        "preflight.json",
        "prior_failure_summary.json",
        "provider_route_map.json",
        "provider_probe_matrix.json",
        "root_cause_classification.json",
        "patch_decision.json",
        "final_report.json",
        "final_safety_verify.json",
    ]:
        assert (EVIDENCE / name).exists(), name


def test_preflight_and_probe_metrics():
    preflight = load_json("preflight.json")
    matrix = load_json("provider_probe_matrix.json")
    assert preflight["hard_gate_pass"] is True
    assert matrix["metrics"]["kimi_direct_success_rate"] >= 0.0
    assert matrix["metrics"]["brain_normal_route_dry_run_rate"] == 1.0
    assert matrix["metrics"]["brain_normal_route_real_llm_rate"] == 0.0


def test_root_cause_and_patch_decision():
    root_cause = load_json("root_cause_classification.json")
    patch = load_json("patch_decision.json")
    assert "ROUTE_SEMANTICS_BUG" in root_cause["classification"]
    assert "DRY_RUN_GUARD_OVERMATCH" in root_cause["classification"]
    assert patch["patch_applied"] is True
    assert "tmp_agent/brain_v9/api/openai_compat.py" in patch["files_changed"]
    assert "tmp_agent/brain_v9/core/router_entrypoint.py" in patch["files_changed"]


def test_post_patch_route_improved():
    post = load_json("post_patch_probe_matrix.json")
    metrics = post["metrics"]
    assert metrics["normal_llm_grounded_route_real_llm_rate"] == 1.0
    assert metrics["normal_llm_grounded_route_dry_run_rate"] == 0.0
    assert metrics["post_patch_calls"] <= 10


def test_canonical_memory_and_safety_unchanged():
    safety = load_json("final_safety_verify.json")
    assert safety["semantic_lines_before"] == safety["semantic_lines_after"]
    assert safety["faiss_ids_before"] == safety["faiss_ids_after"]
    assert safety["faiss_ntotal_before"] == safety["faiss_ntotal_after"]
    assert safety["semantic_hash_unchanged"] is True
    assert safety["faiss_index_hash_unchanged"] is True
    assert safety["faiss_ids_hash_unchanged"] is True
    assert safety["canonical_semantic_mutated"] is False
    assert safety["faiss_mutated"] is False
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False
    assert safety["strategies_touched"] is False
    assert safety["raw_cot_exposed"] is False
    assert safety["secrets_exposed"] is False


def test_patch_source_contains_llm_grounded_eval_route():
    openai_compat = (ROOT / "tmp_agent/brain_v9/api/openai_compat.py").read_text(encoding="utf-8")
    router_entrypoint = (ROOT / "tmp_agent/brain_v9/core/router_entrypoint.py").read_text(encoding="utf-8")
    assert "llm_grounded_cycle" in openai_compat
    assert "llm_grounded_provider_eval" in openai_compat
    assert "llm_grounded_provider_eval" in router_entrypoint
    assert "memory_writes_blocked" in router_entrypoint
    assert "faiss_writes_blocked" in router_entrypoint


def test_final_report_roadmap_and_ledger():
    report = load_json("final_report.json")
    assert report["status"] == "BRAIN_PROVIDER_RELIABILITY_ROOTCAUSE_COMPLETED_WITH_PATCH"
    json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
