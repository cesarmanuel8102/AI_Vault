from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from ibapi.wrapper import EWrapper


def expected_identity_hash(account_id: str) -> str:
    normalized = account_id.strip().upper()
    if not normalized:
        raise ValueError("account identity cannot be empty")
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class ReadOnlySessionSnapshot:
    port: int
    connected: bool
    authenticated: bool
    paper_trading_mode: bool
    managed_accounts: tuple[str, ...]
    connector_account_hash: str | None
    cash: str | None
    settled_cash: str | None
    position_count: int | None
    open_order_count: int | None
    execution_visibility: str
    market_data_entitlements: str
    server_timestamp_utc: datetime | None
    heartbeat_ok: bool


@dataclass(frozen=True)
class IdentityEvidence:
    paper_identity_proven: bool
    event_type: str
    reason_codes: tuple[str, ...]
    account_fingerprint: str
    factor_count: int


@dataclass(frozen=True)
class ReadOnlyInspection:
    status: str
    reason_codes: tuple[str, ...]
    identity: IdentityEvidence
    cash: str | None
    settled_cash: str | None
    position_count: int | None
    open_order_count: int | None
    execution_visibility: str
    market_data_entitlements: str
    server_timestamp_utc: datetime | None
    heartbeat_ok: bool


class ReadOnlySnapshotCollector(EWrapper):
    """Official API callback sink with no network or command-sending surface."""

    def __init__(self) -> None:
        super().__init__()
        self.managed_accounts: tuple[str, ...] = ()
        self.account_values: dict[str, str] = {}
        self.position_contract_ids: set[int] = set()
        self.open_order_ids: set[int] = set()
        self.execution_ids: set[str] = set()
        self.server_time: int | None = None
        self.errors: list[tuple[int, int, str]] = []

    def managedAccounts(self, accountsList: str) -> None:
        self.managed_accounts = tuple(
            account.strip() for account in accountsList.split(",") if account.strip()
        )

    def accountSummary(
        self, reqId: int, account: str, tag: str, value: str, currency: str
    ) -> None:
        self.account_values[f"{tag}:{currency}"] = value

    def position(self, account: str, contract: object, position: object, avgCost: float) -> None:
        contract_id = getattr(contract, "conId", None)
        if isinstance(contract_id, int):
            self.position_contract_ids.add(contract_id)

    def openOrder(self, orderId: int, contract: object, order: object, orderState: object) -> None:
        self.open_order_ids.add(orderId)

    def execDetails(self, reqId: int, contract: object, execution: object) -> None:
        execution_id = getattr(execution, "execId", None)
        if execution_id:
            self.execution_ids.add(str(execution_id))

    def currentTime(self, time: int) -> None:
        self.server_time = time

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        self.errors.append((reqId, errorCode, errorString))


class IBKRReadOnlyAdapter:
    """Validates already-collected observations and owns no API connection."""

    def __init__(self, expected_account_hash: str):
        if len(expected_account_hash) != 64:
            raise ValueError("expected account identity must be a SHA-256 digest")
        self.expected_account_hash = expected_account_hash.lower()

    def prove_identity(self, session: ReadOnlySessionSnapshot) -> IdentityEvidence:
        reasons: list[str] = []
        if session.port != 4002:
            reasons.append("PAPER_PORT_MISMATCH")
        if not session.connected:
            reasons.append("BROKER_DISCONNECTED")
        if not session.authenticated:
            reasons.append("BROKER_AUTH_NOT_PROVEN")
        if not session.paper_trading_mode:
            reasons.append("PAPER_MODE_NOT_PROVEN")
        if len(session.managed_accounts) != 1:
            reasons.append("MANAGED_ACCOUNT_COUNT_INVALID")

        account_hash = ""
        if len(session.managed_accounts) == 1:
            account_hash = expected_identity_hash(session.managed_accounts[0])
            if account_hash != self.expected_account_hash:
                reasons.append("ACCOUNT_IDENTITY_MISMATCH")
        if (
            session.connector_account_hash is not None
            and session.connector_account_hash != self.expected_account_hash
        ):
            reasons.append("CONNECTOR_IDENTITY_MISMATCH")
        if not session.heartbeat_ok:
            reasons.append("BROKER_HEARTBEAT_TIMEOUT")
        proven = not reasons
        fingerprint_source = account_hash or self.expected_account_hash
        return IdentityEvidence(
            paper_identity_proven=proven,
            event_type=(
                "PAPER_IDENTITY_PROVEN" if proven else "POSSIBLE_LIVE_CONNECTION"
            ),
            reason_codes=tuple(reasons),
            account_fingerprint=fingerprint_source[:16],
            factor_count=7,
        )

    def inspect(self, session: ReadOnlySessionSnapshot) -> ReadOnlyInspection:
        identity = self.prove_identity(session)
        reasons = list(identity.reason_codes)
        if session.server_timestamp_utc is None:
            reasons.append("SERVER_TIMESTAMP_UNAVAILABLE")
        if session.position_count is None:
            reasons.append("POSITIONS_VISIBILITY_UNAVAILABLE")
        if session.open_order_count is None:
            reasons.append("OPEN_ORDERS_VISIBILITY_UNAVAILABLE")
        if session.execution_visibility != "AVAILABLE":
            reasons.append("EXECUTION_VISIBILITY_UNAVAILABLE")
        return ReadOnlyInspection(
            status="BLOCK" if reasons else "PASS",
            reason_codes=tuple(reasons),
            identity=identity,
            cash=session.cash,
            settled_cash=session.settled_cash,
            position_count=session.position_count,
            open_order_count=session.open_order_count,
            execution_visibility=session.execution_visibility,
            market_data_entitlements=session.market_data_entitlements,
            server_timestamp_utc=session.server_timestamp_utc,
            heartbeat_ok=session.heartbeat_ok,
        )
