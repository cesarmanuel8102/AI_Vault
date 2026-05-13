"""
Comprehensive tests for brain_v9.brain.self_improvement module.
"""
from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import brain_v9.brain.self_improvement as si


# ─── Fixtures ────────────────────────────────────────────────────────────────

MOCK_UTILITY_STATE = {
    "u_score": 0.5,
    "verdict": "hold",
    "can_promote": False,
    "blockers": [],
    "current_phase": "BL-04",
}


@pytest.fixture
def si_env(tmp_path, monkeypatch):
    """Redirect all self_improvement paths into tmp_path."""
    state_root = tmp_path / "state" / "self_improvement"
    changes_root = state_root / "changes"
    staging_root = tmp_path / "staging"
    ledger_file = state_root / "self_improvement_ledger.json"
    policy_file = state_root / "self_improvement_policy.json"
    brain_dir = tmp_path / "brain_v9"
    brain_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(si, "STATE_ROOT", state_root)
    monkeypatch.setattr(si, "CHANGES_ROOT", changes_root)
    monkeypatch.setattr(si, "STAGING_ROOT", staging_root)
    monkeypatch.setattr(si, "LEDGER_FILE", ledger_file)
    monkeypatch.setattr(si, "POLICY_FILE", policy_file)
    monkeypatch.setattr(si, "ALLOWED_ROOTS", [brain_dir.resolve()])
    monkeypatch.setattr(si, "read_utility_state", lambda: dict(MOCK_UTILITY_STATE))
    # Patch BASE_PATH so that relative_to works with tmp_path
    monkeypatch.setattr(si, "BASE_PATH", tmp_path)

    return types.SimpleNamespace(
        state_root=state_root,
        changes_root=changes_root,
        staging_root=staging_root,
        ledger_file=ledger_file,
        policy_file=policy_file,
        brain_dir=brain_dir,
        tmp_path=tmp_path,
    )


def _make_file(env, name="test_module.py", content="# ok\n"):
    """Create a real file inside the brain_dir (ALLOWED_ROOTS)."""
    p = env.brain_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)


# ─── TestUtcNow ──────────────────────────────────────────────────────────────

class TestUtcNow:
    def test_ends_with_z(self):
        result = si._utc_now()
        assert result.endswith("Z")

    def test_is_iso_format(self):
        result = si._utc_now()
        # Should be parseable as ISO datetime
        from datetime import datetime
        # Remove trailing Z and parse
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt is not None

    def test_returns_string(self):
        assert isinstance(si._utc_now(), str)


class TestMetricDegradation:
    def test_metric_threshold_uses_relative_or_minimum_floor(self):
        assert si._metric_degradation_threshold(1.0) == 0.15
        assert si._metric_degradation_threshold(10.0) == 1.5

    def test_detects_metric_degradation(self):
        assert si._is_metric_degraded({"u_score": 1.0}, {"u_score": 0.7}) is True

    def test_ignores_small_metric_movement(self):
        assert si._is_metric_degraded({"u_score": 1.0}, {"u_score": 0.9}) is False


# ─── TestClassifyDomain ──────────────────────────────────────────────────────

class TestClassifyDomain:
    def test_returns_change_type_if_truthy(self):
        assert si._classify_domain("my_type", [{"target": "anything"}]) == "my_type"

    def test_credentials_via_secrets(self):
        assert si._classify_domain("", [{"target": "C:\\secrets\\key.py"}]) == "credentials"

    def test_credentials_via_credential_keyword(self):
        assert si._classify_domain("", [{"target": "some_credential_file.py"}]) == "credentials"

    def test_trading_capital(self):
        assert si._classify_domain("", [{"target": "C:\\trading\\capital_mgr.py"}]) == "trading_capital"

    def test_trading_broker(self):
        assert si._classify_domain("", [{"target": "C:\\trading\\broker_api.py"}]) == "trading_capital"

    def test_trading_order(self):
        assert si._classify_domain("", [{"target": "C:\\trading\\order_exec.py"}]) == "trading_capital"

    def test_trading_connectors(self):
        assert si._classify_domain("", [{"target": "C:\\trading\\signal.py"}]) == "trading_connectors"

    def test_ui(self):
        assert si._classify_domain("", [{"target": "C:\\ui\\dashboard.py"}]) == "ui"

    def test_tools_via_agent(self):
        assert si._classify_domain("", [{"target": "C:\\agent\\tool_handler.py"}]) == "tools"

    def test_tools_via_tools_py(self):
        assert si._classify_domain("", [{"target": "C:\\tools.py"}]) == "tools"

    def test_runtime_core_default(self):
        assert si._classify_domain("", [{"target": "C:\\brain\\main.py"}]) == "runtime_core"

    def test_empty_change_type_string(self):
        # empty string is falsy, should infer
        assert si._classify_domain("", [{"target": "C:\\brain\\engine.py"}]) == "runtime_core"


# ─── TestRequiredEndpoints ───────────────────────────────────────────────────

class TestRequiredEndpoints:
    def test_always_includes_health_and_status(self):
        result = si._required_endpoints([{"target": "foo.txt"}])
        assert "/health" in result
        assert "/status" in result
        assert "/brain/utility" in result

    def test_adds_brain_utility_for_main_py(self):
        result = si._required_endpoints([{"target": "main.py"}])
        assert "/brain/utility" in result
        assert "/self-diagnostic" in result

    def test_adds_brain_utility_for_utility_py(self):
        result = si._required_endpoints([{"target": "utility.py"}])
        assert "/brain/utility" in result

    def test_adds_brain_utility_for_session_py(self):
        result = si._required_endpoints([{"target": "session.py"}])
        assert "/brain/utility" in result

    def test_adds_brain_utility_for_llm_py(self):
        result = si._required_endpoints([{"target": "llm.py"}])
        assert "/brain/utility" in result

    def test_adds_autonomy_status(self):
        result = si._required_endpoints([{"target": "C:\\autonomy\\handler.py"}])
        assert "/autonomy/status" in result

    def test_adds_trading_health(self):
        result = si._required_endpoints([{"target": "C:\\trading\\connector.py"}])
        assert "/trading/health" in result

    def test_results_are_sorted(self):
        result = si._required_endpoints([
            {"target": "C:\\trading\\x.py"},
            {"target": "C:\\autonomy\\y.py"},
            {"target": "main.py"},
        ])
        assert result == sorted(result)

    def test_no_duplicates(self):
        result = si._required_endpoints([{"target": "main.py"}])
        assert len(result) == len(set(result))


