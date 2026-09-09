"""Deterministic paper-only financial autonomy inventory for BRAIN-101 R11.1.

This module is intentionally inert. It describes paper-only capability surfaces
without importing or executing financial-autonomy runtime code.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


_CAPABILITIES = (
    "market_data_observation",
    "strategy_research",
    "portfolio_state_modeling",
    "risk_precheck_modeling",
    "order_intent_modeling",
)


@dataclass(frozen=True)
class FinancialAutonomyPaperInventory:
    mode: str
    capabilities: tuple[str, ...]
    execution_enabled: bool
    real_money_enabled: bool
    live_trading_enabled: bool
    provider_calls_enabled: bool
    network_enabled: bool
    runtime_imports_enabled: bool
    inventory_sha256: str


def _inventory_sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_paper_only_financial_autonomy_inventory() -> FinancialAutonomyPaperInventory:
    payload: dict[str, object] = {
        "mode": "PAPER_ONLY",
        "capabilities": _CAPABILITIES,
        "execution_enabled": False,
        "real_money_enabled": False,
        "live_trading_enabled": False,
        "provider_calls_enabled": False,
        "network_enabled": False,
        "runtime_imports_enabled": False,
    }
    return FinancialAutonomyPaperInventory(
        **payload,
        inventory_sha256=_inventory_sha256(payload),
    )


def reject_financial_autonomy_effect(operation: str) -> None:
    """Fail closed for every effectful operation in this NO_DEPLOY inventory."""
    raise ValueError(f"paper_only_inventory_no_effects:{operation}")
