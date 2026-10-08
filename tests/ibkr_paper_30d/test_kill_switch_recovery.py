from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.experiment_control import (
    ExperimentClockStore,
    ExperimentControlError,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
from ibkr_paper_30d.kill_switch_recovery import recover_kill_switch
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_clock import BrokerTimeObservation
from ibkr_paper_30d.successor_epoch import (
    BrokerTransitionEvidence,
    commit_successor_transition,
)
from successor_test_support import (
    ACCOUNT_HASH as SUCCESSOR_ACCOUNT_HASH,
    OWNER_SID as SUCCESSOR_OWNER_SID,
    SUCCESSOR_START,
    build_authorized_successor,
)


NOW = datetime(2026, 10, 8, 19, 0, tzinfo=timezone.utc)
OWNER_SID = "S-1-5-21-owner"
ACCOUNT_HASH = "a" * 64
APPROVED_HEAD = "b" * 40
AUTHORIZATION_EVENT_ID = "authorization-1"
CLOCK_HASH = "c" * 64


def _trigger(store: KillSwitchStore) -> tuple[str, str]:
    store.set("KILL_SWITCH_CLEAR", reason="initial owner authorization", actor=OWNER_SID)
    event_id = store.set(
        "KILL_SWITCH_TRIGGERED",
        reason="watchdog failure",
        actor="CONTINUITY_V3_RUNTIME",
    )
    row = store.db.execute(
        "SELECT payload_sha256 FROM kill_switch_events WHERE event_id=?",
        (event_id,),
    ).fetchone()
    return event_id, str(row[0])


def _receipt(trigger_event_id: str, trigger_payload_sha256: str, **updates):
    payload = {
        "schema": "KILL_SWITCH_RECOVERY_RECEIPT_V1",
        "trigger_event_id": trigger_event_id,
        "trigger_payload_sha256": trigger_payload_sha256,
        "approved_head": APPROVED_HEAD,
        "owner_sid": OWNER_SID,
        "account_identity_sha256": ACCOUNT_HASH,
        "authorization_event_id": AUTHORIZATION_EVENT_ID,
        "clock_event_sha256": CLOCK_HASH,
        "broker_evidence_sha256": "d" * 64,
        "broker_server_time_utc": NOW.isoformat().replace("+00:00", "Z"),
        "collected_at_utc": NOW.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (NOW + timedelta(seconds=30)).isoformat().replace(
            "+00:00", "Z"
        ),
        "positions_count": 1,
        "open_orders_count": 0,
        "executions_count": 1,
        "broker_write_count": 0,
        "query_completeness": {
            "managed_accounts": True,
            "positions": True,
            "open_orders": True,
            "executions": True,
            "current_time": True,
        },
        "recovery_reason_code": "CONTINUITY_WATCHDOG_PACING_DEFECT_REMEDIATED",
    }
    payload.update(updates)
    return payload


def _validate(store: KillSwitchStore) -> str:
    return store.validate_history(
        expected_owner_sid=OWNER_SID,
        expected_account_identity_sha256=ACCOUNT_HASH,
        expected_approved_head=APPROVED_HEAD,
        expected_authorization_event_id=AUTHORIZATION_EVENT_ID,
        expected_clock_event_sha256=CLOCK_HASH,
    )


def test_verified_recovery_preserves_trigger_and_restores_clear_state(tmp_path) -> None:
    with Database.open(tmp_path / "recovery.sqlite3") as db:
        store = KillSwitchStore(db)
        trigger_id, trigger_sha = _trigger(store)
        receipt = _receipt(trigger_id, trigger_sha)

        recovery_event_id = store.recover(
            receipt,
            now_utc=NOW + timedelta(seconds=1),
            expected_owner_sid=OWNER_SID,
            expected_account_identity_sha256=ACCOUNT_HASH,
            expected_approved_head=APPROVED_HEAD,
            expected_authorization_event_id=AUTHORIZATION_EVENT_ID,
            expected_clock_event_sha256=CLOCK_HASH,
        )

        rows = db.execute(
            "SELECT event_id,state,payload_json,payload_sha256 "
            "FROM kill_switch_events ORDER BY sequence"
        ).fetchall()
        assert [str(row[1]) for row in rows] == [
            "KILL_SWITCH_CLEAR",
            "KILL_SWITCH_TRIGGERED",
            "KILL_SWITCH_CLEAR",
        ]
        assert str(rows[-1][0]) == recovery_event_id
        assert _validate(store) == "KILL_SWITCH_CLEAR"


def test_generic_clear_cannot_bypass_triggered_history(tmp_path) -> None:
    with Database.open(tmp_path / "generic-clear.sqlite3") as db:
        store = KillSwitchStore(db)
        _trigger(store)

        with pytest.raises(ExperimentControlError, match="RECOVERY_RECEIPT_REQUIRED"):
            store.set("KILL_SWITCH_CLEAR", reason="manual clear", actor=OWNER_SID)


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"approved_head": "e" * 40}, "KILL_SWITCH_RECOVERY_HEAD_MISMATCH"),
        ({"owner_sid": "S-1-5-21-other"}, "KILL_SWITCH_RECOVERY_OWNER_MISMATCH"),
        ({"account_identity_sha256": "f" * 64}, "KILL_SWITCH_RECOVERY_ACCOUNT_MISMATCH"),
        ({"open_orders_count": 1}, "KILL_SWITCH_RECOVERY_OPEN_ORDERS_PRESENT"),
        ({"broker_write_count": 1}, "KILL_SWITCH_RECOVERY_BROKER_WRITE_DETECTED"),
        (
            {
                "broker_server_time_utc": (NOW - timedelta(seconds=10)).isoformat().replace("+00:00", "Z"),
                "collected_at_utc": (NOW - timedelta(seconds=10)).isoformat().replace("+00:00", "Z"),
                "expires_at_utc": (NOW - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
            },
            "KILL_SWITCH_RECOVERY_EVIDENCE_STALE",
        ),
    ],
)
def test_recovery_rejects_untrusted_or_unsafe_evidence(tmp_path, updates, reason) -> None:
    with Database.open(tmp_path / "unsafe.sqlite3") as db:
        store = KillSwitchStore(db)
        trigger_id, trigger_sha = _trigger(store)

        with pytest.raises(ExperimentControlError, match=reason):
            store.recover(
                _receipt(trigger_id, trigger_sha, **updates),
                now_utc=NOW,
                expected_owner_sid=OWNER_SID,
                expected_account_identity_sha256=ACCOUNT_HASH,
                expected_approved_head=APPROVED_HEAD,
                expected_authorization_event_id=AUTHORIZATION_EVENT_ID,
                expected_clock_event_sha256=CLOCK_HASH,
            )


