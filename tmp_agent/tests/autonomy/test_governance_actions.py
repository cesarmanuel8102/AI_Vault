"""
Tests for P3-11: Governance action implementations.

Verifies:
  - reduce_drawdown_and_capital_at_risk() freezes worst-drawdown strategy
  - rebalance_capital_exposure() resolves pending trades + freezes lowest-ranked
  - Both actions are registered in ACTION_MAP
  - Both actions log to the scorecard
  - Edge cases: no strategies, all frozen, empty ranking
"""
import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


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
    engine = state / "strategy_engine"
    monkeypatch.setattr(ae, "STATE_PATH", state)
    monkeypatch.setattr(ae, "ROOMS_PATH", rooms)
    monkeypatch.setattr(ae, "JOBS_PATH", state / "autonomy_action_jobs")
    monkeypatch.setattr(ae, "JOBS_LEDGER", state / "autonomy_action_ledger.json")
    monkeypatch.setattr(ae, "NEXT_ACTIONS_PATH", state / "autonomy_next_actions.json")
    monkeypatch.setattr(ae, "SCORECARD_PATH",
                        rooms / "brain_binary_paper_pb05_journal" / "session_result_scorecard.json")
    monkeypatch.setattr(ae, "PO_BRIDGE_ARTIFACT",
                        rooms / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json")
    monkeypatch.setattr(ae, "IBKR_LANE_PATH",
                        rooms / "brain_financial_ingestion_fi04_structured_api" / "ibkr_readonly_lane.json")
    monkeypatch.setattr(ae, "IBKR_PROBE_PATH",
                        rooms / "brain_financial_ingestion_fi04_structured_api" / "ibkr_marketdata_probe_status.json")
    monkeypatch.setattr(ae, "IBKR_ORDER_CHECK_PATH",
                        state / "trading_execution_checks" / "ibkr_paper_order_check_latest.json")
    monkeypatch.setattr(ae, "TRADING_POLICY_PATH", state / "trading_autonomy_policy.json")

    (state / "autonomy_action_jobs").mkdir(parents=True, exist_ok=True)
    (rooms / "brain_binary_paper_pb05_journal").mkdir(parents=True, exist_ok=True)
    engine.mkdir(parents=True, exist_ok=True)

    return ae


def _make_ranking_with_drawdown():
    """Ranking with 3 strategies, one has high drawdown."""
    return {
        "schema_version": "strategy_ranking_latest_v2",
        "ranked": [
            {
                "strategy_id": "strat_good",
                "venue": "internal_paper_simulator",
                "governance_state": "paper_active",
                "archive_state": "testing",
                "drawdown_penalty": 0.10,
                "rank_score": 0.85,
            },
            {
                "strategy_id": "strat_medium",
                "venue": "internal_paper_simulator",
                "governance_state": "paper_candidate",
                "archive_state": "testing",
                "drawdown_penalty": 0.40,
                "rank_score": 0.55,
            },
            {
                "strategy_id": "strat_bad_drawdown",
                "venue": "internal_paper_simulator",
                "governance_state": "paper_active",
                "archive_state": "testing",
                "drawdown_penalty": 0.90,
                "rank_score": 0.20,
            },
        ],
        "top_recovery_candidate": {"strategy_id": "strat_good"},
    }


def _make_scorecards_payload():
    """Scorecards for 3 strategies."""
    return {
        "schema_version": "strategy_scorecards_v3",
        "scorecards": {
            "strat_good": {
                "strategy_id": "strat_good",
                "governance_state": "paper_active",
                "promotion_state": "paper_active",
                "freeze_recommended": False,
                "entries_resolved": 15,
            },
            "strat_medium": {
                "strategy_id": "strat_medium",
                "governance_state": "paper_candidate",
                "promotion_state": "paper_candidate",
                "freeze_recommended": False,
                "entries_resolved": 8,
            },
            "strat_bad_drawdown": {
                "strategy_id": "strat_bad_drawdown",
                "governance_state": "paper_active",
                "promotion_state": "paper_active",
                "freeze_recommended": False,
                "entries_resolved": 12,
            },
        },
        "symbol_scorecards": {},
        "context_scorecards": {},
    }


# ===========================================================================
# P3-11a: reduce_drawdown_and_capital_at_risk
# ===========================================================================
class TestReduceDrawdownRegistered:

    def test_action_map_includes_reduce_drawdown(self, isolated_base_path, monkeypatch):
        """reduce_drawdown_and_capital_at_risk should be in ACTION_MAP."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        assert "reduce_drawdown_and_capital_at_risk" in ae.ACTION_MAP
        assert ae.ACTION_MAP["reduce_drawdown_and_capital_at_risk"] is ae.reduce_drawdown_and_capital_at_risk


class TestReduceDrawdownFreezeWorst:

    def test_freezes_worst_drawdown_strategy(self, isolated_base_path, monkeypatch):
        """Should freeze the strategy with the highest drawdown_penalty."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", _make_ranking_with_drawdown)

        # Write scorecards
        from brain_v9.trading.strategy_scorecard import SCORECARDS_PATH
        sc_path = isolated_base_path / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
        _write_json(sc_path, _make_scorecards_payload())
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.SCORECARDS_PATH", sc_path
        )

        result = asyncio.get_event_loop().run_until_complete(
            ae.reduce_drawdown_and_capital_at_risk()
        )

        assert result["success"] is True
        assert result["frozen_strategy_id"] == "strat_bad_drawdown"
        assert result["worst_drawdown_penalty"] == 0.90
        assert result["recovery_candidate_id"] == "strat_good"

        # Verify scorecard was updated
        sc = _read_json(sc_path)
        card = sc["scorecards"]["strat_bad_drawdown"]
        assert card["governance_state"] == "frozen"
        assert card["promotion_state"] == "frozen"
        assert card["freeze_recommended"] is True
        assert "drawdown" in card.get("freeze_reason", "")

    def test_skips_already_frozen_strategies(self, isolated_base_path, monkeypatch):
        """Should not freeze an already-frozen strategy."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})

        ranking = _make_ranking_with_drawdown()
        # Make worst one already frozen
        ranking["ranked"][2]["governance_state"] = "frozen"
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: ranking)

        sc_path = isolated_base_path / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
        _write_json(sc_path, _make_scorecards_payload())
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.SCORECARDS_PATH", sc_path
        )

        result = asyncio.get_event_loop().run_until_complete(
            ae.reduce_drawdown_and_capital_at_risk()
        )

        # Should freeze strat_medium (next worst, dd=0.40)
        assert result["success"] is True
        assert result["frozen_strategy_id"] == "strat_medium"

    def test_no_strategies_to_freeze(self, isolated_base_path, monkeypatch):
        """With empty ranking, should return success=False."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: {"ranked": [], "top_recovery_candidate": {}})

        result = asyncio.get_event_loop().run_until_complete(
            ae.reduce_drawdown_and_capital_at_risk()
        )

        assert result["success"] is False
        assert result["frozen_strategy_id"] is None


