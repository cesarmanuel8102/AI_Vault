#!/usr/bin/env python3
from __future__ import annotations

import atexit
import importlib.util
import json
import shutil
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("agent_worker_v157_state_event", MODULE)
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

FRONT = "PILOT-KIMI-CODEX-20260716-091529"
BASE = "a" * 40
HEAD = "b" * 40
_GIT_TEMPLATE_ROOT: Path | None = None
_GIT_TEMPLATE_BASE_SHA: str | None = None


def _base_spec() -> dict:
    return {
        "front_id": FRONT,
        "expected_base_sha": BASE,
        "work_branch": "agent/pilot-20260716-091529",
        "max_kimi_cycles": 3,
        "allowed_paths": sorted(worker.PROFILE_ALLOWED_PATHS["pilot"]),
        "forbidden_paths": sorted(worker.REQUIRED_FORBIDDEN_PATHS),
        "test_profile": "pilot",
        "base_branch": "codex/own-capital-sustainable-return",
        "repo": "cesarmanuel8102/AI_Vault",
        "owner": "cesarmanuel8102",
        "schema_version": 1,
        "objective": "test",
    }


def _cfg(td: str) -> dict:
    return {
        "install_root": td,
        "repo": "cesarmanuel8102/AI_Vault",
        "owner": "cesarmanuel8102",
        "opencode_model": "ollama-cloud/kimi-k2.7-code",
        "opencode_output_token_max": 4096,
        "opencode_timeout_seconds": 5,
    }


def _terminal_set_phase(cfg: dict, state_path: Path, st: dict, phase: str, *, pr_number: int | None = None) -> dict:
    st = dict(st)
    st["status"] = phase
    st["updated_utc"] = worker.utc()
    worker.save_json(state_path, st)
    return st


def _terminal_notify(cfg: dict, state_path: Path, st: dict, phase: str, message: str) -> dict:
    st = dict(st)
    keys = set(st.get("notification_keys") or [])
    key = worker.notification_key(st.get("front"), st.get("pr_number"), st.get("last_head_sha"), phase)
    if key not in keys:
        keys.add(key)
        st["terminal_notified"] = True
    st["notification_keys"] = sorted(keys)
    worker.save_json(state_path, st)
    return st


def _patch_worker(**replacements):
    originals = {name: getattr(worker, name) for name in replacements}
    for name, value in replacements.items():
        setattr(worker, name, value)
    return originals


def _restore(originals):
    for name, value in originals.items():
        setattr(worker, name, value)


def _crash_after_nth_checkpoint(target_failure_class: str, crash_cls: type, n: int = 1):
    """Wrap _checkpoint_initial_cycle to crash after the n-th target class checkpoint."""
    real = worker._checkpoint_initial_cycle
    count = 0
    def wrapper(*a, **k):
        real(*a, **k)
        nonlocal count
        if len(a) > 7 and a[7] == target_failure_class:
            count += 1
            if count == n:
                raise crash_cls(f"crash after {target_failure_class} checkpoint #{n}")
    return wrapper


def _make_state(tmp: Path, cycles: int = 2) -> Path:
    repo_dir = tmp / "repo"
    repo_dir.mkdir()
    spec = _base_spec()
    state = {
        "issue_number": 5,
        "front": FRONT,
        "spec": spec,
        "repo_dir": str(repo_dir),
        "pr_number": 6,
        "pr_url": "https://example.invalid/pr/6",
        "cycles": cycles,
        "last_head_sha": HEAD,
        "opencode_session_id": "session-old",
        "status": "WAITING_GITHUB",
        "updated_utc": worker.utc(),
        "state_schema_version": worker.STATE_SCHEMA_VERSION,
        "worker_version": worker.WORKER_VERSION,
    }
    state_path = tmp / "state" / "issue-5.json"
    worker.save_json(state_path, state)
    return state_path


def _base_process_patches(tmp: Path, *, audit_error: Exception | None = None, marker_ok: bool = True,
                          changed: list[str] | None = None, final_ok: bool = True):
    log = tmp / "opencode.jsonl"
    log.write_text(json.dumps({"type": "text", "part": {"text": worker.prompt_task_sentinel(FRONT, 3)}}) + "\n", encoding="utf-8")
    model_dir = tmp / "model"
    (model_dir / "docs/agent_loop/pilot").mkdir(parents=True)
    (model_dir / "docs/agent_loop/pilot/PILOT_MARKER.md").write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")

    def fake_gh_json(args):
        joined = " ".join(str(x) for x in args)
        if "pr view" in joined:
            return {"number": 6, "url": "https://example.invalid/pr/6", "headRefOid": HEAD, "labels": [{"name": "loop:repairing"}], "state": "OPEN"}
        return {"number": 5, "labels": [{"name": "loop:repairing"}]}

    def fake_run(args, cwd=None, check=True):
        text = " ".join(str(x) for x in args)
        if "rev-parse HEAD" in text:
            return HEAD
        if "diff --cached --name-only" in text:
            return "docs/agent_loop/pilot/PILOT_MARKER.md\ndocs/agent_loop/pilot/EXECUTOR_REPORT.json\n"
        return ""

    def fake_prepare(repo_dir, spec, cycle):
        return model_dir, {}

    def fake_audit(model_dir_arg, repo_dir, seed_hashes, spec):
        if audit_error:
            raise audit_error
        return ["docs/agent_loop/pilot/PILOT_MARKER.md"]

    return {
        "gh_json": fake_gh_json,
        "run": fake_run,
        "latest_feedback": lambda *a, **k: "feedback",
        "prepare_model_workspace": fake_prepare,
        "validate_executor_delivery": lambda *a, **k: None,
        "audit_and_sync_model_workspace": fake_audit,
        "run_marker_content_check": lambda repo_dir, expected_front_id: (marker_ok, "marker failure" if not marker_ok else "ok"),
        "changed_files": lambda repo_dir, base_sha: list(changed if changed is not None else ["docs/agent_loop/pilot/PILOT_MARKER.md"]),
        "marker_hash": lambda repo_dir: "markerhash",
        "path_allowed": lambda path, allowed, forbidden: path in worker.PROFILE_ALLOWED_PATHS["pilot"],
        "write_executor_report": lambda *a, **k: None,
        "run_final_verifier": lambda *a, **k: (final_ok, "final verifier failure" if not final_ok else "ok"),
        "write_final_local_report": lambda *a, **k: tmp / "final.json",
        "set_converged_phase": _terminal_set_phase,
        "publish_terminal_notification": _terminal_notify,
    }


def _common_process_patches(tmp: Path, *, audit_error: Exception | None = None, marker_ok: bool = True,
                            changed: list[str] | None = None, final_ok: bool = True):
    log = tmp / "opencode.jsonl"

    def fake_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
        return log, "session-new"

    replacements = _base_process_patches(tmp, audit_error=audit_error, marker_ok=marker_ok, changed=changed, final_ok=final_ok)
    replacements["run_kimi"] = fake_run_kimi
    return _patch_worker(**replacements)


def _preflight_process_patches(tmp: Path, *, audit_error: Exception | None = None, marker_ok: bool = True,
                               changed: list[str] | None = None, final_ok: bool = True):
    replacements = _base_process_patches(tmp, audit_error=audit_error, marker_ok=marker_ok, changed=changed, final_ok=final_ok)
    return _patch_worker(**replacements)


def _events(tmp: Path) -> list[dict]:
    path = tmp / "reports" / "worker-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_state_schema_version_injected() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "state" / "issue-5.json"
        original = {"issue_number": 5, "front": FRONT, "spec": _base_spec(), "status": "WAITING_GITHUB", "updated_utc": worker.utc()}
        worker.save_json(path, original)
        loaded = worker.load_json(path)
        assert loaded.get("state_schema_version") == worker.STATE_SCHEMA_VERSION
        assert loaded.get("worker_version") == worker.WORKER_VERSION
        assert worker.validate_state_json(loaded) == []


def test_terminalize_state_error_generates_schema_valid_state() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = tmp / "state" / "issue-5.json"
        worker.save_json(state_path, {"issue_number": 5, "front": FRONT, "spec": _base_spec(), "status": "WAITING_GITHUB", "updated_utc": worker.utc()})
        originals = _patch_worker(set_converged_phase=_terminal_set_phase, publish_terminal_notification=_terminal_notify)
        try:
            worker.terminalize_state_error(_cfg(td), state_path, ValueError("base moved: expected x actual y"))
        finally:
            _restore(originals)
        loaded = worker.load_json(state_path)
        assert loaded["status"] == "loop:blocked"
        assert "error" in loaded and "last_error" not in loaded
        assert worker.validate_state_json(loaded) == []


def test_state_validation_rejects_unknown_and_missing() -> None:
    assert any("missing" in e.lower() for e in worker.validate_state_json({"issue_number": 5, "updated_utc": worker.utc()}))
    unknown = {"issue_number": 5, "status": "WAITING_GITHUB", "updated_utc": worker.utc(), "extra_field": True}
    assert any("unknown" in e.lower() for e in worker.validate_state_json(unknown))


def test_event_contract_enforces_required_fields_and_worker_version() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg = _cfg(td)
        worker.event(cfg, "executor_started", front=FRONT, issue=19, cycle=1, command_identity="opencode", model="m")
        try:
            worker.event(cfg, "executor_started", front=FRONT, cycle=1)
        except RuntimeError as exc:
            assert "EVENT_CONTRACT_VIOLATION" in str(exc)
        else:
            raise AssertionError("expected event contract violation")
        evt = _events(Path(td))[0]
        assert evt["kind"] == "executor_started"
        assert evt["worker_version"] == worker.WORKER_VERSION
        assert {"front", "issue", "cycle", "command_identity", "model"}.issubset(evt)


def test_event_contract_rejects_sensitive_fields() -> None:
    with tempfile.TemporaryDirectory() as td:
        try:
            worker.event(_cfg(td), "executor_started", front=FRONT, cycle=1, command_identity="opencode", model="m", token="secret")
        except RuntimeError as exc:
            assert "sensitive field" in str(exc)
        else:
            raise AssertionError("expected sensitive event field rejection")


def test_worker_started_event_contract() -> None:
    with tempfile.TemporaryDirectory() as td:
        worker.event(_cfg(td), "worker_started", once=True, worker_version=worker.WORKER_VERSION, worker_sha256="abc")
        evt = _events(Path(td))[0]
        assert evt["kind"] == "worker_started"
        assert evt["worker_version"] == worker.WORKER_VERSION


def test_legacy_repair_local_gate_aliases_to_local_gate_failed() -> None:
    with tempfile.TemporaryDirectory() as td:
        worker.event(_cfg(td), "repair_local_gate_failed", issue=5, pr=6, cycle=3, failure_class="MODEL_CONTENT_FAILURE", cycle_before=2, cycle_after=3)
        evt = _events(Path(td))[0]
        assert evt["kind"] == "local_gate_failed"
        assert evt["legacy_kind"] == "repair_local_gate_failed"


def test_event_chronology_rejects_impossible_sequence() -> None:
    assert worker.validate_v157_event_chronology([
        {"kind": "state_terminalized", "issue": 5, "pr": 6, "phase": "loop:token-exhausted", "failure_class": "MODEL_CONTENT_FAILURE"},
        {"kind": "local_gate_failed", "issue": 5, "pr": 6, "cycle": 3, "failure_class": "MODEL_CONTENT_FAILURE"},
    ])
    assert worker.validate_v157_event_chronology([
        {"kind": "local_gate_failed", "issue": 5, "pr": 6, "cycle": 3, "failure_class": "MODEL_CONTENT_FAILURE"},
        {"kind": "state_terminalized", "issue": 5, "pr": 6, "phase": "loop:token-exhausted", "failure_class": "MODEL_CONTENT_FAILURE"},
    ]) == []


def test_event_chronology_rejects_pushed_without_committed() -> None:
    assert worker.validate_v157_event_chronology([
        {"kind": "cycle_pushed", "issue": 5, "pr": 6, "cycle": 3, "head_sha": HEAD},
    ])


def test_event_chronology_rejects_pushed_before_committed() -> None:
    assert worker.validate_v157_event_chronology([
        {"kind": "cycle_pushed", "issue": 5, "pr": 6, "cycle": 3, "head_sha": HEAD},
        {"kind": "cycle_committed", "issue": 5, "pr": 6, "cycle": 3, "head_sha": HEAD},
    ])


def test_event_chronology_rejects_committed_pushed_after_terminalized() -> None:
    assert worker.validate_v157_event_chronology([
        {"kind": "state_terminalized", "issue": 5, "pr": 6, "phase": "loop:token-exhausted", "failure_class": "MAX_CYCLES_REACHED"},
        {"kind": "cycle_committed", "issue": 5, "pr": 6, "cycle": 3, "head_sha": HEAD},
    ])
    assert worker.validate_v157_event_chronology([
        {"kind": "state_terminalized", "issue": 5, "pr": 6, "phase": "loop:token-exhausted", "failure_class": "MAX_CYCLES_REACHED"},
        {"kind": "cycle_pushed", "issue": 5, "pr": 6, "cycle": 3, "head_sha": HEAD},
    ])


