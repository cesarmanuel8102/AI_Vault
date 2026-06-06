from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain.external_sources import self_improvement_first_five_patch_plan_dry_run as mod


RECOMMENDATIONS = [
    {
        "recommendation_id": "rec_security",
        "front_id": "SECURITY_SANDBOXING_SUPPLY_CHAIN",
        "benchmark_id": "bench_security",
        "category": "security_supply_chain_gap",
        "severity": "medium",
        "title": "Security policy recommendation",
        "recommended_patch_type": "policy_patch",
        "recommended_scope": "medium",
        "target_files_suggested": ["brain/external_sources/*", "tests/smoke/*"],
        "files_forbidden_to_modify": ["memory/semantic/*", "tmp_agent/strategies/*", "trading/*", "B8/*"],
        "implementation_steps": ["Add token leak fixture", "Add forbidden path fixture"],
        "required_tests": ["token leak scan", "forbidden path scan"],
        "acceptance_criteria": ["secrets redacted", "protected paths blocked"],
        "risk_level": "high",
        "risk_notes": "Security regression would affect secrets or unsafe execution.",
    },
    {
        "recommendation_id": "rec_evaluation",
        "front_id": "EVALUATION_BENCHMARKS_QUALITY_GATES",
        "benchmark_id": "bench_eval",
        "category": "evaluation_gate_gap",
        "severity": "medium",
        "title": "Evaluation gate recommendation",
        "recommended_patch_type": "test_patch",
        "recommended_scope": "small",
        "target_files_suggested": ["tests/smoke/*"],
        "files_forbidden_to_modify": ["memory/semantic/*", "tmp_agent/strategies/*", "trading/*", "B8/*"],
        "implementation_steps": ["Add before after fixture"],
        "required_tests": ["before after gate"],
        "acceptance_criteria": ["bad patch blocked"],
        "risk_level": "low",
        "risk_notes": "Test-only recommendation.",
    },
    {
        "recommendation_id": "rec_auto",
        "front_id": "AUTO_CODING_AGENTS_PATCH_GENERATION",
        "benchmark_id": "bench_auto",
        "category": "patch_hygiene_gap",
        "severity": "medium",
        "title": "Patch hygiene recommendation",
        "recommended_patch_type": "policy_patch",
        "recommended_scope": "medium",
        "target_files_suggested": ["brain/external_sources/*", "tests/smoke/*"],
        "files_forbidden_to_modify": ["memory/semantic/*", "tmp_agent/strategies/*", "trading/*", "B8/*"],
        "implementation_steps": ["Add rollback fixture"],
        "required_tests": ["rollback plan fixture"],
        "acceptance_criteria": ["rollback present"],
        "risk_level": "medium",
        "risk_notes": "Patch hygiene can mix dirty changes.",
    },
    {
        "recommendation_id": "rec_multi",
        "front_id": "MULTI_AGENT_SYSTEMS_ORCHESTRATION",
        "benchmark_id": "bench_multi",
        "category": "orchestration_trace_gap",
        "severity": "medium",
        "title": "Orchestration trace recommendation",
        "recommended_patch_type": "harness_patch",
        "recommended_scope": "medium",
        "target_files_suggested": ["brain/external_sources/*", "tests/smoke/*"],
        "files_forbidden_to_modify": ["memory/semantic/*", "tmp_agent/strategies/*", "trading/*", "B8/*"],
        "implementation_steps": ["Add redacted trace fixture"],
        "required_tests": ["no chain of thought scan"],
        "acceptance_criteria": ["trace summary exists"],
        "risk_level": "medium",
        "risk_notes": "Trace work can leak reasoning if not redacted.",
    },
    {
        "recommendation_id": "rec_memory",
        "front_id": "MEMORY_RAG_KNOWLEDGE_STRUCTURE",
        "benchmark_id": "bench_memory",
        "category": "retrieval_provenance_gap",
        "severity": "medium",
        "title": "Retrieval provenance recommendation",
        "recommended_patch_type": "harness_patch",
        "recommended_scope": "medium",
        "target_files_suggested": ["brain/external_sources/*", "tests/smoke/*"],
        "files_forbidden_to_modify": ["memory/semantic/*", "tmp_agent/strategies/*", "trading/*", "B8/*"],
        "implementation_steps": ["Add read-only fixture corpus"],
        "required_tests": ["missing provenance rejection"],
        "acceptance_criteria": ["source evidence required"],
        "risk_level": "medium",
        "risk_notes": "Retrieval work must not become memory write work.",
    },
]


