from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain.external_sources import self_improvement_first_five_patch_plan_review_dry_run as mod


BASE_PLAN = {
    "patch_plan_id": "plan_safe",
    "recommendation_id": "rec_safe",
    "front_id": "EVALUATION_BENCHMARKS_QUALITY_GATES",
    "category": "evaluation_gate_gap",
    "severity": "medium",
    "patch_type": "test_patch",
    "plan_status": "planned_not_executed",
    "recommended_scope": "small",
    "target_files_suggested": ["tests/smoke/*"],
    "files_forbidden_to_modify": ["memory/semantic/*", "tmp_agent/strategies/*", "trading/*", "B8/*"],
    "implementation_steps": [{"step_id": "s1", "description": "Add fixture", "allowed_now": False}],
    "required_tests": ["before after gate"],
    "acceptance_criteria": ["bad patch blocked"],
    "rollback_plan": {"required": True},
    "risk_assessment": {"risk_level": "low", "risk_notes": "test-only"},
    "execution_allowed_now": False,
    "patch_generated": False,
    "patch_applied": False,
    "memory_write_allowed": False,
    "faiss_write_allowed": False,
    "real_write_allowed": False,
    "promotion_allowed": False,
}


def plan(**updates):
    item = dict(BASE_PLAN)
    item.update(updates)
    return item


PLAN_ITEMS = [
    plan(),
    plan(
        patch_plan_id="plan_security",
        recommendation_id="rec_security",
        front_id="SECURITY_SANDBOXING_SUPPLY_CHAIN",
        category="security_supply_chain_gap",
        patch_type="policy_patch",
        recommended_scope="medium",
        risk_assessment={"risk_level": "medium", "risk_notes": "security policy"},
    ),
]


def fake_patch_plan_run(output_dir: str) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "first_five_patch_plan_items.json").write_text(json.dumps(PLAN_ITEMS, indent=2), encoding="utf-8")
    (out / "first_five_patch_plan_summary.json").write_text(
        json.dumps({"ok": True, "plan_items": len(PLAN_ITEMS)}, indent=2), encoding="utf-8"
    )
    (out / "first_five_patch_plan_governance.json").write_text(
        json.dumps({"status": "plan_only_not_executable"}, indent=2), encoding="utf-8"
    )
    return {"ok": True, "plan_items": len(PLAN_ITEMS), "patches_applied": False}


def run_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "run_first_five_patch_plan_dry_run", fake_patch_plan_run)
    out = tmp_path / "patch_plan_review_run"
    result = mod.run_first_five_patch_plan_review_dry_run(str(out))
    return out, result


def test_import_module():
    assert mod is not None


def test_review_patch_plan_item_exists():
    assert callable(mod.review_patch_plan_item)


def test_review_all_patch_plan_items_exists():
    assert callable(mod.review_all_patch_plan_items)


def test_build_patch_candidate_queue_exists():
    assert callable(mod.build_patch_candidate_queue)


def test_build_review_governance_exists():
    assert callable(mod.build_review_governance)


def test_run_first_five_patch_plan_review_dry_run_exists():
    assert callable(mod.run_first_five_patch_plan_review_dry_run)


def test_now_utc_exists():
    assert callable(mod.now_utc)


def test_load_patch_plan_artifacts_exists():
    assert callable(mod.load_patch_plan_artifacts)


def test_summarize_patch_plan_review_exists():
    assert callable(mod.summarize_patch_plan_review)


def test_review_has_review_score():
    assert "review_score" in mod.review_patch_plan_item(BASE_PLAN)


def test_review_has_decision():
    assert "decision" in mod.review_patch_plan_item(BASE_PLAN)


def test_review_has_scores():
    assert "scores" in mod.review_patch_plan_item(BASE_PLAN)


def test_review_execution_allowed_now_false():
    assert mod.review_patch_plan_item(BASE_PLAN)["execution_allowed_now"] is False


def test_review_patch_generated_false():
    assert mod.review_patch_plan_item(BASE_PLAN)["patch_generated"] is False


def test_review_patch_applied_false():
    assert mod.review_patch_plan_item(BASE_PLAN)["patch_applied"] is False


def test_review_memory_write_allowed_false():
    assert mod.review_patch_plan_item(BASE_PLAN)["memory_write_allowed"] is False


def test_review_faiss_write_allowed_false():
    assert mod.review_patch_plan_item(BASE_PLAN)["faiss_write_allowed"] is False


