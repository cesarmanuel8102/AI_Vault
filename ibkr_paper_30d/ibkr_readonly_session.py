from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.execution import ExecutionFilter
from ibapi.message import OUT
from ibapi.wrapper import EWrapper

from .canonical import canonical_bytes
from .ibkr_readonly import expected_identity_hash


class ReadOnlyTransportViolation(PermissionError):
    pass


class ReadOnlyMessageGuard:
    ALLOWED_MESSAGE_IDS = frozenset(
        {
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
            OUT.REQ_CONTRACT_DATA,
            OUT.REQ_TICK_BY_TICK_DATA,
            OUT.CANCEL_TICK_BY_TICK_DATA,
        }
    )

    @classmethod
    def validate(cls, message: str) -> int:
        try:
            message_id = int(message.split("\0", 1)[0])
        except (TypeError, ValueError) as exc:
            raise ReadOnlyTransportViolation("unparseable IB API message") from exc
        if message_id not in cls.ALLOWED_MESSAGE_IDS:
            raise ReadOnlyTransportViolation(
                f"IB API message id {message_id} is outside the read-only allowlist"
            )
        return message_id


@dataclass(frozen=True)
class IdentityBindingReceipt:
    account_sha256: str
    account_fingerprint: str
    path: Path
    acl_protected: bool


class ExpectedPaperIdentityStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def bind(
        self,
        account_id: str,
        *,
        host: str,
        port: int,
        gateway_mode: str,
        managed_account_count: int,
    ) -> IdentityBindingReceipt:
        normalized = account_id.strip().upper()
        if not normalized.startswith("DU"):
            raise ValueError("paper account identity must use the DU namespace")
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("paper Gateway must be local")
        if port != 4002:
            raise ValueError("paper Gateway port mismatch")
        if gateway_mode.lower() != "p":
            raise ValueError("Gateway paper mode is not proven")
        if managed_account_count != 1:
            raise ValueError("exactly one managed account is required")

        digest = expected_identity_hash(normalized)
        if self.path.exists():
            existing = self.load_hash()
            if existing != digest:
                raise ValueError("expected paper identity is already bound")
            return IdentityBindingReceipt(
                digest, digest[:16], self.path, self._protect_file()
            )
        payload = {
            "schema": "EXPECTED_PAPER_ACCOUNT_IDENTITY_V1",
            "account_sha256": digest,
            "account_fingerprint": digest[:16],
            "host": "127.0.0.1",
            "port": 4002,
            "gateway_mode": "PAPER",
            "managed_account_count": 1,
            "bound_at_utc": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(canonical_bytes(payload))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return IdentityBindingReceipt(
            digest, digest[:16], self.path, self._protect_file()
        )

    def load_hash(self) -> str:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema") != "EXPECTED_PAPER_ACCOUNT_IDENTITY_V1":
            raise ValueError("unexpected identity schema")
        digest = str(payload.get("account_sha256", ""))
        if len(digest) != 64:
            raise ValueError("invalid expected identity hash")
        return digest

    def _protect_file(self) -> bool:
        self.path.chmod(stat.S_IREAD | stat.S_IWRITE)
        if os.name != "nt":
            return True
        username = os.environ.get("USERNAME", "")
        if not username:
            return False
        icacls = (
            Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
            / "System32"
            / "icacls.exe"
        )
        result = subprocess.run(
            [
                str(icacls),
                str(self.path),
                "/inheritance:r",
                "/grant:r",
                f"{username}:(R,W)",
                "SYSTEM:(F)",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0


@dataclass(frozen=True)
class QuoteObservation:
    symbol: str
    market_data_type: int | None
    bid: float | None
    ask: float | None
    last: float | None
    receipt_timestamp_utc: str | None
    snapshot_complete: bool


@dataclass(frozen=True)
class ReadOnlyBrokerEvidence:
    connected: bool
    authenticated: bool
    server_version: int | None
    connection_time: str | None
    managed_accounts: tuple[str, ...]
    account_summary: dict[str, dict[str, str]]
    positions: tuple[dict[str, object], ...]
    open_orders: tuple[dict[str, object], ...]
    executions: tuple[dict[str, object], ...]
    quotes: tuple[QuoteObservation, ...]
    server_timestamp_utc: str | None
    heartbeat_ok: bool
    query_completeness: dict[str, bool]
    errors: tuple[dict[str, object], ...]
    outbound_message_ids: tuple[int, ...]


class _ReadOnlyIBClient(EWrapper, EClient):
    def __init__(self) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.managed_accounts_event = threading.Event()
        self.account_summary_event = threading.Event()
        self.account_values_event = threading.Event()
        self.positions_event = threading.Event()
        self.open_orders_event = threading.Event()
        self.executions_event = threading.Event()
        self.current_time_event = threading.Event()
        self.managed_accounts_value: tuple[str, ...] = ()
        self.account_summary_value: dict[str, dict[str, str]] = {}
        self.positions_value: list[dict[str, object]] = []
        self.open_orders_value: list[dict[str, object]] = []
        self.executions_value: list[dict[str, object]] = []
        self.quote_values: dict[int, dict[str, Any]] = {}
        self.quote_events: dict[int, threading.Event] = {}
        self.server_timestamp: int | None = None
        self.error_values: list[dict[str, object]] = []
        self.outbound_message_ids: list[int] = []

    def sendMsg(self, msg: str) -> None:
        message_id = ReadOnlyMessageGuard.validate(msg)
        self.outbound_message_ids.append(message_id)
        super().sendMsg(msg)

    def nextValidId(self, orderId: int) -> None:
        self.ready.set()

    def managedAccounts(self, accountsList: str) -> None:
        self.managed_accounts_value = tuple(
            account.strip() for account in accountsList.split(",") if account.strip()
        )
        self.managed_accounts_event.set()

    def accountSummary(
        self, reqId: int, account: str, tag: str, value: str, currency: str
    ) -> None:
        self.account_summary_value.setdefault(account, {})[tag] = value

    def accountSummaryEnd(self, reqId: int) -> None:
        self.account_summary_event.set()

    def updateAccountValue(
        self, key: str, value: str, currency: str, accountName: str
    ) -> None:
        self.account_summary_value.setdefault(accountName, {})[key] = value

    def accountDownloadEnd(self, accountName: str) -> None:
        self.account_values_event.set()

    def position(self, account: str, contract: object, position: object, avgCost: float) -> None:
        self.positions_value.append(
            {
                "account": account,
                "contract_id": int(getattr(contract, "conId", 0)),
                "symbol": str(getattr(contract, "symbol", "")),
                "security_type": str(getattr(contract, "secType", "")),
                "currency": str(getattr(contract, "currency", "")),
                "quantity": str(position),
            }
        )

    def positionEnd(self) -> None:
        self.positions_event.set()

    def openOrder(
        self, orderId: int, contract: object, order: object, orderState: object
    ) -> None:
        self.open_orders_value.append(
            {
                "broker_order_id": orderId,
                "contract_id": int(getattr(contract, "conId", 0)),
                "symbol": str(getattr(contract, "symbol", "")),
                "status": str(getattr(orderState, "status", "")),
                "perm_id": int(getattr(order, "permId", 0)),
            }
        )

    def openOrderEnd(self) -> None:
        self.open_orders_event.set()

    def execDetails(self, reqId: int, contract: object, execution: object) -> None:
        self.executions_value.append(
            {
                "execution_id_sha256": hashlib.sha256(
                    str(getattr(execution, "execId", "")).encode("utf-8")
                ).hexdigest(),
                "contract_id": int(getattr(contract, "conId", 0)),
                "symbol": str(getattr(contract, "symbol", "")),
                "quantity": str(getattr(execution, "shares", "")),
                "price": str(getattr(execution, "price", "")),
            }
        )

    def execDetailsEnd(self, reqId: int) -> None:
        self.executions_event.set()

    def currentTime(self, time_value: int) -> None:
        self.server_timestamp = time_value
        self.current_time_event.set()

    def marketDataType(self, reqId: int, marketDataType: int) -> None:
        self.quote_values.setdefault(reqId, {})["market_data_type"] = marketDataType

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib: object) -> None:
        fields = {1: "bid", 2: "ask", 4: "last"}
        field = fields.get(tickType)
        if field is not None and price > 0:
            quote = self.quote_values.setdefault(reqId, {})
            quote[field] = price
            quote["receipt_timestamp_utc"] = datetime.now(timezone.utc).isoformat()

    def tickSnapshotEnd(self, reqId: int) -> None:
        self.quote_events.setdefault(reqId, threading.Event()).set()

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        self.error_values.append(
            {"request_id": reqId, "code": errorCode, "message": errorString[:300]}
        )


class IBKRReadOnlySessionCollector:
    ACCOUNT_TAGS = "AccountType,TotalCashValue,SettledCash,BuyingPower,NetLiquidation"

    def collect(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 19731,
        timeout_seconds: float = 15.0,
        symbols: tuple[str, ...] = ("SPY", "QQQ"),
    ) -> ReadOnlyBrokerEvidence:
        client = _ReadOnlyIBClient()
        thread: threading.Thread | None = None
        try:
            client.connect(host, port, client_id)
            if not client.isConnected():
                raise ConnectionError("IBKR Gateway connection failed")
            thread = threading.Thread(target=client.run, daemon=True)
            thread.start()
            if not client.ready.wait(timeout_seconds):
                raise TimeoutError("IBKR API handshake timed out")

            client.reqManagedAccts()
            if not client.managed_accounts_event.wait(timeout_seconds):
                raise TimeoutError("IBKR managed accounts request timed out")
            if len(client.managed_accounts_value) == 1:
                client.reqAccountUpdates(True, client.managed_accounts_value[0])
            client.reqAccountSummary(7001, "All", self.ACCOUNT_TAGS)
            client.reqPositions()
            client.reqAllOpenOrders()
            client.reqExecutions(7002, ExecutionFilter())
            client.reqCurrentTime()
            client.reqMarketDataType(3)
            for offset, symbol in enumerate(symbols):
                request_id = 7100 + offset
                contract = Contract()
                contract.symbol = symbol
                contract.secType = "STK"
                contract.exchange = "SMART"
                contract.currency = "USD"
                client.quote_values[request_id] = {"symbol": symbol}
                client.quote_events[request_id] = threading.Event()
                client.reqMktData(request_id, contract, "", True, False, [])

            events = {
                "managed_accounts": client.managed_accounts_event,
                "account_summary": client.account_summary_event,
                "account_values": client.account_values_event,
                "positions": client.positions_event,
                "open_orders": client.open_orders_event,
                "executions": client.executions_event,
                "current_time": client.current_time_event,
            }
            deadline = time.monotonic() + timeout_seconds
            for event in (*events.values(), *client.quote_events.values()):
                event.wait(max(0.0, deadline - time.monotonic()))

            client.cancelAccountSummary(7001)
            if len(client.managed_accounts_value) == 1:
                client.reqAccountUpdates(False, client.managed_accounts_value[0])
            client.cancelPositions()
            for request_id in client.quote_events:
                client.cancelMktData(request_id)

            quotes = tuple(
                QuoteObservation(
                    symbol=str(value.get("symbol", "")),
                    market_data_type=value.get("market_data_type"),
                    bid=value.get("bid"),
                    ask=value.get("ask"),
                    last=value.get("last"),
                    receipt_timestamp_utc=value.get("receipt_timestamp_utc"),
                    snapshot_complete=client.quote_events[request_id].is_set(),
                )
                for request_id, value in sorted(client.quote_values.items())
            )
            server_timestamp = (
                datetime.fromtimestamp(client.server_timestamp, timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
                if client.server_timestamp is not None
                else None
            )
            return ReadOnlyBrokerEvidence(
                connected=client.isConnected(),
                authenticated=client.ready.is_set(),
                server_version=client.serverVersion(),
                connection_time=(
                    client.twsConnectionTime().decode("ascii", errors="replace")
                    if isinstance(client.twsConnectionTime(), bytes)
                    else client.twsConnectionTime()
                ),
                managed_accounts=client.managed_accounts_value,
                account_summary=client.account_summary_value,
                positions=tuple(client.positions_value),
                open_orders=tuple(client.open_orders_value),
                executions=tuple(client.executions_value),
                quotes=quotes,
                server_timestamp_utc=server_timestamp,
                heartbeat_ok=client.current_time_event.is_set(),
                query_completeness={
                    name: event.is_set() for name, event in events.items()
                },
                errors=tuple(client.error_values),
                outbound_message_ids=tuple(client.outbound_message_ids),
            )
        finally:
            if client.isConnected():
                client.disconnect()
            if thread is not None:
                thread.join(timeout=2)
