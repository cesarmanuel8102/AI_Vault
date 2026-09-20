from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .canonical import canonical_bytes
from .market_observation import MarketObservation, ObservationWindow


@dataclass(frozen=True)
class LedgerReceipt:
    path: Path
    window_id: str
    first_sequence: int
    last_sequence: int
    record_count: int
    window_sha256: str
    last_record_sha256: str
    durable: bool


@dataclass(frozen=True)
class LedgerVerification:
    valid: bool
    status: str
    record_count: int = 0
    window_count: int = 0
    last_record_sha256: str | None = None


class MarketObservationLedger:
    def __init__(self, path: str | Path) -> None:
        raw = Path(path)
        if ".." in raw.parts:
            raise ValueError("PATH_TRAVERSAL")
        self.path = raw.absolute()
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")

    def append_window(self, window: ObservationWindow) -> LedgerReceipt:
        payload = window.model_dump(mode="json")
        _reject_forbidden_evidence(payload)
        sequences = [item.sequence for item in window.observations]
        if not sequences or sequences != list(range(len(sequences))):
            raise ValueError("SEQUENCE_NOT_MONOTONIC")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._reject_redirected_path()
        with self._exclusive_lock():
            verification = self.verify()
            if not verification.valid:
                raise ValueError(f"LEDGER_INTEGRITY_FAILURE:{verification.status}")
            existing_records = self._read_records() if self.path.exists() else []
            if any(
                record.get("window", {}).get("window_id") == window.window_id
                for record in existing_records
            ):
                raise ValueError("SEQUENCE_NOT_MONOTONIC")

            observations = [
                item.model_dump(mode="json", exclude={"record_sha256"})
                for item in window.observations
            ]
            manifest = self._window_manifest(window)
            window_sha256 = hashlib.sha256(
                canonical_bytes({"window": manifest, "observations": observations})
            ).hexdigest()
            previous = verification.last_record_sha256
            first_sequence = verification.record_count
            encoded_records: list[bytes] = []
            for offset, observation in enumerate(observations):
                record: dict[str, Any] = {
                    "schema": "MARKET_DATA_OBSERVATION_V1",
                    "ledger_sequence": first_sequence + offset,
                    "previous_record_sha256": previous,
                    "window": manifest,
                    "window_sha256": window_sha256,
                    **observation,
                }
                digest = hashlib.sha256(canonical_bytes(record)).hexdigest()
                record["record_sha256"] = digest
                encoded_records.append(canonical_bytes(record) + b"\n")
                previous = digest

            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
            if not self.path.exists():
                flags |= os.O_EXCL
            descriptor = os.open(self.path, flags, 0o600)
            try:
                with os.fdopen(descriptor, "ab", closefd=False) as handle:
                    handle.write(b"".join(encoded_records))
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                os.close(descriptor)

            result = self.verify()
            if not result.valid or result.last_record_sha256 != previous:
                raise RuntimeError("DURABLE_READBACK_FAILED")
            return LedgerReceipt(
                path=self.path,
                window_id=window.window_id,
                first_sequence=first_sequence,
                last_sequence=first_sequence + len(observations) - 1,
                record_count=len(observations),
                window_sha256=window_sha256,
                last_record_sha256=previous or "",
                durable=True,
            )

    def verify(self) -> LedgerVerification:
        if not self.path.exists():
            return LedgerVerification(True, "EMPTY")
        if self.path.is_symlink():
            return LedgerVerification(False, "PATH_REDIRECTED")
        raw = self.path.read_bytes()
        if not raw:
            return LedgerVerification(True, "EMPTY")
        if not raw.endswith(b"\n"):
            return LedgerVerification(False, "TRUNCATED_RECORD")
        try:
            records = [json.loads(line) for line in raw.splitlines()]
        except (json.JSONDecodeError, UnicodeDecodeError):
            return LedgerVerification(False, "MALFORMED_RECORD")

        previous: str | None = None
        windows: dict[str, dict[str, Any]] = {}
        completed_windows: set[str] = set()
        active_window: str | None = None
        for expected_sequence, record in enumerate(records):
            try:
                _reject_forbidden_evidence(record)
            except ValueError:
                return LedgerVerification(False, "FORBIDDEN_EVIDENCE_KEY")
            if record.get("schema") != "MARKET_DATA_OBSERVATION_V1":
                return LedgerVerification(False, "SCHEMA_MISMATCH")
            if record.get("ledger_sequence") != expected_sequence:
                return LedgerVerification(False, "SEQUENCE_NOT_MONOTONIC")
            if record.get("previous_record_sha256") != previous:
                return LedgerVerification(False, "HASH_MISMATCH")
            claimed = record.get("record_sha256")
            unsigned = dict(record)
            unsigned.pop("record_sha256", None)
            actual = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
            if claimed != actual:
                return LedgerVerification(False, "HASH_MISMATCH")
            previous = actual

            manifest = record.get("window")
            if not isinstance(manifest, dict) or not isinstance(
                manifest.get("window_id"), str
            ):
                return LedgerVerification(False, "WINDOW_MISMATCH")
            window_id = manifest["window_id"]
            if active_window != window_id:
                if window_id in completed_windows:
                    return LedgerVerification(False, "WINDOW_MISMATCH")
                if active_window is not None:
                    completed_windows.add(active_window)
                active_window = window_id
            state = windows.setdefault(
                window_id,
                {
                    "manifest": manifest,
                    "digest": record.get("window_sha256"),
                    "observations": [],
                },
            )
            if state["manifest"] != manifest or state["digest"] != record.get(
                "window_sha256"
            ):
                return LedgerVerification(False, "WINDOW_MISMATCH")
            observation = {
                name: record[name]
                for name in MarketObservation.model_fields
                if name != "record_sha256" and name in record
            }
            state["observations"].append(observation)

        for state in windows.values():
            manifest = state["manifest"]
            observations = state["observations"]
            if manifest.get("observation_count") != len(observations):
                return LedgerVerification(False, "WINDOW_MISMATCH")
            if [item.get("sequence") for item in observations] != list(
                range(len(observations))
            ):
                return LedgerVerification(False, "SEQUENCE_NOT_MONOTONIC")
            digest = hashlib.sha256(
                canonical_bytes({"window": manifest, "observations": observations})
            ).hexdigest()
            if digest != state["digest"]:
                return LedgerVerification(False, "WINDOW_HASH_MISMATCH")
        return LedgerVerification(
            True,
            "VALID",
            record_count=len(records),
            window_count=len(windows),
            last_record_sha256=previous,
        )

    @staticmethod
    def _window_manifest(window: ObservationWindow) -> dict[str, Any]:
        return {
            "window_id": window.window_id,
            "started_at_utc": window.started_at_utc.isoformat(),
            "ended_at_utc": window.ended_at_utc.isoformat(),
            "status": window.status,
            "reason_codes": list(window.reason_codes),
            "metadata": window.metadata,
            "identity_receipt_sha256": window.identity_receipt_sha256,
            "reconciliation_receipt_sha256": window.reconciliation_receipt_sha256,
            "observation_count": len(window.observations),
        }

    def _read_records(self) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
        ]

    def _reject_redirected_path(self) -> None:
        current = self.path.parent
        while current != current.parent:
            if current.is_symlink():
                raise ValueError("PATH_REDIRECTED")
            current = current.parent
        if self.path.exists() and self.path.is_symlink():
            raise ValueError("PATH_REDIRECTED")

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        try:
            descriptor = os.open(
                self.lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as exc:
            raise RuntimeError("LEDGER_BUSY") from exc
        try:
            os.close(descriptor)
            yield
        finally:
            self.lock_path.unlink(missing_ok=True)


def _reject_forbidden_evidence(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in {"account", "account_id", "ibkr_account"} or any(
                marker in normalized for marker in ("password", "secret", "token")
            ):
                raise ValueError("FORBIDDEN_EVIDENCE_KEY")
            _reject_forbidden_evidence(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _reject_forbidden_evidence(nested)
        return
    if isinstance(value, str) and re.search(r"\bDU\d{4,}\b", value, re.IGNORECASE):
        raise ValueError("FORBIDDEN_EVIDENCE_KEY")
