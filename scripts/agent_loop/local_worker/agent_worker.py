#!/usr/bin/env python3
"""Allowlisted local OpenCode worker for a single trusted GitHub repository."""
from __future__ import annotations
import argparse, ast, copy, json, os, re, shutil, subprocess, sys, time, traceback, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SPEC_RE = re.compile(r"<!--\s*AGENT_LOOP_SPEC\s*(\{.*?\})\s*AGENT_LOOP_SPEC\s*-->", re.S)
WORKER_VERSION = "1.5.7"
STATE_SCHEMA_VERSION = 1

STATE_KNOWN_TOP_LEVEL_KEYS = {
    "issue_number", "front", "spec", "repo_dir", "pr_number", "pr_url",
    "cycles", "last_head_sha", "opencode_session_id", "status",
    "final_local_report", "worker_version", "updated_utc", "local_retry_count",
    "error", "terminal_notified", "notification_keys", "state_schema_version",
    "trusted_existing_pr_resume_utc", "trusted_base_advance_utc",
    "trusted_v154_resume_done", "trusted_v155_recovery_done", "trusted_v156_post_merge_recovery_done",
    "last_failure_class", "roadmap_binding",
}

EVENT_REQUIRED_FIELDS = {
    "roadmap_manifest_validated": {"issue", "roadmap_id", "roadmap_version", "roadmap_item_id", "manifest_sha256", "roadmap_sha256", "base_sha"},
    "executor_started": {"front", "issue", "cycle", "command_identity", "model"},
    "executor_completed": {"front", "issue", "cycle", "task_acknowledged", "jsonl_events", "ack_source"},
    "executor_failed": {"front", "issue", "cycle", "error", "failure_class"},
    "executor_preflight_failed": {"front", "issue", "pr", "cycle", "failure_class", "command_identity"},
    "local_gate_failed": {"issue", "pr", "cycle", "failure_class", "cycle_before", "cycle_after"},
    "repair_local_gate_failed": {"issue", "pr", "cycle", "failure_class", "cycle_before", "cycle_after"},
    "cycle_committed": {"issue", "pr", "cycle", "head_sha"},
    "cycle_pushed": {"issue", "pr", "cycle", "head_sha"},
    "cycle_commit_reverted": {"issue", "pr", "cycle", "head_sha", "failure_class"},
    "codex_review_started": {"issue", "pr", "head_sha"},
    "codex_review_passed": {"issue", "pr", "head_sha"},
    "codex_review_failed": {"issue", "pr", "head_sha", "error"},
    "codex_repair_requested": {"issue", "pr", "head_sha"},
    "supervisor_authorization_consumed": {"issue", "pr", "authorization"},
    "kimi_cycle_start": {"issue", "cycle", "front"},
    "kimi_cycle_repair_needed": {"issue", "cycle"},
    "pr_created": {"issue", "pr", "sha"},
    "state_terminalized": {"state", "issue", "phase", "failure_class"},
    "worker_started": {"once", "worker_version", "worker_sha256"},
}
PHASE_LABELS = {
    "agent:queued", "loop:executing", "loop:ci", "loop:repairing",
    "loop:ready-human-audit", "loop:blocked", "loop:failed",
    "loop:token-exhausted", "loop:accepted"
}
TERMINAL_LABELS = {"loop:ready-human-audit", "loop:blocked", "loop:failed", "loop:token-exhausted", "loop:accepted"}
PROFILE_ALLOWED_PATHS = {
    "pilot": {
        "docs/agent_loop/pilot/PILOT_MARKER.md",
        "docs/agent_loop/pilot/EXECUTOR_REPORT.json",
    },
    "roadmap-doc": set(),
    "test-only": set(),
}
PROFILE_PATH_PREFIXES = {
    "roadmap-doc": ("docs/roadmap/",),
    "test-only": ("tests/",),
}
PROFILE_EXACT_PATHS = {
    "roadmap-doc": {"ROADMAP_STATUS.json"},
    "test-only": set(),
}
PROFILE_BRANCH_PREFIXES = {
    "pilot": "agent/pilot-",
    "roadmap-doc": "agent/roadmap-doc-",
    "test-only": "agent/test-only-",
}
PROFILE_TRUSTED_COMMANDS = {
    "roadmap-doc": ("git", "diff", "--check"),
    # This identifies the validation contract; run_profile performs AST-only
    # validation and never executes model-authored test code.
    "test-only": ("python", "-m", "py_compile"),
}
REQUIRED_FORBIDDEN_PATHS = {
    "memory/semantic/",
    "memory/rollback",
    "tmp_agent/state/",
    "tmp_agent/brain_v9/trading/",
    "financial_autonomy/",
    "tmp_agent/brain_v9/core/session.py",
}
MODEL_SEED_PATHS: set[str] = set()
ROADMAP_MANIFEST_PATH = "docs/roadmap/BRAIN_101_MANIFEST.json"
_RUN_EVENT_CFG: dict | None = None
_SENSITIVE_COMMAND_WORDS = {"auth", "token", "secret", "login", "password", "key"}
_RUNTIME_EXECUTABLES: dict[str, str] = {}
_EXECUTABLE_ALLOWED_EXTENSIONS = {
    "git": {".exe"},
    "gh": {".exe"},
    "python": {".exe"},
    "opencode": {".cmd", ".exe"},
    "opencode_entrypoint": {".js"},
    "node": {".exe"},
    "cmd": {".exe"},
}
_EXECUTABLE_CONFIG_KEYS = {
    "git": "git_exe",
    "gh": "gh_exe",
    "python": "python_exe",
    "opencode": "opencode_cmd",
    "opencode_entrypoint": "opencode_entrypoint",
    "node": "node_exe",
    "cmd": "cmd_exe",
}
_REQUIRED_EXECUTABLE_CONFIG_KEYS = {"git_exe", "gh_exe", "python_exe", "opencode_cmd", "cmd_exe"}
PILOT_MARKER_TEMPLATE = """# Agent Loop Pilot
WORKER_VERSION={worker_version}
FRONT_ID={front_id}
STATUS=PASS
EXECUTOR=OPENCODE_OLLAMA_TOOL_EXECUTOR
SUPERVISOR=CODEX_GITHUB_ACTION
"""
_FRONT_ID_RE = re.compile(r"[A-Z0-9][A-Z0-9._-]{5,127}")


def valid_front_id(value: object) -> bool:
    text = str(value)
    return bool(_FRONT_ID_RE.fullmatch(text)) and ".." not in text


def profile_paths_are_trusted(profile: str, paths: set[str]) -> bool:
    if profile == "pilot":
        return paths == PROFILE_ALLOWED_PATHS["pilot"]
    prefixes = PROFILE_PATH_PREFIXES.get(profile, ())
    exact = PROFILE_EXACT_PATHS.get(profile, set())
    return bool(paths) and len(paths) <= 20 and all(
        path in exact or any(path.startswith(prefix) for prefix in prefixes)
        for path in paths
    )


def profile_command_is_trusted(profile: str, command: object) -> bool:
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
        return False
    executable = Path(command[0]).name.lower()
    if any(any(token in arg for token in (";", "&&", "||", ">", "<", "`")) for arg in command):
        return False
    if profile == "roadmap-doc":
        return executable in {"git", "git.exe"} and command[1:] == ["diff", "--check"]
    if profile == "test-only":
        if executable not in {"python", "python.exe"}:
            return False
        return command[1:] == ["-m", "py_compile"]
    return False

_CONVERSATIONAL_REJECTION_PATTERNS = {
    "please provide the task",
    "please clarify",
    "what would you like me to do",
    "i need more information",
    "can you provide more details",
    "missing instruction",
    "no task specified",
    "awaiting instructions",
}

def prompt_task_sentinel(front_id: str, cycle: int) -> str:
    return f"ACK_TASK_ID={front_id}|cycle={cycle}"

def prompt_task_failure_sentinel(front_id: str, cycle: int) -> str:
    return f"{prompt_task_sentinel(front_id, cycle)} TASK_FAILED"

_WRITE_RETRY_FAILURE_CLASSES = {
    "NO_WRITE_TOOL_CALL",
    "WRITE_TOOL_FAILED",
    "WRITE_TOOL_NO_EFFECT",
    "EXECUTOR_DECLARED_WRITE_FAILURE",
    "NO_OUTPUT_CHANGE",
}

_WRITE_FAILURE_FEEDBACK = {
    "NO_WRITE_TOOL_CALL": "The prior attempt returned text without invoking the required write tool. Use the OpenCode write tool to create docs/agent_loop/pilot/PILOT_MARKER.md with the exact requested content. Do not emit the success acknowledgement until the write tool has completed.",
    "WRITE_TOOL_FAILED": "The prior write-tool invocation failed. Retry using the OpenCode write tool with the exact relative allowlisted path and exact requested content. Do not use shell or absolute paths.",
    "WRITE_TOOL_NO_EFFECT": "The prior write-tool invocation completed without changing the allowlisted marker. Rewrite the exact marker using the OpenCode write tool, then emit the success acknowledgement.",
    "EXECUTOR_DECLARED_WRITE_FAILURE": "The prior executor declared that it could not write the marker. Retry once using the OpenCode write tool and the exact relative allowlisted path.",
}

def pilot_marker_text(front_id: str) -> str:
    return PILOT_MARKER_TEMPLATE.format(worker_version=WORKER_VERSION, front_id=str(front_id))

class PreExecutionFailure(RuntimeError):
    """Deterministic failure before the OpenCode process was started. Does not consume an executor cycle."""

    def __init__(self, failure_class: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.failure_class = failure_class
        self.details = details or {}


class ExecutorAttemptConsumed(RuntimeError):
    """OpenCode was started and this attempt must consume exactly one executor cycle."""

    def __init__(self, failure_class: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.failure_class = failure_class
        self.details = details or {}


class ModelWorkspaceScopeViolation(RuntimeError):
    """An out-of-scope path or trust boundary violation was detected in the model workspace."""

    def __init__(self, reason_code: str, count: int = 0):
        self.reason_code = reason_code
        self.count = count
        super().__init__(f"workspace_boundary violation: {reason_code}")


class CmdError(RuntimeError):
    def __init__(self, cmd, code, out):
        redacted = _redacted_cmd_repr(cmd)
        super().__init__(f"command failed ({code}): {redacted}\n{out[-4000:]}")
        self.cmd, self.code, self.out = redacted, code, out

def utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False

def _runtime_command_name(value: str) -> str | None:
    base = os.path.basename(str(value)).lower()
    if base in {"git", "git.exe"}:
        return "git"
    if base in {"gh", "gh.exe"}:
        return "gh"
    if base.startswith("python"):
        return "python"
    if base in {"opencode", "opencode.cmd", "opencode.exe"}:
        return "opencode"
    if base in {"opencode-entrypoint", "opencode_entrypoint"}:
        return "opencode_entrypoint"
    if base in {"node", "node.exe"}:
        return "node"
    if base in {"cmd", "cmd.exe"}:
        return "cmd"
    return None

def _safe_version_at_least(actual: str, expected: str) -> bool:
    def nums(text: str) -> tuple[int, ...]:
        m = re.search(r"(\d+(?:\.\d+){0,3})", text or "")
        return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)
    a, b = nums(actual), nums(expected)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) >= b + (0,) * (width - len(b))


def _windows_short_path(path: str) -> str:
    """Return the Windows 8.3 short path for a file or directory.

    Used to avoid quoting/escaping problems when invoking .CMD/.BAT shims
    whose absolute path contains spaces.
    """
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    GetShortPathNameW = kernel32.GetShortPathNameW
    GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    GetShortPathNameW.restype = wintypes.DWORD
    buf = ctypes.create_unicode_buffer(260)
    size = GetShortPathNameW(path, buf, 260)
    if size == 0 or size > 260:
        raise RuntimeError(f"short_path_failed:{path}")
    return str(buf[:size])


def _win_cmd_quote(arg: str) -> str:
    """Quote an argument for cmd.exe using Windows command-line rules.

    Spaces and shell metacharacters (& | < > ^ % !) force quoting.
    Inner double quotes are doubled (CommandLineToArgvW style).
    """
    if not arg:
        return '""'
    needs_quote = ' ' in arg or '"' in arg or any(c in arg for c in "&|<>")
    if not needs_quote and not any(c in arg for c in "^%!"):
        return arg
    out = '"'
    for ch in arg:
        if ch == '"':
            out += '""'
        else:
            out += ch
    out += '"'
    return out


def _opencode_node_entrypoint(opencode_cmd: str) -> str | None:
    """Return the Node entrypoint JS for an installed opencode command.

    npm installs opencode as a .CMD shim that delegates to node.exe and the
    package's bin/opencode JS file. For lossless transport we bypass cmd.exe
    and invoke node.exe with that JS entrypoint directly.
    """
    cmd_path = Path(opencode_cmd).resolve()
    # The shim is at npm/opencode.CMD; the package lives next to it under
    # node_modules/opencode-ai/bin/opencode.
    candidate = cmd_path.parent / "node_modules" / "opencode-ai" / "bin" / "opencode"
    if candidate.is_file():
        return str(candidate)
    # If the configured command itself is a JS file, use it.
    if cmd_path.suffix.lower() == ".js":
        return str(cmd_path)
    return None


def command_for_subprocess(args: list[str]):
    """Resolve commands safely on Windows, including npm .cmd/.bat shims.

    For .CMD/.BAT shims on Windows the function returns a single command-line
    string suitable for passing directly to subprocess.run(..., shell=False).
    This avoids Python's list2cmdline backslash-escaping of inner quotes, which
    breaks cmd.exe parsing for arguments containing spaces.

    For opencode we bypass cmd.exe entirely: node.exe is invoked with the
    package's bin/opencode JS entrypoint, and every argument (including
    multiline prompts) is passed as a list element to subprocess.run. This
    preserves newlines, the sentinel, and shell metacharacters byte-for-byte.
    """
    values = [str(x) for x in args]
    if not values:
        raise ValueError("empty command")
    command_name = _runtime_command_name(values[0])
    resolved = _RUNTIME_EXECUTABLES.get(command_name or "")
    if resolved:
        values[0] = resolved
    else:
        path_resolved = shutil.which(values[0])
        if path_resolved:
            values[0] = path_resolved
    suffix = os.path.splitext(values[0])[1].lower()
    if os.name == "nt" and suffix in {".cmd", ".bat"}:
        # Lossless path for opencode: call node.exe + JS entrypoint directly.
        if command_name == "opencode":
            node_exe = _RUNTIME_EXECUTABLES.get("node")
            entrypoint = _RUNTIME_EXECUTABLES.get("opencode_entrypoint") or _opencode_node_entrypoint(values[0])
            if node_exe and entrypoint:
                return [node_exe, entrypoint, *values[1:]]
        # Fallback for other .CMD/.BAT shims: route through cmd.exe.
        comspec = _RUNTIME_EXECUTABLES.get("cmd") or os.environ.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
        cmd_path = values[0]
        if ' ' in cmd_path or '"' in cmd_path:
            try:
                cmd_path = _windows_short_path(cmd_path)
            except Exception:
                pass
        inner = " ".join(_win_cmd_quote(v) for v in [cmd_path, *values[1:]])
        return f"{comspec} /d /s /c {inner}"
    return values

def _sha256_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _redacted_cmd_repr(args: list[str]) -> list[str]:
    """Return a log/event-safe representation of a command line.

    For the opencode identity the final argument is treated as the prompt and
    is fully redacted to a stable hash/length placeholder so that prompt
    content can never leak into exceptions, logs, events, state, or reports.
    """
    if not args:
        return []
    ident = command_identity(args)
    if ident != "opencode" or len(args) < 2:
        return sanitize_command_for_log(args)
    safe: list[str] = [ident]
    prompt = str(args[-1])
    for value in args[1:-1]:
        lower = str(value).lower()
        if any(word in lower for word in _SENSITIVE_COMMAND_WORDS):
            safe.append("<redacted>")
        elif len(str(value)) > 160:
            safe.append(str(value)[:80] + "...<truncated>")
        else:
            safe.append(str(value))
    safe.append(f"<prompt:redacted bytes={len(prompt.encode('utf-8'))} sha256={_sha256_text(prompt)}>")
    return safe


def sanitize_command_for_log(args: list[str]) -> list[str]:
    if not args:
        return []
    ident = command_identity(args)
    safe: list[str] = [ident]
    for value in args[1:]:
        lower = str(value).lower()
        if any(word in lower for word in _SENSITIVE_COMMAND_WORDS):
            safe.append("<redacted>")
        elif ident == "opencode":
            # Fully redact any prompt-sized argument for the opencode identity.
            safe.append("<redacted>")
        elif len(str(value)) > 160:
            safe.append(str(value)[:80] + "...<truncated>")
        else:
            safe.append(str(value))
    return safe

def resolve_runtime_executables(cfg: dict, *, require_config: bool = False) -> dict[str, str]:
    runtime_cfg = cfg.get("runtime_executables") or {}
    allow_dirs = [Path(x).expanduser().resolve() for x in cfg.get("executable_allowlist_dirs") or []]
    if require_config and (not isinstance(runtime_cfg, dict) or _REQUIRED_EXECUTABLE_CONFIG_KEYS - set(runtime_cfg)):
        raise RuntimeError("RUNTIME_EXECUTABLE_CONFIG_MISSING")
    if require_config and not allow_dirs:
        raise RuntimeError("RUNTIME_EXECUTABLE_ALLOWLIST_MISSING")
    resolved: dict[str, str] = {}
    for name, key in _EXECUTABLE_CONFIG_KEYS.items():
        configured = runtime_cfg.get(key)
        if not configured:
            if require_config and key in _REQUIRED_EXECUTABLE_CONFIG_KEYS:
                raise RuntimeError(f"RUNTIME_EXECUTABLE_MISSING:{key}")
            found = shutil.which("opencode.cmd" if name == "opencode" else f"{name}.exe") or shutil.which(name)
            if found:
                resolved[name] = str(Path(found).resolve())
            continue
        path = Path(str(configured)).expanduser()
        if not path.is_absolute():
            raise RuntimeError(f"RUNTIME_EXECUTABLE_NOT_ABSOLUTE:{key}")
        path = path.resolve()
        if not path.is_file():
            raise RuntimeError(f"RUNTIME_EXECUTABLE_NOT_FILE:{key}")
        suffix = path.suffix.lower()
        # The opencode entrypoint is a Node script; it has no extension when the
        # npm package exposes a shebang file. Accept extensionless JS entrypoints.
        if name == "opencode_entrypoint" and not suffix:
            suffix = ".js"
        if suffix not in _EXECUTABLE_ALLOWED_EXTENSIONS[name]:
            raise RuntimeError(f"RUNTIME_EXECUTABLE_EXTENSION_DENIED:{key}:{suffix}")
        if allow_dirs and not any(_is_relative_to(path, allowed) for allowed in allow_dirs):
            raise RuntimeError(f"RUNTIME_EXECUTABLE_OUTSIDE_ALLOWLIST:{key}")
        resolved[name] = str(path)
    return resolved

def configure_runtime_resolution(cfg: dict, *, require_config: bool = False) -> dict[str, str]:
    global _RUNTIME_EXECUTABLES
    _RUNTIME_EXECUTABLES = resolve_runtime_executables(cfg, require_config=require_config)
    return dict(_RUNTIME_EXECUTABLES)

def decode_process_output(data: bytes | str | None) -> tuple[str, str]:
    if data is None:
        return "", "none"
    if isinstance(data, str):
        return data, "text"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), "utf-8-replace"

def completed_output(p) -> tuple[str, str]:
    return decode_process_output(getattr(p, "stdout", b""))

def command_identity(args: list[str]) -> str:
    if not args:
        return "unknown"
    first = os.path.basename(str(args[0])).lower()
    if first in {"git", "git.exe"}:
        return "git"
    if first in {"gh", "gh.exe"}:
        return "gh"
    if first.startswith("python"):
        return "python"
    if first in {"opencode", "opencode.cmd", "opencode.exe"}:
        return "opencode"
    if any(str(x).lower() in _SENSITIVE_COMMAND_WORDS for x in args[:3]):
        return "sensitive-command"
    return first or "unknown"

def emit_subprocess_decoding_event(cfg: dict | None, args: list[str], mode: str) -> None:
    if not cfg or mode != "utf-8-replace":
        return
    event(cfg, "subprocess_output_decoding_fallback", command=command_identity(args), decoding=mode)

def run(args: list[str], cwd: Path | None = None, env: dict[str,str] | None = None, check=True, timeout=None) -> str:
    p = subprocess.run(command_for_subprocess(args), cwd=str(cwd) if cwd else None, env=env, text=False,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    out, decoding = completed_output(p)
    emit_subprocess_decoding_event(_RUN_EVENT_CFG, args, decoding)
    if check and p.returncode != 0:
        raise CmdError(args, p.returncode, out)
    return out

def gh_json(args: list[str]) -> Any:
    return json.loads(run(["gh", *args]))

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))

