#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
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
        worker.event(cfg, "executor_started", front=FRONT, cycle=1, command_identity="opencode", model="m")
        try:
            worker.event(cfg, "executor_started", front=FRONT, cycle=1)
        except RuntimeError as exc:
            assert "EVENT_CONTRACT_VIOLATION" in str(exc)
        else:
            raise AssertionError("expected event contract violation")
        evt = _events(Path(td))[0]
        assert evt["kind"] == "executor_started"
        assert evt["worker_version"] == worker.WORKER_VERSION
        assert {"front", "cycle", "command_identity", "model"}.issubset(evt)


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
        worker.command_for_subprocess = lambda args: r'C:\System32\cmd.exe /d /s /c fake_opencode.CMD run "prompt"'
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
        worker.command_for_subprocess = lambda args: [r"C:\System32\cmd.exe", "/d", "/s", "/c", "fake_opencode.CMD", "run", "prompt"]
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
        test_final_cycle_audit_failure_terminalizes_same_run,
        test_final_cycle_marker_failure_terminalizes_same_run,
        test_final_cycle_out_of_scope_terminalizes_same_run,
        test_final_cycle_final_verifier_failure_terminalizes_without_push,
        test_executor_attempt_consumed_non_final_saves_state,
        test_executor_attempt_consumed_final_terminalizes,
        test_prompt_canary_absent_from_exception_and_log,
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