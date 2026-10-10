"""Concrete production composition for Continuity V3 in IBKR PAPER."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from .broker_write_coordinator import BrokerWriteCoordinator
from .canonical import canonical_bytes, sha256_json
from .continuity_store import ContinuityStore
from .ibkr_readonly import expected_identity_hash
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7

WRITER_CLIENT_ID = 19761
OBSERVER_CLIENT_ID = 19762
DEFAULT_SMTP_CONFIG = Path("Secrets/email_alerts.env")


class ProductionRuntimeConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MultiUniverseRuntimeAuthority:
    """DB-derived launch authority shared by the one successor runtime graph."""

    schema: str
    transition_phase: str
    supervision_binding_sha256: str
    continuous_authority_sha256: str
    entry_authority_mode: str
    writer_start_allowed: bool
    management_actions_allowed: bool
    continuity_actions_allowed: bool
    new_regular_entries_allowed: bool
    new_continuous_entries_allowed: bool
    legacy_predecessor_allowed: bool


def _is_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def normalize_multi_universe_launch_authority(
    decision: Mapping[str, Any],
) -> MultiUniverseRuntimeAuthority:
    """Reject caller-shaped authority and freeze the DB-derived decision."""

    payload = dict(decision)
    if payload.get("schema") != "MULTI_UNIVERSE_LAUNCH_DECISION_V1":
        raise ProductionRuntimeConfigurationError(
            "MULTI_UNIVERSE_LAUNCH_AUTHORITY_INVALID"
        )
    if not _is_sha256(payload.get("supervision_binding_sha256")):
        raise ProductionRuntimeConfigurationError("SUPERVISION_BINDING_AMBIGUOUS")
    if not _is_sha256(payload.get("continuous_authority_sha256")):
        raise ProductionRuntimeConfigurationError(
            "CONTINUOUS_ENTRY_AUTHORITY_AMBIGUOUS"
        )
    if payload.get("legacy_predecessor_allowed") is not False:
        raise ProductionRuntimeConfigurationError(
            "PREDECESSOR_REACTIVATION_ATTEMPT"
        )
    if payload.get("writer_start_allowed") is not True:
        raise ProductionRuntimeConfigurationError("SUCCESSOR_WRITER_AUTHORITY_REQUIRED")
    boolean_fields = (
        "management_actions_allowed",
        "continuity_actions_allowed",
        "new_regular_entries_allowed",
        "new_continuous_entries_allowed",
    )
    if any(type(payload.get(field)) is not bool for field in boolean_fields):
        raise ProductionRuntimeConfigurationError(
            "MULTI_UNIVERSE_LAUNCH_AUTHORITY_INVALID"
        )

    phase = str(payload.get("transition_phase") or "")
    mode = str(payload.get("entry_authority_mode") or "")
    phases = {
        "SUCCESSOR_COMMITTED",
        "SUPERVISION_BOUND",
        "CANARY_EXCLUSIVE",
        "CANARY_PASS",
        "RUNTIME_BOUND",
        "ACTIVE",
    }
    if phase not in phases:
        raise ProductionRuntimeConfigurationError("SUCCESSOR_TRANSITION_NOT_ELIGIBLE")
    expected_mode = (
        "CANARY_EXCLUSIVE"
        if phase == "CANARY_EXCLUSIVE"
        else "NORMAL"
        if phase == "ACTIVE"
        else "FROZEN"
    )
    if mode != expected_mode and mode != "UNCERTAIN_FREEZE":
        raise ProductionRuntimeConfigurationError("ENTRY_AUTHORITY_PHASE_MISMATCH")
    if mode == "UNCERTAIN_FREEZE" and phase not in {
        "CANARY_EXCLUSIVE",
        "CANARY_PASS",
        "RUNTIME_BOUND",
        "ACTIVE",
    }:
        raise ProductionRuntimeConfigurationError("ENTRY_AUTHORITY_PHASE_MISMATCH")
    normal_entries = mode == "NORMAL"
    if bool(payload.get("new_regular_entries_allowed")) is not normal_entries:
        raise ProductionRuntimeConfigurationError("ENTRY_AUTHORITY_PHASE_MISMATCH")
    if mode != "NORMAL" and bool(payload.get("new_continuous_entries_allowed")):
        raise ProductionRuntimeConfigurationError("ENTRY_AUTHORITY_PHASE_MISMATCH")
    phase_order = (
        "SUCCESSOR_COMMITTED",
        "SUPERVISION_BOUND",
        "CANARY_EXCLUSIVE",
        "CANARY_PASS",
        "RUNTIME_BOUND",
        "ACTIVE",
    )
    management_expected = (
        phase_order.index(phase) >= phase_order.index("SUPERVISION_BOUND")
    )
    if (
        payload.get("management_actions_allowed") is not management_expected
        or payload.get("continuity_actions_allowed") is not management_expected
    ):
        raise ProductionRuntimeConfigurationError("MANAGEMENT_AUTHORITY_PHASE_MISMATCH")

    return MultiUniverseRuntimeAuthority(
        schema="MULTI_UNIVERSE_RUNTIME_AUTHORITY_V1",
        transition_phase=phase,
        supervision_binding_sha256=str(payload["supervision_binding_sha256"]),
        continuous_authority_sha256=str(payload["continuous_authority_sha256"]),
        entry_authority_mode=mode,
        writer_start_allowed=True,
        management_actions_allowed=management_expected,
        continuity_actions_allowed=management_expected,
        new_regular_entries_allowed=normal_entries,
        new_continuous_entries_allowed=bool(
            payload.get("new_continuous_entries_allowed")
        ),
        legacy_predecessor_allowed=False,
    )


def inject_multi_universe_runtime_authority(
    authority: MultiUniverseRuntimeAuthority, *components: Any
) -> None:
    """Attach one immutable authority object to every runtime component."""

    for component in components:
        if component is None:
            raise ProductionRuntimeConfigurationError(
                "MULTI_UNIVERSE_COMPONENT_MISSING"
            )
        existing = getattr(component, "multi_universe_runtime_authority", None)
        if existing is not None and existing is not authority:
            raise ProductionRuntimeConfigurationError(
                "MULTI_UNIVERSE_RUNTIME_AUTHORITY_CONFLICT"
            )
        setattr(component, "multi_universe_runtime_authority", authority)


@dataclass(frozen=True)
class MultiUniverseRuntimeStores:
    """The V4 authorities injected into the existing single runtime graph."""

    ledger: Any
    ownership: Any
    capability: Any
    reconciliation: Any
    transition: Any


class _PathSleeveAuthorityReservationStore:
    """Open the V4 reservation store on the writer thread for each commit."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def reserve(self, request: Any, broker_evidence: Any, snapshot_reader: Any) -> Any:
        from .persistence import Database
        from .sleeve_execution_authority import SleeveAuthorityReservationStore

        with Database.open(self.db_path) as db:
            return SleeveAuthorityReservationStore(db).reserve(
                request, broker_evidence, snapshot_reader
            )