class TestReduceDrawdownLogging:

    def test_logs_in_scorecard(self, isolated_base_path, monkeypatch):
        """Action should append a note to scorecard autonomy_strategy_notes."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", _make_ranking_with_drawdown)

        sc_path = isolated_base_path / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
        _write_json(sc_path, _make_scorecards_payload())
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.SCORECARDS_PATH", sc_path
        )

        asyncio.get_event_loop().run_until_complete(
            ae.reduce_drawdown_and_capital_at_risk()
        )

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_strategy_notes", [])
        assert len(notes) >= 1
        latest = notes[-1]
        assert latest["action"] == "reduce_drawdown_and_capital_at_risk"
        assert "strat_bad_drawdown" in latest["detail"]

    def test_result_structure(self, isolated_base_path, monkeypatch):
        """Result should have standard keys."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: {"ranked": [], "top_recovery_candidate": {}})

        result = asyncio.get_event_loop().run_until_complete(
            ae.reduce_drawdown_and_capital_at_risk()
        )

        assert result["action_name"] == "reduce_drawdown_and_capital_at_risk"
        assert result["mode"] == "risk_management"
        assert result["paper_only_enforced"] is True
        assert "strategies_evaluated" in result


# ===========================================================================
# P3-11b: rebalance_capital_exposure
# ===========================================================================
class TestRebalanceCapitalRegistered:

    def test_action_map_includes_rebalance(self, isolated_base_path, monkeypatch):
        """rebalance_capital_exposure should be in ACTION_MAP."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        assert "rebalance_capital_exposure" in ae.ACTION_MAP
        assert ae.ACTION_MAP["rebalance_capital_exposure"] is ae.rebalance_capital_exposure


class TestRebalanceCapitalResolvePending:

    def test_resolves_pending_trades(self, isolated_base_path, monkeypatch):
        """Should call resolve_pending_paper_trades to free capital."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: {"ranked": []})

        resolve_called = {"count": 0}

        def mock_resolve(feature_snap):
            resolve_called["count"] += 1
            return {"resolved": 3, "expired": 0}

        with patch("brain_v9.trading.paper_execution.resolve_pending_paper_trades",
                    mock_resolve), \
             patch("brain_v9.trading.feature_engine.build_market_feature_snapshot",
                    return_value={"items": []}):
            result = asyncio.get_event_loop().run_until_complete(
                ae.rebalance_capital_exposure()
            )

        assert resolve_called["count"] == 1
        assert result["resolved_pending_trades"] == 3


