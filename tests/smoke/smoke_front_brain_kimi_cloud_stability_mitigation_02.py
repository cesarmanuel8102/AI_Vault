import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def test_state_lock_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/state_lock.json").exists()


def test_prior_failure_summary_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/prior_failure_summary.json").exists()


def test_code_path_audit_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/code_path_audit.json").exists()


def test_probe_matrix_or_post_patch_exists():
    assert (
        (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/probe_matrix.json").exists()
        or (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/post_patch_validation.json").exists()
    )


def test_root_cause_classification_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/root_cause_classification.json").exists()


def test_patch_decision_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/patch_decision.json").exists()


def test_final_report_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/final_report.json").exists()


def test_final_safety_verify_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/final_safety_verify.json").exists()


def test_post_patch_if_applied():
    fr = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/final_report.json").read_text())
    if fr.get("patch_applied"):
        pp = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/post_patch_validation.json").read_text())
        assert pp["kimi_selected_count"] >= 5
        assert pp["kimi_selection_rate"] >= 0.83


def test_semantic_unchanged():
    safety = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/final_safety_verify.json").read_text())
    assert safety["semantic_lines_before"] == 1715
    assert safety["semantic_lines_after"] == 1715
    assert safety["canonical_semantic_mutated"] is False


def test_faiss_unchanged():
    safety = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/final_safety_verify.json").read_text())
    assert safety["faiss_ids_before"] == 1616
    assert safety["faiss_ids_after"] == 1616
    assert safety["faiss_mutated"] is False


def test_no_trading_b8_strategies():
    safety = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/final_safety_verify.json").read_text())
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False


def test_no_secrets_cot():
    safety = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/final_safety_verify.json").read_text())
    assert safety["secrets_exposed"] is False
    assert safety["raw_cot_exposed"] is False


def test_dry_run_zero():
    safety = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/final_safety_verify.json").read_text())
    assert safety["dry_run_count"] == 0


def test_roadmap_valid():
    data = json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    assert "completed_fronts" in data


def test_ledger_exists():
    assert (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").exists()


def test_cesar_review_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_02/cesar_review_report.md").exists()
