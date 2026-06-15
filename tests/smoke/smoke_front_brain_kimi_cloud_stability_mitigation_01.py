import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def test_preflight_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/preflight.json").exists()


def test_prior_failure_summary_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/prior_failure_summary.json").exists()


def test_code_path_audit_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/code_path_audit.json").exists()


def test_kimi_probe_matrix_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/kimi_probe_matrix.json").exists()


def test_root_cause_classification_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/root_cause_classification.json").exists()


def test_patch_decision_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/patch_decision.json").exists()


def test_final_report_exists():
    assert (ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/final_report.md").exists()


def test_semantic_faiss_unchanged():
    safety = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/final_safety_verify.json").read_text())
    assert safety["canonical_semantic_mutated"] is False
    assert safety["faiss_mutated"] is False


def test_no_canonical_mutation():
    safety = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/final_safety_verify.json").read_text())
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False
    assert safety["strategies_touched"] is False


def test_no_secrets_cot():
    safety = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/final_safety_verify.json").read_text())
    assert safety["secrets_exposed"] is False
    assert safety["raw_cot_exposed"] is False


def test_dry_run_zero():
    probe = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/kimi_probe_matrix.json").read_text())
    for p in probe.get("probes", []):
        assert p.get("dry_run") is False


def test_post_patch_success_rate():
    probe = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/kimi_probe_matrix.json").read_text())
    successes = sum(
        1 for p in probe.get("probes", [])
        if p.get("content_non_empty") or (p.get("content_len", 0) > 0)
    )
    total = len(probe.get("probes", []))
    assert total >= 3
    assert successes == total  # 100% success with safe_mode=false


def test_route_not_dry_run():
    rc = json.loads((ROOT / "tmp_agent/front_brain_kimi_cloud_stability_mitigation_01/root_cause_classification.json").read_text())
    ruled_out = rc["root_cause_classification"]["ruled_out"]
    assert any("ROUTE_REGRESSION" in item for item in ruled_out)


def test_roadmap_status_valid():
    data = json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    assert "completed_fronts" in data


def test_ledger_exists():
    assert (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").exists()
