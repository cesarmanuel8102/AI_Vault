"""
Tests for Phase 5 Sprint 4: P5-12, P5-13, P5-14.

P5-12: synthesize_chat_product_contract — quality benchmarking
P5-13: improve_chat_product_quality — LLM param tuning from observed quality
P5-14: synthesize_utility_governance_contract — governance reports

Verifies:
  - All three actions return honest success (based on checks, not hardcoded)
  - Repair plans are built from failing checks
  - Audit trail is written to scorecard
  - Meta execution ledger entries are appended
  - Quality regression detection (P5-13)
  - U-proxy alignment analysis (P5-14)
  - Edge cases: all checks pass, all fail, partial
"""
import asyncio
import json
import pytest
from pathlib import Path
from typing import Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_action_executor(monkeypatch, tmp_path):
    """Redirect action_executor module-level paths to tmp_path."""
    import brain_v9.autonomy.action_executor as ae

    state = tmp_path / "tmp_agent" / "state"
    rooms = state / "rooms"
    monkeypatch.setattr(ae, "STATE_PATH", state)
    monkeypatch.setattr(ae, "ROOMS_PATH", rooms)
    monkeypatch.setattr(ae, "JOBS_PATH", state / "autonomy_action_jobs")
    monkeypatch.setattr(ae, "JOBS_LEDGER", state / "autonomy_action_ledger.json")
    monkeypatch.setattr(ae, "NEXT_ACTIONS_PATH", state / "autonomy_next_actions.json")
    monkeypatch.setattr(ae, "SCORECARD_PATH",
                        rooms / "brain_binary_paper_pb05_journal" / "session_result_scorecard.json")
    monkeypatch.setattr(ae, "TRADING_POLICY_PATH", state / "trading_autonomy_policy.json")

    (state / "autonomy_action_jobs").mkdir(parents=True, exist_ok=True)
    (rooms / "brain_binary_paper_pb05_journal").mkdir(parents=True, exist_ok=True)

    return ae


def _make_chat_status(*, accepted: bool, quality_score: float = 1.0,
                      failing_baseline: list = None, failing_quality: list = None) -> Dict:
    """Build a realistic chat_product_status dict."""
    baseline_checks = [
        {"check_id": "dashboard_has_chat_link", "passed": True,
         "detail": "OK", "repair_hint": "Add href"},
        {"check_id": "brain_ui_exists", "passed": True,
         "detail": "OK", "repair_hint": "Create UI"},
        {"check_id": "main_exposes_chat_route", "passed": True,
         "detail": "OK", "repair_hint": "Add /chat route"},
        {"check_id": "main_exposes_chat_product_status", "passed": True,
         "detail": "OK", "repair_hint": "Add status endpoint"},
    ]
    quality_checks = [
        {"check_id": "ui_has_status_panel", "passed": True,
         "detail": "OK", "repair_hint": "Add panel"},
        {"check_id": "ui_has_model_selector", "passed": True,
         "detail": "OK", "repair_hint": "Add selector"},
        {"check_id": "session_uses_memory_manager", "passed": True,
         "detail": "OK", "repair_hint": "Connect MemoryManager"},
        {"check_id": "session_normalizes_response", "passed": True,
         "detail": "OK", "repair_hint": "Add normalization"},
        {"check_id": "memory_persists_short_and_long_term", "passed": True,
         "detail": "OK", "repair_hint": "Persist both"},
        {"check_id": "main_exposes_chat_product_refresh", "passed": True,
         "detail": "OK", "repair_hint": "Add refresh endpoint"},
    ]

    for check_id in (failing_baseline or []):
        for c in baseline_checks:
            if c["check_id"] == check_id:
                c["passed"] = False
                c["detail"] = "FAILING"

    for check_id in (failing_quality or []):
        for c in quality_checks:
            if c["check_id"] == check_id:
                c["passed"] = False
                c["detail"] = "FAILING"

    failed = [c for c in baseline_checks if not c["passed"]]
    return {
        "schema_version": "chat_product_status_v1",
        "accepted_baseline": accepted,
        "current_state": "quality_observable" if accepted and quality_score >= 0.8 else (
            "accepted_baseline" if accepted else "needs_product_work"
        ),
        "work_status": "ready_for_conversational_tuning" if accepted and quality_score >= 0.8 else (
            "ready_for_chat_improvement" if accepted else "blocked_missing_baseline"
        ),
        "quality_score": quality_score,
        "acceptance_checks": baseline_checks,
        "quality_checks": quality_checks,
        "failed_check_count": len(failed),
        "evidence_paths": ["/some/path"],
        "meta_brain_handoff": "test_handoff",
    }


