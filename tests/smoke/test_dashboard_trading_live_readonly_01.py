from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from tmp_agent.brain_v9.dashboard.dashboard_app import app


ROUTES = ROOT / "tmp_agent" / "brain_v9" / "dashboard" / "dashboard_routes.py"
APPJS = ROOT / "tmp_agent" / "brain_v9" / "dashboard" / "static" / "app.js"
INDEX = ROOT / "tmp_agent" / "brain_v9" / "dashboard" / "static" / "index.html"
STYLES = ROOT / "tmp_agent" / "brain_v9" / "dashboard" / "static" / "styles.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_trading_live_endpoint_readonly_contract():
    client = TestClient(app)
    response = client.get("/brain-dashboard/trading-live")
    assert response.status_code == 200
    payload = response.json()

    assert payload["mode"] == "read_only_observability"
    assert payload["real_money_enabled"] is False
    assert payload["order_submission_enabled"] is False
    assert payload["memory_write_enabled"] is False
    assert payload["faiss_write_enabled"] is False
    assert "qc" in payload
    assert "ibkr" in payload

    ibkr = payload["ibkr"]
    assert ibkr["read_only"] is True
    assert ibkr["paper_port_enforced"] is True
    assert ibkr["port"] == 4002
    assert ibkr["order_submission_enabled"] is False

    port_scan = ibkr["port_scan"]
    for key in ("gateway_live_4001", "gateway_paper_4002", "tws_live_7496", "tws_paper_7497"):
        assert key in port_scan


def test_ibkr_live_port_is_diagnostic_only():
    routes = _read(ROUTES)
    assert "_dashboard_port_listening(4001)" in routes
    assert "live_port_detected_not_used" in routes
    assert "readonly=True" in routes
    assert re.search(r"ib\.connect\(\s*[\"']127\.0\.0\.1[\"']\s*,\s*4002", routes)
    assert not re.search(r"ib\.connect\(\s*[\"']127\.0\.0\.1[\"']\s*,\s*4001", routes)
    assert not re.search(r"ib\.connect\(\s*[\"']127\.0\.0\.1[\"']\s*,\s*7496", routes)


def test_no_order_execution_tokens_in_dashboard_runtime():
    combined = "\n".join([_read(ROUTES), _read(APPJS)])
    forbidden = [
        "placeOrder",
        "cancelOrder",
        "reqGlobalCancel",
        "MarketOrder",
        "LimitOrder",
        "StopOrder",
        "bracketOrder",
        "qualifyContracts(",
        "submit_order",
        "submitOrder",
        "liquidate",
        "close_position",
    ]
    for token in forbidden:
        assert token not in combined

    assert not re.search(r"real_money_enabled\s*[:=]\s*true", combined, re.IGNORECASE)
    assert not re.search(r"order_submission_enabled\s*[:=]\s*true", combined, re.IGNORECASE)


def test_static_ui_exposes_trading_view_without_controls():
    appjs = _read(APPJS)
    index = _read(INDEX)
    styles = _read(STYLES)

    for token in (
        "viewTrading",
        "/brain-dashboard/trading-live",
        "Trading Live",
        "IBKR Read-Only",
        "PH391 Research Running",
        "order_submission_enabled",
    ):
        assert token in appjs

    for token in (
        'data-view="trading"',
        "ts-qc",
        "ts-ibkr",
        "/static/app.js?v=8",
        "/static/styles.css?v=8",
    ):
        assert token in index

    for token in ("live-card", "port-grid"):
        assert token in styles

    dangerous_button = re.compile(
        r"<button[^>]*(Buy|Sell|Cancel|Liquidate|Submit|Transmit)",
        re.IGNORECASE,
    )
    assert not dangerous_button.search(appjs)
    assert not dangerous_button.search(index)


if __name__ == "__main__":
    test_trading_live_endpoint_readonly_contract()
    test_ibkr_live_port_is_diagnostic_only()
    test_no_order_execution_tokens_in_dashboard_runtime()
    test_static_ui_exposes_trading_view_without_controls()
    print("OK: dashboard trading live readonly smoke passed")
