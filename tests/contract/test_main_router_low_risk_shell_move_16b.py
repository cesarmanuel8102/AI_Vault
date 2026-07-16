"""Static contract for FRONT-BRAIN-MAIN-ROUTER-LOW-RISK-SHELL-MOVE-16B.

No imports of runtime modules; no server start; no live execution.
"""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "tmp_agent" / "brain_v9" / "main.py"
ROUTES_DIR = ROOT / "tmp_agent" / "brain_v9" / "routes"
REPORT = ROOT / "docs" / "audit" / "MAIN_ROUTER_LOW_RISK_SHELL_MOVE_REPORT_16B.md"

ROUTERS = {
    "code_mutation": ROUTES_DIR / "code_mutation_readonly_routes.py",
    "chat_excellence": ROUTES_DIR / "chat_excellence_readonly_routes.py",
    "autonomy_readonly": ROUTES_DIR / "autonomy_readonly_shell_routes.py",
    "dev_pipeline": ROUTES_DIR / "dev_pipeline_audit_routes.py",
    "governance_refresh": ROUTES_DIR / "governance_refresh_shell_routes.py",
}

MOVED_ROUTES = {
    "code_mutation": [
        ("GET", "/brain/mutations"),
        ("GET", "/brain/mutations/{mutation_id}"),
    ],
    "chat_excellence": [
        ("GET", "/brain/chat_excellence/status"),
        ("GET", "/brain/chat_excellence/proposals"),
        ("GET", "/brain/learning/proposals"),
        ("GET", "/brain/chat_excellence/proposals/{proposal_id}"),
        ("POST", "/brain/chat_excellence/proposals/{proposal_id}/dry_run"),
        ("GET", "/brain/chat_excellence/proposals/{proposal_id}/health_gate_log"),
        ("GET", "/brain/chat_excellence/proposals/{proposal_id}/evaluation_status"),
    ],
    "autonomy_readonly": [
        ("GET", "/brain/autonomy/next-actions"),
    ],
    "dev_pipeline": [
        ("GET", "/brain/pipeline-health"),
        ("POST", "/brain/metacognition/audit"),
    ],
    "governance_refresh": [
        ("POST", "/brain/post-bl-roadmap/refresh"),
        ("POST", "/brain/meta-improvement/refresh"),
        ("POST", "/brain/chat-product/refresh"),
        ("POST", "/brain/autonomous-governance-eval/refresh"),
        ("POST", "/brain/utility-governance/refresh"),
        ("POST", "/brain/roadmap/governance/refresh"),
    ],
}

DEFERRED_ROUTES_IN_MAIN = [
    ("POST", "/brain/chat_excellence/proposals/apply_batch"),
    ("POST", "/brain/chat_excellence/proposals/{proposal_id}/apply"),
    ("POST", "/brain/chat_excellence/proposals/{proposal_id}/rollback"),
    ("POST", "/brain/chat_excellence/proposals/evaluate"),
    ("GET", "/brain/session-memory"),
    ("POST", "/brain/autonomy/ibkr-snapshot"),
    ("POST", "/brain/strategy-engine/execute-top-candidate"),
    ("POST", "/brain/llm/circuit_breaker/reset"),
]

