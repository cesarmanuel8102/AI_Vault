import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "tmp_agent" / "front_brain_codex_current_run_keep_knowledge_add_missing_core_01"

def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def test_final_report_complete_and_journal_append_authorized():
    report = json.loads((FRONT / "final_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "HOTFIX_CURRENT_RUN_KEEP_KNOWLEDGE_ADD_MISSING_CORE_COMPLETED"
    assert report["journal_append_authorization"]["autonomous_journal_append_included"] is True
    assert report["journal_append_authorization"]["append_only_verified"] is True
    assert report["journal_append_authorization"]["semantic_faiss_effect"] is False

def test_missing_core_domains_promoted_and_auxiliary_kept():
    records = load_jsonl(ROOT / "memory/semantic/semantic_memory.jsonl")
    metas = [(r.get("metadata") or {}) for r in records]
    core = {m.get("canonical_domain") for m in metas if m.get("domain_class") == "core"}
    aux = {m.get("canonical_domain") for m in metas if m.get("domain_class") == "auxiliary"}
    assert "external_source_learning_pipeline_github_repo_docs_official_sources" in core
    assert "autonomy_dashboard_visual_trace_self_improvement_governance" in core
    assert "flatbed_trucking_dispatcher_automation_business_operations" in aux
    assert "english_career_professional_communication" in aux

def test_semantic_faiss_delta_is_six_for_missing_core():
    verify = json.loads((FRONT / "final_consistency_verify.json").read_text(encoding="utf-8"))
    assert verify["semantic_lines_delta_from_start"] == 6
    assert verify["faiss_ids_delta_from_start"] == 6
    assert verify["faiss_ntotal_delta_from_start"] == 6

def test_no_forbidden_scope_staged():
    import subprocess
    out = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    forbidden = ["trading/", "tmp_agent/strategies/", "B8/", ".env"]
    for item in forbidden:
        assert item not in out
