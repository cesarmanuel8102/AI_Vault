import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
if str(TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_autonomy_teaching_loop_and_runner_exist() -> None:
    assert (ROOT / "tmp_agent/brain_v9/autonomy/teacher_student_loop.py").exists()
    assert (ROOT / "tmp_agent/brain_v9/autonomy/autonomy_cycle_runner.py").exists()
    assert (ROOT / "tmp_agent/brain_v9/autonomy/autonomy_models.py").exists()


def test_operational_memory_is_non_semantic() -> None:
    source = _read("tmp_agent/brain_v9/learning/operational_memory.py")
    assert "OPERATIONAL_LESSONS_PATH" in source
    assert "memory/semantic/" in source
    assert "FAISS" not in source
    assert (ROOT / "tmp_agent/brain_v9/learning/operational_lessons.jsonl").exists()


def test_promotion_candidates_are_separate_from_semantic_memory() -> None:
    source = _read("tmp_agent/brain_v9/learning/promotion_gate_registry.py")
    assert "PROMOTION_CANDIDATES_PATH" in source
    assert "semantic_memory_allowed: bool = False" in source
    assert "faiss_write_allowed: bool = False" in source


def test_competency_matrix_and_excellence_scoring_exist() -> None:
    assert (ROOT / "tmp_agent/brain_v9/learning/competency_matrix.py").exists()
    assert (ROOT / "tmp_agent/brain_v9/excellence/competency_matrix.py").exists()
    assert (ROOT / "tmp_agent/brain_v9/excellence/scoring.py").exists()
    from tmp_agent.brain_v9.excellence.scoring import compute_excellence_score

    score = compute_excellence_score({
        "provider_reliability": 1,
        "no_cot_safety": 1,
        "memory_discipline": 1,
        "coding_reliability": 1,
        "test_discipline": 1,
        "cei_fdot_usefulness": 1,
        "financial_safety": 1,
        "autonomy_planning": 1,
        "token_efficiency": 1,
        "operator_clarity": 1,
    })
    assert score["overall"] == 1.0


def test_token_budget_policy_exists_and_is_compact() -> None:
    from tmp_agent.brain_v9.autonomy.token_budget import DEFAULT_TOKEN_BUDGET

    assert DEFAULT_TOKEN_BUDGET.compact_mode is True
    assert DEFAULT_TOKEN_BUDGET.raw_log_dump_default is False
    assert DEFAULT_TOKEN_BUDGET.evidence_files_required is True


def test_operations_status_cli_exists() -> None:
    cli = ROOT / "tools/brain_governed_ops_status.ps1"
    assert cli.exists()
    text = cli.read_text(encoding="utf-8")
    assert "kimi_k2_6_present" in text
    assert "secrets_printed = $false" in text


def test_kimi_primary_and_provider_probe_contract_remain() -> None:
    llm = _read("tmp_agent/brain_v9/core/llm.py")
    adapter = _read("tmp_agent/brain_v9/api/openai_compat.py")
    session = _read("tmp_agent/brain_v9/core/session.py")
    assert '"primary_provider": "kimi_k2_6_cloud"' in llm
    assert "provider_probe" in adapter
    assert "async def provider_probe" in session
    for token in ("tools_blocked", "memory_writes_blocked", "faiss_writes_blocked"):
        assert token in session


def test_no_cot_sanitizer_remains_active() -> None:
    from tmp_agent.brain_v9.core.session import BrainSession

    sanitized, metadata = BrainSession._sanitize_llm_chat_response_with_metadata(
        "Thinking...\nprivate\n...done thinking.\nOK"
    )
    assert sanitized == "OK"
    assert metadata["no_cot_leak"] is True


def test_domain_excellence_packs_exist() -> None:
    base = ROOT / "tmp_agent/brain_v9/evaluation/excellence_packs"
    required = [
        "cei_fdot_excellence.json",
        "financial_research_safety_excellence.json",
        "brain_development_excellence.json",
        "chat_ux_excellence.json",
    ]
    for name in required:
        payload = json.loads((base / name).read_text(encoding="utf-8"))
        assert payload["checks"]
        assert payload["blocked"]


def test_roadmap_and_ledger_valid() -> None:
    json.loads(_read("ROADMAP_STATUS.json"))
    assert (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").exists()


def test_no_protected_or_env_paths_staged() -> None:
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True)
    protected = ("memory/semantic/", "trading/", "B8/", "tmp_agent/strategies/")
    assert not any(line.startswith(protected) for line in staged.splitlines())
    assert ".env" not in staged.splitlines()
