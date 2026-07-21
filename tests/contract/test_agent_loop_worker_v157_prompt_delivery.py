#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("agent_worker_v157_prompt", MODULE)
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

FRONT = "PILOT-KIMI-CODEX-20260716-091529"
MARKER = "docs/agent_loop/pilot/PILOT_MARKER.md"


class Completed:
    def __init__(self, stdout: bytes, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def cfg(root: Path) -> dict:
    return {
        "install_root": str(root / "install"),
        "opencode_model": "ollama-cloud/kimi-k2.7-code",
        "opencode_output_token_max": 4096,
        "opencode_timeout_seconds": 5,
    }


def spec_payload(objective: str = "Create the exact pilot marker.") -> dict:
    return {
        "front_id": FRONT,
        "objective": objective,
    }


def make_workspace(root: Path, seed: str = "old marker\n") -> Path:
    model = root / "model with spaces"
    marker = model / MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(seed, encoding="utf-8")
    return model


def json_event(text: str, session: str | None = "ses_fake") -> bytes:
    event = {"type": "text", "sessionID": session, "part": {"type": "text", "text": text}}
    return (json.dumps(event) + "\n").encode("utf-8")


def expect_error(fn, text: str) -> None:
    try:
        fn()
    except Exception as exc:
        assert text.lower() in str(exc).lower(), (text, str(exc))
    else:
        raise AssertionError(f"expected {text}")


def run_case(mode: str, objective: str = "Create the exact pilot marker.") -> tuple[list[dict], Path, Path]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        model = make_workspace(root)
        install = root / "install"
        (install / "reports").mkdir(parents=True)
        events: list[dict] = []
        old_event = worker.event
        old_subprocess = worker.subprocess.run
        old_help = worker._OPENCODE_RUN_HELP
        worker._OPENCODE_RUN_HELP = "Options:\n  --model\n"
        worker._RUNTIME_EXECUTABLES = {"node": r"C:\fake\node.exe", "opencode_entrypoint": r"C:\fake\opencode.js"}
        worker.event = lambda _cfg, kind, **fields: events.append({"kind": kind, **fields})

        def fake_run(args, **kwargs):
            text_args = " ".join(str(x) for x in args)
            if "session" in text_args and "list" in text_args:
                return Completed(b"[]\n")
            if mode == "timeout":
                raise subprocess.TimeoutExpired(args, timeout=1, output=b"timed out")
            if mode == "executable_failure":
                return Completed(b"native failed\n", returncode=2)
            prompt = str(args[-1])
            sentinel = worker.prompt_task_sentinel(FRONT, 1)
            if mode == "prompt_absent":
                assert sentinel not in prompt
            else:
                assert sentinel in prompt
            marker = model / MARKER
            if mode == "exact":
                marker.write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")
                return Completed(json_event(sentinel))
            if mode == "wrong":
                marker.write_text("wrong\n", encoding="utf-8")
                return Completed(json_event(sentinel))
            if mode == "extra":
                marker.write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")
                extra = model / "extra.txt"
                extra.write_text("extra\n", encoding="utf-8")
                return Completed(json_event(sentinel))
            if mode == "conversation":
                marker.write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")
                return Completed(json_event(worker.prompt_task_sentinel(FRONT, 1) + "\nPlease provide the task or instruction set."))
            if mode == "prompt_absent":
                return Completed(json_event("missing ack"))
            if mode == "no_change":
                return Completed(json_event(sentinel, session=None))
            if mode == "invalid_jsonl":
                return Completed(b"{not-json}\n")
            return Completed(json_event(sentinel))

        try:
            if mode == "prompt_absent":
                old_prompt = worker.make_prompt
                worker.make_prompt = lambda *_args, **_kwargs: "missing sentinel"
            worker.subprocess.run = fake_run
            log, _session = worker.run_kimi(cfg(root), spec_payload(objective), model, 5, 1)
            seed_hash = worker.sha256_file(model / MARKER)
            if mode in {"exact", "wrong", "extra"}:
                seed_hash = None
            worker.validate_executor_delivery(cfg(root), spec_payload(objective), model, log, 1, issue_no=5, seed_hash=seed_hash)
            worker.audit_and_sync_model_workspace(model, root / "repo", {}, spec_payload(objective))
        finally:
            if mode == "prompt_absent":
                worker.make_prompt = old_prompt
            worker.subprocess.run = old_subprocess
            worker.event = old_event
            worker._OPENCODE_RUN_HELP = old_help
        return events, model, log


checks: dict[str, bool] = {}

prompt = worker.make_prompt(spec_payload(), 1)
assert f"You are the OpenCode filesystem executor for {FRONT}." in prompt
assert "You are the Kimi executor" not in prompt
assert "EXECUTOR=OPENCODE_OLLAMA_TOOL_EXECUTOR" in prompt
assert "Your first required action is to invoke the OpenCode write tool." in prompt
assert "A text-only response is a failed attempt." in prompt
assert "Do not output the success sentinel before the write tool reports completion." in prompt
assert "After the tool completes, verify the exact relative path and then output the success sentinel." in prompt
assert worker.prompt_task_failure_sentinel(FRONT, 1) in prompt
checks["prompt_requires_write_tool_before_ack"] = True

events, _model, _log = run_case("exact")
assert any(e["kind"] == "executor_started" and e.get("issue") == 5 for e in events)
assert any(e["kind"] == "executor_started" and e.get("model") == "ollama-cloud/kimi-k2.7-code" for e in events)
assert any(e["kind"] == "executor_completed" and e["task_acknowledged"] is True and e.get("ack_source") == "text_sentinel" for e in events)

checks["prompt_sentinel_received_and_exact_marker_passes"] = True

expect_error(lambda: run_case("prompt_absent"), "prompt missing sentinel")
checks["prompt_absent_fails"] = True

expect_error(lambda: run_case("conversation"), "conversational refusal")
checks["conversation_fails"] = True

expect_error(lambda: run_case("no_change"), "did not modify the pilot marker")
checks["exit_zero_no_modification_fails"] = True

expect_error(lambda: run_case("wrong"), "pilot_marker_content_mismatch")
checks["wrong_marker_fails"] = True

expect_error(lambda: run_case("extra"), "workspace_boundary")
checks["extra_file_fails"] = True

expect_error(lambda: run_case("invalid_jsonl"), "expecting property name")
checks["invalid_jsonl_fails"] = True

expect_error(lambda: run_case("timeout"), "exceeded the configured timeout")
checks["timeout_fails"] = True

expect_error(lambda: run_case("executable_failure"), "exited non-zero")
checks["executable_failure_fails"] = True

events, _model, _log = run_case("exact", objective="Create marker. SECRET_TOKEN_SHOULD_NOT_LEAK")
started = next(e for e in events if e["kind"] == "executor_started")
assert "SECRET_TOKEN_SHOULD_NOT_LEAK" not in json.dumps(started)
checks["secret_absent_from_command_log"] = True

failed = [name for name, ok in checks.items() if not ok]
print(json.dumps({"status": "PASS" if not failed else "FAIL", "checks": checks, "failed": failed}, indent=2))
raise SystemExit(0 if not failed else 1)