def test_event_chronology_rejects_executor_started_after_terminalized() -> None:
    assert worker.validate_v157_event_chronology([
        {"kind": "state_terminalized", "issue": 5, "pr": 6, "phase": "loop:token-exhausted", "failure_class": "MAX_CYCLES_REACHED"},
        {"kind": "executor_started", "issue": 5, "pr": 6, "cycle": 4, "command_identity": "opencode", "model": "m"},
    ])


def test_event_chronology_rejects_reverted_without_committed() -> None:
    assert any(
        "reverted" in e.lower()
        for e in worker.validate_v157_event_chronology([
            {"kind": "cycle_commit_reverted", "issue": 5, "pr": 6, "cycle": 3, "head_sha": HEAD, "failure_class": "TRUSTED_VERIFIER_OR_WORKER_INTERNAL_FAILURE"},
        ])
    )


def test_event_chronology_rejects_preflight_then_executor_started() -> None:
    errors = worker.validate_v157_event_chronology([
        {"kind": "executor_started", "issue": 5, "pr": 6, "cycle": 1, "command_identity": "opencode", "model": "m"},
        {"kind": "executor_preflight_failed", "issue": 5, "pr": 6, "cycle": 1, "failure_class": "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED", "command_identity": "opencode"},
    ])
    assert any("executor_preflight_failed_after_executor_started" in e for e in errors), errors


def test_event_chronology_rejects_post_preflight_actions() -> None:
    errors = worker.validate_v157_event_chronology([
        {"kind": "executor_preflight_failed", "issue": 5, "pr": 6, "cycle": 1, "failure_class": "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED", "command_identity": "opencode"},
        {"kind": "executor_failed", "issue": 5, "pr": 6, "cycle": 1, "error": "x", "failure_class": "COMMAND_FAILED"},
    ])
    assert any("after_executor_preflight_failed" in e for e in errors), errors


def test_event_chronology_preflight_other_issue_does_not_validate_terminalization() -> None:
    errors = worker.validate_v157_event_chronology([
        {"kind": "executor_preflight_failed", "issue": 5, "pr": 6, "cycle": 1, "failure_class": "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED", "command_identity": "opencode"},
        {"kind": "state_terminalized", "issue": 9, "pr": 10, "phase": "loop:blocked", "failure_class": "MODEL_CONTENT_FAILURE"},
    ])
    assert any("state_terminalized_without_prior_local_gate" in e and "('9', '10')" in e for e in errors), errors


def test_event_chronology_preflight_same_issue_validates_terminalization() -> None:
    errors = worker.validate_v157_event_chronology([
        {"kind": "executor_preflight_failed", "issue": 9, "pr": 10, "cycle": 1, "failure_class": "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED", "command_identity": "opencode"},
        {"kind": "state_terminalized", "issue": 9, "pr": 10, "phase": "loop:blocked", "failure_class": "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED"},
    ])
    assert errors == [], errors


def test_event_chronology_local_gate_same_issue_validates_terminalization() -> None:
    errors = worker.validate_v157_event_chronology([
        {"kind": "local_gate_failed", "issue": 9, "pr": 10, "cycle": 3, "failure_class": "MODEL_CONTENT_FAILURE", "cycle_before": 2, "cycle_after": 3},
        {"kind": "state_terminalized", "issue": 9, "pr": 10, "phase": "loop:token-exhausted", "failure_class": "MODEL_CONTENT_FAILURE"},
    ])
    assert errors == [], errors


def test_event_chronology_multi_front_isolation() -> None:
    errors = worker.validate_v157_event_chronology([
        {"kind": "executor_preflight_failed", "issue": 5, "pr": 6, "cycle": 1, "failure_class": "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED", "command_identity": "opencode"},
        {"kind": "state_terminalized", "issue": 7, "pr": 8, "phase": "loop:blocked", "failure_class": "MODEL_CONTENT_FAILURE"},
        {"kind": "local_gate_failed", "issue": 11, "pr": 12, "cycle": 3, "failure_class": "MODEL_CONTENT_FAILURE", "cycle_before": 2, "cycle_after": 3},
        {"kind": "state_terminalized", "issue": 11, "pr": 12, "phase": "loop:token-exhausted", "failure_class": "MODEL_CONTENT_FAILURE"},
        {"kind": "executor_preflight_failed", "issue": 13, "pr": 14, "cycle": 1, "failure_class": "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED", "command_identity": "opencode"},
        {"kind": "state_terminalized", "issue": 13, "pr": 14, "phase": "loop:blocked", "failure_class": "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED"},
    ])
    assert any("state_terminalized_without_prior_local_gate" in e and "('7', '8')" in e for e in errors), errors
    assert not any("state_terminalized_without_prior_local_gate" in e and "('11', '12')" in e for e in errors), errors
    assert not any("state_terminalized_without_prior_local_gate" in e and "('13', '14')" in e for e in errors), errors


def _assert_terminalized_without_post_actions(tmp: Path, state_path: Path) -> None:
    state = worker.load_json(state_path)
    assert state["cycles"] == 3
    assert state["status"] == "loop:token-exhausted"
    assert state.get("terminal_notified") is True
    events = _events(tmp)
    kinds = [e["kind"] for e in events]
    assert "local_gate_failed" in kinds
    assert "state_terminalized" in kinds
    assert "cycle_pushed" not in kinds
    assert worker.validate_v157_event_chronology(events) == []


def test_final_cycle_audit_failure_terminalizes_same_run() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp)
        originals = _common_process_patches(tmp, audit_error=RuntimeError("PILOT_MARKER_CONTENT_MISMATCH"))
        try:
            worker.process_state(_cfg(td), state_path)
            _assert_terminalized_without_post_actions(tmp, state_path)
            before_events = len(_events(tmp))
            worker.process_state(_cfg(td), state_path)
            assert len(_events(tmp)) == before_events
        finally:
            _restore(originals)


def test_final_cycle_marker_failure_terminalizes_same_run() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp)
        originals = _common_process_patches(tmp, marker_ok=False)
        try:
            worker.process_state(_cfg(td), state_path)
            _assert_terminalized_without_post_actions(tmp, state_path)
        finally:
            _restore(originals)


def test_final_cycle_out_of_scope_terminalizes_same_run() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp)
        originals = _common_process_patches(tmp, changed=["docs/agent_loop/pilot/PILOT_MARKER.md", "evil.txt"])
        try:
            worker.process_state(_cfg(td), state_path)
            _assert_terminalized_without_post_actions(tmp, state_path)
        finally:
            _restore(originals)


def test_final_cycle_final_verifier_failure_terminalizes_without_push() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp)
        calls: list[str] = []
        originals = _common_process_patches(tmp, changed=list(worker.PROFILE_ALLOWED_PATHS["pilot"]), final_ok=False)
        real_run = originals.get("run", worker.run)
        def recording_run(args, cwd=None, check=True):
            text = " ".join(str(x) for x in args)
            calls.append(text)
            return real_run(args, cwd=cwd, check=check) if text.startswith("never") else (HEAD if "rev-parse HEAD" in text else "")
        originals2 = _patch_worker(run=recording_run)
        try:
            worker.process_state(_cfg(td), state_path)
            _assert_terminalized_without_post_actions(tmp, state_path)
            assert not any("git push" in c for c in calls)
            events = _events(tmp)
            assert not any(e["kind"] == "cycle_committed" for e in events)
            assert not any(e["kind"] == "cycle_pushed" for e in events)
        finally:
            _restore(originals2)
            _restore(originals)


def test_executor_attempt_consumed_non_final_saves_state() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        events: list[dict] = []
        originals = _common_process_patches(tmp)

        def fake_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            events.append({"kind": "injected", "cycle": cycle})
            raise worker.ExecutorAttemptConsumed("EXECUTOR_TIMEOUT", "timeout", {"cycle": cycle, "command_identity": "opencode", "local_log_path": str(tmp / "opencode.jsonl"), "returncode": None})

        originals2 = _patch_worker(run_kimi=fake_run_kimi)
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            assert state["cycles"] == 2
            assert state["status"] == "WAITING_GITHUB"
            assert not worker.state_is_terminal(state)
            events = _events(tmp)
            assert any(e["kind"] == "executor_failed" and e.get("failure_class") == "EXECUTOR_TIMEOUT" for e in events)
        finally:
            _restore(originals2)
            _restore(originals)


def test_executor_attempt_consumed_final_terminalizes() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=2)
        originals = _common_process_patches(tmp)

        def fake_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            raise worker.ExecutorAttemptConsumed("COMMAND_FAILED", "non-zero", {"cycle": cycle, "command_identity": "opencode", "local_log_path": str(tmp / "opencode.jsonl"), "returncode": 1})

        originals2 = _patch_worker(run_kimi=fake_run_kimi)
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            assert state["cycles"] == 3
            assert state["status"] == "loop:token-exhausted"
            assert any(e["kind"] == "executor_failed" and e.get("failure_class") == "COMMAND_FAILED" for e in events)
            assert any(e["kind"] == "state_terminalized" for e in events)
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            _restore(originals2)
            _restore(originals)


def test_prompt_canary_absent_from_exception_and_log() -> None:
    canary = "CANARY_PROMPT_CONTENT_12345"
    safe = worker._redacted_cmd_repr(["opencode", "run", "--dir", "C:\d", "--model", "m", canary])
    assert all(canary not in str(x) for x in safe), safe


