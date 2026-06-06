from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain.external_sources import self_improvement_first_five_patch_recommendation_dry_run as mod


SCORECARD = [
    {
        "front_id": "MULTI_AGENT_SYSTEMS_ORCHESTRATION",
        "benchmark_id": "bench_multi",
        "average_benchmark_score": 0.728,
        "passed": False,
        "pass_rate": 0.40,
        "weakness": "orchestration trace gap",
        "recommended_action": "add trace fixture",
        "evidence": "partially_validated",
    },
    {
        "front_id": "EVALUATION_BENCHMARKS_QUALITY_GATES",
        "benchmark_id": "bench_eval",
        "average_benchmark_score": 0.90,
        "passed": True,
        "pass_rate": 1.0,
        "weakness": "quality gate acceptable",
        "recommended_action": "monitor",
    },
    {
        "front_id": "MEMORY_RAG_KNOWLEDGE_STRUCTURE",
        "benchmark_id": "bench_memory",
        "average_benchmark_score": 0.732,
        "passed": False,
        "pass_rate": 0.60,
        "weakness": "retrieval provenance gap",
        "recommended_action": "add readonly fixture corpus",
    },
    {
        "front_id": "SECURITY_SANDBOXING_SUPPLY_CHAIN",
        "benchmark_id": "bench_security",
        "average_benchmark_score": 0.844,
        "passed": False,
        "pass_rate": 0.70,
        "weakness": "supply chain scoring synthetic",
        "recommended_action": "add token leak fixture",
    },
    {
        "front_id": "AUTO_CODING_AGENTS_PATCH_GENERATION",
        "benchmark_id": "bench_auto",
        "average_benchmark_score": 0.780,
        "passed": False,
        "pass_rate": 0.60,
        "weakness": "patch hygiene needs rollback fixture",
        "recommended_action": "add patch hygiene harness",
    },
]


def fake_harness(output_dir: str) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "first_five_benchmark_scorecard.json").write_text(json.dumps(SCORECARD, indent=2), encoding="utf-8")
    (out / "first_five_benchmark_harness_summary.json").write_text(
        json.dumps({"ok": True, "benchmark_runs": 5, "scorecard_entries": 5}, indent=2), encoding="utf-8"
    )
    (out / "first_five_benchmark_harness_results.json").write_text(json.dumps([], indent=2), encoding="utf-8")
    return {"ok": True, "output_dir": str(out), "benchmark_runs": 5, "patches_applied": False}


def run_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "run_first_five_benchmark_harness_dry_run", fake_harness)
    out = tmp_path / "patch_recommendation_run"
    result = mod.run_first_five_patch_recommendation_dry_run(str(out))
    return out, result


def test_module_imports():
    assert mod is not None


def test_classify_weakness_exists():
    assert callable(mod.classify_weakness)


def test_build_patch_recommendation_exists():
    assert callable(mod.build_patch_recommendation)


def test_run_first_five_patch_recommendation_dry_run_exists():
    assert callable(mod.run_first_five_patch_recommendation_dry_run)


def test_now_utc_exists():
    assert callable(mod.now_utc)


def test_load_benchmark_harness_artifacts_exists():
    assert callable(mod.load_benchmark_harness_artifacts)


def test_build_all_patch_recommendations_exists():
    assert callable(mod.build_all_patch_recommendations)


def test_build_patch_execution_roadmap_exists():
    assert callable(mod.build_patch_execution_roadmap)


def test_summarize_patch_recommendations_exists():
    assert callable(mod.summarize_patch_recommendations)


def test_classify_weakness_has_required_fields():
    weakness = mod.classify_weakness(SCORECARD[0])
    assert weakness["category"]
    assert weakness["severity"] == "medium"
    assert weakness["safe_to_recommend_patch"] is True


def test_classify_high_if_score_below_060():
    entry = dict(SCORECARD[0], average_benchmark_score=0.59)
    assert mod.classify_weakness(entry)["severity"] == "high"


def test_classify_medium_if_score_between_060_and_079():
    entry = dict(SCORECARD[0], average_benchmark_score=0.70)
    assert mod.classify_weakness(entry)["severity"] == "medium"


def test_classify_low_for_passed_high_score():
    assert mod.classify_weakness(SCORECARD[1])["severity"] == "low"


def test_classify_requires_core_fields_for_safe_recommendation():
    weakness = mod.classify_weakness({"front_id": "X", "benchmark_id": "Y"})
    assert weakness["safe_to_recommend_patch"] is False


def test_recommendation_blocks_patch_now():
    weakness = mod.classify_weakness(SCORECARD[0])
    rec = mod.build_patch_recommendation(SCORECARD[0], weakness)
    assert rec["patch_allowed_now"] is False
    assert rec["auto_apply_allowed"] is False


