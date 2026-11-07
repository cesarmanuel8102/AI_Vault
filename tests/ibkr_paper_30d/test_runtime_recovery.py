"""Fault-injection tests for reason-scoped recovery, the runtime supervisor and receipt renewal."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.alerts import AlertRepository, CriticalAlert
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.experiment_control import (
    ExperimentClockStore,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_ledger import CurrencyBalance, RegularCarryForward, SleeveLedgerStore
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from ibkr_paper_30d import runtime_supervisor as rs

NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER_SID = "S-1-5-21-owner"
HEAD = "e" * 40
CORRELATION = "continuity-v3-" + "1" * 32
ACCOUNT = "DU123456"


class Alerts(list):
    def __call__(self, event_type: str, payload: dict) -> None:
        self.append((event_type, payload))


def _lock(db, *, pid=111, state="ACTIVE", heartbeat=NOW - timedelta(minutes=30)):
    payload = {"pid": pid, "state": state, "generation": 7, "order_authority": False,
               "heartbeat_at_utc": heartbeat.isoformat().replace("+00:00", "Z")}
    db.execute(
        "INSERT OR REPLACE INTO experiment_state(experiment_id,version,payload_json,payload_sha256,updated_at_utc)"
        " VALUES(?,?,?,?,?)",
        ("EXECUTION_LOCK_V1", 1, canonical_bytes(payload).decode(), sha256_json(payload), NOW.isoformat()),
    )


def _repo(tmp_path, *, actor="CONTINUITY_V3_RUNTIME", runtime_reason="CONTINUITY_WATCHDOG_FAILED",
          triggered=True, trigger_age=timedelta(minutes=30), approved_head=HEAD):
    repo = tmp_path / "repo"
    identity = repo / "Secrets" / "expected_paper_account_identity_v1.json"
    identity.parent.mkdir(parents=True)
    identity.write_text(json.dumps({"schema": "EXPECTED_PAPER_ACCOUNT_IDENTITY_V1",
                                    "account_sha256": expected_identity_hash(ACCOUNT)}), encoding="utf-8")
    db_path = repo / "state" / "ibkr_paper_30d" / "autonomous.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        ledger = SleeveLedgerStore(db)
        ledger.bootstrap_regular(RegularCarryForward(
            allocation_usd=Decimal("500.00"),
            currency_balances=(CurrencyBalance(currency="USD", amount=Decimal("500.00")),),
            positions=(), open_order_count=0, fill_count=0, fees_usd=Decimal("0"),
            realized_pnl_usd=Decimal("0"), unrealized_pnl_usd=Decimal("0"),
            historical_event_sha256=(), source_ledger_sha256="a" * 64,
        ))
        ledger.bootstrap_extended()
        ledger.reconcile_broker_snapshot({"positions": [], "open_orders": [], "executions": []},
                                         {"active_contracts": []})
        clock = ExperimentClockStore(db).initialize_or_load(
            requested_start_utc=NOW - timedelta(days=10), duration_days=30,
            initial_allocation=Decimal("500"),
        )
        OwnerAuthorizationStore(db).set("AUTHORIZED", clock_event_sha256=clock.event_sha256,
                                        reason="test", actor=OWNER_SID)
        switch = KillSwitchStore(db)
        switch.set("KILL_SWITCH_CLEAR", reason="initial", actor=OWNER_SID)
        if triggered:
            reason = (f"critical runtime event {CORRELATION}" if actor == "CONTINUITY_V3_RUNTIME"
                      else "owner stop")
            at = (NOW - trigger_age).isoformat().replace("+00:00", "Z")
            trigger = {"schema": "KILL_SWITCH_EVENT_V1", "state": "KILL_SWITCH_TRIGGERED",
                       "reason": reason, "actor": actor, "created_at_utc": at}
            db.execute(
                "INSERT INTO kill_switch_events(event_id,state,payload_json,payload_sha256,created_at_utc)"
                " VALUES(?,?,?,?,?)",
                ("trigger-1", "KILL_SWITCH_TRIGGERED", canonical_bytes(trigger).decode(),
                 sha256_json(trigger), at),
            )
            if runtime_reason is not None:
                AlertRepository(db).persist(CriticalAlert(
                    alert_id=f"alert-{CORRELATION}", event_type=runtime_reason, correlation_id=CORRELATION,
                    occurred_at_utc=NOW - trigger_age, detail=f"runtime_reason_code={runtime_reason}",
                    owner_action_required=True,
                ))
        payload = {"approved_git_head": approved_head, "schema": "MULTI_UNIVERSE_RUNTIME_RELEASE_V1"}
        db.execute(
            "INSERT INTO successor_transition_events(event_id,transition_id,phase,event_type,payload_json,payload_sha256,previous_event_sha256,event_sha256,created_at_utc)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            ("release-1", "t", "ACTIVE", "RUNTIME_RELEASE_AUTHORIZED", canonical_bytes(payload).decode(),
             sha256_json(payload), None, "f" * 64, NOW.isoformat()),
        )
        _lock(db)
    return repo, db_path


def _evidence(positions=(), open_orders=()):
    return SimpleNamespace(
        connected=True, authenticated=True, heartbeat_ok=True, managed_accounts=(ACCOUNT,),
        positions=positions, open_orders=open_orders, executions=(),
        server_timestamp_utc=(NOW + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        query_completeness={k: True for k in ("managed_accounts", "positions", "open_orders", "executions", "current_time")},
        outbound_message_ids=(71, 6, 62), errors=(),
    )


def _recover(repo, alerts, *, evidence=None, pid_alive=lambda pid: False, head=HEAD,
             auditor=lambda: {"gate_status": "PASS"}):
    return rs.automatic_kill_switch_recovery(
        repo_root=repo,
        now_utc=lambda: NOW + timedelta(seconds=1),
        pid_alive=pid_alive,
        auditor_gate=auditor,
        head_reader=lambda _: head,
        evidence_collector=lambda **_: evidence or _evidence(),
        current_sid=lambda: OWNER_SID,
        token_elevated=lambda: True,
        alert_sink=alerts,
    )


def _state(db_path):
    with Database.open(db_path) as db:
        return KillSwitchStore(db).current()


# --- reason-scoped recovery --------------------------------------------------------------

def test_dead_process_flat_account_transient_watchdog_failure_recovers_once(tmp_path):
    repo, db_path = _repo(tmp_path)
    alerts = Alerts()

    first = _recover(repo, alerts)
    second = _recover(repo, alerts)

    assert first["status"] == "RECOVERED", first
    assert _state(db_path) == "KILL_SWITCH_CLEAR"
    assert second["status"] == "NOT_REQUIRED"
    assert [a for a, _ in alerts].count("AUTOMATIC_RUNTIME_RECOVERY_PERFORMED") == 1
    with Database.open(db_path) as db:
        events = db.execute("SELECT COUNT(*) FROM state_events WHERE event_type='AUTOMATIC_KILL_SWITCH_RECOVERY'").fetchone()[0]
    assert events == 1


def test_owner_kill_is_never_recovered_automatically(tmp_path):
    repo, db_path = _repo(tmp_path, actor=OWNER_SID, runtime_reason=None)
    alerts = Alerts()

    result = _recover(repo, alerts)

    assert result["status"] == "BLOCKED"
    assert "KILL_SWITCH_NOT_RUNTIME_SCOPED" in result["reason_codes"]
    assert _state(db_path) == "KILL_SWITCH_TRIGGERED"


def test_unknown_runtime_reason_is_not_recovered(tmp_path):
    repo, db_path = _repo(tmp_path, runtime_reason="BROKER_STATE_UNCERTAIN")

    result = _recover(repo, Alerts())

    assert result["status"] == "BLOCKED"
    assert "RUNTIME_REASON_NOT_RECOVERABLE" in result["reason_codes"]
    assert _state(db_path) == "KILL_SWITCH_TRIGGERED"


@pytest.mark.parametrize("evidence", [
    _evidence(positions=({"account": ACCOUNT, "symbol": "SOL", "position": "4"},)),
    _evidence(open_orders=({"account": ACCOUNT, "orderRef": "codex-ibkr-paper-30d-a-x"},)),
])
def test_open_position_or_order_blocks_recovery(tmp_path, evidence):
    repo, db_path = _repo(tmp_path)

    result = _recover(repo, Alerts(), evidence=evidence)

    assert result["status"] == "BLOCKED"
    assert _state(db_path) == "KILL_SWITCH_TRIGGERED"


def test_uncertain_state_after_trigger_blocks_recovery(tmp_path):
    repo, db_path = _repo(tmp_path)
    with Database.open(db_path) as db:
        db.execute("INSERT INTO alerts(alert_id,event_type,payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?)",
                   ("u1", "BROKER_STATE_UNCERTAIN", "{}", "0" * 64, NOW.isoformat()))

    result = _recover(repo, Alerts())

    assert "UNCERTAIN_STATE_PRESENT" in result["reason_codes"]
    assert _state(db_path) == "KILL_SWITCH_TRIGGERED"


def test_live_writer_blocks_recovery(tmp_path):
    repo, db_path = _repo(tmp_path)

    result = _recover(repo, Alerts(), pid_alive=lambda pid: True)

    assert "WRITER_STILL_ACTIVE" in result["reason_codes"]
    assert _state(db_path) == "KILL_SWITCH_TRIGGERED"


def test_lock_must_be_stale_even_if_pid_is_gone(tmp_path):
    repo, db_path = _repo(tmp_path)
    with Database.open(db_path) as db:
        _lock(db, heartbeat=NOW - timedelta(seconds=20))

    result = _recover(repo, Alerts())

    assert "EXECUTION_LOCK_NOT_STALE" in result["reason_codes"]


def test_cooldown_blocks_immediate_recovery(tmp_path):
    repo, db_path = _repo(tmp_path, trigger_age=timedelta(seconds=30))

    result = _recover(repo, Alerts())

    assert "RECOVERY_COOLDOWN_ACTIVE" in result["reason_codes"]


def test_head_mismatch_blocks_recovery(tmp_path):
    repo, db_path = _repo(tmp_path)

    result = _recover(repo, Alerts(), head="d" * 40)

    assert "APPROVED_HEAD_MISMATCH" in result["reason_codes"]
    assert _state(db_path) == "KILL_SWITCH_TRIGGERED"


def test_invalid_auditor_receipt_blocks_recovery(tmp_path):
    repo, db_path = _repo(tmp_path)

    result = _recover(repo, Alerts(), auditor=lambda: {"gate_status": "BLOCK", "reason_codes": ["RECEIPT_STALE"]})

    assert "AUDITOR_RECEIPT_NOT_PASS" in result["reason_codes"]


def test_recovery_budget_circuit_breaker(tmp_path):
    repo, db_path = _repo(tmp_path)
    with Database.open(db_path) as db:
        for _ in range(rs.MAX_AUTOMATIC_RECOVERIES_PER_DAY):
            rs._append_state_event(db, "AUTOMATIC_KILL_SWITCH_RECOVERY", {"test": True}, now=NOW - timedelta(hours=1))
    alerts = Alerts()

    result = _recover(repo, alerts)

    assert "AUTOMATIC_RECOVERY_BUDGET_EXHAUSTED" in result["reason_codes"]
    assert any(name == "OWNER_ACTION_REQUIRED" for name, _ in alerts)


# --- supervisor --------------------------------------------------------------------------

class Host:
    def __init__(self, *, alive=False, cmdline="python -B -m ibkr_paper_30d.day1_launch --repo-root C:/repo",
                 task_state="Ready"):
        self.alive = alive
        self.cmdline = cmdline
        self.task_state = task_state
        self.started = 0
        self.terminated = []

    def pid_alive(self, pid):
        return self.alive

    def process_cmdline(self, pid):
        return self.cmdline

    def start_task(self):
        self.started += 1

    def terminate(self, pid):
        self.terminated.append(pid)


def _supervise(repo, host, alerts):
    return rs.supervise_runtime(
        repo_root=repo,
        now_utc=lambda: NOW,
        pid_alive=host.pid_alive,
        process_cmdline=host.process_cmdline,
        task_state=lambda: host.task_state,
        start_task=host.start_task,
        terminate_process=host.terminate,
        alert_sink=alerts,
    )


def test_supervisor_relaunches_dead_runtime_through_existing_task(tmp_path):
    repo, _ = _repo(tmp_path, triggered=False)
    host = Host(alive=False)

    result = _supervise(repo, host, Alerts())

    assert result["action"] == "RELAUNCH_REQUESTED"
    assert host.started == 1
    assert host.terminated == []


def test_supervisor_does_not_touch_slow_but_alive_runtime(tmp_path):
    repo, _ = _repo(tmp_path, triggered=False)
    host = Host(alive=True)
    alerts = Alerts()

    result = _supervise(repo, host, alerts)

    assert result["action"] == "SLOW_OR_HUNG_ALERTED"
    assert host.started == 0 and host.terminated == []
    assert alerts and alerts[0][0] == "RUNTIME_HEARTBEAT_STALE"


def test_supervisor_leaves_healthy_runtime_alone(tmp_path):
    repo, db_path = _repo(tmp_path, triggered=False)
    with Database.open(db_path) as db:
        _lock(db, heartbeat=NOW - timedelta(seconds=10))
    host = Host(alive=True)

    result = _supervise(repo, host, Alerts())

    assert result["action"] == "HEALTHY"
    assert host.started == 0 and host.terminated == []


def test_supervisor_never_starts_while_launcher_task_is_running(tmp_path):
    repo, _ = _repo(tmp_path, triggered=False)
    host = Host(alive=False, task_state="Running")

    result = _supervise(repo, host, Alerts())

    assert result["action"] == "LAUNCHER_ALREADY_RUNNING"
    assert host.started == 0


def test_supervisor_circuit_breaker_after_three_relaunches_per_hour(tmp_path):
    repo, _ = _repo(tmp_path, triggered=False)
    host = Host(alive=False)
    alerts = Alerts()

    actions = [_supervise(repo, host, alerts)["action"] for _ in range(4)]

    assert actions[:3] == ["RELAUNCH_REQUESTED"] * 3
    assert actions[3] == "CIRCUIT_BREAKER_OPEN"
    assert host.started == 3
    assert any(name == "RUNTIME_SUPERVISOR_CIRCUIT_BREAKER" for name, _ in alerts)


def test_supervisor_does_not_relaunch_into_owner_kill(tmp_path):
    repo, _ = _repo(tmp_path, actor=OWNER_SID, runtime_reason=None)
    host = Host(alive=False)
    alerts = Alerts()

    result = _supervise(repo, host, alerts)

    assert result["action"] == "OWNER_ACTION_REQUIRED"
    assert host.started == 0


def test_supervisor_stops_only_verified_idle_runtime_under_recoverable_kill(tmp_path):
    repo, db_path = _repo(tmp_path)
    with Database.open(db_path) as db:
        _lock(db, heartbeat=NOW - timedelta(seconds=10))
    host = Host(alive=True)

    result = _supervise(repo, host, Alerts())

    assert result["action"] == "STOP_IDLE_RUNTIME_REQUESTED"
    assert host.terminated == [111]


def test_supervisor_refuses_to_stop_unverified_process(tmp_path):
    repo, db_path = _repo(tmp_path)
    with Database.open(db_path) as db:
        _lock(db, heartbeat=NOW - timedelta(seconds=10))
    host = Host(alive=True, cmdline="notepad.exe")

    result = _supervise(repo, host, Alerts())

    assert host.terminated == []
    assert result["action"] == "PROCESS_IDENTITY_UNVERIFIED"


def test_supervisor_does_not_stop_runtime_with_exposure(tmp_path):
    repo, db_path = _repo(tmp_path)
    with Database.open(db_path) as db:
        _lock(db, heartbeat=NOW - timedelta(seconds=10))
        SleeveLedgerStore(db).append(
            CapitalSleeve.REGULAR_SLEEVE, "BROKER_STATE_RECONCILED",
            {"positions": [{"quantity": "4"}], "open_order_count": 0},
        )
    host = Host(alive=True)

    result = _supervise(repo, host, Alerts())

    assert host.terminated == []
    assert result["action"] == "KILL_SWITCH_EXPOSURE_PRESENT"


# --- auditor receipt renewal -------------------------------------------------------------

def _renew(repo, *, completed_age, runtime_alive=True, head=HEAD, stage_ok=True, gate_after="PASS"):
    calls = []
    receipt = repo / "state" / "ibkr_paper_30d" / "reports" / "auditor_gate_v2_receipt.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"completed_at_utc": (NOW - completed_age).isoformat().replace("+00:00", "Z")}))

    def run_stage(launch_attempt_id):
        calls.append(launch_attempt_id)
        if stage_ok:
            receipt.write_text(json.dumps({"completed_at_utc": NOW.isoformat().replace("+00:00", "Z")}))
        return 0 if stage_ok else 1

    alerts = Alerts()
    result = rs.renew_auditor_receipt_if_due(
        repo_root=repo, now_utc=lambda: NOW, runtime_alive=lambda: runtime_alive,
        head_reader=lambda _: head, run_receipts_stage=run_stage,
        auditor_gate=lambda: {"gate_status": gate_after}, alert_sink=alerts,
        launch_attempt_id_reader=lambda: "11111111-1111-1111-1111-111111111111",
    )
    return result, calls, alerts


def test_receipt_renewal_not_due_when_fresh(tmp_path):
    repo, _ = _repo(tmp_path, triggered=False)

    result, calls, _ = _renew(repo, completed_age=timedelta(hours=5))

    assert result["status"] == "NOT_DUE" and calls == []


def test_receipt_near_expiry_is_renewed_by_independent_stage(tmp_path):
    repo, db_path = _repo(tmp_path, triggered=False)

    result, calls, _ = _renew(repo, completed_age=timedelta(hours=21))

    assert result["status"] == "RENEWED"
    assert calls == ["11111111-1111-1111-1111-111111111111"]


def test_receipt_renewal_failure_alerts_owner(tmp_path):
    repo, _ = _repo(tmp_path, triggered=False)

    result, _, alerts = _renew(repo, completed_age=timedelta(hours=21), stage_ok=False)

    assert result["status"] == "FAILED"
    assert any(name == "AUDITOR_RECEIPT_RENEWAL_FAILED" for name, _ in alerts)


def test_receipt_renewal_requires_gate_pass_after_refresh(tmp_path):
    repo, _ = _repo(tmp_path, triggered=False)

    result, _, alerts = _renew(repo, completed_age=timedelta(hours=21), gate_after="BLOCK")

    assert result["status"] == "FAILED"
    assert alerts


def test_receipt_renewal_blocks_on_head_mismatch(tmp_path):
    repo, _ = _repo(tmp_path, triggered=False)

    result, calls, _ = _renew(repo, completed_age=timedelta(hours=21), head="d" * 40)

    assert result["status"] == "BLOCKED" and calls == []


def test_receipt_renewal_left_to_launcher_when_runtime_is_down(tmp_path):
    repo, _ = _repo(tmp_path, triggered=False)

    result, calls, _ = _renew(repo, completed_age=timedelta(hours=21), runtime_alive=False)

    assert result["status"] == "LAUNCHER_RENEWS" and calls == []


def test_supervisor_does_not_relaunch_after_measurement_clock_end(tmp_path):
    repo, db_path = _repo(tmp_path, triggered=False)
    with Database.open(db_path) as db:
        rs._append_state_event(db, "EXPERIMENT_MEASUREMENT_CLOCK_STARTED",
                               {"end_utc": (NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")},
                               now=NOW - timedelta(days=30))
    host = Host(alive=False)

    result = _supervise(repo, host, Alerts())

    assert result["action"] == "EXPERIMENT_CLOCK_ENDED"
    assert host.started == 0