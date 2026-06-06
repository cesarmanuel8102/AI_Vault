from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain.external_sources import self_improvement_first_five_patch_generation_dry_run as mod


CANDIDATE = {
    "patch_candidate_id": "candidate_eval",
    "review_id": "review_eval",
    "patch_plan_id": "plan_eval",
    "front_id": "EVALUATION_BENCHMARKS_QUALITY_GATES",
    "category": "evaluation_gate_gap",
    "patch_type": "test_patch",
    "candidate_status": "approved_for_future_patch_generation",
    "execution_allowed_now": False,
    "patch_generation_allowed_now": False,
    "requires_operator_approval": True,
    "required_tests": ["before after gate"],
    "acceptance_criteria": ["bad patch blocked"],
    "rollback_required": True,
}
REVIEW = {
    "review_id": "review_eval",
    "patch_plan_id": "plan_eval",
    "front_id": "EVALUATION_BENCHMARKS_QUALITY_GATES",
    "category": "evaluation_gate_gap",
    "decision": "approve_for_patch_candidate",
    "required_tests": ["before after gate"],
    "acceptance_criteria": ["bad patch blocked"],
}
CANDIDATES = [
    CANDIDATE,
    dict(CANDIDATE, patch_candidate_id="candidate_auto", review_id="review_auto", patch_plan_id="plan_auto", front_id="AUTO_CODING_AGENTS_PATCH_GENERATION", category="patch_hygiene_gap", patch_type="policy_patch"),
]
REVIEWS = [REVIEW, dict(REVIEW, review_id="review_auto", patch_plan_id="plan_auto", front_id="AUTO_CODING_AGENTS_PATCH_GENERATION", category="patch_hygiene_gap")]


def fake_review_run(output_dir: str) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "first_five_patch_candidate_queue.json").write_text(json.dumps(CANDIDATES, indent=2), encoding="utf-8")
    (out / "first_five_patch_plan_reviews.json").write_text(json.dumps(REVIEWS, indent=2), encoding="utf-8")
    (out / "first_five_patch_plan_review_summary.json").write_text(
        json.dumps({"ok": True, "approved_candidates": len(CANDIDATES)}, indent=2), encoding="utf-8"
    )
    return {"ok": True, "approved_candidates": len(CANDIDATES), "patches_applied": False}


def run_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "run_first_five_patch_plan_review_dry_run", fake_review_run)
    out = tmp_path / "patch_generation_run"
    result = mod.run_first_five_patch_generation_dry_run(str(out))
    return out, result


def proposal():
    return mod.build_patch_proposal(CANDIDATE, REVIEW)


def test_import_module():
    assert mod is not None


def test_build_patch_proposal_exists():
    assert callable(mod.build_patch_proposal)


def test_build_all_patch_proposals_exists():
    assert callable(mod.build_all_patch_proposals)


def test_render_dry_run_pseudo_diff_exists():
    assert callable(mod.render_dry_run_pseudo_diff)


def test_build_operator_review_packet_exists():
    assert callable(mod.build_operator_review_packet)


def test_run_first_five_patch_generation_dry_run_exists():
    assert callable(mod.run_first_five_patch_generation_dry_run)


def test_now_utc_exists():
    assert callable(mod.now_utc)


def test_load_patch_candidate_queue_artifacts_exists():
    assert callable(mod.load_patch_candidate_queue_artifacts)


def test_summarize_patch_generation_exists():
    assert callable(mod.summarize_patch_generation)


def test_proposal_status_dry_run_patch_proposal_only():
    assert proposal()["proposal_status"] == "dry_run_patch_proposal_only"


def test_proposal_pseudo_diff_generated_true():
    assert proposal()["pseudo_diff_generated"] is True


def test_proposal_pseudo_diff_is_applicable_false():
    assert proposal()["pseudo_diff_is_applicable"] is False


def test_proposal_patch_applied_false():
    assert proposal()["patch_applied"] is False


def test_proposal_patch_staged_false():
    assert proposal()["patch_staged"] is False


def test_proposal_operator_review_required_true():
    assert proposal()["operator_review_required"] is True


def test_proposal_memory_write_allowed_false():
    assert proposal()["memory_write_allowed"] is False


