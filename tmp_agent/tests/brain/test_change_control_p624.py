import json

import brain_v9.brain.change_control as cc


def test_build_change_scorecard_summarizes_entries(tmp_path, monkeypatch):
    changes_root = tmp_path / "changes"
    changes_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cc, "CHANGES_ROOT", changes_root)
    monkeypatch.setattr(cc, "CHANGE_SCORECARD_PATH", tmp_path / "change_scorecard.json")

    ledger = {
        "entries": [
            {
                "change_id": "chg_1",
                "timestamp": "2026-03-27T00:00:00Z",
                "objective": "Improve session routing",
                "files": ["C:\\AI_VAULT\\tmp_agent\\brain_v9\\core\\session.py"],
                "status": "promoted",
                "rollback": False,
                "impact_before": {"u_score": 0.5},
                "impact_after": {"u_score": 0.6},
            },
            {
                "change_id": "chg_2",
                "timestamp": "2026-03-27T01:00:00Z",
                "objective": "Bad runtime change",
                "files": ["C:\\AI_VAULT\\tmp_agent\\brain_v9\\main.py"],
                "status": "rolled_back",
                "rollback": True,
                "impact_before": {"u_score": 0.5},
                "impact_after": {"u_score": 0.2},
            },
        ]
    }
    monkeypatch.setattr(cc, "get_self_improvement_ledger", lambda: ledger)

    chg1 = changes_root / "chg_1"
    chg1.mkdir()
    (chg1 / "metadata.json").write_text(json.dumps({
        "validation": {"checks": {"syntax": {"passed": True}, "imports": {"passed": True}}},
        "impact_before": {"u_score": 0.5},
        "impact_after": {"u_score": 0.6},
        "impact_delta": {"delta_u_score": 0.1},
    }), encoding="utf-8")
    (chg1 / "promotion_result.json").write_text(json.dumps({
        "health_status": "healthy",
        "endpoint_results": [{"endpoint": "/health", "ok": True}],
        "impact_after": {"u_score": 0.6},
    }), encoding="utf-8")

    chg2 = changes_root / "chg_2"
    chg2.mkdir()
    (chg2 / "metadata.json").write_text(json.dumps({
        "validation": {"checks": {"syntax": {"passed": True}, "imports": {"passed": True}}},
        "impact_before": {"u_score": 0.5},
        "impact_after": {"u_score": 0.2},
        "impact_delta": {"delta_u_score": -0.3},
        "rollback": {"timestamp": "2026-03-27T01:10:00Z"},
    }), encoding="utf-8")
    (chg2 / "promotion_result.json").write_text(json.dumps({
        "health_status": "healthy",
        "endpoint_results": [{"endpoint": "metric_check", "ok": False}],
        "impact_after": {"u_score": 0.2},
    }), encoding="utf-8")

    payload = cc.build_change_scorecard()

    assert payload["summary"]["total_changes"] == 2
    assert payload["summary"]["promoted_count"] == 1
    assert payload["summary"]["reverted_count"] == 1
    assert payload["summary"]["rollback_count"] == 1
    assert payload["summary"]["metric_degraded_count"] == 1
