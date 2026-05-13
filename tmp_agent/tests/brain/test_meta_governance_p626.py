import json


def _seed_common(tmp_path):
    (tmp_path / "strategy_engine").mkdir(parents=True, exist_ok=True)
    utility_snapshot = {
        "u_score": -0.25,
        "u_proxy_score": -0.25,
        "components": {"drawdown_penalty": 0.2},
        "sample": {"entries_resolved": 6},
        "strategy_context": {"reference_strategy": {"best_entries_resolved": 6, "best_sample_quality": 0.12}},
    }
    utility_gate = {
        "verdict": "no_promote",
        "blockers": ["sample_not_ready", "no_validated_edge"],
        "required_next_actions": [
            "improve_expectancy_or_reduce_penalties",
            "increase_resolved_sample",
            "select_and_compare_strategies",
        ],
    }
    edge = {
        "summary": {
            "validated_count": 0,
            "promotable_count": 0,
            "probation_count": 1,
            "blocked_count": 2,
            "refuted_count": 0,
        }
    }
    ranking = {"summary": {"top_strategy_id": None}}
    cycle = {"cycle_count": 12}
    control = {"mode": "ACTIVE", "execution_allowed": True}
    post_trade = {"summary": {"recent_resolved_trades": 3}}
    return utility_snapshot, utility_gate, edge, ranking, cycle, control, post_trade


def test_meta_governance_prioritizes_sample_over_optimization(monkeypatch, tmp_path):
    import brain_v9.brain.meta_governance as mg

    utility_snapshot, utility_gate, edge, ranking, cycle, control, post_trade = _seed_common(tmp_path)
    monkeypatch.setattr(mg, "STATE_PATH", tmp_path)
    monkeypatch.setattr(mg, "META_GOVERNANCE_STATUS_PATH", tmp_path / "meta_governance_status_latest.json")
    monkeypatch.setattr(mg, "EDGE_VALIDATION_PATH", tmp_path / "strategy_engine" / "edge_validation_latest.json")
    monkeypatch.setattr(mg, "RANKING_V2_PATH", tmp_path / "strategy_engine" / "strategy_ranking_v2_latest.json")
    monkeypatch.setattr(mg, "AUTONOMY_CYCLE_LATEST_PATH", tmp_path / "autonomy_cycle_latest.json")
    monkeypatch.setattr(mg, "CONTROL_LAYER_STATUS_PATH", tmp_path / "control_layer_status.json")
    monkeypatch.setattr(mg, "POST_TRADE_ANALYSIS_PATH", tmp_path / "strategy_engine" / "post_trade_analysis_latest.json")

    (tmp_path / "strategy_engine" / "edge_validation_latest.json").write_text(json.dumps(edge), encoding="utf-8")
    (tmp_path / "strategy_engine" / "strategy_ranking_v2_latest.json").write_text(json.dumps(ranking), encoding="utf-8")
    (tmp_path / "autonomy_cycle_latest.json").write_text(json.dumps(cycle), encoding="utf-8")
    (tmp_path / "control_layer_status.json").write_text(json.dumps(control), encoding="utf-8")
    (tmp_path / "strategy_engine" / "post_trade_analysis_latest.json").write_text(json.dumps(post_trade), encoding="utf-8")

    payload = mg.build_meta_governance_status(
        utility_snapshot=utility_snapshot,
        utility_gate=utility_gate,
        raw_next_actions={
            "recommended_actions": utility_gate["required_next_actions"],
            "top_action": "improve_expectancy_or_reduce_penalties",
            "consecutive_skips": 0,
        },
    )

    assert payload["top_action"] == "increase_resolved_sample"
    assert payload["discipline"]["optimization_allowed"] is False
    assert "resolved_sample_below_15" in payload["discipline"]["optimize_blockers"]