def test_command_string_fallback_blocks_without_executor_started() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        calls: list[str] = []
        old_subprocess_run = worker.subprocess.run
        old_command_for_subprocess = worker.command_for_subprocess
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP

        def fake_subprocess_run(*args, **kwargs):
            calls.append("subprocess.run")
            raise AssertionError("subprocess.run must not be called for preflight failure")

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.subprocess.run = fake_subprocess_run
        worker.command_for_subprocess = lambda args: r'cmd.exe /d /s /c fake_opencode.CMD run "prompt"'
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            kinds = [e["kind"] for e in events]
            assert state["cycles"] == 1
            assert state["status"] == "loop:blocked"
            assert "executor_preflight_failed" in kinds
            assert "executor_started" not in kinds
            assert "executor_failed" not in kinds
            assert "state_terminalized" in kinds
            assert not any("subprocess.run" in c for c in calls)
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            worker.subprocess.run = old_subprocess_run
            worker.command_for_subprocess = old_command_for_subprocess
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def test_cmd_exe_fallback_blocks_without_executor_started() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        calls: list[str] = []
        old_subprocess_run = worker.subprocess.run
        old_command_for_subprocess = worker.command_for_subprocess
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP

        def fake_subprocess_run(*args, **kwargs):
            calls.append("subprocess.run")
            raise AssertionError("subprocess.run must not be called for cmd.exe fallback")

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.subprocess.run = fake_subprocess_run
        worker.command_for_subprocess = lambda args: ["cmd.exe", "/d", "/s", "/c", "fake_opencode.CMD", "run", "prompt"]
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            kinds = [e["kind"] for e in events]
            assert state["cycles"] == 1
            assert state["status"] == "loop:blocked"
            assert "executor_preflight_failed" in kinds
            assert "executor_started" not in kinds
            assert not any("subprocess.run" in c for c in calls)
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            worker.subprocess.run = old_subprocess_run
            worker.command_for_subprocess = old_command_for_subprocess
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def test_missing_node_exe_blocks_without_executor_started() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        old_subprocess_run = worker.subprocess.run
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP

        def fake_subprocess_run(*args, **kwargs):
            raise AssertionError("subprocess.run must not be called when node is missing")

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.subprocess.run = fake_subprocess_run
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            kinds = [e["kind"] for e in events]
            assert state["cycles"] == 1
            assert state["status"] == "loop:blocked"
            assert "executor_preflight_failed" in kinds
            assert "executor_started" not in kinds
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            worker.subprocess.run = old_subprocess_run
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def test_missing_entrypoint_blocks_without_executor_started() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        old_subprocess_run = worker.subprocess.run
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP

        def fake_subprocess_run(*args, **kwargs):
            raise AssertionError("subprocess.run must not be called when entrypoint is missing")

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe"}
        worker.subprocess.run = fake_subprocess_run
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            kinds = [e["kind"] for e in events]
            assert state["cycles"] == 1
            assert state["status"] == "loop:blocked"
            assert "executor_preflight_failed" in kinds
            assert "executor_started" not in kinds
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            worker.subprocess.run = old_subprocess_run
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def test_prompt_missing_sentinel_blocks_without_executor_started() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        old_subprocess_run = worker.subprocess.run
        old_make_prompt = worker.make_prompt
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP

        def fake_subprocess_run(*args, **kwargs):
            raise AssertionError("subprocess.run must not be called when sentinel is missing")

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.make_prompt = lambda spec, cycle, feedback=None: "prompt without sentinel"
        worker.subprocess.run = fake_subprocess_run
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            kinds = [e["kind"] for e in events]
            assert state["cycles"] == 1
            assert state["status"] == "loop:blocked"
            assert "executor_preflight_failed" in kinds
            assert "executor_started" not in kinds
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            worker.subprocess.run = old_subprocess_run
            worker.make_prompt = old_make_prompt
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def test_preflight_blocked_state_does_not_retry_kimi() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        old_subprocess_run = worker.subprocess.run
        old_command_for_subprocess = worker.command_for_subprocess
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP

        def fake_subprocess_run(*args, **kwargs):
            raise AssertionError("no subprocess")

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.subprocess.run = fake_subprocess_run
        worker.command_for_subprocess = lambda args: r'C:\System32\cmd.exe /d /s /c fake_opencode.CMD run "prompt"'
        try:
            worker.process_state(_cfg(td), state_path)
            before_events = len(_events(tmp))
            worker.process_state(_cfg(td), state_path)
            after_events = len(_events(tmp))
            state = worker.load_json(state_path)
            assert state["status"] == "loop:blocked"
            assert after_events == before_events
        finally:
            worker.subprocess.run = old_subprocess_run
            worker.command_for_subprocess = old_command_for_subprocess
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def test_timeout_consumes_attempt_and_preserves_local_log_path() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        old_subprocess_run = worker.subprocess.run
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP
        canary = "ULTRA_SECRET_STDOUT_CANARY_4C92E8"

        def fake_subprocess_run(*args, **kwargs):
            raise worker.subprocess.TimeoutExpired(args, timeout=1, output=(canary + " timeout output").encode("utf-8"))

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.subprocess.run = fake_subprocess_run
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            kinds = [e["kind"] for e in events]
            assert state["cycles"] == 2
            assert state["status"] == "WAITING_GITHUB"
            assert "executor_started" in kinds
            assert "executor_failed" in kinds
            assert "executor_preflight_failed" not in kinds
            log_event = next(e for e in events if e["kind"] == "executor_failed")
            assert log_event.get("local_log_path")
            assert canary not in json.dumps(state)
            assert canary not in json.dumps(events)
            assert canary not in str(state.get("error", ""))
            assert canary not in log_event.get("error", "")
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            worker.subprocess.run = old_subprocess_run
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def test_token_exhausted_output_canary_not_leaked() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        old_subprocess_run = worker.subprocess.run
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP
        canary = "ULTRA_SECRET_STDOUT_CANARY_4C92E8"

        def fake_subprocess_run(*args, **kwargs):
            return worker.subprocess.CompletedProcess(args, returncode=1, stdout=(canary + " token context rate limit").encode("utf-8"))

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.subprocess.run = fake_subprocess_run
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            failure_event = next(e for e in events if e["kind"] == "executor_failed")
            assert failure_event["failure_class"] == "TOKEN_EXHAUSTED"
            assert canary not in json.dumps(state)
            assert canary not in json.dumps(events)
            assert canary not in str(state.get("error", ""))
            assert canary not in failure_event.get("error", "")
            log_path = Path(str(failure_event.get("local_log_path")))
            assert log_path.exists() and canary in log_path.read_text(encoding="utf-8")
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            worker.subprocess.run = old_subprocess_run
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def test_command_failed_output_canary_not_leaked() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        old_subprocess_run = worker.subprocess.run
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP
        canary = "ULTRA_SECRET_STDOUT_CANARY_4C92E8"

        def fake_subprocess_run(*args, **kwargs):
            return worker.subprocess.CompletedProcess(args, returncode=2, stdout=(canary + " generic crash").encode("utf-8"))

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.subprocess.run = fake_subprocess_run
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            failure_event = next(e for e in events if e["kind"] == "executor_failed")
            assert failure_event["failure_class"] == "COMMAND_FAILED"
            assert canary not in json.dumps(state)
            assert canary not in json.dumps(events)
            assert canary not in failure_event.get("error", "")
            log_path = Path(str(failure_event.get("local_log_path")))
            assert log_path.exists() and canary in log_path.read_text(encoding="utf-8")
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            worker.subprocess.run = old_subprocess_run
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def test_prompt_canary_not_leaked_anywhere() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        old_subprocess_run = worker.subprocess.run
        old_make_prompt = worker.make_prompt
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP
        canary = "ULTRA_SECRET_PROMPT_CANARY_7F3A91"

        base_prompt = worker.make_prompt(_base_spec(), 1)

        def canary_prompt(spec, cycle, feedback=None):
            return base_prompt + "\n" + canary

        def fake_subprocess_run(args, **kwargs):
            prompt = str(args[-1]) if isinstance(args, list) else ""
            assert canary in prompt, "canary must be in prompt for this test"
            return worker.subprocess.CompletedProcess(args, returncode=1, stdout=b"token context rate limit")

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.make_prompt = canary_prompt
        worker.subprocess.run = fake_subprocess_run
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            prompt_arg = canary_prompt(_base_spec(), 1)
            safe_log = worker.sanitize_command_for_log(["opencode", "run", "--dir", "C:\d", "--model", "m", prompt_arg])
            redacted_log = worker._redacted_cmd_repr(["opencode", "run", "--dir", "C:\d", "--model", "m", prompt_arg])
            all_surfaces = [json.dumps(state), json.dumps(events), json.dumps(safe_log), json.dumps(redacted_log), str(state.get("error", ""))]
            assert all(canary not in s for s in all_surfaces), all_surfaces
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            worker.subprocess.run = old_subprocess_run
            worker.make_prompt = old_make_prompt
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def test_timeout_traceback_does_not_leak_prompt_or_stdout_canary() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = {
            "install_root": td,
            "opencode_model": "ollama-cloud/kimi-k2.7-code",
            "opencode_output_token_max": 4096,
            "opencode_timeout_seconds": 5,
        }
        model_dir = tmp / "model"
        model_dir.mkdir(parents=True)
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")
        (Path(td) / "reports").mkdir(parents=True, exist_ok=True)
        prompt_canary = "ULTRA_SECRET_PROMPT_CANARY_7F3A91"
        stdout_canary = "ULTRA_SECRET_STDOUT_CANARY_4C92E8"

        old_subprocess_run = worker.subprocess.run
        old_event = worker.event
        old_make_prompt = worker.make_prompt
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP
        original_make_prompt = old_make_prompt

        worker._OPENCODE_RUN_HELP = "Options:\n  --model\n"
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}

        def canary_prompt(spec, cycle, feedback=None):
            return original_make_prompt(spec, cycle, feedback) + "\n" + prompt_canary

        captured_args = None
        def fake_subprocess_run(args, **kwargs):
            nonlocal captured_args
            captured_args = args
            prompt = str(args[-1]) if isinstance(args, list) else ""
            assert prompt_canary in prompt, "prompt canary must be in prompt for this test"
            raise worker.subprocess.TimeoutExpired(args, timeout=1, output=(stdout_canary + " timeout output").encode("utf-8"))

        events_before = []
        worker.event = lambda _cfg, kind, **fields: events_before.append({"kind": kind, **fields})
        worker.make_prompt = canary_prompt
        worker.subprocess.run = fake_subprocess_run
        exc = None
        try:
            worker.run_kimi(cfg, _base_spec(), model_dir, 5, 1)
        except Exception as caught:
            exc = caught
        finally:
            worker.make_prompt = old_make_prompt
            worker.subprocess.run = old_subprocess_run
            worker.event = old_event
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help

        assert exc is not None
        assert isinstance(exc, worker.ExecutorAttemptConsumed), type(exc)
        assert exc.failure_class == "EXECUTOR_TIMEOUT"
        assert exc.__cause__ is None
        trace_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        assert prompt_canary not in str(exc)
        assert prompt_canary not in trace_text
        assert stdout_canary not in str(exc)
        assert stdout_canary not in trace_text
        assert any(e["kind"] == "executor_started" for e in events_before)
        assert captured_args is not None
        log = Path(td) / "reports" / "issue-5-cycle-1-opencode.jsonl"
        assert log.exists()
        assert stdout_canary in log.read_text(encoding="utf-8")
        assert worker.subprocess.run is old_subprocess_run
        assert worker.event is old_event
        assert worker.make_prompt is old_make_prompt
        assert worker._RUNTIME_EXECUTABLES is old_runtime
        assert worker._OPENCODE_RUN_HELP == old_help


def test_timeout_via_process_state_consumes_exactly_one_cycle() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_state(tmp, cycles=1)
        originals = _preflight_process_patches(tmp)
        old_subprocess_run = worker.subprocess.run
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP
        prompt_canary = "ULTRA_SECRET_PROMPT_CANARY_7F3A91"
        stdout_canary = "ULTRA_SECRET_STDOUT_CANARY_4C92E8"
        original_make_prompt = worker.make_prompt

        def canary_prompt(spec, cycle, feedback=None):
            return original_make_prompt(spec, cycle, feedback) + "\n" + prompt_canary

        def fake_subprocess_run(args, **kwargs):
            prompt = str(args[-1]) if isinstance(args, list) else ""
            assert prompt_canary in prompt, "prompt canary must be in prompt for this test"
            raise worker.subprocess.TimeoutExpired(args, timeout=1, output=(stdout_canary + " timeout output").encode("utf-8"))

        worker._OPENCODE_RUN_HELP = ""
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.make_prompt = canary_prompt
        worker.subprocess.run = fake_subprocess_run
        try:
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            failure_event = next(e for e in events if e["kind"] == "executor_failed")
            assert failure_event["failure_class"] == "EXECUTOR_TIMEOUT"
            assert prompt_canary not in json.dumps(events)
            assert prompt_canary not in json.dumps(state)
            assert prompt_canary not in str(state.get("error", ""))
            assert prompt_canary not in failure_event.get("error", "")
            assert stdout_canary not in json.dumps(events)
            assert stdout_canary not in json.dumps(state)
            assert stdout_canary not in failure_event.get("error", "")
            assert state["cycles"] == 2
            log_path = Path(str(failure_event.get("local_log_path")))
            assert log_path.exists() and stdout_canary in log_path.read_text(encoding="utf-8")
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            worker.subprocess.run = old_subprocess_run
            worker.make_prompt = original_make_prompt
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help
            _restore(originals)


def _initial_front_spec(issue_number: int = 19) -> dict:
    spec = dict(_base_spec())
    spec["front_id"] = "PILOT-V157-ACTIVATION-20260720-0255"
    spec["work_branch"] = "agent/pilot-v157-activation-20260720-0255"
    spec["max_kimi_cycles"] = 3
    return spec


def _make_initial_state(tmp: Path, issue_number: int = 19) -> Path:
    spec = _initial_front_spec(issue_number)
    state = {
        "issue_number": issue_number,
        "front": spec["front_id"],
        "spec": spec,
        "repo_dir": str(tmp / "runs" / f"issue-{issue_number}" / "repo"),
        "cycles": 0,
        "status": "LOCAL_EXECUTION",
        "updated_utc": worker.utc(),
        "state_schema_version": worker.STATE_SCHEMA_VERSION,
        "worker_version": worker.WORKER_VERSION,
    }
    state_path = tmp / "state" / f"issue-{issue_number}.json"
    worker.save_json(state_path, state)
    return state_path


def _cleanup_git_template() -> None:
    global _GIT_TEMPLATE_ROOT
    if _GIT_TEMPLATE_ROOT is not None:
        shutil.rmtree(_GIT_TEMPLATE_ROOT, ignore_errors=True)
        _GIT_TEMPLATE_ROOT = None


def _git_template() -> tuple[Path, str]:
    global _GIT_TEMPLATE_ROOT, _GIT_TEMPLATE_BASE_SHA
    if _GIT_TEMPLATE_ROOT is not None and _GIT_TEMPLATE_BASE_SHA is not None:
        return _GIT_TEMPLATE_ROOT, _GIT_TEMPLATE_BASE_SHA

    root = Path(tempfile.mkdtemp(prefix="v157-git-template-"))
    devnull = worker.subprocess.DEVNULL
    worker.subprocess.run(["git", "init", "-q"], cwd=str(root), check=True, stdout=devnull, stderr=devnull)
    worker.subprocess.run(["git", "config", "user.name", "Test"], cwd=str(root), check=True, stdout=devnull, stderr=devnull)
    worker.subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(root), check=True, stdout=devnull, stderr=devnull)
    (root / "base.txt").write_text("base", encoding="utf-8")
    worker.subprocess.run(["git", "add", "base.txt"], cwd=str(root), check=True, stdout=devnull, stderr=devnull)
    worker.subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-q", "-m", "base"],
        cwd=str(root),
        check=True,
        stdout=devnull,
        stderr=devnull,
    )
    base_sha = worker.subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _GIT_TEMPLATE_ROOT = root
    _GIT_TEMPLATE_BASE_SHA = base_sha
    atexit.register(_cleanup_git_template)
    return root, base_sha


def _setup_git_repo(repo_dir: Path) -> str:
    if (repo_dir / ".git").is_dir():
        return worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
    template, base_sha = _git_template()
    shutil.copytree(template, repo_dir, dirs_exist_ok=True)
    return base_sha


