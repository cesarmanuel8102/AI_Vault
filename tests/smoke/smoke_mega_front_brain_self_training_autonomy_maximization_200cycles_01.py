from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tmp_agent/mega_front_brain_self_training_autonomy_maximization_200cycles_01"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def test_mega_cycle_runner_checkpoint_schema_and_compactor_exist():
    for path in [
        "tmp_agent/brain_v9/autonomy/mega_cycle_runner.py",
        "tmp_agent/brain_v9/autonomy/mega_cycle_contracts.py",
        "tmp_agent/brain_v9/autonomy/mega_cycle_checkpoint.py",
        "tmp_agent/brain_v9/autonomy/mega_cycle_compactor.py",
    ]:
        assert (ROOT / path).exists()
    contracts = read("tmp_agent/brain_v9/autonomy/mega_cycle_contracts.py")
    assert "MegaCycleRecord" in contracts
    assert "risk_level" in contracts


def test_kimi_dialogue_calibration_exists_and_records_stability():
    assert (ROOT / "tmp_agent/brain_v9/autonomy/dialogue_prompt_profiles.py").exists()
    assert (ROOT / "tmp_agent/brain_v9/autonomy/provider_dialogue_calibrator.py").exists()
    data = read_json(EVIDENCE / "kimi_dialogue_calibration.json")
    assert data["total_count"] >= 8
    assert data["stable_count"] >= 1 or "UNSTABLE" in data["kimi_open_dialogue_stability"]
    assert "recommended_mode" in data


def test_domain_plan_score_progression_and_resume_materials_exist():
    assert (EVIDENCE / "domain_cycle_plan.json").exists()
    assert (EVIDENCE / "domain_cycle_plan.md").exists()
    assert (EVIDENCE / "excellence_score_progression.jsonl").exists()
    assert (EVIDENCE / "RESUME_STATE.json").exists()
    assert (EVIDENCE / "RESUME_PROMPT.md").exists()
    assert (EVIDENCE / "HANDOFF_FOR_NEXT_CODEX.md").exists()
    summary = read_json(EVIDENCE / "mega_cycle_summary.json")
    assert summary["cycles_completed"] >= 100
    assert summary["batches_completed"] >= 10


def test_operational_learning_is_separate_from_semantic_memory():
    for path in [
        "tmp_agent/brain_v9/learning/operational_lessons.jsonl",
        "tmp_agent/brain_v9/learning/mistakes.jsonl",
        "tmp_agent/brain_v9/learning/promotion_candidates.jsonl",
        "tmp_agent/brain_v9/learning/competency_matrix.json",
    ]:
        assert (ROOT / path).exists()
    promotions = read("tmp_agent/brain_v9/learning/promotion_candidates.jsonl")
    assert "semantic_memory_allowed" in promotions
    assert "faiss_write_allowed" in promotions
    assert "memory/semantic" not in promotions


def test_protected_paths_and_side_effects_are_blocked_by_source_contract():
    source = read("tmp_agent/brain_v9/autonomy/mega_cycle_runner.py")
    assert "PROTECTED_MARKERS" in source
    for token in ["memory/semantic", "trading/", "B8/", "tmp_agent/strategies", ".env"]:
        assert token in source
    assert "faiss.write" not in source.lower()
    assert "read_index" not in source


def test_no_cot_sanitizer_and_fallback_transparency_recorded():
    calibration = read_json(EVIDENCE / "kimi_dialogue_calibration.json")
    for result in calibration["results"]:
        assert "fallback_used" in result
        assert result["no_cot_leak"] is True
    cycles = [json.loads(line) for line in (EVIDENCE / "cycles.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert cycles
    assert all("risk_level" in cycle for cycle in cycles)
    assert all("fallback_used" in cycle for cycle in cycles)


def test_daily_dryrun_tool_exists_when_cycles_exceed_sixty():
    summary = read_json(EVIDENCE / "mega_cycle_summary.json")
    if summary["cycles_completed"] >= 60:
        assert (ROOT / "tmp_agent/brain_v9/operations/daily_autonomy_dryrun.py").exists()
        assert (ROOT / "tools/brain_daily_autonomous_dryrun.ps1").exists()
        assert (ROOT / "docs/BRAIN_DAILY_AUTONOMOUS_DRYRUN_RUNBOOK.md").exists()


def test_all_implemented_improvements_have_tests_or_reason():
    cycles = [json.loads(line) for line in (EVIDENCE / "cycles.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    implemented = [cycle for cycle in cycles if cycle.get("implemented")]
    assert implemented
    assert all(cycle.get("tests_run") or cycle.get("codex_critique") for cycle in implemented)


def test_roadmap_valid_ledger_exists_and_no_raw_cot_in_summaries():
    json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8-sig"))
    assert (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").exists()
    for name in ["kimi_dialogue_calibration.md", "domain_cycle_plan.md"]:
        text = (EVIDENCE / name).read_text(encoding="utf-8").lower()
        assert "chain-of-thought" not in text
        assert "<think" not in text


def test_no_protected_paths_staged_or_env_staged():
    import subprocess
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-status"], cwd=ROOT, text=True)
    forbidden = ["memory/semantic", "trading/", "B8/", "tmp_agent/strategies", ".env"]
    for token in forbidden:
        assert token not in staged