def save_json(path: Path, data: Any) -> None:
    if isinstance(data, dict) and "issue_number" in data and "status" in data:
        data = normalize_state(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def event(cfg, kind, **fields):
    if kind == "repair_local_gate_failed":
        fields.setdefault("legacy_kind", "repair_local_gate_failed")
        kind = "local_gate_failed"
    for key in fields:
        if key.lower() in {"prompt", "token", "secret", "password", "credential"}:
            raise RuntimeError(f"EVENT_CONTRACT_VIOLATION:{kind}: sensitive field {key}")
    fields.setdefault("worker_version", WORKER_VERSION)
    record = {"timestamp_utc": utc(), "kind": kind, **fields}
    required = EVENT_REQUIRED_FIELDS.get(kind)
    if required and not required.issubset(fields):
        raise RuntimeError(f"EVENT_CONTRACT_VIOLATION:{kind}: missing {sorted(required - set(fields))}")
    p = Path(cfg["install_root"]) / "reports" / "worker-events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def normalize_state(st: dict) -> dict:
    st = dict(st)
    st["state_schema_version"] = STATE_SCHEMA_VERSION
    st["worker_version"] = WORKER_VERSION
    return st

def validate_state_json(st: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(st, dict):
        return ["state is not a JSON object"]
    if st.get("state_schema_version") != STATE_SCHEMA_VERSION:
        errors.append(f"state_schema_version must be {STATE_SCHEMA_VERSION}")
    required = {"issue_number", "status", "updated_utc"}
    missing = sorted(required - set(st))
    if missing:
        errors.append(f"missing required state keys: {missing}")
    unknown = sorted(set(st) - STATE_KNOWN_TOP_LEVEL_KEYS)
    if unknown:
        errors.append(f"unknown state keys: {unknown}")
    return errors

def labels(obj) -> set[str]:
    return {x["name"] for x in obj.get("labels", [])}

def edit_labels(repo: str, number: int, add=(), remove=()):
    # Remove individually because gh may reject a combined mutation when one label is absent.
    for label in remove:
        run(["gh", "issue", "edit", str(number), "--repo", repo, "--remove-label", label], check=False)
    for label in add:
        run(["gh", "issue", "edit", str(number), "--repo", repo, "--add-label", label])

def set_phase(repo: str, number: int, phase: str) -> None:
    """Apply exactly one loop phase label and remove all conflicting phases."""
    if phase not in PHASE_LABELS:
        raise ValueError(f"unknown phase label: {phase}")
    edit_labels(repo, number, add=[phase], remove=sorted(PHASE_LABELS - {phase}))

def phase_labels(obj: dict) -> set[str]:
    return labels(obj) & PHASE_LABELS

def assert_exact_phase(obj: dict, expected: str, label: str = "object") -> None:
    actual = phase_labels(obj)
    if actual != {expected}:
        raise ValueError(f"{label} phase mismatch: expected {expected}, actual {sorted(actual)}")

def restore_label_set(repo: str, number: int, original_labels: set[str]) -> None:
    current = labels(gh_json(["issue", "view", str(number), "--repo", repo, "--json", "labels"]))
    # Remove all non-original phase labels even if the preceding readback was stale
    # or incomplete. GitHub label removal is best-effort per label in edit_labels.
    remove = (current - original_labels) | (PHASE_LABELS - original_labels)
    edit_labels(repo, number, add=sorted(original_labels - current), remove=sorted(remove))
    edit_labels(repo, number, add=sorted(original_labels), remove=sorted(PHASE_LABELS - original_labels))

def read_issue_labels(repo: str, number: int) -> dict:
    return gh_json(["issue", "view", str(number), "--repo", repo, "--json", "number,labels"])

def read_pr_labels(repo: str, number: int) -> dict:
    return gh_json(["pr", "view", str(number), "--repo", repo, "--json", "number,labels"])

def set_converged_phase(cfg: dict, state_path: Path, st: dict, phase: str, *, pr_number: int | None = None) -> dict:
    issue = int(st["issue_number"])
    prn = int(pr_number if pr_number is not None else st.get("pr_number") or 0)
    original_state_bytes = state_path.read_bytes() if state_path.exists() else b""
    original_issue_labels = labels(read_issue_labels(cfg["repo"], issue))
    original_pr_labels = labels(read_pr_labels(cfg["repo"], prn)) if prn else set()
    new_state = dict(st)
    new_state["status"] = "WAITING_GITHUB" if phase == "loop:ci" else phase
    new_state["updated_utc"] = utc()
    try:
        save_json(state_path, new_state)
        set_phase(cfg["repo"], issue, phase)
        if prn:
            set_phase(cfg["repo"], prn, phase)
        assert_exact_phase(read_issue_labels(cfg["repo"], issue), phase, f"Issue #{issue}")
        if prn:
            assert_exact_phase(read_pr_labels(cfg["repo"], prn), phase, f"PR #{prn}")
        return new_state
    except Exception as exc:
        rollback = {"state": False, "issue_labels": False, "pr_labels": False}
        try:
            if original_state_bytes:
                state_path.write_bytes(original_state_bytes)
            elif state_path.exists():
                state_path.unlink()
            rollback["state"] = True
        except Exception:
            pass
        try:
            restore_label_set(cfg["repo"], issue, original_issue_labels)
            rollback["issue_labels"] = True
        except Exception:
            pass
        if prn:
            try:
                restore_label_set(cfg["repo"], prn, original_pr_labels)
                rollback["pr_labels"] = True
            except Exception:
                pass
        try:
            event(cfg, "phase_convergence_rollback", issue=issue, pr=prn or None, phase=phase, error=bounded_tail(str(exc)), rollback=rollback)
        except Exception:
            pass
        raise

def pr_changed_files(repo: str, pr_number: int) -> list[str]:
    out = run(["gh", "pr", "diff", str(pr_number), "--repo", repo, "--name-only"])
    return sorted(x.strip().replace("\\", "/") for x in out.splitlines() if x.strip())

def has_terminal_label(obj: dict) -> bool:
    return bool(labels(obj) & TERMINAL_LABELS)

def terminal_phase_from_labels(obj: dict) -> str | None:
    labs = labels(obj)
    for phase in ("loop:accepted", "loop:ready-human-audit", "loop:token-exhausted", "loop:failed", "loop:blocked"):
        if phase in labs:
            return phase
    return None

def state_is_terminal(st: dict) -> bool:
    return str(st.get("status", "")) in TERMINAL_LABELS

def should_terminalize_failed_cycle(st: dict, spec: dict, cycle: int) -> bool:
    return (
        cycle >= int(spec["max_kimi_cycles"])
        and st.get("state_schema_version") == STATE_SCHEMA_VERSION
        and st.get("worker_version") == WORKER_VERSION
    )

def comment(repo: str, number: int, body: str):
    run(["gh", "issue", "comment", str(number), "--repo", repo, "--body", body])

def issue_comments(repo: str, number: int) -> list[dict]:
    return gh_json(["api", f"repos/{repo}/issues/{number}/comments?per_page=100"])


def seed_terminal_notification_keys_from_comments(cfg: dict, st: dict, phase: str, message: str) -> dict:
    """Seed stable notification ledger from existing marker or legacy terminal comments."""
    pr_number = int(st.get("pr_number") or 0) or None
    target = pr_number or int(st["issue_number"])
    key = notification_key(st.get("front"), pr_number, st.get("last_head_sha"), phase)
    marker = notification_marker(key)
    ledger = set(st.get("notification_keys") or [])
    for item in issue_comments(cfg["repo"], target):
        body = item.get("body") or ""
        if marker in body or is_legacy_terminal_notification(body, phase, message):
            ledger.add(key)
    st["notification_keys"] = sorted(ledger)
    return st

def _safe_cmd_identity(command_line: str) -> str:
    text = re.sub(r"(?i)(token|secret|password|key)=\S+", r"\1=<redacted>", str(command_line or ""))
    return text[:500]

def worker_process_evidence(install_root: str) -> list[dict]:
    """Return bounded evidence for exact agent_worker.py/config worker command lines."""
    if os.name != "nt":
        return []
    worker = str(Path(install_root) / "worker" / "agent_worker.py")
    config = str(Path(install_root) / "config" / "worker.json")
    ps = (
        "$ErrorActionPreference='SilentlyContinue'; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*agent_worker.py*' -and $_.CommandLine -like '*worker.json*' } | "
        "Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Depth 4"
    )
    out = run(["powershell", "-NoProfile", "-Command", ps], check=False)
    if not out.strip():
        return []
    try:
        raw = json.loads(out)
    except Exception:
        return [{"parse_error": bounded_tail(out)}]
    items = raw if isinstance(raw, list) else [raw]
    evidence = []
    for item in items:
        cmd = item.get("CommandLine") or ""
        if worker.lower() in cmd.lower() and config.lower() in cmd.lower():
            evidence.append({
                "pid": item.get("ProcessId"),
                "executable": item.get("ExecutablePath"),
                "command_identity": _safe_cmd_identity(cmd),
            })
    return evidence[:5]

def acquire_quiescence_or_raise(cfg: dict):
    require_scheduled_task_disabled_for_trusted(cfg, "trusted maintenance")
    try:
        return SingleInstanceLock(Path(cfg["install_root"]) / "state" / "worker.lock").__enter__()
    except Exception as exc:
        evidence = worker_process_evidence(cfg["install_root"])
        raise RuntimeError("worker.lock busy; trusted maintenance aborted before mutation; process_evidence=" + json.dumps(evidence, sort_keys=True)) from exc

def notification_key(front_id: str | None, pr_number: int | None, head_sha: str | None, terminal_phase: str) -> str:
    return "|".join([str(front_id or ""), str(pr_number or ""), str(head_sha or ""), str(terminal_phase)])

def notification_marker(key: str) -> str:
    return f"<!-- AGENT_LOOP_NOTIFICATION_KEY:{key} -->"

def terminal_notification_tag(phase: str) -> str:
    return {
        "loop:token-exhausted": "TOKEN_EXHAUSTED",
        "loop:blocked": "BLOCKED",
        "loop:failed": "FAILED",
        "loop:ready-human-audit": "READY_HUMAN_AUDIT",
        "loop:accepted": "ACCEPTED",
    }.get(phase, phase.split(":")[-1].upper())

def normalize_terminal_message(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()

def is_legacy_terminal_notification(body: str, phase: str, message: str) -> bool:
    tag = terminal_notification_tag(phase)
    normalized_body = normalize_terminal_message(body)
    normalized_message = normalize_terminal_message(message)
    if f"[agent-loop][{tag.lower()}]" not in normalized_body:
        return False
    if normalized_message and normalized_message[:120] not in normalized_body:
        return False
    return True

def publish_terminal_notification(cfg: dict, state_path: Path, st: dict, phase: str, message: str) -> dict:
    pr_number = int(st.get("pr_number") or 0) or None
    target = pr_number or int(st["issue_number"])
    key = notification_key(st.get("front"), pr_number, st.get("last_head_sha"), phase)
    marker = notification_marker(key)
    ledger = set(st.get("notification_keys") or [])
    if key in ledger:
        st["terminal_notified"] = True
        save_json(state_path, st)
        return st
    st = seed_terminal_notification_keys_from_comments(cfg, st, phase, message)
    ledger = set(st.get("notification_keys") or [])
    if key in ledger:
        st["terminal_notified"] = True
        save_json(state_path, st)
        return st
    body = f"{marker}\n[AGENT-LOOP][{terminal_notification_tag(phase)}]\n\n@{cfg['owner']} {message[-4000:]}"
    comment(cfg["repo"], target, body)
    ledger.add(key)
    st["notification_keys"] = sorted(ledger)
    st["terminal_notified"] = True
    save_json(state_path, st)
    return st

def update_issue_body(repo: str, number: int, body: str) -> None:
    run(["gh", "issue", "edit", str(number), "--repo", repo, "--body", body])

def update_pr_body(repo: str, number: int, body: str) -> None:
    run(["gh", "pr", "edit", str(number), "--repo", repo, "--body", body])

def update_issue_spec_body(body: str, new_base_sha: str) -> str:
    match = SPEC_RE.search(body or "")
    if not match:
        raise ValueError("AGENT_LOOP_SPEC missing")
    spec = json.loads(match.group(1))
    spec["expected_base_sha"] = new_base_sha
    compact = json.dumps(spec, separators=(",", ":"), ensure_ascii=False)
    return (body[:match.start()] + f"<!-- AGENT_LOOP_SPEC {compact} AGENT_LOOP_SPEC -->" + body[match.end():])

def verify_commit_contains(cfg: dict, ancestor_sha: str, descendant_sha: str) -> None:
    cmp = gh_json(["api", f"repos/{cfg['repo']}/compare/{ancestor_sha}...{descendant_sha}"])
    if cmp.get("status") not in {"ahead", "identical"}:
        raise ValueError("approved new base does not contain approved control-plane commit")

def _normalize_repo_path(value: str) -> str:
    norm = str(value).replace("\\", "/").strip().lstrip("./")
    if not norm or norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        raise ValueError(f"invalid repository path: {value!r}")
    parts = [p for p in norm.split("/") if p]
    if any(p == ".." for p in parts):
        raise ValueError(f"path traversal is not allowed: {value!r}")
    return "/".join(parts)


def _github_file_bytes(cfg: dict, repo_path: str, ref: str) -> bytes:
    import base64
    path = _normalize_repo_path(repo_path)
    data = gh_json(["api", f"repos/{cfg['repo']}/contents/{path}?ref={ref}"])
    if not isinstance(data, dict) or data.get("type") != "file" or not isinstance(data.get("content"), str):
        raise ValueError(f"roadmap source unavailable: {path}")
    try:
        return base64.b64decode(data["content"].replace("\n", ""), validate=True)
    except Exception as exc:
        raise ValueError(f"roadmap source encoding invalid: {path}") from exc


def _sha256_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _roadmap_source(cfg: dict, spec: dict) -> tuple[dict, bytes, bytes]:
    loader = cfg.get("_roadmap_manifest_loader")
    if loader is not None:
        if not callable(loader):
            raise ValueError("roadmap loader must be callable")
        manifest, manifest_bytes, roadmap_bytes = loader(spec)
        return manifest, bytes(manifest_bytes), bytes(roadmap_bytes)
    manifest_bytes = _github_file_bytes(cfg, ROADMAP_MANIFEST_PATH, spec["expected_base_sha"])
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    except Exception as exc:
        raise ValueError("roadmap manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("roadmap manifest must be an object")
    roadmap_path = _normalize_repo_path(str(manifest.get("roadmap_path") or ""))
    roadmap_bytes = _github_file_bytes(cfg, roadmap_path, spec["expected_base_sha"])
    return manifest, manifest_bytes, roadmap_bytes


def validate_roadmap_contract(cfg: dict, spec: dict) -> dict:
    required = ["roadmap_id", "roadmap_version", "roadmap_sha256", "roadmap_item_id", "dependencies", "human_final_authority"]
    missing = [key for key in required if key not in spec]
    if missing:
        raise ValueError(f"roadmap contract missing fields: {missing}")
    if spec["human_final_authority"] is not True:
        raise ValueError("human_final_authority must be true")
    claimed_hash = str(spec["roadmap_sha256"])
    if not re.fullmatch(r"[0-9a-f]{64}", claimed_hash):
        raise ValueError("roadmap_sha256 must be a lowercase 64-character SHA-256")
    if not isinstance(spec["dependencies"], list) or not all(isinstance(value, str) for value in spec["dependencies"]):
        raise ValueError("dependencies must be a string list")

    manifest, manifest_bytes, roadmap_bytes = _roadmap_source(cfg, spec)
    if manifest.get("repository") != cfg["repo"] or manifest.get("integration_branch") != cfg["base_branch"]:
        raise ValueError("roadmap manifest repository binding mismatch")
    if manifest.get("approval_status") != "HUMAN_ADOPTED" or manifest.get("r0_status") != "CLOSED_HUMAN_ADOPTED":
        raise ValueError("roadmap manifest is not human-adopted")
    if spec["roadmap_id"] != manifest.get("roadmap_id"):
        raise ValueError("roadmap id mismatch")
    if spec["roadmap_version"] != manifest.get("roadmap_version"):
        raise ValueError("roadmap version mismatch")
    actual_roadmap_hash = _sha256_bytes(roadmap_bytes)
    if manifest.get("roadmap_sha256") != actual_roadmap_hash:
        raise ValueError("roadmap manifest hash does not match roadmap bytes")
    if claimed_hash != actual_roadmap_hash:
        raise ValueError("roadmap hash mismatch")

    items = manifest.get("roadmap_items")
    if not isinstance(items, dict):
        raise ValueError("roadmap item registry missing")
    item_id = str(spec["roadmap_item_id"])
    item = items.get(item_id)
    if not isinstance(item, dict):
        raise ValueError("roadmap item is not registered")
    if item.get("status") != "AUTHORIZED_ACTIVE":
        raise ValueError("roadmap item is not authorized active")
    expected_dependencies = item.get("dependencies")
    if not isinstance(expected_dependencies, list) or not all(isinstance(value, str) for value in expected_dependencies):
        raise ValueError("roadmap item dependencies are invalid")
    if sorted(spec["dependencies"]) != sorted(expected_dependencies):
        raise ValueError("roadmap dependency declaration mismatch")
    for dependency in expected_dependencies:
        if dependency == "R0":
            closed = manifest.get("r0_status") == "CLOSED_HUMAN_ADOPTED"
        else:
            dependency_item = items.get(dependency)
            closed = isinstance(dependency_item, dict) and str(dependency_item.get("status", "")).startswith("CLOSED")
        if not closed:
            raise ValueError(f"roadmap dependency open: {dependency}")
    return {
        "schema_version": 1,
        "repository": manifest["repository"],
        "integration_branch": manifest["integration_branch"],
        "approval_status": manifest["approval_status"],
        "r0_status": manifest["r0_status"],
        "roadmap_id": manifest["roadmap_id"],
        "roadmap_version": manifest["roadmap_version"],
        "roadmap_item_id": item_id,
        "roadmap_item_status": item["status"],
        "manifest_path": ROADMAP_MANIFEST_PATH,
        "manifest_sha256": _sha256_bytes(manifest_bytes),
        "roadmap_path": manifest["roadmap_path"],
        "roadmap_sha256": actual_roadmap_hash,
        "base_sha": spec["expected_base_sha"],
        "dependencies": sorted(expected_dependencies),
    }


def validate_persisted_roadmap_binding(st: dict) -> None:
    spec = st.get("spec") or {}
    roadmap_spec_fields = {
        "roadmap_id",
        "roadmap_version",
        "roadmap_sha256",
        "roadmap_item_id",
        "dependencies",
        "human_final_authority",
    }
    binding = st.get("roadmap_binding")
    if binding is None:
        if any(field in spec for field in roadmap_spec_fields):
            raise ValueError("persisted roadmap binding missing")
        return  # Pre-R1 state retained for backward-compatible recovery only.
    if not isinstance(binding, dict) or binding.get("schema_version") != 1:
        raise ValueError("persisted roadmap binding invalid")

    spec_dependencies = spec.get("dependencies")
    binding_dependencies = binding.get("dependencies")
    for dependencies in (spec_dependencies, binding_dependencies):
        if (
            not isinstance(dependencies, list)
            or not all(isinstance(value, str) for value in dependencies)
            or len(dependencies) != len(set(dependencies))
        ):
            raise ValueError("persisted roadmap binding dependencies invalid")

    manifest_sha256 = binding.get("manifest_sha256")
    if not isinstance(manifest_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256):
        raise ValueError("persisted roadmap binding manifest hash invalid")
    expected = {
        "repository": "cesarmanuel8102/AI_Vault",
        "integration_branch": "codex/own-capital-sustainable-return",
        "approval_status": "HUMAN_ADOPTED",
        "r0_status": "CLOSED_HUMAN_ADOPTED",
        "roadmap_id": spec.get("roadmap_id"),
        "roadmap_version": spec.get("roadmap_version"),
        "roadmap_item_id": spec.get("roadmap_item_id"),
        "roadmap_item_status": "AUTHORIZED_ACTIVE",
        "roadmap_sha256": spec.get("roadmap_sha256"),
        "base_sha": spec.get("expected_base_sha"),
        "dependencies": sorted(spec_dependencies),
        "manifest_path": ROADMAP_MANIFEST_PATH,
        "roadmap_path": "docs/roadmap/BRAIN_101_ROADMAP.md",
    }
    actual = dict(binding)
    actual["dependencies"] = sorted(binding_dependencies)
    if any(actual.get(key) != value for key, value in expected.items()):
        raise ValueError("persisted roadmap binding mismatch")

def parse_spec(issue: dict, cfg: dict) -> dict:
    author = (issue.get("author") or {}).get("login")
    if author != cfg["owner"]:
        raise ValueError(f"untrusted issue author: {author}")
    m = SPEC_RE.search(issue.get("body") or "")
    if not m:
        raise ValueError("AGENT_LOOP_SPEC missing")
    spec = json.loads(m.group(1))
    required = ["schema_version","front_id","repo","owner","base_branch","expected_base_sha",
                "work_branch","objective","test_profile","max_kimi_cycles","allowed_paths","forbidden_paths"]
    missing = [k for k in required if k not in spec]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    if spec["schema_version"] != 1:
        raise ValueError("unsupported schema_version")
    if not valid_front_id(spec["front_id"]):
        raise ValueError("invalid front_id")
    if spec["repo"] != cfg["repo"] or spec["owner"] != cfg["owner"]:
        raise ValueError("repo/owner mismatch")
    if spec["base_branch"] != cfg["base_branch"]:
        raise ValueError("base branch mismatch")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", str(spec["expected_base_sha"])):
        raise ValueError("expected_base_sha must be a full 40-character commit SHA")
    profile = str(spec["test_profile"])
    if profile not in PROFILE_ALLOWED_PATHS:
        raise ValueError("unknown test profile")
    if profile == "pilot" and profile not in cfg["test_profiles"]:
        raise ValueError("unknown test profile")
    if profile != "pilot" and not profile_command_is_trusted(profile, list(PROFILE_TRUSTED_COMMANDS[profile])):
        raise ValueError("unsafe internal test profile command")
    branch_prefix = PROFILE_BRANCH_PREFIXES[profile]
    if not spec["work_branch"].startswith(branch_prefix):
        if profile == "pilot":
            raise ValueError("pilot worker only accepts agent/pilot-* branches")
        raise ValueError(f"work branch must start with {branch_prefix}")
    if not (1 <= int(spec["max_kimi_cycles"]) <= int(cfg["max_kimi_cycles_default"])):
        raise ValueError("invalid max cycles")
    if not isinstance(spec["allowed_paths"], list) or not all(isinstance(x, str) for x in spec["allowed_paths"]):
        raise ValueError("allowed_paths must be a string list")
    if not isinstance(spec["forbidden_paths"], list) or not all(isinstance(x, str) for x in spec["forbidden_paths"]):
        raise ValueError("forbidden_paths must be a string list")
    allowed = {_normalize_repo_path(x) for x in spec["allowed_paths"]}
    if len(allowed) != len(spec["allowed_paths"]):
        raise ValueError("allowed_paths must not contain duplicates")
    if not profile_paths_are_trusted(profile, allowed):
        raise ValueError(f"allowed_paths do not match trusted profile {profile}")
    forbidden = {str(x).replace("\\", "/").strip().lstrip("./") for x in spec["forbidden_paths"]}
    if not REQUIRED_FORBIDDEN_PATHS.issubset(forbidden):
        raise ValueError("required forbidden paths are missing")
    spec["allowed_paths"] = sorted(allowed)
    return spec

def path_allowed(path: str, allowed: list[str], forbidden: list[str]) -> bool:
    norm = path.replace("\\", "/").lstrip("./")
    for f in forbidden:
        ff = f.replace("\\", "/").lstrip("./")
        if ff and (norm == ff or norm.startswith(ff.rstrip("/") + "/")): return False
    return norm in {x.replace("\\", "/").lstrip("./") for x in allowed}

def changed_files(repo_dir: Path, base_sha: str) -> list[str]:
    out = run(["git", "diff", "--name-only", base_sha], cwd=repo_dir)
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo_dir)
    return sorted({x.strip() for x in (out + "\n" + untracked).splitlines() if x.strip()})

def opencode_env(cfg: dict, repo_dir: Path, spec: dict | None = None) -> dict[str,str]:
    model = cfg["opencode_model"]
    # Preserve the user's existing OpenCode provider/auth configuration.
    # Override only the selected model and the worker permission boundary.
    strict_permissions = {
        "read":"allow", "edit":"allow", "glob":"allow", "grep":"allow", "list":"allow",
        "bash":"deny", "task":"deny", "external_directory":"deny", "webfetch":"deny",
        "websearch":"deny", "lsp":"deny", "skill":"deny", "question":"deny", "todowrite":"deny"
    }
    allowed_hint = ", ".join(sorted(str(x) for x in (spec or {}).get("allowed_paths", [])))
    agent_prompt = "Follow the user prompt exactly. The current directory is the workspace. Write files using only relative paths. Never use absolute paths, shell, network, subagents, skills, LSP, or external paths."
    if allowed_hint:
        agent_prompt += f" Allowed paths: {allowed_hint}."
    conf = {
        "$schema":"https://opencode.ai/config.json",
        "model":model,
        "permission":strict_permissions,
        "agent":{
            "brain-opencode-executor":{
                "description":"Writes exact allowlisted artifacts in a detached workspace.",
                "mode":"primary", "steps":30, "temperature":0.1, "model":model,
                "prompt":agent_prompt,
                "permission":strict_permissions
            }
        }
    }
    env = os.environ.copy()
    # Never expose GitHub/OpenAI credentials to OpenCode.
    for key in list(env):
        if key.upper() in {"GH_TOKEN","GITHUB_TOKEN","OPENAI_API_KEY"}: env.pop(key, None)
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(conf, separators=(",",":"))
    env["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] = str(cfg["opencode_output_token_max"])
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "true"
    return env

def discover_session_id(repo_dir: Path, title: str) -> str | None:
    try:
        data = json.loads(run(["opencode","session","list","--format","json","-n","50"], cwd=repo_dir))
    except Exception:
        return None
    items = data if isinstance(data, list) else data.get("sessions", []) if isinstance(data, dict) else []
    for item in items:
        if not isinstance(item, dict): continue
        if item.get("title") == title or item.get("name") == title:
            return item.get("id") or item.get("sessionID") or item.get("session_id")
    return None

def make_prompt(spec: dict, cycle: int, feedback: str | None = None) -> str:
    sentinel = prompt_task_sentinel(spec["front_id"], cycle)
    failure_sentinel = prompt_task_failure_sentinel(spec["front_id"], cycle)
    if spec.get("test_profile", "pilot") != "pilot":
        allowed = "\n".join(f"- {path}" for path in spec["allowed_paths"])
        base = f"""You are the OpenCode filesystem executor for {spec['front_id']}.
Complete only this objective: {spec['objective']}
The current workspace contains only explicitly allowlisted files and no Git metadata or credentials.
You may create or modify exactly these relative paths:
{allowed}
Do not create, delete, rename, or access any other path.
Your first required action is a write or edit tool call to an allowlisted path.
Make a real change to every allowlisted path and do not emit the acknowledgement before all writes complete.
Do not invoke shell, network, Git, GitHub, subagents, skills, LSP, or external directories.
After all write tools complete, output exactly this line and nothing else:
{sentinel}
If the write tool is unavailable or fails, output only this line:
{failure_sentinel}
This is cycle {cycle}.
"""
        if feedback:
            base += f"\nRepair only these verified failures:\n{feedback[:6000]}\n"
        return base
    base = f"""You are the OpenCode filesystem executor for {spec['front_id']}.
Your only job is to write exactly one file in the current workspace and then output the sentinel line.
The current workspace is the directory passed via --dir. It contains no Git metadata and no credentials.
Do not invoke a shell, commit, push, use gh, merge, or access external directories.
Allowed output path (relative to the current workspace, no leading '/' or drive letter): docs/agent_loop/pilot/PILOT_MARKER.md
Write that file with exactly this UTF-8 content:
{pilot_marker_text(spec["front_id"])}
Your first required action is to invoke the OpenCode write tool.
A text-only response is a failed attempt.
Do not output the success sentinel before the write tool reports completion.
After the tool completes, verify the exact relative path and then output the success sentinel.
After writing the file, output exactly this line and nothing else:
{sentinel}
If the write tool is unavailable or fails, output only this line:
{failure_sentinel}
Do not ask questions, do not run tools other than read/write for the allowed file, and do not create or edit any other file.
Do not create or edit EXECUTOR_REPORT.json; the trusted worker writes it after validation.
This is cycle {cycle}.
"""
    if feedback:
        base += f"\nRepair only these verified failures:\n{feedback[:6000]}\n"
    return base

_OPENCODE_RUN_HELP: str | None = None

def opencode_run_supports(flag: str, cwd: Path | None = None) -> bool:
    """Return whether the installed OpenCode CLI advertises a run flag.

    OpenCode CLI releases are not uniform. Some builds support --auto while
    others rely exclusively on agent permission policy. Detect support instead
    of assuming a specific release.
    """
    global _OPENCODE_RUN_HELP
    if _OPENCODE_RUN_HELP is None:
        _OPENCODE_RUN_HELP = run(["opencode", "run", "--help"], cwd=cwd, check=False)
    return flag in _OPENCODE_RUN_HELP

def _walk_workspace_files(root: Path) -> list[str]:
    files = []
    for path in root.rglob("*"):
        if _is_reparse_or_symlink(path):
            raise ModelWorkspaceScopeViolation("MODEL_WORKSPACE_LINK_DENIED")
        if path.is_file():
            files.append(path.relative_to(root).as_posix())
    return sorted(files)

def prepare_model_workspace(repo_dir: Path, spec: dict, cycle: int) -> tuple[Path, dict[str, str]]:
    """Create a no-.git workspace for the executor and seed only trusted, non-secret files."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    model_dir = repo_dir.parent / f"model-cycle-{cycle}-{stamp}-{os.getpid()}"
    model_dir.mkdir(parents=True, exist_ok=False)
    seed_hashes: dict[str, str] = {}
    seed_paths = set(MODEL_SEED_PATHS)
    if spec.get("test_profile", "pilot") != "pilot":
        seed_paths.update(rel for rel in spec["allowed_paths"] if (repo_dir / rel).is_file())
    for rel in sorted(seed_paths):
        src = repo_dir / rel
        if not src.is_file():
            raise RuntimeError(f"MODEL_SEED_MISSING:{rel}")
        if _is_reparse_or_symlink(src):
            raise ModelWorkspaceScopeViolation("MODEL_SEED_LINK_DENIED")
        dst = model_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        seed_hashes[rel] = sha256_file(dst)
    if spec.get("test_profile", "pilot") == "pilot":
        marker_rel = "docs/agent_loop/pilot/PILOT_MARKER.md"
        marker_src = repo_dir / marker_rel
        if marker_src.is_file():
            marker_dst = model_dir / marker_rel
            marker_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(marker_src, marker_dst)
    if (model_dir / ".git").exists():
        raise RuntimeError("MODEL_WORKSPACE_GIT_METADATA_PRESENT")
    return model_dir, seed_hashes

def audit_and_sync_model_workspace(model_dir: Path, repo_dir: Path, seed_hashes: dict[str, str], spec: dict | None = None) -> list[str]:
    """Reject metadata/extra writes, verify exact output, then copy only allowlisted output."""
    if (model_dir / ".git").exists():
        raise ModelWorkspaceScopeViolation("MODEL_WORKSPACE_GIT_METADATA_DENIED")
    try:
        files = set(_walk_workspace_files(model_dir))
    except ModelWorkspaceScopeViolation:
        raise
    if spec and spec.get("test_profile", "pilot") != "pilot":
        allowed = set(spec["allowed_paths"])
        extra = sorted(files - allowed)
        missing = sorted(set(seed_hashes) - files)
        if extra:
            raise ModelWorkspaceScopeViolation("MODEL_WORKSPACE_EXTRA_PATHS", count=len(extra))
        if missing:
            raise ModelWorkspaceScopeViolation("MODEL_WORKSPACE_DELETION_DENIED", count=len(missing))
        changed = sorted(
            rel for rel in files
            if rel not in seed_hashes or sha256_file(model_dir / rel) != seed_hashes[rel]
        )
        if set(changed) != allowed:
            raise ModelWorkspaceScopeViolation("MODEL_WORKSPACE_EXACT_DIFF_REQUIRED", count=len(changed))
        for rel in changed:
            destination = repo_dir / rel
            current = repo_dir
            for part in Path(rel).parts[:-1]:
                current = current / part
                if _is_reparse_or_symlink(current):
                    raise ModelWorkspaceScopeViolation("TRUSTED_OUTPUT_PARENT_LINK_DENIED")
            if _is_reparse_or_symlink(destination):
                raise ModelWorkspaceScopeViolation("TRUSTED_OUTPUT_LINK_DENIED")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((model_dir / rel).read_bytes())
        return changed
    marker_rel = "docs/agent_loop/pilot/PILOT_MARKER.md"
    expected = set(MODEL_SEED_PATHS) | {marker_rel}
    extra = sorted(files - expected)
    missing = sorted(expected - files)
    if extra:
        raise ModelWorkspaceScopeViolation("MODEL_WORKSPACE_EXTRA_PATHS", count=len(extra))
    if missing:
        raise RuntimeError(f"MODEL_WORKSPACE_BOUNDARY_FAILED missing={missing}")
    for rel, expected_hash in seed_hashes.items():
        if sha256_file(model_dir / rel) != expected_hash:
            raise ModelWorkspaceScopeViolation("MODEL_WORKSPACE_SEED_MODIFIED", count=1)
    marker = model_dir / marker_rel
    content = marker.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    # OpenCode write tools may omit the final newline while preserving every
    # contractual marker line. Canonicalize only that EOF representation.
    if not content.endswith("\n"):
        content += "\n"
    expected_front = (spec or {}).get("front_id", "PILOT-KIMI-CODEX-20260716-091529")
    expected_content = pilot_marker_text(expected_front)
    if content != expected_content:
        raise RuntimeError("PILOT_MARKER_CONTENT_MISMATCH")
    destination = repo_dir / marker_rel
    current = repo_dir
    for part in Path(marker_rel).parts[:-1]:
        current = current / part
        if _is_reparse_or_symlink(current):
            raise ModelWorkspaceScopeViolation("TRUSTED_OUTPUT_PARENT_LINK_DENIED")
    if _is_reparse_or_symlink(destination):
        raise ModelWorkspaceScopeViolation("TRUSTED_OUTPUT_LINK_DENIED")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(expected_content.encode("utf-8"))
    return [marker_rel]

def _require_lossless_opencode_transport() -> None:
    missing: list[str] = []
    if not _RUNTIME_EXECUTABLES.get("node"):
        missing.append("node_exe")
    if not _RUNTIME_EXECUTABLES.get("opencode_entrypoint"):
        missing.append("opencode_entrypoint")
    if missing:
        raise PreExecutionFailure(
            "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED",
            f"LOSSLESS_OPENCODE_TRANSPORT_REQUIRED: missing {', '.join(missing)}",
            {"command_identity": "opencode"},
        )


def _lossless_transport_or_raise(cmd: list[str], prepared):
    """Ensure the resolved opencode command bypasses cmd.exe for lossless transport."""
    if isinstance(prepared, str):
        raise PreExecutionFailure(
            "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED",
            "OpenCode execution resolved to a single command-line string; must use node.exe+JS entrypoint",
            {"resolved_identity": command_identity(cmd)},
        )
    if prepared and _runtime_command_name(str(prepared[0])) == "cmd":
        raise PreExecutionFailure(
            "LOSSLESS_OPENCODE_TRANSPORT_REQUIRED",
            "OpenCode execution resolved to cmd.exe; must use node.exe+JS entrypoint",
            {"resolved_identity": command_identity(cmd)},
        )


def safe_executor_error(exc: Exception) -> str:
    """Return a safe, fixed error description that never contains stdout, stderr, prompt, or raw argv."""
    if isinstance(exc, ExecutorAttemptConsumed):
        return {
            "EXECUTOR_TIMEOUT": "OpenCode execution exceeded the configured timeout. See governed local log.",
            "TOKEN_EXHAUSTED": "OpenCode execution ended because the runtime reported token, context, or rate-limit exhaustion. See governed local log.",
            "COMMAND_FAILED": "OpenCode process exited non-zero. See governed local log.",
            "EXECUTOR_JSONL_INVALID": "OpenCode produced invalid or empty JSONL output. See governed local log.",
            "TASK_NOT_ACKNOWLEDGED": "OpenCode output did not contain the required task acknowledgement. See governed local log.",
            "NO_OUTPUT_CHANGE": "OpenCode completed without modifying the allowlisted output file. See governed local log.",
            "NO_WRITE_TOOL_CALL": "OpenCode completed without invoking the required write tool. See governed local log.",
            "WRITE_TOOL_FAILED": "The required OpenCode write-tool invocation failed. See governed local log.",
            "WRITE_TOOL_NO_EFFECT": "The OpenCode write tool completed without changing the allowlisted output. See governed local log.",
            "EXECUTOR_DECLARED_WRITE_FAILURE": "OpenCode declared that it could not write the allowlisted output. See governed local log.",
        }.get(exc.failure_class, "OpenCode execution failed after the process started. See governed local log.")
    if isinstance(exc, PreExecutionFailure):
        return f"OpenCode could not start: {exc.failure_class}. See governed local log."
    return "OpenCode execution encountered an unexpected failure. See governed local log."


def run_kimi(cfg, spec, model_dir, issue_no, cycle, feedback=None, session_id=None):
    # Legacy function/event/schema names remain for v1.5.7 compatibility; they do not identify the configured model.
    report_dir = Path(cfg["install_root"]) / "reports"
    log = report_dir / f"issue-{issue_no}-cycle-{cycle}-opencode.jsonl"
    title = f"AI_Vault {spec['front_id']}"
    _require_lossless_opencode_transport()
    sentinel = prompt_task_sentinel(spec["front_id"], cycle)
    prompt = make_prompt(spec, cycle, feedback)
    if sentinel not in prompt:
        raise PreExecutionFailure(
            "TASK_NOT_ACKNOWLEDGED",
            "prompt missing sentinel",
            {"cycle": cycle, "front": spec["front_id"]},
        )
    cmd = ["opencode","run","--dir",str(model_dir),"--model",cfg["opencode_model"],
           "--agent","brain-opencode-executor","--format","json",
           "--title",title]
    if opencode_run_supports("--auto", cwd=model_dir):
        cmd.append("--auto")
    if session_id: cmd += ["--session", session_id]
    cmd.append(prompt)
    timeout = cfg.get("opencode_timeout_seconds")
    prepared = command_for_subprocess(cmd)
    _lossless_transport_or_raise(cmd, prepared)
    # All deterministic pre-execution validations have passed; the OpenCode process is about to start.
    event(cfg, "executor_started", front=spec["front_id"], issue=issue_no, cycle=cycle,
          command_identity="opencode", model=cfg["opencode_model"],
          prompt_bytes=len(prompt.encode("utf-8")), sentinel_in_prompt=True)
    try:
        p = subprocess.run(prepared, cwd=str(model_dir), env=opencode_env(cfg, model_dir, spec), text=False,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        out = (exc.output or b"").decode("utf-8", errors="replace")
        log.write_text(out, encoding="utf-8")
        raise ExecutorAttemptConsumed(
            "EXECUTOR_TIMEOUT",
            "OpenCode execution exceeded the configured timeout. See governed local log.",
            {"returncode": None, "command_identity": "opencode", "cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)},
        ) from None
    out, decoding = completed_output(p)
    log.write_text(out, encoding="utf-8")
    emit_subprocess_decoding_event(cfg, ["opencode"], decoding)
    if p.returncode != 0:
        low = out.lower()
        failure_class = "TOKEN_EXHAUSTED" if ("context" in low or "token" in low or "rate limit" in low) else "COMMAND_FAILED"
        safe = {
            "TOKEN_EXHAUSTED": "OpenCode execution ended because the runtime reported token, context, or rate-limit exhaustion. See governed local log.",
            "COMMAND_FAILED": "OpenCode process exited non-zero. See governed local log.",
        }[failure_class]
        raise ExecutorAttemptConsumed(
            failure_class,
            safe,
            {"returncode": p.returncode, "command_identity": "opencode", "cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)},
        )
    return log, discover_session_id(model_dir, title)

def _completed_tool_name(part: dict) -> str | None:
    if not isinstance(part, dict):
        return None
    return part.get("tool") if isinstance(part.get("tool"), str) else None


def _completed_tool_input(part: dict) -> dict:
    """Return the tool input dict from the real OpenCode tool event structure.

    Issue #19 demonstrates the input lives under part.state.input."""
    if not isinstance(part, dict):
        return {}
    state = part.get("state")
    if isinstance(state, dict):
        real_input = state.get("input")
        if isinstance(real_input, dict):
            return real_input
    return {}


def _completed_tool_target(part: dict) -> str:
    tool_input = _completed_tool_input(part)
    if not isinstance(tool_input, dict):
        return ""
    candidates = [
        tool_input.get("filePath"),
        tool_input.get("path"),
        tool_input.get("file_path"),
        tool_input.get("target"),
    ]
    for value in candidates:
        if isinstance(value, str):
            return value
    return ""


def _normalize_tool_target(target: str, model_dir: Path) -> str | None:
    """Return the allowlisted marker rel-path if target points exactly at the marker.

    Accepts both the exact POSIX relative path and an absolute Windows path that
    ends exactly in docs/agent_loop/pilot/PILOT_MARKER.md under the model_dir.
    """
    marker_rel = "docs/agent_loop/pilot/PILOT_MARKER.md"
    target_norm = target.replace("\\", "/").strip()
    if target_norm == marker_rel:
        return marker_rel
    model_marker = str((model_dir / marker_rel).resolve()).replace("\\", "/").lower()
    candidate_abs = str(Path(target).resolve()).replace("\\", "/").lower()
    if candidate_abs == model_marker:
        return marker_rel
    return None


def _normalize_allowed_tool_target(target: str, model_dir: Path, allowed: set[str]) -> str | None:
    target_norm = target.replace("\\", "/").strip()
    for rel in allowed:
        if target_norm == rel:
            return rel
        candidate = str(Path(target).resolve()).replace("\\", "/").lower()
        expected = str((model_dir / rel).resolve()).replace("\\", "/").lower()
        if candidate == expected:
            return rel
    return None


def _completed_write_targets(model_dir: Path, parsed: list[dict], allowed: set[str]) -> set[str]:
    write_tools = {"write", "write_file", "edit_file", "create_file", "edit"}
    completed: set[str] = set()
    for item in parsed:
        part = item.get("part") or item if isinstance(item, dict) else {}
        if not isinstance(part, dict) or part.get("type") != "tool":
            continue
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        if state.get("status") != "completed" or _completed_tool_name(part) not in write_tools:
            continue
        normalized = _normalize_allowed_tool_target(_completed_tool_target(part), model_dir, allowed)
        if normalized:
            completed.add(normalized)
    return completed


def _artifact_tool_completed_marker(model_dir: Path, spec: dict, parsed: list[dict]) -> tuple[bool, str]:
    """Return (True, input_schema) if a completed write tool targeted the allowlisted marker and the workspace is clean."""
    marker_rel = "docs/agent_loop/pilot/PILOT_MARKER.md"
    marker = model_dir / marker_rel
    if not marker.is_file() or marker.is_symlink():
        return False, ""
    expected_content = pilot_marker_text(spec["front_id"])
    actual_content = marker.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if actual_content != expected_content:
        return False, ""
    if any(p == ".." for p in marker.relative_to(model_dir).parts):
        return False, ""
    files = set(_walk_workspace_files(model_dir))
    expected_files = set(MODEL_SEED_PATHS) | {marker_rel}
    if files != expected_files:
        return False, ""
    write_tools = {"write", "write_file", "edit_file", "create_file", "edit"}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        part = item.get("part") or item
        if not isinstance(part, dict):
            continue
        if item.get("type") != "tool_use" and part.get("type") != "tool":
            continue
        state = part.get("state")
        if not isinstance(state, dict):
            continue
        if state.get("status") != "completed":
            continue
        tool_name = _completed_tool_name(part)
        if tool_name not in write_tools:
            continue
        target = _completed_tool_target(part)
        normalized = _normalize_tool_target(target, model_dir)
        if normalized == marker_rel:
            schema_used = "state.input" if isinstance((part.get("state") or {}).get("input"), dict) else "parameters"
            return True, schema_used
    return False, ""


def _executor_text_lines(parsed: list[dict]) -> list[str]:
    """Return normalized lines from model text parts only."""
    lines: list[str] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        part = item.get("part")
        if not isinstance(part, dict):
            text = item.get("text")
            if isinstance(text, str):
                lines.extend(line.strip() for line in text.splitlines() if line.strip())
            continue
        if (part.get("type") or item.get("type")) != "text":
            continue
        text = part.get("text")
        if isinstance(text, str):
            lines.extend(line.strip() for line in text.splitlines() if line.strip())
    return lines


def _write_tool_summary(model_dir: Path, parsed: list[dict]) -> dict:
    write_tools = {"write", "write_file", "edit_file", "create_file", "edit"}
    total = completed = failed = exact_targets = 0
    for item in parsed:
        if not isinstance(item, dict):
            continue
        part = item.get("part") or item
        if not isinstance(part, dict) or part.get("type") != "tool":
            continue
        if _completed_tool_name(part) not in write_tools:
            continue
        total += 1
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        status = str(state.get("status") or "").lower()
        if status == "completed":
            completed += 1
        elif status in {"error", "failed"}:
            failed += 1
        if _normalize_tool_target(_completed_tool_target(part), model_dir):
            exact_targets += 1
    return {
        "write_tool_events": total,
        "write_tool_completed": completed,
        "write_tool_failed": failed,
        "write_tool_exact_targets": exact_targets,
    }


def validate_executor_delivery(cfg: dict, spec: dict, model_dir: Path, log: Path, cycle: int, *, issue_no: int = 0, seed_hash: str | None = None) -> None:
    out = log.read_text(encoding="utf-8-sig")
    lines = [x.strip() for x in out.splitlines() if x.strip()]
    if not lines:
        raise ExecutorAttemptConsumed(
            "EXECUTOR_JSONL_INVALID",
            "empty output",
            {"cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)},
        )
    parsed: list[dict] = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except Exception as exc:
            raise ExecutorAttemptConsumed(
                "EXECUTOR_JSONL_INVALID",
                f"{exc}",
                {"cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)},
            ) from exc
    session_error_count = 0
    for item in parsed:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "error":
            session_error_count += 1
    sentinel = prompt_task_sentinel(spec["front_id"], cycle)
    failure_sentinel = prompt_task_failure_sentinel(spec["front_id"], cycle)
    text_lines = _executor_text_lines(parsed)
    text_acknowledged = sentinel in text_lines
    declared_write_failure = failure_sentinel in text_lines
    full_output = "\n".join(text_lines)
    lowered = full_output.lower()
    refused = any(pattern in lowered for pattern in _CONVERSATIONAL_REJECTION_PATTERNS)
    if spec.get("test_profile", "pilot") != "pilot":
        allowed = set(spec["allowed_paths"])
        completed_targets = _completed_write_targets(model_dir, parsed, allowed)
        workspace_files = set(_walk_workspace_files(model_dir))
        acknowledged = sentinel in text_lines and not declared_write_failure
        event(cfg, "executor_completed", front=spec["front_id"], issue=issue_no, cycle=cycle,
              task_acknowledged=acknowledged, ack_source="text_sentinel" if acknowledged else "none",
              conversational_refusal=refused, jsonl_events=len(parsed),
              session_error_count=session_error_count, declared_write_failure=declared_write_failure,
              write_tool_completed=len(completed_targets), write_tool_exact_targets=len(completed_targets))
        if declared_write_failure:
            raise ExecutorAttemptConsumed("EXECUTOR_DECLARED_WRITE_FAILURE", "executor declared write failure",
                                          {"cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)})
        if not acknowledged or refused or session_error_count:
            raise ExecutorAttemptConsumed("TASK_NOT_ACKNOWLEDGED", "executor did not complete the governed profile task",
                                          {"cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)})
        if workspace_files != allowed or completed_targets != allowed:
            raise ExecutorAttemptConsumed("PROFILE_WRITE_CONTRACT_FAILED", "executor did not write every exact allowlisted profile path",
                                          {"cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)})
        return
    marker = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
    unchanged = False
    if seed_hash is not None and marker.is_file():
        unchanged = sha256_file(marker) == seed_hash
    artifact_tool_completed, tool_input_schema = _artifact_tool_completed_marker(model_dir, spec, parsed)
    artifact_acknowledged = (
        artifact_tool_completed
        and session_error_count == 0
        and (seed_hash is None or sha256_file(marker) != seed_hash)
    )
    write_summary = _write_tool_summary(model_dir, parsed)
    output_changed = marker.is_file() and (seed_hash is None or sha256_file(marker) != seed_hash)
    acknowledged = not declared_write_failure and (text_acknowledged or artifact_acknowledged)
    ack_source = (
        "declared_write_failure" if declared_write_failure else
        "text_sentinel" if text_acknowledged else
        "verified_artifact_tool" if artifact_acknowledged else
        "none"
    )
    event_fields = {
        "front": spec["front_id"], "issue": issue_no, "cycle": cycle,
        "task_acknowledged": acknowledged, "ack_source": ack_source,
        "conversational_refusal": refused, "marker_unchanged": unchanged,
        "jsonl_events": len(parsed), "session_error_count": session_error_count,
        "declared_write_failure": declared_write_failure,
        **write_summary,
    }
    if artifact_acknowledged and tool_input_schema:
        event_fields["tool_input_schema"] = tool_input_schema
    event(cfg, "executor_completed", **event_fields)
    if declared_write_failure:
        raise ExecutorAttemptConsumed(
            "EXECUTOR_DECLARED_WRITE_FAILURE",
            "executor declared write failure",
            {"cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)},
        )
    if not acknowledged:
        raise ExecutorAttemptConsumed(
            "TASK_NOT_ACKNOWLEDGED",
            "OpenCode output did not contain the required task acknowledgement and no verified artifact tool completed the allowlisted marker.",
            {"cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)},
        )
    if refused:
        raise ExecutorAttemptConsumed(
            "TASK_NOT_ACKNOWLEDGED",
            "executor issued conversational refusal",
            {"cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)},
        )
    if not output_changed:
        if write_summary["write_tool_events"] == 0:
            failure_class = "NO_WRITE_TOOL_CALL"
        elif write_summary["write_tool_failed"]:
            failure_class = "WRITE_TOOL_FAILED"
        else:
            failure_class = "WRITE_TOOL_NO_EFFECT"
        raise ExecutorAttemptConsumed(
            failure_class,
            "executor did not modify the pilot marker",
            {"cycle": cycle, "front": spec["front_id"], "local_log_path": str(log)},
        )

def run_profile(cfg, spec, repo_dir) -> tuple[bool,str]:
    profile = spec["test_profile"]
    configured = cfg["test_profiles"][profile] if profile == "pilot" else PROFILE_TRUSTED_COMMANDS[profile]
    cmd = [str(x) for x in configured]
    if spec["test_profile"] == "pilot":
        cmd += ["--expected-front-id", str(spec["front_id"])]
    elif spec["test_profile"] == "roadmap-doc":
        cmd += [spec["expected_base_sha"], "--", *spec["allowed_paths"]]
    elif spec["test_profile"] == "test-only":
        # Never execute model-authored tests on the worker host. Behavioral
        # execution belongs to the isolated CI and Codex review boundary.
        validated: list[str] = []
        for rel in spec["allowed_paths"]:
            path = Path(repo_dir) / rel
            if not path.is_file() or _is_reparse_or_symlink(path):
                return False, "TEST_ONLY_SOURCE_INVALID"
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            except (OSError, UnicodeError, SyntaxError) as exc:
                return False, f"TEST_ONLY_SYNTAX_INVALID:{rel}:{type(exc).__name__}"
            validated.append(rel)
        return True, f"TEST_ONLY_AST_VALIDATED:{len(validated)}"
    commands = [cmd]
    outputs: list[str] = []
    timeout = int(cfg.get("profile_timeout_seconds", 300))
    for current in commands:
        try:
            p = subprocess.run(command_for_subprocess(current), cwd=str(repo_dir), text=False,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, "PROFILE_COMMAND_TIMEOUT"
        out, decoding = completed_output(p)
        outputs.append(out)
        emit_subprocess_decoding_event(cfg, current, decoding)
        if p.returncode != 0:
            return False, "\n".join(outputs)
    return True, "\n".join(outputs)

def bounded_tail(text: str, limit: int = 3000) -> str:
    return (text or "")[-limit:]

def marker_hash(repo_dir: Path) -> str | None:
    marker = repo_dir / "docs/agent_loop/pilot/PILOT_MARKER.md"
    return sha256_file(marker) if marker.is_file() else None

def run_marker_content_check(repo_dir: Path, expected_front_id: str) -> tuple[bool, str]:
    cmd = [sys.executable, "scripts/agent_loop/pilot_verify.py", "--local", "--content-only",
           "--expected-front-id", str(expected_front_id)]
    p = subprocess.run(command_for_subprocess(cmd), cwd=str(repo_dir), text=False,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = completed_output(p)
    return p.returncode == 0, out

def run_final_verifier(repo_dir: Path, base_sha: str, head_sha: str, expected_front_id: str) -> tuple[bool, str]:
    cmd = [sys.executable, "scripts/agent_loop/pilot_verify.py", "--base-sha", base_sha, "--head-sha", head_sha,
           "--expected-front-id", str(expected_front_id)]
    p = subprocess.run(command_for_subprocess(cmd), cwd=str(repo_dir), text=False,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = completed_output(p)
    return p.returncode == 0, out

def write_executor_report(cfg, spec, repo_dir, issue_no, cycle, changes, test_ok, test_out, log_path, state=None):
    p = repo_dir / "docs/agent_loop/pilot/EXECUTOR_REPORT.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    executor_evidence = build_executor_review_evidence(log_path, spec, cycle)
    data = {
        "schema_version":1,"worker_version":WORKER_VERSION,"front_id":spec["front_id"],"issue_number":issue_no,
        "cycle":cycle,"executor":"OpenCode/Ollama tool executor","agent":"brain-opencode-executor",
        "model":cfg["opencode_model"],
        "base_sha":spec["expected_base_sha"],"changed_files":sorted({"docs/agent_loop/pilot/PILOT_MARKER.md", "docs/agent_loop/pilot/EXECUTOR_REPORT.json"}),
        "local_test_profile":spec["test_profile"],"local_test_passed":test_ok,
        "local_test_tail":bounded_tail(test_out),"opencode_log_local":str(log_path),
        "executor_evidence":executor_evidence,
        "generated_utc":utc(),"merge_performed":False,"canonical_local_sync":False,
        "live_trading_enabled":False,
    }
    roadmap_fields = {
        "roadmap_id", "roadmap_version", "roadmap_sha256", "roadmap_item_id",
        "dependencies", "human_final_authority",
    }
    if any(field in spec for field in roadmap_fields):
        if not isinstance(state, dict):
            raise ValueError("validated roadmap state required for executor report")
        validate_persisted_roadmap_binding(state)
        if state["spec"].get("human_final_authority") is not True:
            raise ValueError("human final authority must be true")
        binding = state["roadmap_binding"]
        data["roadmap_binding"] = {
            key: copy.deepcopy(binding[key])
            for key in (
                "repository", "integration_branch", "approval_status", "r0_status",
                "roadmap_id", "roadmap_version", "roadmap_item_id", "roadmap_sha256",
                "roadmap_item_status", "manifest_sha256", "base_sha", "dependencies",
            )
        }
        data["human_final_authority"] = state["spec"]["human_final_authority"]
    save_json(p, data)


def build_executor_review_evidence(log_path: Path, spec: dict, cycle: int) -> dict:
    """Extract bounded, reviewable proof from the governed OpenCode JSONL log."""
    parsed: list[dict] = []
    for line in Path(log_path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            parsed.append(json.loads(line))

    sentinel = prompt_task_sentinel(spec["front_id"], cycle)
    text_acknowledged = sentinel in _executor_text_lines(parsed)
    marker_rel = "docs/agent_loop/pilot/PILOT_MARKER.md"
    write_tools = {"write", "write_file", "edit_file", "create_file", "edit"}
    relative_write_completed = False
    completed_tool = ""
    for item in parsed:
        if not isinstance(item, dict):
            continue
        part = item.get("part") or item
        if not isinstance(part, dict) or part.get("type") != "tool":
            continue
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        tool_name = _completed_tool_name(part) or ""
        target = _completed_tool_target(part).replace("\\", "/").strip()
        if state.get("status") == "completed" and tool_name in write_tools and target == marker_rel:
            relative_write_completed = True
            completed_tool = tool_name
            break

    return {
        "source": "worker_parsed_opencode_jsonl",
        "log_sha256": sha256_file(Path(log_path)),
        "task_acknowledged": text_acknowledged,
        "task_ack": sentinel if text_acknowledged else "",
        "ack_source": "text_sentinel" if text_acknowledged else "none",
        "write_tool_completed": relative_write_completed,
        "write_tool_name": completed_tool,
        "write_tool_target": marker_rel if relative_write_completed else "",
        "write_tool_target_kind": "relative" if relative_write_completed else "none",
    }

def sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def run_preflight(cfg: dict) -> dict:
    """Validate deterministic local dependencies without spending model tokens."""
    checks = {}
    resolved = configure_runtime_resolution(cfg, require_config=True)
    for name in ("git", "gh", "python", "opencode", "cmd"):
        checks[name] = {"ok": name in resolved, "path": resolved.get(name)}
    min_versions = cfg.get("runtime_min_versions") or {}
    version_commands = {
        "git": ["git", "--version"],
        "gh": ["gh", "--version"],
        "python": ["python", "--version"],
        "opencode": ["opencode", "--version"],
    }
    for name, command in version_commands.items():
        if name not in resolved:
            continue
        out = run(command, check=False)
        expected = min_versions.get(name)
        checks[f"{name}_version"] = {
            "ok": _safe_version_at_least(out, expected) if expected else True,
            "minimum": expected,
            "output": bounded_tail(out, 500),
        }
    gh_status = subprocess.run(command_for_subprocess(["gh", "auth", "status"]), text=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    gh_out, _ = completed_output(gh_status)
    emit_subprocess_decoding_event(cfg, ["gh", "auth", "status"], _)
    checks["gh_auth"] = {"ok": gh_status.returncode == 0, "tail": gh_out[-1000:]}
    models = run(["opencode", "models"], check=False)
    checks["opencode_model"] = {"ok": cfg["opencode_model"] in models, "model": cfg["opencode_model"]}
    ok = all(bool(v.get("ok")) for v in checks.values())
    report = {"schema_version": 1, "worker_version": WORKER_VERSION, "status": "PASS" if ok else "FAIL", "checks": checks, "generated_utc": utc()}
    out = Path(cfg["install_root"]) / "reports" / "worker-preflight.json"
    save_json(out, report)
    if not ok:
        raise RuntimeError("PREFLIGHT_FAILED:" + json.dumps(checks, ensure_ascii=False))
    return report

def cleanup_stale_workspaces(cfg: dict) -> None:
    retention_days = int(cfg.get("workspace_retention_days", 7))
    runs_root = Path(cfg["install_root"]) / "runs"
    if not runs_root.exists():
        return
    cutoff = time.time() - retention_days * 86400
    active_paths = set()
    state_dir = Path(cfg["install_root"]) / "state"
    for state_path in state_dir.glob("issue-*.json"):
        try:
            st = load_json(state_path)
            if not str(st.get("status", "")).startswith("loop:") and st.get("repo_dir"):
                active_paths.add(str(Path(st["repo_dir"]).parent.resolve()))
        except Exception:
            pass
    for child in runs_root.iterdir():
        try:
            if not child.is_dir() or str(child.resolve()) in active_paths or child.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(child)
            event(cfg, "workspace_cleaned", workspace=str(child))
        except Exception as exc:
            event(cfg, "workspace_cleanup_preserved", workspace=str(child), error=str(exc))

def write_final_local_report(cfg: dict, spec: dict, issue_no: int, cycle: int, repo_dir: Path, pr: dict) -> Path:
    head_sha = run(["git", "rev-parse", "HEAD"], cwd=repo_dir).strip()
    diff_names = [x for x in run(["git", "diff", "--name-only", f"{spec['expected_base_sha']}..{head_sha}"], cwd=repo_dir).splitlines() if x.strip()]
    status = run(["git", "status", "--porcelain"], cwd=repo_dir)
    report = {
        "schema_version": 1,
        "worker_version": WORKER_VERSION,
        "worker_sha256": sha256_file(Path(__file__)),
        "front_id": spec["front_id"],
        "issue_number": issue_no,
        "pr_number": pr["number"],
        "pr_url": pr["url"],
        "cycle": cycle,
        "base_sha": spec["expected_base_sha"],
        "head_sha": head_sha,
        "remote_head_sha": pr["headRefOid"],
        "same_head": head_sha == pr["headRefOid"],
        "final_changed_files": sorted(diff_names),
        "working_tree_clean": status.strip() == "",
        "merge_performed": False,
        "canonical_local_sync": False,
        "generated_utc": utc(),
    }
    path = Path(cfg["install_root"]) / "reports" / f"issue-{issue_no}-final-local.json"
    save_json(path, report)
    return path

def classify_error(exc: Exception) -> str:
    text = str(exc).lower()
    if any(x in text for x in ("token_exhausted", "max_cycles", "rate limit", "context length")):
        return "loop:token-exhausted"
    permanent = (
        "winerror 2", "unknown option", "unrecognized", "base moved", "untrusted issue author",
        "repo/owner mismatch", "base branch mismatch", "agent_loop_spec missing", "missing fields",
        "invalid max cycles", "unknown test profile", "prefight_failed", "preflight_failed",
        "out-of-scope", "not allowlisted"
    )
    if any(x in text for x in permanent):
        return "loop:blocked"
    return "RETRY"

def terminalize_state_error(cfg: dict, state_path: Path, exc: Exception) -> None:
    st = load_json(state_path)
    issue = int(st["issue_number"])
    classification = classify_error(exc)
    retries = int(st.get("local_retry_count", 0)) + 1
    max_retries = int(cfg.get("max_local_retries", 2))
    st["local_retry_count"] = retries
    st["error"] = str(exc)[-5000:]
    st["updated_utc"] = utc()
    if classification == "RETRY" and retries <= max_retries:
        st["status"] = "LOCAL_RETRY"
        save_json(state_path, st)
        event(cfg, "state_retry_scheduled", state=str(state_path), issue=issue, retry=retries, max_retries=max_retries, error=str(exc))
        return
    phase = classification if classification != "RETRY" else "loop:blocked"
    st = set_converged_phase(cfg, state_path, st, phase)
    st = publish_terminal_notification(cfg, state_path, st, phase, str(exc))
    event(cfg, "state_terminalized", state=str(state_path), issue=issue, phase=phase,
          failure_class=classification, error=str(exc))

def prepare_repo(cfg, spec, issue_no):
    # Never require deletion of a previous Git checkout on Windows. Git pack files can
    # remain temporarily locked by Git, antivirus, indexing, or an interrupted child
    # process. Every attempt therefore receives an immutable, generation-specific
    # workspace. Stale workspaces are retained for later best-effort cleanup.
    runs_root = Path(cfg["install_root"]) / "runs"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_root = runs_root / f"issue-{issue_no}-{stamp}-{os.getpid()}"
    repo_dir = run_root / "repo"
    run_root.mkdir(parents=True, exist_ok=False)
    event(cfg, "workspace_created", issue=issue_no, workspace=str(run_root))
    run(["gh","repo","clone",cfg["repo"],str(repo_dir),"--","--no-checkout"])
    run(["git","fetch","origin",spec["base_branch"]], cwd=repo_dir)
    remote_sha = run(["git","rev-parse",f"origin/{spec['base_branch']}"],cwd=repo_dir).strip()
    if remote_sha != spec["expected_base_sha"]:
        raise ValueError(f"base moved: expected {spec['expected_base_sha']} actual {remote_sha}")
    run(["git","checkout","-B",spec["work_branch"],remote_sha], cwd=repo_dir)
    run(["git","config","user.name","AI Vault OpenCode Worker"],cwd=repo_dir)
    run(["git","config","user.email","ai-vault-worker@users.noreply.github.com"],cwd=repo_dir)
    return repo_dir

def latest_feedback(repo: str, pr_no: int, spec: dict, head_sha: str, install_root: str) -> str:
    runs = gh_json(["run","list","--repo",repo,"--workflow","agent-loop-pilot.yml",
                    "--branch",spec["work_branch"],"--event","pull_request","--limit","20",
                    "--json","databaseId,headSha,status,conclusion,createdAt,url"])
    run_item = next((r for r in runs if r.get("headSha") == head_sha and r.get("status") == "completed"), None)
    if not run_item:
        return "GitHub gate requested repair but no completed workflow run was found for the current HEAD."
    run_id = str(run_item["databaseId"])
    temp = Path(tempfile.mkdtemp(prefix="codex-feedback-", dir=str(Path(install_root)/"reports")))
    try:
        p = subprocess.run(command_for_subprocess(["gh","run","download",run_id,"--repo",repo,"--name","codex-supervisor-report","--dir",str(temp)]),
                           text=False,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        _, decoding = completed_output(p)
        emit_subprocess_decoding_event({"install_root": install_root}, ["gh", "run", "download"], decoding)
        if p.returncode == 0:
            candidates=list(temp.rglob("codex-output.json"))
            if candidates:
                return "CODEX SUPERVISOR REPORT:\n" + candidates[0].read_text(encoding="utf-8-sig")[:8000]
        logs = run(["gh","run","view",run_id,"--repo",repo,"--log-failed"],check=False)
        return "GITHUB FAILED CHECK LOGS:\n" + logs[-8000:]
    finally:
        shutil.rmtree(temp,ignore_errors=True)

def create_pr(cfg, spec, issue_no, repo_dir):
    run(["git","push","-u","origin",spec["work_branch"]],cwd=repo_dir)
    body = f"""AGENT_LOOP_FRONT: {spec['front_id']}
AGENT_LOOP_ISSUE: #{issue_no}
EXPECTED_BASE_SHA: {spec['expected_base_sha']}
EXECUTOR_MODEL: {cfg['opencode_model']}
AGENT_LOOP_PROFILE: {spec['test_profile']}

Automated governed change. No auto-merge. The configured OpenCode/Ollama executor writes; Codex supervises read-only; human audit is final.
"""
    url = run(["gh","pr","create","--repo",cfg["repo"],"--base",spec["base_branch"],"--head",spec["work_branch"],
               "--draft","--title",f"test(agent-loop): {spec['front_id']}","--body",body],cwd=repo_dir).strip()
    pr = gh_json(["pr","view",url,"--repo",cfg["repo"],"--json","number,url,headRefOid"])
    return pr

_TASK_NOT_ACKNOWLEDGED_FEEDBACK = "The prior executor attempt did not emit the required task acknowledgement. Write the exact allowlisted marker and complete the required acknowledgement. Do not create any other file."


def _is_within_install_root(path: Path, install_root: Path) -> bool:
    try:
        path.resolve().relative_to(install_root.resolve())
        return True
    except Exception:
        return False


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        stat_result = os.lstat(str(path))
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return bool(getattr(stat_result, "st_reparse_tag", 0))


def _workspace_is_trusted(repo_dir: Path, cfg: dict, spec: dict) -> bool:
    install_root = Path(cfg["install_root"]).resolve()
    if not repo_dir.is_dir() or _is_reparse_or_symlink(repo_dir):
        return False
    if not _is_within_install_root(repo_dir, install_root / "runs"):
        return False
    try:
        head = run(["git", "rev-parse", "HEAD"], cwd=repo_dir).strip()
        base = run(["git", "merge-base", "HEAD", spec["expected_base_sha"]], cwd=repo_dir).strip()
    except Exception:
        return False
    if base != spec["expected_base_sha"]:
        return False
    changes = changed_files(repo_dir, spec["expected_base_sha"])
    return all(path_allowed(p, spec["allowed_paths"], spec["forbidden_paths"]) for p in changes)


def _safe_feedback_for_failure(failure_class: str) -> str | None:
    if failure_class in _WRITE_FAILURE_FEEDBACK:
        return _WRITE_FAILURE_FEEDBACK[failure_class]
    if failure_class == "NO_OUTPUT_CHANGE":
        return _WRITE_FAILURE_FEEDBACK["NO_WRITE_TOOL_CALL"]
    if failure_class == "TASK_NOT_ACKNOWLEDGED":
        return _TASK_NOT_ACKNOWLEDGED_FEEDBACK
    if failure_class == "EXECUTOR_DELIVERY_ACCEPTED_PENDING_LOCAL_GATES":
        return "The prior executor delivery passed governed acknowledgement. Complete the remaining allowlisted artifact and satisfy the configured test profile. Do not create any other file."
    if failure_class == "INITIAL_WORKSPACE_AUDIT_FAILED":
        return "The prior candidate failed the governed workspace audit. Recreate only the exact allowlisted files and marker. Do not create any other file."
    if failure_class == "INITIAL_LOCAL_GATE_FAILED":
        return "The prior candidate failed governed local validation. Correct only the allowlisted pilot artifacts and satisfy the configured test profile."
    if failure_class == "INITIAL_OUT_OF_SCOPE_PATHS":
        return "Out-of-scope changes were detected in the governed workspace. Human audit is required."
    return None


def _failure_requires_fresh_session(failure_class: str) -> bool:
    return failure_class in _WRITE_RETRY_FAILURE_CLASSES


def _checkpoint_initial_cycle(cfg: dict, state_path: Path, issue_no: int, spec: dict, repo_dir: Path,
                              cycle: int, session_id: str | None, failure_class: str, safe_error: str) -> None:
    """Atomically persist that an initial cycle has started before downstream gates run."""
    st = load_json(state_path)
    st.update({
        "issue_number": issue_no,
        "front": spec["front_id"],
        "spec": spec,
        "repo_dir": str(repo_dir),
        "cycles": cycle,
        "opencode_session_id": session_id,
        "status": "loop:executing",
        "error": safe_error,
        "updated_utc": utc(),
        "worker_version": WORKER_VERSION,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "last_failure_class": failure_class,
    })
    save_json(state_path, st)


def execute_initial(cfg, issue, spec, state_path):
    n = issue["number"]
    set_phase(cfg["repo"], n, "loop:executing")
    st = load_json(state_path)
    persisted_cycles = int(st.get("cycles", 0))
    session_id = st.get("opencode_session_id") or None
    last_failure_class = str(st.get("last_failure_class") or "")
    if _failure_requires_fresh_session(last_failure_class):
        session_id = None
    feedback = _safe_feedback_for_failure(last_failure_class)
    max_cycles = int(spec["max_kimi_cycles"])

    if persisted_cycles >= max_cycles:
        safe_error = "Maximum executor cycles reached without success. Human audit required."
        st.update({"issue_number": n, "front": spec["front_id"], "spec": spec,
                   "cycles": persisted_cycles, "opencode_session_id": session_id,
                   "status": "loop:token-exhausted", "error": safe_error,
                   "updated_utc": utc(), "worker_version": WORKER_VERSION,
                   "state_schema_version": STATE_SCHEMA_VERSION})
        st = set_converged_phase(cfg, state_path, st, "loop:token-exhausted")
        st = publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", safe_error)
        event(cfg, "state_terminalized", state=str(state_path), issue=n, phase="loop:token-exhausted",
              failure_class="MAX_CYCLES_REACHED", error=safe_error)
        return

    repo_dir = None
    if persisted_cycles > 0:
        persisted_repo_dir = Path(str(st.get("repo_dir") or ""))
        if not _workspace_is_trusted(persisted_repo_dir, cfg, spec):
            safe_error = "Initial retry workspace is unavailable or not trustworthy; cannot resume without human audit."
            st.update({"issue_number": n, "front": spec["front_id"], "spec": spec,
                       "cycles": persisted_cycles, "opencode_session_id": session_id, "status": "loop:blocked",
                       "error": safe_error, "updated_utc": utc(), "worker_version": WORKER_VERSION,
                       "state_schema_version": STATE_SCHEMA_VERSION, "last_failure_class": "INITIAL_RETRY_WORKSPACE_UNAVAILABLE"})
            st = set_converged_phase(cfg, state_path, st, "loop:blocked")
            st = publish_terminal_notification(cfg, state_path, st, "loop:blocked", safe_error)
            event(cfg, "state_terminalized", state=str(state_path), issue=n, phase="loop:blocked",
                  failure_class="INITIAL_RETRY_WORKSPACE_UNAVAILABLE", error=safe_error)
            return
        repo_dir = persisted_repo_dir
    else:
        repo_dir = prepare_repo(cfg, spec, n)

    for cycle in range(persisted_cycles + 1, max_cycles + 1):
        event(cfg,"kimi_cycle_start",issue=n,cycle=cycle,front=spec["front_id"])
        model_dir, seed_hashes = prepare_model_workspace(repo_dir, spec, cycle)
        marker_seed = None
        if spec["test_profile"] == "pilot":
            marker_path = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
            marker_seed = sha256_file(marker_path) if marker_path.is_file() else None
        try:
            log, discovered_session = run_kimi(cfg,spec,model_dir,n,cycle,feedback,session_id)
            if discovered_session: session_id = discovered_session
            validate_executor_delivery(cfg, spec, model_dir, log, cycle, issue_no=n, seed_hash=marker_seed)
        except PreExecutionFailure as exc:
            safe_error = safe_executor_error(exc)
            event(cfg, "executor_preflight_failed", front=spec["front_id"], issue=n, pr=None, cycle=cycle,
                  failure_class=exc.failure_class, command_identity=exc.details.get("command_identity") or "opencode",
                  local_log_path=exc.details.get("local_log_path"), worker_version=WORKER_VERSION)
            st = load_json(state_path)
            st.update({"issue_number": n, "front": spec["front_id"], "spec": spec, "repo_dir": str(repo_dir),
                       "cycles": cycle - 1, "opencode_session_id": session_id, "status": "loop:blocked",
                       "error": safe_error, "updated_utc": utc(), "worker_version": WORKER_VERSION,
                       "state_schema_version": STATE_SCHEMA_VERSION})
            st = set_converged_phase(cfg, state_path, st, "loop:blocked")
            st = publish_terminal_notification(cfg, state_path, st, "loop:blocked", safe_error)
            event(cfg, "state_terminalized", state=str(state_path), issue=n, phase="loop:blocked",
                  failure_class=exc.failure_class, error=safe_error)
            return
        except ExecutorAttemptConsumed as exc:
            safe_error = safe_executor_error(exc)
            event(cfg, "executor_failed", front=spec["front_id"], issue=n, pr=None, cycle=cycle,
                  error=safe_error, failure_class=exc.failure_class,
                  local_log_path=exc.details.get("local_log_path"), returncode=exc.details.get("returncode"),
                  command_identity=exc.details.get("command_identity") or "opencode")
            if cycle >= int(spec["max_kimi_cycles"]):
                st = load_json(state_path)
                st.update({"issue_number": n, "front": spec["front_id"], "spec": spec, "repo_dir": str(repo_dir),
                           "cycles": cycle, "opencode_session_id": session_id, "status": "loop:token-exhausted",
                           "error": safe_error, "updated_utc": utc(), "worker_version": WORKER_VERSION,
                           "state_schema_version": STATE_SCHEMA_VERSION})
                st = set_converged_phase(cfg, state_path, st, "loop:token-exhausted")
                st = publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum executor cycles reached. Human audit required.")
                event(cfg, "local_gate_failed", issue=n, pr=None, cycle=cycle,
                      failure_class=exc.failure_class, cycle_before=cycle-1, cycle_after=cycle,
                      changed_files=[], test_output_tail=safe_error,
                      marker_hash=marker_hash(repo_dir), current_head=run(["git","rev-parse","HEAD"], cwd=repo_dir).strip(),
                      expected_base=spec["expected_base_sha"], bad=[], test_ok=False)
                event(cfg, "state_terminalized", state=str(state_path), issue=n, phase="loop:token-exhausted",
                      failure_class=exc.failure_class, cycle=cycle, error=safe_error)
                return
            feedback = _safe_feedback_for_failure(exc.failure_class)
            if _failure_requires_fresh_session(exc.failure_class):
                session_id = None
            _checkpoint_initial_cycle(cfg, state_path, n, spec, repo_dir, cycle, session_id,
                                      exc.failure_class, safe_error)
            continue

        _checkpoint_initial_cycle(cfg, state_path, n, spec, repo_dir, cycle, session_id,
                                  "EXECUTOR_DELIVERY_ACCEPTED_PENDING_LOCAL_GATES",
                                  "Executor delivery passed; governed local gates are pending.")
        try:
            audit_and_sync_model_workspace(model_dir, repo_dir, seed_hashes, spec)
        except ModelWorkspaceScopeViolation as exc:
            safe_error = "Out-of-scope changes were detected in the governed workspace. Human audit is required."
            _checkpoint_initial_cycle(cfg, state_path, n, spec, repo_dir, cycle, session_id,
                                      "INITIAL_OUT_OF_SCOPE_PATHS", safe_error)
            st = load_json(state_path)
            st.update({
                "issue_number": n, "front": spec["front_id"], "spec": spec,
                "repo_dir": str(repo_dir), "cycles": cycle, "opencode_session_id": session_id,
                "status": "loop:blocked", "error": safe_error, "updated_utc": utc(),
                "worker_version": WORKER_VERSION, "state_schema_version": STATE_SCHEMA_VERSION,
                "last_failure_class": "INITIAL_OUT_OF_SCOPE_PATHS",
            })
            save_json(state_path, st)
            st = set_converged_phase(cfg, state_path, st, "loop:blocked")
            event(cfg, "local_gate_failed", issue=n, pr=None, cycle=cycle,
                  failure_class="INITIAL_OUT_OF_SCOPE_PATHS", cycle_before=cycle-1, cycle_after=cycle,
                  scope_reason=exc.reason_code, bad_count=exc.count, test_ok=False)
            st = publish_terminal_notification(cfg, state_path, st, "loop:blocked", safe_error)
            event(cfg, "state_terminalized", state=str(state_path), issue=n, phase="loop:blocked",
                  failure_class="INITIAL_OUT_OF_SCOPE_PATHS", error=safe_error)
            return
        except Exception:
            safe_error = "The prior candidate failed the governed workspace audit."
            feedback = _safe_feedback_for_failure("INITIAL_WORKSPACE_AUDIT_FAILED")
            event(cfg,"kimi_cycle_repair_needed",issue=n,cycle=cycle,bad=[],test_ok=False)
            _checkpoint_initial_cycle(cfg, state_path, n, spec, repo_dir, cycle, session_id,
                                      "INITIAL_WORKSPACE_AUDIT_FAILED", safe_error)
            continue
        changes = changed_files(repo_dir,spec["expected_base_sha"])
        bad = [p for p in changes if not path_allowed(p,spec["allowed_paths"],spec["forbidden_paths"])]
        if bad:
            safe_error = "Out-of-scope changes were detected in the governed workspace. Human audit is required."
            _checkpoint_initial_cycle(cfg, state_path, n, spec, repo_dir, cycle, session_id,
                                      "INITIAL_OUT_OF_SCOPE_PATHS", safe_error)
            st = load_json(state_path)
            st.update({
                "issue_number": n, "front": spec["front_id"], "spec": spec,
                "repo_dir": str(repo_dir), "cycles": cycle, "opencode_session_id": session_id,
                "status": "loop:blocked", "error": safe_error, "updated_utc": utc(),
                "worker_version": WORKER_VERSION, "state_schema_version": STATE_SCHEMA_VERSION,
                "last_failure_class": "INITIAL_OUT_OF_SCOPE_PATHS",
            })
            save_json(state_path, st)
            st = set_converged_phase(cfg, state_path, st, "loop:blocked")
            event(cfg, "local_gate_failed", issue=n, pr=None, cycle=cycle,
                  failure_class="INITIAL_OUT_OF_SCOPE_PATHS", cycle_before=cycle-1, cycle_after=cycle,
                  bad_count=len(bad), test_ok=False)
            st = publish_terminal_notification(cfg, state_path, st, "loop:blocked", safe_error)
            event(cfg, "state_terminalized", state=str(state_path), issue=n, phase="loop:blocked",
                  failure_class="INITIAL_OUT_OF_SCOPE_PATHS", error=safe_error)
            return
        test_ok, test_out = run_profile(cfg,spec,repo_dir)
        if not test_ok:
            safe_error = "The prior candidate failed governed local validation."
            feedback = _safe_feedback_for_failure("INITIAL_LOCAL_GATE_FAILED")
            event(cfg,"kimi_cycle_repair_needed",issue=n,cycle=cycle,bad=[],test_ok=test_ok)
            _checkpoint_initial_cycle(cfg, state_path, n, spec, repo_dir, cycle, session_id,
                                      "INITIAL_LOCAL_GATE_FAILED", safe_error)
            continue
        state = load_json(state_path)
        validate_persisted_roadmap_binding(state)
        if spec["test_profile"] == "pilot":
            write_executor_report(cfg,spec,repo_dir,n,cycle,changes,test_ok,test_out,log,state=state)
        final_changes = changed_files(repo_dir,spec["expected_base_sha"])
        bad2 = [p for p in final_changes if not path_allowed(p,spec["allowed_paths"],spec["forbidden_paths"])]
        if bad2: raise RuntimeError(f"worker report path not allowlisted or extra changes: {bad2}")
        if set(final_changes) != set(spec["allowed_paths"]):
            raise RuntimeError("candidate diff does not exactly match allowed profile paths")
        run(["git","add","--all"],cwd=repo_dir)
        run(["git","commit","-m",f"test(agent-loop): complete {spec['front_id']}"] ,cwd=repo_dir)
        pr = create_pr(cfg,spec,n,repo_dir)
        final_report = write_final_local_report(cfg, spec, n, cycle, repo_dir, pr)
        state = load_json(state_path)
        state.update({
            "issue_number": n, "front": spec["front_id"], "spec": spec, "repo_dir": str(repo_dir),
            "pr_number": pr["number"], "pr_url": pr["url"], "cycles": cycle,
            "last_head_sha": pr["headRefOid"], "opencode_session_id": session_id,
            "status": "WAITING_GITHUB", "final_local_report": str(final_report),
            "worker_version": WORKER_VERSION, "state_schema_version": STATE_SCHEMA_VERSION,
            "updated_utc": utc(),
        })
        validate_persisted_roadmap_binding(state)
        set_converged_phase(cfg, state_path, state, "loop:ci", pr_number=int(pr["number"]))
        event(cfg,"pr_created",issue=n,pr=pr["number"],sha=pr["headRefOid"])
        return
    st = load_json(state_path)
    st.update({"issue_number": n, "front": spec["front_id"], "spec": spec, "repo_dir": str(repo_dir),
               "cycles": int(spec["max_kimi_cycles"]), "opencode_session_id": session_id,
               "status": "loop:token-exhausted", "error": "Maximum executor cycles reached without success. Human audit required.",
               "updated_utc": utc(), "worker_version": WORKER_VERSION, "state_schema_version": STATE_SCHEMA_VERSION})
    st = set_converged_phase(cfg, state_path, st, "loop:token-exhausted")
    st = publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum executor cycles reached. Human audit required.")
    event(cfg, "state_terminalized", state=str(state_path), issue=n, phase="loop:token-exhausted",
          failure_class="MAX_CYCLES_REACHED", error="max cycles reached")


def process_state(cfg, state_path):
    st=load_json(state_path); issue=st["issue_number"]; spec=st["spec"]
    if state_is_terminal(st):
        return
    validate_persisted_roadmap_binding(st)
    if not st.get("pr_number"):
        issue_obj=gh_json(["issue","view",str(issue),"--repo",cfg["repo"],"--json","number,title,body,author,labels,url"])
        execute_initial(cfg,issue_obj,spec,state_path)
        return
    prn=st["pr_number"]
    pr=gh_json(["pr","view",str(prn),"--repo",cfg["repo"],"--json","number,url,headRefOid,labels,state"])
    labs=labels(pr)
    if labs & TERMINAL_LABELS:
        phase = next((x for x in ("loop:accepted", "loop:ready-human-audit", "loop:token-exhausted", "loop:failed", "loop:blocked") if x in labs), None)
        if phase:
            st["status"] = phase
            st["updated_utc"] = utc()
            set_converged_phase(cfg, state_path, st, phase, pr_number=prn)
        return
    if "loop:repairing" not in labs: return
    if pr["headRefOid"] != st.get("last_head_sha"):
        # A new head may already be under review; avoid duplicate repair.
        st["last_head_sha"]=pr["headRefOid"]; save_json(state_path,st); return
    if st["cycles"] >= int(spec["max_kimi_cycles"]):
        st["status"] = "loop:token-exhausted"
        st["updated_utc"] = utc()
        st = set_converged_phase(cfg, state_path, st, "loop:token-exhausted", pr_number=prn)
        st = publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum executor cycles reached. Human audit required.")
        event(cfg, "state_terminalized", state=str(state_path), issue=issue, phase="loop:token-exhausted",
              failure_class="MAX_CYCLES_REACHED", error="max cycles reached")
        return
    feedback=latest_feedback(cfg["repo"],prn,spec,pr["headRefOid"],cfg["install_root"])
    repo_dir=Path(st["repo_dir"])
    run(["git","fetch","origin",spec["work_branch"]],cwd=repo_dir)
    run(["git","checkout",spec["work_branch"]],cwd=repo_dir)
    run(["git","reset","--hard",f"origin/{spec['work_branch']}"],cwd=repo_dir)
    cycle=st["cycles"]+1
    model_dir, seed_hashes = prepare_model_workspace(repo_dir, spec, cycle)
    marker_seed = None
    if spec["test_profile"] == "pilot":
        marker_path = model_dir / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
        marker_seed = sha256_file(marker_path) if marker_path.is_file() else None
    try:
        log, discovered_session=run_kimi(cfg,spec,model_dir,issue,cycle,feedback,st.get("opencode_session_id"))
        if discovered_session: st["opencode_session_id"] = discovered_session
        validate_executor_delivery(cfg, spec, model_dir, log, cycle, issue_no=issue, seed_hash=marker_seed)
    except PreExecutionFailure as exc:
        # Deterministic pre-execution failure: OpenCode never started. Do not consume a cycle.
        safe_error = safe_executor_error(exc)
        event(cfg, "executor_preflight_failed", front=spec["front_id"], issue=issue, pr=prn, cycle=cycle,
              failure_class=exc.failure_class, command_identity=exc.details.get("command_identity") or "opencode",
              local_log_path=exc.details.get("local_log_path"), worker_version=WORKER_VERSION)
        st["updated_utc"] = utc()
        st["error"] = safe_error
        st = set_converged_phase(cfg, state_path, st, "loop:blocked", pr_number=prn)
        st = publish_terminal_notification(cfg, state_path, st, "loop:blocked", safe_error)
        event(cfg, "state_terminalized", state=str(state_path), issue=issue, pr=prn, phase="loop:blocked",
              failure_class=exc.failure_class, error=safe_error)
        return
    except ExecutorAttemptConsumed as exc:
        event(cfg, "executor_failed", front=spec["front_id"], issue=issue, cycle=cycle, error=safe_executor_error(exc), failure_class=exc.failure_class,
              local_log_path=exc.details.get("local_log_path"), returncode=exc.details.get("returncode"),
              command_identity=exc.details.get("command_identity"))
        st["cycles"] = cycle
        st["last_failure_class"] = exc.failure_class
        if _failure_requires_fresh_session(exc.failure_class):
            st["opencode_session_id"] = None
        if cycle >= int(spec["max_kimi_cycles"]):
            safe_error = safe_executor_error(exc)
            st["status"] = "loop:token-exhausted"
            st["error"] = safe_error
            st = set_converged_phase(cfg, state_path, st, "loop:token-exhausted", pr_number=prn)
            st = publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum executor cycles reached. Human audit required.")
            event(cfg, "local_gate_failed", issue=issue, pr=prn, cycle=cycle,
                  failure_class=exc.failure_class, cycle_before=cycle-1, cycle_after=cycle,
                  changed_files=[], test_output_tail=safe_error,
                  marker_hash=marker_hash(repo_dir), current_head=run(["git","rev-parse","HEAD"], cwd=repo_dir).strip(),
                  expected_base=spec["expected_base_sha"], bad=[], test_ok=False)
            event(cfg, "state_terminalized", state=str(state_path), issue=issue, phase="loop:token-exhausted",
                  failure_class=exc.failure_class, cycle=cycle, pr=prn, error=safe_error)
            return
        st["updated_utc"] = utc()
        save_json(state_path, st)
        return
    try:
        audit_and_sync_model_workspace(model_dir, repo_dir, seed_hashes, spec)
    except Exception as exc:
        event(cfg, "repair_local_gate_failed", issue=issue, pr=prn, cycle=cycle,
              failure_class="MODEL_CONTENT_FAILURE", cycle_before=cycle-1, cycle_after=cycle,
              changed_files=changed_files(repo_dir, spec["expected_base_sha"]), test_output_tail=bounded_tail(str(exc)),
              marker_hash=marker_hash(repo_dir), current_head=run(["git","rev-parse","HEAD"], cwd=repo_dir).strip(),
              expected_base=spec["expected_base_sha"], bad=[], test_ok=False)
        st["cycles"] = cycle
        st["updated_utc"] = utc()
        if should_terminalize_failed_cycle(st, spec, cycle):
            st["status"] = "loop:token-exhausted"
            st["error"] = str(exc)[-5000:]
            st = set_converged_phase(cfg, state_path, st, "loop:token-exhausted", pr_number=prn)
            st = publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum executor cycles reached. Human audit required.")
            event(cfg, "state_terminalized", state=str(state_path), issue=issue, phase="loop:token-exhausted",
                  failure_class="MODEL_CONTENT_FAILURE", cycle=cycle, pr=prn, error=bounded_tail(str(exc)))
        else:
            save_json(state_path, st)
        return
    content_ok, content_out = (True, "PROFILE_CONTENT_VALIDATED")
    if spec["test_profile"] == "pilot":
        content_ok, content_out = run_marker_content_check(repo_dir, spec["front_id"])
    if not content_ok:
        event(cfg, "repair_local_gate_failed", issue=issue, pr=prn, cycle=cycle,
              failure_class="MODEL_CONTENT_FAILURE", cycle_before=cycle-1, cycle_after=cycle,
              changed_files=changed_files(repo_dir, spec["expected_base_sha"]), test_output_tail=bounded_tail(content_out),
              marker_hash=marker_hash(repo_dir), current_head=run(["git","rev-parse","HEAD"], cwd=repo_dir).strip(),
              expected_base=spec["expected_base_sha"], bad=[], test_ok=False)
        st["cycles"] = cycle
        st["updated_utc"] = utc()
        if should_terminalize_failed_cycle(st, spec, cycle):
            st["status"] = "loop:token-exhausted"
            st["error"] = bounded_tail(content_out)
            st = set_converged_phase(cfg, state_path, st, "loop:token-exhausted", pr_number=prn)
            st = publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum executor cycles reached. Human audit required.")
            event(cfg, "state_terminalized", state=str(state_path), issue=issue, phase="loop:token-exhausted",
                  failure_class="MODEL_CONTENT_FAILURE", cycle=cycle, pr=prn, error=bounded_tail(content_out))
        else:
            save_json(state_path, st)
        return
    changes=changed_files(repo_dir,spec["expected_base_sha"])
    bad=[p for p in changes if not path_allowed(p,spec["allowed_paths"],spec["forbidden_paths"])]
    if bad:
        terminalize = should_terminalize_failed_cycle(st, spec, cycle)
        cycle_after = cycle if terminalize else cycle - 1
        event(cfg,"repair_local_gate_failed",issue=issue,pr=prn,cycle=cycle,
              failure_class="TRUSTED_VERIFIER_OR_WORKER_INTERNAL_FAILURE", cycle_before=cycle-1, cycle_after=cycle_after,
              changed_files=changes, test_output_tail="", marker_hash=marker_hash(repo_dir),
              current_head=run(["git","rev-parse","HEAD"], cwd=repo_dir).strip(), expected_base=spec["expected_base_sha"], bad=bad,test_ok=False)
        st["updated_utc"] = utc()
        if terminalize:
            st["cycles"] = cycle
            st["status"] = "loop:token-exhausted"
            st["error"] = "out-of-scope files: " + json.dumps(bad)
            st = set_converged_phase(cfg, state_path, st, "loop:token-exhausted", pr_number=prn)
            st = publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum executor cycles reached. Human audit required.")
            event(cfg, "state_terminalized", state=str(state_path), issue=issue, phase="loop:token-exhausted",
                  failure_class="TRUSTED_VERIFIER_OR_WORKER_INTERNAL_FAILURE", cycle=cycle, pr=prn, error=st["error"])
        else:
            save_json(state_path, st)
        return
    validate_persisted_roadmap_binding(st)
    if spec["test_profile"] == "pilot":
        write_executor_report(cfg,spec,repo_dir,issue,cycle,changes,True,content_out,log,state=st)
    run(["git","add","--all"],cwd=repo_dir)
    final_candidate = run(["git","diff","--cached","--name-only"], cwd=repo_dir).splitlines()
    if sorted(x for x in final_candidate if x.strip()) != sorted(spec["allowed_paths"]):
        terminalize = should_terminalize_failed_cycle(st, spec, cycle)
        cycle_after = cycle if terminalize else cycle - 1
        event(cfg,"repair_local_gate_failed",issue=issue,pr=prn,cycle=cycle,
              failure_class="TRUSTED_VERIFIER_OR_WORKER_INTERNAL_FAILURE", cycle_before=cycle-1, cycle_after=cycle_after,
              changed_files=final_candidate, test_output_tail="staged diff is not exactly profile artifacts",
              marker_hash=marker_hash(repo_dir), current_head=run(["git","rev-parse","HEAD"], cwd=repo_dir).strip(),
              expected_base=spec["expected_base_sha"], bad=final_candidate,test_ok=False)
        run(["git","reset"], cwd=repo_dir)
        st["updated_utc"] = utc()
        if terminalize:
            st["cycles"] = cycle
            st["status"] = "loop:token-exhausted"
            st["error"] = "staged diff is not exactly profile artifacts"
            st = set_converged_phase(cfg, state_path, st, "loop:token-exhausted", pr_number=prn)
            st = publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum executor cycles reached. Human audit required.")
            event(cfg, "state_terminalized", state=str(state_path), issue=issue, phase="loop:token-exhausted",
                  failure_class="TRUSTED_VERIFIER_OR_WORKER_INTERNAL_FAILURE", cycle=cycle, pr=prn, error=st["error"])
        else:
            save_json(state_path, st)
        return
    run(["git","commit","-m",f"test(agent-loop): complete {spec['front_id']}"],cwd=repo_dir)
    newsha=run(["git","rev-parse","HEAD"],cwd=repo_dir).strip()
    if spec["test_profile"] == "pilot":
        final_ok, final_out = run_final_verifier(repo_dir, spec["expected_base_sha"], newsha, spec["front_id"])
    else:
        final_ok, final_out = run_profile(cfg, spec, repo_dir)
    if not final_ok:
        run(["git","reset","--hard","HEAD~1"], cwd=repo_dir)
        terminalize = should_terminalize_failed_cycle(st, spec, cycle)
        cycle_after = cycle if terminalize else int(st.get("cycles", cycle - 1))
        event(cfg,"repair_local_gate_failed",issue=issue,pr=prn,cycle=cycle,
              failure_class="TRUSTED_VERIFIER_OR_WORKER_INTERNAL_FAILURE", cycle_before=cycle-1, cycle_after=cycle_after,
              changed_files=changed_files(repo_dir,spec["expected_base_sha"]), test_output_tail=bounded_tail(final_out),
              marker_hash=marker_hash(repo_dir), current_head=newsha, expected_base=spec["expected_base_sha"], bad=[],test_ok=False)
        st["updated_utc"] = utc()
        if terminalize:
            st["cycles"] = cycle
            st["status"] = "loop:token-exhausted"
            st["error"] = bounded_tail(final_out)
            st = set_converged_phase(cfg, state_path, st, "loop:token-exhausted", pr_number=prn)
            st = publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum executor cycles reached. Human audit required.")
            event(cfg, "state_terminalized", state=str(state_path), issue=issue, phase="loop:token-exhausted",
                  failure_class="TRUSTED_VERIFIER_OR_WORKER_INTERNAL_FAILURE", cycle=cycle, pr=prn, error=bounded_tail(final_out))
        else:
            save_json(state_path, st)
        return
    event(cfg, "cycle_committed", issue=issue, pr=prn, cycle=cycle, head_sha=newsha)
    run(["git","push","origin",spec["work_branch"]],cwd=repo_dir)
    event(cfg, "cycle_pushed", issue=issue, pr=prn, cycle=cycle, head_sha=newsha)
    pr_after = gh_json(["pr","view",str(prn),"--repo",cfg["repo"],"--json","number,url,headRefOid"])
    final_report = write_final_local_report(cfg, spec, issue, cycle, repo_dir, pr_after)
    st.update(cycles=cycle,last_head_sha=newsha,status="WAITING_GITHUB",final_local_report=str(final_report),worker_version=WORKER_VERSION,updated_utc=utc())
    set_converged_phase(cfg, state_path, st, "loop:ci", pr_number=prn)

def process_once(cfg):
    state_dir=Path(cfg["install_root"])/"state"
    active=list(state_dir.glob("issue-*.json"))
    for p in active:
        try:
            process_state(cfg, p)
        except Exception as e:
            event(cfg,"state_error",state=str(p),error=str(e),trace=traceback.format_exc()[-5000:])
            terminalize_state_error(cfg, p, e)
    # One active nonterminal state at a time.
    nonterm=[]
    for p in state_dir.glob("issue-*.json"):
        try:
            s=load_json(p)
            if not state_is_terminal(s): nonterm.append(p)
        except Exception: pass
    if nonterm: return
    issues=gh_json(["issue","list","--repo",cfg["repo"],"--state","open","--label","agent:queued","--limit","10",
                    "--json","number,title,body,author,labels,url"])
    for issue in issues:
        if has_terminal_label(issue):
            phase = terminal_phase_from_labels(issue)
            event(cfg, "queued_terminal_issue_skipped", issue=issue["number"], phase=phase)
            continue
        state_path=state_dir/f"issue-{issue['number']}.json"
        if state_path.exists():
            try:
                existing = load_json(state_path)
                if state_is_terminal(existing):
                    phase = str(existing.get("status"))
                    set_phase(cfg["repo"], issue["number"], phase)
                    event(cfg, "terminal_state_preserved", issue=issue["number"], phase=phase)
                    continue
            except Exception:
                pass
        spec = None
        try:
            spec=parse_spec(issue,cfg)
            roadmap_binding = validate_roadmap_contract(cfg, spec)
            save_json(state_path,{"issue_number":issue["number"],"front":spec["front_id"],"spec":spec,"roadmap_binding":roadmap_binding,"status":"LOCAL_EXECUTION","updated_utc":utc(),"state_schema_version":STATE_SCHEMA_VERSION})
            event(cfg, "roadmap_manifest_validated", issue=issue["number"], **{key: roadmap_binding[key] for key in ("roadmap_id", "roadmap_version", "roadmap_item_id", "manifest_sha256", "roadmap_sha256", "base_sha")})
            execute_initial(cfg,issue,spec,state_path)
        except Exception as e:
            msg=str(e)
            label="loop:token-exhausted" if ("TOKEN_EXHAUSTED" in msg or "MAX_CYCLES" in msg) else "loop:blocked"
            st = load_json(state_path) if state_path.exists() else {}
            st.update({
                "issue_number": issue["number"],
                "front": spec.get("front_id") if isinstance(spec, dict) else None,
                "spec": spec if isinstance(spec, dict) else {},
                "status": label,
                "worker_version": WORKER_VERSION,
                "state_schema_version": STATE_SCHEMA_VERSION,
                "error": msg[-5000:],
                "updated_utc": utc(),
            })
            if st.get("roadmap_binding") is not None:
                validate_persisted_roadmap_binding(st)
            st = set_converged_phase(cfg, state_path, st, label)
            publish_terminal_notification(cfg, state_path, st, label, msg)
            event(cfg,"issue_blocked",issue=issue["number"],error=msg,trace=traceback.format_exc()[-5000:])
        break

def trusted_resume_existing_pr(
    cfg: dict,
    issue_number: int,
    expected_front: str,
    expected_base_sha: str,
    expected_pr_number: int,
    expected_work_branch: str,
    expected_pr_head: str,
) -> Path:
    if int(issue_number) != 5 or int(expected_pr_number) != 6:
        raise ValueError("trusted resume is restricted to Issue #5 and PR #6")
    require_scheduled_task_disabled_for_trusted(cfg, "trusted resume")
    state_path = Path(cfg["install_root"]) / "state" / f"issue-{issue_number}.json"
    if not state_path.exists():
        raise FileNotFoundError(str(state_path))
    st = load_json(state_path)
    spec = st.get("spec") or {}
    if st.get("front") != expected_front or spec.get("front_id") != expected_front:
        raise ValueError("front mismatch")
    if spec.get("expected_base_sha") != expected_base_sha:
        raise ValueError("base sha mismatch")
    if spec.get("work_branch") != expected_work_branch:
        raise ValueError("work branch mismatch")
    issue = gh_json(["issue", "view", str(issue_number), "--repo", cfg["repo"],
                     "--json", "number,state,body,author,labels,url"])
    issue_spec = parse_spec(issue, cfg)
    if issue.get("number") != int(issue_number) or issue_spec.get("front_id") != expected_front:
        raise ValueError("remote issue/front mismatch")
    if issue_spec.get("expected_base_sha") != expected_base_sha:
        raise ValueError("remote issue base mismatch")
    if issue_spec.get("work_branch") != expected_work_branch:
        raise ValueError("remote issue work branch mismatch")
    if str(issue.get("state", "")).upper() != "OPEN":
        raise ValueError("issue is not open")
    pr = gh_json(["pr", "view", str(expected_pr_number), "--repo", cfg["repo"],
                  "--json", "number,url,state,isDraft,headRefName,headRefOid,baseRefName,labels"])
    if pr.get("number") != int(expected_pr_number):
        raise ValueError("PR number mismatch")
    if str(pr.get("state", "")).upper() != "OPEN":
        raise ValueError("PR is not open")
    if pr.get("headRefName") != expected_work_branch:
        raise ValueError("PR branch differs")
    if pr.get("headRefOid") != expected_pr_head:
        raise ValueError("PR HEAD moved")
    if pr.get("baseRefName") != spec.get("base_branch"):
        raise ValueError("PR base branch differs")
    ref = gh_json(["api", f"repos/{cfg['repo']}/git/ref/heads/{spec['base_branch']}"])
    current_base = ((ref.get("object") or {}).get("sha") or "").strip()
    if current_base != expected_base_sha:
        raise ValueError(f"base moved: expected {expected_base_sha} actual {current_base}")
    backup = state_path.with_suffix(state_path.suffix + ".bak-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    shutil.copy2(state_path, backup)
    max_cycles = int(spec.get("max_kimi_cycles", cfg.get("max_kimi_cycles_default", 1)))
    st["pr_number"] = int(expected_pr_number)
    st["pr_url"] = pr.get("url") or st.get("pr_url")
    st["last_head_sha"] = expected_pr_head
    st["cycles"] = max(0, max_cycles - 1)
    st["local_retry_count"] = 0
    st["terminal_notified"] = False
    st["status"] = "WAITING_GITHUB"
    st["trusted_existing_pr_resume_utc"] = utc()
    st["updated_utc"] = utc()
    save_json(state_path, st)
    set_phase(cfg["repo"], issue_number, "loop:repairing")
    set_phase(cfg["repo"], int(expected_pr_number), "loop:repairing")
    event(cfg, "trusted_existing_pr_resume", issue=issue_number, pr=expected_pr_number,
          front=expected_front, branch=expected_work_branch, head=expected_pr_head,
          state_backup=str(backup))
    return backup

def trusted_base_advance_existing_pr(
    cfg: dict,
    issue_number: int,
    expected_front: str,
    expected_old_base_sha: str,
    approved_new_base_sha: str,
    approved_control_plane_commit: str,
    expected_pr_number: int,
    expected_work_branch: str,
    expected_old_pr_head: str,
) -> Path:
    if int(issue_number) != 5 or int(expected_pr_number) != 6:
        raise ValueError("trusted base advance is restricted to Issue #5 and PR #6")
    require_scheduled_task_disabled_for_trusted(cfg, "trusted base advance")
    verify_commit_contains(cfg, approved_control_plane_commit, approved_new_base_sha)
    state_path = Path(cfg["install_root"]) / "state" / f"issue-{issue_number}.json"
    if not state_path.exists():
        raise FileNotFoundError(str(state_path))
    st = load_json(state_path)
    spec = st.get("spec") or {}
    if st.get("front") != expected_front or spec.get("front_id") != expected_front:
        raise ValueError("front mismatch")
    if spec.get("expected_base_sha") != expected_old_base_sha:
        raise ValueError("old base mismatch")
    if spec.get("work_branch") != expected_work_branch:
        raise ValueError("work branch mismatch")
    issue = gh_json(["issue", "view", str(issue_number), "--repo", cfg["repo"],
                     "--json", "number,state,body,author,labels,url"])
    issue_spec = parse_spec(issue, cfg)
    original_issue_body = issue.get("body") or ""
    if issue.get("number") != int(issue_number) or issue_spec.get("front_id") != expected_front:
        raise ValueError("remote issue/front mismatch")
    if issue_spec.get("expected_base_sha") != expected_old_base_sha:
        raise ValueError("remote issue old base mismatch")
    if issue_spec.get("work_branch") != expected_work_branch:
        raise ValueError("remote issue work branch mismatch")
    if str(issue.get("state", "")).upper() != "OPEN":
        raise ValueError("issue is not open")
    pr = gh_json(["pr", "view", str(expected_pr_number), "--repo", cfg["repo"],
                  "--json", "number,url,state,isDraft,headRefName,headRefOid,baseRefName,labels"])
    if pr.get("number") != int(expected_pr_number):
        raise ValueError("PR number mismatch")
    if str(pr.get("state", "")).upper() != "OPEN":
        raise ValueError("PR is not open")
    if pr.get("isDraft") is not True:
        raise ValueError("PR is not draft")
    if pr.get("headRefName") != expected_work_branch:
        raise ValueError("PR branch differs")
    if pr.get("headRefOid") != expected_old_pr_head:
        raise ValueError("old PR HEAD mismatch")
    if pr.get("baseRefName") != spec.get("base_branch"):
        raise ValueError("PR base branch differs")
    ref = gh_json(["api", f"repos/{cfg['repo']}/git/ref/heads/{spec['base_branch']}"])
    current_base = ((ref.get("object") or {}).get("sha") or "").strip()
    if current_base != approved_new_base_sha:
        raise ValueError(f"new base mismatch: expected {approved_new_base_sha} actual {current_base}")
    reports = Path(cfg["install_root"]) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    state_backup = state_path.with_suffix(state_path.suffix + ".bak-base-advance-" + stamp)
    issue_body_backup = reports / f"issue-{issue_number}-body.bak-base-advance-{stamp}.md"
    old_head_backup = reports / f"pr-{expected_pr_number}-old-head.bak-base-advance-{stamp}.txt"
    shutil.copy2(state_path, state_backup)
    issue_body_backup.write_text(original_issue_body, encoding="utf-8")
    old_head_backup.write_text(expected_old_pr_head + "\n", encoding="utf-8")
    repo_dir = Path(st.get("repo_dir") or "")
    if not repo_dir.exists():
        raise ValueError("state repo_dir missing")
    new_head = None
    issue_updated = False
    branch_pushed = False
    try:
        run(["git", "fetch", "origin", spec["base_branch"], expected_work_branch], cwd=repo_dir)
        run(["git", "checkout", expected_work_branch], cwd=repo_dir)
        run(["git", "reset", "--hard", expected_old_pr_head], cwd=repo_dir)
        run(["git", "config", "user.name", "AI Vault OpenCode Worker"], cwd=repo_dir)
        run(["git", "config", "user.email", "ai-vault-worker@users.noreply.github.com"], cwd=repo_dir)
        run(["git", "merge", "--no-edit", approved_new_base_sha], cwd=repo_dir)
        new_head = run(["git", "rev-parse", "HEAD"], cwd=repo_dir).strip()
        diff_names = sorted(x for x in run(["git", "diff", "--name-only", approved_new_base_sha, new_head], cwd=repo_dir).splitlines() if x.strip())
        expected = sorted(PROFILE_ALLOWED_PATHS["pilot"])
        if diff_names != expected:
            raise ValueError(f"pilot diff after base advance is not exact: {diff_names}")
        run(["git", "push", "origin", f"HEAD:{expected_work_branch}"], cwd=repo_dir)
        branch_pushed = True
        new_body = update_issue_spec_body(original_issue_body, approved_new_base_sha)
        update_issue_body(cfg["repo"], issue_number, new_body)
        issue_updated = True
        max_cycles = int(spec.get("max_kimi_cycles", cfg.get("max_kimi_cycles_default", 1)))
        spec["expected_base_sha"] = approved_new_base_sha
        st["spec"] = spec
        st["pr_number"] = int(expected_pr_number)
        st["pr_url"] = pr.get("url") or st.get("pr_url")
        st["last_head_sha"] = new_head
        st["cycles"] = max(0, max_cycles - 1)
        st["local_retry_count"] = 0
        st["terminal_notified"] = False
        st["status"] = "WAITING_GITHUB"
        st["trusted_base_advance_utc"] = utc()
        st["updated_utc"] = utc()
        save_json(state_path, st)
        set_phase(cfg["repo"], issue_number, "loop:repairing")
        set_phase(cfg["repo"], int(expected_pr_number), "loop:repairing")
        event(cfg, "trusted_base_advance_existing_pr", issue=issue_number, pr=expected_pr_number,
              front=expected_front, old_base=expected_old_base_sha, new_base=approved_new_base_sha,
              old_head=expected_old_pr_head, new_head=new_head, state_backup=str(state_backup),
              issue_body_backup=str(issue_body_backup), old_head_backup=str(old_head_backup))
        return state_backup
    except Exception:
        save_json(state_path, load_json(state_backup))
        if issue_updated:
            try: update_issue_body(cfg["repo"], issue_number, original_issue_body)
            except Exception: pass
        if branch_pushed and new_head:
            try:
                run(["git", "push", f"--force-with-lease=refs/heads/{expected_work_branch}:{new_head}",
                     "origin", f"{expected_old_pr_head}:refs/heads/{expected_work_branch}"], cwd=repo_dir)
            except Exception:
                pass
        raise

def scheduled_task_disabled(task_name: str = "AI_Vault_Kimi_GitHub_Worker") -> bool:
    if os.name != "nt":
        return True
    out = run(["powershell", "-NoProfile", "-Command", f"(Get-ScheduledTask -TaskName '{task_name}').State"], check=False)
    return "Disabled" in out

def require_scheduled_task_disabled_for_trusted(cfg: dict, action: str) -> None:
    if os.name != "nt":
        return
    install_root = Path(str(cfg.get("install_root", ""))).resolve()
    production_root = Path("C:/AI_VAULT_AGENT_WORKER").resolve()
    if install_root == production_root and not scheduled_task_disabled():
        raise ValueError(f"scheduled task must be Disabled before {action}")

def _iter_worker_events(cfg: dict) -> list[dict]:
    events_path = Path(cfg["install_root"]) / "reports" / "worker-events.jsonl"
    if not events_path.exists():
        raise FileNotFoundError(str(events_path))
    out = []
    for line_no, raw in enumerate(events_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except Exception as exc:
            raise ValueError(f"malformed worker event at line {line_no}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"non-object worker event at line {line_no}")
        out.append(item)
    return out

def _event_kind(item: dict) -> str:
    return str(item.get("event") or item.get("kind") or item.get("type") or "")

def _event_field(item: dict, key: str):
    if key in item:
        return item.get(key)
    fields = item.get("fields")
    if isinstance(fields, dict):
        return fields.get(key)
    return None

def _event_matches(item: dict, kind: str, expected: dict) -> bool:
    item_kind = _event_kind(item)
    if item_kind != kind and not (kind == "repair_local_gate_failed" and item_kind == "local_gate_failed"):
        return False
    for key, value in expected.items():
        got = _event_field(item, key)
        if isinstance(value, int):
            try:
                if int(got or 0) != value:
                    return False
            except Exception:
                return False
        elif str(got) != str(value):
            return False
    return True

def validate_v157_event_chronology(events: list[dict]) -> list[str]:
    """Validate core v1.5.7 event ordering without requiring GitHub access."""
    errors: list[str] = []
    first_terminal: dict[tuple[str, str], int] = {}
    first_local_gate: dict[tuple[str, str], int] = {}
    first_committed: dict[tuple[str, str], int] = {}
    first_pushed: dict[tuple[str, str], int] = {}
    preflight_failed_cycles: dict[tuple[str, str, str], int] = {}
    started_cycles: dict[tuple[str, str, str], int] = {}
    reverted_indexes: list[int] = []
    for idx, item in enumerate(events):
        kind = _event_kind(item)
        issue = str(_event_field(item, "issue") or "")
        pr = str(_event_field(item, "pr") or "")
        key = (issue, pr)
        cycle = _event_field(item, "cycle")
        cycle_key = (issue, pr, str(cycle) if cycle is not None else "")
        if kind == "local_gate_failed":
            first_local_gate.setdefault(key, idx)
        if kind == "cycle_committed":
            first_committed.setdefault(key, idx)
        if kind == "cycle_pushed":
            first_pushed.setdefault(key, idx)
        if kind == "cycle_commit_reverted":
            reverted_indexes.append(idx)
        if kind == "executor_preflight_failed" and cycle_key:
            preflight_failed_cycles.setdefault(cycle_key, idx)
        if kind == "executor_started" and cycle_key:
            started_cycles.setdefault(cycle_key, idx)
        if kind == "state_terminalized":
            first_terminal.setdefault(key, idx)
            failure_class = _event_field(item, "failure_class") or ""
            has_matching_preflight = any(
                cycle_key[0] == issue and cycle_key[1] == pr
                for cycle_key in preflight_failed_cycles
            )
            if key not in first_local_gate and failure_class != "MAX_CYCLES_REACHED" and not has_matching_preflight:
                errors.append(f"state_terminalized_without_prior_local_gate:{key}")
        if kind in {"cycle_committed", "cycle_pushed", "executor_started", "executor_completed", "executor_failed", "cycle_commit_reverted"} and key in first_terminal and idx > first_terminal[key]:
            errors.append(f"{kind}_after_state_terminalized:{key}")
        if kind in {"executor_started", "executor_completed", "executor_failed", "cycle_committed", "cycle_pushed"} and cycle_key in preflight_failed_cycles and idx > preflight_failed_cycles[cycle_key]:
            errors.append(f"{kind}_after_executor_preflight_failed:{cycle_key}")
        if kind == "executor_preflight_failed" and cycle_key in started_cycles and idx > started_cycles[cycle_key]:
            errors.append(f"executor_preflight_failed_after_executor_started:{cycle_key}")
    for key, gate_idx in first_local_gate.items():
        term_idx = first_terminal.get(key)
        if term_idx is not None and term_idx < gate_idx:
            errors.append(f"state_terminalized_before_local_gate:{key}")
    for key in set(first_committed) | set(first_pushed) | {(str(_event_field(events[rev_idx], "issue") or ""), str(_event_field(events[rev_idx], "pr") or "")) for rev_idx in reverted_indexes}:
        committed_idx = first_committed.get(key)
        pushed_idx = first_pushed.get(key)
        if pushed_idx is not None and committed_idx is not None and pushed_idx < committed_idx:
            errors.append(f"cycle_pushed_before_cycle_committed:{key}")
        if pushed_idx is not None and key in first_terminal and pushed_idx > first_terminal[key]:
            errors.append(f"cycle_pushed_after_state_terminalized:{key}")
        for rev_idx in reverted_indexes:
            rev_key = (str(_event_field(events[rev_idx], "issue") or ""), str(_event_field(events[rev_idx], "pr") or ""))
            if rev_key != key:
                continue
            if committed_idx is None:
                errors.append(f"cycle_commit_reverted_without_cycle_committed:{key}")
            elif rev_idx < committed_idx:
                errors.append(f"cycle_commit_reverted_before_cycle_committed:{key}")
    for key, pushed_idx in first_pushed.items():
        if key not in first_committed:
            errors.append(f"cycle_pushed_without_cycle_committed:{key}")
    for cycle_key, preflight_idx in preflight_failed_cycles.items():
        issue_pr = cycle_key[:2]
        term_idx = first_terminal.get(issue_pr)
        if term_idx is not None and term_idx < preflight_idx:
            errors.append(f"state_terminalized_before_executor_preflight_failed:{cycle_key}")
    return errors

def validate_v155_recovery_event_chronology(cfg: dict, base_sha: str, head_sha: str, repo_dir: str | None = None) -> None:
    events = _iter_worker_events(cfg)
    resume_expected = {"issue": 5, "pr": 6, "base": base_sha, "head": head_sha}
    failure_expected = {
        "issue": 5, "pr": 6, "cycle": 3, "cycle_before": 2, "cycle_after": 3,
        "failure_class": "MODEL_CONTENT_FAILURE", "current_head": head_sha, "expected_base": base_sha,
    }
    resume_indexes = [i for i, e in enumerate(events) if _event_matches(e, "trusted_v154_resume_existing_pr", resume_expected)]
    if len(resume_indexes) != 1:
        raise ValueError(f"expected exactly one trusted_v154_resume_existing_pr event; found {len(resume_indexes)}")
    failure_indexes = [i for i, e in enumerate(events) if _event_matches(e, "repair_local_gate_failed", failure_expected)]
    if len(failure_indexes) != 1:
        raise ValueError(f"expected exactly one matching repair_local_gate_failed event; found {len(failure_indexes)}")
    if failure_indexes[0] <= resume_indexes[0]:
        raise ValueError("repair_local_gate_failed event is not later than trusted_v154_resume_existing_pr")
    terminal_bad = {"cycle_pushed", "trusted_cycle_success", "repair_success", "set_loop_ci", "loop_ci_transition"}
    for item in events[failure_indexes[0] + 1:]:
        kind = _event_kind(item)
        if kind in terminal_bad and int(_event_field(item, "issue") or 5) == 5:
            raise ValueError(f"unexpected later terminal event after failed cycle: {kind}")
        if kind == "set_phase" and str(_event_field(item, "phase")) == "loop:ci":
            raise ValueError("unexpected later loop:ci phase after failed cycle")
    if not isinstance(repo_dir, str) or not repo_dir.strip():
        raise ValueError("state.repo_dir is required for v1.5.5 recovery")
    repo_path = Path(repo_dir)
    if not repo_path.exists() or not repo_path.is_dir():
        raise ValueError(f"state.repo_dir does not exist or is not a directory: {repo_dir}")
    inside = run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo_path).strip().lower()
    if inside != "true":
        raise ValueError("state.repo_dir is not a Git worktree")
    actual = run(["git", "rev-parse", "HEAD"], cwd=repo_path).strip()
    if actual != head_sha:
        raise ValueError(f"local repo_dir HEAD mismatch: {actual}")
    remote_ref = run(["git", "rev-parse", "origin/agent/pilot-20260716-091529"], cwd=repo_path).strip()
    if remote_ref != head_sha:
        raise ValueError(f"origin/agent/pilot-20260716-091529 mismatch: {remote_ref}")
    status = run(["git", "status", "--porcelain"], cwd=repo_path).strip()
    if status:
        raise ValueError("local repo_dir has pending candidate changes")
    above = run(["git", "rev-list", f"{head_sha}..HEAD"], cwd=repo_path).strip()
    if above:
        raise ValueError("local repo_dir has commit above expected PR HEAD")

def trusted_resume_issue5_pr6_v154(cfg: dict, issue_number: int, expected_front: str, expected_base_sha: str, expected_pr_number: int, expected_work_branch: str, expected_pr_head: str) -> Path:
    if int(issue_number) != 5 or int(expected_pr_number) != 6:
        raise ValueError("v1.5.4 resume is restricted to Issue #5 and PR #6")
    require_scheduled_task_disabled_for_trusted(cfg, "trusted resume")
    state_path = Path(cfg["install_root"]) / "state" / "issue-5.json"
    original_state_bytes = state_path.read_bytes()
    st = json.loads(original_state_bytes.decode("utf-8-sig"))
    if st.get("trusted_v154_resume_done"):
        raise ValueError("trusted v1.5.4 resume already completed")
    spec = st.get("spec") or {}
    if st.get("front") != expected_front or spec.get("front_id") != expected_front:
        raise ValueError("front mismatch")
    if spec.get("expected_base_sha") != expected_base_sha:
        raise ValueError("base mismatch")
    if spec.get("work_branch") != expected_work_branch:
        raise ValueError("branch mismatch")
    issue = gh_json(["issue", "view", str(issue_number), "--repo", cfg["repo"], "--json", "number,state,body,author,labels,url"])
    pr = gh_json(["pr", "view", str(expected_pr_number), "--repo", cfg["repo"], "--json", "number,url,state,isDraft,headRefName,headRefOid,baseRefName,body,labels"])
    issue_spec = parse_spec(issue, cfg)
    if str(issue.get("state", "")).upper() != "OPEN":
        raise ValueError("issue is not open")
    if str(pr.get("state", "")).upper() != "OPEN":
        raise ValueError("PR is not open")
    if pr.get("isDraft") is not True:
        raise ValueError("PR is not draft")
    if issue_spec.get("front_id") != expected_front or issue_spec.get("work_branch") != expected_work_branch:
        raise ValueError("remote issue mismatch")
    if pr.get("number") != expected_pr_number or pr.get("headRefName") != expected_work_branch or pr.get("headRefOid") != expected_pr_head:
        raise ValueError("remote PR mismatch")
    if pr.get("baseRefName") != spec.get("base_branch"):
        raise ValueError("remote PR base/draft mismatch")
    assert_exact_phase(issue, "loop:repairing", f"Issue #{issue_number}")
    assert_exact_phase(pr, "loop:repairing", f"PR #{expected_pr_number}")
    ref = gh_json(["api", f"repos/{cfg['repo']}/git/ref/heads/{spec['base_branch']}"])
    current_base = ((ref.get("object") or {}).get("sha") or "").strip()
    if current_base != expected_base_sha:
        raise ValueError(f"base moved: expected {expected_base_sha} actual {current_base}")
    diff_files = pr_changed_files(cfg["repo"], int(expected_pr_number))
    if diff_files != sorted(PROFILE_ALLOWED_PATHS["pilot"]):
        raise ValueError(f"unexpected PR diff: {diff_files}")
    reports = Path(cfg["install_root"]) / "reports"; reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = state_path.with_suffix(state_path.suffix + ".bak-v154-resume-" + stamp)
    issue_body_backup = reports / f"issue-5-body.bak-v154-resume-{stamp}.md"
    pr_body_backup = reports / f"pr-6-body.bak-v154-resume-{stamp}.md"
    worker_backup = reports / f"agent_worker.py.bak-v154-resume-{stamp}"
    original_issue_body = issue.get("body") or ""
    original_pr_body = pr.get("body") or ""
    original_issue_labels = labels(issue)
    original_pr_labels = labels(pr)
    backup.write_bytes(original_state_bytes)
    issue_body_backup.write_text(original_issue_body, encoding="utf-8")
    pr_body_backup.write_text(original_pr_body, encoding="utf-8")
    installed = Path(cfg["install_root"]) / "worker" / "agent_worker.py"
    if installed.exists(): shutil.copy2(installed, worker_backup)
    mutated = False
    try:
        body = re.sub(r"EXPECTED_BASE_SHA:\s*[0-9a-fA-F]{40}", f"EXPECTED_BASE_SHA: {expected_base_sha}", original_pr_body)
        if body == original_pr_body and expected_base_sha not in body:
            body = body.rstrip() + f"\nEXPECTED_BASE_SHA: {expected_base_sha}\n"
        update_pr_body(cfg["repo"], expected_pr_number, body); mutated = True
        max_cycles = int(spec.get("max_kimi_cycles", cfg.get("max_kimi_cycles_default", 3)))
        st.update({"pr_number": expected_pr_number, "pr_url": pr.get("url") or st.get("pr_url"), "repo_dir": st.get("repo_dir"),
                   "last_head_sha": expected_pr_head, "cycles": max(0, max_cycles - 1), "local_retry_count": 0,
                   "status": "WAITING_GITHUB", "trusted_v154_resume_done": True,
                   "trusted_v154_resume_utc": utc(), "updated_utc": utc()})
        st.setdefault("notification_keys", st.get("notification_keys") or [])
        save_json(state_path, st); mutated = True
        set_phase(cfg["repo"], issue_number, "loop:repairing"); mutated = True
        set_phase(cfg["repo"], expected_pr_number, "loop:repairing"); mutated = True
        assert_exact_phase(read_issue_labels(cfg["repo"], issue_number), "loop:repairing", f"Issue #{issue_number}")
        assert_exact_phase(read_pr_labels(cfg["repo"], expected_pr_number), "loop:repairing", f"PR #{expected_pr_number}")
        event(cfg, "trusted_v154_resume_existing_pr", issue=issue_number, pr=expected_pr_number, front=expected_front,
              base=expected_base_sha, head=expected_pr_head, state_backup=str(backup), issue_body_backup=str(issue_body_backup),
              pr_body_backup=str(pr_body_backup), worker_backup=str(worker_backup))
        return backup
    except Exception as exc:
        rollback = {"state": False, "issue_body": False, "pr_body": False, "issue_labels": False, "pr_labels": False, "worker": False, "scheduled_task_disabled": scheduled_task_disabled()}
        if mutated:
            try: state_path.write_bytes(original_state_bytes); rollback["state"] = True
            except Exception: pass
            try: update_issue_body(cfg["repo"], issue_number, original_issue_body); rollback["issue_body"] = True
            except Exception: pass
            try: update_pr_body(cfg["repo"], expected_pr_number, original_pr_body); rollback["pr_body"] = True
            except Exception: pass
            try: restore_label_set(cfg["repo"], issue_number, original_issue_labels); rollback["issue_labels"] = True
            except Exception: pass
            try: restore_label_set(cfg["repo"], expected_pr_number, original_pr_labels); rollback["pr_labels"] = True
            except Exception: pass
            try:
                if worker_backup.exists():
                    shutil.copy2(worker_backup, installed)
                    rollback["worker"] = True
            except Exception: pass
        event(cfg, "trusted_v154_resume_rollback", issue=issue_number, pr=expected_pr_number,
              error=bounded_tail(str(exc)), rollback=rollback)
        raise


def trusted_v155_recover_existing_pr(cfg: dict, issue_number: int, expected_base_sha: str | None = None, expected_pr_head: str | None = None, approved_worker_sha256: str | None = None) -> Path:
    if int(issue_number) != 5:
        raise ValueError("trusted v1.5.5 recovery is restricted to Issue #5 and PR #6")
    require_scheduled_task_disabled_for_trusted(cfg, "trusted recovery")
    state_path = Path(cfg["install_root"]) / "state" / "issue-5.json"
    original_state_bytes = state_path.read_bytes()
    st = json.loads(original_state_bytes.decode("utf-8-sig"))
    spec = st.get("spec") or {}
    expected_front = "PILOT-KIMI-CODEX-20260716-091529"
    expected_branch = "agent/pilot-20260716-091529"
    expected_pr_number = 6
    if st.get("trusted_v155_recovery_done"):
        raise ValueError("trusted v1.5.5 recovery already completed")
    if st.get("front") != expected_front or spec.get("front_id") != expected_front:
        raise ValueError("front mismatch")
    if spec.get("work_branch") != expected_branch:
        raise ValueError("work branch mismatch")
    if int(st.get("pr_number") or 0) != expected_pr_number:
        raise ValueError("PR number mismatch")
    if st.get("trusted_v154_resume_done") is not True:
        raise ValueError("trusted_v154_resume_done is required")
    if int(st.get("cycles") or -1) != 3 or st.get("status") != "WAITING_GITHUB":
        raise ValueError("recovery requires cycles=3 and status=WAITING_GITHUB")
    if expected_base_sha and spec.get("expected_base_sha") != expected_base_sha:
        raise ValueError("base mismatch")
    if expected_pr_head and st.get("last_head_sha") != expected_pr_head:
        raise ValueError("state PR HEAD mismatch")
    validate_v155_recovery_event_chronology(cfg, str(expected_base_sha or spec.get("expected_base_sha") or ""), str(expected_pr_head or st.get("last_head_sha") or ""), st.get("repo_dir"))
    issue = gh_json(["issue", "view", "5", "--repo", cfg["repo"], "--json", "number,state,body,author,labels,url"])
    pr = gh_json(["pr", "view", "6", "--repo", cfg["repo"], "--json", "number,url,state,isDraft,headRefName,headRefOid,baseRefName,body,labels"])
    issue_spec = parse_spec(issue, cfg)
    base_sha = expected_base_sha or spec.get("expected_base_sha")
    head_sha = expected_pr_head or st.get("last_head_sha")
    if str(issue.get("state", "")).upper() != "OPEN":
        raise ValueError("issue is not open")
    if str(pr.get("state", "")).upper() != "OPEN" or pr.get("isDraft") is not True:
        raise ValueError("PR must be open and Draft")
    if issue_spec.get("expected_base_sha") != base_sha:
        raise ValueError("remote issue base mismatch")
    if pr.get("headRefName") != expected_branch or pr.get("headRefOid") != head_sha:
        raise ValueError("remote PR head mismatch")
    ref = gh_json(["api", f"repos/{cfg['repo']}/git/ref/heads/{spec['base_branch']}"])
    current_base = ((ref.get("object") or {}).get("sha") or "").strip()
    if current_base != base_sha:
        raise ValueError(f"base moved: expected {base_sha} actual {current_base}")
    if pr_changed_files(cfg["repo"], 6) != sorted(PROFILE_ALLOWED_PATHS["pilot"]):
        raise ValueError("unexpected PR diff")
    reports = Path(cfg["install_root"]) / "reports"; reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = state_path.with_suffix(state_path.suffix + ".bak-v155-recovery-" + stamp)
    issue_body_backup = reports / f"issue-5-body.bak-v155-recovery-{stamp}.md"
    pr_body_backup = reports / f"pr-6-body.bak-v155-recovery-{stamp}.md"
    worker_backup = reports / f"agent_worker.py.bak-v155-recovery-{stamp}"
    original_issue_body = issue.get("body") or ""
    original_pr_body = pr.get("body") or ""
    original_issue_labels = labels(issue)
    original_pr_labels = labels(pr)
    backup.write_bytes(original_state_bytes)
    issue_body_backup.write_text(original_issue_body, encoding="utf-8")
    pr_body_backup.write_text(original_pr_body, encoding="utf-8")
    installed = Path(cfg["install_root"]) / "worker" / "agent_worker.py"
    if installed.exists(): shutil.copy2(installed, worker_backup)
    mutated = False
    try:
        # Preserve the exact historical v1.5.4 comment body solely for notification-ledger migration.
        st = seed_terminal_notification_keys_from_comments(cfg, st, "loop:token-exhausted", "Maximum Kimi cycles reached. Human audit required.")
        st.update({"cycles": 2, "status": "WAITING_GITHUB", "last_head_sha": head_sha,
                   "local_retry_count": 0, "terminal_notified": False,
                   "trusted_v155_recovery_done": True, "trusted_v155_recovery_utc": utc(), "updated_utc": utc()})
        save_json(state_path, st); mutated = True
        set_phase(cfg["repo"], 5, "loop:repairing"); mutated = True
        set_phase(cfg["repo"], 6, "loop:repairing"); mutated = True
        assert_exact_phase(read_issue_labels(cfg["repo"], 5), "loop:repairing", "Issue #5")
        assert_exact_phase(read_pr_labels(cfg["repo"], 6), "loop:repairing", "PR #6")
        reloaded = load_json(state_path)
        if int(reloaded.get("cycles") or -1) != 2:
            raise ValueError("postcondition failed: cycles")
        if reloaded.get("status") != "WAITING_GITHUB":
            raise ValueError("postcondition failed: status")
        if reloaded.get("last_head_sha") != head_sha:
            raise ValueError("postcondition failed: last_head_sha")
        if reloaded.get("trusted_v155_recovery_done") is not True:
            raise ValueError("postcondition failed: trusted_v155_recovery_done")
        if approved_worker_sha256 and sha256_file(installed).upper() != str(approved_worker_sha256).upper():
            raise ValueError("postcondition failed: installed worker SHA")
        event(cfg, "trusted_v155_recovery_existing_pr", issue=5, pr=6, base=base_sha, head=head_sha,
              state_backup=str(backup), issue_body_backup=str(issue_body_backup), pr_body_backup=str(pr_body_backup), worker_backup=str(worker_backup))
        return backup
    except Exception as exc:
        rollback = {"state": False, "issue_body": False, "pr_body": False, "issue_labels": False, "pr_labels": False, "worker": False, "scheduled_task_disabled": scheduled_task_disabled()}
        try: state_path.write_bytes(original_state_bytes); rollback["state"] = True
        except Exception: pass
        try: update_issue_body(cfg["repo"], 5, original_issue_body); rollback["issue_body"] = True
        except Exception: pass
        try: update_pr_body(cfg["repo"], 6, original_pr_body); rollback["pr_body"] = True
        except Exception: pass
        try: restore_label_set(cfg["repo"], 5, original_issue_labels); rollback["issue_labels"] = True
        except Exception: pass
        try: restore_label_set(cfg["repo"], 6, original_pr_labels); rollback["pr_labels"] = True
        except Exception: pass
        try:
            if worker_backup.exists(): shutil.copy2(worker_backup, installed); rollback["worker"] = True
        except Exception: pass
        event(cfg, "trusted_v155_recovery_rollback", issue=5, pr=6, error=bounded_tail(str(exc)), rollback=rollback)
        raise

def trusted_v155_deploy_recover_existing_pr(cfg: dict, issue_number: int, source_worker: str, approved_worker_sha256: str, expected_base_sha: str | None = None, expected_pr_head: str | None = None) -> Path:
    if int(issue_number) != 5:
        raise ValueError("trusted v1.5.5 deploy recovery is restricted to Issue #5 and PR #6")
    require_scheduled_task_disabled_for_trusted(cfg, "trusted deploy recovery")
    source = Path(source_worker).resolve()
    if not source.exists():
        raise FileNotFoundError(str(source))
    source_sha = sha256_file(source)
    if source_sha.upper() != str(approved_worker_sha256).upper():
        raise ValueError(f"approved source worker SHA mismatch: {source_sha}")
    install_root = Path(cfg["install_root"])
    installed = install_root / "worker" / "agent_worker.py"
    state_path = install_root / "state" / "issue-5.json"
    if not installed.exists():
        raise FileNotFoundError(str(installed))
    if not state_path.exists():
        raise FileNotFoundError(str(state_path))
    reports = install_root / "reports"; reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    worker_backup = reports / f"agent_worker.py.bak-v155-deploy-{stamp}"
    state_backup = reports / f"issue-5.json.bak-v155-deploy-{stamp}"
    original_worker = installed.read_bytes()
    original_state = state_path.read_bytes()
    shutil.copy2(installed, worker_backup)
    state_backup.write_bytes(original_state)
    try:
        shutil.copy2(source, installed)
        installed_sha = sha256_file(installed)
        if installed_sha.upper() != str(approved_worker_sha256).upper():
            raise ValueError(f"installed worker SHA mismatch: {installed_sha}")
        backup = trusted_v155_recover_existing_pr(cfg, issue_number, expected_base_sha, expected_pr_head, approved_worker_sha256)
        try:
            event(cfg, "trusted_v155_deploy_recovery_existing_pr", issue=5, pr=6, source_sha=installed_sha, recovery_backup=str(backup), worker_backup=str(worker_backup), state_backup=str(state_backup))
        except Exception:
            pass
        return backup
    except Exception as exc:
        rollback = {"state": False, "worker": False, "scheduled_task_disabled": scheduled_task_disabled()}
        try: installed.write_bytes(original_worker); rollback["worker"] = True
        except Exception: pass
        try: state_path.write_bytes(original_state); rollback["state"] = True
        except Exception: pass
        event(cfg, "trusted_v155_deploy_recovery_rollback", issue=5, pr=6, error=bounded_tail(str(exc)), rollback=rollback)
        raise




class SingleInstanceLock:
    def __init__(self, path: Path):
        self.path=path; self.handle=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.handle=self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0); self.handle.write(b"0"); self.handle.flush(); self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception as exc:
            self.handle.close()
            try:
                install_root = str(self.path.parent.parent)
                evidence = worker_process_evidence(install_root)
            except Exception:
                evidence = []
            raise RuntimeError("another worker instance is already running; process_evidence=" + json.dumps(evidence, sort_keys=True)) from exc
        return self
    def __exit__(self, exc_type, exc, tb):
        try:
            if self.handle:
                if os.name == "nt":
                    import msvcrt
                    self.handle.seek(0); msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            if self.handle: self.handle.close()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); ap.add_argument("--once",action="store_true"); ap.add_argument("--trusted-resume-existing-pr", type=int); ap.add_argument("--trusted-base-advance-existing-pr", type=int); ap.add_argument("--trusted-v154-resume-existing-pr", type=int); ap.add_argument("--trusted-v155-recover-existing-pr", type=int); ap.add_argument("--trusted-v155-deploy-recover-existing-pr", type=int); ap.add_argument("--expected-front"); ap.add_argument("--expected-base-sha"); ap.add_argument("--expected-old-base-sha"); ap.add_argument("--approved-new-base-sha"); ap.add_argument("--approved-control-plane-commit"); ap.add_argument("--expected-pr-number", type=int); ap.add_argument("--expected-work-branch"); ap.add_argument("--expected-pr-head"); ap.add_argument("--expected-old-pr-head"); ap.add_argument("--source-worker"); ap.add_argument("--approved-worker-sha256"); ap.add_argument("--historical-base-sha"); ap.add_argument("--approved-current-base-sha")
    args=ap.parse_args(); cfg=load_json(Path(args.config)); Path(cfg["install_root"]).mkdir(parents=True,exist_ok=True)
    global _RUN_EVENT_CFG
    _RUN_EVENT_CFG = cfg
    if args.trusted_base_advance_existing_pr is not None:
        if not all([args.expected_front, args.expected_old_base_sha, args.approved_new_base_sha,
                    args.approved_control_plane_commit, args.expected_pr_number,
                    args.expected_work_branch, args.expected_old_pr_head]):
            raise SystemExit("trusted base advance requires expected front, old base, approved new base, approved control-plane commit, PR number, branch, and old PR head")
        with SingleInstanceLock(Path(cfg["install_root"])/"state"/"worker.lock"):
            backup = trusted_base_advance_existing_pr(cfg, args.trusted_base_advance_existing_pr,
                                                      args.expected_front, args.expected_old_base_sha,
                                                      args.approved_new_base_sha, args.approved_control_plane_commit,
                                                      args.expected_pr_number, args.expected_work_branch,
                                                      args.expected_old_pr_head)
        print(json.dumps({"status":"BASE_ADVANCED_EXISTING_PR", "backup": str(backup)}, indent=2))
        return
    if args.trusted_v154_resume_existing_pr is not None:
        if not all([args.expected_front, args.expected_base_sha, args.expected_pr_number, args.expected_work_branch, args.expected_pr_head]):
            raise SystemExit("trusted v1.5.4 resume requires expected front, base, PR number, branch, and PR head")
        with SingleInstanceLock(Path(cfg["install_root"])/"state"/"worker.lock"):
            backup = trusted_resume_issue5_pr6_v154(cfg, args.trusted_v154_resume_existing_pr, args.expected_front, args.expected_base_sha, args.expected_pr_number, args.expected_work_branch, args.expected_pr_head)
        print(json.dumps({"status":"RESUMED_EXISTING_PR_V154", "backup": str(backup)}, indent=2))
        return
    if args.trusted_v155_deploy_recover_existing_pr is not None:
        if not all([args.source_worker, args.approved_worker_sha256, args.expected_base_sha, args.expected_pr_head]):
            raise SystemExit("trusted v1.5.5 deploy recovery requires source worker, approved worker sha256, expected base, and expected PR head")
        lock_path = Path(cfg["install_root"])/"state"/"worker.lock"
        try:
            with SingleInstanceLock(lock_path):
                backup = trusted_v155_deploy_recover_existing_pr(cfg, args.trusted_v155_deploy_recover_existing_pr, args.source_worker, args.approved_worker_sha256, args.expected_base_sha, args.expected_pr_head)
        except RuntimeError as exc:
            evidence = worker_process_evidence(cfg["install_root"])
            raise SystemExit("worker.lock busy; trusted v1.5.5 deploy recovery aborted before mutation; process_evidence=" + json.dumps(evidence, sort_keys=True)) from exc
        print(json.dumps({"status":"DEPLOY_RECOVERED_EXISTING_PR_V155", "backup": str(backup)}, indent=2))
        return
    if args.trusted_v155_recover_existing_pr is not None:
        with SingleInstanceLock(Path(cfg["install_root"])/"state"/"worker.lock"):
            backup = trusted_v155_recover_existing_pr(cfg, args.trusted_v155_recover_existing_pr, args.expected_base_sha, args.expected_pr_head)
        print(json.dumps({"status":"RECOVERED_EXISTING_PR_V155", "backup": str(backup)}, indent=2))
        return
    if args.trusted_resume_existing_pr is not None:
        if not all([args.expected_front, args.expected_base_sha, args.expected_pr_number,
                    args.expected_work_branch, args.expected_pr_head]):
            raise SystemExit("trusted existing-PR resume requires expected front, base, PR number, branch, and PR head")
        with SingleInstanceLock(Path(cfg["install_root"])/"state"/"worker.lock"):
            backup = trusted_resume_existing_pr(cfg, args.trusted_resume_existing_pr, args.expected_front,
                                                args.expected_base_sha, args.expected_pr_number,
                                                args.expected_work_branch, args.expected_pr_head)
        print(json.dumps({"status":"RESUMED_EXISTING_PR", "backup": str(backup)}, indent=2))
        return
    with SingleInstanceLock(Path(cfg["install_root"])/"state"/"worker.lock"):
        run_preflight(cfg)
        cleanup_stale_workspaces(cfg)
        event(cfg,"worker_started",once=args.once,worker_version=WORKER_VERSION,worker_sha256=sha256_file(Path(__file__)))
        while True:
            try: process_once(cfg)
            except Exception as e: event(cfg,"poll_error",error=str(e),trace=traceback.format_exc()[-5000:])
            if args.once: break
            time.sleep(int(cfg["poll_seconds"]))
if __name__ == "__main__": main()