def _make_utility_status(*, accepted: bool, u_proxy_score=None, verdict=None,
                         blockers=None, failing_checks=None) -> Dict:
    """Build a realistic utility_governance_status dict."""
    checks = [
        {"check_id": "utility_snapshot_exists", "passed": True,
         "detail": "OK", "repair_hint": "Recalculate snapshot"},
        {"check_id": "utility_gate_exists", "passed": True,
         "detail": "OK", "repair_hint": "Recalculate gate"},
        {"check_id": "utility_module_has_lifts", "passed": True,
         "detail": "OK", "repair_hint": "Add lifts"},
        {"check_id": "main_exposes_utility_route", "passed": True,
         "detail": "OK", "repair_hint": "Add /brain/utility"},
        {"check_id": "main_exposes_utility_governance_status", "passed": True,
         "detail": "OK", "repair_hint": "Add governance endpoint"},
    ]
    for check_id in (failing_checks or []):
        for c in checks:
            if c["check_id"] == check_id:
                c["passed"] = False
                c["detail"] = "FAILING"

    failed = [c for c in checks if not c["passed"]]
    return {
        "schema_version": "utility_governance_status_v1",
        "accepted_baseline": accepted,
        "current_state": "accepted_baseline" if accepted else "needs_governance_baseline",
        "work_status": "ready_for_utility_improvement" if accepted else "blocked_missing_baseline",
        "acceptance_checks": checks,
        "failed_check_count": len(failed),
        "u_proxy_score": u_proxy_score,
        "verdict": verdict,
        "blockers": blockers or [],
        "evidence_paths": ["/some/path"],
        "meta_brain_handoff": "test_handoff",
    }