def test_proposal_faiss_write_allowed_false():
    assert proposal()["faiss_write_allowed"] is False


def test_proposal_real_write_allowed_false():
    assert proposal()["real_write_allowed"] is False


def test_proposal_promotion_allowed_false():
    assert proposal()["promotion_allowed"] is False


def test_proposal_has_forbidden_files():
    assert "memory/semantic/*" in proposal()["files_forbidden_to_modify"]
    assert "tmp_agent/strategies/*" in proposal()["files_forbidden_to_modify"]


def test_proposal_has_required_tests():
    assert proposal()["required_tests"]


def test_proposal_has_acceptance_criteria():
    assert proposal()["acceptance_criteria"]


def test_proposal_has_rollback_instructions():
    assert proposal()["rollback_instructions"]


def test_pseudo_diff_contains_dry_run_banner():
    assert "DRY RUN PATCH PROPOSAL ONLY" in mod.render_dry_run_pseudo_diff(proposal())


def test_pseudo_diff_contains_not_applied():
    assert "not_applied" in mod.render_dry_run_pseudo_diff(proposal())


def test_pseudo_diff_contains_not_staged():
    assert "not_staged" in mod.render_dry_run_pseudo_diff(proposal())


def test_pseudo_diff_says_not_executable():
    assert "NO ES UN DIFF EJECUTABLE" in mod.render_dry_run_pseudo_diff(proposal())


def test_pseudo_diff_says_operator_approval_required():
    assert "REQUIERE APROBACION DEL OPERADOR" in mod.render_dry_run_pseudo_diff(proposal())


def test_pseudo_diff_does_not_contain_diff_git():
    assert "diff --git" not in mod.render_dry_run_pseudo_diff(proposal())


def test_pseudo_diff_does_not_contain_plus_b():
    assert "+++ b/" not in mod.render_dry_run_pseudo_diff(proposal())


def test_pseudo_diff_does_not_contain_minus_a():
    assert "--- a/" not in mod.render_dry_run_pseudo_diff(proposal())


def test_packet_status_operator_review_required():
    packet = mod.build_operator_review_packet([proposal()])
    assert packet["status"] == "operator_review_required"


def test_packet_execution_allowed_now_false():
    assert mod.build_operator_review_packet([])["execution_allowed_now"] is False


def test_packet_patch_application_allowed_now_false():
    assert mod.build_operator_review_packet([])["patch_application_allowed_now"] is False


def test_packet_patches_applied_false():
    assert mod.build_operator_review_packet([])["patches_applied"] is False


def test_packet_patches_staged_false():
    assert mod.build_operator_review_packet([])["patches_staged"] is False


def test_packet_requires_operator_approval_true():
    assert mod.build_operator_review_packet([])["requires_operator_approval"] is True


def test_packet_writes_allowed_false():
    assert mod.build_operator_review_packet([])["writes_allowed"] is False


def test_packet_memory_write_allowed_false():
    assert mod.build_operator_review_packet([])["memory_write_allowed"] is False


def test_packet_faiss_write_allowed_false():
    assert mod.build_operator_review_packet([])["faiss_write_allowed"] is False


def test_packet_promotion_allowed_false():
    assert mod.build_operator_review_packet([])["promotion_allowed"] is False


