"""Validate-only and one-phase apply orchestration for the V4 successor."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from .canonical import canonical_bytes, sha256_json
from .multi_universe_models import (
    GIT_HEAD_PATTERN,
    SHA256_PATTERN,
    TransitionPhase,
    TransitionTarget,
)
from .multi_universe_schema import install_multi_universe_schema_v4
from .multi_universe_transition import (
    MultiUniverseTransitionCoordinator,
    MultiUniverseTransitionError,
)
from .persistence import Database
from .successor_supervision import (
    SuccessorSupervisionBinder,
    SupervisionBindingPlan,
)


class _MaintenanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class MaintenanceConfig(_MaintenanceModel):
    repo_root: Path
    database_path: Path
    backup_directory: Path
    authority_file_paths: tuple[Path, ...]
    approved_head: str = Field(pattern=GIT_HEAD_PATTERN)
    target: TransitionTarget
    requested_phase: TransitionPhase
    now_utc: datetime
    maximum_evidence_age_seconds: int = Field(default=120, gt=0, le=900)


class MaintenanceEvidence(_MaintenanceModel):
    observed_at_utc: datetime
    current_head: str = Field(pattern=GIT_HEAD_PATTERN)
    tracked_tree_clean: bool
    paper_port_4002_listening: bool
    live_port_4001_listening: bool
    authenticated_paper: bool
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    broker_state_certain: bool
    writer_count: int = Field(ge=0)
    writer_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    receipt_sha256: tuple[str, ...]
    phase_evidence: dict[str, Any]


class MaintenanceResult(_MaintenanceModel):
    status: Literal["PASS", "BLOCK"]
    reason_codes: tuple[str, ...]
    phase: TransitionPhase | None = None
    phase_event_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    mutation_performed: bool = False
    idempotent: bool = False
    backup_manifest_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


def _readonly_state(path: Path) -> tuple[bool, str | None, str | None]:
    if not path.is_file():
        return False, None, None
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "successor_transition_events" not in tables:
            return False, None, None
        version = connection.execute(
            "SELECT COUNT(*) FROM schema_versions WHERE version=4"
        ).fetchone()
        v4 = bool(version and int(version[0]) == 1)
        row = connection.execute(
            "SELECT transition_id,phase,payload_json FROM successor_transition_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return v4, None, None
        payload = json.loads(str(row[2]))
        return v4, str(row[1]), str(payload.get("target_sha256") or "")
    finally:
        connection.close()


def validate_maintenance(
    config: MaintenanceConfig, evidence: MaintenanceEvidence
) -> MaintenanceResult:
    reasons: list[str] = []
    age = (config.now_utc - evidence.observed_at_utc).total_seconds()
    if age < 0 or age > config.maximum_evidence_age_seconds:
        reasons.append("MAINTENANCE_EVIDENCE_STALE")
    if evidence.current_head != config.approved_head:
        reasons.append("APPROVED_HEAD_MISMATCH")
    if config.target.approved_git_head != config.approved_head:
        reasons.append("TRANSITION_HEAD_MISMATCH")
    if not evidence.tracked_tree_clean:
        reasons.append("TRACKED_TREE_DIRTY")
    if not evidence.paper_port_4002_listening or not evidence.authenticated_paper:
        reasons.append("PAPER_PORT_UNAVAILABLE")
    if evidence.live_port_4001_listening:
        reasons.append("POSSIBLE_LIVE_CONNECTION")
    if not evidence.broker_state_certain:
        reasons.append("BROKER_STATE_UNCERTAIN")
    if evidence.writer_count > 1:
        reasons.append("DUPLICATE_WRITER_ACTIVE")
    if evidence.account_identity_sha256 != config.target.account_identity_sha256:
        reasons.append("PAPER_ACCOUNT_MISMATCH")
    if evidence.writer_binding_sha256 != config.target.writer_binding_sha256:
        reasons.append("WRITER_BINDING_MISMATCH")
    required_receipts = {
        config.target.owner_authorization_sha256,
        config.target.canary_authorization_sha256,
        config.target.successor_definition_sha256,
    }
    if not required_receipts.issubset(set(evidence.receipt_sha256)):
        reasons.append("MAINTENANCE_RECEIPTS_INCOMPLETE")

    v4, phase_text, target_sha = _readonly_state(config.database_path)
    if target_sha and target_sha != config.target.sha256:
        reasons.append("TRANSITION_TARGET_CONFLICT")
    if not v4 and config.requested_phase is not TransitionPhase.PREPARED:
        reasons.append("TRANSITION_PHASE_ORDER_INVALID")
    if phase_text is not None:
        current = TransitionPhase(phase_text)
        phases = tuple(TransitionPhase)
        allowed = {current}
        index = phases.index(current)
        if index + 1 < len(phases):
            allowed.add(phases[index + 1])
        if config.requested_phase not in allowed:
            reasons.append("TRANSITION_PHASE_ORDER_INVALID")
    unique = tuple(dict.fromkeys(reasons))
    return MaintenanceResult(
        status="BLOCK" if unique else "PASS",
        reason_codes=unique,
        phase=None if phase_text is None else TransitionPhase(phase_text),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _create_backup(config: MaintenanceConfig) -> str:
    config.backup_directory.mkdir(parents=True, exist_ok=True)
    sources: list[Path] = []
    for path in (
        config.database_path,
        Path(str(config.database_path) + "-wal"),
        Path(str(config.database_path) + "-shm"),
        *config.authority_file_paths,
    ):
        if path in config.authority_file_paths and not path.is_file():
            raise FileNotFoundError(path)
        if path.is_file():
            sources.append(path)
    if config.database_path not in sources:
        raise FileNotFoundError(config.database_path)
    files: list[dict[str, str]] = []
    for index, source in enumerate(sources):
        destination = config.backup_directory / f"{index:02d}-{source.name}"
        shutil.copy2(source, destination)
        files.append(
            {
                "source": str(source.resolve()),
                "backup": str(destination.resolve()),
                "sha256": _sha256_file(destination),
            }
        )
    manifest = {
        "schema": "MULTI_UNIVERSE_MAINTENANCE_BACKUP_V1",
        "database_path": str(config.database_path.resolve()),
        "files": files,
    }
    manifest_path = config.backup_directory / "backup_manifest.json"
    manifest_path.write_bytes(canonical_bytes(manifest))
    return sha256_json(manifest)


def _block(reason: str) -> MaintenanceResult:
    return MaintenanceResult(status="BLOCK", reason_codes=(reason,))


def apply_next_phase(
    config: MaintenanceConfig, evidence: MaintenanceEvidence
) -> MaintenanceResult:
    validation = validate_maintenance(config, evidence)
    if validation.status != "PASS":
        return validation
    v4, phase_text, _target_sha = _readonly_state(config.database_path)
    backup_sha: str | None = None
    if not v4:
        try:
            backup_sha = _create_backup(config)
        except Exception:
            return _block("MAINTENANCE_BACKUP_FAILED")
    try:
        with Database.open(config.database_path) as db:
            if not v4:
                install_multi_universe_schema_v4(db)
            coordinator = MultiUniverseTransitionCoordinator(db)
            if phase_text is None:
                transition = coordinator.prepare(config.target)
            elif config.requested_phase is TransitionPhase.PREPARED:
                transition = coordinator.prepare(config.target)
            else:
                recovered = coordinator.recover(config.target)
                if config.requested_phase is TransitionPhase.SUPERVISION_BOUND:
                    raw_plan = evidence.phase_evidence.get("supervision_binding_plan")
                    snapshot = evidence.phase_evidence.get("fresh_broker_snapshot")
                    if not isinstance(raw_plan, Mapping) or not isinstance(snapshot, Mapping):
                        return _block("SUPERVISION_BINDING_EVIDENCE_REQUIRED")
                    plan = SupervisionBindingPlan.model_validate(raw_plan)
                    receipt = SuccessorSupervisionBinder(db).bind(plan, snapshot)
                    transition = coordinator.recover(config.target)
                    if transition.phase_event_sha256 != receipt.transition_event_sha256:
                        return _block("SUPERVISION_BINDING_AMBIGUOUS")
                else:
                    transition = coordinator.advance(
                        config.requested_phase, evidence.phase_evidence
                    )
    except MultiUniverseTransitionError as exc:
        return _block(str(exc))
    except Exception as exc:
        return _block(f"MAINTENANCE_APPLY_FAILED:{type(exc).__name__}")
    changed = not transition.idempotent
    return MaintenanceResult(
        status="PASS",
        reason_codes=(),
        phase=transition.phase,
        phase_event_sha256=transition.phase_event_sha256,
        mutation_performed=changed or backup_sha is not None,
        idempotent=transition.idempotent,
        backup_manifest_sha256=backup_sha,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("validate", "apply"), required=True)
    parser.add_argument("--phase", choices=[item.value for item in TransitionPhase], required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    config_raw = json.loads(args.config.read_text(encoding="utf-8"))
    config_raw["requested_phase"] = args.phase
    config = MaintenanceConfig.model_validate(config_raw)
    evidence = MaintenanceEvidence.model_validate_json(
        args.evidence.read_text(encoding="utf-8")
    )
    result = (
        validate_maintenance(config, evidence)
        if args.mode == "validate"
        else apply_next_phase(config, evidence)
    )
    print(result.model_dump_json())
    return 0 if result.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