def test_recommendation_requires_human_approval_and_rollback():
    weakness = mod.classify_weakness(SCORECARD[0])
    rec = mod.build_patch_recommendation(SCORECARD[0], weakness)
    assert rec["rollback_plan_required"] is True
    assert rec["operator_approval_required"] is True


def test_recommendation_contains_target_files():
    rec = mod.build_patch_recommendation(SCORECARD[0], mod.classify_weakness(SCORECARD[0]))
    assert rec["target_files_suggested"]


def test_recommendation_contains_forbidden_files():
    rec = mod.build_patch_recommendation(SCORECARD[2], mod.classify_weakness(SCORECARD[2]))
    assert "memory/semantic/*" in rec["files_forbidden_to_modify"]
    assert "tmp_agent/strategies/*" in rec["files_forbidden_to_modify"]
    assert "B8/*" in rec["files_forbidden_to_modify"]


def test_recommendation_contains_required_tests():
    rec = mod.build_patch_recommendation(SCORECARD[4], mod.classify_weakness(SCORECARD[4]))
    assert rec["required_tests"]


def test_recommendation_disables_memory_faiss_real_and_promotion():
    rec = mod.build_patch_recommendation(SCORECARD[2], mod.classify_weakness(SCORECARD[2]))
    assert rec["memory_write_allowed"] is False
    assert rec["faiss_write_allowed"] is False
    assert rec["real_write_allowed"] is False
    assert rec["promotion_allowed"] is False


def test_recommendation_raises_high_risk_for_high_severity():
    entry = dict(SCORECARD[0], average_benchmark_score=0.40)
    rec = mod.build_patch_recommendation(entry, mod.classify_weakness(entry))
    assert rec["severity"] == "high"
    assert rec["risk_level"] == "high"


def test_build_all_generates_expected_recommendations():
    recs = mod.build_all_patch_recommendations(SCORECARD)
    assert len(recs) == 4


def test_build_all_skips_passed_high_score_front():
    recs = mod.build_all_patch_recommendations(SCORECARD)
    assert "EVALUATION_BENCHMARKS_QUALITY_GATES" not in {rec["front_id"] for rec in recs}


def test_build_all_has_medium_priority_recommendation():
    recs = mod.build_all_patch_recommendations(SCORECARD)
    assert any(rec["severity"] == "medium" for rec in recs)


def test_roadmap_status_is_recommendations_only():
    roadmap = mod.build_patch_execution_roadmap(mod.build_all_patch_recommendations(SCORECARD))
    assert roadmap["status"] == "recommendations_only_not_executed"


def test_roadmap_execution_disallowed():
    roadmap = mod.build_patch_execution_roadmap(mod.build_all_patch_recommendations(SCORECARD))
    assert roadmap["execution_allowed_now"] is False
    assert roadmap["auto_apply_allowed"] is False


def test_roadmap_never_generates_or_applies_patches():
    roadmap = mod.build_patch_execution_roadmap(mod.build_all_patch_recommendations(SCORECARD))
    assert roadmap["patches_generated"] is False
    assert roadmap["patches_applied"] is False