def _initial_attempt_patches(tmp: Path, *, pass_on_cycle: int | None = None, failure_class: str = "TASK_NOT_ACKNOWLEDGED", preexecution: bool = False):
    repo_dir = tmp / "runs" / "issue-19" / "repo"
    _setup_git_repo(repo_dir)
    base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
    state_path = tmp / "state" / "issue-19.json"
    if state_path.exists():
        spec = worker.load_json(state_path).get("spec") or _initial_front_spec()
    else:
        spec = _initial_front_spec()
    spec["expected_base_sha"] = base_sha
    if state_path.exists():
        st = worker.load_json(state_path)
        st["spec"] = spec
        worker.save_json(state_path, st)

    def fake_gh_json(args):
        joined = " ".join(str(x) for x in args)
        if "issue view" in joined:
            return {"number": 19, "labels": [{"name": "agent:queued"}], "state": "OPEN", "author": {"login": "cesarmanuel8102"}}
        return {}

    old_run = worker.run

    def fake_run(args, cwd=None, check=True):
        text = " ".join(str(x) for x in args)
        if "rev-parse HEAD" in text:
            return old_run(["git", "rev-parse", "HEAD"], cwd=str(cwd)).strip()
        if "merge-base" in text:
            return spec["expected_base_sha"]
        if "diff --cached --name-only" in text:
            return "\n".join(worker.PROFILE_ALLOWED_PATHS["pilot"])
        if "git commit" in text and "complete" in text:
            old_run(["git", "add", "--all"], cwd=cwd, check=True)
            old_run(["git", "commit", "-m", f"complete {spec['front_id']}"], cwd=cwd, check=True)
            return ""
        if "git push" in text and "-u origin" in text:
            return ""
        return ""

    def fake_create_pr(cfg, spec, issue_no, repo_dir):
        return {"number": 99, "url": "https://example.invalid/pr/99", "headRefOid": old_run(["git", "rev-parse", "HEAD"], cwd=repo_dir).strip()}

    def fake_prepare(repo_dir_path, spec, cycle):
        cycle_dir = tmp / f"model-cycle-{cycle}"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        marker = cycle_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True, exist_ok=True)
        # Do not seed the marker; the executor must create it.
        return cycle_dir, {}

    calls: list[tuple[int, str | None]] = []

    def fake_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
        calls.append((cycle, feedback))
        if preexecution:
            raise worker.PreExecutionFailure(
                "PROMPT_MISSING_SENTINEL",
                "prompt missing sentinel",
                {"command_identity": "opencode"},
            )
        if pass_on_cycle is not None and cycle == pass_on_cycle:
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            front = spec["front_id"]
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(front, cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
            return log_path, "session-new"
        raise worker.ExecutorAttemptConsumed(
            failure_class,
            "ack missing",
            {"cycle": cycle, "command_identity": "opencode", "local_log_path": str(tmp / f"cycle-{cycle}.jsonl"), "returncode": None},
        )

    def fake_audit(model_dir_arg, repo_dir_path, seed_hashes, spec):
        marker_dst = Path(repo_dir_path) / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker_dst.parent.mkdir(parents=True, exist_ok=True)
        marker_src = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        shutil.copy2(marker_src, marker_dst)
        return ["docs/agent_loop/pilot/PILOT_MARKER.md"]

    def fake_profile(cfg, spec, repo_dir_path):
        return True, "ok"

    def fake_final_report(cfg, spec, issue_no, cycle, repo_dir_path, pr):
        return tmp / "final.json"

    return _patch_worker(
        gh_json=fake_gh_json,
        run=fake_run,
        prepare_repo=lambda cfg, spec, issue_no: repo_dir,
        prepare_model_workspace=fake_prepare,
        run_kimi=fake_run_kimi,
        audit_and_sync_model_workspace=fake_audit,
        run_profile=fake_profile,
        run_marker_content_check=lambda repo_dir_path, expected_front_id: (True, "ok"),
        changed_files=lambda repo_dir_path, base_sha: list(worker.PROFILE_ALLOWED_PATHS["pilot"]),
        path_allowed=lambda path, allowed, forbidden: path in worker.PROFILE_ALLOWED_PATHS["pilot"],
        marker_hash=lambda repo_dir_path: "markerhash",
        write_executor_report=lambda *a, **k: None,
        write_final_local_report=fake_final_report,
        create_pr=fake_create_pr,
        set_converged_phase=_terminal_set_phase,
        publish_terminal_notification=_terminal_notify,
    ), calls


def test_initial_attempt_ack_missing_then_success() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_initial_state(tmp)
        originals, calls = _initial_attempt_patches(tmp, pass_on_cycle=2)
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            kinds = [e["kind"] for e in events]
            assert state["cycles"] == 2
            assert state["status"] == "loop:ci"
            assert state["pr_number"] == 99
            assert "executor_failed" in kinds
            assert "pr_created" in kinds
            failed_events = [e for e in events if e["kind"] == "executor_failed"]
            assert len(failed_events) == 1
            assert failed_events[0]["issue"] == 19
            assert failed_events[0].get("pr") is None
            assert worker.validate_v157_event_chronology(events) == []
            assert calls == [(1, None), (2, worker._TASK_NOT_ACKNOWLEDGED_FEEDBACK)]
        finally:
            _restore(originals)


def test_initial_attempt_timeout_then_success() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_initial_state(tmp)
        originals, calls = _initial_attempt_patches(tmp, pass_on_cycle=2, failure_class="EXECUTOR_TIMEOUT")
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            failed = [e for e in events if e["kind"] == "executor_failed"]
            assert len(failed) == 1
            assert failed[0]["failure_class"] == "EXECUTOR_TIMEOUT"
            assert state["cycles"] == 2
            assert state["status"] == "loop:ci"
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            _restore(originals)


def test_initial_preexecution_failure_blocks_no_cycle() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_initial_state(tmp)
        originals, _calls = _initial_attempt_patches(tmp, preexecution=True)
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            kinds = [e["kind"] for e in events]
            assert state["cycles"] == 0
            assert state["status"] == "loop:blocked"
            assert "executor_preflight_failed" in kinds
            assert "executor_started" not in kinds
            assert "executor_failed" not in kinds
            assert "state_terminalized" in kinds
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            _restore(originals)


def test_initial_all_attempts_consumed_terminalizes() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_initial_state(tmp)
        originals, _calls = _initial_attempt_patches(tmp)
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            kinds = [e["kind"] for e in events]
            assert state["cycles"] == 3
            assert state["status"] == "loop:token-exhausted"
            assert kinds.count("executor_failed") == 3
            assert "local_gate_failed" in kinds
            assert "state_terminalized" in kinds
            assert "pr_created" not in kinds
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            _restore(originals)


def test_executor_completed_event_includes_issue_and_ack_source() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        log = tmp / "opencode.jsonl"
        log.write_text(
            json.dumps(_issue19_tool_event()) + "\n",
            encoding="utf-8",
        )
        worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        events = _events(tmp)
        completed = next(e for e in events if e["kind"] == "executor_completed")
        assert completed["issue"] == 19
        assert completed.get("pr") is None
        assert completed.get("ack_source") == "verified_artifact_tool"
        assert completed.get("tool_input_schema") == "state.input"


def test_executor_started_event_includes_issue() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = {
            "install_root": td,
            "opencode_model": "ollama-cloud/kimi-k2.7-code",
            "opencode_output_token_max": 4096,
            "opencode_timeout_seconds": 5,
        }
        model_dir = tmp / "model"
        model_dir.mkdir(parents=True)
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text("PILOT-V157-ACTIVATION-20260720-0255"), encoding="utf-8")
        (tmp / "reports").mkdir(parents=True, exist_ok=True)
        old_subprocess_run = worker.subprocess.run
        old_event = worker.event
        old_runtime = worker._RUNTIME_EXECUTABLES
        old_help = worker._OPENCODE_RUN_HELP
        old_discover = worker.discover_session_id
        worker._OPENCODE_RUN_HELP = "Options:\n  --model\n"
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        events: list[dict] = []
        worker.event = lambda _cfg, kind, **fields: events.append({"kind": kind, **fields})
        worker.discover_session_id = lambda _repo_dir, _title: "session-test"

        def fake_subprocess_run(args, **kwargs):
            return worker.subprocess.CompletedProcess(args, returncode=0, stdout=b"ok")

        worker.subprocess.run = fake_subprocess_run
        try:
            worker.run_kimi(cfg, _artifact_spec(), model_dir, 19, 1)
            started = next(e for e in events if e["kind"] == "executor_started")
            assert started["issue"] == 19
            assert started.get("pr") is None
        finally:
            worker.subprocess.run = old_subprocess_run
            worker.event = old_event
            worker.discover_session_id = old_discover
            worker._RUNTIME_EXECUTABLES = old_runtime
            worker._OPENCODE_RUN_HELP = old_help


def test_no_generic_issue_blocked_for_recoverable_attempt() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_initial_state(tmp)
        originals, _calls = _initial_attempt_patches(tmp, pass_on_cycle=2)
        generic_called = []
        old_terminalize = worker.terminalize_state_error
        def capture_terminalize(cfg, state_path_arg, exc):
            generic_called.append(exc)
        worker.terminalize_state_error = capture_terminalize
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            assert not generic_called, f"generic terminalize called with {generic_called}"
        finally:
            worker.terminalize_state_error = old_terminalize
            _restore(originals)


def _artifact_spec() -> dict:
    return _initial_front_spec()


def _issue19_tool_event(target: str = "docs/agent_loop/pilot/PILOT_MARKER.md", *, status: str = "completed", tool: str = "write", content: str = "REDACTED") -> dict:
    """Sanitized fixture matching the real OpenCode tool event schema observed in Issue #19."""
    return {
        "type": "tool_use",
        "part": {
            "id": "prt_test",
            "sessionID": "ses_test",
            "messageID": "msg_test",
            "type": "tool",
            "callID": "functions.write:0",
            "tool": tool,
            "state": {
                "status": status,
                "input": {
                    "filePath": target,
                    "content": content,
                },
            },
        },
    }


def _text_event(text: str) -> dict:
    return {"type": "text", "part": {"type": "text", "text": text}}


def _delivery_fixture(tmp: Path, *, seed: str = "old marker\n") -> tuple[dict, dict, Path, Path, str]:
    cfg = _cfg(str(tmp))
    spec = _artifact_spec()
    model_dir = tmp / "model"
    marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
    marker.parent.mkdir(parents=True)
    marker.write_text(seed, encoding="utf-8")
    return cfg, spec, model_dir, marker, worker.sha256_file(marker)


def _delivery_failure(tmp: Path, events: list[dict], expected: str) -> list[dict]:
    cfg, spec, model_dir, _marker, seed = _delivery_fixture(tmp)
    log = tmp / "opencode.jsonl"
    log.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    try:
        worker.validate_executor_delivery(cfg, spec, model_dir, log, 1, issue_no=21, seed_hash=seed)
    except worker.ExecutorAttemptConsumed as exc:
        assert exc.failure_class == expected
    else:
        raise AssertionError(f"expected {expected}")
    return _events(tmp)


def test_task_failed_is_not_success_ack() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        failure = worker.prompt_task_failure_sentinel(_artifact_spec()["front_id"], 1)
        events = _delivery_failure(tmp, [_text_event(failure)], "EXECUTOR_DECLARED_WRITE_FAILURE")
        completed = next(event for event in events if event["kind"] == "executor_completed")
        assert completed["task_acknowledged"] is False
        assert completed["ack_source"] == "declared_write_failure"


def test_sentinel_substring_is_not_ack() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sentinel = worker.prompt_task_sentinel(_artifact_spec()["front_id"], 1)
        events = _delivery_failure(tmp, [_text_event("prefix " + sentinel + " suffix")], "TASK_NOT_ACKNOWLEDGED")
        completed = next(event for event in events if event["kind"] == "executor_completed")
        assert completed["task_acknowledged"] is False


def test_success_sentinel_exact_line_accepted() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg, spec, model_dir, marker, seed = _delivery_fixture(tmp)
        marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
        log = tmp / "opencode.jsonl"
        log.write_text(json.dumps(_text_event(worker.prompt_task_sentinel(spec["front_id"], 1))) + "\n", encoding="utf-8")
        worker.validate_executor_delivery(cfg, spec, model_dir, log, 1, issue_no=21, seed_hash=seed)
        completed = next(event for event in _events(tmp) if event["kind"] == "executor_completed")
        assert completed["task_acknowledged"] is True
        assert completed["ack_source"] == "text_sentinel"


def test_no_write_tool_call_classified() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sentinel = worker.prompt_task_sentinel(_artifact_spec()["front_id"], 1)
        events = _delivery_failure(tmp, [_text_event(sentinel)], "NO_WRITE_TOOL_CALL")
        completed = next(event for event in events if event["kind"] == "executor_completed")
        assert completed["write_tool_events"] == 0


def test_failed_write_tool_classified() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sentinel = worker.prompt_task_sentinel(_artifact_spec()["front_id"], 1)
        events = _delivery_failure(tmp, [_issue19_tool_event(status="error"), _text_event(sentinel)], "WRITE_TOOL_FAILED")
        completed = next(event for event in events if event["kind"] == "executor_completed")
        assert completed["write_tool_failed"] == 1
        assert completed["write_tool_exact_targets"] == 1


def test_completed_write_without_change_classified() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sentinel = worker.prompt_task_sentinel(_artifact_spec()["front_id"], 1)
        events = _delivery_failure(tmp, [_issue19_tool_event(), _text_event(sentinel)], "WRITE_TOOL_NO_EFFECT")
        completed = next(event for event in events if event["kind"] == "executor_completed")
        assert completed["write_tool_completed"] == 1


