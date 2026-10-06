"""Concrete production composition for Continuity V3 in IBKR PAPER."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from .broker_write_coordinator import BrokerWriteCoordinator
from .canonical import sha256_json
from .continuity_store import ContinuityStore
from .ibkr_readonly import expected_identity_hash


WRITER_CLIENT_ID = 19761
OBSERVER_CLIENT_ID = 19762
DEFAULT_SMTP_CONFIG = Path("Secrets/email_alerts.env")


class ProductionRuntimeConfigurationError(RuntimeError):
    pass


def validate_production_runtime_configuration(config: Any) -> dict[str, Path]:
    repo_root = Path(config.repo_root).resolve()
    smtp_config = repo_root / DEFAULT_SMTP_CONFIG
    if not smtp_config.is_file():
        raise ProductionRuntimeConfigurationError(
            "EXTERNAL_ALERT_CONFIGURATION_MISSING"
        )
    return {"smtp_config": smtp_config}


def build_ibkr_session_factory(
    *,
    host: str,
    port: int,
    expected_account_hash: str,
    client_id: int,
    read_only: bool,
    ib_factory: Callable[[], Any] | None = None,
) -> Callable[[], Any]:
    if client_id not in {WRITER_CLIENT_ID, OBSERVER_CLIENT_ID}:
        raise ProductionRuntimeConfigurationError("IBKR_CLIENT_ID_NOT_AUTHORIZED")
    if read_only is not (client_id == OBSERVER_CLIENT_ID):
        raise ProductionRuntimeConfigurationError("IBKR_CLIENT_MODE_MISMATCH")
    if len(expected_account_hash) != 64:
        raise ProductionRuntimeConfigurationError("PAPER_ACCOUNT_HASH_INVALID")

    def create() -> Any:
        if ib_factory is None:
            from ib_insync import IB

            broker = IB()
        else:
            broker = ib_factory()
        try:
            broker.connect(
                host,
                int(port),
                clientId=client_id,
                timeout=20.0,
                readonly=read_only,
            )
            if broker.isConnected() is not True:
                raise ConnectionError("IBKR_PAPER_CONNECTION_FAILED")
            accounts = tuple(str(value) for value in broker.managedAccounts())
            if len(accounts) != 1 or not accounts[0].upper().startswith("DU"):
                raise PermissionError("SINGLE_PAPER_ACCOUNT_REQUIRED")
            if expected_identity_hash(accounts[0]) != expected_account_hash:
                raise PermissionError("PAPER_ACCOUNT_IDENTITY_MISMATCH")
            broker.client_id = client_id
            broker.read_only = read_only
            broker.all_order_visibility = True
            return broker
        except BaseException:
            try:
                broker.disconnect()
            except Exception:
                pass
            raise

    return create


def create_broker_write_coordinator() -> BrokerWriteCoordinator:
    return BrokerWriteCoordinator()


def create_continuity_store(db: Any) -> ContinuityStore:
    return ContinuityStore(db)


def _current_head(repo_root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def _accepted_result_sha256(db_path: Path, invocation_id: str) -> str:
    from .persistence import Database

    with Database.open(db_path) as db:
        row = db.execute(
            "SELECT accepted,payload_sha256 FROM trader_results "
            "WHERE invocation_id=? ORDER BY rowid DESC LIMIT 1",
            (invocation_id,),
        ).fetchone()
    if row is None or int(row[0]) != 1:
        raise ProductionRuntimeConfigurationError("ACCEPTED_RESULT_NOT_DURABLE")
    return str(row[1])


def _invocation_id(db_path: Path, decision_cycle_id: str) -> str:
    from .persistence import Database

    with Database.open(db_path) as db:
        row = db.execute(
            "SELECT invocation_id FROM trader_invocations "
            "WHERE decision_cycle_id=? ORDER BY rowid DESC LIMIT 1",
            (decision_cycle_id,),
        ).fetchone()
    if row is None:
        raise ProductionRuntimeConfigurationError("INVOCATION_ID_NOT_DURABLE")
    return str(row[0])


def _sequence_allocator(coordinator: BrokerWriteCoordinator) -> Callable[[], int]:
    lock = getattr(coordinator, "_production_sequence_lock", None)
    if lock is None:
        lock = threading.Lock()
        coordinator._production_sequence_lock = lock
        coordinator._production_sequence = 0

    def allocate() -> int:
        with lock:
            coordinator._production_sequence += 1
            return int(coordinator._production_sequence)

    return allocate


def create_model_executor(
    *,
    coordinator: BrokerWriteCoordinator,
    db_path: Path,
    config: Any,
    preflight: Any,
    production_validation_sha256: str | None,
) -> Any:
    from .coordinated_model_executor import CoordinatedModelExecutor

    approved_head = _current_head(Path(config.repo_root))
    return CoordinatedModelExecutor(
        coordinator=coordinator,
        launch_attempt_id=str(config.launch_attempt_id),
        epoch_id=str(config.target_successor_epoch_id or "AUTONOMY_EPOCH_1"),
        approved_head=approved_head,
        account_identity_sha256=str(preflight.expected_account_hash),
        accepted_result_sha256_reader=lambda invocation_id: _accepted_result_sha256(
            Path(db_path), invocation_id
        ),
        invocation_id_reader=lambda bundle: _invocation_id(
            Path(db_path), bundle.decision_cycle_id
        ),
        durable_sequence_allocator=_sequence_allocator(coordinator),
        now_utc=lambda: datetime.now(timezone.utc),
        result_timeout_seconds=300.0,
        production_validation_sha256=production_validation_sha256,
    )


class _DurableNewOrderAuthority:
    def __init__(self, db: Any) -> None:
        self.db = db

    def revoke_new_orders(self, correlation_id: str) -> None:
        from .experiment_control import KillSwitchStore

        store = KillSwitchStore(self.db)
        if store.current() == "KILL_SWITCH_TRIGGERED":
            return
        with self.db.transaction():
            store.set(
                "KILL_SWITCH_TRIGGERED",
                reason=f"critical runtime event {correlation_id}",
                actor="CONTINUITY_V3_RUNTIME",
            )


class ProductionCriticalAlertReporter:
    def __init__(
        self,
        *,
        db_path: Path,
        smtp_config_path: Path,
        launch_attempt_id: str,
        smtp_factory: Callable[[Path], Any] | None = None,
        event_log_factory: Callable[[], Any] | None = None,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.smtp_config_path = Path(smtp_config_path)
        self.launch_attempt_id = launch_attempt_id
        self.smtp_factory = smtp_factory
        self.event_log_factory = event_log_factory
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def __call__(self, reason_code: str) -> None:
        from .alerts import (
            CRITICAL_EVENT_TYPES,
            AlertEvent,
            AlertRepository,
            AlertService,
            WindowsEventLogChannel,
            load_smtp_channel,
        )
        from .persistence import Database

        event_type = (
            reason_code if reason_code in CRITICAL_EVENT_TYPES else "FAIL_CLOSED"
        )
        fingerprint = hashlib.sha256(
            f"{self.launch_attempt_id}:{reason_code}".encode("utf-8")
        ).hexdigest()[:32]
        correlation_id = f"continuity-v3-{fingerprint}"
        with Database.open(self.db_path) as db:
            authority = _DurableNewOrderAuthority(db)
            authority.revoke_new_orders(correlation_id)
            repository = AlertRepository(db)
            if repository.exists(f"alert-{correlation_id}"):
                return
            smtp = (
                load_smtp_channel(self.smtp_config_path)
                if self.smtp_factory is None
                else self.smtp_factory(self.smtp_config_path)
            )
            event_log = (
                WindowsEventLogChannel()
                if self.event_log_factory is None
                else self.event_log_factory()
            )
            service = AlertService(
                repository, authority, smtp, event_log
            )
            result = service.raise_critical(
                AlertEvent(
                    event_type=event_type,
                    correlation_id=correlation_id,
                    occurred_at_utc=self.now_utc(),
                    detail=f"runtime_reason_code={reason_code}",
                )
            )
            if result.external_status not in {"CONFIRMED", "RETRY_SCHEDULED"}:
                raise RuntimeError("EXTERNAL_OWNER_ALERT_NOT_DURABLE")


def create_critical_alert_reporter(
    *, db_path: Path, config: Any, preflight: Any
) -> ProductionCriticalAlertReporter:
    paths = validate_production_runtime_configuration(config)
    return ProductionCriticalAlertReporter(
        db_path=Path(db_path),
        smtp_config_path=paths["smtp_config"],
        launch_attempt_id=str(config.launch_attempt_id),
    )


def _canonical_contract(contract: Any) -> dict[str, Any]:
    return {
        "conId": int(getattr(contract, "conId", 0) or 0),
        "symbol": str(getattr(contract, "symbol", "") or ""),
        "localSymbol": str(getattr(contract, "localSymbol", "") or ""),
        "secType": str(getattr(contract, "secType", "") or ""),
        "exchange": str(getattr(contract, "exchange", "") or ""),
        "currency": str(getattr(contract, "currency", "") or ""),
        "expiry": str(
            getattr(contract, "lastTradeDateOrContractMonth", "") or ""
        ),
        "strike": str(getattr(contract, "strike", 0) or 0),
        "right": str(getattr(contract, "right", "") or ""),
        "multiplier": str(getattr(contract, "multiplier", "") or "1"),
    }


def _canonical_positions(values: list[Any]) -> list[dict[str, Any]]:
    result = []
    for value in values:
        result.append(
            {
                "account_identity_sha256": expected_identity_hash(
                    str(getattr(value, "account", "") or "")
                ),
                "position": str(getattr(value, "position", 0) or 0),
                "average_cost": str(getattr(value, "avgCost", 0) or 0),
                "contract": _canonical_contract(getattr(value, "contract", None)),
            }
        )
    return sorted(result, key=sha256_json)


def _canonical_executions(values: list[Any]) -> list[dict[str, Any]]:
    result = []
    for value in values:
        execution = getattr(value, "execution", value)
        contract = getattr(value, "contract", None)
        result.append(
            {
                "exec_id_sha256": hashlib.sha256(
                    str(getattr(execution, "execId", "") or "").encode("utf-8")
                ).hexdigest(),
                "order_id": int(getattr(execution, "orderId", 0) or 0),
                "perm_id": int(getattr(execution, "permId", 0) or 0),
                "client_id": int(getattr(execution, "clientId", 0) or 0),
                "side": str(getattr(execution, "side", "") or ""),
                "shares": str(getattr(execution, "shares", 0) or 0),
                "price": str(getattr(execution, "price", 0) or 0),
                "time": str(getattr(execution, "time", "") or ""),
                "contract": _canonical_contract(contract),
            }
        )
    return sorted(result, key=sha256_json)


class ReadOnlyContinuityBroker:
    """Narrow observer surface for factual continuity collection only."""

    read_only = True
    client_id = OBSERVER_CLIENT_ID
    environment = "PAPER"
    all_order_visibility = True

    def __init__(self, broker: Any, *, account_identity_sha256: str) -> None:
        self._broker = broker
        self.account_identity_sha256 = account_identity_sha256

    def reqCurrentTime(self) -> datetime:
        return self._broker.reqCurrentTime()

    def disconnect(self) -> None:
        self._broker.disconnect()

    def _matching_order(self, binding: Any) -> dict[str, Any] | None:
        from .open_order_management import canonical_open_order

        matches = []
        for trade in self._broker.reqAllOpenOrders():
            snapshot = canonical_open_order(trade)
            if (
                snapshot["orderRef"] == binding.order_ref
                and snapshot["orderId"] == int(binding.ibkr_order_id or 0)
                and snapshot["permId"] == int(binding.perm_id or 0)
                and snapshot["clientId"] == int(binding.execution_client_id)
                and expected_identity_hash(snapshot["account"])
                == binding.account_identity_sha256
                and sha256_json(snapshot["contract"])
                == binding.contract_identity_sha256
            ):
                matches.append(snapshot)
        if len(matches) > 1:
            raise RuntimeError("OPEN_ORDER_IDENTITY_AMBIGUOUS")
        return None if not matches else matches[0]

    def current_order_snapshot(self, binding: Any) -> dict[str, Any] | None:
        return self._matching_order(binding)

    def collect_continuity_facts(
        self, binding: Any, now: datetime
    ) -> dict[str, dict[str, Any]]:
        snapshot = self._matching_order(binding)
        source = "IBKR_PAPER_READ_ONLY_CLIENT_19762"

        def fact(value: Any, max_age_seconds: int = 15) -> dict[str, Any]:
            return {
                "value": value,
                "source": source,
                "collected_at_utc": now,
                "max_age_seconds": max_age_seconds,
            }

        values: dict[str, dict[str, Any]] = {
            "MARKET_SESSION_STATE": fact("UNKNOWN", 30),
        }
        if snapshot is None:
            values.update(
                {
                    "ORDER_STATUS": fact("ABSENT"),
                    "ORDER_FILLED_QUANTITY": fact("0"),
                    "ORDER_REMAINING_QUANTITY": fact("0"),
                    "ORDER_TOTAL_QUANTITY": fact("0"),
                }
            )
        else:
            raw_status = str(snapshot["status"] or "").upper()
            filled = Decimal(str(snapshot["filled"]))
            if raw_status in {"PENDINGCANCEL", "PENDING_CANCEL"}:
                order_state = "PENDING_CANCEL"
            elif raw_status in {"CANCELLED", "APICANCELLED"}:
                order_state = "CANCELLED"
            elif raw_status in {"REJECTED", "INACTIVE"}:
                order_state = "REJECTED"
            elif raw_status == "FILLED":
                order_state = "FILLED"
            elif filled > 0:
                order_state = "PARTIALLY_FILLED"
            else:
                order_state = "UNFILLED"
            values.update(
                {
                    "ORDER_STATUS": fact(order_state),
                    "ORDER_FILLED_QUANTITY": fact(snapshot["filled"]),
                    "ORDER_REMAINING_QUANTITY": fact(snapshot["remaining"]),
                    "ORDER_TOTAL_QUANTITY": fact(snapshot["totalQuantity"]),
                }
            )

        quantity = Decimal("0")
        for position in self._broker.positions():
            account = str(getattr(position, "account", "") or "")
            from .open_order_management import canonical_contract_identity

            contract = canonical_contract_identity(
                getattr(position, "contract", None)
            )
            if (
                expected_identity_hash(account) == binding.account_identity_sha256
                and sha256_json(contract) == binding.contract_identity_sha256
            ):
                quantity += Decimal(str(getattr(position, "position", 0) or 0))
        values["POSITION_EXISTS"] = fact(quantity != 0)
        values["POSITION_QUANTITY"] = fact(str(quantity))
        return values


def _latest_broker_observation(db: Any) -> dict[str, Any]:
    row = db.execute(
        "SELECT payload_json,payload_sha256 FROM state_events "
        "WHERE event_type='BROKER_AUTHORITY_OBSERVATION_V1' "
        "ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise ProductionRuntimeConfigurationError("BROKER_AUTHORITY_OBSERVATION_MISSING")
    payload = json.loads(str(row[0]))
    if sha256_json(payload) != str(row[1]):
        raise ProductionRuntimeConfigurationError("BROKER_AUTHORITY_OBSERVATION_CORRUPT")
    return payload


class _ProductionSnapshotReader:
    def __init__(
        self,
        *,
        db_path: Path,
        config: Any,
        preflight: Any,
        execution_lock_verifier: Callable[[], bool],
    ) -> None:
        self.db_path = Path(db_path)
        self.config = config
        self.preflight = preflight
        self.execution_lock_verifier = execution_lock_verifier

    def __call__(self, request: Any) -> Any:
        from .broker_write_coordinator import AuthorizedBrokerCommand
        from .coordinated_model_executor import ModelExecutionRequest
        from .experiment_control import (
            ExperimentClockStore,
            KillSwitchStore,
            OwnerAuthorizationStore,
        )
        from .experiment_epoch import ExperimentEpochStore
        from .experiment_ledger import AutonomousExperimentLedger
        from .persistence import Database
        from .production_authority import ProductionAuthoritySnapshot
        from .runtime_provenance import (
            build_approved_runtime_material,
            verify_runtime_provenance,
        )
        from .successor_authorization import validate_successor_authorization_record

        with Database.open(self.db_path) as db:
            store = ContinuityStore(db)
            observation = _latest_broker_observation(db)
            if self.config.target_successor_epoch_id is not None:
                clock = ExperimentClockStore(db).clock_for_epoch(
                    str(self.config.target_successor_epoch_id)
                )
            else:
                clock = ExperimentClockStore(db).load()
            now = datetime.now(timezone.utc)
            clock_active = bool(
                clock is not None and clock.start_utc <= now < clock.end_utc
            )
            if self.config.target_successor_epoch_id is not None:
                try:
                    validate_successor_authorization_record(
                        db=db,
                        epoch_id=str(self.config.target_successor_epoch_id),
                        definition_sha256=str(
                            self.config.target_successor_definition_sha256
                        ),
                        expected_actor_sid=str(self.preflight.owner_sid),
                        receipt=dict(self.preflight.owner_authorization_receipt),
                    )
                    owner_valid = True
                except Exception:
                    owner_valid = False
            else:
                owner_valid = bool(
                    clock is not None
                    and OwnerAuthorizationStore(db).current(
                        clock_event_sha256=clock.event_sha256
                    )
                    == "AUTHORIZED"
                )
            continuity_schema_valid = True
            authority_chains_valid = True
            try:
                store.verify_all_chains()
                ExperimentEpochStore(db).current()
            except Exception:
                continuity_schema_valid = False
                authority_chains_valid = False

            active_plan_sha256 = None
            binding_plan_sha256 = None
            order_state_sha256 = "0" * 64
            execution_count = 0
            review_allows = True
            if isinstance(request, AuthorizedBrokerCommand):
                active = store.active_plan(request.order_ref)
                active_plan_sha256 = None if active is None else active.sha256
                binding = (
                    None
                    if active is None
                    else _verified_registry_binding(db, active)
                )
                if binding is not None:
                    if any(
                        (
                            binding["order_ref"] != request.order_ref,
                            binding["order_id"] != request.order_id,
                            binding["perm_id"] != request.perm_id,
                            binding["execution_client_id"]
                            != request.execution_client_id,
                            binding["account_identity_sha256"]
                            != request.account_identity_sha256,
                            binding["contract_identity_sha256"]
                            != request.contract_identity_sha256,
                        )
                    ):
                        raise ProductionRuntimeConfigurationError(
                            "ORDER_REGISTRY_IDENTITY_MISMATCH"
                        )
                    binding_plan_sha256 = active.sha256
                    order_state_sha256 = str(
                        observation.get("target_order_state_sha256") or "0" * 64
                    )
                execution_count = int(
                    db.execute(
                        "SELECT COUNT(*) FROM continuity_execution_events "
                        "WHERE plan_id=? AND order_ref=?",
                        (request.plan_id, request.order_ref),
                    ).fetchone()[0]
                )
            else:
                order_state_sha256 = str(
                    observation.get("target_order_state_sha256") or "0" * 64
                )

            used_execution_keys = tuple(
                str(json.loads(str(row[0])).get("execution_key") or "")
                for row in db.execute(
                    "SELECT payload_json FROM state_events "
                    "WHERE event_type='BROKER_WRITE_ATTEMPT_V1' ORDER BY sequence"
                ).fetchall()
            )
            accepted_result = getattr(request, "accepted_result_sha256", "0" * 64)
            if isinstance(request, AuthorizedBrokerCommand):
                accepted_result = "0" * 64
            ledger_state = AutonomousExperimentLedger(
                db, allocation=Decimal(str(self.config.initial_allocation))
            ).project()
            capital = ledger_state.equity if ledger_state.valid else Decimal("0")

            provider_state_allows = False
            if isinstance(request, ModelExecutionRequest):
                provider = store.provider_projection(request.invocation_id)
                provider_state_allows = provider.get("state") == "COMPLETED_ACCEPTED"
            elif isinstance(request, AuthorizedBrokerCommand):
                provider_state_allows = store.latest_provider_projection().get(
                    "state"
                ) in {"TIMEOUT_CONFIRMED", "PROCESS_ERROR", "ABANDONED"}

            runtime_provenance_valid = False
            try:
                root = Path(self.config.repo_root)
                head = _current_head(root)
                material = build_approved_runtime_material(root, head)
                runtime_provenance_valid = (
                    verify_runtime_provenance(root, material).get("gate_status")
                    == "PASS"
                )
            except Exception:
                runtime_provenance_valid = False

            auditor_ok = (
                hashlib.sha256(Path(self.config.auditor_receipt_path).read_bytes()).hexdigest()
                == self.preflight.auditor_receipt_sha256
            )
            market_ok = (
                hashlib.sha256(Path(self.config.market_policy_path).read_bytes()).hexdigest()
                == self.preflight.market_policy_sha256
                and hashlib.sha256(
                    Path(self.config.market_validation_path).read_bytes()
                ).hexdigest()
                == self.preflight.market_validation_sha256
            )
            return ProductionAuthoritySnapshot(
                snapshot_id=f"authority-{observation['evidence_id']}",
                observed_at_utc=now,
                lock_owned_by_process=self.execution_lock_verifier() is True,
                approved_head=_current_head(Path(self.config.repo_root)),
                runtime_provenance_valid=runtime_provenance_valid,
                environment="PAPER",
                account_identity_sha256=str(self.preflight.expected_account_hash),
                owner_authorization_valid=owner_valid,
                epoch_id=str(
                    self.config.target_successor_epoch_id or "AUTONOMY_EPOCH_1"
                ),
                clock_active=clock_active,
                kill_switch_clear=(
                    KillSwitchStore(db).current() == "KILL_SWITCH_CLEAR"
                ),
                auditor_gate_pass=auditor_ok,
                market_data_gate_pass=market_ok,
                continuity_schema_valid=continuity_schema_valid,
                authority_chains_valid=authority_chains_valid,
                active_plan_sha256=active_plan_sha256,
                binding_plan_sha256=binding_plan_sha256,
                provider_state_allows=provider_state_allows,
                accepted_result_sha256=str(accepted_result),
                review_allows=review_allows,
                execution_count=execution_count,
                maximum_execution_count=1,
                used_execution_keys=used_execution_keys,
                order_state_sha256=order_state_sha256,
                positions_sha256=str(observation["positions_sha256"]),
                executions_sha256=str(observation["executions_sha256"]),
                experiment_capital_boundary=capital,
                sqlite_write_transaction_active=db.connection.in_transaction,
            )


def _broker_evidence_collector(db_path: Path) -> Callable[..., Any]:
    def collect(broker: Any, request: Any, raw: dict[str, Any]) -> Any:
        from .broker_write_coordinator import AuthorizedBrokerCommand
        from .persistence import Database
        from .production_authority import ProductionBrokerEvidence
        from .repositories import EventRepository

        collected = datetime.now(timezone.utc)
        broker_time = broker.reqCurrentTime()
        if broker_time.tzinfo is None or broker_time.utcoffset() is None:
            broker_time = broker_time.replace(tzinfo=timezone.utc)
        accounts = tuple(str(value) for value in broker.managedAccounts())
        if len(accounts) != 1:
            raise PermissionError("BROKER_ACCOUNT_AMBIGUOUS")
        open_hash = sha256_json(raw["open_orders"])
        positions_hash = sha256_json(_canonical_positions(raw["positions"]))
        executions_hash = sha256_json(_canonical_executions(raw["executions"]))
        target_hash = "0" * 64
        if isinstance(request, AuthorizedBrokerCommand):
            matching = [
                item
                for item in raw["open_orders"]
                if item["orderRef"] == request.order_ref
                and item["orderId"] == request.order_id
                and item["permId"] == request.perm_id
            ]
            if len(matching) != 1:
                raise RuntimeError("TARGET_ORDER_IDENTITY_UNCERTAIN")
            target_hash = str(matching[0]["state_sha256"])
        body = {
            "evidence_id": f"broker-{sha256_json([collected, open_hash])[:24]}",
            "collected_at_utc": collected,
            "broker_time_utc": broker_time,
            "account_identity_sha256": expected_identity_hash(accounts[0]),
            "all_order_visibility": bool(
                getattr(broker, "all_order_visibility", False)
            ),
            "open_orders_sha256": open_hash,
            "positions_sha256": positions_hash,
            "executions_sha256": executions_hash,
            "target_order_state_sha256": target_hash,
        }
        persisted_body = {"schema": "BROKER_AUTHORITY_OBSERVATION_V1", **body}
        evidence_sha256 = sha256_json(persisted_body)
        payload = {**persisted_body, "evidence_sha256": evidence_sha256}
        with Database.open(db_path) as db, db.transaction():
            EventRepository(db).append("BROKER_AUTHORITY_OBSERVATION_V1", payload)
        return ProductionBrokerEvidence(
            **body,
            fresh_until_utc=collected + timedelta(seconds=30),
            evidence_sha256=evidence_sha256,
        )

    return collect


class _LazyProductionModelEngine:
    def __init__(self, *, db_path: Path, toolbox: Any) -> None:
        self.db_path = Path(db_path)
        self.toolbox = toolbox
        self.db = None
        self.engine = None

    def _load(self) -> Any:
        if self.engine is None:
            from .autonomous_execution import WriterOwnedModelExecutionMechanics
            from .continuity_binding import ContinuityBindingService
            from .model_execution_engine import ModelExecutionEngine
            from .persistence import Database

            self.db = Database.open(self.db_path)
            store = ContinuityStore(self.db)
            mechanics = WriterOwnedModelExecutionMechanics(
                self.toolbox,
                armed=True,
                database=self.db,
                fresh_safety_check=lambda scope: (),
                operator_control_check=lambda: (),
                continuity_binding_service=ContinuityBindingService(self.db, store),
            )
            self.engine = ModelExecutionEngine(mechanics=mechanics)
        return self.engine

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self._load().execute(*args, **kwargs)

    def close(self) -> None:
        if self.db is not None:
            self.db.close()
            self.db = None
            self.engine = None


def _request_id(request: Any) -> str:
    return str(getattr(request, "request_id", None) or request.command_id)


def _production_persistence(db_path: Path) -> tuple[Callable[..., None], Callable[..., None]]:
    from .persistence import Database

    def persist_attempt(request: Any, evidence: dict[str, Any]) -> None:
        authority = dict(evidence.get("production_authority") or {})
        with Database.open(db_path) as db:
            ContinuityStore(db).append_production_write_attempt(
                request_id=_request_id(request),
                request_sha256=request.sha256,
                execution_key=request.execution_key,
                authority_snapshot_sha256=str(
                    authority["authority_snapshot_sha256"]
                ),
                broker_evidence_sha256=str(authority["broker_evidence_sha256"]),
                liability_evidence_sha256=authority.get(
                    "liability_evidence_sha256"
                ),
            )

    def persist_result(request: Any, result: Any, evidence: dict[str, Any]) -> None:
        with Database.open(db_path) as db:
            ContinuityStore(db).append_production_write_result(
                request_id=_request_id(request),
                request_sha256=request.sha256,
                execution_key=request.execution_key,
                result_sha256=sha256_json(
                    {
                        "success": result.success,
                        "status": result.status,
                        "reason_codes": result.reason_codes,
                        "order": result.order,
                        "broker_validation": result.broker_validation,
                    }
                ),
                status=result.status,
                success=result.success,
            )

    return persist_attempt, persist_result


def _exact_continuity_maximum_loss(
    broker: Any,
    contract: Any,
    order: Any,
) -> tuple[bool, Decimal | None, tuple[str, ...], list[dict[str, Any]]]:
    from ib_insync import Contract
    from .open_order_management import canonical_contract_identity

    identity = canonical_contract_identity(contract)
    sec_type = str(identity["secType"]).upper()
    action = str(getattr(order, "action", "") or "").upper()
    quantity = Decimal(str(getattr(order, "totalQuantity", 0) or 0))
    limit_price = Decimal(str(getattr(order, "lmtPrice", 0) or 0))
    currency = str(identity["currency"] or "").upper()
    if quantity <= 0 or limit_price <= 0 or len(currency) != 3:
        return False, None, (), []

    combo_legs = list(identity.get("comboLegs") or [])
    if sec_type != "BAG":
        covered = (sha256_json(identity),)
        multiplier = Decimal(str(identity.get("multiplier") or "1"))
        if action == "BUY" and sec_type in {"OPT", "STK"}:
            return True, limit_price * multiplier * quantity, covered, [identity]
        if action == "SELL" and sec_type == "OPT" and identity.get("right") == "P":
            strike = Decimal(str(identity.get("strike") or "0"))
            maximum_loss = max(strike - limit_price, Decimal("0"))
            return True, maximum_loss * multiplier * quantity, covered, [identity]
        return False, None, covered, [identity]

    if not combo_legs:
        return False, None, (), []
    covered = tuple(sha256_json(leg) for leg in combo_legs)
    resolved: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for leg in combo_legs:
        details = list(
            broker.reqContractDetails(
                Contract(
                    conId=int(leg["conId"]),
                    exchange=str(leg.get("exchange") or "SMART"),
                )
            )
        )
        matches = [
            item
            for item in details
            if int(getattr(getattr(item, "contract", None), "conId", 0) or 0)
            == int(leg["conId"])
        ]
        if len(matches) != 1:
            return False, None, covered, []
        resolved.append((leg, canonical_contract_identity(matches[0].contract)))

    terms = [contract_identity for _leg, contract_identity in resolved]
    if any(str(term["secType"]).upper() != "OPT" for term in terms):
        return False, None, covered, terms
    if len({str(term["symbol"]).upper() for term in terms}) != 1:
        return False, None, covered, terms
    if len({str(term["expiry"]) for term in terms}) != 1:
        return False, None, covered, terms
    if {str(term["currency"]).upper() for term in terms} != {currency}:
        return False, None, covered, terms
    multipliers = {Decimal(str(term.get("multiplier") or "1")) for term in terms}
    if len(multipliers) != 1 or next(iter(multipliers)) <= 0:
        return False, None, covered, terms
    multiplier = next(iter(multipliers))

    direction = Decimal("1") if action == "BUY" else Decimal("-1")
    if action not in {"BUY", "SELL"}:
        return False, None, covered, terms
    signed_legs: list[tuple[Decimal, Decimal, str]] = []
    net_upper_slope = Decimal("0")
    strikes: set[Decimal] = set()
    for leg, term in resolved:
        right = str(term["right"]).upper()
        if right not in {"C", "P"}:
            return False, None, covered, terms
        strike = Decimal(str(term["strike"]))
        ratio = Decimal(str(leg["ratio"]))
        leg_direction = (
            Decimal("1")
            if str(leg["action"]).upper() == "BUY"
            else Decimal("-1")
        )
        signed_ratio = direction * leg_direction * ratio
        signed_legs.append((signed_ratio, strike, right))
        strikes.add(strike)
        if right == "C":
            net_upper_slope += signed_ratio
    if net_upper_slope < 0:
        return False, None, covered, terms

    initial_cash = (
        -limit_price * multiplier * quantity
        if action == "BUY"
        else limit_price * multiplier * quantity
    )
    minimum_pnl: Decimal | None = None
    for underlying in sorted({Decimal("0"), *strikes}):
        pnl = initial_cash
        for signed_ratio, strike, right in signed_legs:
            payoff = (
                max(underlying - strike, Decimal("0"))
                if right == "C"
                else max(strike - underlying, Decimal("0"))
            )
            pnl += signed_ratio * payoff * multiplier * quantity
        minimum_pnl = pnl if minimum_pnl is None else min(minimum_pnl, pnl)
    maximum_loss = max(-(minimum_pnl or Decimal("0")), Decimal("0"))
    return True, maximum_loss, covered, terms


def _collect_continuity_liability_evidence(
    broker: Any,
    command: Any,
    _broker_evidence: dict[str, Any],
) -> Any:
    from .continuity_liability import (
        LiabilityEvidenceSource,
        MaximumLiabilityEvidence,
    )
    from .open_order_management import canonical_contract_identity, canonical_open_order

    matches = []
    for trade in broker.reqAllOpenOrders():
        snapshot = canonical_open_order(trade)
        if (
            snapshot["orderRef"] == command.order_ref
            and snapshot["orderId"] == command.ibkr_order_id
            and snapshot["permId"] == command.perm_id
            and snapshot["clientId"] == command.execution_client_id
            and expected_identity_hash(snapshot["account"])
            == command.account_identity_sha256
            and sha256_json(snapshot["contract"])
            == command.contract_identity_sha256
        ):
            matches.append((trade, snapshot))
    if len(matches) != 1:
        raise ProductionRuntimeConfigurationError(
            "LIABILITY_ORDER_IDENTITY_UNCERTAIN"
        )
    trade, snapshot = matches[0]
    proposed_order = copy.deepcopy(trade.order)
    proposed_order.totalQuantity = float(command.resolved_total_quantity)
    proposed_order.lmtPrice = float(command.resolved_limit_price)
    if command.new_tif is not None:
        proposed_order.tif = str(command.new_tif.value)
        proposed_order.goodTillDate = (
            ""
            if command.new_good_till_date_utc is None
            else command.new_good_till_date_utc.astimezone(timezone.utc).strftime(
                "%Y%m%d %H:%M:%S UTC"
            )
        )
    proposed_order.whatIf = True
    proposed_order.transmit = True
    what_if_state = broker.whatIfOrder(trade.contract, proposed_order)
    if what_if_state is None:
        raise ProductionRuntimeConfigurationError("LIABILITY_WHAT_IF_UNAVAILABLE")

    bounded, maximum_loss, covered_legs, resolved_terms = (
        _exact_continuity_maximum_loss(broker, trade.contract, proposed_order)
    )
    collected = datetime.now(timezone.utc)
    maximum_age = min(
        Decimal("30"),
        Decimal(str(command.liability_requirement.maximum_evidence_age_seconds)),
    )
    broker_evidence = {
        "schema": "CONTINUITY_LIABILITY_BROKER_EVIDENCE_V1",
        "command_sha256": command.sha256,
        "proposed_order_sha256": command.proposed_order_sha256,
        "current_order_state_sha256": snapshot["state_sha256"],
        "contract": canonical_contract_identity(trade.contract),
        "resolved_terms": resolved_terms,
        "covered_leg_identity_sha256": list(covered_legs),
        "bounded": bounded,
        "maximum_loss": None if maximum_loss is None else str(maximum_loss),
        "what_if": {
            "commission": str(getattr(what_if_state, "commission", "") or ""),
            "init_margin_change": str(
                getattr(what_if_state, "initMarginChange", "") or ""
            ),
            "maint_margin_change": str(
                getattr(what_if_state, "maintMarginChange", "") or ""
            ),
            "warning_text": str(getattr(what_if_state, "warningText", "") or ""),
        },
        "collected_at_utc": collected,
    }
    evidence_sha256 = sha256_json(broker_evidence)
    currency = str(
        canonical_contract_identity(trade.contract).get("currency") or ""
    ).upper()
    return MaximumLiabilityEvidence(
        evidence_id=f"liability:{command.sha256}:{evidence_sha256}",
        source=LiabilityEvidenceSource.PROVEN_EXACT_FORMULA,
        collected_at_utc=collected,
        fresh_until_utc=collected + timedelta(seconds=float(maximum_age)),
        account_identity_sha256=command.account_identity_sha256,
        contract_identity_sha256=command.contract_identity_sha256,
        proposed_order_sha256=command.proposed_order_sha256,
        command_sha256=command.sha256,
        bounded=bounded,
        maximum_loss=maximum_loss,
        currency=currency,
        covered_leg_identity_sha256=covered_legs,
        broker_evidence_sha256=evidence_sha256,
    )


def create_authoritative_writer(
    *,
    coordinator: BrokerWriteCoordinator,
    db_path: Path,
    config: Any,
    preflight: Any,
    execution_lock_verifier: Callable[[], bool],
    uncertainty_reporter: Callable[[str], None],
    toolbox: Any,
    production_validation_sha256: str | None,
    validation_broker_factory: Callable[[], Any] | None = None,
) -> Any:
    from .authoritative_broker_writer import AuthoritativeBrokerWriter
    from .production_authority import ProductionAuthorityValidator

    validate_production_runtime_configuration(config)
    session_factory = build_ibkr_session_factory(
        host=str(config.paper_host),
        port=int(config.paper_port),
        expected_account_hash=str(preflight.expected_account_hash),
        client_id=WRITER_CLIENT_ID,
        read_only=False,
    )
    lazy_engine = _LazyProductionModelEngine(db_path=Path(db_path), toolbox=toolbox)
    snapshot_reader = _ProductionSnapshotReader(
        db_path=Path(db_path),
        config=config,
        preflight=preflight,
        execution_lock_verifier=execution_lock_verifier,
    )
    attempt_persister, result_persister = _production_persistence(Path(db_path))
    validator = ProductionAuthorityValidator(
        snapshot_reader=snapshot_reader,
        expected_approved_head=_current_head(Path(config.repo_root)),
    )
    effective_session_factory = validation_broker_factory or session_factory
    return AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=lambda client_id: effective_session_factory()
        if client_id == WRITER_CLIENT_ID
        else (_ for _ in ()).throw(
            ProductionRuntimeConfigurationError("WRITER_CLIENT_ID_MISMATCH")
        ),
        execution_client_id=WRITER_CLIENT_ID,
        execution_lock_verifier=execution_lock_verifier,
        authority_validator=lambda request, evidence: (),
        attempt_persister=attempt_persister,
        result_persister=result_persister,
        model_execution_engine=lazy_engine,
        production_validation_sha256=production_validation_sha256,
        production_authority_validator=validator,
        production_broker_evidence_collector=_broker_evidence_collector(
            Path(db_path)
        ),
        liability_evidence_collector=_collect_continuity_liability_evidence,
        resource_closer=lazy_engine.close,
        uncertainty_reporter=uncertainty_reporter,
    )


class _ProductionClock:
    def __init__(self, db: Any, epoch_id: str | None) -> None:
        self.db = db
        self.epoch_id = epoch_id

    def state(self) -> str:
        from .experiment_control import ExperimentClockStore

        store = ExperimentClockStore(self.db)
        clock = (
            store.load()
            if self.epoch_id is None
            else store.clock_for_epoch(self.epoch_id)
        )
        now = datetime.now(timezone.utc)
        if now < clock.start_utc:
            return "NOT_STARTED"
        if now >= clock.end_utc:
            return "EXPIRED"
        return "ACTIVE"


def _verified_registry_binding(db: Any, plan: Any) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT payload_json,payload_sha256 FROM experiment_order_registry "
        "WHERE order_ref=? AND perm_id>0 ORDER BY sequence DESC LIMIT 1",
        (plan.order_binding.order_ref,),
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(str(row[0]))
    if sha256_json(payload) != str(row[1]):
        raise ProductionRuntimeConfigurationError("ORDER_REGISTRY_HASH_MISMATCH")
    if (
        payload.get("plan_sha256") != plan.sha256
        and plan.predecessor_plan_sha256 is None
    ):
        raise ProductionRuntimeConfigurationError("PLAN_BINDING_MISMATCH")
    account = str(payload.get("account") or "")
    contract = dict(payload.get("contract") or {})
    binding = plan.order_binding
    checks = (
        str(payload.get("order_ref") or "") == binding.order_ref,
        binding.ibkr_order_id is None
        or int(payload.get("ibkr_order_id") or 0) == binding.ibkr_order_id,
        binding.perm_id is None
        or int(payload.get("perm_id") or 0) == binding.perm_id,
        int(payload.get("execution_client_id") or -1)
        == binding.execution_client_id,
        expected_identity_hash(account) == binding.account_identity_sha256,
        sha256_json(contract) == binding.contract_identity_sha256,
        str(payload.get("action") or "").upper() == binding.action,
    )
    if not all(checks):
        raise ProductionRuntimeConfigurationError("ORDER_REGISTRY_IDENTITY_MISMATCH")
    combo_legs = list(contract.get("comboLegs") or [])
    leg_hashes = tuple(sha256_json(leg) for leg in combo_legs) or (
        sha256_json(contract),
    )
    return {
        "plan_id": plan.plan_id,
        "plan_sha256": plan.sha256,
        "order_ref": str(payload.get("order_ref") or ""),
        "order_id": int(payload.get("ibkr_order_id") or 0),
        "perm_id": int(payload.get("perm_id") or 0),
        "execution_client_id": int(payload.get("execution_client_id") or -1),
        "account_identity_sha256": expected_identity_hash(account),
        "contract_identity_sha256": sha256_json(contract),
        "contract_leg_identity_sha256": leg_hashes,
    }


class ProductionContinuityPoller:
    """Evaluate durable model-authored plans and submit at most one exact command."""

    def __init__(
        self,
        *,
        coordinator: BrokerWriteCoordinator,
        config: Any,
        preflight: Any,
    ) -> None:
        self.coordinator = coordinator
        self.config = config
        self.preflight = preflight
        self.allocate_sequence = _sequence_allocator(coordinator)

    @staticmethod
    def _execution_counts(db: Any, plan_id: str) -> dict[str, int]:
        rows = db.execute(
            "SELECT json_extract(e.payload_json,'$.selected_contingency_id'),COUNT(*) "
            "FROM continuity_execution_events x "
            "JOIN continuity_evaluation_events e ON e.evaluation_id=x.evaluation_id "
            "WHERE x.plan_id=? GROUP BY 1",
            (plan_id,),
        ).fetchall()
        return {str(key): int(count) for key, count in rows if key is not None}

    def __call__(self, db: Any, broker: ReadOnlyContinuityBroker, _: Any) -> None:
        from concurrent.futures import TimeoutError as FutureTimeout
        from types import SimpleNamespace

        from .continuity_evaluator import ContinuityEvaluator, ContinuityFactCollector
        from .continuity_executor import ContinuityExecutor
        from .experiment_ledger import AutonomousExperimentLedger
        from .provider_lifecycle import BrokerTimeEvidence

        store = ContinuityStore(db)
        for plan in store.active_plans():
            binding = _verified_registry_binding(db, plan)
            if binding is None:
                continue
            identity = SimpleNamespace(
                order_ref=binding["order_ref"],
                ibkr_order_id=binding["order_id"],
                perm_id=binding["perm_id"],
                execution_client_id=binding["execution_client_id"],
                account_identity_sha256=binding["account_identity_sha256"],
                contract_identity_sha256=binding["contract_identity_sha256"],
            )
            observed_at = datetime.now(timezone.utc)
            broker_time = broker.reqCurrentTime()
            if broker_time.tzinfo is None or broker_time.utcoffset() is None:
                broker_time = broker_time.replace(tzinfo=timezone.utc)
            time_evidence = BrokerTimeEvidence.create_authenticated_paper(
                time_utc=broker_time,
                observed_at_utc=observed_at,
                account_identity_sha256=str(self.preflight.expected_account_hash),
            )
            collector = ContinuityFactCollector(
                store,
                broker,
                AutonomousExperimentLedger(
                    db, allocation=Decimal(str(self.config.initial_allocation))
                ),
                _ProductionClock(db, self.config.target_successor_epoch_id),
            )
            facts = collector.collect(
                SimpleNamespace(order_binding=identity),
                broker_time_utc=time_evidence,
            )
            evaluation = ContinuityEvaluator(
                execution_counts=self._execution_counts(db, plan.plan_id)
            ).evaluate(plan, facts)
            store.append_evaluation(evaluation, plan.order_binding.order_ref)
            if (
                evaluation.authority_active is not True
                or evaluation.selected_action is None
                or evaluation.execution_ordinal is None
            ):
                continue
            snapshot = broker.current_order_snapshot(identity)
            if snapshot is None:
                continue
            active_binding = {
                **binding,
                "observed_state_sha256": snapshot["state_sha256"],
                "current_total_quantity": snapshot["totalQuantity"],
                "current_limit_price": snapshot["limitPrice"],
                "current_tif": snapshot["tif"],
                "current_good_till_date_utc": snapshot["orderAttributes"].get(
                    "goodTillDate"
                ),
                "current_maximum_liability": str(
                    plan.order_binding.original_maximum_liability
                    or plan.maximum_authorized_liability
                ),
            }
            fact_values = {
                item.fact.value: item.canonical_value for item in facts.facts
            }
            executor = ContinuityExecutor(
                plan_reader=lambda plan_id, value=plan: value,
                active_binding_reader=lambda plan_id, value=active_binding: value,
                fact_values_reader=lambda digest, value=fact_values: value,
                fresh_gate_checker=lambda authority_class: (),
                durable_sequence_allocator=self.allocate_sequence,
            )
            command = executor.build_command(evaluation)
            future = self.coordinator.submit(command)
            try:
                result = future.result(timeout=30.0)
            except FutureTimeout as exc:
                raise RuntimeError("CONTINUITY_WRITER_RESULT_TIMEOUT") from exc
            store.append_execution_event(
                execution_id=command.execution_key,
                evaluation_id=evaluation.evaluation_id,
                plan_id=plan.plan_id,
                order_ref=plan.order_binding.order_ref,
                execution_ordinal=evaluation.execution_ordinal,
                event_type=str(result.status),
                payload={
                    "schema": "CONTINUITY_EXECUTION_RESULT_V1",
                    "command_sha256": command.sha256,
                    "success": bool(result.success),
                    "status": str(result.status),
                    "reason_codes": list(result.reason_codes),
                },
            )
            break


def create_continuity_watchdog(
    *,
    coordinator: BrokerWriteCoordinator,
    db_path: Path,
    config: Any,
    preflight: Any,
    uncertainty_reporter: Callable[[str], None],
    validation_broker_factory: Callable[[], Any] | None = None,
) -> Any:
    from .continuity_watchdog import ContinuityWatchdog
    from .persistence import Database

    validate_production_runtime_configuration(config)
    raw_factory = build_ibkr_session_factory(
        host=str(config.paper_host),
        port=int(config.paper_port),
        expected_account_hash=str(preflight.expected_account_hash),
        client_id=OBSERVER_CLIENT_ID,
        read_only=True,
    )

    effective_session_factory = validation_broker_factory or raw_factory

    def broker_factory() -> ReadOnlyContinuityBroker:
        return ReadOnlyContinuityBroker(
            effective_session_factory(),
            account_identity_sha256=str(preflight.expected_account_hash),
        )

    return ContinuityWatchdog(
        db_factory=lambda: Database.open(Path(db_path)),
        broker_factory=broker_factory,
        poll_once=ProductionContinuityPoller(
            coordinator=coordinator,
            config=config,
            preflight=preflight,
        ),
        coordinator=coordinator,
        broker_time_reader=lambda broker: broker.reqCurrentTime(),
        poll_interval_seconds=5.0,
        heartbeat_max_age_seconds=20.0,
        uncertainty_reporter=uncertainty_reporter,
    )


class _ValidationBroker:
    """Socket-free PAPER boundary used only by composition validation."""

    all_order_visibility = True
    environment = "PAPER"

    def __init__(self, *, client_id: int, read_only: bool) -> None:
        self.client_id = client_id
        self.read_only = read_only
        self.disconnected = False

    def reqCurrentTime(self) -> datetime:
        return datetime.now(timezone.utc)

    def reqAllOpenOrders(self) -> list[Any]:
        return []

    def reqExecutions(self) -> list[Any]:
        return []

    def positions(self) -> list[Any]:
        return []

    def disconnect(self) -> None:
        self.disconnected = True


def _validation_block(reason_code: str) -> dict[str, Any]:
    return {
        "status": "BLOCK",
        "reason_codes": [reason_code],
        "broker_connections": 0,
        "broker_writes": 0,
    }


def _verify_installed_continuity_schema(db_path: Path) -> None:
    from .continuity_schema import verify_continuity_schema_v3
    from .persistence import Database

    target = Path(db_path).resolve()
    if not target.is_file():
        raise ProductionRuntimeConfigurationError("CONTINUITY_SCHEMA_V3_INVALID")
    connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
    try:
        verify_continuity_schema_v3(Database(connection))
    except Exception as exc:
        reason = str(exc)
        if reason != "CONTINUITY_SCHEMA_V3_INVALID":
            reason = "CONTINUITY_SCHEMA_V3_INVALID"
        raise ProductionRuntimeConfigurationError(reason) from exc
    finally:
        connection.close()


def validate_production_composition(
    *,
    config: Any,
    preflight: Any,
    toolbox: Any,
    production_validation_sha256: str,
) -> dict[str, Any]:
    """Exercise the production graph with socket-free, write-free boundaries."""

    writer = None
    watchdog = None
    writer_started = False
    watchdog_started = False
    writer_stopped = False
    watchdog_stopped = False
    stage = "CONFIGURATION"
    try:
        validate_production_runtime_configuration(config)
        if (
            not isinstance(production_validation_sha256, str)
            or len(production_validation_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in production_validation_sha256
            )
        ):
            return _validation_block("PRODUCTION_VALIDATION_SHA256_INVALID")
        _verify_installed_continuity_schema(Path(config.db_path))

        with tempfile.TemporaryDirectory(prefix="ibkr-continuity-v3-validate-") as root:
            from .continuity_schema import install_continuity_schema_v3
            from .persistence import Database
            from .successor_schema import install_successor_schema_v2

            validation_db_path = Path(root) / "validation.sqlite3"
            with Database.open(validation_db_path) as db:
                install_successor_schema_v2(db)
                install_continuity_schema_v3(db)
            validation_config = SimpleNamespace(
                **{
                    **vars(config),
                    "db_path": validation_db_path,
                }
            )
            coordinator = create_broker_write_coordinator()
            model_executor = create_model_executor(
                coordinator=coordinator,
                db_path=validation_db_path,
                config=validation_config,
                preflight=preflight,
                production_validation_sha256=None,
            )
            if (
                getattr(model_executor, "is_coordinated_model_executor", False)
                is not True
                or getattr(model_executor, "armed", True) is not False
            ):
                raise ProductionRuntimeConfigurationError(
                    "PRODUCTION_COMPOSITION_MODEL_EXECUTOR_INVALID"
                )
            reporter = create_critical_alert_reporter(
                db_path=validation_db_path,
                config=validation_config,
                preflight=preflight,
            )
            writer = create_authoritative_writer(
                coordinator=coordinator,
                db_path=validation_db_path,
                config=validation_config,
                preflight=preflight,
                execution_lock_verifier=lambda: False,
                uncertainty_reporter=reporter,
                toolbox=toolbox,
                production_validation_sha256=None,
                validation_broker_factory=lambda: _ValidationBroker(
                    client_id=WRITER_CLIENT_ID, read_only=False
                ),
            )
            watchdog = create_continuity_watchdog(
                coordinator=coordinator,
                db_path=validation_db_path,
                config=validation_config,
                preflight=preflight,
                uncertainty_reporter=reporter,
                validation_broker_factory=lambda: _ValidationBroker(
                    client_id=OBSERVER_CLIENT_ID, read_only=True
                ),
            )

            stage = "START"
            writer.start()
            writer_started = True
            if writer.wait_until_ready(2.0) is not True:
                raise RuntimeError("AUTHORITATIVE_WRITER_NOT_READY")
            writer_sole_capability = False
            if getattr(writer, "coordinator", None) is coordinator:
                try:
                    coordinator.attach_writer()
                except RuntimeError as exc:
                    writer_sole_capability = str(exc) == "AUTHORITATIVE_WRITER_ALREADY_ATTACHED"
            watchdog.start(2.0)
            watchdog_started = True

            production_gates_callable = all(
                (
                    callable(getattr(writer, "execution_lock_verifier", None)),
                    callable(
                        getattr(
                            getattr(writer, "production_authority_validator", None),
                            "validate_before_write",
                            None,
                        )
                    ),
                    callable(reporter),
                    callable(getattr(writer, "liability_evidence_collector", None)),
                )
            )
            if production_gates_callable is not True:
                raise ProductionRuntimeConfigurationError(
                    "PRODUCTION_COMPOSITION_GATE_INVALID"
                )
            watchdog_shutdown = watchdog.stop(2.0)
            watchdog_stopped = bool(getattr(watchdog_shutdown, "stopped", False))
            writer_stopped = bool(writer.stop(2.0))
            if not watchdog_stopped or not writer_stopped:
                raise RuntimeError("PRODUCTION_COMPOSITION_SHUTDOWN_INCOMPLETE")

            return {
                "status": "PASS",
                "reason_codes": [],
                "broker_connections": 0,
                "broker_writes": 0,
                "model_executor_coordinated": bool(
                    getattr(model_executor, "is_coordinated_model_executor", False)
                ),
                "model_executor_armed": bool(getattr(model_executor, "armed", True)),
                "writer_client_id": int(writer.execution_client_id),
                "observer_client_id": OBSERVER_CLIENT_ID,
                "observer_read_only": True,
                "writer_started": writer_started,
                "writer_stopped": writer_stopped,
                "watchdog_started": watchdog_started,
                "watchdog_stopped": watchdog_stopped,
                "writer_sole_capability": writer_sole_capability,
                "legacy_direct_executor_selected": False,
                "production_gates_callable": production_gates_callable,
                "liability_evidence_collector_callable": callable(
                    getattr(writer, "liability_evidence_collector", None)
                ),
            }
    except ProductionRuntimeConfigurationError as exc:
        return _validation_block(str(exc))
    except Exception as exc:
        prefix = (
            "PRODUCTION_COMPOSITION_START_FAILED"
            if stage == "START"
            else "PRODUCTION_COMPOSITION_CONSTRUCTION_FAILED"
        )
        return _validation_block(f"{prefix}:{type(exc).__name__}")
    finally:
        if watchdog is not None and not watchdog_stopped:
            try:
                stopped = watchdog.stop(2.0)
                watchdog_stopped = bool(getattr(stopped, "stopped", False))
            except Exception:
                pass
        if writer is not None and not writer_stopped:
            try:
                writer_stopped = bool(writer.stop(2.0))
            except Exception:
                pass