# ─── TestBuildImportCheckScript ──────────────────────────────────────────────

class TestBuildImportCheckScript:
    def test_returns_string(self):
        result = si._build_import_check_script(["a.py", "b.py"])
        assert isinstance(result, str)

    def test_contains_import_code(self):
        result = si._build_import_check_script(["test.py"])
        assert "importlib.util" in result
        assert "spec_from_file_location" in result

    def test_includes_file_names(self):
        result = si._build_import_check_script(["my_module.py"])
        assert "my_module.py" in result

    def test_multiple_files(self):
        result = si._build_import_check_script(["a.py", "b.py", "c.py"])
        assert "'a.py'" in result
        assert "'b.py'" in result
        assert "'c.py'" in result

    def test_empty_list(self):
        result = si._build_import_check_script([])
        assert "files = []" in result


# ─── TestComputeImpactDelta ──────────────────────────────────────────────────

class TestComputeImpactDelta:
    def test_returns_none_if_before_is_none(self):
        assert si._compute_impact_delta(None, {"u_score": 1}) is None

    def test_returns_none_if_after_is_none(self):
        assert si._compute_impact_delta({"u_score": 1}, None) is None

    def test_returns_none_if_before_is_empty(self):
        assert si._compute_impact_delta({}, {"u_score": 1}) is None

    def test_returns_none_if_after_is_empty(self):
        assert si._compute_impact_delta({"u_score": 1}, {}) is None

    def test_computes_delta_u_score(self):
        before = {"u_score": 0.3, "verdict": "hold", "can_promote": False, "blockers": []}
        after = {"u_score": 0.8, "verdict": "hold", "can_promote": False, "blockers": []}
        result = si._compute_impact_delta(before, after)
        assert result["delta_u_score"] == pytest.approx(0.5, abs=1e-5)
        assert result["before_u_score"] == 0.3
        assert result["after_u_score"] == 0.8

    def test_verdict_changed_true(self):
        before = {"u_score": 0.5, "verdict": "hold", "can_promote": False, "blockers": []}
        after = {"u_score": 0.5, "verdict": "promote", "can_promote": False, "blockers": []}
        result = si._compute_impact_delta(before, after)
        assert result["verdict_changed"] is True

    def test_verdict_changed_false(self):
        before = {"u_score": 0.5, "verdict": "hold", "can_promote": False, "blockers": []}
        after = {"u_score": 0.6, "verdict": "hold", "can_promote": False, "blockers": []}
        result = si._compute_impact_delta(before, after)
        assert result["verdict_changed"] is False

    def test_can_promote_changed(self):
        before = {"u_score": 0.5, "verdict": "hold", "can_promote": False, "blockers": []}
        after = {"u_score": 0.5, "verdict": "hold", "can_promote": True, "blockers": []}
        result = si._compute_impact_delta(before, after)
        assert result["can_promote_changed"] is True

    def test_blockers_changed(self):
        before = {"u_score": 0.5, "verdict": "hold", "can_promote": False, "blockers": ["a"]}
        after = {"u_score": 0.5, "verdict": "hold", "can_promote": False, "blockers": []}
        result = si._compute_impact_delta(before, after)
        assert result["blockers_changed"] is True

    def test_delta_none_if_scores_not_numeric(self):
        before = {"u_score": "x"}
        after = {"u_score": "y"}
        result = si._compute_impact_delta(before, after)
        assert result["delta_u_score"] is None

    def test_delta_works_with_int_scores(self):
        before = {"u_score": 1}
        after = {"u_score": 3}
        result = si._compute_impact_delta(before, after)
        assert result["delta_u_score"] == 2


# ─── TestCheckAllowedTarget ─────────────────────────────────────────────────

class TestCheckAllowedTarget:
    def test_raises_permission_error_outside_allowed_roots(self, si_env):
        outside = si_env.tmp_path / "other" / "file.py"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("# outside", encoding="utf-8")
        with pytest.raises(PermissionError):
            si._check_allowed_target(str(outside))

    def test_raises_file_not_found_for_missing_file(self, si_env):
        missing = si_env.brain_dir / "nonexistent.py"
        with pytest.raises(FileNotFoundError):
            si._check_allowed_target(str(missing))

    def test_returns_path_for_valid_file(self, si_env):
        f = _make_file(si_env, "allowed.py")
        result = si._check_allowed_target(f)
        assert isinstance(result, Path)
        assert result.exists()

    def test_resolved_path_returned(self, si_env):
        f = _make_file(si_env, "resolved.py")
        result = si._check_allowed_target(f)
        assert result == result.resolve()


# ─── TestEnsureDirs ──────────────────────────────────────────────────────────

class TestEnsureDirs:
    def test_creates_state_root(self, si_env):
        si._ensure_dirs()
        assert si_env.state_root.is_dir()

    def test_creates_changes_root(self, si_env):
        si._ensure_dirs()
        assert si_env.changes_root.is_dir()

    def test_creates_staging_root(self, si_env):
        si._ensure_dirs()
        assert si_env.staging_root.is_dir()

    def test_idempotent(self, si_env):
        si._ensure_dirs()
        si._ensure_dirs()  # should not raise
        assert si_env.state_root.is_dir()


# ─── TestEnsurePolicy ────────────────────────────────────────────────────────

