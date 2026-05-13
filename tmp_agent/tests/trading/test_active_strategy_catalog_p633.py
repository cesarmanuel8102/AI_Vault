from __future__ import annotations

from unittest.mock import patch

import pytest

import brain_v9.trading.active_strategy_catalog as ac
import brain_v9.trading.strategy_engine as se


def _strategy(
    strategy_id: str,
    venue: str = "pocket_option",
    family: str = "mean_reversion",
    source_universe: list[str] | None = None,
    auto_generated: bool = False,
) -> dict:
    source_universe = source_universe or (["AUDNZD_otc"] if venue == "pocket_option" else ["SPY", "QQQ", "AAPL"])
    return {
        "strategy_id": strategy_id,
        "venue": venue,
        "family": family,
        "primary_asset_class": "otc_binary" if venue == "pocket_option" else "stocks",
        "asset_classes": ["otc_binary"] if venue == "pocket_option" else ["stocks", "etfs"],
        "timeframes": ["1m"] if venue == "pocket_option" else ["5m", "15m"],
        "universe": list(source_universe),
        "source_universe": list(source_universe),
        "runtime_symbol_locked": venue == "pocket_option",
        "success_criteria": {"min_resolved_trades": 20 if venue == "pocket_option" else 30},
        "paper_only": True,
        "auto_generated": auto_generated,
    }


def _scorecards(**items: dict) -> dict:
    return {"scorecards": items, "symbol_scorecards": {}, "context_scorecards": {}}


def _card(governance_state: str = "paper_candidate", entries_resolved: int = 0, expectancy: float = 0.0) -> dict:
    return {
        "governance_state": governance_state,
        "promotion_state": governance_state,
        "entries_resolved": entries_resolved,
        "sample_quality": 0.0 if entries_resolved <= 0 else round(min(entries_resolved / 30.0, 1.0), 4),
        "expectancy": expectancy,
    }


class TestActiveStrategyCatalog:
    @patch("brain_v9.trading.active_strategy_catalog.write_json")
    def test_archived_and_frozen_negative_are_excluded(self, mock_write):
        strategies = [
            _strategy("archived_po"),
            _strategy("frozen_ibkr", venue="ibkr", family="trend_following"),
            _strategy("probation_po"),
        ]
        cards = _scorecards(
            archived_po=_card("frozen", 30, -4.0),
            frozen_ibkr=_card("frozen", 5, -2.0),
            probation_po=_card("paper_probe", 2, -0.5),
        )
        archive = {
            "archived": [{"strategy_id": "archived_po", "archive_state": "archived_refuted"}],
            "active": [],
            "watchlist": [],
            "testing": [],
        }

        payload = ac.build_active_strategy_catalog_snapshot(strategies, cards, archive)
        by_id = {item["strategy_id"]: item for item in payload["items"]}

        assert by_id["archived_po"]["catalog_state"] == "excluded"
        assert by_id["frozen_ibkr"]["catalog_state"] == "excluded"
        assert by_id["probation_po"]["catalog_state"] == "probation"
        assert payload["summary"]["operational_strategy_ids"] == ["probation_po"]

    @patch("brain_v9.trading.active_strategy_catalog.write_json")
    def test_redundant_same_lane_keeps_single_operational_winner(self, mock_write):
        strategies = [
            _strategy("po_probe"),
            _strategy("po_auto", auto_generated=True),
        ]
        cards = _scorecards(
            po_probe=_card("paper_probe", 2, -0.5),
            po_auto=_card("paper_candidate", 0, 0.0),
        )
        archive = {"archived": [], "active": [], "watchlist": [], "testing": []}

        payload = ac.build_active_strategy_catalog_snapshot(strategies, cards, archive)
        by_id = {item["strategy_id"]: item for item in payload["items"]}

        assert by_id["po_probe"]["catalog_state"] == "probation"
        assert by_id["po_probe"]["lane_winner"] is True
        assert by_id["po_auto"]["catalog_state"] == "excluded"
        assert by_id["po_auto"]["catalog_reason"] == "redundant_same_lane"
        assert payload["summary"]["duplicate_excluded_count"] == 1
        assert payload["summary"]["operational_count"] == 1


