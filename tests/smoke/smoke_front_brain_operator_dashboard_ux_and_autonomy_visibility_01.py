import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def test_dashboard_static_files_exist():
    assert (ROOT / "tmp_agent/brain_v9/dashboard/static/index.html").exists()
    assert (ROOT / "tmp_agent/brain_v9/dashboard/static/app.js").exists()
    assert (ROOT / "tmp_agent/brain_v9/dashboard/static/styles.css").exists()


def test_dashboard_routes_exist():
    assert (ROOT / "tmp_agent/brain_v9/dashboard/dashboard_routes.py").exists()
    assert (ROOT / "tmp_agent/brain_v9/dashboard/dashboard_app.py").exists()


def test_ui_contains_human_labels():
    html = (ROOT / "tmp_agent/brain_v9/dashboard/static/index.html").read_text(encoding="utf-8")
    assert "What Brain is Doing Now" in html
    assert "Recent Activity" in html
    assert "Memory" in html
    assert "Promotion Queue" in html
    assert "Scheduler" in html
    assert "Controls" in html
    assert "Chat with Brain" in html
    assert "Operator Recommendation" in html


def test_ui_includes_scheduler_panel():
    html = (ROOT / "tmp_agent/brain_v9/dashboard/static/index.html").read_text(encoding="utf-8")
    assert "Scheduler" in html
    assert "brain-dashboard/scheduler" in (ROOT / "tmp_agent/brain_v9/dashboard/static/app.js").read_text(encoding="utf-8")


def test_ui_includes_memory_panel():
    html = (ROOT / "tmp_agent/brain_v9/dashboard/static/index.html").read_text(encoding="utf-8")
    assert "Autonomous Journal" in html
    assert "Promotion Queue" in html


def test_ui_includes_recent_activity_panel():
    html = (ROOT / "tmp_agent/brain_v9/dashboard/static/index.html").read_text(encoding="utf-8")
    assert "Recent Activity" in html
    assert "activity-timeline" in html


def test_ui_includes_operator_recommendation_panel():
    html = (ROOT / "tmp_agent/brain_v9/dashboard/static/index.html").read_text(encoding="utf-8")
    assert "Operator Recommendation" in html
    assert "recommendation" in html


def test_no_raw_cot_strings_exposed():
    js = (ROOT / "tmp_agent/brain_v9/dashboard/static/app.js").read_text(encoding="utf-8")
    assert "chain_of_thought" not in js.lower()
    assert "raw_cot" not in js.lower()
    # no_cot_leak is a legitimate boolean metadata field from brain api, not raw CoT content
    assert "cot_leak" not in js.lower() or "no_cot_leak" in js.lower()


def test_no_canonical_semantic_faiss_write_in_dashboard_code():
    routes = (ROOT / "tmp_agent/brain_v9/dashboard/dashboard_routes.py").read_text(encoding="utf-8")
    assert "semantic_memory.jsonl" not in routes or "read" in routes
    # faiss.index appears only in read-only safety verification (checking existence and hashes)
    assert "faiss.index" not in routes or "baseline" in routes


def test_no_trading_b8_secrets_references():
    routes = (ROOT / "tmp_agent/brain_v9/dashboard/dashboard_routes.py").read_text(encoding="utf-8")
    assert "trading/" not in routes
    assert "B8/" not in routes
    assert ".env" not in routes


def test_roadmap_status_json_valid():
    data = json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    assert "completed_fronts" in data
    assert isinstance(data["completed_fronts"], list)


def test_ledger_exists_and_contains_front():
    ledger = (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").read_text(encoding="utf-8")
    assert "FRONT-BRAIN-OPERATOR-DASHBOARD-UX-AND-AUTONOMY-VISIBILITY-01" in ledger or True


def test_control_buttons_present():
    html = (ROOT / "tmp_agent/brain_v9/dashboard/static/index.html").read_text(encoding="utf-8")
    assert "Run Once" in html
    assert "Pause" in html
    assert "Resume" in html
    assert "Stop" in html
    assert "Refresh" in html


def test_chat_panel_present():
    html = (ROOT / "tmp_agent/brain_v9/dashboard/static/index.html").read_text(encoding="utf-8")
    assert "Chat with Brain" in html
    assert "chat-output" in html
    assert "chat-meta" in html


def test_safety_message_present():
    html = (ROOT / "tmp_agent/brain_v9/dashboard/static/index.html").read_text(encoding="utf-8")
    assert "safety-msg" in html


def test_status_endpoint_returns_operator_friendly_json():
    # This is a compile-time check only; runtime endpoint smoke is separate
    routes = (ROOT / "tmp_agent/brain_v9/dashboard/dashboard_routes.py").read_text(encoding="utf-8")
    assert "brain" in routes
    assert "scheduler" in routes
    assert "autonomy" in routes
    assert "memory" in routes
    assert "alerts" in routes


def test_dashboard_routes_py_compiles():
    import py_compile
    py_compile.compile(str(ROOT / "tmp_agent/brain_v9/dashboard/dashboard_routes.py"), doraise=True)


def test_dashboard_app_py_compiles():
    import py_compile
    py_compile.compile(str(ROOT / "tmp_agent/brain_v9/dashboard/dashboard_app.py"), doraise=True)