def test_meta_governance_respects_focus_lock(monkeypatch, tmp_path):
    import brain_v9.brain.meta_governance as mg

    utility_snapshot, utility_gate, edge, ranking, _, control, post_trade = _seed_common(tmp_path)
    utility_snapshot["sample"]["entries_resolved"] = 20
    utility_snapshot["strategy_context"]["reference_strategy"]["best_entries_resolved"] = 20
    utility_snapshot["strategy_context"]["reference_strategy"]["best_sample_quality"] = 0.5
    utility_gate["blockers"] = ["no_validated_edge"]

    monkeypatch.setattr(mg, "STATE_PATH", tmp_path)
    monkeypatch.setattr(mg, "META_GOVERNANCE_STATUS_PATH", tmp_path / "meta_governance_status_latest.json")
    monkeypatch.setattr(mg, "EDGE_VALIDATION_PATH", tmp_path / "strategy_engine" / "edge_validation_latest.json")
    monkeypatch.setattr(mg, "RANKING_V2_PATH", tmp_path / "strategy_engine" / "strategy_ranking_v2_latest.json")
    monkeypatch.setattr(mg, "AUTONOMY_CYCLE_LATEST_PATH", tmp_path / "autonomy_cycle_latest.json")
    monkeypatch.setattr(mg, "CONTROL_LAYER_STATUS_PATH", tmp_path / "control_layer_status.json")
    monkeypatch.setattr(mg, "POST_TRADE_ANALYSIS_PATH", tmp_path / "strategy_engine" / "post_trade_analysis_latest.json")

    (tmp_path / "strategy_engine" / "edge_validation_latest.json").write_text(json.dumps(edge), encoding="utf-8")
    (tmp_path / "strategy_engine" / "strategy_ranking_v2_latest.json").write_text(json.dumps(ranking), encoding="utf-8")
    (tmp_path / "autonomy_cycle_latest.json").write_text(json.dumps({"cycle_count": 20}), encoding="utf-8")
    (tmp_path / "control_layer_status.json").write_text(json.dumps(control), encoding="utf-8")
    (tmp_path / "strategy_engine" / "post_trade_analysis_latest.json").write_text(json.dumps(post_trade), encoding="utf-8")
    (tmp_path / "meta_governance_status_latest.json").write_text(json.dumps({
        "current_focus": {
            "action": "select_and_compare_strategies",
            "last_focus_change_cycle": 15,
            "focus_started_cycle": 15,
        }
    }), encoding="utf-8")

    payload = mg.build_meta_governance_status(
        utility_snapshot=utility_snapshot,
        utility_gate=utility_gate,
        raw_next_actions={
            "recommended_actions": [
                "increase_resolved_sample",
                "select_and_compare_strategies",
            ],
            "top_action": "increase_resolved_sample",
        },
    )

    assert payload["top_action"] == "select_and_compare_strategies"
    assert payload["current_focus"]["focus_lock_active"] is True
    assert payload["current_focus"]["focus_switch_allowed"] is False


def test_meta_governance_forces_minimum_action_after_skips(monkeypatch, tmp_path):
    import brain_v9.brain.meta_governance as mg

    utility_snapshot, utility_gate, edge, ranking, cycle, control, post_trade = _seed_common(tmp_path)
    monkeypatch.setattr(mg, "STATE_PATH", tmp_path)
    monkeypatch.setattr(mg, "META_GOVERNANCE_STATUS_PATH", tmp_path / "meta_governance_status_latest.json")
    monkeypatch.setattr(mg, "EDGE_VALIDATION_PATH", tmp_path / "strategy_engine" / "edge_validation_latest.json")
    monkeypatch.setattr(mg, "RANKING_V2_PATH", tmp_path / "strategy_engine" / "strategy_ranking_v2_latest.json")
    monkeypatch.setattr(mg, "AUTONOMY_CYCLE_LATEST_PATH", tmp_path / "autonomy_cycle_latest.json")
    monkeypatch.setattr(mg, "CONTROL_LAYER_STATUS_PATH", tmp_path / "control_layer_status.json")
    monkeypatch.setattr(mg, "POST_TRADE_ANALYSIS_PATH", tmp_path / "strategy_engine" / "post_trade_analysis_latest.json")

    (tmp_path / "strategy_engine" / "edge_validation_latest.json").write_text(json.dumps(edge), encoding="utf-8")
    (tmp_path / "strategy_engine" / "strategy_ranking_v2_latest.json").write_text(json.dumps(ranking), encoding="utf-8")
    (tmp_path / "autonomy_cycle_latest.json").write_text(json.dumps(cycle), encoding="utf-8")
    (tmp_path / "control_layer_status.json").write_text(json.dumps(control), encoding="utf-8")
    (tmp_path / "strategy_engine" / "post_trade_analysis_latest.json").write_text(json.dumps(post_trade), encoding="utf-8")

    payload = mg.build_meta_governance_status(
        utility_snapshot=utility_snapshot,
        utility_gate=utility_gate,
        raw_next_actions={
            "recommended_actions": [
                "select_and_compare_strategies",
                "increase_resolved_sample",
            ],
            "top_action": "select_and_compare_strategies",
            "consecutive_skips": 3,
        },
    )

    assert payload["top_action"] == "increase_resolved_sample"
    assert payload["current_focus"]["forced_minimum_action"] is True