def test_no_write_tool_call_feedback_present() -> None:
    assert worker._safe_feedback_for_failure("NO_WRITE_TOOL_CALL") == (
        "The prior attempt returned text without invoking the required write tool. Use the OpenCode write tool to create docs/agent_loop/pilot/PILOT_MARKER.md with the exact requested content. Do not emit the success acknowledgement until the write tool has completed."
    )


def _initial_write_retry_flow(tmp: Path, first_failure: str) -> tuple[dict, list[tuple[int, str | None, str | None]]]:
    state_path = _make_initial_state(tmp)
    originals, _calls = _initial_attempt_patches(tmp)
    calls: list[tuple[int, str | None, str | None]] = []

    def fake_run_kimi(cfg, spec, model_dir, issue_no, cycle, feedback=None, session_id=None):
        calls.append((cycle, feedback, session_id))
        log = tmp / f"cycle-{cycle}-opencode.jsonl"
        if cycle == 1:
            sentinel = (
                worker.prompt_task_failure_sentinel(spec["front_id"], cycle)
                if first_failure == "EXECUTOR_DECLARED_WRITE_FAILURE"
                else worker.prompt_task_sentinel(spec["front_id"], cycle)
            )
            log.write_text(json.dumps(_text_event(sentinel)) + "\n", encoding="utf-8")
            return log, "session-old"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
        log.write_text(
            json.dumps(_issue19_tool_event(content="REDACTED")) + "\n" +
            json.dumps(_text_event(worker.prompt_task_sentinel(spec["front_id"], cycle))) + "\n",
            encoding="utf-8",
        )
        return log, "session-new"

    original_run_kimi = worker.run_kimi
    worker.run_kimi = fake_run_kimi
    try:
        worker.execute_initial(_cfg(str(tmp)), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
        return worker.load_json(state_path), calls
    finally:
        worker.run_kimi = original_run_kimi
        _restore(originals)


def test_retry_clears_session() -> None:
    with tempfile.TemporaryDirectory() as td:
        state, calls = _initial_write_retry_flow(Path(td), "NO_WRITE_TOOL_CALL")
        assert calls[0][2] is None
        assert calls[1][2] is None
        assert calls[1][1] == worker._WRITE_FAILURE_FEEDBACK["NO_WRITE_TOOL_CALL"]
        assert state["status"] == "loop:ci"


def test_first_no_write_then_success() -> None:
    with tempfile.TemporaryDirectory() as td:
        state, calls = _initial_write_retry_flow(Path(td), "NO_WRITE_TOOL_CALL")
        assert state["cycles"] == 2
        assert state["pr_number"] == 99
        assert state["status"] == "loop:ci"
        assert len(calls) == 2


def test_failure_sentinel_then_success() -> None:
    with tempfile.TemporaryDirectory() as td:
        state, calls = _initial_write_retry_flow(Path(td), "EXECUTOR_DECLARED_WRITE_FAILURE")
        assert state["cycles"] == 2
        assert state["pr_number"] == 99
        assert calls[1][2] is None
        assert calls[1][1] == worker._WRITE_FAILURE_FEEDBACK["EXECUTOR_DECLARED_WRITE_FAILURE"]


def test_prompt_requires_write_tool() -> None:
    prompt = worker.make_prompt(_artifact_spec(), 1)
    required = (
        "Your first required action is to invoke the OpenCode write tool.",
        "A text-only response is a failed attempt.",
        "Do not output the success sentinel before the write tool reports completion.",
        "After the tool completes, verify the exact relative path and then output the success sentinel.",
    )
    assert all(text in prompt for text in required)
    assert worker.prompt_task_failure_sentinel(_artifact_spec()["front_id"], 1) in prompt


def test_write_failure_nondisclosure() -> None:
    canary = "SECRET_MODEL_STDOUT_CANARY_21"
    for failure_class in worker._WRITE_RETRY_FAILURE_CLASSES:
        feedback = worker._safe_feedback_for_failure(failure_class)
        assert feedback is not None
        assert canary not in feedback
        exc = worker.ExecutorAttemptConsumed(failure_class, canary, {})
        assert canary not in worker.safe_executor_error(exc)


def test_verified_artifact_tool_ack_passes_without_text_sentinel() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        log = tmp / "opencode.jsonl"
        log.write_text(
            json.dumps(_issue19_tool_event()) + "\n",
            encoding="utf-8",
        )
        worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        events = _events(tmp)
        completed = next(e for e in events if e["kind"] == "executor_completed")
        assert completed["task_acknowledged"] is True
        assert completed["ack_source"] == "verified_artifact_tool"
        assert completed["issue"] == 19
        assert completed.get("tool_input_schema") == "state.input"


def test_verified_artifact_tool_ack_requires_exact_marker() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text("wrong content", encoding="utf-8")
        log = tmp / "opencode.jsonl"
        log.write_text(
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "write", "state": {"status": "completed"}, "parameters": {"path": "docs/agent_loop/pilot/PILOT_MARKER.md"}}}) + "\n",
            encoding="utf-8",
        )
        try:
            worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        except worker.ExecutorAttemptConsumed as exc:
            assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED"
        else:
            raise AssertionError("expected failure")


def test_verified_artifact_tool_ack_requires_completed_write_tool() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        log = tmp / "opencode.jsonl"
        log.write_text(
            json.dumps(_issue19_tool_event(tool="read")) + "\n",
            encoding="utf-8",
        )
        try:
            worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        except worker.ExecutorAttemptConsumed as exc:
            assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED"
        else:
            raise AssertionError("expected failure")


def test_verified_artifact_tool_ack_rejects_unchanged_marker() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        seed = worker.sha256_file(marker)
        log = tmp / "opencode.jsonl"
        log.write_text(
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "write", "state": {"status": "completed"}, "parameters": {"path": "docs/agent_loop/pilot/PILOT_MARKER.md"}}}) + "\n",
            encoding="utf-8",
        )
        try:
            worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=seed)
        except worker.ExecutorAttemptConsumed as exc:
            assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED"
        else:
            raise AssertionError("expected failure")


def test_verified_artifact_tool_ack_rejects_extra_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        (model_dir / "extra.txt").write_text("extra", encoding="utf-8")
        log = tmp / "opencode.jsonl"
        log.write_text(
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "write", "state": {"status": "completed"}, "parameters": {"path": "docs/agent_loop/pilot/PILOT_MARKER.md"}}}) + "\n",
            encoding="utf-8",
        )
        try:
            worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        except worker.ExecutorAttemptConsumed as exc:
            assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED"
        else:
            raise AssertionError("expected failure")


def test_verified_artifact_tool_ack_rejects_session_error() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        log = tmp / "opencode.jsonl"
        log.write_text(
            json.dumps({"type": "error"}) + "\n" +
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "write", "state": {"status": "completed"}, "parameters": {"path": "docs/agent_loop/pilot/PILOT_MARKER.md"}}}) + "\n",
            encoding="utf-8",
        )
        try:
            worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        except worker.ExecutorAttemptConsumed as exc:
            assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED"
        else:
            raise AssertionError("expected failure")


def test_verified_artifact_tool_ack_rejects_conversational_refusal() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        log = tmp / "opencode.jsonl"
        log.write_text(
            json.dumps({"type": "text", "part": {"type": "text", "text": "Please provide the task or instruction set."}}) + "\n" +
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "write", "state": {"status": "completed"}, "parameters": {"path": "docs/agent_loop/pilot/PILOT_MARKER.md"}}}) + "\n",
            encoding="utf-8",
        )
        try:
            worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        except worker.ExecutorAttemptConsumed as exc:
            assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED"
        else:
            raise AssertionError("expected failure")


def test_marker_without_text_sentinel_still_rejected_when_no_tool() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        log = tmp / "opencode.jsonl"
        log.write_text("{}", encoding="utf-8")
        try:
            worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        except worker.ExecutorAttemptConsumed as exc:
            assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED"
        else:
            raise AssertionError("expected failure")


def test_initial_attempt_nondisclosure_canaries() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _make_initial_state(tmp)
        originals, _calls = _initial_attempt_patches(tmp)
        prompt_canary = "ULTRA_SECRET_PROMPT_CANARY_INITIAL_19"
        stdout_canary = "ULTRA_SECRET_STDOUT_CANARY_INITIAL_19"
        original_make_prompt = worker.make_prompt

        def canary_prompt(spec, cycle, feedback=None):
            return original_make_prompt(spec, cycle, feedback) + "\n" + prompt_canary

        def fake_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            log_path = tmp / f"cycle-{cycle}.jsonl"
            log_path.write_text(stdout_canary, encoding="utf-8")
            raise worker.ExecutorAttemptConsumed(
                "COMMAND_FAILED",
                "non-zero",
                {"cycle": cycle, "command_identity": "opencode", "local_log_path": str(log_path), "returncode": 1},
            )

        originals2 = _patch_worker(run_kimi=fake_run_kimi, make_prompt=canary_prompt)
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            all_surfaces = [json.dumps(state), json.dumps(events), str(state.get("error", ""))]
            for s in all_surfaces:
                assert prompt_canary not in s
                assert stdout_canary not in s
            for e in events:
                if e["kind"] == "executor_failed":
                    assert prompt_canary not in e.get("error", "")
                    assert stdout_canary not in e.get("error", "")
        finally:
            _restore(originals2)
            _restore(originals)


def _resume_state(tmp: Path, *, cycles: int = 1, repo_dir: Path | None = None, last_failure_class: str = "TASK_NOT_ACKNOWLEDGED") -> Path:
    spec = _initial_front_spec()
    state = {
        "issue_number": 19,
        "front": spec["front_id"],
        "spec": spec,
        "repo_dir": str(repo_dir or tmp / "runs" / "issue-19" / "repo"),
        "cycles": cycles,
        "status": "loop:executing",
        "updated_utc": worker.utc(),
        "state_schema_version": worker.STATE_SCHEMA_VERSION,
        "worker_version": worker.WORKER_VERSION,
        "last_failure_class": last_failure_class,
    }
    state_path = tmp / "state" / "issue-19.json"
    worker.save_json(state_path, state)
    return state_path


def test_real_issue19_tool_schema_accepted() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        log = tmp / "opencode.jsonl"
        log.write_text(
            json.dumps(_issue19_tool_event(target=str(marker.resolve()))) + "\n",
            encoding="utf-8",
        )
        worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        events = _events(tmp)
        completed = next(e for e in events if e["kind"] == "executor_completed")
        assert completed["ack_source"] == "verified_artifact_tool"
        assert completed.get("tool_input_schema") == "state.input"


def test_synthetic_parameters_only_rejected() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        log = tmp / "opencode.jsonl"
        synthetic = {"type": "tool_use", "part": {"type": "tool", "tool": "write", "state": {"status": "completed"}, "parameters": {"path": "docs/agent_loop/pilot/PILOT_MARKER.md"}}}
        log.write_text(json.dumps(synthetic) + "\n", encoding="utf-8")
        try:
            worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        except worker.ExecutorAttemptConsumed as exc:
            assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED"
        else:
            raise AssertionError("expected synthetic parameters-only fixture to fail")


def test_completed_state_required() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        for status in ("running", "pending", "error"):
            log = tmp / f"opencode-{status}.jsonl"
            log.write_text(json.dumps(_issue19_tool_event(status=status)) + "\n", encoding="utf-8")
            try:
                worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
            except worker.ExecutorAttemptConsumed as exc:
                assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED", status
            else:
                raise AssertionError(f"expected failure for status={status}")


def test_exact_target_required() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        bad_targets = [
            "docs/agent_loop/pilot/PILOT_MARKER.md.bak",
            "docs/agent_loop/../pilot/PILOT_MARKER.md",
            str((model_dir / "evil").resolve()),
            "docs/agent_loop/pilot/PILOT_MARKER.md_extra_text",
            ["docs/agent_loop/pilot/PILOT_MARKER.md"],
            {"path": "docs/agent_loop/pilot/PILOT_MARKER.md"},
        ]
        for target in bad_targets:
            log = tmp / f"opencode-{id(target)}.jsonl"
            log.write_text(json.dumps(_issue19_tool_event(target=str(target) if isinstance(target, str) else target)) + "\n", encoding="utf-8")
            try:
                worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
            except worker.ExecutorAttemptConsumed as exc:
                assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED", target
            else:
                raise AssertionError(f"expected failure for target={target!r}")


def test_real_tool_name_required() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        for tool in ("bash", "webfetch", "unknown_write"):
            log = tmp / f"opencode-{tool}.jsonl"
            log.write_text(json.dumps(_issue19_tool_event(tool=tool)) + "\n", encoding="utf-8")
            try:
                worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
            except worker.ExecutorAttemptConsumed as exc:
                assert exc.failure_class == "TASK_NOT_ACKNOWLEDGED", tool
            else:
                raise AssertionError(f"expected failure for tool={tool}")