def test_history_validation_detects_recovery_receipt_tampering(tmp_path) -> None:
    with Database.open(tmp_path / "tamper.sqlite3") as db:
        store = KillSwitchStore(db)
        trigger_id, trigger_sha = _trigger(store)
        store.recover(
            _receipt(trigger_id, trigger_sha),
            now_utc=NOW,
            expected_owner_sid=OWNER_SID,
            expected_account_identity_sha256=ACCOUNT_HASH,
            expected_approved_head=APPROVED_HEAD,
            expected_authorization_event_id=AUTHORIZATION_EVENT_ID,
            expected_clock_event_sha256=CLOCK_HASH,
        )
        row = db.execute(
            "SELECT sequence,payload_json FROM kill_switch_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        tampered = str(row[1]).replace(APPROVED_HEAD, "e" * 40)
        trigger_names = [
            str(item[0])
            for item in db.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "AND tbl_name='kill_switch_events'"
            ).fetchall()
        ]
        for name in trigger_names:
            db.execute(f'DROP TRIGGER "{name}"')
        db.execute(
            "UPDATE kill_switch_events SET payload_json=? WHERE sequence=?",
            (tampered, int(row[0])),
        )

        with pytest.raises(ExperimentControlError, match="KILL_SWITCH_EVENT_HASH_MISMATCH"):
            _validate(store)