def fake_recommendation_run(output_dir: str) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "first_five_patch_recommendations.json").write_text(json.dumps(RECOMMENDATIONS, indent=2), encoding="utf-8")
    (out / "first_five_patch_recommendations.jsonl").write_text(
        "\n".join(json.dumps(item, sort_keys=True) for item in RECOMMENDATIONS) + "\n",
        encoding="utf-8",
    )
    (out / "first_five_patch_recommendation_summary.json").write_text(
        json.dumps({"ok": True, "recommendations_count": len(RECOMMENDATIONS)}, indent=2), encoding="utf-8"
    )
    (out / "first_five_patch_recommendation_roadmap.json").write_text(
        json.dumps({"status": "recommendations_only_not_executed"}, indent=2), encoding="utf-8"
    )
    return {"ok": True, "recommendations_count": len(RECOMMENDATIONS), "patches_applied": False}


def run_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "run_first_five_patch_recommendation_dry_run", fake_recommendation_run)
    out = tmp_path / "patch_plan_run"
    result = mod.run_first_five_patch_plan_dry_run(str(out))
    return out, result


def sample_plan_item():
    return mod.build_patch_plan_item(RECOMMENDATIONS[0])


def test_import_module():
    assert mod is not None


def test_build_patch_plan_item_exists():
    assert callable(mod.build_patch_plan_item)


def test_build_all_patch_plan_items_exists():
    assert callable(mod.build_all_patch_plan_items)


def test_build_patch_plan_execution_order_exists():
    assert callable(mod.build_patch_plan_execution_order)


def test_build_patch_plan_governance_exists():
    assert callable(mod.build_patch_plan_governance)


def test_run_first_five_patch_plan_dry_run_exists():
    assert callable(mod.run_first_five_patch_plan_dry_run)


def test_now_utc_exists():
    assert callable(mod.now_utc)


def test_load_patch_recommendation_artifacts_exists():
    assert callable(mod.load_patch_recommendation_artifacts)


def test_summarize_patch_plan_exists():
    assert callable(mod.summarize_patch_plan)


def test_plan_item_has_planned_status():
    assert sample_plan_item()["plan_status"] == "planned_not_executed"


def test_plan_item_execution_allowed_now_false():
    assert sample_plan_item()["execution_allowed_now"] is False


def test_plan_item_operator_approval_required_true():
    assert sample_plan_item()["operator_approval_required"] is True


def test_plan_item_auto_apply_allowed_false():
    assert sample_plan_item()["auto_apply_allowed"] is False


def test_plan_item_patch_generated_false():
    assert sample_plan_item()["patch_generated"] is False


def test_plan_item_patch_applied_false():
    assert sample_plan_item()["patch_applied"] is False


def test_plan_item_memory_write_allowed_false():
    assert sample_plan_item()["memory_write_allowed"] is False


def test_plan_item_faiss_write_allowed_false():
    assert sample_plan_item()["faiss_write_allowed"] is False


def test_plan_item_real_write_allowed_false():
    assert sample_plan_item()["real_write_allowed"] is False


def test_plan_item_promotion_allowed_false():
    assert sample_plan_item()["promotion_allowed"] is False


def test_plan_item_has_rollback_plan_required():
    assert sample_plan_item()["rollback_plan"]["required"] is True


def test_plan_item_rollback_preserves_dirty_state():
    assert sample_plan_item()["rollback_plan"]["must_preserve_existing_dirty_state"] is True


