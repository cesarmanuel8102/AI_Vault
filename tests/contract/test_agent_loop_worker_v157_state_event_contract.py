#!/usr/bin/env python3
from __future__ import annotations

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
        "run_marker_content_check": lambda repo_dir: (marker_ok, "marker failure" if not marker_ok else "ok"),
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
        old_run = worker.run
        def recording_run(args, cwd=None, check=True):
            text = " ".join(str(x) for x in args)
            calls.append(text)
            return old_run(args, cwd=cwd, check=check) if text.startswith("never") else (HEAD if "rev-parse HEAD" in text else "")
        worker.run = recording_run
        try:
            worker.process_state(_cfg(td), state_path)
            _assert_terminalized_without_post_actions(tmp, state_path)
            assert not any("git push" in c for c in calls)
            events = _events(tmp)
            assert not any(e["kind"] == "cycle_committed" for e in events)
            assert not any(e["kind"] == "cycle_pushed" for e in events)
        finally:
            _restore(originals)
            worker.run = old_run


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
        "repo_dir": str(tmp / "repo"),
        "cycles": 0,
        "status": "LOCAL_EXECUTION",
        "updated_utc": worker.utc(),
        "state_schema_version": worker.STATE_SCHEMA_VERSION,
        "worker_version": worker.WORKER_VERSION,
    }
    state_path = tmp / "state" / f"issue-{issue_number}.json"
    worker.save_json(state_path, state)
    return state_path


def _setup_git_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    worker.subprocess.run(["git", "init"], cwd=str(repo_dir), check=True)
    worker.subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo_dir), check=True)
    worker.subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)
    (repo_dir / "base.txt").write_text("base", encoding="utf-8")
    worker.subprocess.run(["git", "add", "base.txt"], cwd=str(repo_dir), check=True)
    worker.subprocess.run(["git", "commit", "-m", "base"], cwd=str(repo_dir), check=True)


def _initial_attempt_patches(tmp: Path, *, pass_on_cycle: int | None = None, failure_class: str = "TASK_NOT_ACKNOWLEDGED", preexecution: bool = False):
    repo_dir = tmp / "repo"
    _setup_git_repo(repo_dir)
    base_sha = worker.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir)).strip()
    spec = _initial_front_spec()
    spec["expected_base_sha"] = base_sha
    state_path = tmp / "state" / "issue-19.json"
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
        run_marker_content_check=lambda repo_dir_path: (True, "ok"),
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
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "write", "state": {"status": "completed"}, "parameters": {"path": "docs/agent_loop/pilot/PILOT_MARKER.md"}}}) + "\n",
            encoding="utf-8",
        )
        worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        events = _events(tmp)
        completed = next(e for e in events if e["kind"] == "executor_completed")
        assert completed["issue"] == 19
        assert completed.get("pr") is None
        assert completed.get("ack_source") == "verified_artifact_tool"


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
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "write", "state": {"status": "completed"}, "parameters": {"path": "docs/agent_loop/pilot/PILOT_MARKER.md"}}}) + "\n",
            encoding="utf-8",
        )
        worker.validate_executor_delivery(cfg, _artifact_spec(), model_dir, log, 1, issue_no=19, seed_hash=None)
        events = _events(tmp)
        completed = next(e for e in events if e["kind"] == "executor_completed")
        assert completed["task_acknowledged"] is True
        assert completed["ack_source"] == "verified_artifact_tool"
        assert completed["issue"] == 19


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
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "read", "state": {"status": "completed"}, "parameters": {"path": "docs/agent_loop/pilot/PILOT_MARKER.md"}}}) + "\n",
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
        test_verified_artifact_tool_ack_passes_without_text_sentinel,
        test_verified_artifact_tool_ack_requires_exact_marker,
        test_verified_artifact_tool_ack_requires_completed_write_tool,
        test_verified_artifact_tool_ack_rejects_unchanged_marker,
        test_verified_artifact_tool_ack_rejects_extra_file,
        test_verified_artifact_tool_ack_rejects_session_error,
        test_verified_artifact_tool_ack_rejects_conversational_refusal,
        test_marker_without_text_sentinel_still_rejected_when_no_tool,
        test_initial_attempt_nondisclosure_canaries,
    ]

    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL: {test.__name__}: {type(exc).__name__}: {exc}")
    print(json.dumps({"status": "PASS" if failed == 0 else "FAIL", "passed": len(tests) - failed, "failed": failed}, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())