def test_review_real_write_allowed_false():
    assert mod.review_patch_plan_item(BASE_PLAN)["real_write_allowed"] is False


def test_review_promotion_allowed_false():
    assert mod.review_patch_plan_item(BASE_PLAN)["promotion_allowed"] is False


def test_forbidden_target_file_rejected():
    review = mod.review_patch_plan_item(plan(target_files_suggested=["memory/semantic/semantic_memory.jsonl"]))
    assert review["decision"] == "reject_too_risky"
    assert "forbidden_target_file" in review["blocking_issues"]


def test_missing_tests_rejected_or_not_actionable():
    review = mod.review_patch_plan_item(plan(required_tests=[]))
    assert review["decision"] == "reject_not_actionable"


def test_missing_acceptance_criteria_not_actionable():
    review = mod.review_patch_plan_item(plan(acceptance_criteria=[]))
    assert review["decision"] == "reject_not_actionable"


def test_missing_steps_not_actionable():
    review = mod.review_patch_plan_item(plan(implementation_steps=[]))
    assert review["decision"] == "reject_not_actionable"


def test_large_scope_requests_scope_reduction():
    review = mod.review_patch_plan_item(plan(recommended_scope="large", risk_assessment={"risk_level": "medium"}))
    assert review["decision"] == "request_scope_reduction"


def test_too_many_targets_requests_scope_reduction():
    review = mod.review_patch_plan_item(plan(target_files_suggested=[f"tests/file_{i}.py" for i in range(6)]))
    assert review["decision"] == "request_scope_reduction"


def test_high_risk_rejected():
    review = mod.review_patch_plan_item(plan(risk_assessment={"risk_level": "high"}))
    assert review["decision"] == "reject_too_risky"


def test_safe_plan_approved_for_patch_candidate():
    review = mod.review_patch_plan_item(BASE_PLAN)
    assert review["decision"] == "approve_for_patch_candidate"
    assert review["patch_candidate_allowed"] is True


def test_unsupported_patch_type_not_approved():
    review = mod.review_patch_plan_item(plan(patch_type="runtime_write_patch"))
    assert review["decision"] != "approve_for_patch_candidate"


def test_candidate_queue_includes_only_approved_plans():
    reviews = [mod.review_patch_plan_item(BASE_PLAN), mod.review_patch_plan_item(plan(required_tests=[]))]
    queue = mod.build_patch_candidate_queue(reviews)
    assert len(queue) == 1
    assert queue[0]["review_id"] == reviews[0]["review_id"]


def test_candidate_queue_item_execution_allowed_now_false():
    queue = mod.build_patch_candidate_queue([mod.review_patch_plan_item(BASE_PLAN)])
    assert queue[0]["execution_allowed_now"] is False


def test_candidate_queue_item_patch_generation_allowed_now_false():
    queue = mod.build_patch_candidate_queue([mod.review_patch_plan_item(BASE_PLAN)])
    assert queue[0]["patch_generation_allowed_now"] is False


def test_candidate_queue_item_requires_operator_approval():
    queue = mod.build_patch_candidate_queue([mod.review_patch_plan_item(BASE_PLAN)])
    assert queue[0]["requires_operator_approval"] is True


