"""Tests for dashboard load performance fix.

Front: FRONT-BRAIN-UI-DASHBOARD-STARTUP-POLLING-THROTTLE-05A
Verifies that the snapshot cache, run limiting, and refresh guard are in place.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_snapshot_cache_exists():
    """Verify dashboard_routes has snapshot cache."""
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _AGENT_V2_SNAPSHOT_CACHE
    assert "ts" in _AGENT_V2_SNAPSHOT_CACHE
    assert "data" in _AGENT_V2_SNAPSHOT_CACHE


def test_snapshot_ttl_configured():
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _AGENT_V2_SNAPSHOT_TTL_SEC
    assert _AGENT_V2_SNAPSHOT_TTL_SEC > 0
    assert _AGENT_V2_SNAPSHOT_TTL_SEC <= 60


def test_run_limit_configured():
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _AGENT_V2_SNAPSHOT_RUN_LIMIT
    assert _AGENT_V2_SNAPSHOT_RUN_LIMIT > 0
    assert _AGENT_V2_SNAPSHOT_RUN_LIMIT <= 100


def test_limit_runs_for_dashboard_truncates():
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _limit_runs_for_dashboard
    runs = [{"run_id": f"agv2_{i:04d}", "created_at": f"2026-01-0{i%9+1}"} for i in range(100)]
    limited = _limit_runs_for_dashboard(runs, limit=50)
    assert len(limited) <= 50


def test_limit_runs_for_dashboard_preserves_small_lists():
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _limit_runs_for_dashboard
    runs = [{"run_id": "agv2_001"}]
    limited = _limit_runs_for_dashboard(runs, limit=50)
    assert len(limited) == 1


def test_limit_runs_for_dashboard_sorts_by_timestamp():
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _limit_runs_for_dashboard
    runs = [
        {"run_id": "old", "created_at": "2026-01-01"},
        {"run_id": "new", "created_at": "2026-06-01"},
        {"run_id": "mid", "created_at": "2026-03-01"},
    ]
    limited = _limit_runs_for_dashboard(runs, limit=2)
    assert len(limited) == 2
    ids = [r["run_id"] for r in limited]
    assert "new" in ids


def test_limit_runs_does_not_mutate_input():
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _limit_runs_for_dashboard
    runs = [{"run_id": f"r{i}", "created_at": f"2026-01-0{i%9+1}"} for i in range(100)]
    original_len = len(runs)
    _limit_runs_for_dashboard(runs, limit=10)
    assert len(runs) == original_len


def test_app_js_has_refresh_guard():
    with open("tmp_agent/brain_v9/dashboard/static/app.js", encoding="utf-8") as f:
        src = f.read()
    assert "refreshInFlight" in src, "app.js must have refreshInFlight guard"
    assert "Promise.allSettled" in src, "app.js must use Promise.allSettled"


def test_app_js_preserves_streaming_endpoint():
    with open("tmp_agent/brain_v9/dashboard/static/app.js", encoding="utf-8") as f:
        src = f.read()
    assert "/brain-dashboard/chat/stream" in src


def test_app_js_preserves_legacy_fallback():
    with open("tmp_agent/brain_v9/dashboard/static/app.js", encoding="utf-8") as f:
        src = f.read()
    assert "sendChatLegacy" in src


def test_no_forbidden_tokens():
    _tok_p1 = "AGENTV2_TEST_ADMIN_TOKEN"
    _tok_p2 = "_08F8_R1B"
    _pwd_p1 = "dev_admin_"
    _pwd_p2 = "2026!"
    _bearer_p1 = "MiClave"
    _bearer_p2 = "UltraSegura"
    for f in ["tmp_agent/brain_v9/dashboard/dashboard_routes.py",
              "tmp_agent/brain_v9/dashboard/static/app.js"]:
        with open(f, encoding="utf-8") as fh:
            src = fh.read()
        assert _tok_p1 + _tok_p2 not in src
        assert _pwd_p1 + _pwd_p2 not in src
        assert _bearer_p1 + _bearer_p2 not in src


if __name__ == "__main__":
    tests = [
        test_snapshot_cache_exists,
        test_snapshot_ttl_configured,
        test_run_limit_configured,
        test_limit_runs_for_dashboard_truncates,
        test_limit_runs_for_dashboard_preserves_small_lists,
        test_limit_runs_for_dashboard_sorts_by_timestamp,
        test_limit_runs_does_not_mutate_input,
        test_app_js_has_refresh_guard,
        test_app_js_preserves_streaming_endpoint,
        test_app_js_preserves_legacy_fallback,
        test_no_forbidden_tokens,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")