def test_packet_next_safe_front_correct():
    assert mod.build_operator_review_packet([])["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-GENERATION-REVIEW-DRY-RUN-01"


def test_packet_approval_options_present():
    packet = mod.build_operator_review_packet([])
    assert "approve_one_for_real_patch_planning" in packet["approval_options"]


def test_build_all_patch_proposals_uses_approved_candidates():
    proposals = mod.build_all_patch_proposals(CANDIDATES, REVIEWS)
    assert len(proposals) == len(CANDIDATES)


def test_summary_counts_proposals_and_pseudo_diffs():
    summary = mod.summarize_patch_generation([proposal()])
    assert summary["proposals_count"] == 1
    assert summary["pseudo_diffs_created"] == 1


def test_summary_disables_application_and_stage():
    summary = mod.summarize_patch_generation([proposal()])
    assert summary["patch_application_allowed_now"] is False
    assert summary["patches_applied"] is False
    assert summary["patches_staged"] is False


def test_run_writes_proposals_json(tmp_path, monkeypatch):
    out, result = run_demo(tmp_path, monkeypatch)
    assert result["ok"] is True
    assert (out / "first_five_patch_generation_proposals.json").exists()


def test_run_writes_proposals_jsonl(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_generation_proposals.jsonl").exists()


def test_run_writes_summary_json(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_generation_summary.json").exists()


def test_run_writes_operator_review_packet_json(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_generation_operator_review_packet.json").exists()


def test_run_writes_report_md(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_generation_report.md").exists()


def test_run_writes_pseudo_diffs_directory(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "pseudo_diffs").is_dir()
    assert list((out / "pseudo_diffs").glob("*.txt"))


def test_report_is_spanish_readable(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    report = (out / "first_five_patch_generation_report.md").read_text(encoding="utf-8")
    assert "Generacion de propuestas" in report
    assert "Que NO se aplico" in report
    assert "revision humana" in report.lower()


def test_no_token_leak_in_outputs(tmp_path, monkeypatch):
    out, result = run_demo(tmp_path, monkeypatch)
    assert result["token_leak_detected"] is False
    assert mod._output_has_token_marker(out) is False


def test_run_no_memory_semantic_write(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["memory_write_performed"] is False


def test_run_no_faiss_write(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["faiss_write_performed"] is False


def test_run_no_real_write(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["real_write_performed"] is False


def test_run_no_promotion(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["promotion_performed"] is False


def test_run_no_runtime_chat_integration(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["runtime_chat_integration"] is False


def test_run_no_trading_b8(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["trading_used"] is False
    assert result["b8_touched"] is False


def test_run_patches_applied_false(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["patches_applied"] is False


def test_run_patches_staged_false(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["patches_staged"] is False


def test_at_least_one_proposal_generated_if_candidates_exist(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["approved_candidates"] > 0
    assert result["proposals_count"] >= 1


def test_no_target_file_is_directly_modified(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    allowed = {
        "run_patch_plan_review",
        "first_five_patch_generation_proposals.json",
        "first_five_patch_generation_proposals.jsonl",
        "first_five_patch_generation_summary.json",
        "first_five_patch_generation_operator_review_packet.json",
        "first_five_patch_generation_report.md",
        "pseudo_diffs",
    }
    assert {item.name for item in out.iterdir()} <= allowed


def test_pseudo_diffs_are_non_applicable_text_only(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    text = "\n".join(path.read_text(encoding="utf-8") for path in (out / "pseudo_diffs").glob("*.txt"))
    assert "NO ES UN DIFF EJECUTABLE" in text
    assert "diff --git" not in text
    assert "+++ b/" not in text
    assert "--- a/" not in text


def test_module_has_no_runtime_imports():
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "tmp_agent.brain_v9.main" not in source
    assert "tmp_agent.brain_v9.core.session" not in source


def test_module_has_no_semantic_writer_imports():
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "semantic_memory_faiss" not in source
    assert "semantic_memory_adapter_real" not in source


def test_module_has_no_network_or_subprocess():
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "requests" not in source
    assert "httpx" not in source
    assert "subprocess" not in source


def test_load_patch_candidate_queue_artifacts_reads_expected_files(tmp_path):
    (tmp_path / "first_five_patch_candidate_queue.json").write_text(json.dumps(CANDIDATES), encoding="utf-8")
    (tmp_path / "first_five_patch_plan_reviews.json").write_text(json.dumps(REVIEWS), encoding="utf-8")
    artifacts = mod.load_patch_candidate_queue_artifacts(str(tmp_path))
    assert len(artifacts["candidate_queue"]) == 2
    assert len(artifacts["reviews"]) == 2


def test_load_patch_candidate_queue_artifacts_handles_missing_files(tmp_path):
    artifacts = mod.load_patch_candidate_queue_artifacts(str(tmp_path))
    assert artifacts["candidate_queue"] == []
    assert artifacts["reviews"] == []


def test_proposal_ids_are_stable_for_same_input():
    first = mod.build_patch_proposal(CANDIDATE, REVIEW)["patch_proposal_id"]
    second = mod.build_patch_proposal(CANDIDATE, REVIEW)["patch_proposal_id"]
    assert first == second


def test_empty_candidates_produce_empty_proposals():
    assert mod.build_all_patch_proposals([], REVIEWS) == []
