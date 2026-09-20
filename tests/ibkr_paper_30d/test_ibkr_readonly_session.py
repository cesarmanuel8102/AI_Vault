from __future__ import annotations

import json

import pytest
from ibapi.message import OUT

from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
from ibkr_paper_30d.ibkr_readonly_session import (
    ExpectedPaperIdentityStore,
    ReadOnlyMessageGuard,
    ReadOnlyTransportViolation,
)


def wire_message(message_id: int) -> str:
    return f"{message_id}\0payload\0"


@pytest.mark.parametrize(
    "message_id",
    [
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
    ],
)
def test_readonly_wire_guard_accepts_only_declared_read_messages(message_id) -> None:
    assert ReadOnlyMessageGuard.validate(wire_message(message_id)) == message_id


@pytest.mark.parametrize("message_id", [3, 4, 8, 9, 15, 66])
def test_readonly_wire_guard_rejects_every_non_allowlisted_message(message_id) -> None:
    with pytest.raises(ReadOnlyTransportViolation, match="message id"):
        ReadOnlyMessageGuard.validate(wire_message(message_id))


def test_identity_store_persists_only_hash_and_mask(tmp_path) -> None:
    target = tmp_path / "expected-paper-identity.json"
    store = ExpectedPaperIdentityStore(target)

    receipt = store.bind(
        "DU123456",
        host="127.0.0.1",
        port=4002,
        gateway_mode="p",
        managed_account_count=1,
    )

    text = target.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert "DU123456" not in text
    assert payload["schema"] == "EXPECTED_PAPER_ACCOUNT_IDENTITY_V1"
    assert payload["account_sha256"] == expected_identity_hash("DU123456")
    assert payload["account_fingerprint"] == receipt.account_fingerprint
    assert store.load_hash() == expected_identity_hash("DU123456")


@pytest.mark.parametrize(
    "updates",
    [
        {"port": 4001},
        {"gateway_mode": "l"},
        {"managed_account_count": 2},
        {"account_id": "U123456"},
    ],
)
def test_identity_binding_fails_closed_without_paper_factors(tmp_path, updates) -> None:
    values = {
        "account_id": "DU123456",
        "host": "127.0.0.1",
        "port": 4002,
        "gateway_mode": "p",
        "managed_account_count": 1,
    }
    values.update(updates)

    with pytest.raises(ValueError):
        ExpectedPaperIdentityStore(tmp_path / "identity.json").bind(**values)


def test_identity_rebinding_to_different_account_is_rejected(tmp_path) -> None:
    store = ExpectedPaperIdentityStore(tmp_path / "identity.json")
    store.bind(
        "DU123456",
        host="127.0.0.1",
        port=4002,
        gateway_mode="p",
        managed_account_count=1,
    )

    with pytest.raises(ValueError, match="already bound"):
        store.bind(
            "DU654321",
            host="127.0.0.1",
            port=4002,
            gateway_mode="p",
            managed_account_count=1,
        )
