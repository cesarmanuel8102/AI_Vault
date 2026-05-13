from datetime import datetime

from .types import AccountState, Decision, FirmProfile, StrategySignal


def _in_session(now_et: datetime, session_start_et: str, session_end_et: str) -> bool:
    start_h, start_m = [int(x) for x in session_start_et.split(":")]
    end_h, end_m = [int(x) for x in session_end_et.split(":")]
    hhmm = now_et.hour * 100 + now_et.minute
    start = start_h * 100 + start_m
    end = end_h * 100 + end_m
    return start <= hhmm <= end


def check_firm_rules(
    signal: StrategySignal,
    account: AccountState,
    profile: FirmProfile,
    now_et: datetime,
) -> Decision:
    if not profile.automation_allowed:
        return Decision(False, f"automation_blocked:{profile.name}")

    if not _in_session(now_et, profile.session_start_et, profile.session_end_et):
        return Decision(False, "outside_allowed_session")

    if signal.qty < 1:
        return Decision(False, "invalid_qty")
    if signal.qty > profile.max_contracts_per_order:
        return Decision(False, "qty_over_order_limit")
    if (account.open_contracts + signal.qty) > profile.max_contracts_total:
        return Decision(False, "qty_over_total_limit")

    if account.day_pnl_pct <= -abs(profile.daily_loss_limit_pct):
        return Decision(False, "daily_loss_limit_reached")

    if account.trailing_dd_pct >= abs(profile.trailing_drawdown_limit_pct):
        return Decision(False, "trailing_drawdown_limit_reached")

    if signal.side not in ("BUY", "SELL"):
        return Decision(False, "invalid_side")

    return Decision(True, "accepted", route_provider=profile.provider)