class _ProductionSleeveAuthoritySnapshotReader:
    def __init__(
        self,
        db_path: Path,
        config: Any,
        current_adapter_sha256: str,
    ) -> None:
        if (
            len(str(current_adapter_sha256)) != 64
            or any(
                char not in "0123456789abcdef"
                for char in str(current_adapter_sha256)
            )
        ):
            raise ProductionRuntimeConfigurationError(
                "CURRENT_ADAPTER_SHA256_REQUIRED"
            )
        self.db_path = Path(db_path)
        self.config = config
        self.current_adapter_sha256 = str(current_adapter_sha256)

    def __call__(self, request: Any) -> Any:
        from .contract_ownership import ContractOwnershipStore
        from .coordinated_model_executor import ModelExecutionOperation
        from .multi_universe_models import (
            ProductFamilyKey,
            TransitionPhase,
            TransitionTarget,
        )
        from .persistence import Database
        from .product_capability import ProductFamilyCertificationStore
        from .sleeve_execution_authority import SleeveAuthoritySnapshot
        from .sleeve_ledger import SleeveLedgerStore

        with Database.open(self.db_path) as db:
            ledger = SleeveLedgerStore(db).project(request.capital_sleeve)
            if not ledger.initialized:
                raise ProductionRuntimeConfigurationError("SLEEVE_NOT_INITIALIZED")
            ownership = ContractOwnershipStore(db).projection()
            family_payload = next(
                (
                    item.get("family")
                    for item in (
                        request.input_bundle.product_capability_snapshot or {}
                    ).get("families", ())
                    if item.get("family_sha256") == request.product_family_sha256
                ),
                None,
            )
            if family_payload is None:
                raise ProductionRuntimeConfigurationError(
                    "PRODUCT_FAMILY_DB_AUTHORITY_REQUIRED"
                )
            family = ProductFamilyKey.model_validate(family_payload)
            capability = ProductFamilyCertificationStore(
                db,
                current_adapter_sha256=self.current_adapter_sha256,
            ).projection(family)
            row = db.execute(
                "SELECT phase,payload_json FROM successor_transition_events "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if row is None:
                raise ProductionRuntimeConfigurationError("SUCCESSOR_TRANSITION_REQUIRED")
            transition_payload = json.loads(str(row[1]))
            target = TransitionTarget.model_validate(transition_payload.get("target"))
            if (
                target.successor_epoch_id != request.epoch_id
                or target.successor_definition_sha256
                != str(self.config.target_successor_definition_sha256)
            ):
                raise ProductionRuntimeConfigurationError(
                    "SUCCESSOR_TRANSITION_BINDING_MISMATCH"
                )
            economic_row = db.execute(
                "SELECT payload_json FROM owner_economic_risk_authorization_events "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            economic_valid = False
            if economic_row is not None:
                economic_payload = json.loads(str(economic_row[0]))
                economic_valid = (
                    economic_payload.get("authorization_sha256")
                    == target.economic_risk_authorization_sha256
                    or economic_payload.get("authority_sha256")
                    == target.economic_risk_authorization_sha256
                )
            equity = (
                ledger.allocation_usd
                + ledger.realized_pnl_usd
                + ledger.unrealized_pnl_usd
                - ledger.fees_usd
            )
            proposed = Decimal("0")
            if request.operation.value == "NEW_TRADE":
                proposed = Decimal(str(request.payload.maximum_loss))
            phase = TransitionPhase(str(row[0]))
            phase_index = tuple(TransitionPhase).index(phase)
            supervision_bound = phase_index >= tuple(TransitionPhase).index(
                TransitionPhase.SUPERVISION_BOUND
            )
            entry_authority = (
                "ACTIVE"
                if phase is TransitionPhase.ACTIVE
                else (
                    "CANARY_ONLY"
                    if phase is TransitionPhase.CANARY_EXCLUSIVE
                    else "FROZEN"
                )
            )
            management = request.operation in {
                ModelExecutionOperation.OPEN_ORDER_ACTION,
                ModelExecutionOperation.POSITION_ACTION,
            }
            contract_id = int(getattr(request.payload, "contract_id", 0) or 0)
            observations = (
                request.input_bundle.open_orders_snapshot
                if request.operation is ModelExecutionOperation.OPEN_ORDER_ACTION
                else request.input_bundle.positions_snapshot
            )
            observed = next(
                (
                    item
                    for item in observations
                    if int(item.get("contract_id") or item.get("con_id") or 0)
                    == contract_id
                ),
                None,
            )
            owner = next(
                (
                    item
                    for item in ownership.active_contracts
                    if item.contract.con_id == contract_id
                ),
                None,
            )
            inherited_position = bool(
                management
                and owner is not None
                and owner.sleeve is request.capital_sleeve
                and (
                    owner.group_id.startswith("inherited-")
                    or bool((observed or {}).get("inherited_position"))
                )
            )
            instrument_management_tradable = bool(
                management
                and observed is not None
                and observed.get("management_tradable") is True
            )
            reconciliation = request.input_bundle.reconciliation_receipt or {}
            return SleeveAuthoritySnapshot(
                capital_sleeve=request.capital_sleeve,
                sleeve_authority_sha256=request.sleeve_authority_sha256,
                ownership_projection_sha256=ownership.projection_sha256,
                product_family_sha256=capability.family_sha256,
                economic_authorization_sha256=target.economic_risk_authorization_sha256,
                transition_target_sha256=target.sha256,
                writer_binding_sha256=target.writer_binding_sha256,
                epoch_id=target.successor_epoch_id,
                approved_head=target.approved_git_head,
                account_identity_sha256=target.account_identity_sha256,
                transition_phase=str(row[0]),
                supervision_bound=supervision_bound,
                inherited_position=inherited_position,
                entry_authority=entry_authority,
                instrument_management_tradable=instrument_management_tradable,
                reconciliation_fresh=(
                    reconciliation.get("status") == "PASS"
                    and reconciliation.get("fresh", True) is True
                ),
                paper_only=True,
                family_executable=capability.executable,
                capability_fresh=(
                    capability.expires_at_utc is not None
                    and capability.expires_at_utc > datetime.now(timezone.utc)
                ),
                ownership_conflict=(
                    ownership.projection_sha256
                    != request.ownership_projection_sha256
                ),
                economic_authorization_valid=economic_valid,
                equity_usd=equity,
                reserved_liability_usd=ledger.reserved_liability_usd,
                proposed_maximum_loss_usd=proposed,
                continuity_required=bool(
                    request.input_bundle.continuity_context.get(
                        "authority_contract_required", False
                    )
                ),
                continuity_plan_sha256=request.continuity_plan_sha256,
            )


def _sleeve_broker_evidence_collector(
    expected_account_sha256: str,
) -> Callable[[Any, Any, dict[str, Any]], dict[str, Any]]:
    def collect(_broker: Any, request: Any, evidence: dict[str, Any]) -> dict[str, Any]:
        context = dict(evidence.get("model_write_context") or {})
        contract = context.get("canonical_contract")
        contract_sha = None
        ownership_contracts: list[dict[str, Any]] = []
        if contract is not None:
            from .contract_ownership import (
                CanonicalContractIdentity,
                canonical_contract_identity,
            )

            parent = CanonicalContractIdentity.model_validate(contract)
            contract_sha = parent.sha256
            ownership_contracts.append(parent.model_dump(mode="json"))
            if parent.security_type == "BAG":
                from ib_insync import Contract

                for leg in parent.bag_legs:
                    details = list(
                        _broker.reqContractDetails(Contract(conId=leg.con_id))
                    )
                    if len(details) != 1:
                        raise RuntimeError(
                            "BAG_LEG_CONTRACT_IDENTITY_UNCERTAIN"
                        )
                    resolved = details[0].contract
                    identity = canonical_contract_identity(
                        {
                            "conId": int(getattr(resolved, "conId", 0) or 0),
                            "secType": str(
                                getattr(resolved, "secType", "") or ""
                            ),
                            "currency": str(
                                getattr(resolved, "currency", "") or ""
                            ),
                            "exchange": str(
                                getattr(resolved, "exchange", "") or ""
                            ),
                            "primaryExchange": str(
                                getattr(resolved, "primaryExchange", "") or ""
                            )
                            or None,
                            "localSymbol": str(
                                getattr(resolved, "localSymbol", "") or ""
                            )
                            or None,
                            "tradingClass": str(
                                getattr(resolved, "tradingClass", "") or ""
                            )
                            or None,
                            "multiplier": str(
                                getattr(resolved, "multiplier", "") or ""
                            )
                            or None,
                        }
                    )
                    if identity.con_id != leg.con_id:
                        raise RuntimeError(
                            "BAG_LEG_CONTRACT_IDENTITY_MISMATCH"
                        )
                    ownership_contracts.append(
                        identity.model_dump(mode="json")
                    )
        bundle = getattr(request, "input_bundle", None)
        portfolio = (
            dict(getattr(bundle, "multi_sleeve_portfolio", None) or {})
            if bundle is not None
            else {}
        )
        ownership = (
            dict(getattr(bundle, "contract_ownership_snapshot", None) or {})
            if bundle is not None
            else {}
        )
        reconciliation = (
            dict(getattr(bundle, "reconciliation_receipt", None) or {})
            if bundle is not None
            else {}
        )
        owned_sleeve = None
        if contract_sha is not None:
            owned_sleeve = (ownership.get("contract_sleeves") or {}).get(
                contract_sha
            )
            if owned_sleeve is None:
                owned_sleeve = next(
                    (
                        item.get("sleeve")
                        for item in ownership.get("active_contracts", ())
                        if item.get("contract_identity_sha256") == contract_sha
                    ),
                    None,
                )
        payload_contract_id = int(
            getattr(getattr(request, "payload", None), "contract_id", 0) or 0
        )
        management_identity_match = bool(
            contract is not None
            and (
                payload_contract_id == 0
                or int(contract.get("con_id") or contract.get("conId") or 0)
                == payload_contract_id
            )
        )
        return {
            "paper_only": True,
            "fresh": True,
            "account_identity_sha256": expected_account_sha256,
            "transition_target_sha256": portfolio.get(
                "transition_target_sha256"
            ),
            "writer_binding_sha256": portfolio.get("writer_binding_sha256"),
            "reconciliation_status": reconciliation.get("status"),
            "owned_contract_sleeve": owned_sleeve,
            "management_identity_match": management_identity_match,
            "possible_live_connection": False,
            "contract_identity_sha256": contract_sha,
            "canonical_contract": contract,
            "ownership_contracts": ownership_contracts,
            "order_ref": str(context.get("order_ref") or ""),
            "observed_at_utc": datetime.now(timezone.utc),
            "production_authority_sha256": (
                evidence.get("production_authority") or {}
            ).get("authority_snapshot_sha256"),
            "request_sha256": request.sha256,
        }

    return collect


def build_multi_universe_runtime_stores(
    db: Any, *, current_adapter_sha256: str
) -> MultiUniverseRuntimeStores:
    from .contract_ownership import ContractOwnershipStore
    from .multi_universe_transition import MultiUniverseTransitionCoordinator
    from .product_capability import ProductFamilyCertificationStore
    from .sleeve_ledger import SleeveLedgerStore
    from .sleeve_reconciliation import SleeveReconciler

    return MultiUniverseRuntimeStores(
        ledger=SleeveLedgerStore(db),
        ownership=ContractOwnershipStore(db),
        capability=ProductFamilyCertificationStore(
            db, current_adapter_sha256=current_adapter_sha256
        ),
        reconciliation=SleeveReconciler(),
        transition=MultiUniverseTransitionCoordinator(db),
    )


def validate_multi_universe_runtime_topology(
    *,
    providers: tuple[Any, ...],
    service_loops: tuple[Any, ...],
    coordinators: tuple[Any, ...],
    writers: tuple[Any, ...],
    write_capable_client_ids: tuple[int, ...],
    execution_locks: tuple[Any, ...],
    stores: MultiUniverseRuntimeStores,
    direct_executor_selected: bool,
) -> dict[str, Any]:
    counts = {
        "providers": len(providers),
        "service_loops": len(service_loops),
        "coordinators": len(coordinators),
        "writers": len(writers),
        "write_capable_clients": len(write_capable_client_ids),
        "execution_locks": len(execution_locks),
    }
    reasons: list[str] = []
    checks = (
        (counts["providers"] == 1, "PROVIDER_COUNT_INVALID"),
        (counts["service_loops"] == 1, "SERVICE_LOOP_COUNT_INVALID"),
        (counts["coordinators"] == 1, "COORDINATOR_COUNT_INVALID"),
        (counts["writers"] == 1, "WRITER_COUNT_INVALID"),
        (counts["write_capable_clients"] == 1, "WRITE_CLIENT_COUNT_INVALID"),
        (counts["execution_locks"] == 1, "EXECUTION_LOCK_COUNT_INVALID"),
        (not direct_executor_selected, "DIRECT_EXECUTOR_FORBIDDEN"),
    )
    reasons.extend(reason for valid, reason in checks if not valid)
    if write_capable_client_ids and write_capable_client_ids != (WRITER_CLIENT_ID,):
        reasons.append("WRITE_CLIENT_IDENTITY_INVALID")
    if (
        writers
        and int(getattr(writers[0], "execution_client_id", -1)) != WRITER_CLIENT_ID
    ):
        reasons.append("WRITER_CLIENT_IDENTITY_INVALID")
    store_names = tuple(
        name
        for name in (
            "ledger",
            "ownership",
            "capability",
            "reconciliation",
            "transition",
        )
        if getattr(stores, name, None) is not None
    )
    if len(store_names) != 5:
        reasons.append("MULTI_UNIVERSE_STORE_INJECTION_INCOMPLETE")
    return {
        "schema": "MULTI_UNIVERSE_RUNTIME_TOPOLOGY_V1",
        "status": "PASS" if not reasons else "BLOCK",
        "reason_codes": list(dict.fromkeys(reasons)),
        "authority_counts": counts,
        "injected_stores": store_names,
        "writer_client_id": WRITER_CLIENT_ID,
        "observer_client_id": OBSERVER_CLIENT_ID,
        "legacy_direct_executor_selected": direct_executor_selected,
    }


def inject_multi_universe_runtime_stores(
    stores: MultiUniverseRuntimeStores, *components: Any
) -> None:
    """Bind the same V4 authority graph to every component in the one runtime."""

    for component in components:
        if component is None:
            raise ProductionRuntimeConfigurationError(
                "MULTI_UNIVERSE_COMPONENT_MISSING"
            )
        existing = getattr(component, "multi_universe_stores", None)
        if existing is not None and existing is not stores:
            raise ProductionRuntimeConfigurationError(
                "MULTI_UNIVERSE_STORE_BINDING_CONFLICT"
            )
        setattr(component, "multi_universe_stores", stores)


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
            if hasattr(broker, "RequestTimeout"):
                broker.RequestTimeout = 4.0
            broker.connect(
                host,
                int(port),
                clientId=client_id,
                timeout=4.0,
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
            service = AlertService(repository, authority, smtp, event_log)
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
        "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", "") or ""),
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

    def __init__(
        self,
        broker: Any,
        *,
        account_identity_sha256: str,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._broker = broker
        self.account_identity_sha256 = account_identity_sha256
        self._monotonic = monotonic
        self._last_server_time: datetime | None = None
        self._last_server_time_observed_at: float | None = None

    def reqCurrentTime(self) -> datetime:
        observed_at = self._monotonic()
        if (
            self._last_server_time is not None
            and self._last_server_time_observed_at is not None
            and 0 <= observed_at - self._last_server_time_observed_at < 4.0
        ):
            return self._last_server_time
        server_time = self._broker.reqCurrentTime()
        self._last_server_time = server_time
        self._last_server_time_observed_at = observed_at
        return server_time

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

            contract = canonical_contract_identity(getattr(position, "contract", None))
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
        raise ProductionRuntimeConfigurationError(
            "BROKER_AUTHORITY_OBSERVATION_MISSING"
        )
    payload = json.loads(str(row[0]))
    if sha256_json(payload) != str(row[1]):
        raise ProductionRuntimeConfigurationError(
            "BROKER_AUTHORITY_OBSERVATION_CORRUPT"
        )
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
                    None if active is None else _verified_registry_binding(db, active)
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
                hashlib.sha256(
                    Path(self.config.auditor_receipt_path).read_bytes()
                ).hexdigest()
                == self.preflight.auditor_receipt_sha256
            )
            market_ok = (
                hashlib.sha256(
                    Path(self.config.market_policy_path).read_bytes()
                ).hexdigest()
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


def _broker_evidence_collector(
    db_path: Path,
    *,
    now_utc: Callable[[], datetime] | None = None,
) -> Callable[..., Any]:
    clock = now_utc or (lambda: datetime.now(timezone.utc))
    last_broker: Any | None = None
    last_broker_time: datetime | None = None
    last_broker_time_collected_at: datetime | None = None
    broker_time_pacing_window = timedelta(seconds=15)

    def collect(broker: Any, request: Any, raw: dict[str, Any]) -> Any:
        nonlocal last_broker
        nonlocal last_broker_time
        nonlocal last_broker_time_collected_at

        from .broker_write_coordinator import AuthorizedBrokerCommand
        from .persistence import Database
        from .production_authority import ProductionBrokerEvidence
        from .repositories import EventRepository

        collected = clock()
        reuse_broker_time = bool(
            broker is last_broker
            and last_broker_time is not None
            and last_broker_time_collected_at is not None
            and last_broker_time_collected_at <= collected
            and collected - last_broker_time_collected_at < broker_time_pacing_window
        )
        if reuse_broker_time:
            broker_time = last_broker_time
            broker_time_collected_at = last_broker_time_collected_at
        else:
            broker_time = broker.reqCurrentTime()
            broker_time_collected_at = collected
            last_broker = broker
            last_broker_time = broker_time
            last_broker_time_collected_at = broker_time_collected_at
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
            fresh_until_utc=broker_time_collected_at + timedelta(seconds=30),
            evidence_sha256=evidence_sha256,
        )

    return collect


class _LazyProductionModelEngine:
    def __init__(
        self,
        *,
        db_path: Path,
        toolbox: Any,
        final_write_authority_required: bool = False,
    ) -> None:
        self.db_path = Path(db_path)
        self.toolbox = toolbox
        self.final_write_authority_required = bool(
            final_write_authority_required
        )
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
                final_write_authority_required=(
                    self.final_write_authority_required
                ),
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


def _production_persistence(
    db_path: Path,
) -> tuple[Callable[..., None], Callable[..., None]]:
    from .persistence import Database

    def persist_attempt(request: Any, evidence: dict[str, Any]) -> None:
        authority = dict(evidence.get("production_authority") or {})
        with Database.open(db_path) as db:
            ContinuityStore(db).append_production_write_attempt(
                request_id=_request_id(request),
                request_sha256=request.sha256,
                execution_key=request.execution_key,
                authority_snapshot_sha256=str(authority["authority_snapshot_sha256"]),
                broker_evidence_sha256=str(authority["broker_evidence_sha256"]),
                liability_evidence_sha256=authority.get("liability_evidence_sha256"),
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
            Decimal("1") if str(leg["action"]).upper() == "BUY" else Decimal("-1")
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
            and sha256_json(snapshot["contract"]) == command.contract_identity_sha256
        ):
            matches.append((trade, snapshot))
    if len(matches) != 1:
        raise ProductionRuntimeConfigurationError("LIABILITY_ORDER_IDENTITY_UNCERTAIN")
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
    current_adapter_sha256: str | None = None,
) -> Any:
    from .authoritative_broker_writer import AuthoritativeBrokerWriter
    from .canary_execution import CanaryExecutionAdapter
    from .production_authority import ProductionAuthorityValidator

    validate_production_runtime_configuration(config)
    session_factory = build_ibkr_session_factory(
        host=str(config.paper_host),
        port=int(config.paper_port),
        expected_account_hash=str(preflight.expected_account_hash),
        client_id=WRITER_CLIENT_ID,
        read_only=False,
    )
    v4_active = getattr(config, "target_successor_definition_sha256", None) is not None
    lazy_engine = _LazyProductionModelEngine(
        db_path=Path(db_path),
        toolbox=toolbox,
        final_write_authority_required=v4_active,
    )
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
    sleeve_reservation_store = (
        _PathSleeveAuthorityReservationStore(Path(db_path)) if v4_active else None
    )
    sleeve_snapshot_reader = (
        _ProductionSleeveAuthoritySnapshotReader(
            Path(db_path), config, str(current_adapter_sha256 or "")
        )
        if v4_active
        else None
    )
    sleeve_broker_collector = (
        _sleeve_broker_evidence_collector(str(preflight.expected_account_hash))
        if v4_active
        else None
    )
    canary_store = _ProductionCanaryStore(Path(db_path)) if v4_active else None
    canary_adapter = (
        CanaryExecutionAdapter(
            begin_write=canary_store.begin_write,
            receipt_persister=canary_store.persist_receipt,
        )
        if canary_store is not None
        else None
    )
    return AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=lambda client_id: (
            effective_session_factory()
            if client_id == WRITER_CLIENT_ID
            else (_ for _ in ()).throw(
                ProductionRuntimeConfigurationError("WRITER_CLIENT_ID_MISMATCH")
            )
        ),
        execution_client_id=WRITER_CLIENT_ID,
        execution_lock_verifier=execution_lock_verifier,
        authority_validator=lambda request, evidence: (),
        attempt_persister=attempt_persister,
        result_persister=result_persister,
        model_execution_engine=lazy_engine,
        production_validation_sha256=production_validation_sha256,
        production_authority_validator=validator,
        production_broker_evidence_collector=_broker_evidence_collector(Path(db_path)),
        liability_evidence_collector=_collect_continuity_liability_evidence,
        resource_closer=lazy_engine.close,
        uncertainty_reporter=uncertainty_reporter,
        sleeve_authority_reservation_store=sleeve_reservation_store,
        sleeve_authority_snapshot_reader=sleeve_snapshot_reader,
        sleeve_broker_evidence_collector=sleeve_broker_collector,
        canary_execution_adapter=canary_adapter,
        canary_evidence_collector=(
            canary_store.authority_evidence if canary_store is not None else None
        ),
    )