class TestEnsurePolicy:
    def test_creates_policy_file(self, si_env):
        si_env.state_root.mkdir(parents=True, exist_ok=True)
        si._ensure_policy()
        assert si_env.policy_file.exists()

    def test_policy_has_schema_version(self, si_env):
        si_env.state_root.mkdir(parents=True, exist_ok=True)
        si._ensure_policy()
        data = json.loads(si_env.policy_file.read_text(encoding="utf-8"))
        assert data["schema_version"] == "self_improvement_policy_v2"

    def test_does_not_overwrite_existing(self, si_env):
        si_env.state_root.mkdir(parents=True, exist_ok=True)
        custom = {"schema_version": "custom", "my_key": 42}
        si_env.policy_file.write_text(json.dumps(custom), encoding="utf-8")
        si._ensure_policy()
        data = json.loads(si_env.policy_file.read_text(encoding="utf-8"))
        assert data["schema_version"] == "custom"

    def test_policy_has_domain_rules(self, si_env):
        si_env.state_root.mkdir(parents=True, exist_ok=True)
        si._ensure_policy()
        data = json.loads(si_env.policy_file.read_text(encoding="utf-8"))
        assert "domain_rules" in data
        assert "credentials" in data["domain_rules"]

    def test_policy_has_forbidden_markers(self, si_env):
        si_env.state_root.mkdir(parents=True, exist_ok=True)
        si._ensure_policy()
        data = json.loads(si_env.policy_file.read_text(encoding="utf-8"))
        assert "forbidden_path_markers" in data
        assert len(data["forbidden_path_markers"]) > 0


# ─── TestLoadPolicy ─────────────────────────────────────────────────────────

class TestLoadPolicy:
    def test_returns_dict(self, si_env):
        policy = si._load_policy()
        assert isinstance(policy, dict)

    def test_creates_dirs_and_policy(self, si_env):
        policy = si._load_policy()
        assert si_env.state_root.is_dir()
        assert si_env.policy_file.exists()

    def test_returns_existing_policy(self, si_env):
        si_env.state_root.mkdir(parents=True, exist_ok=True)
        custom = {"schema_version": "v_test", "data": True}
        si_env.policy_file.write_text(json.dumps(custom), encoding="utf-8")
        policy = si._load_policy()
        assert policy["schema_version"] == "v_test"


# ─── TestLoadLedger ──────────────────────────────────────────────────────────

class TestLoadLedger:
    def test_creates_seed_if_not_exists(self, si_env):
        ledger = si._load_ledger()
        assert ledger["schema_version"] == "self_improvement_ledger_v2"
        assert ledger["entries"] == []

    def test_returns_existing_ledger(self, si_env):
        si._ensure_dirs()
        si._ensure_policy()
        existing = {"schema_version": "v_x", "updated_utc": "2025", "entries": [{"id": 1}]}
        si_env.ledger_file.write_text(json.dumps(existing), encoding="utf-8")
        ledger = si._load_ledger()
        assert ledger["schema_version"] == "v_x"
        assert len(ledger["entries"]) == 1

    def test_writes_seed_to_disk(self, si_env):
        si._load_ledger()
        assert si_env.ledger_file.exists()


# ─── TestSaveLedger ─────────────────────────────────────────────────────────

class TestSaveLedger:
    def test_writes_ledger_to_disk(self, si_env):
        si._ensure_dirs()
        si._ensure_policy()
        ledger = {"schema_version": "v1", "entries": []}
        si._save_ledger(ledger)
        assert si_env.ledger_file.exists()

    def test_updates_updated_utc(self, si_env):
        si._ensure_dirs()
        si._ensure_policy()
        ledger = {"schema_version": "v1", "entries": []}
        si._save_ledger(ledger)
        saved = json.loads(si_env.ledger_file.read_text(encoding="utf-8"))
        assert "updated_utc" in saved
        assert saved["updated_utc"].endswith("Z")

    def test_roundtrip(self, si_env):
        si._ensure_dirs()
        si._ensure_policy()
        ledger = {"schema_version": "v1", "entries": [{"id": "abc"}]}
        si._save_ledger(ledger)
        loaded = json.loads(si_env.ledger_file.read_text(encoding="utf-8"))
        assert loaded["entries"] == [{"id": "abc"}]


# ─── TestApplyResultToEntry ──────────────────────────────────────────────────

class TestApplyResultToEntry:
    def test_promoted_status(self):
        entry = {"impact_before": {"u_score": 0.5}}
        result = {"promoted": True, "health_status": "healthy", "impact_after": {"u_score": 0.7}}
        si._apply_result_to_entry(entry, result)
        assert entry["status"] == "promoted"
        assert entry["restart"] == "ok"
        assert entry["health"] == "healthy"
        assert entry["rollback"] is False

    def test_rolled_back_healthy(self):
        entry = {"impact_before": {"u_score": 0.5}}
        result = {"promoted": False, "rollback": True, "health_status": "healthy", "impact_after": None}
        si._apply_result_to_entry(entry, result)
        assert entry["status"] == "rolled_back"
        assert entry["restart"] == "rolled_back_healthy"
        assert entry["rollback"] is True

    def test_rolled_back_unhealthy(self):
        entry = {"impact_before": {"u_score": 0.5}}
        result = {"promoted": False, "rollback": True, "health_status": "unhealthy", "impact_after": None}
        si._apply_result_to_entry(entry, result)
        assert entry["status"] == "rolled_back"
        assert entry["restart"] == "failed"

    def test_promotion_failed(self):
        entry = {}
        result = {"promoted": False, "rollback": False}
        si._apply_result_to_entry(entry, result)
        assert entry["status"] == "promotion_failed"
        assert entry["restart"] == "failed"

    def test_sets_impact_after(self):
        entry = {"impact_before": {"u_score": 0.3}}
        result = {"promoted": True, "impact_after": {"u_score": 0.9}}
        si._apply_result_to_entry(entry, result)
        assert entry["impact_after"] == {"u_score": 0.9}

    def test_computes_impact_delta(self):
        entry = {"impact_before": {"u_score": 0.3, "verdict": "hold", "can_promote": False, "blockers": []}}
        result = {"promoted": True, "impact_after": {"u_score": 0.8, "verdict": "hold", "can_promote": False, "blockers": []}}
        si._apply_result_to_entry(entry, result)
        assert entry["impact_delta"]["delta_u_score"] == pytest.approx(0.5, abs=1e-5)

    def test_returns_entry(self):
        entry = {}
        result = {"promoted": True}
        ret = si._apply_result_to_entry(entry, result)
        assert ret is entry


