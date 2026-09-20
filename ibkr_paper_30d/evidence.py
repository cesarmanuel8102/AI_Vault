from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .canonical import canonical_bytes
from .persistence import Database
from .repositories import utc_now


class ImmutableRecordError(RuntimeError):
    pass


class MissingPredecessorError(RuntimeError):
    pass


class EvidenceIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvidenceReceipt:
    record_id: str
    sha256: str
    durable: bool
    committed_at_utc: str


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    reason: str


@dataclass(frozen=True)
class StoredEvidence:
    receipt: EvidenceReceipt
    payload: dict[str, Any]


def _no_phase_hook(_: str) -> None:
    return None


class EvidenceFreezer:
    def __init__(
        self,
        db: Database,
        *,
        phase_hook: Callable[[str], None] = _no_phase_hook,
    ):
        self.db = db
        self.phase_hook = phase_hook

    def exists(self, decision_id: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM decision_records WHERE decision_id=?", (decision_id,)
        ).fetchone()
        return row is not None

    def freeze(self, record: Mapping[str, object]) -> EvidenceReceipt:
        decision_id = str(record.get("decision_id", "")).strip()
        if not decision_id:
            raise ValueError("decision_id is required")
        if self.exists(decision_id):
            raise ImmutableRecordError(f"decision {decision_id} is already frozen")
        predecessor = record.get("predecessor_id")
        predecessor_id = str(predecessor).strip() if predecessor is not None else None
        if predecessor_id and not self.exists(predecessor_id):
            raise MissingPredecessorError(predecessor_id)

        payload = canonical_bytes(dict(record))
        digest = hashlib.sha256(payload).hexdigest()
        committed_at = utc_now()
        self.phase_hook("BEFORE_COMMIT")
        try:
            with self.db.transaction() as tx:
                tx.execute(
                    "INSERT INTO decision_records(decision_id,predecessor_id,payload_json,payload_sha256,created_at_utc) "
                    "VALUES(?,?,?,?,?)",
                    (
                        decision_id,
                        predecessor_id,
                        payload.decode("utf-8"),
                        digest,
                        committed_at,
                    ),
                )
                self.phase_hook("DURING_TRANSACTION")
        except sqlite3.IntegrityError as exc:
            raise ImmutableRecordError(decision_id) from exc

        self.phase_hook("AFTER_COMMIT")
        stored = self.read(decision_id)
        if stored.receipt.sha256 != digest or not self.verify(stored.receipt).valid:
            raise EvidenceIntegrityError("durable read-back mismatch")
        return EvidenceReceipt(decision_id, digest, True, committed_at)

    def read(self, decision_id: str) -> StoredEvidence:
        row = self.db.execute(
            "SELECT payload_json,payload_sha256,created_at_utc FROM decision_records "
            "WHERE decision_id=?",
            (decision_id,),
        ).fetchone()
        if row is None:
            raise KeyError(decision_id)
        payload_json, digest, created_at = map(str, row)
        return StoredEvidence(
            receipt=EvidenceReceipt(decision_id, digest, True, created_at),
            payload=json.loads(payload_json),
        )

    def verify(self, receipt: EvidenceReceipt) -> VerificationResult:
        row = self.db.execute(
            "SELECT payload_json,payload_sha256 FROM decision_records WHERE decision_id=?",
            (receipt.record_id,),
        ).fetchone()
        if row is None:
            return VerificationResult(False, "MISSING_RECORD")
        payload_json, stored_digest = map(str, row)
        actual = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        if actual != stored_digest or actual != receipt.sha256:
            return VerificationResult(False, "HASH_MISMATCH")
        return VerificationResult(True, "VALID")
