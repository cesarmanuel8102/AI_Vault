"""Canonical provider lifecycle anchored to authenticated PAPER broker time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .continuity_models import ProviderInvocationState
from .continuity_store import ContinuityStore
from .trader_invocation import InvocationRequest


class ProviderLifecycleError(RuntimeError):
    pass


class BrokerTimeEvidence(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    time_utc: datetime
    environment: str
    account_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProviderInvocationToken:
    invocation_id: str
    decision_cycle_id: str
    launch_attempt_id: str
    pid: int
    boot_session_identity: str
    started_at_broker_utc: datetime
    declared_deadline_broker_utc: datetime
    in_flight_event_sha256: str


_TERMINAL_STATES = {
    ProviderInvocationState.TIMEOUT_CONFIRMED,
    ProviderInvocationState.PROCESS_ERROR,
    ProviderInvocationState.COMPLETED_UNACCEPTED,
    ProviderInvocationState.COMPLETED_ACCEPTED,
    ProviderInvocationState.ABANDONED,
}


class ProviderLifecycleRecorder:
    def __init__(
        self,
        store: ContinuityStore,
        *,
        launch_attempt_id: str,
        pid: int,
        boot_session_identity: str,
    ) -> None:
        if not launch_attempt_id or pid <= 0 or not boot_session_identity:
            raise ValueError("launch attempt, positive PID, and boot session are required")
        self.store = store
        self.launch_attempt_id = launch_attempt_id
        self.pid = pid
        self.boot_session_identity = boot_session_identity

    @staticmethod
    def _validated_time(evidence: BrokerTimeEvidence | None) -> datetime:
        if evidence is None:
            raise ProviderLifecycleError("BROKER_TIME_REQUIRED")
        value = evidence.time_utc
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProviderLifecycleError("BROKER_TIME_NAIVE")
        if evidence.environment != "PAPER":
            raise ProviderLifecycleError("BROKER_TIME_NOT_PAPER")
        return value

    def _latest_broker_time(self) -> datetime | None:
        rows = self.store.db.execute(
            "SELECT invocation_id FROM provider_invocation_events "
            "GROUP BY invocation_id ORDER BY MAX(sequence) DESC"
        ).fetchall()
        latest: datetime | None = None
        for row in rows:
            projection = self.store.provider_projection(str(row[0]))
            raw = projection.get("payload", {}).get("broker_time_utc")
            if raw:
                observed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                latest = observed if latest is None else max(latest, observed)
        return latest

    def _assert_monotonic(
        self, evidence: BrokerTimeEvidence | None, *, floor: datetime | None = None
    ) -> datetime:
        current = self._validated_time(evidence)
        authoritative_floor = floor or self._latest_broker_time()
        if authoritative_floor is not None and current < authoritative_floor:
            raise ProviderLifecycleError("BROKER_TIME_BACKWARD")
        return current

    def begin(
        self, request: InvocationRequest, broker_time_utc: BrokerTimeEvidence | None
    ) -> ProviderInvocationToken:
        started = self._assert_monotonic(broker_time_utc)
        deadline = started + timedelta(seconds=request.timeout_seconds)
        current = ProviderInvocationState(
            self.store.provider_projection(request.invocation_id)["state"]
        )
        if current in _TERMINAL_STATES:
            raise ProviderLifecycleError("TERMINAL_CONFLICT")
        payload = {
            "decision_cycle_id": request.decision_cycle_id,
            "launch_attempt_id": self.launch_attempt_id,
            "pid": self.pid,
            "boot_session_identity": self.boot_session_identity,
            "broker_time_utc": started.isoformat(),
            "declared_deadline_broker_utc": deadline.isoformat(),
            "broker_time_evidence_sha256": broker_time_utc.evidence_sha256,
            "account_identity_sha256": broker_time_utc.account_identity_sha256,
        }
        event_hash = self.store.append_provider_event(
            request.invocation_id,
            ProviderInvocationState.IN_FLIGHT.value,
            payload,
            event_id=f"provider:{request.invocation_id}:in-flight",
        )
        return ProviderInvocationToken(
            invocation_id=request.invocation_id,
            decision_cycle_id=request.decision_cycle_id,
            launch_attempt_id=self.launch_attempt_id,
            pid=self.pid,
            boot_session_identity=self.boot_session_identity,
            started_at_broker_utc=started,
            declared_deadline_broker_utc=deadline,
            in_flight_event_sha256=event_hash,
        )

    def _terminal(
        self,
        token: ProviderInvocationToken,
        state: ProviderInvocationState,
        broker_time_utc: BrokerTimeEvidence | None,
        *,
        failure_code: str | None = None,
        result_sha256: str | None = None,
    ) -> str:
        observed = self._assert_monotonic(
            broker_time_utc, floor=token.started_at_broker_utc
        )
        projection = self.store.provider_projection(token.invocation_id)
        current = ProviderInvocationState(projection["state"])
        if current in _TERMINAL_STATES and current != state:
            raise ProviderLifecycleError("TERMINAL_CONFLICT")
        if current not in {ProviderInvocationState.IN_FLIGHT, state}:
            raise ProviderLifecycleError("INVALID_PROVIDER_TRANSITION")
        payload = {
            "decision_cycle_id": token.decision_cycle_id,
            "launch_attempt_id": token.launch_attempt_id,
            "pid": token.pid,
            "boot_session_identity": token.boot_session_identity,
            "broker_time_utc": observed.isoformat(),
            "broker_time_evidence_sha256": broker_time_utc.evidence_sha256,
            "account_identity_sha256": broker_time_utc.account_identity_sha256,
            "failure_code": failure_code,
            "result_sha256": result_sha256,
            "in_flight_event_sha256": token.in_flight_event_sha256,
        }
        return self.store.append_provider_event(
            token.invocation_id,
            state.value,
            payload,
            event_id=f"provider:{token.invocation_id}:terminal",
        )

    def complete(
        self,
        token: ProviderInvocationToken,
        state: str | ProviderInvocationState,
        broker_time_utc: BrokerTimeEvidence | None,
        result_sha256: str | None = None,
    ) -> str:
        terminal = ProviderInvocationState(state)
        if terminal not in {
            ProviderInvocationState.COMPLETED_ACCEPTED,
            ProviderInvocationState.COMPLETED_UNACCEPTED,
        }:
            raise ProviderLifecycleError("COMPLETION_STATE_INVALID")
        expected_accepted = terminal == ProviderInvocationState.COMPLETED_ACCEPTED
        result = self.store.db.execute(
            "SELECT accepted,payload_sha256 FROM trader_results WHERE invocation_id=?",
            (token.invocation_id,),
        ).fetchone()
        if (
            result is None
            or bool(result[0]) != expected_accepted
            or result_sha256 is None
            or str(result[1]) != result_sha256
        ):
            raise ProviderLifecycleError("RESULT_NOT_DURABLE")
        return self._terminal(
            token, terminal, broker_time_utc, result_sha256=result_sha256
        )

    def fail(
        self,
        token: ProviderInvocationToken,
        failure_code: str,
        broker_time_utc: BrokerTimeEvidence | None,
    ) -> str:
        state = (
            ProviderInvocationState.TIMEOUT_CONFIRMED
            if failure_code == "PROVIDER_TIMEOUT"
            else ProviderInvocationState.PROCESS_ERROR
        )
        return self._terminal(
            token, state, broker_time_utc, failure_code=failure_code
        )

    def recover_abandoned(
        self,
        current_lock_owner: dict[str, Any] | None,
        broker_time_utc: BrokerTimeEvidence | None,
    ) -> tuple[str, ...]:
        observed = self._assert_monotonic(broker_time_utc)
        if not current_lock_owner or current_lock_owner.get("status") != "OWNED":
            return ()
        invocation_ids = [
            str(row[0])
            for row in self.store.db.execute(
                "SELECT invocation_id FROM provider_invocation_events GROUP BY invocation_id"
            ).fetchall()
        ]
        abandoned: list[str] = []
        for invocation_id in invocation_ids:
            projection = self.store.provider_projection(invocation_id)
            if projection["state"] != ProviderInvocationState.IN_FLIGHT.value:
                continue
            payload = projection["payload"]
            same_owner = (
                int(payload.get("pid", -1)) == int(current_lock_owner.get("pid", -2))
                and payload.get("boot_session_identity")
                == current_lock_owner.get("boot_session_identity")
            )
            requested_invocation = current_lock_owner.get("invocation_id")
            if requested_invocation is not None:
                same_owner = same_owner and requested_invocation == invocation_id
            if same_owner:
                continue
            token = ProviderInvocationToken(
                invocation_id=invocation_id,
                decision_cycle_id=str(payload["decision_cycle_id"]),
                launch_attempt_id=str(payload["launch_attempt_id"]),
                pid=int(payload["pid"]),
                boot_session_identity=str(payload["boot_session_identity"]),
                started_at_broker_utc=datetime.fromisoformat(
                    str(payload["broker_time_utc"]).replace("Z", "+00:00")
                ),
                declared_deadline_broker_utc=datetime.fromisoformat(
                    str(payload["declared_deadline_broker_utc"]).replace("Z", "+00:00")
                ),
                in_flight_event_sha256=str(projection["event_sha256"]),
            )
            self._terminal(
                token,
                ProviderInvocationState.ABANDONED,
                broker_time_utc.model_copy(update={"time_utc": observed}),
                failure_code="EXECUTION_LOCK_OWNER_REPLACED",
            )
            abandoned.append(invocation_id)
        return tuple(abandoned)