# ─── TestApplyResultToMetadata ───────────────────────────────────────────────

class TestApplyResultToMetadata:
    def test_promoted_status(self):
        metadata = {"change_dir": "C:\\fake\\dir", "impact_before": {"u_score": 0.5}}
        result = {"promoted": True, "impact_after": {"u_score": 0.7}}
        si._apply_result_to_metadata(metadata, result)
        assert metadata["status"] == "promoted"

    def test_rolled_back_status(self):
        metadata = {"change_dir": "C:\\fake\\dir", "impact_before": None}
        result = {"promoted": False, "rollback": True, "impact_after": None}
        si._apply_result_to_metadata(metadata, result)
        assert metadata["status"] == "rolled_back"

    def test_promotion_failed_status(self):
        metadata = {"change_dir": "C:\\fake\\dir", "impact_before": None}
        result = {"promoted": False, "rollback": False}
        si._apply_result_to_metadata(metadata, result)
        assert metadata["status"] == "promotion_failed"

    def test_sets_promotion_field(self):
        metadata = {"change_dir": "C:\\fake\\dir", "impact_before": None}
        result = {"promoted": True}
        si._apply_result_to_metadata(metadata, result)
        assert metadata["promotion"]["status"] == "completed"
        assert "result" in metadata["promotion"]

    def test_sets_impact_after(self):
        metadata = {"change_dir": "C:\\fake\\dir", "impact_before": {"u_score": 0.1}}
        result = {"promoted": True, "impact_after": {"u_score": 0.9}}
        si._apply_result_to_metadata(metadata, result)
        assert metadata["impact_after"] == {"u_score": 0.9}

    def test_computes_impact_delta(self):
        before = {"u_score": 0.2, "verdict": "hold", "can_promote": False, "blockers": []}
        after = {"u_score": 0.6, "verdict": "hold", "can_promote": False, "blockers": []}
        metadata = {"change_dir": "C:\\fake\\dir", "impact_before": before}
        result = {"promoted": True, "impact_after": after}
        si._apply_result_to_metadata(metadata, result)
        assert metadata["impact_delta"]["delta_u_score"] == pytest.approx(0.4, abs=1e-5)

    def test_rollback_field_set_on_rollback(self):
        metadata = {"change_dir": "C:\\fake\\dir", "impact_before": None}
        result = {"promoted": False, "rollback": True}
        si._apply_result_to_metadata(metadata, result)
        assert "rollback" in metadata
        assert metadata["rollback"]["trigger"] == "automatic_after_promotion_failure"

    def test_rollback_preserves_existing(self):
        existing_rollback = {"timestamp": "old", "trigger": "manual"}
        metadata = {"change_dir": "C:\\fake\\dir", "impact_before": None, "rollback": existing_rollback}
        result = {"promoted": False, "rollback": True}
        si._apply_result_to_metadata(metadata, result)
        # Should keep existing rollback
        assert metadata["rollback"]["trigger"] == "manual"

    def test_returns_metadata(self):
        metadata = {"change_dir": "C:\\fake\\dir", "impact_before": None}
        result = {"promoted": True}
        ret = si._apply_result_to_metadata(metadata, result)
        assert ret is metadata


# ─── TestEvaluatePromotionGate ───────────────────────────────────────────────

class TestEvaluatePromotionGate:
    def test_allow_promote_when_all_checks_pass(self, si_env):
        metadata = {
            "change_type": "tools",
            "files": [{"target": str(si_env.brain_dir / "tool.py")}],
            "validation": {"passed": True, "required_endpoints": ["/health"]},
        }
        gate = si._evaluate_promotion_gate(metadata)
        assert gate["allow_promote"] is True
        assert gate["blockers"] == []

    def test_blocked_for_forbidden_domain(self, si_env):
        metadata = {
            "change_type": "credentials",
            "files": [{"target": "some_file.py"}],
            "validation": {"passed": True, "required_endpoints": ["/health"]},
        }
        gate = si._evaluate_promotion_gate(metadata)
        assert gate["allow_promote"] is False
        assert "domain_allowed" in gate["blockers"]

    def test_blocked_for_sensitive_path(self, si_env):
        metadata = {
            "change_type": "tools",
            "files": [{"target": "C:\\tmp_agent\\Secrets\\key.py"}],
            "validation": {"passed": True, "required_endpoints": ["/health"]},
        }
        gate = si._evaluate_promotion_gate(metadata)
        assert gate["allow_promote"] is False
        assert "sensitive_paths_allowed" in gate["blockers"]

    def test_blocked_for_failed_validation(self, si_env):
        metadata = {
            "change_type": "tools",
            "files": [{"target": str(si_env.brain_dir / "tool.py")}],
            "validation": {"passed": False},
        }
        gate = si._evaluate_promotion_gate(metadata)
        assert gate["allow_promote"] is False
        assert "validation_passed" in gate["blockers"]

    def test_blocked_for_missing_validation(self, si_env):
        metadata = {
            "change_type": "tools",
            "files": [{"target": str(si_env.brain_dir / "tool.py")}],
            "validation": None,
        }
        gate = si._evaluate_promotion_gate(metadata)
        assert gate["allow_promote"] is False

    def test_blocked_for_no_required_endpoints(self, si_env):
        metadata = {
            "change_type": "tools",
            "files": [{"target": str(si_env.brain_dir / "tool.py")}],
            "validation": {"passed": True},
        }
        gate = si._evaluate_promotion_gate(metadata)
        assert gate["allow_promote"] is False
        assert "required_endpoints_declared" in gate["blockers"]

    def test_returns_domain_and_rule(self, si_env):
        metadata = {
            "change_type": "ui",
            "files": [{"target": "x.py"}],
            "validation": {"passed": True, "required_endpoints": ["/health"]},
        }
        gate = si._evaluate_promotion_gate(metadata)
        assert gate["domain"] == "ui"
        assert gate["domain_rule"] == "auto_with_validation"

    def test_returns_evaluated_utc(self, si_env):
        metadata = {
            "change_type": "tools",
            "files": [{"target": "x.py"}],
            "validation": {"passed": True, "required_endpoints": ["/health"]},
        }
        gate = si._evaluate_promotion_gate(metadata)
        assert gate["evaluated_utc"].endswith("Z")

    def test_capital_state_forbidden_marker(self, si_env):
        metadata = {
            "change_type": "tools",
            "files": [{"target": "capital_state.json"}],
            "validation": {"passed": True, "required_endpoints": ["/health"]},
        }
        gate = si._evaluate_promotion_gate(metadata)
        assert gate["allow_promote"] is False
        assert "sensitive_paths_allowed" in gate["blockers"]


