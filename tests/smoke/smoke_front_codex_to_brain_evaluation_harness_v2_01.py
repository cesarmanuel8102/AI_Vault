import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))

from brain_v9.evaluation.codex_brain_eval_harness import classify_row, load_suite, score_results


def test_01_default_suite_loads():
    suite = load_suite(ROOT / "tmp_agent" / "brain_v9" / "evaluation" / "default_codex_brain_eval_suite.json")
    assert len(suite) >= 8
    assert all("prompt_id" in item and "prompt" in item for item in suite)


def test_02_timeout_fallback_is_not_useful_success():
    row = classify_row({"content": "El modelo tardó demasiado en responder.", "brain": {}, "error": None, "latency_ms": 30000})
    assert row["fallback_used"] is True
    assert row["useful_response"] is False
    assert row["fallback_reason"] == "timeout_or_deterministic_fallback"


def test_03_score_results_counts_metadata_and_no_cot():
    summary = score_results([
        {"content": "Respuesta útil", "brain": {"intent":"QUERY","route":"chat","governance_applied":True,"no_cot_leak":True,"canonical_path":"C:/AI_VAULT_CANONICAL"}, "error": None},
        {"content": "fallback deterministico por LLM lento", "brain": {}, "error": None},
    ])
    assert summary["prompts_attempted"] == 2
    assert summary["successful_responses"] == 1
    assert summary["timeout_fallback_count"] == 1
    assert summary["raw_cot_count"] == 0


def test_04_domain_fixture_shape_supported():
    suite = load_suite(ROOT / "tests" / "fixtures" / "cei_fdot_eval_pack_v1.json", max_prompts=2)
    assert len(suite) == 2
    assert suite[0]["prompt_id"].startswith("cei_fdot")
