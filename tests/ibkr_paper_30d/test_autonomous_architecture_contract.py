from pathlib import Path

AUTONOMOUS_MODULES = [
    Path("ibkr_paper_30d/autonomous_research.py"),
    Path("ibkr_paper_30d/autonomous_execution.py"),
    Path("ibkr_paper_30d/autonomous_runtime.py"),
    Path("ibkr_paper_30d/autonomous_state.py"),
    Path("ibkr_paper_30d/autonomous_service.py"),
    Path("ibkr_paper_30d/ibkr_research_tools.py"),
    Path("ibkr_paper_30d/scanner_capability.py"),
    Path("ibkr_paper_30d/research_telemetry.py"),
    Path("ibkr_paper_30d/decision_diagnostics.py"),
]


def combined_source():
    return "\n".join(path.read_text(encoding="utf-8") for path in AUTONOMOUS_MODULES)


def test_autonomous_path_never_uses_legacy_percentage_risk_engine():
    source = combined_source()
    assert "RiskEngine.month1()" not in source
    assert "max_loss_per_trade" not in source
    assert "max_total_open_risk" not in source
    assert "max_total_drawdown" not in source
    assert "AGGRESSIVE_CAPITAL_BOUNDARY_V1" in source


def test_autonomous_path_does_not_enforce_frozen_candidate_universe():
    source = combined_source()
    assert "SYMBOL_NOT_IN_FROZEN_CANDIDATES" not in source
    assert "candidate_screen_results=[" in source
    state_source = Path("ibkr_paper_30d/autonomous_state.py").read_text(encoding="utf-8")
    assert "candidate_screen_results=[]" in state_source


def test_autonomous_service_uses_agreed_observation_cadence():
    source = Path("ibkr_paper_30d/autonomous_service.py").read_text(encoding="utf-8")
    assert "scan_interval_seconds: float = 300.0" in source
    assert "position_interval_seconds: float = 60.0" in source
    assert 'trigger = "POSITION_EVENT"' in source
    assert 'trigger = "SCHEDULED_SCAN"' in source


def test_broker_feasibility_remains_authoritative():
    source = Path("ibkr_paper_30d/ibkr_research_tools.py").read_text(encoding="utf-8")
    assert "whatIf=True" in source
    assert "BROKER_MARGIN_EXCEEDS_EXPERIMENT_EQUITY" in source
    assert "EXPERIMENT_CAPITAL_BOUNDARY_AFTER_COSTS" in source


def test_open_order_writes_exist_only_in_authoritative_executor():
    executor_path = Path("ibkr_paper_30d/autonomous_execution.py")
    executor = executor_path.read_text(encoding="utf-8")
    assert ".cancelOrder(" in executor
    assert ".placeOrder(" in executor
    for path in AUTONOMOUS_MODULES:
        if path == executor_path:
            continue
        source = path.read_text(encoding="utf-8")
        assert ".cancelOrder(" not in source


def test_no_quantitative_activity_targets_across_autonomous_modules():
    source = combined_source()
    for forbidden in (
        "min_trades",
        "min_exposure",
        "trade_quota",
        "mandatory_scanner",
        "minimum_research",
        "required_symbols",
    ):
        assert forbidden not in source, forbidden


def test_shared_readonly_guard_is_unchanged():
    from ibapi.message import OUT

    from ibkr_paper_30d.ibkr_readonly_session import ReadOnlyMessageGuard

    assert set(ReadOnlyMessageGuard.ALLOWED_MESSAGE_IDS) == {
        OUT.START_API,
        OUT.REQ_MANAGED_ACCTS,
        OUT.REQ_ACCT_DATA,
        OUT.REQ_ACCOUNT_SUMMARY,
        OUT.CANCEL_ACCOUNT_SUMMARY,
        OUT.REQ_POSITIONS,
        OUT.CANCEL_POSITIONS,
        OUT.REQ_ALL_OPEN_ORDERS,
        OUT.REQ_EXECUTIONS,
        OUT.REQ_CURRENT_TIME,
        OUT.REQ_MKT_DATA,
        OUT.CANCEL_MKT_DATA,
        OUT.REQ_MARKET_DATA_TYPE,
        OUT.REQ_CONTRACT_DATA,
        OUT.REQ_TICK_BY_TICK_DATA,
        OUT.CANCEL_TICK_BY_TICK_DATA,
    }


def test_client_id_authority_separation_is_preserved():
    from ibkr_paper_30d.open_order_management import EXECUTION_CLIENT_ID
    from ibkr_paper_30d import scanner_capability

    assert EXECUTION_CLIENT_ID == 19761
    assert scanner_capability.SCANNER_CLIENT_ID == 19791
    assert scanner_capability.SCANNER_CLIENT_ID != EXECUTION_CLIENT_ID


def test_telemetry_and_diagnostics_never_gate_execution():
    validation_modules = [
        Path("ibkr_paper_30d/autonomous_research.py"),
        Path("ibkr_paper_30d/autonomous_execution.py"),
        Path("ibkr_paper_30d/ibkr_research_tools.py"),
    ]
    for path in validation_modules:
        source = path.read_text(encoding="utf-8")
        assert "build_risk_diagnostics" not in source
        assert "classify_research_depth" not in source


def test_scanner_output_never_becomes_authorized_universe():
    source = combined_source()
    assert "authorized_universe" not in source
    assert "discovery_evidence_only" in source


def test_open_order_management_retains_paper_arm_and_live_route_guards():
    executor = Path("ibkr_paper_30d/autonomous_execution.py").read_text(
        encoding="utf-8"
    )
    toolbox = Path("ibkr_paper_30d/ibkr_research_tools.py").read_text(
        encoding="utf-8"
    )
    assert "IBKR_AUTONOMOUS_PAPER_ARMED" in executor
    assert "EXECUTION_CLIENT_ID" in executor
    assert 'startswith("DU")' in executor
    assert 'PAPER_HOSTS = {"127.0.0.1", "localhost"}' in toolbox
    assert "PAPER_PORT = 4002" in toolbox
    assert "host not in PAPER_HOSTS or port != PAPER_PORT" in toolbox
    assert "7497" not in executor
    assert "7496" not in executor