# ─── TestCreateStagedChange ──────────────────────────────────────────────────

class TestCreateStagedChange:
    def test_creates_metadata(self, si_env):
        f = _make_file(si_env)
        metadata = si.create_staged_change([f], objective="test obj", change_type="code_patch")
        assert metadata["status"] == "staged"
        assert metadata["objective"] == "test obj"
        assert metadata["change_type"] == "code_patch"

    def test_creates_change_dir(self, si_env):
        f = _make_file(si_env)
        metadata = si.create_staged_change([f])
        change_dir = Path(metadata["change_dir"])
        assert change_dir.is_dir()
        assert (change_dir / "metadata.json").exists()

    def test_copies_files_to_staging(self, si_env):
        f = _make_file(si_env, content="hello world\n")
        metadata = si.create_staged_change([f])
        staged = Path(metadata["files"][0]["staged"])
        assert staged.exists()
        assert staged.read_text(encoding="utf-8") == "hello world\n"

    def test_creates_backups_dir(self, si_env):
        f = _make_file(si_env)
        metadata = si.create_staged_change([f])
        backups_dir = Path(metadata["change_dir"]) / "backups"
        assert backups_dir.is_dir()

    def test_appends_ledger_entry(self, si_env):
        f = _make_file(si_env)
        metadata = si.create_staged_change([f], objective="ledger test")
        ledger = json.loads(si_env.ledger_file.read_text(encoding="utf-8"))
        assert len(ledger["entries"]) == 1
        assert ledger["entries"][0]["change_id"] == metadata["change_id"]
        assert ledger["entries"][0]["objective"] == "ledger test"
        assert ledger["entries"][0]["status"] == "staged"

    def test_multiple_files(self, si_env):
        f1 = _make_file(si_env, "a.py", "# a\n")
        f2 = _make_file(si_env, "b.py", "# b\n")
        metadata = si.create_staged_change([f1, f2])
        assert len(metadata["files"]) == 2

    def test_change_id_format(self, si_env):
        f = _make_file(si_env)
        metadata = si.create_staged_change([f])
        assert metadata["change_id"].startswith("chg_")

    def test_impact_before_captured(self, si_env):
        f = _make_file(si_env)
        metadata = si.create_staged_change([f])
        assert metadata["impact_before"] is not None
        assert "u_score" in metadata["impact_before"]

    def test_initial_fields_are_none(self, si_env):
        f = _make_file(si_env)
        metadata = si.create_staged_change([f])
        assert metadata["validation"] is None
        assert metadata["promotion_gate"] is None
        assert metadata["promotion"] is None
        assert metadata["rollback"] is None

    def test_raises_for_disallowed_file(self, si_env):
        outside = si_env.tmp_path / "other" / "bad.py"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("# bad", encoding="utf-8")
        with pytest.raises(PermissionError):
            si.create_staged_change([str(outside)])


# ─── TestValidateStagedChange ────────────────────────────────────────────────

