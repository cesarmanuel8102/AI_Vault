import json


def test_build_change_validation_status_from_scorecard(monkeypatch, tmp_path):
    import brain_v9.governance.change_validation as cv

    monkeypatch.setattr(cv, "CHANGE_VALIDATION_STATUS_PATH", tmp_path / "change_validation_status_latest.json")
    monkeypatch.setattr(cv, "get_change_scorecard_latest", lambda: {
        "entries": [
            {
                "change_id": "chg_ok",
                "timestamp": "2026-03-27T20:00:00Z",
                "result": "promoted",
                "rollback_executed": False,
                "stages": {
                    "static_check": {"state": "passed"},
                    "unit_test": {"state": "passed"},
                    "runtime_check": {"state": "passed"},
                    "metric_check": {"state": "passed"},
                },
            }
        ]
    })

    payload = cv.build_change_validation_status(refresh_scorecard=False)

    assert payload["summary"]["total_validations"] == 1
    assert payload["summary"]["passed_count"] == 1
    assert payload["summary"]["apply_gate_ready"] is True
    assert payload["last_validation"]["pipeline_state"] == "passed"


def test_build_governance_health_learning_active(monkeypatch, tmp_path):
    import brain_v9.governance.governance_health as gh

    layer_path = tmp_path / "layer_composition.json"
    layer_path.write_text(json.dumps({
        "layers": {
            "V3": {"name": "control_layer"},
            "V4": {"name": "change_validation"},
            "V5": {"name": "risk_contract"},
            "V6": {"name": "meta_governance"},
            "V7": {"name": "learning_feedback"},
            "V8": {"name": "validated_edge_promotion"},
        },
        "modes": {
            "paper_mode": ["V3", "V4", "V5"],
            "paper_strict": ["V3", "V4", "V5", "V6"],
            "learning_active": ["V3", "V4", "V5", "V6", "V7"],
            "edge_validated": ["V3", "V4", "V5", "V6", "V7", "V8"],
            "frozen": ["V3", "V5"],
        },
    }), encoding="utf-8")

    monkeypatch.setattr(gh, "LAYER_COMPOSITION_PATH", layer_path)
    monkeypatch.setattr(gh, "GOVERNANCE_HEALTH_PATH", tmp_path / "governance_health_latest.json")
    monkeypatch.setattr(gh, "SESSION_MEMORY_PATH", tmp_path / "session_memory.json")
    monkeypatch.setattr(gh, "write_utility_snapshots", lambda: {"snapshot": {"u_score": -0.15}})
    monkeypatch.setattr(gh, "read_utility_state", lambda: {"u_score": -0.15})
    monkeypatch.setattr(gh, "get_control_layer_status_latest", lambda: {"mode": "ACTIVE"})
    monkeypatch.setattr(gh, "build_control_layer_status", lambda refresh_change_scorecard=True: {"mode": "ACTIVE"})
    monkeypatch.setattr(gh, "get_meta_governance_status_latest", lambda: {"top_priority": {"action": "increase_resolved_sample"}})
    monkeypatch.setattr(gh, "build_meta_governance_status", lambda: {"top_priority": {"action": "increase_resolved_sample"}})
    monkeypatch.setattr(gh, "read_risk_contract_status", lambda: {"status": "degraded", "execution_allowed": True})
    monkeypatch.setattr(gh, "build_risk_contract_status", lambda refresh=True: {"status": "degraded", "execution_allowed": True})
    monkeypatch.setattr(gh, "read_edge_validation_state", lambda: {"summary": {"validated_count": 0, "promotable_count": 0, "probation_count": 2}})
    monkeypatch.setattr(gh, "read_post_trade_hypothesis_snapshot", lambda: {"summary": {"recent_resolved_trades": 3, "next_focus": "continue_probation"}})
    monkeypatch.setattr(gh, "read_change_validation_status", lambda: {"summary": {"last_run_utc": "2026-03-27T20:00:00Z", "last_pipeline_state": "passed"}})
    monkeypatch.setattr(gh, "build_change_validation_status", lambda refresh_scorecard=True: {"summary": {"last_run_utc": "2026-03-27T20:00:00Z", "last_pipeline_state": "passed"}})
    monkeypatch.setattr(gh, "get_self_improvement_ledger", lambda: {"entries": [{"timestamp": "2026-03-27T20:00:00Z", "rollback": True}]})
    (tmp_path / "session_memory.json").write_text(json.dumps({"current_focus": "increase_resolved_sample"}), encoding="utf-8")

    payload = gh.build_governance_health(refresh=False)

    assert payload["current_operating_mode"] == "learning_active"
    assert payload["layer_composition"]["active_layers"] == ["V3", "V4", "V5", "V6", "V7"]
    assert payload["layers"]["V7"]["state"] == "active"
    assert payload["rollbacks_last_7d"] == 1


def test_build_governance_health_frozen(monkeypatch, tmp_path):
    import brain_v9.governance.governance_health as gh

    layer_path = tmp_path / "layer_composition.json"
    layer_path.write_text(json.dumps({
        "layers": {"V3": {"name": "control_layer"}, "V5": {"name": "risk_contract"}},
        "modes": {"frozen": ["V3", "V5"]},
    }), encoding="utf-8")

    monkeypatch.setattr(gh, "LAYER_COMPOSITION_PATH", layer_path)
    monkeypatch.setattr(gh, "GOVERNANCE_HEALTH_PATH", tmp_path / "governance_health_latest.json")
    monkeypatch.setattr(gh, "SESSION_MEMORY_PATH", tmp_path / "session_memory.json")
    monkeypatch.setattr(gh, "write_utility_snapshots", lambda: {"snapshot": {"u_score": -1.0}})
    monkeypatch.setattr(gh, "read_utility_state", lambda: {"u_score": -1.0})
    monkeypatch.setattr(gh, "get_control_layer_status_latest", lambda: {"mode": "FROZEN", "reason": "manual_override"})
    monkeypatch.setattr(gh, "build_control_layer_status", lambda refresh_change_scorecard=True: {"mode": "FROZEN", "reason": "manual_override"})
    monkeypatch.setattr(gh, "get_meta_governance_status_latest", lambda: {})
    monkeypatch.setattr(gh, "build_meta_governance_status", lambda: {})
    monkeypatch.setattr(gh, "read_risk_contract_status", lambda: {"status": "critical", "execution_allowed": False})
    monkeypatch.setattr(gh, "build_risk_contract_status", lambda refresh=True: {"status": "critical", "execution_allowed": False})
    monkeypatch.setattr(gh, "read_edge_validation_state", lambda: {"summary": {}})
    monkeypatch.setattr(gh, "read_post_trade_hypothesis_snapshot", lambda: {})
    monkeypatch.setattr(gh, "read_change_validation_status", lambda: {"summary": {}})
    monkeypatch.setattr(gh, "build_change_validation_status", lambda refresh_scorecard=True: {"summary": {}})
    monkeypatch.setattr(gh, "get_self_improvement_ledger", lambda: {"entries": []})
    (tmp_path / "session_memory.json").write_text(json.dumps({}), encoding="utf-8")

    payload = gh.build_governance_health(refresh=False)

    assert payload["overall_status"] == "critical"
    assert payload["current_operating_mode"] == "frozen"
    assert payload["kill_switch"]["active"] is True
