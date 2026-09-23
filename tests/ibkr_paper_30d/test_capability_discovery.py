from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

import ibkr_paper_30d.capability_discovery as discovery


def _contract(**updates):
    values = {
        "conId": 265598,
        "symbol": "AAPL",
        "localSymbol": "AAPL",
        "secType": "STK",
        "exchange": "NASDAQ",
        "primaryExchange": "NASDAQ",
        "currency": "USD",
        "lastTradeDateOrContractMonth": "",
        "strike": 0.0,
        "right": "",
        "multiplier": "",
        "tradingClass": "NMS",
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _details(**updates):
    values = {
        "contract": _contract(),
        "marketName": "NMS",
        "longName": "APPLE INC",
        "minTick": 0.01,
        "orderTypes": "ACTIVETIM,AD,ALERT,REL,LMT,MKT",
        "validExchanges": "SMART,AMEX,NYSE,CBOE,NASDAQ,OVERNIGHT",
        "priceMagnifier": 1,
        "underConId": 0,
        "contractMonth": "",
        "timeZoneId": "US/Eastern",
        "tradingHours": "20260922:0400-20260922:2000",
        "liquidHours": "20260922:0930-20260922:1600",
        "marketRuleIds": "26,26,26,26,26,26",
        "realExpirationDate": "",
        "stockType": "COMMON",
        "minSize": 1,
        "sizeIncrement": 1,
        "suggestedSizeIncrement": 1,
        "aggGroup": 1,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_default_probes_cover_session_and_asset_class_discovery() -> None:
    by_label = {item.label: item for item in discovery.DEFAULT_PROBES}

    assert by_label["AAPL_STK_SMART"].exchange == "SMART"
    assert by_label["AAPL_STK_OVERNIGHT"].exchange == "OVERNIGHT"
    assert by_label["SPY_STK_OVERNIGHT"].exchange == "OVERNIGHT"
    assert by_label["EURUSD_CASH_IDEALPRO"].sec_type == "CASH"
    assert by_label["ES_FUT_CME"].sec_type == "FUT"
    assert by_label["SPX_IND_CBOE"].sec_type == "IND"
    assert by_label["BTC_CRYPTO_PAXOS"].sec_type == "CRYPTO"
    assert by_label["XAUUSD_CMDTY_IBCMDTY"].sec_type == "CMDTY"
    assert by_label["AAPL_CFD_SMART"].sec_type == "CFD"


def test_probe_spec_accepts_arbitrary_contract_identity_fields() -> None:
    spec = discovery.ProbeSpec.from_mapping(
        {
            "label": "custom",
            "symbol": "aapl",
            "secType": "opt",
            "exchange": "smart",
            "currency": "usd",
            "conId": 123,
            "expiry": "20261016",
            "strike": 350,
            "right": "c",
            "multiplier": "100",
        }
    )

    assert spec.symbol == "AAPL"
    assert spec.sec_type == "OPT"
    assert spec.exchange == "SMART"
    assert spec.con_id == 123
    assert spec.expiry == "20261016"
    assert spec.strike == 350
    assert spec.right == "C"
    assert spec.multiplier == "100"


def test_contract_details_preserve_broker_capability_fields() -> None:
    row = discovery._serialize_contract_details(_details())

    assert row["orderTypes"].startswith("ACTIVETIM")
    assert "OVERNIGHT" in row["validExchanges"]
    assert row["tradingHours"] == "20260922:0400-20260922:2000"
    assert row["liquidHours"] == "20260922:0930-20260922:1600"
    assert row["timeZoneId"] == "US/Eastern"
    assert row["marketRuleIds"] == "26,26,26,26,26,26"
    assert row["minTick"] == 0.01
    assert row["minSize"] == 1
    assert row["sizeIncrement"] == 1


def test_future_selection_prefers_nonexpired_contract(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "datetime", SimpleNamespace(
        now=lambda tz: SimpleNamespace(strftime=lambda fmt: "20260922"),
    ))
    expired = _details(
        contract=_contract(
            conId=1,
            secType="FUT",
            lastTradeDateOrContractMonth="20260918",
        )
    )
    future = _details(
        contract=_contract(
            conId=2,
            secType="FUT",
            lastTradeDateOrContractMonth="20261218",
        )
    )
    spec = discovery.ProbeSpec("ES", "ES", "FUT", "CME")

    selected = discovery._select_detail(spec, [expired, future])

    assert selected.contract.conId == 2


def test_read_only_probe_module_contains_no_order_write_surface() -> None:
    source = inspect.getsource(discovery)
    forbidden = (
        "place" + "Order",
        "cancel" + "Order",
        "reqGlobal" + "Cancel",
        "whatIf" + "Order",
    )

    assert not any(name in source for name in forbidden)
    assert "ReadOnlyMessageGuard.validate" in source
    assert '"real_order_writes_attempted": 0' in source
    assert '"paper_execution_armed": False' in source


@pytest.mark.parametrize(
    ("host", "port"),
    [
        ("127.0.0.1", 4001),
        ("localhost", 7497),
        ("example.com", 4002),
    ],
)
def test_discovery_rejects_nonpaper_endpoint_before_network(host: str, port: int) -> None:
    with pytest.raises(ValueError, match="PAPER Gateway"):
        discovery.discover_capabilities(
            [discovery.DEFAULT_PROBES[0]],
            host=host,
            port=port,
            expected_account_hash="a" * 64,
        )


def test_nonfinite_broker_scalars_fail_closed_to_none() -> None:
    assert discovery._safe_scalar(float("nan")) is None
    assert discovery._safe_scalar(float("inf")) is None


def test_capability_discovery_source_marks_permissions_unproven() -> None:
    source = inspect.getsource(discovery)

    assert "UNPROVEN_READ_ONLY_DISCOVERY" in source
    assert '"account_trading_permission_proven": False' in source
    assert '"what_if_orders": False' in source
