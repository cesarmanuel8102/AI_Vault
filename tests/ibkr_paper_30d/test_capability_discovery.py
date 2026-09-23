from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.capability_discovery import (
    CAPABILITY_ALLOWED_MESSAGE_IDS,
    REQ_SEC_DEF_OPT_PARAMS_ID,
    _contract_capability,
    _sample_derivative_spec,
    discover_ibkr_capabilities,
    report_sha256,
    select_contract_details,
    validate_capability_message,
    write_capability_discovery,
)
from ibkr_paper_30d.canonical import canonical_bytes
from ibkr_paper_30d.ibkr_readonly_session import ReadOnlyTransportViolation

ROOT = Path(__file__).parents[2]
RUNNER = ROOT / "RUN_IBKR_CAPABILITY_DISCOVERY.ps1"


def fake_details(
    *,
    con_id: int,
    symbol: str,
    sec_type: str,
    exchange: str,
    expiry: str = "",
    valid_exchanges: str = "",
    order_types: str = "MKT,LMT",
):
    contract = SimpleNamespace(
        conId=con_id,
        symbol=symbol,
        localSymbol=symbol,
        secType=sec_type,
        exchange=exchange,
        primaryExchange="NASDAQ" if sec_type == "STK" else "",
        currency="USD",
        tradingClass=symbol,
        multiplier="50" if sec_type == "FUT" else "",
        lastTradeDateOrContractMonth=expiry,
    )
    return SimpleNamespace(
        contract=contract,
        minTick=0.01,
        minSize=1,
        sizeIncrement=1,
        suggestedSizeIncrement=1,
        validExchanges=valid_exchanges,
        orderTypes=order_types,
        tradingHours="20260922:0400-20260922:2000",
        liquidHours="20260922:0930-20260922:1600",
        timeZoneId="US/Eastern",
        marketRuleIds="26,26",
    )


@pytest.mark.parametrize("message_id", [3, 4, 58])
def test_capability_transport_rejects_order_write_message_ids(message_id: int) -> None:
    with pytest.raises(ReadOnlyTransportViolation):
        validate_capability_message(f"{message_id}\0payload")


def test_capability_transport_allows_secdef_reference_data() -> None:
    assert REQ_SEC_DEF_OPT_PARAMS_ID in CAPABILITY_ALLOWED_MESSAGE_IDS
    assert validate_capability_message(f"{REQ_SEC_DEF_OPT_PARAMS_ID}\0payload") == REQ_SEC_DEF_OPT_PARAMS_ID


def test_contract_projection_exposes_route_hours_and_order_types() -> None:
    details = fake_details(
        con_id=265598,
        symbol="AAPL",
        sec_type="STK",
        exchange="SMART",
        valid_exchanges="SMART,NASDAQ,OVERNIGHT",
        order_types="MKT,LMT,STP",
    )

    result = _contract_capability("AAPL_STK_SMART", details)

    assert result.con_id == 265598
    assert result.sec_type == "STK"
    assert result.overnight_route_advertised is True
    assert result.order_types == ("MKT", "LMT", "STP")
    assert result.valid_exchanges == ("SMART", "NASDAQ", "OVERNIGHT")
    assert result.trading_hours
    assert result.liquid_hours


def test_sample_derivative_spec_uses_reference_data_without_order_preview() -> None:
    client = SimpleNamespace(
        secdef_values={
            21000: [
                {
                    "exchange": "SMART",
                    "underlying_con_id": 265598,
                    "trading_class": "AAPL",
                    "multiplier": "100",
                    "expirations": ("20260923", "20261016"),
                    "strikes": (330.0, 340.0, 350.0),
                }
            ]
        }
    )

    contract = _sample_derivative_spec(
        client,
        secdef_req_id=21000,
        symbol="AAPL",
        sec_type="OPT",
        currency="USD",
        preferred_exchange="SMART",
    )

    assert contract is not None
    assert contract.secType == "OPT"
    assert contract.exchange == "SMART"
    assert contract.lastTradeDateOrContractMonth == "20260923"
    assert contract.strike == 340.0
    assert contract.right == "C"
    assert contract.multiplier == "100"
    assert contract.tradingClass == "AAPL"


def test_future_selection_prefers_nearest_nonexpired_contract() -> None:
    expired = fake_details(
        con_id=1,
        symbol="ES",
        sec_type="FUT",
        exchange="CME",
        expiry="20260918",
    )
    front = fake_details(
        con_id=2,
        symbol="ES",
        sec_type="FUT",
        exchange="CME",
        expiry="20261218",
    )
    later = fake_details(
        con_id=3,
        symbol="ES",
        sec_type="FUT",
        exchange="CME",
        expiry="20270319",
    )

    chosen = select_contract_details([later, expired, front], sec_type="FUT")

    assert chosen.contract.conId == 2


def test_wrong_endpoint_blocks_without_touching_broker() -> None:
    result = discover_ibkr_capabilities(host="127.0.0.1", port=4001)

    assert result["status"] == "BLOCK"
    assert result["reason_codes"] == ["PAPER_ENDPOINT_REQUIRED"]
    assert result["real_order_writes_attempted"] == 0


def test_capability_report_hash_matches_written_bytes(tmp_path: Path) -> None:
    report = {
        "schema": "IBKR_CAPABILITY_DISCOVERY_V1",
        "status": "PASS",
        "real_order_writes_attempted": 0,
        "outbound_allowlist_only": True,
    }
    destination = tmp_path / "capability.json"

    write_capability_discovery(report, destination)

    expected = hashlib.sha256(canonical_bytes(report)).hexdigest()
    assert destination.read_bytes() == canonical_bytes(report)
    assert report_sha256(report) == expected


def test_capability_probe_source_contains_no_order_write_surface() -> None:
    source = (ROOT / "ibkr_paper_30d" / "capability_discovery.py").read_text(
        encoding="utf-8"
    )
    forbidden = ("place" + "Order", "cancel" + "Order", "reqGlobal" + "Cancel")
    assert not any(name in source for name in forbidden)


def test_runner_is_unarmed_and_fail_closed() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "CAPABILITY_DISCOVERY_REQUIRES_UNARMED_EXPERIMENT" in text
    assert "IBKR_PAPER_GATEWAY_4002_NOT_LISTENING" in text
    assert "CAPABILITY_DISCOVERY_ORDER_WRITE_INVARIANT_BROKEN" in text
    assert "CAPABILITY_DISCOVERY_TRANSPORT_ALLOWLIST_BROKEN" in text
    assert "CAPABILITY_DISCOVERY_NOT_PAPER" in text
    assert "IBKR_AUTONOMOUS_PAPER_ARMED=true" not in text


def test_probe_catalog_is_explicitly_non_restrictive_in_source() -> None:
    source = (ROOT / "ibkr_paper_30d" / "capability_discovery.py").read_text(
        encoding="utf-8"
    )

    assert '"representative_probe_only": True' in source
    assert '"probe_catalog_not_trading_universe": True' in source
