from pathlib import Path

AUTONOMOUS_MODULES = [
    Path("ibkr_paper_30d/autonomous_research.py"),
    Path("ibkr_paper_30d/autonomous_execution.py"),
    Path("ibkr_paper_30d/autonomous_runtime.py"),
    Path("ibkr_paper_30d/autonomous_state.py"),
    Path("ibkr_paper_30d/autonomous_service.py"),
    Path("ibkr_paper_30d/ibkr_research_tools.py"),
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