def _stub_refreshes(monkeypatch, ae, chat_status=None, utility_status=None):
    """Stub out refresh functions so they return test data without touching real files."""
    if chat_status is not None:
        monkeypatch.setattr(ae, "refresh_chat_product_status", lambda: chat_status)
    if utility_status is not None:
        monkeypatch.setattr(ae, "refresh_utility_governance_status", lambda: utility_status)
    monkeypatch.setattr(ae, "refresh_post_bl_roadmap_status", lambda: {})


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ========================================================================
# P5-12: synthesize_chat_product_contract
# ========================================================================
class TestSynthesizeChatContractRegistered:

    def test_in_action_map(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        assert "synthesize_chat_product_contract" in ae.ACTION_MAP
        assert ae.ACTION_MAP["synthesize_chat_product_contract"] is ae.synthesize_chat_product_contract


class TestSynthesizeChatContractAccepted:

    def test_success_when_baseline_accepted(self, isolated_base_path, monkeypatch):
        """Should return success=True when all baseline checks pass."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_chat_status(accepted=True, quality_score=1.0)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        result = _run(ae.synthesize_chat_product_contract())

        assert result["success"] is True
        assert result["accepted_baseline"] is True
        assert result["failed_check_count"] == 0
        assert result["repair_plan"] == []

    def test_result_structure(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_chat_status(accepted=True)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        result = _run(ae.synthesize_chat_product_contract())

        assert result["action_name"] == "synthesize_chat_product_contract"
        assert result["mode"] == "meta_governance"
        assert result["paper_only_enforced"] is True
        assert "repair_plan" in result
        assert "quality_score" in result
        assert "evidence_paths" in result


class TestSynthesizeChatContractFailing:

    def test_failure_when_baseline_not_accepted(self, isolated_base_path, monkeypatch):
        """Should return success=False when baseline checks fail."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_chat_status(
            accepted=False,
            failing_baseline=["dashboard_has_chat_link", "main_exposes_chat_route"],
        )
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        result = _run(ae.synthesize_chat_product_contract())

        assert result["success"] is False
        assert result["accepted_baseline"] is False
        assert result["failed_check_count"] == 2
        assert len(result["repair_plan"]) >= 2
        repair_ids = {r["check_id"] for r in result["repair_plan"]}
        assert "dashboard_has_chat_link" in repair_ids
        assert "main_exposes_chat_route" in repair_ids

    def test_repair_plan_includes_quality_failures(self, isolated_base_path, monkeypatch):
        """Repair plan should include both baseline AND quality failures."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_chat_status(
            accepted=True,  # baseline passes
            quality_score=0.5,
            failing_quality=["ui_has_status_panel", "session_normalizes_response"],
        )
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        result = _run(ae.synthesize_chat_product_contract())

        assert result["success"] is True  # baseline accepted
        repair_ids = {r["check_id"] for r in result["repair_plan"]}
        assert "ui_has_status_panel" in repair_ids
        assert "session_normalizes_response" in repair_ids


class TestSynthesizeChatContractAudit:

    def test_logs_to_scorecard(self, isolated_base_path, monkeypatch):
        """Should append to scorecard autonomy_strategy_notes."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_chat_status(accepted=True)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        _run(ae.synthesize_chat_product_contract())

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_strategy_notes", [])
        assert len(notes) >= 1
        assert notes[-1]["action"] == "synthesize_chat_product_contract"
        assert notes[-1]["result"] == "contract_accepted"

    def test_logs_failure_to_scorecard(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_chat_status(accepted=False, failing_baseline=["brain_ui_exists"])
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        _run(ae.synthesize_chat_product_contract())

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_strategy_notes", [])
        assert notes[-1]["result"] == "contract_needs_work"
        assert "brain_ui_exists" in notes[-1]["detail"]

    def test_appends_meta_execution(self, isolated_base_path, monkeypatch):
        """Should append to meta execution ledger."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        import brain_v9.brain.meta_improvement as mi
        ledger_path = isolated_base_path / "tmp_agent" / "state" / "brain_meta_execution_ledger.json"
        monkeypatch.setattr(mi, "FILES", {**mi.FILES, "execution_ledger": ledger_path})

        status = _make_chat_status(accepted=True, quality_score=0.9)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        _run(ae.synthesize_chat_product_contract())

        ledger = _read_json(ledger_path)
        entries = ledger.get("entries", [])
        assert len(entries) >= 1
        last = entries[-1]
        assert last["action"] == "synthesize_chat_product_contract"
        assert last["accepted_baseline"] is True
        assert last["quality_score"] == 0.9


# ========================================================================
# P5-13: improve_chat_product_quality
# ========================================================================
class TestImproveChatQualityRegistered:

    def test_in_action_map(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        assert "improve_chat_product_quality" in ae.ACTION_MAP
        assert ae.ACTION_MAP["improve_chat_product_quality"] is ae.improve_chat_product_quality


class TestImproveChatQualitySuccess:

    def test_success_when_accepted_no_regression(self, isolated_base_path, monkeypatch):
        """success=True when baseline accepted and quality not regressed."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        # Write "previous" status to state dir for regression comparison
        prev_status = _make_chat_status(accepted=True, quality_score=0.8)
        _write_json(ae.STATE_PATH / "chat_product_status_latest.json", prev_status)

        current_status = _make_chat_status(accepted=True, quality_score=0.9)
        _stub_refreshes(monkeypatch, ae, chat_status=current_status)

        result = _run(ae.improve_chat_product_quality())

        assert result["success"] is True
        assert result["quality_score"] == 0.9
        assert result["previous_quality_score"] == 0.8
        assert result["quality_delta"] == pytest.approx(0.1, abs=0.001)
        assert result["regressed"] is False

    def test_result_structure(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        _write_json(ae.STATE_PATH / "chat_product_status_latest.json",
                     _make_chat_status(accepted=True, quality_score=1.0))
        status = _make_chat_status(accepted=True, quality_score=1.0)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        result = _run(ae.improve_chat_product_quality())

        assert result["action_name"] == "improve_chat_product_quality"
        assert result["mode"] == "meta_governance"
        assert result["paper_only_enforced"] is True
        assert "improvement_recommendations" in result
        assert "llm_recommendations" in result
        assert "quality_delta" in result
        assert "regressed" in result


class TestImproveChatQualityRegression:

    def test_failure_on_quality_regression(self, isolated_base_path, monkeypatch):
        """success=False when quality_score drops by more than 1%."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        prev_status = _make_chat_status(accepted=True, quality_score=0.9)
        _write_json(ae.STATE_PATH / "chat_product_status_latest.json", prev_status)

        current_status = _make_chat_status(accepted=True, quality_score=0.7)
        _stub_refreshes(monkeypatch, ae, chat_status=current_status)

        result = _run(ae.improve_chat_product_quality())

        assert result["success"] is False
        assert result["regressed"] is True
        assert result["quality_delta"] == pytest.approx(-0.2, abs=0.001)

    def test_failure_when_baseline_not_accepted(self, isolated_base_path, monkeypatch):
        """success=False when baseline is not accepted, even if quality is high."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        _write_json(ae.STATE_PATH / "chat_product_status_latest.json",
                     _make_chat_status(accepted=False, quality_score=0.5))

        current_status = _make_chat_status(accepted=False, quality_score=0.5)
        _stub_refreshes(monkeypatch, ae, chat_status=current_status)

        result = _run(ae.improve_chat_product_quality())

        assert result["success"] is False


class TestImproveChatQualityRecommendations:

    def test_improvement_recs_for_failing_checks(self, isolated_base_path, monkeypatch):
        """Should build recs for failing quality checks."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        _write_json(ae.STATE_PATH / "chat_product_status_latest.json",
                     _make_chat_status(accepted=True, quality_score=0.5))

        status = _make_chat_status(
            accepted=True, quality_score=0.5,
            failing_quality=["ui_has_model_selector", "memory_persists_short_and_long_term"],
        )
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        result = _run(ae.improve_chat_product_quality())

        recs = result["improvement_recommendations"]
        rec_ids = {r["check_id"] for r in recs}
        assert "ui_has_model_selector" in rec_ids
        assert "memory_persists_short_and_long_term" in rec_ids

    def test_llm_recs_when_session_features_missing(self, isolated_base_path, monkeypatch):
        """Should recommend LLM config changes when runtime features are missing."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        _write_json(ae.STATE_PATH / "chat_product_status_latest.json",
                     _make_chat_status(accepted=True, quality_score=1.0))

        # Write telemetry with missing runtime features
        _write_json(ae.STATE_PATH / "chat_product_telemetry_latest.json", {
            "runtime_features": {
                "session_memory_manager": False,
                "response_normalization": False,
            },
        })

        status = _make_chat_status(accepted=True, quality_score=1.0)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        result = _run(ae.improve_chat_product_quality())

        assert len(result["llm_recommendations"]) >= 2
        combined = " ".join(result["llm_recommendations"])
        assert "MemoryManager" in combined
        assert "normalization" in combined

    def test_no_previous_status_means_zero_baseline(self, isolated_base_path, monkeypatch):
        """When no previous status file exists, previous_quality=0."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        # Don't write any previous status

        status = _make_chat_status(accepted=True, quality_score=0.8)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        result = _run(ae.improve_chat_product_quality())

        assert result["previous_quality_score"] == 0.0
        assert result["quality_delta"] == pytest.approx(0.8, abs=0.001)
        assert result["success"] is True


class TestImproveChatQualityAudit:

    def test_logs_to_scorecard(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        _write_json(ae.STATE_PATH / "chat_product_status_latest.json",
                     _make_chat_status(accepted=True, quality_score=0.8))

        status = _make_chat_status(accepted=True, quality_score=0.9)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        _run(ae.improve_chat_product_quality())

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_strategy_notes", [])
        assert len(notes) >= 1
        assert notes[-1]["action"] == "improve_chat_product_quality"
        assert notes[-1]["result"] == "quality_improved"

    def test_logs_regression_to_scorecard(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        _write_json(ae.STATE_PATH / "chat_product_status_latest.json",
                     _make_chat_status(accepted=True, quality_score=0.9))

        status = _make_chat_status(accepted=True, quality_score=0.5)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        _run(ae.improve_chat_product_quality())

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_strategy_notes", [])
        assert notes[-1]["result"] == "quality_regressed"

    def test_logs_stable_to_scorecard(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        _write_json(ae.STATE_PATH / "chat_product_status_latest.json",
                     _make_chat_status(accepted=True, quality_score=1.0))

        status = _make_chat_status(accepted=True, quality_score=1.0)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        _run(ae.improve_chat_product_quality())

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_strategy_notes", [])
        assert notes[-1]["result"] == "quality_stable"

    def test_appends_meta_execution(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        import brain_v9.brain.meta_improvement as mi
        ledger_path = isolated_base_path / "tmp_agent" / "state" / "brain_meta_execution_ledger.json"
        monkeypatch.setattr(mi, "FILES", {**mi.FILES, "execution_ledger": ledger_path})

        _write_json(ae.STATE_PATH / "chat_product_status_latest.json",
                     _make_chat_status(accepted=True, quality_score=0.8))
        status = _make_chat_status(accepted=True, quality_score=0.9)
        _stub_refreshes(monkeypatch, ae, chat_status=status)

        _run(ae.improve_chat_product_quality())

        ledger = _read_json(ledger_path)
        entries = ledger.get("entries", [])
        assert len(entries) >= 1
        last = entries[-1]
        assert last["action"] == "improve_chat_product_quality"
        assert last["quality_delta"] == pytest.approx(0.1, abs=0.001)
        assert last["regressed"] is False


# ========================================================================
# P5-14: synthesize_utility_governance_contract
# ========================================================================
class TestSynthesizeUtilityContractRegistered:

    def test_in_action_map(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        assert "synthesize_utility_governance_contract" in ae.ACTION_MAP
        assert ae.ACTION_MAP["synthesize_utility_governance_contract"] is ae.synthesize_utility_governance_contract


class TestSynthesizeUtilityContractAccepted:

    def test_success_when_baseline_accepted(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(accepted=True, u_proxy_score=0.75, verdict="promote")
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        result = _run(ae.synthesize_utility_governance_contract())

        assert result["success"] is True
        assert result["accepted_baseline"] is True
        assert result["failed_check_count"] == 0
        assert result["repair_plan"] == []

    def test_result_structure(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(accepted=True, u_proxy_score=0.6, verdict="hold")
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        result = _run(ae.synthesize_utility_governance_contract())

        assert result["action_name"] == "synthesize_utility_governance_contract"
        assert result["mode"] == "meta_governance"
        assert result["paper_only_enforced"] is True
        assert "repair_plan" in result
        assert "u_proxy_aligned" in result
        assert "alignment_detail" in result
        assert "evidence_paths" in result


class TestSynthesizeUtilityContractFailing:

    def test_failure_when_baseline_not_accepted(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(
            accepted=False,
            failing_checks=["utility_snapshot_exists", "utility_gate_exists"],
        )
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        result = _run(ae.synthesize_utility_governance_contract())

        assert result["success"] is False
        assert result["accepted_baseline"] is False
        assert result["failed_check_count"] == 2
        repair_ids = {r["check_id"] for r in result["repair_plan"]}
        assert "utility_snapshot_exists" in repair_ids
        assert "utility_gate_exists" in repair_ids

    def test_blockers_passed_through(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(
            accepted=False,
            blockers=["no_fresh_data", "insufficient_sample"],
            failing_checks=["utility_snapshot_exists"],
        )
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        result = _run(ae.synthesize_utility_governance_contract())

        assert result["blockers"] == ["no_fresh_data", "insufficient_sample"]


class TestSynthesizeUtilityUProxyAlignment:

    def test_aligned_promote(self, isolated_base_path, monkeypatch):
        """u_proxy >= 0.6 with verdict=promote should be aligned."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(accepted=True, u_proxy_score=0.75, verdict="promote")
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        result = _run(ae.synthesize_utility_governance_contract())

        assert result["u_proxy_aligned"] is True
        assert "aligned" in result["alignment_detail"]

    def test_aligned_hold(self, isolated_base_path, monkeypatch):
        """u_proxy in [0.3, 0.6) with verdict=hold should be aligned."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(accepted=True, u_proxy_score=0.45, verdict="hold")
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        result = _run(ae.synthesize_utility_governance_contract())

        assert result["u_proxy_aligned"] is True

    def test_aligned_weak(self, isolated_base_path, monkeypatch):
        """u_proxy < 0.3 with no verdict should be aligned."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(accepted=True, u_proxy_score=0.1, verdict=None)
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        result = _run(ae.synthesize_utility_governance_contract())

        assert result["u_proxy_aligned"] is True

    def test_misaligned(self, isolated_base_path, monkeypatch):
        """u_proxy=0.2 with verdict=promote should be misaligned."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(accepted=True, u_proxy_score=0.2, verdict="promote")
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        result = _run(ae.synthesize_utility_governance_contract())

        assert result["u_proxy_aligned"] is False
        assert "misalignment" in result["alignment_detail"]

    def test_no_score_available(self, isolated_base_path, monkeypatch):
        """When u_proxy_score is None, alignment should be 'no_score_available'."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(accepted=True, u_proxy_score=None, verdict=None)
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        result = _run(ae.synthesize_utility_governance_contract())

        assert result["u_proxy_aligned"] is False
        assert result["alignment_detail"] == "no_score_available"