def test_candidate_queue_next_safe_front_correct():
    queue = mod.build_patch_candidate_queue([mod.review_patch_plan_item(BASE_PLAN)])
    assert queue[0]["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-GENERATION-DRY-RUN-01"


def test_governance_status_review_only_not_executable():
    governance = mod.build_review_governance([mod.review_patch_plan_item(BASE_PLAN)])
    assert governance["status"] == "review_only_not_executable"


def test_governance_execution_allowed_now_false():
    governance = mod.build_review_governance([])
    assert governance["execution_allowed_now"] is False


def test_governance_patch_generation_allowed_now_false():
    governance = mod.build_review_governance([])
    assert governance["patch_generation_allowed_now"] is False


def test_governance_patches_generated_false():
    governance = mod.build_review_governance([])
    assert governance["patches_generated"] is False


def test_governance_patches_applied_false():
    governance = mod.build_review_governance([])
    assert governance["patches_applied"] is False


def test_governance_writes_allowed_false():
    governance = mod.build_review_governance([])
    assert governance["writes_allowed"] is False


def test_governance_memory_faiss_real_promotion_false():
    governance = mod.build_review_governance([])
    assert governance["memory_write_allowed"] is False
    assert governance["faiss_write_allowed"] is False
    assert governance["real_write_allowed"] is False
    assert governance["promotion_allowed"] is False


def test_governance_next_safe_front_correct():
    governance = mod.build_review_governance([])
    assert governance["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-GENERATION-DRY-RUN-01"


def test_governance_preserves_dirty_and_separate_commits():
    governance = mod.build_review_governance([])
    assert governance["must_preserve_dirty_preexisting_files"] is True
    assert governance["must_keep_code_and_ledger_commits_separate"] is True


def test_summary_counts_decisions():
    reviews = [mod.review_patch_plan_item(BASE_PLAN), mod.review_patch_plan_item(plan(required_tests=[]))]
    queue = mod.build_patch_candidate_queue(reviews)
    summary = mod.summarize_patch_plan_review(reviews, queue)
    assert summary["reviews_count"] == 2
    assert summary["approved_candidates"] == 1
    assert summary["rejected"] == 1


def test_summary_execution_and_generation_false():
    summary = mod.summarize_patch_plan_review([mod.review_patch_plan_item(BASE_PLAN)], [])
    assert summary["execution_allowed_now"] is False
    assert summary["patch_generation_allowed_now"] is False
    assert summary["patches_generated"] is False
    assert summary["patches_applied"] is False


def test_run_writes_reviews_json(tmp_path, monkeypatch):
    out, result = run_demo(tmp_path, monkeypatch)
    assert result["ok"] is True
    assert (out / "first_five_patch_plan_reviews.json").exists()


def test_run_writes_reviews_jsonl(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_plan_reviews.jsonl").exists()


def test_run_writes_candidate_queue_json(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_candidate_queue.json").exists()


def test_run_writes_review_governance_json(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_plan_review_governance.json").exists()


def test_run_writes_review_summary_json(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_plan_review_summary.json").exists()


def test_run_writes_review_report_md(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_plan_review_report.md").exists()


def test_report_is_spanish_readable(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    report = (out / "first_five_patch_plan_review_report.md").read_text(encoding="utf-8")
    assert "Revision de planes" in report
    assert "Decision" in report
    assert "aprobacion humana" in report.lower()


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


def test_run_patches_generated_false(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["patches_generated"] is False


def test_run_patches_applied_false(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["patches_applied"] is False


def test_reviewed_plans_count_at_least_one(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["reviews_count"] >= 1


def test_next_safe_front_is_patch_generation_dry_run(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-GENERATION-DRY-RUN-01"


def test_no_target_file_is_directly_modified(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    allowed = {
        "run_patch_plan",
        "first_five_patch_plan_reviews.json",
        "first_five_patch_plan_reviews.jsonl",
        "first_five_patch_candidate_queue.json",
        "first_five_patch_plan_review_governance.json",
        "first_five_patch_plan_review_summary.json",
        "first_five_patch_plan_review_report.md",
    }
    assert {item.name for item in out.iterdir()} <= allowed


def test_candidate_queue_count_lte_reviews_count(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["approved_candidates"] <= result["reviews_count"]


def test_outputs_do_not_contain_applicable_diff(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    text = "\n".join(path.read_text(encoding="utf-8") for path in out.glob("first_five_patch*"))
    assert "diff --git" not in text
    assert "+++ b/" not in text


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


def test_load_patch_plan_artifacts_reads_expected_files(tmp_path):
    (tmp_path / "first_five_patch_plan_items.json").write_text(json.dumps(PLAN_ITEMS), encoding="utf-8")
    (tmp_path / "first_five_patch_plan_summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    artifacts = mod.load_patch_plan_artifacts(str(tmp_path))
    assert len(artifacts["plan_items"]) == 2
    assert artifacts["summary"]["ok"] is True


def test_load_patch_plan_artifacts_handles_missing_files(tmp_path):
    artifacts = mod.load_patch_plan_artifacts(str(tmp_path))
    assert artifacts["plan_items"] == []
    assert artifacts["summary"] == {}


def test_review_ids_are_stable_for_same_input():
    first = mod.review_patch_plan_item(BASE_PLAN)["review_id"]
    second = mod.review_patch_plan_item(BASE_PLAN)["review_id"]
    assert first == second


def test_review_score_is_weighted_between_zero_and_one():
    score = mod.review_patch_plan_item(BASE_PLAN)["review_score"]
    assert 0.0 <= score <= 1.0


def test_request_more_evidence_decision_path():
    weak = plan(rollback_plan={}, acceptance_criteria=[], risk_assessment={"risk_level": "medium"})
    review = mod.review_patch_plan_item(weak)
    assert review["decision"] in {"request_more_evidence", "reject_not_actionable"}

