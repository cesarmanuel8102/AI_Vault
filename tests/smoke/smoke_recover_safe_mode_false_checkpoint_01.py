import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def test_current_state_exists():
    assert (ROOT / "tmp_agent/recover_safe_mode_false_checkpoint_01/current_state.json").exists()


def test_source_safe_mode_false():
    content = (ROOT / "tmp_agent/brain_v9/start_safe_server.py").read_text(encoding="utf-8")
    assert 'os.environ.setdefault("BRAIN_SAFE_MODE", "false")' in content
    assert 'os.environ.setdefault("BRAIN_SAFE_MODE", "true")' not in content


def test_other_defaults_preserved():
    content = (ROOT / "tmp_agent/brain_v9/start_safe_server.py").read_text(encoding="utf-8")
    assert 'os.environ.setdefault("BRAIN_START_AUTONOMY", "false")' in content
    assert 'os.environ.setdefault("BRAIN_START_PROACTIVE", "false")' in content
    assert 'os.environ.setdefault("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "false")' in content


def test_live_8091_safe_mode_verify_exists():
    assert (ROOT / "tmp_agent/recover_safe_mode_false_checkpoint_01/live_8091_safe_mode_verify.json").exists()


def test_normal_route_after_safe_mode_false_exists():
    assert (ROOT / "tmp_agent/recover_safe_mode_false_checkpoint_01/normal_route_after_safe_mode_false.json").exists()


def test_route_is_not_diagnostic_dry_run():
    report = json.loads((ROOT / "tmp_agent/recover_safe_mode_false_checkpoint_01/normal_route_after_safe_mode_false.json").read_text())
    route = report["normal_route_probe"]["route"]
    assert "diagnostic_dry_run" not in route


def test_dry_run_is_false():
    report = json.loads((ROOT / "tmp_agent/recover_safe_mode_false_checkpoint_01/normal_route_after_safe_mode_false.json").read_text())
    assert report["normal_route_probe"]["dry_run"] is False


def test_provider_selected_present():
    report = json.loads((ROOT / "tmp_agent/recover_safe_mode_false_checkpoint_01/normal_route_after_safe_mode_false.json").read_text())
    assert report["normal_route_probe"]["provider_selected"] is not None


def test_semantic_faiss_unchanged():
    report = json.loads((ROOT / "tmp_agent/recover_safe_mode_false_checkpoint_01/final_safety_verify.json").read_text())
    assert report["canonical_semantic_mutated"] is False
    assert report["faiss_mutated"] is False


def test_no_trading_b8_strategies_touched():
    report = json.loads((ROOT / "tmp_agent/recover_safe_mode_false_checkpoint_01/final_safety_verify.json").read_text())
    assert report["trading_touched"] is False
    assert report["b8_touched"] is False


def test_roadmap_status_valid():
    data = json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    assert "completed_fronts" in data


def test_ledger_exists():
    assert (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").exists()