class TestValidateStagedChange:
    def _create_staged(self, si_env, content="x = 1\n"):
        f = _make_file(si_env, "valid_module.py", content)
        return si.create_staged_change([f], objective="validate test")

    def test_validate_passing(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]
        # Mock _run_subprocess to return passing results
        monkeypatch.setattr(si, "_run_subprocess", lambda args, timeout=90: {
            "passed": True, "returncode": 0, "stdout": "", "stderr": "", "duration_ms": 10
        })
        result = si.validate_staged_change(change_id)
        assert result["passed"] is True
        assert result["errors"] == []

    def test_validate_updates_metadata_status(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]
        monkeypatch.setattr(si, "_run_subprocess", lambda args, timeout=90: {
            "passed": True, "returncode": 0, "stdout": "", "stderr": "", "duration_ms": 10
        })
        si.validate_staged_change(change_id)
        meta_path = si.CHANGES_ROOT / change_id / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["status"] == "validated"

    def test_validate_syntax_failure(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]
        call_count = [0]
        def mock_run(args, timeout=90):
            call_count[0] += 1
            if call_count[0] == 1:  # syntax check
                return {"passed": False, "returncode": 1, "stdout": "", "stderr": "SyntaxError", "duration_ms": 5}
            return {"passed": True, "returncode": 0, "stdout": "", "stderr": "", "duration_ms": 5}
        monkeypatch.setattr(si, "_run_subprocess", mock_run)
        result = si.validate_staged_change(change_id)
        assert result["passed"] is False
        assert len(result["errors"]) > 0

    def test_validate_import_failure(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]
        call_count = [0]
        def mock_run(args, timeout=90):
            call_count[0] += 1
            if call_count[0] == 2:  # import check
                return {"passed": False, "returncode": 1, "stdout": "", "stderr": "ImportError", "duration_ms": 5}
            return {"passed": True, "returncode": 0, "stdout": "", "stderr": "", "duration_ms": 5}
        monkeypatch.setattr(si, "_run_subprocess", mock_run)
        result = si.validate_staged_change(change_id)
        assert result["passed"] is False

    def test_validate_updates_ledger(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]
        monkeypatch.setattr(si, "_run_subprocess", lambda args, timeout=90: {
            "passed": True, "returncode": 0, "stdout": "", "stderr": "", "duration_ms": 10
        })
        si.validate_staged_change(change_id)
        ledger = json.loads(si_env.ledger_file.read_text(encoding="utf-8"))
        entry = next(e for e in ledger["entries"] if e["change_id"] == change_id)
        assert entry["validation"] == "passed"
        assert entry["status"] == "validated"

    def test_validate_sets_gate(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]
        monkeypatch.setattr(si, "_run_subprocess", lambda args, timeout=90: {
            "passed": True, "returncode": 0, "stdout": "", "stderr": "", "duration_ms": 10
        })
        si.validate_staged_change(change_id)
        meta_path = si.CHANGES_ROOT / change_id / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["promotion_gate"] is not None
        assert "allow_promote" in meta["promotion_gate"]

    def test_validate_not_found_raises(self, si_env):
        with pytest.raises(FileNotFoundError):
            si.validate_staged_change("nonexistent_id")

    def test_validate_includes_required_endpoints(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]
        monkeypatch.setattr(si, "_run_subprocess", lambda args, timeout=90: {
            "passed": True, "returncode": 0, "stdout": "", "stderr": "", "duration_ms": 10
        })
        result = si.validate_staged_change(change_id)
        assert "/health" in result["required_endpoints"]
        assert "/status" in result["required_endpoints"]

    def test_validate_failed_status_in_metadata(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]
        monkeypatch.setattr(si, "_run_subprocess", lambda args, timeout=90: {
            "passed": False, "returncode": 1, "stdout": "", "stderr": "fail", "duration_ms": 5
        })
        si.validate_staged_change(change_id)
        meta_path = si.CHANGES_ROOT / change_id / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["status"] == "validation_failed"

    def test_validate_ledger_entry_failed(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]
        monkeypatch.setattr(si, "_run_subprocess", lambda args, timeout=90: {
            "passed": False, "returncode": 1, "stdout": "", "stderr": "fail", "duration_ms": 5
        })
        si.validate_staged_change(change_id)
        ledger = json.loads(si_env.ledger_file.read_text(encoding="utf-8"))
        entry = next(e for e in ledger["entries"] if e["change_id"] == change_id)
        assert entry["validation"] == "failed"

    def test_validate_runs_relevant_unit_tests(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]

        def _fake_run(args, timeout=90):
            return {"passed": True, "returncode": 0, "stdout": "", "stderr": "", "duration_ms": 10}

        monkeypatch.setattr(si, "_run_subprocess", _fake_run)
        monkeypatch.setattr(si, "_discover_relevant_tests", lambda files: ["C:/AI_VAULT/tmp_agent/tests/test_sample.py"])
        monkeypatch.setattr(
            si,
            "_run_subprocess_with_env",
            lambda args, timeout=90, extra_env=None: {
                "passed": True,
                "returncode": 0,
                "stdout": "1 passed",
                "stderr": "",
                "duration_ms": 25,
            },
        )

        result = si.validate_staged_change(change_id)

        assert result["checks"]["unit_tests"]["passed"] is True
        assert result["checks"]["unit_tests"]["targets"] == ["C:/AI_VAULT/tmp_agent/tests/test_sample.py"]

    def test_validate_marks_unit_tests_not_found(self, si_env, monkeypatch):
        metadata = self._create_staged(si_env)
        change_id = metadata["change_id"]
        monkeypatch.setattr(si, "_run_subprocess", lambda args, timeout=90: {
            "passed": True, "returncode": 0, "stdout": "", "stderr": "", "duration_ms": 10
        })
        monkeypatch.setattr(si, "_discover_relevant_tests", lambda files: [])

        result = si.validate_staged_change(change_id)

        assert result["checks"]["unit_tests"]["status"] == "no_relevant_tests_found"
        assert result["checks"]["unit_tests"]["passed"] is None


# ─── TestPromoteStagedChange ────────────────────────────────────────────────

