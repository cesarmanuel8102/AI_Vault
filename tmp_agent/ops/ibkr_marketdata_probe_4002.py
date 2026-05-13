from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper


ARTIFACT = Path(
    r"C:\AI_VAULT\tmp_agent\state\rooms\brain_financial_ingestion_fi04_structured_api\ibkr_marketdata_probe_status.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_stock(symbol: str, exchange: str = "SMART", primary: str | None = None) -> Contract:
    c = Contract()
    c.symbol = symbol
    c.secType = "STK"
    c.exchange = exchange
    c.currency = "USD"
    if primary:
        c.primaryExchange = primary
    return c


def make_option(symbol: str, expiry: str, strike: float, right: str) -> Contract:
    c = Contract()
    c.symbol = symbol
    c.secType = "OPT"
    c.exchange = "SMART"
    c.currency = "USD"
    c.lastTradeDateOrContractMonth = expiry
    c.strike = strike
    c.right = right
    c.multiplier = "100"
    return c


def make_fx(symbol: str, currency: str = "USD") -> Contract:
    c = Contract()
    c.symbol = symbol
    c.secType = "CASH"
    c.exchange = "IDEALPRO"
    c.currency = currency
    return c


def make_crypto(symbol: str, exchange: str = "PAXOS") -> Contract:
    c = Contract()
    c.symbol = symbol
    c.secType = "CRYPTO"
    c.exchange = exchange
    c.currency = "USD"
    return c


class Probe(EWrapper, EClient):
    def __init__(self) -> None:
        EClient.__init__(self, self)
        self.connected_ok = False
        self.server_time = None
        self.managed_accounts = None
        self.next_valid = None
        self.errors: list[dict] = []
        self.symbols: dict[str, dict] = {}

    def nextValidId(self, orderId: int):
        self.next_valid = orderId
        self.connected_ok = True

    def managedAccounts(self, accountsList: str):
        self.managed_accounts = accountsList

    def currentTime(self, time_: int):
        self.server_time = time_

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        self.errors.append(
            {
                "reqId": reqId,
                "errorCode": errorCode,
                "errorString": errorString,
            }
        )

    def tickPrice(self, reqId, tickType, price, attrib):
        data = self._ensure(reqId)
        data.setdefault("tick_prices", []).append({"tickType": tickType, "price": price})
        if tickType == 1:
            data["bid"] = price
        elif tickType == 2:
            data["ask"] = price
        elif tickType == 4:
            data["last"] = price
        elif tickType == 9:
            data["close"] = price

    def tickSize(self, reqId, tickType, size):
        data = self._ensure(reqId)
        data.setdefault("tick_sizes", []).append({"tickType": tickType, "size": size})
        if tickType == 0:
            data["bidSize"] = size
        elif tickType == 3:
            data["askSize"] = size
        elif tickType == 5:
            data["lastSize"] = size

    def tickSnapshotEnd(self, reqId: int):
        data = self._ensure(reqId)
        data["snapshot_end"] = True

    def _ensure(self, reqId: int) -> dict:
        key = str(reqId)
        if key not in self.symbols:
            self.symbols[key] = {"reqId": reqId}
        return self.symbols[key]


def main() -> int:
    tests = {
        1: ("AAPL_STK", make_stock("AAPL", primary="NASDAQ")),
        2: ("SPY_ETF", make_stock("SPY", primary="ARCA")),
        3: ("AAPL_OPT_20260417_200C", make_option("AAPL", "20260417", 200, "C")),
        4: ("EURUSD_FX", make_fx("EUR")),
        5: ("BTCUSD_CRYPTO", make_crypto("BTC")),
    }

    app = Probe()
    app.connect("127.0.0.1", 4002, clientId=193)
    t = threading.Thread(target=app.run, daemon=True)
    t.start()

    time.sleep(2)
    if app.isConnected():
        app.reqMarketDataType(1)
        app.reqCurrentTime()

    for req_id, (_, contract) in tests.items():
        app.reqMktData(req_id, contract, "", True, False, [])

    time.sleep(8)

    for req_id in tests:
        try:
            app.cancelMktData(req_id)
        except Exception:
            pass

    time.sleep(1)
    try:
        app.disconnect()
    except Exception:
        pass

    results = {}
    for req_id, (name, _) in tests.items():
        raw = app.symbols.get(str(req_id), {"reqId": req_id})
        results[name] = {
            "reqId": req_id,
            "bid": raw.get("bid"),
            "ask": raw.get("ask"),
            "last": raw.get("last"),
            "close": raw.get("close"),
            "bidSize": raw.get("bidSize"),
            "askSize": raw.get("askSize"),
            "lastSize": raw.get("lastSize"),
            "snapshot_end": raw.get("snapshot_end", False),
            "has_any_tick": bool(raw.get("tick_prices") or raw.get("tick_sizes")),
        }

    payload = {
        "schema_version": "ibkr_marketdata_probe_status_v2",
        "checked_utc": utc_now(),
        "provider": "ibkr",
        "host": "127.0.0.1",
        "port": 4002,
        "client_id": 193,
        "connected": app.connected_ok,
        "managed_accounts": app.managed_accounts,
        "server_time": app.server_time,
        "symbols": results,
        "errors": app.errors,
    }
    ARTIFACT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
