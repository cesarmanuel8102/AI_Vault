from __future__ import annotations

from decimal import Decimal

import pytest

from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.config import Settings
from ibkr_paper_30d.redaction import redact_text
from ibkr_paper_30d.types import (
    BrokerState,
    ExecutionState,
    KillSwitchState,
    SystemState,
    new_uuid7,
)


def test_broker_writes_are_hard_disabled_by_default() -> None:
    settings = Settings.load({})

    assert settings.paper_only is True
    assert settings.broker_write_authorized is False
    assert settings.experiment_allocation == Decimal("500.00")
    assert settings.options_permission_level == 4
    assert settings.autonomous_research_enabled is True
    assert settings.research_round_budget == 8


def test_broker_write_enable_attempt_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside current authority"):
        Settings.load({"BROKER_WRITE_AUTHORIZED": "true"})


def test_redaction_masks_accounts_and_secret_assignments() -> None:
    raw = "account=DU1234567 EMAIL_PASS=hunter2 token=abc123 safe=value"

    clean = redact_text(raw)

    assert "DU1234567" not in clean
    assert "hunter2" not in clean
    assert "abc123" not in clean
    assert "safe=value" in clean


def test_canonical_hash_is_key_order_independent() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}

    assert canonical_bytes(left) == b'{"a":1,"b":2}'
    assert sha256_json(left) == sha256_json(right)


def test_uuid7_encodes_version_variant_and_timestamp() -> None:
    value = new_uuid7(now_ms=1_700_000_000_123)

    assert value.version == 7
    assert value.variant == "specified in RFC 4122"
    assert value.int >> 80 == 1_700_000_000_123


def test_uuid7_rejects_timestamp_outside_48_bits() -> None:
    with pytest.raises(ValueError, match="48-bit"):
        new_uuid7(now_ms=1 << 48)


def test_all_required_state_enums_are_present() -> None:
    assert {state.value for state in SystemState} == {
        "SYSTEM_BOOTING",
        "SYSTEM_PREFLIGHT",
        "SYSTEM_BLOCKED",
        "SYSTEM_READY",
        "SYSTEM_PAUSED",
        "SYSTEM_RECOVERING",
        "SYSTEM_STOPPED",
    }
    assert "BROKER_READY" in {state.value for state in BrokerState}
    assert "BROKER_RECONNECTING" in {state.value for state in BrokerState}
    assert "ORDER_SUBMIT_UNKNOWN" in {state.value for state in ExecutionState}
    assert {state.value for state in KillSwitchState} == {
        "KILL_SWITCH_CLEAR",
        "KILL_SWITCH_TRIGGERED",
        "KILL_SWITCH_RECOVERY_REVIEW",
    }