class TestSynthesizeUtilityContractAudit:

    def test_logs_to_scorecard(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(accepted=True, u_proxy_score=0.7, verdict="hold")
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        _run(ae.synthesize_utility_governance_contract())

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_strategy_notes", [])
        assert len(notes) >= 1
        assert notes[-1]["action"] == "synthesize_utility_governance_contract"
        assert notes[-1]["result"] == "contract_accepted"

    def test_logs_failure_to_scorecard(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        status = _make_utility_status(
            accepted=False, failing_checks=["main_exposes_utility_route"],
        )
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        _run(ae.synthesize_utility_governance_contract())

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_strategy_notes", [])
        assert notes[-1]["result"] == "contract_needs_work"
        assert "main_exposes_utility_route" in notes[-1]["detail"]

    def test_appends_meta_execution(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        import brain_v9.brain.meta_improvement as mi
        ledger_path = isolated_base_path / "tmp_agent" / "state" / "brain_meta_execution_ledger.json"
        monkeypatch.setattr(mi, "FILES", {**mi.FILES, "execution_ledger": ledger_path})

        status = _make_utility_status(accepted=True, u_proxy_score=0.65, verdict="promote")
        _stub_refreshes(monkeypatch, ae, utility_status=status)

        _run(ae.synthesize_utility_governance_contract())

        ledger = _read_json(ledger_path)
        entries = ledger.get("entries", [])
        assert len(entries) >= 1
        last = entries[-1]
        assert last["action"] == "synthesize_utility_governance_contract"
        assert last["accepted_baseline"] is True
        assert last["u_proxy_aligned"] is True


# ========================================================================
# Cross-cutting: ACTION_MAP completeness
# ========================================================================
class TestActionMapStillComplete:

    def test_action_map_still_has_12_entries(self, isolated_base_path, monkeypatch):
        """ACTION_MAP count should be 12 (11 prior + 1 P8 break_system_deadlock)."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        assert len(ae.ACTION_MAP) == 12