def test_roadmap_next_safe_front():
    roadmap = mod.build_patch_execution_roadmap(mod.build_all_patch_recommendations(SCORECARD))
    assert roadmap["next_safe_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-PLAN-DRY-RUN-01"


def test_summary_disables_all_writes():
    summary = mod.summarize_patch_recommendations(mod.build_all_patch_recommendations(SCORECARD))
    assert summary["memory_write_performed"] is False
    assert summary["faiss_write_performed"] is False
    assert summary["real_write_performed"] is False
    assert summary["promotion_performed"] is False


def test_run_writes_recommendations_json(tmp_path, monkeypatch):
    out, result = run_demo(tmp_path, monkeypatch)
    assert result["ok"] is True
    assert (out / "first_five_patch_recommendations.json").exists()


def test_run_writes_recommendations_jsonl(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_recommendations.jsonl").exists()


def test_run_writes_summary_json(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_recommendation_summary.json").exists()


def test_run_writes_roadmap_json(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert (out / "first_five_patch_recommendation_roadmap.json").exists()


def test_run_writes_spanish_report(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    report = (out / "first_five_patch_recommendation_report.md").read_text(encoding="utf-8")
    assert "Recomendaciones" in report
    assert "No se aplicaron patches" in report


def test_run_outputs_at_least_one_recommendation(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    recs = json.loads((out / "first_five_patch_recommendations.json").read_text(encoding="utf-8"))
    assert len(recs) >= 1


def test_run_outputs_high_or_medium_priority_recommendation(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    recs = json.loads((out / "first_five_patch_recommendations.json").read_text(encoding="utf-8"))
    assert any(rec["severity"] in {"high", "medium"} for rec in recs)


def test_run_result_never_generates_or_applies_patches(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["patches_generated"] is False
    assert result["patches_applied"] is False


def test_run_result_no_memory_faiss_real_promotion(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["memory_write_performed"] is False
    assert result["faiss_write_performed"] is False
    assert result["real_write_performed"] is False
    assert result["promotion_performed"] is False


def test_run_result_no_runtime_trading_b8(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["runtime_chat_integration"] is False
    assert result["trading_used"] is False
    assert result["b8_touched"] is False


def test_run_result_no_token_leak(tmp_path, monkeypatch):
    _, result = run_demo(tmp_path, monkeypatch)
    assert result["token_leak_detected"] is False


def test_output_files_have_no_token_markers(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    assert mod._output_has_token_marker(out) is False


def test_recommendations_do_not_contain_raw_diff_fields(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    raw = (out / "first_five_patch_recommendations.json").read_text(encoding="utf-8")
    assert "diff --git" not in raw
    assert "patch_content" not in raw


def test_recommendations_do_not_target_memory_semantic(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    recs = json.loads((out / "first_five_patch_recommendations.json").read_text(encoding="utf-8"))
    for rec in recs:
        assert not any(target.startswith("memory/semantic") for target in rec["target_files_suggested"])


def test_recommendations_do_not_target_trading_or_b8(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    recs = json.loads((out / "first_five_patch_recommendations.json").read_text(encoding="utf-8"))
    for rec in recs:
        targets = "\n".join(rec["target_files_suggested"])
        assert "trading" not in targets.lower()
        assert "b8" not in targets.lower()


def test_required_tests_are_recommendations_not_executed_patches(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    recs = json.loads((out / "first_five_patch_recommendations.json").read_text(encoding="utf-8"))
    assert all(rec["required_tests"] for rec in recs)
    assert all(rec["patch_allowed_now"] is False for rec in recs)


def test_no_target_file_directly_modified_by_run(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    allowed_names = {
        "run_benchmark_harness",
        "first_five_patch_recommendations.json",
        "first_five_patch_recommendations.jsonl",
        "first_five_patch_recommendation_summary.json",
        "first_five_patch_recommendation_roadmap.json",
        "first_five_patch_recommendation_report.md",
    }
    assert {item.name for item in out.iterdir()} <= allowed_names


def test_module_source_has_no_runtime_imports():
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "tmp_agent.brain_v9.main" not in source
    assert "tmp_agent.brain_v9.core.session" not in source


def test_module_source_has_no_semantic_writer_imports():
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "semantic_memory_faiss" not in source
    assert "semantic_memory_adapter_real" not in source


def test_module_source_has_no_network_or_subprocess():
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "requests" not in source
    assert "httpx" not in source
    assert "subprocess" not in source


def test_load_benchmark_harness_artifacts_reads_expected_files(tmp_path):
    (tmp_path / "first_five_benchmark_scorecard.json").write_text(json.dumps(SCORECARD), encoding="utf-8")
    (tmp_path / "first_five_benchmark_harness_summary.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    artifacts = mod.load_benchmark_harness_artifacts(str(tmp_path))
    assert len(artifacts["scorecard"]) == 5
    assert artifacts["summary"]["ok"] is True


def test_load_benchmark_harness_artifacts_handles_missing_files(tmp_path):
    artifacts = mod.load_benchmark_harness_artifacts(str(tmp_path))
    assert artifacts["scorecard"] == []
    assert artifacts["summary"] == {}


def test_summary_counts_priorities():
    recs = mod.build_all_patch_recommendations(SCORECARD)
    summary = mod.summarize_patch_recommendations(recs)
    assert summary["recommendations_count"] == 4
    assert summary["medium_priority_count"] == 3
    assert summary["low_priority_count"] == 1


def test_roadmap_orders_high_before_medium():
    high_entry = dict(SCORECARD[0], average_benchmark_score=0.40)
    recs = mod.build_all_patch_recommendations([SCORECARD[4], high_entry])
    roadmap = mod.build_patch_execution_roadmap(recs)
    first = next(rec for rec in recs if rec["recommendation_id"] == roadmap["recommended_order"][0])
    assert first["severity"] == "high"


def test_recommendation_ids_are_stable_for_same_input():
    weakness = mod.classify_weakness(SCORECARD[0])
    one = mod.build_patch_recommendation(SCORECARD[0], weakness)["recommendation_id"]
    two = mod.build_patch_recommendation(SCORECARD[0], weakness)["recommendation_id"]
    assert one == two


def test_report_mentions_human_approval(tmp_path, monkeypatch):
    out, _ = run_demo(tmp_path, monkeypatch)
    report = (out / "first_five_patch_recommendation_report.md").read_text(encoding="utf-8")
    assert "aprobacion humana" in report.lower()

