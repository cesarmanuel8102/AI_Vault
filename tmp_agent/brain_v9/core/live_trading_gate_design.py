"""Pure, disabled LiveTradingGate contract for BRAIN-101 R16.1."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class DisabledLiveTradingGateReceipt:
    accepted: bool
    reason: str
    preview_only: bool
    audit_recorded: bool
    execution_permitted: bool
    receipt_id: str


def evaluate_disabled_live_trading_gate(
    *,
    human_final_authority: bool,
    operator_confirmation: bool,
    account_binding: str,
    capital_cap: float,
    loss_cap: float,
    symbol: str,
    strategy: str,
    allowed_symbols: tuple[str, ...],
    allowed_strategies: tuple[str, ...],
    within_time_window: bool,
    kill_switch_engaged: bool,
    preview_only: bool,
    broker_action: bool,
    provider_call: bool,
    network_call: bool,
    runtime_execution: bool,
    scheduler_activation: bool,
    live_trading: bool,
    real_money: bool,
) -> DisabledLiveTradingGateReceipt:
    """Evaluate design evidence only; this function cannot authorize execution."""
    checks = (
        (not human_final_authority, "human_final_authority_required"),
        (not operator_confirmation, "operator_confirmation_required"),
        (not account_binding.strip(), "account_binding_required"),
        (capital_cap <= 0, "capital_cap_required"),
        (loss_cap <= 0, "loss_cap_required"),
        (symbol not in allowed_symbols, "symbol_not_allowlisted"),
        (strategy not in allowed_strategies, "strategy_not_allowlisted"),
        (not within_time_window, "time_window_required"),
        (kill_switch_engaged, "kill_switch_engaged"),
        (not preview_only, "preview_only_required"),
        (broker_action, "broker_action_forbidden"),
        (provider_call, "provider_call_forbidden"),
        (network_call, "network_call_forbidden"),
        (runtime_execution, "runtime_execution_forbidden"),
        (scheduler_activation, "scheduler_activation_forbidden"),
        (live_trading, "live_trading_forbidden"),
        (real_money, "real_money_forbidden"),
    )
    reason = next((reason for invalid, reason in checks if invalid), "")
    accepted = not reason
    identity = {
        "account_binding": account_binding,
        "accepted": accepted,
        "allowed_strategies": allowed_strategies,
        "allowed_symbols": allowed_symbols,
        "capital_cap": capital_cap,
        "loss_cap": loss_cap,
        "reason": reason,
        "strategy": strategy,
        "symbol": symbol,
    }
    receipt_id = sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return DisabledLiveTradingGateReceipt(
        accepted=accepted,
        reason=reason,
        preview_only=preview_only,
        audit_recorded=accepted,
        execution_permitted=False,
        receipt_id=receipt_id,
    )