def test_plan_item_has_files_forbidden_to_modify():
    item = sample_plan_item()
    assert "memory/semantic/*" in item["files_forbidden_to_modify"]
    assert "tmp_agent/strategies/*" in item["files_forbidden_to_modify"]


def test_plan_item_has_required_tests():
    assert sample_plan_item()["required_tests"]


def test_plan_item_has_acceptance_criteria():
    assert sample_plan_item()["acceptance_criteria"]


def test_plan_item_has_implementation_steps_with_allowed_now_false():
    steps = sample_plan_item()["implementation_steps"]
    assert steps
    assert all(step["allowed_now"] is False for step in steps)


def test_plan_item_expected_change_type_policy_only():
    assert sample_plan_item()["implementation_steps"][0]["expected_change_type"] == "policy_only"


def test_unknown_patch_type_normalizes_to_harness():
    rec = dict(RECOMMENDATIONS[0], recommended_patch_type="unknown")
    assert mod.build_patch_plan_item(rec)["patch_type"] == "harness_patch"


def test_execution_order_prioritizes_security_before_evaluation():
    items = mod.build_all_patch_plan_items([RECOMMENDATIONS[1], RECOMMENDATIONS[0]])
    ordered = mod.build_patch_plan_execution_order(items)
    assert ordered[0]["category"] == "security_supply_chain_gap"
    assert ordered[1]["category"] == "evaluation_gate_gap"


def test_execution_order_prioritizes_evaluation_before_patch_hygiene():
    items = mod.build_all_patch_plan_items([RECOMMENDATIONS[2], RECOMMENDATIONS[1]])
    ordered = mod.build_patch_plan_execution_order(items)
    assert ordered[0]["category"] == "evaluation_gate_gap"


def test_execution_order_assigns_sequential_priorities():
    ordered = mod.build_patch_plan_execution_order(mod.build_all_patch_plan_items(RECOMMENDATIONS))
    assert [item["execution_priority"] for item in ordered] == [1, 2, 3, 4, 5]


def test_execution_order_sorts_high_before_medium_same_category():
    high = dict(RECOMMENDATIONS[2], recommendation_id="rec_auto_high", severity="high")
    medium = dict(RECOMMENDATIONS[2], recommendation_id="rec_auto_medium", severity="medium")
    ordered = mod.build_patch_plan_execution_order(mod.build_all_patch_plan_items([medium, high]))
    assert ordered[0]["severity"] == "high"


def test_execution_order_sorts_small_before_medium_same_category():
    small = dict(RECOMMENDATIONS[2], recommendation_id="rec_auto_small", recommended_scope="small")
    medium = dict(RECOMMENDATIONS[2], recommendation_id="rec_auto_medium", recommended_scope="medium")
    ordered = mod.build_patch_plan_execution_order(mod.build_all_patch_plan_items([medium, small]))
    assert ordered[0]["recommended_scope"] == "small"


def test_governance_status_plan_only_not_executable():
    governance = mod.build_patch_plan_governance(mod.build_all_patch_plan_items(RECOMMENDATIONS))
    assert governance["status"] == "plan_only_not_executable"


def test_governance_execution_allowed_now_false():
    governance = mod.build_patch_plan_governance([])
    assert governance["execution_allowed_now"] is False


def test_governance_requires_operator_approval_true():
    governance = mod.build_patch_plan_governance([])
    assert governance["requires_operator_approval"] is True


def test_governance_auto_apply_allowed_false():
    governance = mod.build_patch_plan_governance([])
    assert governance["auto_apply_allowed"] is False


def test_governance_patches_generated_false():
    governance = mod.build_patch_plan_governance([])
    assert governance["patches_generated"] is False


def test_governance_patches_applied_false():
    governance = mod.build_patch_plan_governance([])
    assert governance["patches_applied"] is False


def test_governance_must_separate_code_and_ledger_commits_true():
    governance = mod.build_patch_plan_governance([])
    assert governance["must_separate_code_and_ledger_commits"] is True


def test_governance_must_preserve_dirty_preexisting_files_true():
    governance = mod.build_patch_plan_governance([])
    assert governance["must_preserve_dirty_preexisting_files"] is True


