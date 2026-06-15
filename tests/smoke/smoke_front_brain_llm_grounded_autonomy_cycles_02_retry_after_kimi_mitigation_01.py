import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def test_state_lock_exists():
    assert (ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/state_lock.json").exists()


def test_kimi_stability_closeout_exists():
    assert (ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/kimi_stability_closeout_verify.json").exists()


def test_live_runtime_verify_exists():
    assert (ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/live_runtime_verify.json").exists()


def test_kimi_route_preflight_exists():
    assert (ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/kimi_route_preflight.json").exists()


def test_final_report_exists():
    assert (ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/final_report.json").exists()


def test_final_safety_verify_exists():
    assert (ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/final_safety_verify.json").exists()


def test_semantic_unchanged():
    safety = json.loads((ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/final_safety_verify.json").read_text())
    assert safety["semantic_lines_before"] == 1715
    assert safety["semantic_lines_after"] == 1715
    assert safety["canonical_semantic_mutated"] is False


def test_faiss_unchanged():
    safety = json.loads((ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/final_safety_verify.json").read_text())
    assert safety["faiss_ids_before"] == 1616
    assert safety["faiss_ids_after"] == 1616
    assert safety["faiss_mutated"] is False


def test_no_trading_b8_strategies_touched():
    safety = json.loads((ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/final_safety_verify.json").read_text())
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False
    assert safety["strategies_touched"] is False


def test_no_secrets_cot():
    safety = json.loads((ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/final_safety_verify.json").read_text())
    assert safety["secrets_exposed"] is False
    assert safety["raw_cot_exposed"] is False


def test_no_canonical_promotions():
    safety = json.loads((ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/final_safety_verify.json").read_text())
    assert safety["canonical_promotions"] == 0


def test_dry_run_count_zero():
    safety = json.loads((ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/final_safety_verify.json").read_text())
    assert safety["dry_run_count"] == 0


def test_preflight_kimi_selected_once():
    pf = json.loads((ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/kimi_route_preflight.json").read_text())
    assert pf["kimi_selected_count"] == 1
    assert pf["verdict"] == "FAILED_KIMI_NOT_SELECTED_PREFLIGHT"


def test_roadmap_status_valid():
    data = json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    assert "completed_fronts" in data


def test_ledger_exists():
    assert (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").exists()


def test_cesar_review_exists():
    assert (ROOT / "tmp_agent/front_brain_llm_grounded_autonomy_cycles_02_retry_after_kimi_mitigation_01/cesar_review_report.md").exists()