def test_recovery_event_hash_binds_the_exact_receipt(tmp_path) -> None:
    with Database.open(tmp_path / "binding.sqlite3") as db:
        store = KillSwitchStore(db)
        trigger_id, trigger_sha = _trigger(store)
        receipt = _receipt(trigger_id, trigger_sha)
        store.recover(
            receipt,
            now_utc=NOW,
            expected_owner_sid=OWNER_SID,
            expected_account_identity_sha256=ACCOUNT_HASH,
            expected_approved_head=APPROVED_HEAD,
            expected_authorization_event_id=AUTHORIZATION_EVENT_ID,
            expected_clock_event_sha256=CLOCK_HASH,
        )
        payload_json, payload_sha = db.execute(
            "SELECT payload_json,payload_sha256 FROM kill_switch_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()

        import json

        payload = json.loads(str(payload_json))
        assert payload["recovery_receipt_sha256"] == sha256_json(receipt)
        assert str(payload_sha) == sha256_json(payload)


def test_recovery_command_collects_readonly_paper_evidence_before_db_clear(
    tmp_path,
) -> None:
    repo = tmp_path / "repo"
    db_path = repo / "state" / "ibkr_paper_30d" / "autonomous.sqlite3"
    expected_path = repo / "Secrets" / "expected_paper_account_identity_v1.json"
    report_path = (
        repo / "state" / "ibkr_paper_30d" / "reports" / "kill_switch_recovery_v1.json"
    )
    expected_path.parent.mkdir(parents=True)
    account_hash = expected_identity_hash("DU123456")
    expected_path.write_text(
        '{"schema":"EXPECTED_PAPER_ACCOUNT_IDENTITY_V1","account_sha256":"'
        + account_hash
        + '"}',
        encoding="utf-8",
    )
    with Database.open(db_path) as db:
        clock = ExperimentClockStore(db).initialize_or_load(
            requested_start_utc=NOW - timedelta(days=1),
            duration_days=30,
            initial_allocation=Decimal("500"),
        )
        authorization_event_id = OwnerAuthorizationStore(db).set(
            "AUTHORIZED",
            clock_event_sha256=clock.event_sha256,
            reason="test",
            actor=OWNER_SID,
        )
        switch = KillSwitchStore(db)
        switch.set("KILL_SWITCH_CLEAR", reason="initial", actor=OWNER_SID)
        switch.set(
            "KILL_SWITCH_TRIGGERED",
            reason="watchdog failure",
            actor="CONTINUITY_V3_RUNTIME",
        )
    evidence = SimpleNamespace(
        connected=True,
        authenticated=True,
        managed_accounts=("DU123456",),
        positions=({"account": "DU123456", "symbol": "HAE", "position": "4"},),
        open_orders=(),
        executions=({"account": "DU123456", "execId": "exec-1"},),
        server_timestamp_utc=NOW.isoformat().replace("+00:00", "Z"),
        heartbeat_ok=True,
        query_completeness={
            "managed_accounts": True,
            "positions": True,
            "open_orders": True,
            "executions": True,
            "current_time": True,
        },
        outbound_message_ids=(71, 6, 62),
        errors=(),
    )

    result = recover_kill_switch(
        repo_root=repo,
        approved_head=APPROVED_HEAD,
        recovery_reason_code="CONTINUITY_WATCHDOG_PACING_DEFECT_REMEDIATED",
        evidence_collector=lambda **_: evidence,
        head_reader=lambda _: APPROVED_HEAD,
        current_sid=lambda: OWNER_SID,
        token_elevated=lambda: True,
        now_utc=lambda: NOW + timedelta(seconds=1),
    )

    assert result["status"] == "PASS"
    assert result["receipt"]["authorization_event_id"] == authorization_event_id
    assert result["receipt"]["account_identity_sha256"] == account_hash
    assert result["receipt"]["positions_count"] == 1
    assert result["receipt"]["open_orders_count"] == 0
    assert result["receipt"]["broker_write_count"] == 0
    assert report_path.is_file()
    with Database.open(db_path) as db:
        assert KillSwitchStore(db).current() == "KILL_SWITCH_CLEAR"


def test_recovery_command_binds_active_successor_authority(tmp_path) -> None:
    repo = tmp_path / "repo"
    db_path = repo / "state" / "ibkr_paper_30d" / "autonomous.sqlite3"
    successor_receipt_path = repo / "owner-successor.json"
    expected_path = repo / "Secrets" / "expected_paper_account_identity_v1.json"
    expected_path.parent.mkdir(parents=True)
    account = "DU123456"
    account_hash = expected_identity_hash(account)
    expected_path.write_text(
        '{"schema":"EXPECTED_PAPER_ACCOUNT_IDENTITY_V1","account_sha256":"'
        + account_hash
        + '"}',
        encoding="utf-8",
    )
    definition, successor_receipt = build_authorized_successor(
        db_path, successor_receipt_path
    )
    collected_at = SUCCESSOR_START + timedelta(seconds=1)
    with Database.open(db_path) as db:
        transition = commit_successor_transition(
            db=db,
            launch_attempt_id="launch-successor-recovery",
            target_successor_epoch_id=str(definition["epoch_id"]),
            target_successor_definition_sha256=str(definition["definition_sha256"]),
            expected_account_identity_sha256=SUCCESSOR_ACCOUNT_HASH,
            expected_owner_sid=SUCCESSOR_OWNER_SID,
            owner_authorization_receipt=successor_receipt,
            execution_lock_verifier=lambda: True,
            broker_evidence_collector=lambda: BrokerTransitionEvidence(
                account_identity_sha256=SUCCESSOR_ACCOUNT_HASH,
                collected_at_utc=collected_at,
                observation=BrokerTimeObservation(
                    server_time_utc=SUCCESSOR_START,
                    observed_at_utc=collected_at,
                    authenticated=True,
                    paper_session=True,
                ),
                positions_count=0,
                open_orders_count=0,
                broker_write_count=0,
            ),
            now_utc=lambda: SUCCESSOR_START + timedelta(seconds=2),
        )
        switch = KillSwitchStore(db)
        switch.set("KILL_SWITCH_CLEAR", reason="initial", actor=SUCCESSOR_OWNER_SID)
        switch.set(
            "KILL_SWITCH_TRIGGERED",
            reason="watchdog failure",
            actor="CONTINUITY_V3_RUNTIME",
        )
    recovery_time = NOW + timedelta(seconds=1)
    evidence = SimpleNamespace(
        connected=True,
        authenticated=True,
        managed_accounts=(account,),
        positions=({"account": account, "symbol": "HAE", "position": "4"},),
        open_orders=(),
        executions=({"account": account, "execId": "exec-1"},),
        server_timestamp_utc=recovery_time.isoformat().replace("+00:00", "Z"),
        heartbeat_ok=True,
        query_completeness={
            "managed_accounts": True,
            "positions": True,
            "open_orders": True,
            "executions": True,
            "current_time": True,
        },
        outbound_message_ids=(71, 6, 62),
        errors=(),
    )

    result = recover_kill_switch(
        repo_root=repo,
        approved_head=APPROVED_HEAD,
        recovery_reason_code="CONTINUITY_WATCHDOG_PACING_DEFECT_REMEDIATED",
        evidence_collector=lambda **_: evidence,
        head_reader=lambda _: APPROVED_HEAD,
        current_sid=lambda: SUCCESSOR_OWNER_SID,
        token_elevated=lambda: True,
        now_utc=lambda: recovery_time,
    )

    assert result["status"] == "PASS"
    assert (
        result["receipt"]["authorization_event_id"]
        == successor_receipt["authorization_event_id"]
    )
    assert result["receipt"]["clock_event_sha256"] == transition.clock_event_sha256


def test_recovery_blocks_if_authorization_changes_before_commit(tmp_path) -> None:
    with Database.open(tmp_path / "authority-race.sqlite3") as db:
        clock = ExperimentClockStore(db).initialize_or_load(
            requested_start_utc=NOW - timedelta(days=1),
            duration_days=30,
            initial_allocation=Decimal("500"),
        )
        authorization = OwnerAuthorizationStore(db)
        original_event_id = authorization.set(
            "AUTHORIZED",
            clock_event_sha256=clock.event_sha256,
            reason="initial",
            actor=OWNER_SID,
        )
        switch = KillSwitchStore(db)
        trigger_id, trigger_sha = _trigger(switch)
        receipt = _receipt(
            trigger_id,
            trigger_sha,
            authorization_event_id=original_event_id,
            clock_event_sha256=clock.event_sha256,
        )
        authorization.set(
            "REVOKED",
            clock_event_sha256=clock.event_sha256,
            reason="concurrent owner change",
            actor=OWNER_SID,
        )

        with pytest.raises(
            ExperimentControlError,
            match="KILL_SWITCH_RECOVERY_AUTHORIZATION_CHANGED",
        ):
            switch.recover(
                receipt,
                now_utc=NOW,
                expected_owner_sid=OWNER_SID,
                expected_account_identity_sha256=ACCOUNT_HASH,
                expected_approved_head=APPROVED_HEAD,
                expected_authorization_event_id=original_event_id,
                expected_clock_event_sha256=clock.event_sha256,
            )