class TestPromoteStagedChange:
    def _create_and_validate(self, si_env, monkeypatch):
        f = _make_file(si_env, "promo_module.py", "x = 1\n")
        metadata = si.create_staged_change([f], objective="promote test")
        change_id = metadata["change_id"]
        monkeypatch.setattr(si, "_run_subprocess", lambda args, timeout=90: {
            "passed": True, "returncode": 0, "stdout": "", "stderr": "", "duration_ms": 10
        })
        si.validate_staged_change(change_id)
        return change_id

    def test_promote_blocked_when_gate_fails(self, si_env, monkeypatch):
        f = _make_file(si_env, "blocked.py", "x = 1\n")
        metadata = si.create_staged_change([f], objective="blocked", change_type="credentials")
        change_id = metadata["change_id"]
        # Don't validate - force gate failure
        monkeypatch.setattr(si, "_run_subprocess", lambda args, timeout=90: {
            "passed": False, "returncode": 1, "stdout": "", "stderr": "fail", "duration_ms": 5
        })
        si.validate_staged_change(change_id)
        # Mock subprocess.run to avoid real execution
        monkeypatch.setattr("subprocess.run", MagicMock())
        result = si.promote_staged_change(change_id)
        assert result["success"] is False
        assert result["status"] == "promotion_blocked"

    def test_promote_success_schedules(self, si_env, monkeypatch):
        change_id = self._create_and_validate(si_env, monkeypatch)
        mock_subproc = MagicMock()
        monkeypatch.setattr("subprocess.run", mock_subproc)
        result = si.promote_staged_change(change_id)
        assert result["success"] is True
        assert result["status"] == "promotion_scheduled"
        assert "job_id" in result

    def test_promote_writes_helper(self, si_env, monkeypatch):
        change_id = self._create_and_validate(si_env, monkeypatch)
        monkeypatch.setattr("subprocess.run", MagicMock())
        result = si.promote_staged_change(change_id)
        helper_path = Path(result["helper"])
        assert helper_path.exists()
        assert helper_path.suffix == ".ps1"

    def test_promote_helper_contains_metric_gate(self, si_env, monkeypatch):
        change_id = self._create_and_validate(si_env, monkeypatch)
        monkeypatch.setattr("subprocess.run", MagicMock())
        result = si.promote_staged_change(change_id)
        helper_path = Path(result["helper"])
        helper_text = helper_path.read_text(encoding="utf-8")
        assert "metric_check" in helper_text
        assert "u_score degraded" in helper_text

    def test_promote_updates_ledger(self, si_env, monkeypatch):
        change_id = self._create_and_validate(si_env, monkeypatch)
        monkeypatch.setattr("subprocess.run", MagicMock())
        si.promote_staged_change(change_id)
        ledger = json.loads(si_env.ledger_file.read_text(encoding="utf-8"))
        entry = next(e for e in ledger["entries"] if e["change_id"] == change_id)
        assert entry["status"] == "promotion_scheduled"

    def test_promote_updates_metadata(self, si_env, monkeypatch):
        change_id = self._create_and_validate(si_env, monkeypatch)
        monkeypatch.setattr("subprocess.run", MagicMock())
        si.promote_staged_change(change_id)
        meta_path = si.CHANGES_ROOT / change_id / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["status"] == "promotion_scheduled"
        assert meta["promotion"]["status"] == "scheduled"

    def test_promote_not_found_raises(self, si_env, monkeypatch):
        monkeypatch.setattr("subprocess.run", MagicMock())
        with pytest.raises(FileNotFoundError):
            si.promote_staged_change("nonexistent_id")

    def test_promote_returns_gate(self, si_env, monkeypatch):
        change_id = self._create_and_validate(si_env, monkeypatch)
        monkeypatch.setattr("subprocess.run", MagicMock())
        result = si.promote_staged_change(change_id)
        assert "gate" in result
        assert result["gate"]["allow_promote"] is True


# ─── TestRollbackChange ──────────────────────────────────────────────────────

class TestRollbackChange:
    def test_rollback_restores_files(self, si_env, monkeypatch):
        f = _make_file(si_env, "rollback_mod.py", "original\n")
        metadata = si.create_staged_change([f], objective="rollback test")
        change_id = metadata["change_id"]
        # Create backup
        backups_dir = Path(metadata["change_dir"]) / "backups"
        backup_file = backups_dir / "0_rollback_mod.py.bak"
        backup_file.write_text("original\n", encoding="utf-8")
        # Modify the original
        Path(f).write_text("modified\n", encoding="utf-8")
        result = si.rollback_change(change_id)
        assert result["success"] is True
        assert result["status"] == "rolled_back"
        assert Path(f).read_text(encoding="utf-8") == "original\n"

    def test_rollback_updates_metadata(self, si_env, monkeypatch):
        f = _make_file(si_env, "rb_meta.py", "content\n")
        metadata = si.create_staged_change([f], objective="rb meta test")
        change_id = metadata["change_id"]
        si.rollback_change(change_id)
        meta_path = si.CHANGES_ROOT / change_id / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["status"] == "rolled_back"
        assert meta["rollback"]["timestamp"].endswith("Z")

    def test_rollback_updates_ledger(self, si_env, monkeypatch):
        f = _make_file(si_env, "rb_ledger.py", "content\n")
        metadata = si.create_staged_change([f], objective="rb ledger test")
        change_id = metadata["change_id"]
        si.rollback_change(change_id)
        ledger = json.loads(si_env.ledger_file.read_text(encoding="utf-8"))
        entry = next(e for e in ledger["entries"] if e["change_id"] == change_id)
        assert entry["rollback"] is True
        assert entry["status"] == "rolled_back"

    def test_rollback_not_found_raises(self, si_env):
        with pytest.raises(FileNotFoundError):
            si.rollback_change("nonexistent_id")

    def test_rollback_no_backup_skips_restore(self, si_env, monkeypatch):
        f = _make_file(si_env, "no_bak.py", "content\n")
        metadata = si.create_staged_change([f], objective="no backup test")
        change_id = metadata["change_id"]
        result = si.rollback_change(change_id)
        assert result["restored_files"] == []


# ─── TestGetChangeStatus ─────────────────────────────────────────────────────

class TestGetChangeStatus:
    def test_returns_status_for_staged_change(self, si_env):
        f = _make_file(si_env, "status_mod.py")
        metadata = si.create_staged_change([f], objective="status test")
        change_id = metadata["change_id"]
        status = si.get_change_status(change_id)
        assert status["change_id"] == change_id
        assert status["status"] == "staged"
        assert status["objective"] == "status test"

    def test_raises_for_unknown_change(self, si_env):
        # Need to ensure ledger exists
        si._ensure_dirs()
        si._ensure_policy()
        si._load_ledger()
        with pytest.raises(FileNotFoundError):
            si.get_change_status("nonexistent_id")

    def test_job_status_idle(self, si_env):
        f = _make_file(si_env, "idle_mod.py")
        metadata = si.create_staged_change([f])
        status = si.get_change_status(metadata["change_id"])
        assert status["job_status"] == "idle"

    def test_job_status_completed_with_result(self, si_env):
        f = _make_file(si_env, "completed_mod.py")
        metadata = si.create_staged_change([f])
        change_id = metadata["change_id"]
        result_path = Path(metadata["change_dir"]) / "promotion_result.json"
        result_path.write_text(json.dumps({"promoted": True}), encoding="utf-8")
        status = si.get_change_status(change_id)
        assert status["job_status"] == "completed"
        assert status["promotion_result"] == {"promoted": True}

    def test_job_id_format(self, si_env):
        f = _make_file(si_env, "jid_mod.py")
        metadata = si.create_staged_change([f])
        status = si.get_change_status(metadata["change_id"])
        assert status["job_id"] == f"job_{metadata['change_id']}"