@pytest.mark.asyncio
async def test_refresh_uses_only_operational_catalog_strategies(monkeypatch):
    keep_strategy = _strategy("keep_me")
    drop_strategy = _strategy("drop_me")

    monkeypatch.setattr(se, "_normalize_strategy_specs", lambda: {"strategies": [keep_strategy, drop_strategy]})
    monkeypatch.setattr(se, "ensure_scorecards", lambda strategies: None)
    monkeypatch.setattr(se, "adapt_strategy_parameters", lambda strategies, cards: strategies)
    monkeypatch.setattr(
        se,
        "read_scorecards",
        lambda: _scorecards(
            keep_me=_card("paper_probe", 2, -0.5),
            drop_me=_card("frozen", 20, -4.0),
        ),
    )
    monkeypatch.setattr(se, "read_json", lambda path, default=None: {"top_action": "increase_resolved_sample"} if path == se.NEXT_ACTIONS_PATH else (default or {}))
    monkeypatch.setattr(se, "_venue_health", lambda: {
        "pocket_option": {"ready": True, "detail": "demo_bridge_live", "paper_order_ready": True},
        "ibkr": {"ready": True, "detail": "marketdata_live", "paper_order_ready": True},
        "internal_paper_simulator": {"ready": True, "detail": "safe_fallback", "paper_order_ready": True},
    })
    monkeypatch.setattr(se, "read_hypothesis_queue", lambda: {"hypotheses": []})
    monkeypatch.setattr(se, "evaluate_hypotheses", lambda hypotheses, scorecards: {"results": []})
    monkeypatch.setattr(
        se,
        "build_strategy_archive",
        lambda strategies, scorecards_payload, hypothesis_payload: {
            "archived": [{"strategy_id": "drop_me", "archive_state": "archived_refuted"}],
            "active": [],
            "watchlist": [],
            "testing": [],
            "summary": {"archived_count": 1, "active_count": 0, "watch_count": 0, "testing_count": 1},
        },
    )

    captured = {"history": None, "signals": None, "candidate_ids": None}

    monkeypatch.setattr(
        se,
        "build_market_history_snapshot",
        lambda strategies: captured.__setitem__("history", [s["strategy_id"] for s in strategies]) or {"symbols": {}, "summary": {}},
    )
    monkeypatch.setattr(se, "build_market_feature_snapshot", lambda: {"items": [], "summary": {}})
    monkeypatch.setattr(se, "resolve_pending_paper_trades", lambda feature_snapshot: None)
    monkeypatch.setattr(
        se,
        "build_strategy_signal_snapshot",
        lambda strategies, feature_snapshot=None: captured.__setitem__("signals", [s["strategy_id"] for s in strategies]) or {"items": [], "by_strategy": [], "signals_count": 0},
    )
    monkeypatch.setattr(
        se,
        "build_expectancy_snapshot",
        lambda: {"by_strategy": {"items": []}, "by_strategy_symbol": {"items": []}, "by_strategy_context": {"items": []}, "summary": {}},
    )
    monkeypatch.setattr(
        se,
        "build_strategy_candidates",
        lambda strategies=None: captured.__setitem__("candidate_ids", [s["strategy_id"] for s in (strategies or [])]) or [
            {"strategy_id": s["strategy_id"], "objective": "", "success_metric": ""}
            for s in (strategies or [])
        ],
    )
    monkeypatch.setattr(
        se,
        "build_context_edge_validation_snapshot",
        lambda candidates: {"summary": {}, "items": [
            {
                "strategy_id": c["strategy_id"],
                "current_context_edge_state": "blocked",
                "current_context_execution_allowed": False,
            }
            for c in candidates
        ]},
    )
    monkeypatch.setattr(
        se,
        "build_edge_validation_snapshot",
        lambda ranked: {"summary": {}, "items": [
            {
                "strategy_id": r["strategy_id"],
                "edge_state": "probation",
                "execution_lane": "watch",
                "forward_validated": False,
                "validated": False,
                "promotable": False,
                "best_entries_resolved": 0,
                "best_sample_quality": 0.0,
                "effective_expectancy": 0.0,
                "signal_confidence": 0.0,
                "drawdown_penalty": 0.0,
                "probation_budget": 0,
                "signal_ready": False,
                "governance_ready": True,
                "execution_ready_now": False,
                "blockers": [],
                "thresholds": {},
            }
            for r in ranked
        ]},
    )
    monkeypatch.setattr(se, "build_ranking", lambda candidates, top_action: candidates)
    monkeypatch.setattr(se, "choose_top_candidate", lambda ranked, allow_frozen=False: None)
    monkeypatch.setattr(se, "choose_recovery_candidate", lambda ranked: None)
    monkeypatch.setattr(se, "choose_exploit_candidate", lambda ranked: None)
    monkeypatch.setattr(se, "choose_explore_candidate", lambda ranked, exclude_strategy_id=None: None)
    monkeypatch.setattr(se, "choose_probation_candidate", lambda ranked, exclude_strategy_id=None: None)
    monkeypatch.setattr(se, "build_pipeline_integrity_snapshot", lambda: {"summary": {}})
    monkeypatch.setattr(se, "_append_report", lambda event: None)
    monkeypatch.setattr(se, "write_json", lambda path, payload: None)

    import brain_v9.brain.utility as utility_mod
    monkeypatch.setattr(utility_mod, "write_utility_snapshots", lambda: {})

    result = se.refresh_strategy_engine()

    assert captured["history"] == ["keep_me"]
    assert captured["signals"] == ["keep_me"]
    assert captured["candidate_ids"] == ["keep_me"]
    assert result["summary"]["active_catalog_summary"]["operational_count"] == 1
    assert result["summary"]["active_catalog_summary"]["excluded_count"] >= 1
