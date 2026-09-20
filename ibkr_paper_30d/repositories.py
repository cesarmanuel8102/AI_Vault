from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from .canonical import canonical_bytes
from .persistence import Database
from .types import new_uuid7


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    count: int
    first_invalid_sequence: int | None = None


class EventRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _event_hash(
        sequence: int,
        event_id: str,
        event_type: str,
        payload_json: str,
        payload_sha256: str,
        previous_hash: str | None,
        created_at_utc: str,
    ) -> str:
        envelope = {
            "sequence": sequence,
            "event_id": event_id,
            "event_type": event_type,
            "payload_json": payload_json,
            "payload_sha256": payload_sha256,
            "previous_event_sha256": previous_hash,
            "created_at_utc": created_at_utc,
        }
        return hashlib.sha256(canonical_bytes(envelope)).hexdigest()

    def append(self, event_type: str, payload: Mapping[str, object]) -> str:
        last = self.db.execute(
            "SELECT sequence, event_sha256 FROM state_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if last is None else int(last[0]) + 1
        previous_hash = None if last is None else str(last[1])
        event_id = str(new_uuid7())
        payload_bytes = canonical_bytes(payload)
        payload_json = payload_bytes.decode("utf-8")
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
        created_at = utc_now()
        event_sha256 = self._event_hash(
            sequence,
            event_id,
            event_type,
            payload_json,
            payload_sha256,
            previous_hash,
            created_at,
        )
        self.db.execute(
            "INSERT INTO state_events(sequence,event_id,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
            (
                sequence,
                event_id,
                event_type,
                payload_json,
                payload_sha256,
                previous_hash,
                event_sha256,
                created_at,
            ),
        )
        return event_id

    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM state_events").fetchone()[0])

    def verify_chain(self) -> ChainVerification:
        rows = self.db.execute(
            "SELECT sequence,event_id,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc "
            "FROM state_events ORDER BY sequence"
        ).fetchall()
        expected_previous = None
        for row in rows:
            sequence, event_id, event_type, payload_json, payload_sha256, previous, digest, created = row
            try:
                canonical_payload = canonical_bytes(json.loads(payload_json))
            except (json.JSONDecodeError, TypeError, ValueError):
                return ChainVerification(False, len(rows), int(sequence))
            if hashlib.sha256(canonical_payload).hexdigest() != payload_sha256:
                return ChainVerification(False, len(rows), int(sequence))
            expected = self._event_hash(
                int(sequence),
                str(event_id),
                str(event_type),
                str(payload_json),
                str(payload_sha256),
                expected_previous,
                str(created),
            )
            if previous != expected_previous or digest != expected:
                return ChainVerification(False, len(rows), int(sequence))
            expected_previous = str(digest)
        return ChainVerification(True, len(rows))
