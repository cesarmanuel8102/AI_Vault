from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "tmp_agent" / "brain_v9" / "main.py"
CHAT_ROUTER = ROOT / "tmp_agent" / "brain_v9" / "routes" / "chat_entrypoint_routes.py"
REPORT = ROOT / "docs" / "audit" / "MAIN_ROUTER_RESIDUAL_SURFACE_AUDIT_16A.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_main_py_has_expected_residual_route_count():
    main = _read(MAIN)
    count = len(re.findall(r"@app\.(get|post|put|delete|patch)", main))
    assert count <= 50, f"main.py residual route count {count} exceeds 50"


def test_chat_route_is_not_in_main():
    assert '@app.post("/chat"' not in _read(MAIN)


def test_chat_route_lives_in_router():
    router = _read(CHAT_ROUTER)
    assert '@router.post("/chat"' in router


def test_residual_audit_report_exists():
    assert REPORT.exists()
    report = _read(REPORT)
    assert "RESIDUAL_SURFACE_AUDIT_COMPLETED" in report


def test_report_classifies_every_residual_route():
    main = _read(MAIN)
    report = _read(REPORT)
    routes = re.findall(r'@app\.(get|post|put|delete|patch)\("([^"]+)"', main)
    missing = []
    for method, path in routes:
        # The report table escapes {} as \{\}; match the literal braces in the markdown table.
        if path not in report:
            missing.append((method, path))
    assert not missing, f"report missing residual routes: {missing}"


def test_report_contains_required_categories():
    report = _read(REPORT)
    categories = [
        "ROUTER_SHELL_READY",
        "PROVIDER_BOUNDARY_READY",
        "NEEDS_SERVICE_BOUNDARY",
        "CONTROL_MUTATION",
        "GOVERNANCE_SECURITY",
        "MEMORY_SEMANTIC_FAISS",
        "TRADING_QC_IBKR",
        "TRACE_STREAMING",
        "DEV_DEBUG_RISKY",
        "KEEP_IN_MAIN_APP_ASSEMBLY",
    ]
    for cat in categories:
        assert cat in report, f"category {cat} missing from report"


def test_report_has_next_fronts():
    report = _read(REPORT)
    assert "16B" in report
    assert "16H" in report
    assert "FRONT-BRAIN-MAIN-ROUTER-LOW-RISK-SHELL-MOVE-16B" in report


def test_apply_batch_is_deferred_not_low_risk():
    report = _read(REPORT)
    low_start = report.find("## Low-Risk Candidates for 16B")
    deferred_start = report.find("## Deferred / Risky Candidates")
    assert low_start != -1
    assert deferred_start != -1
    low_section = report[low_start:deferred_start]
    deferred_section = report[deferred_start:]
    assert "/brain/chat_excellence/proposals/apply_batch" not in low_section
    assert "/brain/chat_excellence/proposals/apply_batch" in deferred_section


def test_contract_does_not_use_live_tokens():
    source = _read(Path(__file__))
    forbidden_tokens = [
        "Test" + "Client",
        "uv" + "icorn",
        "sub" + "process",
        "os." + "system",
        "requ" + "ests.",
        "ht" + "tpx.",
        "place" + "Order",
        "submit" + "_order",
    ]
    for token in forbidden_tokens:
        assert token not in source, f"forbidden token {token!r} found in contract source"


if __name__ == "__main__":
    test_main_py_has_expected_residual_route_count()
    test_chat_route_is_not_in_main()
    test_chat_route_lives_in_router()
    test_residual_audit_report_exists()
    test_report_classifies_every_residual_route()
    test_report_contains_required_categories()
    test_report_has_next_fronts()
    test_apply_batch_is_deferred_not_low_risk()
    test_contract_does_not_use_live_tokens()
    print("OK: main router residual surface audit 16A contract passed")