def test_governance_disables_all_writes():
    governance = mod.build_patch_plan_governance([])
    assert governance["writes_allowed"] is False
    assert governance["memory_write_allowed"] is False
    assert governance["faiss_write_allowed"] is False
    assert governance["real_write_allowed"] is False
    assert governance["promotion_allowed"] is False


def test_governance_next_safe_front_patch_plan_review():
    governance = mod.build_patch_plan_governance([])
    assert governance["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-PLAN-REVIEW-DRY-RUN-01"


def test_summary_counts_plan_items():
    summary = mod.summarize_patch_plan(mod.build_all_patch_plan_items(RECOMMENDATIONS))
    assert summary["plan_items"] == 5


def test_summary_disables_execution_and_patches():
    summary = mod.summarize_patch_plan(mod.build_all_patch_plan_items(RECOMMENDATIONS))
    assert summary["execution_allowed_now"] is False
    assert summary["patches_generated"] is False
    assert summary["patches_applied"] is False


def test_run_writes_plan_items_json(tmp_path, monkeypatch):
    out, result = run_demo(tmp_path, monkeypatch)
    assert result["ok"] is True
    assert (out / "first_five_patch_plan_items.json").exists()


def test_run_writes_plan_items_jsonl(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_plan_items.jsonl").exists()


def test_run_writes_execution_order_json(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_plan_execution_order.json").exists()


def test_run_writes_governance_json(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_plan_governance.json").exists()


def test_run_writes_summary_json(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_plan_summary.json").exists()


def test_run_writes_report_md(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_plan_report.md").exists()


def test_report_is_spanish_readable(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    report = (out / "first_five_patch_plan_report.md").read_text(encoding="utf-8")
    assert "Planes de patch" in report
    assert "Que NO se aplico" in report
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


def test_run_no_trading_or_b8(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["trading_used"] is False
    assert result["b8_touched"] is False


def test_run_patches_generated_false(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["patches_generated"] is False


def test_run_patches_applied_false(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["patches_applied"] is False


def test_run_generates_at_least_one_plan_item(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["plan_items"] >= 1


def test_run_next_safe_front_is_patch_plan_review(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-PLAN-REVIEW-DRY-RUN-01"


def test_no_target_file_is_directly_modified(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    allowed = {
        "run_patch_recommendation",
        "first_five_patch_plan_items.json",
        "first_five_patch_plan_items.jsonl",
        "first_five_patch_plan_execution_order.json",
        "first_five_patch_plan_governance.json",
        "first_five_patch_plan_summary.json",
        "first_five_patch_plan_report.md",
    }
    assert {item.name for item in out.iterdir()} <= allowed


def test_outputs_do_not_contain_applicable_diff(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    text = "\n".join(path.read_text(encoding="utf-8") for path in out.glob("first_five_patch_plan*"))
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


def test_load_patch_recommendation_artifacts_reads_expected_files(tmp_path):
    (tmp_path / "first_five_patch_recommendations.json").write_text(json.dumps(RECOMMENDATIONS), encoding="utf-8")
    (tmp_path / "first_five_patch_recommendation_summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    artifacts = mod.load_patch_recommendation_artifacts(str(tmp_path))
    assert len(artifacts["recommendations"]) == 5
    assert artifacts["summary"]["ok"] is True


def test_load_patch_recommendation_artifacts_handles_missing_files(tmp_path):
    artifacts = mod.load_patch_recommendation_artifacts(str(tmp_path))
    assert artifacts["recommendations"] == []
    assert artifacts["summary"] == {}


def test_patch_plan_ids_are_stable_for_same_input():
    first = mod.build_patch_plan_item(RECOMMENDATIONS[0])["patch_plan_id"]
    second = mod.build_patch_plan_item(RECOMMENDATIONS[0])["patch_plan_id"]
    assert first == second


def test_report_lists_forbidden_files(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    report = (out / "first_five_patch_plan_report.md").read_text(encoding="utf-8")
    assert "memory/semantic/*" in report
    assert "tmp_agent/strategies/*" in report