class _ProductionCanaryStore:
    """Durable canary authorization, idempotency, and lifecycle receipts."""

    SCHEMA = "PRODUCTION_CANARY_EVENT_V1"

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    @staticmethod
    def _verified_events(db: Any) -> list[dict[str, Any]]:
        rows = db.execute(
            "SELECT payload_json,payload_sha256,previous_event_sha256,event_sha256 "
            "FROM canary_authorization_events ORDER BY sequence"
        ).fetchall()
        events: list[dict[str, Any]] = []
        previous: str | None = None
        for payload_json, payload_sha256, stored_previous, event_sha256 in rows:
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ProductionRuntimeConfigurationError(
                    "CANARY_AUTHORITY_CHAIN_INVALID"
                ) from exc
            normalized_previous = (
                None if stored_previous is None else str(stored_previous)
            )
            expected_event = sha256_json(
                {"previous_event_sha256": previous, "payload": payload}
            )
            if (
                payload.get("schema") != _ProductionCanaryStore.SCHEMA
                or sha256_json(payload) != str(payload_sha256)
                or normalized_previous != previous
                or expected_event != str(event_sha256)
            ):
                raise ProductionRuntimeConfigurationError(
                    "CANARY_AUTHORITY_CHAIN_INVALID"
                )
            events.append({**payload, "event_sha256": str(event_sha256)})
            previous = str(event_sha256)
        return events

    @staticmethod
    def _append_in_transaction(
        db: Any,
        *,
        authorization_id: str,
        event_type: str,
        body: Mapping[str, Any],
    ) -> str:
        previous_row = db.execute(
            "SELECT event_sha256 FROM canary_authorization_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = None if previous_row is None else str(previous_row[0])
        payload = {
            "schema": _ProductionCanaryStore.SCHEMA,
            "authorization_id": authorization_id,
            "event_type": event_type,
            **dict(body),
        }
        event_sha256 = sha256_json(
            {"previous_event_sha256": previous, "payload": payload}
        )
        db.execute(
            "INSERT INTO canary_authorization_events("
            "event_id,authorization_id,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                str(new_uuid7()),
                authorization_id,
                event_type,
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                previous,
                event_sha256,
                utc_now(),
            ),
        )
        return event_sha256

    def persist_authorization(
        self, *, candidate_sha256: str, authorization: Any
    ) -> str:
        payload = authorization.model_dump(mode="json")
        with Database.open(self.db_path) as db, db.transaction():
            existing = next(
                (
                    event
                    for event in reversed(self._verified_events(db))
                    if event.get("authorization_id") == authorization.authorization_id
                    and event.get("event_type") == "AUTHORIZED"
                ),
                None,
            )
            if existing is not None:
                stored = existing
                if (
                    stored.get("candidate_sha256") != candidate_sha256
                    or stored.get("authorization_sha256") != authorization.sha256
                ):
                    raise ProductionRuntimeConfigurationError(
                        "CANARY_AUTHORIZATION_CONFLICT"
                    )
                return str(existing["event_sha256"])
            return self._append_in_transaction(
                db,
                authorization_id=authorization.authorization_id,
                event_type="AUTHORIZED",
                body={
                    "candidate_sha256": candidate_sha256,
                    "authorization_sha256": authorization.sha256,
                    "authorization": payload,
                },
            )

    def begin_write(self, execution_key: str) -> bool:
        with Database.open(self.db_path) as db, db.transaction():
            if any(
                event.get("event_type") == "EXECUTION_CLAIMED"
                and event.get("execution_key") == execution_key
                for event in self._verified_events(db)
            ):
                return False
            self._append_in_transaction(
                db,
                authorization_id=execution_key,
                event_type="EXECUTION_CLAIMED",
                body={"execution_key": execution_key},
            )
            return True

    def persist_receipt(self, receipt: Any) -> None:
        with Database.open(self.db_path) as db, db.transaction():
            if any(
                event.get("authorization_id") == receipt.canary_id
                and event.get("event_type") == "LIFECYCLE_RECEIPT"
                and event.get("receipt_sha256") == receipt.sha256
                for event in self._verified_events(db)
            ):
                return
            self._append_in_transaction(
                db,
                authorization_id=receipt.canary_id,
                event_type="LIFECYCLE_RECEIPT",
                body={
                    "receipt_sha256": receipt.sha256,
                    "receipt": receipt.model_dump(mode="json"),
                },
            )

    def authority_evidence(
        self, broker: Any, request: Any, base_evidence: dict[str, Any]
    ) -> dict[str, Any]:
        del broker, base_evidence
        from .multi_universe_models import CanaryAuthorization

        with Database.open(self.db_path) as db:
            events = self._verified_events(db)
            transition_row = db.execute(
                "SELECT phase,payload_json FROM successor_transition_events "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        if transition_row is None:
            return {"fresh": False}
        transition_payload = json.loads(str(transition_row[1]))
        target = dict(transition_payload.get("target") or {})
        authorization = None
        candidate_sha256 = None
        for payload in reversed(events):
            if payload.get("event_type") != "AUTHORIZED":
                continue
            if payload.get("authorization_sha256") == request.authorization_sha256:
                authorization = CanaryAuthorization.model_validate(
                    payload.get("authorization")
                )
                candidate_sha256 = payload.get("candidate_sha256")
                break
        now = datetime.now(timezone.utc)
        return {
            "transition_phase": str(transition_row[0]),
            "ordinary_entry_authority": False,
            "paper_only": True,
            "fresh": bool(
                authorization is not None
                and authorization.issued_at_utc <= now < authorization.expires_at_utc
            ),
            "candidate_sha256": candidate_sha256,
            "authorization_sha256": (
                None if authorization is None else authorization.sha256
            ),
            "authorization": authorization,
            "account_identity_sha256": target.get("account_identity_sha256"),
            "successor_definition_sha256": target.get(
                "successor_definition_sha256"
            ),
            "writer_binding_sha256": target.get("writer_binding_sha256"),
            "request_sha256": request.sha256,
        }


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
        binding.perm_id is None or int(payload.get("perm_id") or 0) == binding.perm_id,
        int(payload.get("execution_client_id") or -1) == binding.execution_client_id,
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
                if getattr(config, "target_successor_definition_sha256", None):
                    from .multi_universe_schema import install_multi_universe_schema_v4

                    install_multi_universe_schema_v4(db)
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
                current_adapter_sha256=production_validation_sha256,
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
                    writer_sole_capability = (
                        str(exc) == "AUTHORITATIVE_WRITER_ALREADY_ATTACHED"
                    )
            watchdog.start(2.0)
            watchdog_started = True

            v4_active = (
                getattr(config, "target_successor_definition_sha256", None)
                is not None
            )
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
                    (
                        not v4_active
                        or getattr(writer, "canary_execution_adapter", None) is not None
                    ),
                    (
                        not v4_active
                        or callable(getattr(writer, "canary_evidence_collector", None))
                    ),
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
                "canary_execution_adapter_wired": (
                    getattr(writer, "canary_execution_adapter", None) is not None
                ),
                "canary_evidence_collector_callable": callable(
                    getattr(writer, "canary_evidence_collector", None)
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
