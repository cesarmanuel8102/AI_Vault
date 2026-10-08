from __future__ import annotations

from collections.abc import Mapping


REQUIRED_READONLY_QUERIES = (
    "managed_accounts",
    "positions",
    "open_orders",
    "executions",
    "current_time",
)


def is_safe_account_summary_partial(payload: Mapping[str, object]) -> bool:
    completeness = payload.get("query_completeness")
    return (
        payload.get("status") == "PARTIAL"
        and payload.get("reason_codes") == ["ACCOUNT_SUMMARY_FIELDS_INCOMPLETE"]
        and payload.get("broker_reconciliation_gate") == "BLOCK"
        and payload.get("paper_account_identity_gate") == "PASS"
        and payload.get("real_ibkr_read_only_identity_gate") == "PASS"
        and payload.get("expected_account_identity_bound") is True
        and payload.get("paper_account_namespace_ok") is True
        and payload.get("managed_account_count") == 1
        and payload.get("heartbeat_ok") is True
        and payload.get("gateway_mode") == "PAPER"
        and payload.get("outbound_allowlist_only") is True
        and payload.get("real_order_writes_attempted") == 0
        and payload.get("account_summary_consistent") is True
        and payload.get("account_summary_complete") is False
        and payload.get("gateway_config_consistent") is True
        and isinstance(completeness, Mapping)
        and all(completeness.get(name) is True for name in REQUIRED_READONLY_QUERIES)
    )
