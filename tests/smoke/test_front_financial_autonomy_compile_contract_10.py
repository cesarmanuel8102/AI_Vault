"""Smoke test: financial_autonomy package is importable and dry-run safe."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_financial_autonomy_imports_and_exposes_dry_run_metrics(tmp_path):
    from financial_autonomy import FinancialAutonomyBridge, FinancialTrustIntegration

    bridge = FinancialAutonomyBridge(str(tmp_path))
    metrics = bridge.expose_financial_metrics()

    assert "error" not in metrics
    assert metrics["real_money_enabled"] is False
    assert metrics["broker_execution_enabled"] is False
    assert metrics["portfolio_performance"]["sharpe"] == 0.0
    assert bridge.apply_parameter_optimization({"x": 1})["applied"] is False
    assert bridge.adjust_risk_settings({"risk": "test"})["applied"] is False

    trust = FinancialTrustIntegration(str(tmp_path))
    trust_metrics = trust.calculate_financial_trust_metrics()
    assert trust_metrics["composite_score"] >= 0


def test_financial_endpoints_import_and_return_no_real_money_flags():
    from financial_autonomy.api import financial_endpoints as fe

    metrics = asyncio.run(fe.get_financial_metrics())
    trust = asyncio.run(fe.get_financial_trust())

    assert metrics.autonomy_integration["real_money_enabled"] is False
    assert metrics.autonomy_integration["broker_execution_enabled"] is False
    assert trust["real_money_enabled"] is False
    assert trust["broker_execution_enabled"] is False


def test_integration_setup_dry_run_does_not_modify_brain_file(tmp_path):
    from financial_autonomy.integration_setup import integrate_with_brain_server

    brain_file = tmp_path / "brain_server.py"
    original = "import os\n\napp = object()\n"
    brain_file.write_text(original, encoding="utf-8")

    assert integrate_with_brain_server(tmp_path, dry_run=True) is True
    assert brain_file.read_text(encoding="utf-8") == original


def test_financial_autonomy_sources_do_not_hardcode_legacy_vault_path():
    files = [
        ROOT / "financial_autonomy/__init__.py",
        ROOT / "financial_autonomy/financial_autonomy_autobuild.py",
        ROOT / "financial_autonomy/integration_setup.py",
        ROOT / "financial_autonomy/api/financial_endpoints.py",
        ROOT / "financial_autonomy/bridge/financial_autonomy_bridge.py",
        ROOT / "financial_autonomy/bridge/trust_score_integration.py",
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "C:/AI_VAULT" not in text
        assert "C:\\AI_VAULT" not in text