def test_actual_log_structural_replay() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _cfg(td)
        front = "PILOT-V157-ACTIVATION-20260720-0255"
        model_dir = tmp / "model"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(front), encoding="utf-8")
        log = tmp / "opencode.jsonl"
        real_struct = {
            "type": "tool_use",
            "part": {
                "id": "prt_f7d8d4d6d0019Ic5qoIiTQSGB8",
                "sessionID": "ses_08272d956ffe4vYGnyq4gERQD1",
                "messageID": "msg_f7d8d450a001S7hikHfAD0nCZG",
                "type": "tool",
                "callID": "functions.write:2",
                "tool": "write",
                "state": {
                    "status": "completed",
                    "input": {
                        "filePath": "REDACTED_ABSOLUTE_PATH\\docs\\agent_loop\\pilot\\PILOT_MARKER.md",
                        "content": "REDACTED_MARKER_CONTENT",
                    }
                }
            }
        }
        log.write_text(json.dumps(real_struct) + "\n", encoding="utf-8")
        try:
            worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        except worker.ExecutorAttemptConsumed:
            pass
        events = _events(tmp)
        if events:
            assert all(e.get("tool_input_schema") != "parameters" for e in events if e["kind"] == "executor_completed")


def test_initial_restart_after_one_consumed_attempt() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _resume_state(tmp, cycles=1, repo_dir=repo_dir, last_failure_class="TASK_NOT_ACKNOWLEDGED")
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        originals, calls = _initial_attempt_patches(tmp, pass_on_cycle=2)
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["cycles"] == 2
            assert state["status"] == "loop:ci"
            assert calls == [(2, worker._TASK_NOT_ACKNOWLEDGED_FEEDBACK)]
        finally:
            _restore(originals)


def test_initial_restart_after_timeout() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _resume_state(tmp, cycles=1, repo_dir=repo_dir, last_failure_class="EXECUTOR_TIMEOUT")
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        originals, calls = _initial_attempt_patches(tmp, pass_on_cycle=2, failure_class="EXECUTOR_TIMEOUT")
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            assert state["cycles"] == 2
            assert calls == [(2, None)]
            for e in events:
                if e["kind"] == "executor_failed" and e["cycle"] == 1:
                    assert "timeout output" not in e.get("error", "").lower()
        finally:
            _restore(originals)


def test_initial_restart_at_max() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _resume_state(tmp, cycles=3, repo_dir=repo_dir, last_failure_class="TASK_NOT_ACKNOWLEDGED")
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[tuple[int, str | None]] = []
        originals = _patch_worker(
            run_kimi=lambda *a, **k: calls.append(a[4]) or (_ for _ in ()).throw(AssertionError("run_kimi must not be called at max cycles")),
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            assert state["cycles"] == 3
            assert state["status"] == "loop:token-exhausted"
            assert calls == []
            assert not any(e["kind"] == "executor_started" for e in events)
        finally:
            _restore(originals)


def test_initial_restart_workspace_missing() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _resume_state(tmp, cycles=1, repo_dir=tmp / "missing_repo", last_failure_class="TASK_NOT_ACKNOWLEDGED")
        st = worker.load_json(state_path)
        worker.save_json(state_path, st)
        originals = _patch_worker(
            terminalize_state_error=lambda *a, **k: None,
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["cycles"] == 1
            assert state["status"] == "loop:blocked"
            assert state.get("last_failure_class") == "INITIAL_RETRY_WORKSPACE_UNAVAILABLE"
        finally:
            _restore(originals)


def test_initial_restart_workspace_outside_runs() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        outside = Path(td).parent / "outside-repo"
        outside.mkdir(parents=True, exist_ok=True)
        state_path = _resume_state(tmp, cycles=1, repo_dir=outside, last_failure_class="TASK_NOT_ACKNOWLEDGED")
        st = worker.load_json(state_path)
        worker.save_json(state_path, st)
        originals = _patch_worker(
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["status"] == "loop:blocked"
            assert state.get("last_failure_class") == "INITIAL_RETRY_WORKSPACE_UNAVAILABLE"
        finally:
            _restore(originals)


def test_process_restart_accounting() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        st["spec"]["max_kimi_cycles"] = 2
        worker.save_json(state_path, st)
        calls: list[tuple[int, str | None]] = []

        def failing_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append((cycle, feedback))
            raise worker.ExecutorAttemptConsumed(
                "TASK_NOT_ACKNOWLEDGED",
                "ack missing",
                {"cycle": cycle, "command_identity": "opencode", "local_log_path": str(tmp / f"cycle-{cycle}.jsonl"), "returncode": None},
            )

        originals = _initial_attempt_patches(tmp)[0]
        originals2 = _patch_worker(run_kimi=failing_run_kimi)
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            assert calls == [(1, None), (2, worker._TASK_NOT_ACKNOWLEDGED_FEEDBACK)]
        finally:
            _restore(originals2)
            _restore(originals)


def test_crash_window_simulation() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        st["spec"]["max_kimi_cycles"] = 3
        worker.save_json(state_path, st)
        calls: list[int] = []

        class SimulatedProcessCrash(BaseException):
            pass

        def crash_after_checkpoint_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            if cycle <= 2:
                log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
                log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
                marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
                return log_path, "session-new"
            raise worker.ExecutorAttemptConsumed(
                "TASK_NOT_ACKNOWLEDGED",
                "ack missing",
                {"cycle": cycle, "command_identity": "opencode", "local_log_path": str(tmp / f"cycle-{cycle}.jsonl"), "returncode": None},
            )

        originals = _initial_attempt_patches(tmp)[0]
        real_audit = originals.get("audit_and_sync_model_workspace", worker.audit_and_sync_model_workspace)
        def audit_wrapper(*a, **k):
            result = real_audit(*a, **k)
            raise SimulatedProcessCrash("crash after delivery checkpoint")
        originals2 = _patch_worker(
            run_kimi=crash_after_checkpoint_run_kimi,
            audit_and_sync_model_workspace=audit_wrapper,
        )
        try:
            try:
                worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            except SimulatedProcessCrash:
                pass
            assert calls == [1]
            mid = worker.load_json(state_path)
            assert mid["cycles"] == 1
            assert mid["status"] == "loop:executing"
            assert mid.get("last_failure_class") == "EXECUTOR_DELIVERY_ACCEPTED_PENDING_LOCAL_GATES"
            try:
                worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            except SimulatedProcessCrash:
                pass
            assert calls == [1, 2]
        finally:
            _restore(originals2)
            _restore(originals)


def test_initial_delivery_checkpoint_before_audit() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[int] = []
        checkpoint = {}

        class SimulatedProcessCrash(BaseException):
            pass

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        real_audit = originals.get("audit_and_sync_model_workspace", worker.audit_and_sync_model_workspace)
        def capture_then_crash_audit(*a, **k):
            checkpoint["before_audit"] = dict(worker.load_json(state_path))
            real_audit(*a, **k)
            raise SimulatedProcessCrash("crash after delivery checkpoint")

        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            audit_and_sync_model_workspace=capture_then_crash_audit,
        )
        try:
            try:
                worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            except SimulatedProcessCrash:
                pass
        finally:
            _restore(originals2)
            _restore(originals)
        before = checkpoint["before_audit"]
        assert before["cycles"] == 1
        assert before["status"] == "loop:executing"
        assert before.get("last_failure_class") == "EXECUTOR_DELIVERY_ACCEPTED_PENDING_LOCAL_GATES"


def test_restart_after_audit_failure() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[int] = []
        attempt = 0

        def pass_delivery_then_fail_audit_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            return log_path, "session-new"

        class SimulatedProcessCrash(BaseException):
            pass

        class SimulatedProcessCrash(BaseException):
            pass

        originals = _initial_attempt_patches(tmp)[0]
        originals2 = _patch_worker(
            run_kimi=pass_delivery_then_fail_audit_run_kimi,
            audit_and_sync_model_workspace=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("audit fail cycle 1")),
            _checkpoint_initial_cycle=_crash_after_nth_checkpoint("INITIAL_WORKSPACE_AUDIT_FAILED", SimulatedProcessCrash, 1),
        )
        try:
            try:
                worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            except SimulatedProcessCrash:
                pass
            state = worker.load_json(state_path)
            assert state["cycles"] == 1
            assert state.get("last_failure_class") == "INITIAL_WORKSPACE_AUDIT_FAILED"

            real_audit = originals.get("audit_and_sync_model_workspace", worker.audit_and_sync_model_workspace)
            def audit_succeed_once_then_crash(*a, **k):
                real_audit(*a, **k)
                raise SimulatedProcessCrash("crash after audit success on cycle 2")
            originals3 = _patch_worker(
                run_kimi=pass_delivery_then_fail_audit_run_kimi,
                audit_and_sync_model_workspace=audit_succeed_once_then_crash,
            )
            try:
                try:
                    worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
                except SimulatedProcessCrash:
                    pass
                assert calls == [1, 2]
            finally:
                _restore(originals3)
        finally:
            _restore(originals2)
            _restore(originals)


def test_restart_after_local_test_failure() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[int] = []

        class SimulatedProcessCrash(BaseException):
            pass

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            run_profile=lambda *a, **k: (False, "profile failure no prompt canary"),
            _checkpoint_initial_cycle=_crash_after_nth_checkpoint("INITIAL_LOCAL_GATE_FAILED", SimulatedProcessCrash, 1),
        )
        try:
            try:
                worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            except SimulatedProcessCrash:
                pass
            state = worker.load_json(state_path)
            assert state["cycles"] == 1
            assert state.get("last_failure_class") == "INITIAL_LOCAL_GATE_FAILED"

            originals3 = _patch_worker(
                run_kimi=pass_delivery_run_kimi,
                run_profile=lambda *a, **k: (_ for _ in ()).throw(SimulatedProcessCrash("crash after profile success on cycle 2")),
            )
            try:
                try:
                    worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
                except SimulatedProcessCrash:
                    pass
                assert calls == [1, 2]
            finally:
                _restore(originals3)
        finally:
            _restore(originals2)
            _restore(originals)


