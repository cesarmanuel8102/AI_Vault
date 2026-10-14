"""One-off, Owner-authorized recovery through the existing PAPER writer."""

import argparse
import json
import os
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .canary_execution import CanaryRecoveryRequest
from .canonical import sha256_json
from .persistence import Database


class CanaryRecoveryStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)

    def authorize(self, original, *, entry_execution_id_sha256,
                  owner_decision_sha256, approved_head, now):
        from .production_continuity_runtime import _ProductionCanaryStore
        store = _ProductionCanaryStore(self.db_path)
        stored = store.load_request(original.candidate_sha256)
        if stored is None or stored.sha256 != original.sha256 or not store.execution_claimed(original.execution_key):
            raise ValueError("CANARY_ORIGINAL_CLAIM_REQUIRED")
        with Database.open(self.db_path) as db, db.transaction():
            events = store._verified_events(db)
            existing = next((e for e in events if e.get("event_type") == "OWNER_CANARY_RECOVERY_AUTHORIZED"
                             and e.get("original_request_sha256") == original.sha256
                             and e.get("owner_decision_sha256") == owner_decision_sha256), None)
            if existing is not None:
                if (existing.get("owner_decision_sha256") != owner_decision_sha256
                        or existing.get("approved_head") != approved_head):
                    raise ValueError("CANARY_RECOVERY_AUTHORIZATION_CONFLICT")
                return CanaryRecoveryRequest.model_validate(existing["request"])
            body = {"original_request_sha256": original.sha256,
                    "original_authorization_sha256": original.authorization_sha256,
                    "owner_decision_sha256": owner_decision_sha256,
                    "entry_execution_id_sha256": entry_execution_id_sha256,
                    "approved_head": approved_head, "maximum_order_count": 1,
                    "action": original.flat_return_plan.action,
                    "quantity": str(original.quantity), "issued_at_utc": now.isoformat(),
                    "expires_at_utc": (now + timedelta(minutes=30)).isoformat()}
            owner_hash = sha256_json(body)
            request = CanaryRecoveryRequest(
                original_request=original, durable_sequence=original.durable_sequence + 1,
                execution_key=f"canary-recovery:{original.sha256}:{owner_hash}",
                owner_authorization_sha256=owner_hash,
                entry_execution_id_sha256=entry_execution_id_sha256,
                created_at_utc=now, expires_at_utc=now + timedelta(minutes=30))
            store._append_in_transaction(db, authorization_id=request.execution_key,
                event_type="OWNER_CANARY_RECOVERY_AUTHORIZED", body={**body,
                    "candidate_sha256": original.candidate_sha256,
                    "owner_authorization_sha256": owner_hash,
                    "request_sha256": request.sha256, "request": request.model_dump(mode="json")})
        return request

    def claim(self, request, facts):
        from .production_continuity_runtime import _ProductionCanaryStore
        original = request.original_request
        expected = {"request_sha256": request.sha256,
                    "original_request_sha256": original.sha256,
                    "entry_execution_id_sha256": request.entry_execution_id_sha256,
                    "account_identity_sha256": original.account_identity_sha256,
                    "contract_identity_sha256": original.canonical_contract.sha256,
                    "position_quantity": str(original.quantity if original.entry_terms.action == "BUY" else -original.quantity)}
        if any(facts.get(key) != value for key, value in expected.items()):
            return False
        store = _ProductionCanaryStore(self.db_path)
        store.reserve_recovery_ownership(original)
        with Database.open(self.db_path) as db, db.transaction():
            events = store._verified_events(db)
            authority = next((e for e in events if e.get("event_type") == "OWNER_CANARY_RECOVERY_AUTHORIZED"
                              and e.get("request_sha256") == request.sha256), None)
            if (authority is None or authority.get("owner_authorization_sha256") != request.owner_authorization_sha256
                    or not request.created_at_utc <= datetime.now(timezone.utc) < request.expires_at_utc):
                return False
            if any(e.get("event_type") == "CANARY_RECOVERY_CLAIMED"
                   and e.get("request_sha256") == request.sha256 for e in events):
                return False
            store._append_in_transaction(db, authorization_id=request.execution_key,
                event_type="CANARY_RECOVERY_CLAIMED", body={
                    "candidate_sha256": original.candidate_sha256,
                    "original_request_sha256": original.sha256,
                    "request_sha256": request.sha256, "facts": facts,
                    "facts_sha256": sha256_json(facts)})
        return True

    def persist_result(self, request, result):
        from .production_continuity_runtime import _ProductionCanaryStore
        with Database.open(self.db_path) as db, db.transaction():
            store = _ProductionCanaryStore(self.db_path)
            store._verified_events(db)
            store._append_in_transaction(db, authorization_id=request.execution_key,
                event_type="CANARY_RECOVERY_RESULT", body={
                    "candidate_sha256": request.original_request.candidate_sha256,
                    "original_request_sha256": request.original_request.sha256,
                    "request_sha256": request.sha256,
                    "result": asdict(result) if is_dataclass(result) else result.model_dump(mode="json")})


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--approved-head", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--expected-original-request-sha256", required=True)
    parser.add_argument("--entry-execution-id-sha256", required=True)
    parser.add_argument("--owner-decision-sha256", required=True)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != args.approved_head or Path(__file__).resolve().parents[1] != root:
        raise ValueError("CANARY_RECOVERY_APPROVED_HEAD_MISMATCH")
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("CANARY_RECOVERY_TRACKED_TREE_DIRTY")
    from .kernel_manifest import verify_kernel_manifest
    manifest = json.loads((root / "IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json").read_text())
    if verify_kernel_manifest(root, manifest).get("verified") is not True:
        raise ValueError("CANARY_RECOVERY_KERNEL_MISMATCH")
    from .authoritative_broker_writer import AuthoritativeBrokerWriter
    from .broker_write_coordinator import BrokerWriteCoordinator
    from .canary_broker_accounting import CanaryBrokerAccounting
    from .execution_lock import ExecutionLock, LockOwner, WindowsProcessObserver
    from .production_continuity_runtime import _ProductionCanaryStore, build_ibkr_session_factory
    db_path = root / "state/ibkr_paper_30d/autonomous.sqlite3"
    store = _ProductionCanaryStore(db_path)
    original = store.load_request(args.candidate_sha256)
    if original is None or original.sha256 != args.expected_original_request_sha256:
        raise ValueError("CANARY_ORIGINAL_REQUEST_MISMATCH")
    recovery = CanaryRecoveryStore(db_path)
    with Database.open(db_path) as db:
        observer = WindowsProcessObserver()
        process = observer.observe(os.getpid())
        if process is None:
            raise ValueError("CANARY_RECOVERY_PROCESS_IDENTITY_REQUIRED")
        lock = ExecutionLock(db)
        receipt = lock.acquire(LockOwner(owner_id=f"canary-recovery:{original.sha256}", **process.model_dump()))
        if not receipt.acquired:
            raise ValueError(f"CANARY_RECOVERY_LOCK_BLOCK:{receipt.reason}")
        writer = None
        try:
            backup = root / "state/ibkr_paper_30d" / f"autonomous-pre-canary-flat-recovery-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
            import sqlite3
            with sqlite3.connect(backup) as target:
                db.connection.backup(target)
            request = recovery.authorize(original,
                entry_execution_id_sha256=args.entry_execution_id_sha256,
                owner_decision_sha256=args.owner_decision_sha256,
                approved_head=head, now=datetime.now(timezone.utc))
            coordinator = BrokerWriteCoordinator()
            factory = build_ibkr_session_factory(host="127.0.0.1", port=4002,
                expected_account_hash=original.account_identity_sha256,
                client_id=19761, read_only=False)
            writer = AuthoritativeBrokerWriter(coordinator,
                broker_factory=lambda client_id: factory() if client_id == 19761 else None,
                execution_client_id=19761, execution_lock_verifier=lambda: receipt.acquired,
                authority_validator=lambda *_args: ("NEW_ENTRY_FORBIDDEN",),
                canary_recovery_claim=recovery.claim,
                canary_recovery_result_persister=recovery.persist_result,
                canary_broker_accounting=CanaryBrokerAccounting(db_path),
                broker_request_timeout_seconds=60)
            writer.start()
            if not writer.wait_until_ready(15):
                raise ValueError("CANARY_RECOVERY_WRITER_NOT_READY")
            result = coordinator.submit(request).result(timeout=75)
            print(json.dumps({"status": result.status, "success": result.success,
                "reason_codes": result.reason_codes, "order": result.order,
                "broker_validation": result.broker_validation,
                "request_sha256": request.sha256, "backup": str(backup)}))
            return 0 if result.success else 1
        finally:
            if writer is not None and not writer.stop(75):
                raise ValueError("CANARY_RECOVERY_WRITER_STILL_ACTIVE")
            lock.release(receipt)


if __name__ == "__main__":
    raise SystemExit(main())
