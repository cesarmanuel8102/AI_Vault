import json


def _seed_pipeline_paths(tmp_path):
    root = tmp_path / "state"
    strategy_engine = root / "strategy_engine"
    platforms = root / "platforms"
    strategy_engine.mkdir(parents=True, exist_ok=True)
    platforms.mkdir(parents=True, exist_ok=True)
    return root, strategy_engine, platforms


def test_pipeline_integrity_reports_healthy_when_pipeline_is_consistent(monkeypatch, tmp_path):
    import brain_v9.trading.pipeline_integrity as pi

    root, strategy_engine, platforms = _seed_pipeline_paths(tmp_path)

    monkeypatch.setattr(pi, "PIPELINE_INTEGRITY_PATH", strategy_engine / "pipeline_integrity_latest.json")
    monkeypatch.setattr(pi, "SIGNAL_SNAPSHOT_PATH", strategy_engine / "strategy_signal_snapshot_latest.json")
    monkeypatch.setattr(pi, "PAPER_EXECUTION_LEDGER_PATH", strategy_engine / "signal_paper_execution_ledger.json")
    monkeypatch.setattr(pi, "SCORECARDS_PATH", strategy_engine / "strategy_scorecards.json")
    monkeypatch.setattr(pi, "RANKING_V2_PATH", strategy_engine / "strategy_ranking_v2_latest.json")
    monkeypatch.setattr(pi, "UTILITY_LATEST_PATH", root / "utility_u_latest.json")
    monkeypatch.setattr(pi, "AUTONOMY_NEXT_ACTIONS_PATH", root / "autonomy_next_actions.json")
    monkeypatch.setattr(pi, "PLATFORMS_STATE_PATH", platforms)

    (platforms / "pocket_option_metrics.json").write_text("{}", encoding="utf-8")
    (platforms / "pocket_option_u.json").write_text("{}", encoding="utf-8")
    (platforms / "ibkr_metrics.json").write_text("{}", encoding="utf-8")
    (platforms / "ibkr_u.json").write_text("{}", encoding="utf-8")
    (platforms / "internal_paper_metrics.json").write_text("{}", encoding="utf-8")
    (platforms / "internal_paper_u.json").write_text("{}", encoding="utf-8")

    (strategy_engine / "strategy_signal_snapshot_latest.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-03-27T20:00:00Z",
                "items": [
                    {
                        "strategy_id": "po_reversion_v1",
                        "symbol": "AUDNZD_otc",
                        "execution_ready": True,
                        "is_stale": False,
                        "blockers": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (strategy_engine / "signal_paper_execution_ledger.json").write_text(
        json.dumps(
            {
                "updated_utc": "2026-03-27T20:00:02Z",
                "entries": [
                    {
                        "timestamp": "2026-03-27T20:00:01Z",
                        "resolved_utc": "2026-03-27T20:00:02Z",
                        "strategy_id": "po_reversion_v1",
                        "symbol": "AUDNZD_otc",
                        "direction": "put",
                        "result": "win",
                        "resolved": True,
                        "venue": "pocket_option",
                        "timeframe": "1m",
                        "setup_variant": "base",
                        "paper_shadow": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (strategy_engine / "strategy_scorecards.json").write_text(
        json.dumps(
            {
                "updated_utc": "2026-03-27T20:00:03Z",
                "scorecards": {
                    "po_reversion_v1": {
                        "strategy_id": "po_reversion_v1",
                        "venue": "pocket_option",
                        "entries_taken": 1,
                        "entries_resolved": 1,
                        "entries_open": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (strategy_engine / "strategy_ranking_v2_latest.json").write_text(
        json.dumps({"top_action": "increase_resolved_sample"}),
        encoding="utf-8",
    )
    (root / "utility_u_latest.json").write_text(
        json.dumps({"updated_utc": "2026-03-27T20:00:04Z", "u_score": -0.15}),
        encoding="utf-8",
    )
    (root / "autonomy_next_actions.json").write_text(
        json.dumps({"updated_utc": "2026-03-27T20:00:05Z", "top_action": "increase_resolved_sample", "current_focus": {"action": "increase_resolved_sample"}}),
        encoding="utf-8",
    )

    payload = pi.build_pipeline_integrity_snapshot()

    assert payload["summary"]["status"] == "healthy"
    assert payload["summary"]["pipeline_ok"] is True
    assert payload["summary"]["resolved_entries"] == 1
    assert payload["summary"]["platform_isolation_ok"] is True
    assert payload["stages"]["scorecard"]["ok"] is True
    assert payload["stages"]["decision"]["top_action"] == "increase_resolved_sample"


def test_pipeline_integrity_flags_duplicate_and_mismatch(monkeypatch, tmp_path):
    import brain_v9.trading.pipeline_integrity as pi

    root, strategy_engine, platforms = _seed_pipeline_paths(tmp_path)

    monkeypatch.setattr(pi, "PIPELINE_INTEGRITY_PATH", strategy_engine / "pipeline_integrity_latest.json")
    monkeypatch.setattr(pi, "SIGNAL_SNAPSHOT_PATH", strategy_engine / "strategy_signal_snapshot_latest.json")
    monkeypatch.setattr(pi, "PAPER_EXECUTION_LEDGER_PATH", strategy_engine / "signal_paper_execution_ledger.json")
    monkeypatch.setattr(pi, "SCORECARDS_PATH", strategy_engine / "strategy_scorecards.json")
    monkeypatch.setattr(pi, "RANKING_V2_PATH", strategy_engine / "strategy_ranking_v2_latest.json")
    monkeypatch.setattr(pi, "UTILITY_LATEST_PATH", root / "utility_u_latest.json")
    monkeypatch.setattr(pi, "AUTONOMY_NEXT_ACTIONS_PATH", root / "autonomy_next_actions.json")
    monkeypatch.setattr(pi, "PLATFORMS_STATE_PATH", platforms)

    (strategy_engine / "strategy_signal_snapshot_latest.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-03-27T20:00:00Z",
                "items": [
                    {
                        "strategy_id": "po_reversion_v1",
                        "symbol": "AUDNZD_otc",
                        "execution_ready": False,
                        "is_stale": True,
                        "blockers": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    duplicate_entry = {
        "timestamp": "2026-03-27T20:00:01Z",
        "strategy_id": "po_reversion_v1",
        "symbol": "AUDNZD_otc",
        "direction": "put",
        "result": "pending_resolution",
        "resolved": False,
        "venue": "pocket_option",
        "timeframe": "1m",
        "setup_variant": "base",
    }
    (strategy_engine / "signal_paper_execution_ledger.json").write_text(
        json.dumps({"entries": [duplicate_entry, duplicate_entry]}),
        encoding="utf-8",
    )
    (strategy_engine / "strategy_scorecards.json").write_text(
        json.dumps(
            {
                "updated_utc": "2026-03-27T19:59:59Z",
                "scorecards": {
                    "po_reversion_v1": {
                        "strategy_id": "po_reversion_v1",
                        "venue": "pocket_option",
                        "entries_taken": 0,
                        "entries_resolved": 1,
                        "entries_open": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (strategy_engine / "strategy_ranking_v2_latest.json").write_text(json.dumps({}), encoding="utf-8")
    (root / "utility_u_latest.json").write_text(
        json.dumps({"updated_utc": "2026-03-27T19:59:58Z", "u_score": -0.5}),
        encoding="utf-8",
    )
    (root / "autonomy_next_actions.json").write_text(
        json.dumps({"updated_utc": "2026-03-27T19:59:57Z", "top_action": None}),
        encoding="utf-8",
    )

    payload = pi.build_pipeline_integrity_snapshot()

    assert payload["summary"]["status"] == "critical"
    assert payload["summary"]["pipeline_ok"] is False
    codes = {item["code"] for item in payload["anomalies"]}
    assert "duplicate_trade_detected" in codes
    assert "pending_resolution_mismatch" in codes
    assert "stale_signal_not_marked" in codes


def test_pipeline_integrity_treats_frozen_orphaned_scorecard_history_as_warning(monkeypatch, tmp_path):
    import brain_v9.trading.pipeline_integrity as pi

    root, strategy_engine, platforms = _seed_pipeline_paths(tmp_path)

    monkeypatch.setattr(pi, "PIPELINE_INTEGRITY_PATH", strategy_engine / "pipeline_integrity_latest.json")
    monkeypatch.setattr(pi, "SIGNAL_SNAPSHOT_PATH", strategy_engine / "strategy_signal_snapshot_latest.json")
    monkeypatch.setattr(pi, "PAPER_EXECUTION_LEDGER_PATH", strategy_engine / "signal_paper_execution_ledger.json")
    monkeypatch.setattr(pi, "SCORECARDS_PATH", strategy_engine / "strategy_scorecards.json")
    monkeypatch.setattr(pi, "RANKING_V2_PATH", strategy_engine / "strategy_ranking_v2_latest.json")
    monkeypatch.setattr(pi, "UTILITY_LATEST_PATH", root / "utility_u_latest.json")
    monkeypatch.setattr(pi, "AUTONOMY_NEXT_ACTIONS_PATH", root / "autonomy_next_actions.json")
    monkeypatch.setattr(pi, "PLATFORMS_STATE_PATH", platforms)

    for name in (
        "pocket_option_metrics.json",
        "pocket_option_u.json",
        "ibkr_metrics.json",
        "ibkr_u.json",
        "internal_paper_metrics.json",
        "internal_paper_u.json",
    ):
        (platforms / name).write_text("{}", encoding="utf-8")

    (strategy_engine / "strategy_signal_snapshot_latest.json").write_text(
        json.dumps({"generated_utc": "2026-03-27T20:00:00Z", "items": []}),
        encoding="utf-8",
    )
    (strategy_engine / "signal_paper_execution_ledger.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "timestamp": "2026-03-27T20:00:01Z",
                        "resolved_utc": "2026-03-27T20:00:02Z",
                        "strategy_id": "po_reversion_v1",
                        "symbol": "AUDNZD_otc",
                        "direction": "put",
                        "result": "win",
                        "resolved": True,
                        "venue": "pocket_option",
                        "timeframe": "1m",
                        "setup_variant": "base",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (strategy_engine / "strategy_scorecards.json").write_text(
        json.dumps(
            {
                "updated_utc": "2026-03-27T20:00:03Z",
                "scorecards": {
                    "po_reversion_v1": {
                        "strategy_id": "po_reversion_v1",
                        "venue": "pocket_option",
                        "entries_taken": 1,
                        "entries_resolved": 1,
                        "entries_open": 0,
                        "governance_state": "paper_active",
                    },
                    "ibkr_frozen_v1": {
                        "strategy_id": "ibkr_frozen_v1",
                        "venue": "ibkr",
                        "entries_taken": 5,
                        "entries_resolved": 5,
                        "entries_open": 0,
                        "governance_state": "frozen",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (strategy_engine / "strategy_ranking_v2_latest.json").write_text(
        json.dumps({"top_action": "increase_resolved_sample"}),
        encoding="utf-8",
    )
    (root / "utility_u_latest.json").write_text(
        json.dumps({"updated_utc": "2026-03-27T20:00:04Z", "u_score": -0.15}),
        encoding="utf-8",
    )
    (root / "autonomy_next_actions.json").write_text(
        json.dumps({"updated_utc": "2026-03-27T20:00:05Z", "top_action": "increase_resolved_sample"}),
        encoding="utf-8",
    )

    payload = pi.build_pipeline_integrity_snapshot()

    assert payload["summary"]["status"] == "degraded"
    assert payload["summary"]["pipeline_ok"] is True
    assert payload["summary"]["scorecard_resolved_match"] is True
    assert payload["summary"]["orphaned_scorecard_resolved_total"] == 5
    codes = {item["code"] for item in payload["anomalies"]}
    assert "orphaned_scorecard_history" in codes