# ─── TestReconcileLedger ────────────────────────────────────────────────────

class TestReconcileLedger:
    def test_syncs_validation_from_metadata(self, si_env):
        f = _make_file(si_env, "recon_val.py")
        metadata = si.create_staged_change([f], objective="recon test")
        change_id = metadata["change_id"]
        # Write metadata with validation info
        meta_path = si.CHANGES_ROOT / change_id / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["validation"] = {"passed": True}
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        ledger = si._load_ledger()
        ledger = si._reconcile_ledger(ledger)
        entry = next(e for e in ledger["entries"] if e["change_id"] == change_id)
        assert entry["validation"] == "passed"

    def test_syncs_gate_from_metadata(self, si_env):
        f = _make_file(si_env, "recon_gate.py")
        metadata = si.create_staged_change([f])
        change_id = metadata["change_id"]
        meta_path = si.CHANGES_ROOT / change_id / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["promotion_gate"] = {"allow_promote": True}
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        ledger = si._load_ledger()
        ledger = si._reconcile_ledger(ledger)
        entry = next(e for e in ledger["entries"] if e["change_id"] == change_id)
        assert entry["gate"] is True

    def test_syncs_impact_before_from_metadata(self, si_env):
        f = _make_file(si_env, "recon_impact.py")
        metadata = si.create_staged_change([f])
        change_id = metadata["change_id"]
        meta_path = si.CHANGES_ROOT / change_id / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["impact_before"] = {"u_score": 0.42}
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        # Clear ledger entry impact_before to force sync
        ledger = si._load_ledger()
        for entry in ledger["entries"]:
            if entry["change_id"] == change_id:
                entry["impact_before"] = None
        si._save_ledger(ledger)
        ledger = si._load_ledger()
        ledger = si._reconcile_ledger(ledger)
        entry = next(e for e in ledger["entries"] if e["change_id"] == change_id)
        assert entry["impact_before"]["u_score"] == 0.42

    def test_applies_promotion_result(self, si_env):
        f = _make_file(si_env, "recon_promo.py")
        metadata = si.create_staged_change([f])
        change_id = metadata["change_id"]
        result_path = si.CHANGES_ROOT / change_id / "promotion_result.json"
        result_path.write_text(json.dumps({
            "promoted": True, "rollback": False, "health_status": "healthy",
            "impact_after": {"u_score": 0.9}
        }), encoding="utf-8")
        ledger = si._load_ledger()
        ledger = si._reconcile_ledger(ledger)
        entry = next(e for e in ledger["entries"] if e["change_id"] == change_id)
        assert entry["status"] == "promoted"
        assert entry["health"] == "healthy"

    def test_no_change_no_save(self, si_env):
        """If nothing changes, ledger should not be re-saved."""
        f = _make_file(si_env, "recon_noop.py")
        si.create_staged_change([f])
        ledger = si._load_ledger()
        old_text = si_env.ledger_file.read_text(encoding="utf-8")
        # Reconcile with no extra metadata updates
        si._reconcile_ledger(ledger)
        # The file should have the same entries (updated_utc may change if saved)
        # Since no changes, _save_ledger should not be called
        new_text = si_env.ledger_file.read_text(encoding="utf-8")
        assert old_text == new_text

    def test_reconcile_handles_missing_metadata(self, si_env):
        """Entries whose change_dir doesn't have metadata.json are just skipped."""
        si._ensure_dirs()
        si._ensure_policy()
        ledger = si._load_ledger()
        ledger["entries"].append({
            "change_id": "ghost_id",
            "timestamp": si._utc_now(),
            "objective": "",
            "files": [],
            "status": "staged",
            "validation": None,
            "gate": None,
            "restart": None,
            "health": None,
            "rollback": False,
            "impact_before": None,
            "impact_after": None,
            "impact_delta": None,
        })
        si._save_ledger(ledger)
        ledger = si._load_ledger()
        # Should not raise
        result = si._reconcile_ledger(ledger)
        entry = next(e for e in result["entries"] if e["change_id"] == "ghost_id")
        assert entry["status"] == "staged"

    def test_syncs_status_from_metadata_without_promotion_result(self, si_env):
        f = _make_file(si_env, "recon_status.py")
        metadata = si.create_staged_change([f])
        change_id = metadata["change_id"]
        meta_path = si.CHANGES_ROOT / change_id / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = "validated"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        ledger = si._load_ledger()
        ledger = si._reconcile_ledger(ledger)
        entry = next(e for e in ledger["entries"] if e["change_id"] == change_id)
        assert entry["status"] == "validated"


# ─── TestGetSelfImprovementLedger ───────────────────────────────────────────

class TestGetSelfImprovementLedger:
    def test_returns_ledger(self, si_env):
        ledger = si.get_self_improvement_ledger()
        assert "entries" in ledger
        assert "schema_version" in ledger

    def test_creates_seed_if_empty(self, si_env):
        ledger = si.get_self_improvement_ledger()
        assert ledger["entries"] == []

    def test_reconciles_entries(self, si_env):
        f = _make_file(si_env, "get_ledger_test.py")
        metadata = si.create_staged_change([f])
        change_id = metadata["change_id"]
        meta_path = si.CHANGES_ROOT / change_id / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["validation"] = {"passed": True}
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        ledger = si.get_self_improvement_ledger()
        entry = next(e for e in ledger["entries"] if e["change_id"] == change_id)
        assert entry["validation"] == "passed"