def test_out_of_scope_path_blocks_after_consumed_cycle() -> None:
    """An out-of-scope path detected after delivery consumes the cycle and blocks the issue."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[int] = []

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            # The executor writes an additional file into the model workspace. The
            # patched audit copies it into the governed repo_dir, so the real
            # changed_files() and path_allowed() detect an out-of-scope path.
            (model_dir_arg / "evil.txt").write_text("out-of-scope", encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        # Audit is patched to sync every model file, not just the allowlisted marker,
        # so evil.txt reaches repo_dir and the real gate sees it.
        real_audit = originals.get("audit_and_sync_model_workspace", worker.audit_and_sync_model_workspace)
        def permissive_audit(model_dir_arg, repo_dir_path, seed_hashes, spec):
            for src in model_dir_arg.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(model_dir_arg).as_posix()
                    dst = Path(repo_dir_path) / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            return ["docs/agent_loop/pilot/PILOT_MARKER.md"]

        # Recover the real changed_files/path_allowed/run that _initial_attempt_patches
        # replaced, so the gate observes the actual filesystem state including evil.txt.
        real_changed_files = originals["changed_files"]
        real_path_allowed = originals["path_allowed"]
        real_run = originals["run"]
        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            run=real_run,
            audit_and_sync_model_workspace=permissive_audit,
            changed_files=real_changed_files,
            path_allowed=real_path_allowed,
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["cycles"] == 1
            assert state["status"] == "loop:blocked"
            assert state.get("last_failure_class") == "INITIAL_OUT_OF_SCOPE_PATHS"
            assert calls == [1]
            events = _events(tmp)
            kinds = [e["kind"] for e in events]
            assert "local_gate_failed" in kinds
            assert "state_terminalized" in kinds
            assert "pr_created" not in kinds
            assert "kimi_cycle_start" in kinds
            assert worker.validate_v157_event_chronology(events) == []
            assert state.get("error") == "Out-of-scope changes were detected in the governed workspace. Human audit is required."
            assert "evil.txt" not in json.dumps(state)
        finally:
            _restore(originals2)
            _restore(originals)


def test_out_of_scope_block_survives_process_restart() -> None:
    """A blocked out-of-scope state must not resume or duplicate events/notifications."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[int] = []

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            (model_dir_arg / "evil.txt").write_text("out-of-scope", encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        real_audit = originals.get("audit_and_sync_model_workspace", worker.audit_and_sync_model_workspace)
        def permissive_audit(model_dir_arg, repo_dir_path, seed_hashes, spec):
            for src in model_dir_arg.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(model_dir_arg).as_posix()
                    dst = Path(repo_dir_path) / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            return ["docs/agent_loop/pilot/PILOT_MARKER.md"]

        real_changed_files = originals["changed_files"]
        real_path_allowed = originals["path_allowed"]
        real_run = originals["run"]
        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            run=real_run,
            audit_and_sync_model_workspace=permissive_audit,
            changed_files=real_changed_files,
            path_allowed=real_path_allowed,
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["status"] == "loop:blocked"
            assert state.get("last_failure_class") == "INITIAL_OUT_OF_SCOPE_PATHS"
            assert calls == [1]
            first_event_count = len(_events(tmp))

            # A real second process would call process_state(), which checks
            # state_is_terminal() and returns immediately without re-entering
            # execute_initial() or emitting duplicate events.
            worker.process_state(_cfg(td), state_path)
            state = worker.load_json(state_path)
            assert state["status"] == "loop:blocked"
            assert state["cycles"] == 1
            assert calls == [1]  # no second Kimi call
            assert len(_events(tmp)) == first_event_count  # no duplicated terminal events
        finally:
            _restore(originals2)
            _restore(originals)


def test_out_of_scope_skips_run_profile() -> None:
    """An out-of-scope path must block before run_profile is called."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[int] = []
        profile_calls: list[str] = []

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        real_changed_files = originals["changed_files"]
        real_run = originals["run"]

        def changed_files_with_evil(repo_dir_path, base_sha):
            real_changes = real_changed_files(repo_dir_path, base_sha)
            if "evil.txt" not in real_changes:
                (Path(repo_dir_path) / "evil.txt").write_text("out-of-scope", encoding="utf-8")
                real_changes = real_changed_files(repo_dir_path, base_sha)
            return real_changes

        def run_profile_that_must_not_be_called(cfg, spec, repo_dir_path):
            profile_calls.append(str(repo_dir_path))
            raise AssertionError("run_profile must not be called when bad paths exist")

        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            run=real_run,
            changed_files=changed_files_with_evil,
            path_allowed=originals["path_allowed"],
            run_profile=run_profile_that_must_not_be_called,
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["status"] == "loop:blocked"
            assert state.get("last_failure_class") == "INITIAL_OUT_OF_SCOPE_PATHS"
            assert state["cycles"] == 1
            assert calls == [1]
            assert profile_calls == []
        finally:
            _restore(originals2)
            _restore(originals)


def test_model_extra_file_blocks() -> None:
    """An extra file in the model workspace triggers scope violation, not a retry."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[int] = []
        profile_calls: list[str] = []

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            (model_dir_arg / "evil.txt").write_text("out-of-scope", encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        real_run = originals["run"]
        real_changed_files = originals["changed_files"]
        real_prepare = originals["prepare_model_workspace"]
        real_audit = originals["audit_and_sync_model_workspace"]
        real_path_allowed = originals["path_allowed"]

        def run_profile_that_must_not_be_called(cfg, spec, repo_dir_path):
            profile_calls.append(str(repo_dir_path))
            raise AssertionError("run_profile must not be called on model scope violation")

        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            run=real_run,
            prepare_model_workspace=real_prepare,
            changed_files=real_changed_files,
            path_allowed=real_path_allowed,
            audit_and_sync_model_workspace=real_audit,
            run_profile=run_profile_that_must_not_be_called,
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["status"] == "loop:blocked"
            assert state.get("last_failure_class") == "INITIAL_OUT_OF_SCOPE_PATHS"
            assert state["cycles"] == 1
            assert calls == [1]
            assert profile_calls == []
            events = _events(tmp)
            gate_event = next(e for e in events if e["kind"] == "local_gate_failed")
            assert gate_event.get("scope_reason") == "MODEL_WORKSPACE_EXTRA_PATHS"
            assert gate_event.get("bad_count") == 1
        finally:
            _restore(originals2)
            _restore(originals)


def test_model_git_metadata_blocks() -> None:
    """A .git directory inside the model workspace is a scope violation."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[int] = []
        profile_calls: list[str] = []

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            (model_dir_arg / ".git").mkdir(parents=True, exist_ok=True)
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        real_run = originals["run"]
        real_changed_files = originals["changed_files"]
        real_prepare = originals["prepare_model_workspace"]
        real_audit = originals["audit_and_sync_model_workspace"]
        real_path_allowed = originals["path_allowed"]

        def run_profile_that_must_not_be_called(cfg, spec, repo_dir_path):
            profile_calls.append(str(repo_dir_path))
            raise AssertionError("run_profile must not be called on model scope violation")

        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            run=real_run,
            prepare_model_workspace=real_prepare,
            changed_files=real_changed_files,
            path_allowed=real_path_allowed,
            audit_and_sync_model_workspace=real_audit,
            run_profile=run_profile_that_must_not_be_called,
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["status"] == "loop:blocked"
            assert state.get("last_failure_class") == "INITIAL_OUT_OF_SCOPE_PATHS"
            assert state["cycles"] == 1
            assert calls == [1]
            assert profile_calls == []
        finally:
            _restore(originals2)
            _restore(originals)


def test_seed_modification_blocks() -> None:
    """Modification of a seeded allowlisted file is a scope violation."""

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        # Seed a protected file so MODEL_SEED_PATHS is non-empty.
        seed_file = repo_dir / "docs" / "agent_loop" / "pilot" / "SEED.md"
        seed_file.parent.mkdir(parents=True, exist_ok=True)
        seed_file.write_text("seed", encoding="utf-8")
        worker.run(["git", "add", "-A"], cwd=str(repo_dir), check=True)
        worker.run(["git", "commit", "-m", "seed"], cwd=str(repo_dir), check=True)
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[int] = []
        profile_calls: list[str] = []

        # Temporarily add the seeded path to MODEL_SEED_PATHS.
        old_model_seed_paths = set(worker.MODEL_SEED_PATHS)
        worker.MODEL_SEED_PATHS.add("docs/agent_loop/pilot/SEED.md")

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            seed_dst = model_dir_arg / "docs" / "agent_loop" / "pilot" / "SEED.md"
            seed_dst.parent.mkdir(parents=True, exist_ok=True)
            seed_dst.write_text("modified", encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        real_run = originals["run"]
        real_changed_files = originals["changed_files"]
        real_prepare = originals["prepare_model_workspace"]
        real_audit = originals["audit_and_sync_model_workspace"]
        real_path_allowed = originals["path_allowed"]

        def run_profile_that_must_not_be_called(cfg, spec, repo_dir_path):
            profile_calls.append(str(repo_dir_path))
            raise AssertionError("run_profile must not be called on model scope violation")

        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            run=real_run,
            prepare_model_workspace=real_prepare,
            changed_files=real_changed_files,
            path_allowed=real_path_allowed,
            audit_and_sync_model_workspace=real_audit,
            run_profile=run_profile_that_must_not_be_called,
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["status"] == "loop:blocked"
            assert state.get("last_failure_class") == "INITIAL_OUT_OF_SCOPE_PATHS"
            assert state["cycles"] == 1
            assert calls == [1]
            assert profile_calls == []
        finally:
            _restore(originals2)
            _restore(originals)
            worker.MODEL_SEED_PATHS.clear()
            worker.MODEL_SEED_PATHS.update(old_model_seed_paths)


def test_marker_mismatch_remains_recoverable() -> None:
    """An allowlisted marker with wrong content is recoverable within the cycle budget.

    A marker content mismatch is treated as a recoverable workspace audit failure,
    not a permanent out-of-scope block. The worker retries, but if every attempt
    produces the wrong marker the budget is exhausted and the issue terminalizes as
    token-exhausted rather than blocked.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        st["spec"]["max_kimi_cycles"] = 3
        worker.save_json(state_path, st)
        calls: list[int] = []

        def wrong_marker_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("wrong", encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        real_run = originals["run"]
        real_changed_files = originals["changed_files"]
        real_prepare = originals["prepare_model_workspace"]
        real_audit = originals["audit_and_sync_model_workspace"]
        real_path_allowed = originals["path_allowed"]

        originals2 = _patch_worker(
            run_kimi=wrong_marker_run_kimi,
            run=real_run,
            prepare_model_workspace=real_prepare,
            changed_files=real_changed_files,
            path_allowed=real_path_allowed,
            audit_and_sync_model_workspace=real_audit,
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["status"] == "loop:token-exhausted"
            assert state.get("last_failure_class") == "INITIAL_WORKSPACE_AUDIT_FAILED"
            assert state["cycles"] == 3
            assert calls == [1, 2, 3]
            events = _events(tmp)
            assert all(e.get("failure_class") != "INITIAL_OUT_OF_SCOPE_PATHS" for e in events)
            assert worker.validate_v157_event_chronology(events) == []
        finally:
            _restore(originals2)
            _restore(originals)


def test_repo_bad_defense_in_depth() -> None:
    """Even if audit passes, a bad path introduced into repo_dir blocks before profile."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        calls: list[int] = []
        profile_calls: list[str] = []

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append(cycle)
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        real_run = originals["run"]
        real_changed_files = originals["changed_files"]
        real_path_allowed = originals["path_allowed"]

        # Audit copies marker only; after audit we inject evil.txt directly into repo_dir.
        def marker_only_audit_then_inject_evil(model_dir_arg, repo_dir_path, seed_hashes, spec):
            marker_dst = Path(repo_dir_path) / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker_dst.parent.mkdir(parents=True, exist_ok=True)
            marker_src = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            shutil.copy2(marker_src, marker_dst)
            (Path(repo_dir_path) / "evil.txt").write_text("out-of-scope", encoding="utf-8")
            return ["docs/agent_loop/pilot/PILOT_MARKER.md"]

        def run_profile_that_must_not_be_called(cfg, spec, repo_dir_path):
            profile_calls.append(str(repo_dir_path))
            raise AssertionError("run_profile must not be called when bad repo paths exist")

        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            run=real_run,
            changed_files=real_changed_files,
            path_allowed=real_path_allowed,
            audit_and_sync_model_workspace=marker_only_audit_then_inject_evil,
            run_profile=run_profile_that_must_not_be_called,
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["status"] == "loop:blocked"
            assert state.get("last_failure_class") == "INITIAL_OUT_OF_SCOPE_PATHS"
            assert state["cycles"] == 1
            assert calls == [1]
            assert profile_calls == []
        finally:
            _restore(originals2)
            _restore(originals)


def test_scope_violation_nondisclosure() -> None:
    """Out-of-scope path names and contents must not leak into state or events."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        canary_name = "EVIL_SECRET_PATH_4711"
        canary_content = "EVIL_SECRET_CONTENT_4711"

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            (model_dir_arg / canary_name).write_text(canary_content, encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        real_run = originals["run"]
        real_changed_files = originals["changed_files"]
        real_prepare = originals["prepare_model_workspace"]
        real_audit = originals["audit_and_sync_model_workspace"]
        real_path_allowed = originals["path_allowed"]

        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            run=real_run,
            prepare_model_workspace=real_prepare,
            changed_files=real_changed_files,
            path_allowed=real_path_allowed,
            audit_and_sync_model_workspace=real_audit,
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            events = _events(tmp)
            dumped = json.dumps(state) + json.dumps(events)
            assert canary_name not in dumped
            assert canary_content not in dumped
        finally:
            _restore(originals2)
            _restore(originals)


def test_mixed_ack_then_timeout_feedback() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        st["spec"]["max_kimi_cycles"] = 3
        worker.save_json(state_path, st)
        calls: list[tuple[int, str | None]] = []

        def mixed_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            calls.append((cycle, feedback))
            if cycle == 1:
                raise worker.ExecutorAttemptConsumed(
                    "TASK_NOT_ACKNOWLEDGED",
                    "ack missing",
                    {"cycle": cycle, "command_identity": "opencode", "local_log_path": str(tmp / f"cycle-{cycle}.jsonl"), "returncode": None},
                )
            if cycle == 2:
                raise worker.ExecutorAttemptConsumed(
                    "EXECUTOR_TIMEOUT",
                    "timeout",
                    {"cycle": cycle, "command_identity": "opencode", "local_log_path": str(tmp / f"cycle-{cycle}.jsonl"), "returncode": None},
                )
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            return log_path, "session-new"

        originals = _initial_attempt_patches(tmp)[0]
        originals2 = _patch_worker(run_kimi=mixed_run_kimi)
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            assert calls == [(1, None), (2, worker._TASK_NOT_ACKNOWLEDGED_FEEDBACK), (3, None)]
        finally:
            _restore(originals2)
            _restore(originals)


def test_max_cycles_with_missing_workspace() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state_path = _resume_state(tmp, cycles=3, repo_dir=tmp / "missing_repo", last_failure_class="TASK_NOT_ACKNOWLEDGED")
        st = worker.load_json(state_path)
        worker.save_json(state_path, st)
        originals = _patch_worker(
            set_phase=lambda repo, number, phase: None,
            set_converged_phase=_terminal_set_phase,
            publish_terminal_notification=_terminal_notify,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
            state = worker.load_json(state_path)
            assert state["cycles"] == 3
            assert state["status"] == "loop:token-exhausted"
            assert state.get("last_failure_class") != "INITIAL_RETRY_WORKSPACE_UNAVAILABLE"
        finally:
            _restore(originals)


def test_audit_and_gate_output_nondisclosure() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = tmp / "runs" / "issue-19" / "repo"
        _setup_git_repo(repo_dir)
        base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
        state_path = _make_initial_state(tmp)
        st = worker.load_json(state_path)
        st["spec"]["expected_base_sha"] = base_sha
        worker.save_json(state_path, st)
        canary = "profile failure no prompt canary"

        def pass_delivery_run_kimi(cfg, spec, model_dir_arg, issue_no, cycle, feedback=None, session_id=None):
            log_path = tmp / f"cycle-{cycle}-opencode.jsonl"
            log_path.write_text(json.dumps({"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(spec["front_id"], cycle)}}) + "\n", encoding="utf-8")
            marker = model_dir_arg / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(worker.pilot_marker_text(spec["front_id"]), encoding="utf-8")
            return log_path, "session-new"

        def leaky_profile(cfg, spec, repo_dir_path):
            return False, canary

        originals = _initial_attempt_patches(tmp)[0]
        originals2 = _patch_worker(
            run_kimi=pass_delivery_run_kimi,
            run_profile=leaky_profile,
            set_phase=lambda repo, number, phase: None,
        )
        try:
            worker.execute_initial(_cfg(td), {"number": 19}, worker.load_json(state_path)["spec"], state_path)
        finally:
            _restore(originals2)
            _restore(originals)
        state = worker.load_json(state_path)
        events = _events(tmp)
        assert canary not in json.dumps(state)
        assert canary not in json.dumps(events)


def test_git_template_isolation() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        repo_a = root / "repo-a"
        repo_b = root / "repo-b"
        base_a = _setup_git_repo(repo_a)
        base_b = _setup_git_repo(repo_b)
        assert base_a == base_b
        assert (repo_a / ".git").resolve() != (repo_b / ".git").resolve()
        assert worker.run(["git", "config", "user.name"], cwd=str(repo_a)).strip() == "Test"
        assert worker.run(["git", "config", "user.email"], cwd=str(repo_b)).strip() == "test@example.com"

        unique = repo_a / "a-only.txt"
        unique.write_text("isolated", encoding="utf-8")
        worker.run(["git", "add", "a-only.txt"], cwd=str(repo_a))
        worker.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-q", "-m", "repo-a-only"],
            cwd=str(repo_a),
        )

        assert worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_a)).strip() != base_a
        assert worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_b)).strip() == base_b
        assert not (repo_b / unique.name).exists()


def test_model_reparse_point_blocked() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        blocked = root / "blocked.txt"
        blocked.write_text("blocked", encoding="utf-8")
        originals = _patch_worker(_is_reparse_or_symlink=lambda path: path == blocked)
        try:
            try:
                worker._walk_workspace_files(root)
                raise AssertionError("model reparse point must be blocked")
            except worker.ModelWorkspaceScopeViolation as exc:
                assert exc.reason_code == "MODEL_WORKSPACE_LINK_DENIED"
        finally:
            _restore(originals)


def test_trusted_output_parent_reparse_blocked() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        model_dir = root / "model"
        repo_dir = root / "repo"
        marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")
        repo_dir.mkdir()
        blocked_parent = repo_dir / "docs"
        originals = _patch_worker(_is_reparse_or_symlink=lambda path: path == blocked_parent)
        try:
            try:
                worker.audit_and_sync_model_workspace(model_dir, repo_dir, {}, {"front_id": FRONT})
                raise AssertionError("trusted output parent reparse point must be blocked")
            except worker.ModelWorkspaceScopeViolation as exc:
                assert exc.reason_code == "TRUSTED_OUTPUT_PARENT_LINK_DENIED"
        finally:
            _restore(originals)


def test_trusted_output_destination_reparse_blocked() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        model_dir = root / "model"
        repo_dir = root / "repo"
        marker_rel = Path("docs/agent_loop/pilot/PILOT_MARKER.md")
        marker = model_dir / marker_rel
        marker.parent.mkdir(parents=True)
        marker.write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")
        repo_dir.mkdir()
        blocked_destination = repo_dir / marker_rel
        originals = _patch_worker(_is_reparse_or_symlink=lambda path: path == blocked_destination)
        try:
            try:
                worker.audit_and_sync_model_workspace(model_dir, repo_dir, {}, {"front_id": FRONT})
                raise AssertionError("trusted output destination reparse point must be blocked")
            except worker.ModelWorkspaceScopeViolation as exc:
                assert exc.reason_code == "TRUSTED_OUTPUT_LINK_DENIED"
        finally:
            _restore(originals)


def test_lstat_error_fails_closed() -> None:
    class FakePath:
        def is_symlink(self) -> bool:
            return False

        def __str__(self) -> str:
            return "unreadable-path"

    original_lstat = worker.os.lstat
    worker.os.lstat = lambda _path: (_ for _ in ()).throw(PermissionError("denied"))
    try:
        assert worker._is_reparse_or_symlink(FakePath())
    finally:
        worker.os.lstat = original_lstat


def test_normal_file_not_reparse() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "normal.txt"
        path.write_text("normal", encoding="utf-8")
        assert not worker._is_reparse_or_symlink(path)


def test_r1_ready_human_audit_poll_converges_without_executor() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        repo = root / "repo"
        repo.mkdir()
        roadmap_spec = _base_spec()
        roadmap_spec.update({
            "front_id": "BRAIN-101-R1.1-ASYNC-POLL",
            "roadmap_id": "BRAIN-101",
            "roadmap_version": "1.0.0-reconstructed-glm-harmonized",
            "roadmap_sha256": "c" * 64,
            "roadmap_item_id": "R1.1",
            "dependencies": ["R0"],
            "human_final_authority": True,
        })
        binding = {
            "schema_version": 1,
            "repository": "cesarmanuel8102/AI_Vault",
            "integration_branch": "codex/own-capital-sustainable-return",
            "approval_status": "HUMAN_ADOPTED",
            "r0_status": "CLOSED_HUMAN_ADOPTED",
            "roadmap_id": roadmap_spec["roadmap_id"],
            "roadmap_version": roadmap_spec["roadmap_version"],
            "roadmap_item_id": roadmap_spec["roadmap_item_id"],
            "roadmap_item_status": "AUTHORIZED_ACTIVE",
            "manifest_path": worker.ROADMAP_MANIFEST_PATH,
            "manifest_sha256": "d" * 64,
            "roadmap_path": "docs/roadmap/BRAIN_101_ROADMAP.md",
            "roadmap_sha256": roadmap_spec["roadmap_sha256"],
            "base_sha": roadmap_spec["expected_base_sha"],
            "dependencies": ["R0"],
        }
        state_path = root / "state" / "issue-101.json"
        original_state = {
            "issue_number": 101,
            "front": roadmap_spec["front_id"],
            "spec": roadmap_spec,
            "roadmap_binding": binding,
            "repo_dir": str(repo),
            "pr_number": 39,
            "pr_url": "https://example.invalid/pr/39",
            "cycles": 1,
            "last_head_sha": HEAD,
            "status": "loop:ci",
            "state_schema_version": worker.STATE_SCHEMA_VERSION,
            "worker_version": worker.WORKER_VERSION,
            "updated_utc": worker.utc(),
        }
        worker.save_json(state_path, original_state)
        convergence = []

        def fake_gh(args):
            assert args[:2] == ["pr", "view"]
            return {
                "number": 39, "url": "https://example.invalid/pr/39", "headRefOid": HEAD,
                "labels": [{"name": "loop:ready-human-audit"}], "state": "OPEN",
            }

        def converge(_cfg, path, current, phase, *, pr_number=None):
            convergence.append((phase, pr_number))
            current = dict(current)
            current["status"] = phase
            worker.save_json(path, current)
            return current

        def forbidden(*_a, **_k):
            raise AssertionError("executor must not run during async convergence poll")

        originals = _patch_worker(
            gh_json=fake_gh,
            set_converged_phase=converge,
            execute_initial=forbidden,
            run_kimi=forbidden,
        )
        try:
            worker.process_state(_cfg(td), state_path)
        finally:
            _restore(originals)

        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert convergence == [("loop:ready-human-audit", 39)]
        assert saved["status"] == "loop:ready-human-audit"
        assert saved["cycles"] == 1
        assert saved["last_head_sha"] == HEAD
        assert saved["roadmap_binding"] == binding


def main() -> int:
    tests = [
        test_state_schema_version_injected,
        test_terminalize_state_error_generates_schema_valid_state,
        test_state_validation_rejects_unknown_and_missing,
        test_event_contract_enforces_required_fields_and_worker_version,
        test_event_contract_rejects_sensitive_fields,
        test_worker_started_event_contract,
        test_legacy_repair_local_gate_aliases_to_local_gate_failed,
        test_event_chronology_rejects_impossible_sequence,
        test_event_chronology_rejects_pushed_without_committed,
        test_event_chronology_rejects_pushed_before_committed,
        test_event_chronology_rejects_committed_pushed_after_terminalized,
        test_event_chronology_rejects_executor_started_after_terminalized,
        test_event_chronology_rejects_reverted_without_committed,
        test_event_chronology_rejects_preflight_then_executor_started,
        test_event_chronology_rejects_post_preflight_actions,
        test_event_chronology_preflight_other_issue_does_not_validate_terminalization,
        test_event_chronology_preflight_same_issue_validates_terminalization,
        test_event_chronology_local_gate_same_issue_validates_terminalization,
        test_event_chronology_multi_front_isolation,
        test_command_string_fallback_blocks_without_executor_started,
        test_cmd_exe_fallback_blocks_without_executor_started,
        test_missing_node_exe_blocks_without_executor_started,
        test_missing_entrypoint_blocks_without_executor_started,
        test_prompt_missing_sentinel_blocks_without_executor_started,
        test_preflight_blocked_state_does_not_retry_kimi,
        test_timeout_consumes_attempt_and_preserves_local_log_path,
        test_token_exhausted_output_canary_not_leaked,
        test_command_failed_output_canary_not_leaked,
        test_prompt_canary_not_leaked_anywhere,
        test_timeout_traceback_does_not_leak_prompt_or_stdout_canary,
        test_timeout_via_process_state_consumes_exactly_one_cycle,
        test_final_cycle_audit_failure_terminalizes_same_run,
        test_final_cycle_marker_failure_terminalizes_same_run,
        test_final_cycle_out_of_scope_terminalizes_same_run,
        test_final_cycle_final_verifier_failure_terminalizes_without_push,
        test_executor_attempt_consumed_non_final_saves_state,
        test_executor_attempt_consumed_final_terminalizes,
        test_prompt_canary_absent_from_exception_and_log,
        test_initial_attempt_ack_missing_then_success,
        test_initial_attempt_timeout_then_success,
        test_initial_preexecution_failure_blocks_no_cycle,
        test_initial_all_attempts_consumed_terminalizes,
        test_executor_completed_event_includes_issue_and_ack_source,
        test_executor_started_event_includes_issue,
        test_no_generic_issue_blocked_for_recoverable_attempt,
        test_task_failed_is_not_success_ack,
        test_sentinel_substring_is_not_ack,
        test_success_sentinel_exact_line_accepted,
        test_no_write_tool_call_classified,
        test_failed_write_tool_classified,
        test_completed_write_without_change_classified,
        test_no_write_tool_call_feedback_present,
        test_retry_clears_session,
        test_first_no_write_then_success,
        test_failure_sentinel_then_success,
        test_prompt_requires_write_tool,
        test_write_failure_nondisclosure,
        test_verified_artifact_tool_ack_passes_without_text_sentinel,
        test_verified_artifact_tool_ack_requires_exact_marker,
        test_verified_artifact_tool_ack_requires_completed_write_tool,
        test_verified_artifact_tool_ack_rejects_unchanged_marker,
        test_verified_artifact_tool_ack_rejects_extra_file,
        test_verified_artifact_tool_ack_rejects_session_error,
        test_verified_artifact_tool_ack_rejects_conversational_refusal,
        test_marker_without_text_sentinel_still_rejected_when_no_tool,
        test_initial_attempt_nondisclosure_canaries,
        test_real_issue19_tool_schema_accepted,
        test_synthetic_parameters_only_rejected,
        test_completed_state_required,
        test_exact_target_required,
        test_real_tool_name_required,
        test_actual_log_structural_replay,
        test_initial_restart_after_one_consumed_attempt,
        test_initial_restart_after_timeout,
        test_initial_restart_at_max,
        test_initial_restart_workspace_missing,
        test_initial_restart_workspace_outside_runs,
        test_process_restart_accounting,
        test_crash_window_simulation,
        test_initial_delivery_checkpoint_before_audit,
        test_restart_after_audit_failure,
        test_restart_after_local_test_failure,
        test_out_of_scope_path_blocks_after_consumed_cycle,
        test_out_of_scope_block_survives_process_restart,
        test_out_of_scope_skips_run_profile,
        test_model_extra_file_blocks,
        test_model_git_metadata_blocks,
        test_seed_modification_blocks,
        test_marker_mismatch_remains_recoverable,
        test_repo_bad_defense_in_depth,
        test_scope_violation_nondisclosure,
        test_mixed_ack_then_timeout_feedback,
        test_max_cycles_with_missing_workspace,
        test_audit_and_gate_output_nondisclosure,
        test_git_template_isolation,
        test_model_reparse_point_blocked,
        test_trusted_output_parent_reparse_blocked,
        test_trusted_output_destination_reparse_blocked,
        test_lstat_error_fails_closed,
        test_normal_file_not_reparse,
        test_r1_ready_human_audit_poll_converges_without_executor,
    ]

    failed = 0
    for test in tests:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"FAIL: {test.__name__}: {type(exc).__name__}: {exc}")
    if failed == 0:
        print(f"PASS: {len(tests)} state/event contracts")
    print(json.dumps({"status": "PASS" if failed == 0 else "FAIL", "passed": len(tests) - failed, "failed": failed}, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
