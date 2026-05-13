import json

import pytest

from brain_v9.core.state_io import read_json, write_json


def _seed_cycle_inputs(am, tmp_path):
    write_json(tmp_path / "utility_u_latest.json", {
        "u_score": -0.25,
        "governance_u_score": 0.1,
        "real_venue_u_score": -0.25,
        "verdict": "no_promote",
        "blockers": ["sample_not_ready"],
    })
    write_json(tmp_path / "edge_validation_latest.json", {
        "summary": {
            "validated_count": 0,
            "promotable_count": 0,
            "probation_count": 2,
            "blocked_count": 1,
            "refuted_count": 0,
        }
    })
    write_json(tmp_path / "strategy_ranking_v2_latest.json", {
        "summary": {
            "top_strategy_id": None,
            "top_action": "increase_resolved_sample",
            "exploit_candidate_id": None,
            "probation_candidate_id": "po_otc_reversion_probe_v1",
        }
    })
    write_json(tmp_path / "autonomy_skip_state.json", {"consecutive_skips": 3})
    write_json(tmp_path / "post_trade_analysis_latest.json", {"summary": {"recent_trades_count": 4}})
    write_json(tmp_path / "post_trade_hypotheses_latest.json", {"summary": {"hypotheses_count": 2}})
    write_json(tmp_path / "autonomy_action_ledger.json", {"items": [{"action": "increase_resolved_sample"}]})

    am.UTILITY_LATEST_PATH = tmp_path / "utility_u_latest.json"
    am.EDGE_VALIDATION_LATEST_PATH = tmp_path / "edge_validation_latest.json"
    am.RANKING_V2_LATEST_PATH = tmp_path / "strategy_ranking_v2_latest.json"
    am.AUTONOMY_SKIP_STATE_PATH = tmp_path / "autonomy_skip_state.json"
    am.POST_TRADE_ANALYSIS_LATEST_PATH = tmp_path / "post_trade_analysis_latest.json"
    am.POST_TRADE_HYPOTHESES_LATEST_PATH = tmp_path / "post_trade_hypotheses_latest.json"
    am.AUTONOMY_ACTION_LEDGER_PATH = tmp_path / "autonomy_action_ledger.json"


def test_initial_status_exposes_cycle_fields():
    from brain_v9.autonomy.manager import AutonomyManager

    mgr = AutonomyManager()
    status = mgr.get_status()

    assert status["cycle_count"] >= 0
    assert "last_cycle_utc" in status
    assert status["current_cycle_stage"] in {"idle", "detect", "plan", "execute", "verify", "evaluate", "improve", "log", "done"}


def test_cycle_snapshot_persists_and_logs(monkeypatch, tmp_path):
    import brain_v9.autonomy.manager as am

    cycle_path = tmp_path / "autonomy_cycle_latest.json"
    events_path = tmp_path / "agent_events.ndjson"
    monkeypatch.setattr(am, "AUTONOMY_CYCLE_LATEST_PATH", cycle_path)
    monkeypatch.setattr(am, "AGENT_EVENTS_LOG_PATH", events_path)
    _seed_cycle_inputs(am, tmp_path)

    mgr = am.AutonomyManager()
    cycle = mgr._build_cycle_snapshot(
        {"required_next_actions": ["increase_resolved_sample"], "allow_promote": False, "verdict": "no_promote", "blockers": []},
        {"u_proxy_score": -0.25},
    )
    mgr._persist_cycle_snapshot(cycle)
    finalized = mgr._finalize_cycle_snapshot(
        cycle,
        actions_results=[{"action": "increase_resolved_sample", "status": "success"}],
        result="success",
    )

    stored = read_json(cycle_path, {})
    assert stored["cycle_id"] == finalized["cycle_id"]
    assert stored["result"] == "success"
    assert stored["metrics_after"]["probation_count"] == 2

    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "autonomy_cycle_completed"
    assert event["result"] == "success"


@pytest.mark.asyncio
async def test_run_action_appends_structured_event(monkeypatch, tmp_path):
    import brain_v9.autonomy.manager as am

    cycle_path = tmp_path / "autonomy_cycle_latest.json"
    events_path = tmp_path / "agent_events.ndjson"
    monkeypatch.setattr(am, "AUTONOMY_CYCLE_LATEST_PATH", cycle_path)
    monkeypatch.setattr(am, "AGENT_EVENTS_LOG_PATH", events_path)
    _seed_cycle_inputs(am, tmp_path)

    async def _fake_execute_action(action_name):
        return {"status": "success", "action": action_name}

    monkeypatch.setattr(am, "execute_action", _fake_execute_action)

    mgr = am.AutonomyManager()
    result = await mgr._run_action(
        "increase_resolved_sample",
        "trading",
        {"u_proxy_score": -0.25},
        {"cycle_id": "autocycle_000001"},
    )

    assert result["status"] == "success"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "action_executed"
    assert event["action"] == "increase_resolved_sample"
    assert event["cycle_id"] == "autocycle_000001"


@pytest.mark.asyncio
async def test_dispatch_actions_blocked_by_control_layer(monkeypatch, tmp_path):
    import brain_v9.autonomy.manager as am

    cycle_path = tmp_path / "autonomy_cycle_latest.json"
    events_path = tmp_path / "agent_events.ndjson"
    monkeypatch.setattr(am, "AUTONOMY_CYCLE_LATEST_PATH", cycle_path)
    monkeypatch.setattr(am, "AGENT_EVENTS_LOG_PATH", events_path)
    _seed_cycle_inputs(am, tmp_path)
    monkeypatch.setattr(
        am,
        "get_control_layer_status_latest",
        lambda: {"mode": "FROZEN", "reason": "manual_test", "execution_allowed": False},
    )

    mgr = am.AutonomyManager()
    cycle = mgr._build_cycle_snapshot(
        {"required_next_actions": ["increase_resolved_sample"], "allow_promote": False, "verdict": "no_promote", "blockers": []},
        {"u_proxy_score": -0.25},
    )

    result = await mgr._dispatch_actions(
        {"required_next_actions": ["increase_resolved_sample"]},
        {"u_proxy_score": -0.25},
        cycle,
    )

    assert result[0]["status"] == "blocked_control_layer"
    stored = read_json(cycle_path, {})
    assert stored["execution"]["blocked_by_control_layer"]["reason"] == "manual_test"
