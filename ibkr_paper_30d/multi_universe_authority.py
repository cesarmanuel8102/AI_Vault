"""Append-only authority records for the two-sleeve successor runtime."""

from __future__ import annotations

import json
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict

from .canonical import canonical_bytes, sha256_json
from .multi_universe_models import (
    CapitalSleeve,
    OwnerEconomicRiskAuthorization,
    SleeveAuthorityDefinition,
    TransitionTarget,
)
from .multi_universe_schema import verify_multi_universe_schema_v4
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


class MultiUniverseAuthorityError(RuntimeError):
    pass


class AuthorityBindingReceipt(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS"] = "PASS"
    regular_sleeve_authority_sha256: str
    continuous_sleeve_authority_sha256: str
    economic_risk_authorization_sha256: str
    idempotent: bool


class MultiUniverseAuthorityStore:
    """Persist and replay immutable authority without trusting launch callers."""

    SLEEVE_SCHEMA = "SLEEVE_AUTHORITY_EVENT_V1"
    ECONOMIC_SCHEMA = "OWNER_ECONOMIC_RISK_AUTHORIZATION_EVENT_V1"

    def __init__(self, db: Database):
        verify_multi_universe_schema_v4(db)
        self.db = db

    def _events(self, table: str, schema: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            f"SELECT payload_json,payload_sha256,previous_event_sha256,"  # noqa: S608
            f"event_sha256 FROM {table} ORDER BY sequence"
        ).fetchall()
        events: list[dict[str, Any]] = []
        previous: str | None = None
        for payload_json, payload_sha, stored_previous, event_sha in rows:
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError) as exc:
                raise MultiUniverseAuthorityError("AUTHORITY_PROJECTION_AMBIGUOUS") from exc
            normalized_previous = (
                None if stored_previous is None else str(stored_previous)
            )
            if (
                payload.get("schema") != schema
                or sha256_json(payload) != str(payload_sha)
                or normalized_previous != previous
                or sha256_json(
                    {"previous_event_sha256": previous, "payload": payload}
                )
                != str(event_sha)
            ):
                raise MultiUniverseAuthorityError("AUTHORITY_PROJECTION_AMBIGUOUS")
            events.append(payload)
            previous = str(event_sha)
        return events

    def _insert(
        self,
        *,
        table: str,
        authority_column: str,
        authority_value: str,
        event_type: str,
        schema: str,
        payload: dict[str, Any],
    ) -> None:
        body = {
            "schema": schema,
            "event_type": event_type,
            **payload,
        }
        row = self.db.execute(
            f"SELECT event_sha256 FROM {table} ORDER BY sequence DESC LIMIT 1"  # noqa: S608
        ).fetchone()
        previous = None if row is None else str(row[0])
        event_sha = sha256_json(
            {"previous_event_sha256": previous, "payload": body}
        )
        self.db.execute(
            f"INSERT INTO {table}(event_id,{authority_column},event_type,"  # noqa: S608
            "payload_json,payload_sha256,previous_event_sha256,event_sha256,"
            "created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
            (
                str(new_uuid7()),
                authority_value,
                event_type,
                canonical_bytes(body).decode("utf-8"),
                sha256_json(body),
                previous,
                event_sha,
                utc_now(),
            ),
        )

    @staticmethod
    def _ordered_authorities(
        sleeve_authorities: Sequence[SleeveAuthorityDefinition],
    ) -> tuple[SleeveAuthorityDefinition, SleeveAuthorityDefinition]:
        by_sleeve = {item.sleeve: item for item in sleeve_authorities}
        if len(by_sleeve) != 2 or set(by_sleeve) != {
            CapitalSleeve.REGULAR_SLEEVE,
            CapitalSleeve.CONTINUOUS_SLEEVE,
        }:
            raise MultiUniverseAuthorityError("AUTHORITY_SET_INVALID")
        return (
            by_sleeve[CapitalSleeve.REGULAR_SLEEVE],
            by_sleeve[CapitalSleeve.CONTINUOUS_SLEEVE],
        )

    @staticmethod
    def _validate_target(
        target: TransitionTarget,
        regular: SleeveAuthorityDefinition,
        continuous: SleeveAuthorityDefinition,
        economic: OwnerEconomicRiskAuthorization,
    ) -> None:
        if (
            regular.sha256 != target.regular_sleeve_authority_sha256
            or continuous.sha256 != target.continuous_sleeve_authority_sha256
            or economic.sha256 != target.economic_risk_authorization_sha256
            or economic.successor_definition_sha256
            != target.successor_definition_sha256
        ):
            raise MultiUniverseAuthorityError("AUTHORITY_TARGET_MISMATCH")

    def _current(
        self,
    ) -> tuple[
        dict[CapitalSleeve, SleeveAuthorityDefinition],
        OwnerEconomicRiskAuthorization | None,
    ]:
        sleeve_events = self._events(
            "sleeve_authority_events", self.SLEEVE_SCHEMA
        )
        economic_events = self._events(
            "owner_economic_risk_authorization_events", self.ECONOMIC_SCHEMA
        )
        authorities: dict[CapitalSleeve, SleeveAuthorityDefinition] = {}
        for event in sleeve_events:
            if event.get("event_type") != "SLEEVE_AUTHORITY_BOUND":
                raise MultiUniverseAuthorityError("AUTHORITY_PROJECTION_AMBIGUOUS")
            try:
                authority = SleeveAuthorityDefinition.model_validate(
                    event.get("authority")
                )
            except ValueError as exc:
                raise MultiUniverseAuthorityError(
                    "AUTHORITY_PROJECTION_AMBIGUOUS"
                ) from exc
            if (
                event.get("authority_sha256") != authority.sha256
                or authority.sleeve in authorities
            ):
                raise MultiUniverseAuthorityError("AUTHORITY_PROJECTION_AMBIGUOUS")
            authorities[authority.sleeve] = authority
        if len(economic_events) > 1:
            raise MultiUniverseAuthorityError("AUTHORITY_PROJECTION_AMBIGUOUS")
        economic: OwnerEconomicRiskAuthorization | None = None
        if economic_events:
            event = economic_events[0]
            if event.get("event_type") != "ECONOMIC_RISK_AUTHORIZATION_BOUND":
                raise MultiUniverseAuthorityError("AUTHORITY_PROJECTION_AMBIGUOUS")
            try:
                economic = OwnerEconomicRiskAuthorization.model_validate(
                    event.get("authorization")
                )
            except ValueError as exc:
                raise MultiUniverseAuthorityError(
                    "AUTHORITY_PROJECTION_AMBIGUOUS"
                ) from exc
            if event.get("authorization_sha256") != economic.sha256:
                raise MultiUniverseAuthorityError("AUTHORITY_PROJECTION_AMBIGUOUS")
        return authorities, economic

    def bind(
        self,
        *,
        target: TransitionTarget,
        sleeve_authorities: Sequence[SleeveAuthorityDefinition],
        economic_authorization: OwnerEconomicRiskAuthorization,
    ) -> AuthorityBindingReceipt:
        with self.db.transaction():
            return self.bind_in_transaction(
                target=target,
                sleeve_authorities=sleeve_authorities,
                economic_authorization=economic_authorization,
            )

    def bind_in_transaction(
        self,
        *,
        target: TransitionTarget,
        sleeve_authorities: Sequence[SleeveAuthorityDefinition],
        economic_authorization: OwnerEconomicRiskAuthorization,
    ) -> AuthorityBindingReceipt:
        if not self.db.connection.in_transaction:
            raise MultiUniverseAuthorityError("ATOMIC_AUTHORITY_BIND_REQUIRED")
        regular, continuous = self._ordered_authorities(sleeve_authorities)
        self._validate_target(target, regular, continuous, economic_authorization)
        current, current_economic = self._current()
        if current or current_economic is not None:
            if current != {
                CapitalSleeve.REGULAR_SLEEVE: regular,
                CapitalSleeve.CONTINUOUS_SLEEVE: continuous,
            } or current_economic != economic_authorization:
                raise MultiUniverseAuthorityError("AUTHORITY_BINDING_CONFLICT")
            return self._receipt(regular, continuous, economic_authorization, True)
        for authority in (regular, continuous):
            self._insert(
                table="sleeve_authority_events",
                authority_column="sleeve",
                authority_value=authority.sleeve.value,
                event_type="SLEEVE_AUTHORITY_BOUND",
                schema=self.SLEEVE_SCHEMA,
                payload={
                    "authority": authority.model_dump(mode="json"),
                    "authority_sha256": authority.sha256,
                    "transition_target_sha256": target.sha256,
                },
            )
        self._insert(
            table="owner_economic_risk_authorization_events",
            authority_column="authorization_id",
            authority_value=economic_authorization.authorization_id,
            event_type="ECONOMIC_RISK_AUTHORIZATION_BOUND",
            schema=self.ECONOMIC_SCHEMA,
            payload={
                "authorization": economic_authorization.model_dump(mode="json"),
                "authorization_sha256": economic_authorization.sha256,
                "transition_target_sha256": target.sha256,
            },
        )
        return self._receipt(regular, continuous, economic_authorization, False)

    @staticmethod
    def _receipt(
        regular: SleeveAuthorityDefinition,
        continuous: SleeveAuthorityDefinition,
        economic: OwnerEconomicRiskAuthorization,
        idempotent: bool,
    ) -> AuthorityBindingReceipt:
        return AuthorityBindingReceipt(
            regular_sleeve_authority_sha256=regular.sha256,
            continuous_sleeve_authority_sha256=continuous.sha256,
            economic_risk_authorization_sha256=economic.sha256,
            idempotent=idempotent,
        )

    def sleeve_authority(
        self, sleeve: CapitalSleeve
    ) -> SleeveAuthorityDefinition | None:
        authorities, _ = self._current()
        return authorities.get(CapitalSleeve(sleeve))

    def economic_authorization(self) -> OwnerEconomicRiskAuthorization | None:
        _, economic = self._current()
        return economic