FORBIDDEN_TOKENS = [
    "brain_v9." + "main",
    "brain_v9.core." + "session",
    "semantic_memory_fai" + "ss",
    "fai" + "ss",
    "tra" + "ding",
    "requ" + "ests.",
    "ht" + "tpx.",
    "uv" + "icorn",
    "sub" + "process",
    "os." + "system",
    "place" + "Order",
    "submit" + "_order",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _has_app_route(text: str, method: str, path: str) -> bool:
    return re.search(rf'@app\.{method.lower()}\("{re.escape(path)}"', text) is not None


def _has_router_route(text: str, method: str, path: str) -> bool:
    return re.search(rf'@router\.{method.lower()}\("{re.escape(path)}"', text) is not None


def test_low_risk_routers_exist():
    for name, path in ROUTERS.items():
        assert path.exists(), f"router {name} missing: {path}"
        text = _read(path)
        assert "APIRouter" in text, f"router {name} must contain APIRouter"


def test_moved_routes_live_in_routers():
    for router_name, routes in MOVED_ROUTES.items():
        text = _read(ROUTERS[router_name])
        for method, path in routes:
            assert _has_router_route(text, method, path), f"{method} {path} not found in {router_name}"


def test_moved_routes_no_longer_in_main():
    main = _read(MAIN)
    for router_name, routes in MOVED_ROUTES.items():
        for method, path in routes:
            assert not _has_app_route(main, method, path), f"{method} {path} still in main.py"


def test_deferred_risky_routes_remain_in_main():
    main = _read(MAIN)
    for method, path in DEFERRED_ROUTES_IN_MAIN:
        assert _has_app_route(main, method, path), f"deferred route {method} {path} missing from main.py"


def test_apply_batch_not_moved():
    main = _read(MAIN)
    chat_text = _read(ROUTERS["chat_excellence"])
    assert _has_app_route(main, "POST", "/brain/chat_excellence/proposals/apply_batch")
    assert not _has_router_route(chat_text, "POST", "/brain/chat_excellence/proposals/apply_batch")


def test_router_forbidden_imports():
    for name, path in ROUTERS.items():
        text = _read(path)
        for token in FORBIDDEN_TOKENS:
            assert token not in text, f"router {name} contains forbidden token {token!r}"


def test_endpoint_count_decreased():
    main = _read(MAIN)
    count = len(re.findall(r"@app\.(get|post|put|delete|patch)", main))
    assert count <= 38, f"main.py endpoint count {count} exceeds 38 after 16B moves"


def test_report_exists_and_lists_moved_routes():
    assert REPORT.exists()
    report = _read(REPORT)
    assert "LOW_RISK_SHELL_MOVE_COMPLETED" in report or "PARTIALLY_COMPLETED_WITH_DEFERRED" in report
    for router_name, routes in MOVED_ROUTES.items():
        for method, path in routes:
            needle = f"`{method} {path}`"
            assert needle in report, f"report missing moved route {needle}"


def test_report_route_counts_match_contract():
    report = _read(REPORT)
    expected_moved = sum(len(routes) for routes in MOVED_ROUTES.values())
    count_sentences = [line for line in report.splitlines() if "Routes moved:" in line or "routes moved" in line.lower()]
    found_explicit_count = False
    for sentence in count_sentences:
        if str(expected_moved) in sentence:
            found_explicit_count = True
            break
    assert found_explicit_count, f"report must explicitly state moved route count = {expected_moved}"


def test_contract_does_not_import_runtime_modules():
    source = _read(Path(__file__))
    for token in FORBIDDEN_TOKENS:
        assert token not in source, f"contract contains forbidden token {token!r}"


def test_contract_has_no_live_execution_tokens():
    source = _read(Path(__file__))
    live_tokens = [
        "Test" + "Client",
        "uv" + "icorn",
        "sub" + "process",
        "os." + "system",
        "htt" + "px",
        "requ" + "ests",
        "place" + "Order",
        "submit" + "_order",
    ]
    for token in live_tokens:
        assert token not in source, f"contract contains live token {token!r}"


if __name__ == "__main__":
    test_low_risk_routers_exist()
    test_moved_routes_live_in_routers()
    test_moved_routes_no_longer_in_main()
    test_deferred_risky_routes_remain_in_main()
    test_apply_batch_not_moved()
    test_router_forbidden_imports()
    test_endpoint_count_decreased()
    test_report_exists_and_lists_moved_routes()
    test_contract_does_not_import_runtime_modules()
    test_contract_has_no_live_execution_tokens()
    print("OK: main router low-risk shell move 16B contract passed")