class TestRebalanceCapitalFreezeLowest:

    def test_freezes_lowest_ranked_strategy(self, isolated_base_path, monkeypatch):
        """Should freeze the bottom-ranked non-frozen strategy."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", _make_ranking_with_drawdown)

        sc_path = isolated_base_path / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
        _write_json(sc_path, _make_scorecards_payload())
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.SCORECARDS_PATH", sc_path
        )

        with patch("brain_v9.trading.paper_execution.resolve_pending_paper_trades",
                    return_value={"resolved": 0, "expired": 0}), \
             patch("brain_v9.trading.feature_engine.build_market_feature_snapshot",
                    return_value={"items": []}):
            result = asyncio.get_event_loop().run_until_complete(
                ae.rebalance_capital_exposure()
            )

        assert result["success"] is True
        # The lowest-ranked is strat_bad_drawdown (last in ranking)
        assert result["frozen_strategy_id"] == "strat_bad_drawdown"

        # Verify scorecard was updated
        sc = _read_json(sc_path)
        card = sc["scorecards"]["strat_bad_drawdown"]
        assert card["governance_state"] == "frozen"
        assert "capital_commitment" in card.get("freeze_reason", "")

    def test_skips_frozen_and_archived(self, isolated_base_path, monkeypatch):
        """Should skip frozen and archived strategies when picking lowest-ranked."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})

        ranking = _make_ranking_with_drawdown()
        # Make the worst one frozen and second-worst archived
        ranking["ranked"][2]["governance_state"] = "frozen"
        ranking["ranked"][1]["archive_state"] = "archived_2024"
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: ranking)

        sc_path = isolated_base_path / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
        _write_json(sc_path, _make_scorecards_payload())
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.SCORECARDS_PATH", sc_path
        )

        with patch("brain_v9.trading.paper_execution.resolve_pending_paper_trades",
                    return_value={"resolved": 0, "expired": 0}), \
             patch("brain_v9.trading.feature_engine.build_market_feature_snapshot",
                    return_value={"items": []}):
            result = asyncio.get_event_loop().run_until_complete(
                ae.rebalance_capital_exposure()
            )

        # Should freeze strat_good (only non-frozen, non-archived left)
        assert result["frozen_strategy_id"] == "strat_good"

    def test_no_strategy_to_freeze(self, isolated_base_path, monkeypatch):
        """With all frozen, no strategy should be frozen."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})

        ranking = _make_ranking_with_drawdown()
        for r in ranking["ranked"]:
            r["governance_state"] = "frozen"
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: ranking)

        with patch("brain_v9.trading.paper_execution.resolve_pending_paper_trades",
                    return_value={"resolved": 1, "expired": 0}), \
             patch("brain_v9.trading.feature_engine.build_market_feature_snapshot",
                    return_value={"items": []}):
            result = asyncio.get_event_loop().run_until_complete(
                ae.rebalance_capital_exposure()
            )

        assert result["success"] is True  # Still succeeds (resolved trades)
        assert result["frozen_strategy_id"] is None


class TestRebalanceCapitalLogging:

    def test_logs_in_scorecard(self, isolated_base_path, monkeypatch):
        """Should log rebalance action in scorecard notes."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: {"ranked": []})

        with patch("brain_v9.trading.paper_execution.resolve_pending_paper_trades",
                    return_value={"resolved": 2, "expired": 0}), \
             patch("brain_v9.trading.feature_engine.build_market_feature_snapshot",
                    return_value={"items": []}):
            asyncio.get_event_loop().run_until_complete(
                ae.rebalance_capital_exposure()
            )

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_strategy_notes", [])
        assert len(notes) >= 1
        latest = notes[-1]
        assert latest["action"] == "rebalance_capital_exposure"
        assert "2" in latest["detail"]  # resolved count

    def test_result_structure(self, isolated_base_path, monkeypatch):
        """Result should have standard keys."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: {"ranked": []})

        with patch("brain_v9.trading.paper_execution.resolve_pending_paper_trades",
                    return_value={"resolved": 0, "expired": 0}), \
             patch("brain_v9.trading.feature_engine.build_market_feature_snapshot",
                    return_value={"items": []}):
            result = asyncio.get_event_loop().run_until_complete(
                ae.rebalance_capital_exposure()
            )

        assert result["action_name"] == "rebalance_capital_exposure"
        assert result["mode"] == "capital_management"
        assert result["paper_only_enforced"] is True
        assert "resolved_pending_trades" in result
        assert "frozen_strategy_id" in result
        assert "strategies_evaluated" in result


# ===========================================================================
# P3-11: ACTION_MAP completeness
# ===========================================================================
class TestActionMapComplete:

    def test_all_utility_actions_registered(self, isolated_base_path, monkeypatch):
        """Every action emitted by _compute_components should have a handler."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        # These are all action names emitted by utility._compute_components
        required_actions = [
            "increase_resolved_sample",
            "reduce_drawdown_and_capital_at_risk",
            "rebalance_capital_exposure",
            "improve_signal_capture_and_context_window",
        ]
        for action_name in required_actions:
            assert action_name in ae.ACTION_MAP, \
                f"Action '{action_name}' emitted by utility but not in ACTION_MAP"

    def test_action_map_has_12_entries(self, isolated_base_path, monkeypatch):
        """ACTION_MAP should now have 12 entries (8 original + 2 P3 + 1 P4-11 QC + 1 P8 deadlock)."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        assert len(ae.ACTION_MAP) == 12
