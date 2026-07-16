#!/usr/bin/env python3
"""Allowlisted local Kimi/OpenCode worker for a single trusted GitHub repository."""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys, time, traceback, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SPEC_RE = re.compile(r"<!--\s*AGENT_LOOP_SPEC\s*(\{.*?\})\s*AGENT_LOOP_SPEC\s*-->", re.S)
WORKER_VERSION = "1.5.2"
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
    }
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
PILOT_MARKER_TEXT = """# Agent Loop Pilot
WORKER_VERSION=1.5.2
STATUS=PASS
EXECUTOR=KIMI_OPENCODE_OLLAMA
SUPERVISOR=CODEX_GITHUB_ACTION
"""

class CmdError(RuntimeError):
    def __init__(self, cmd, code, out):
        super().__init__(f"command failed ({code}): {cmd}\n{out[-4000:]}")
        self.cmd, self.code, self.out = cmd, code, out

def utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def command_for_subprocess(args: list[str]) -> list[str]:
    """Resolve commands safely on Windows, including npm .cmd/.bat shims."""
    values = [str(x) for x in args]
    if not values:
        raise ValueError("empty command")
    resolved = shutil.which(values[0])
    if resolved:
        values[0] = resolved
    if os.name == "nt" and Path(values[0]).suffix.lower() in {".cmd", ".bat"}:
        comspec = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
        return [comspec, "/d", "/s", "/c", subprocess.list2cmdline(values)]
    return values

def run(args: list[str], cwd: Path | None = None, env: dict[str,str] | None = None, check=True, timeout=None) -> str:
    p = subprocess.run(command_for_subprocess(args), cwd=str(cwd) if cwd else None, env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if check and p.returncode != 0:
        raise CmdError(args, p.returncode, p.stdout)
    return p.stdout

def gh_json(args: list[str]) -> Any:
    return json.loads(run(["gh", *args]))

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))

def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def event(cfg, kind, **fields):
    record = {"timestamp_utc": utc(), "kind": kind, **fields}
    p = Path(cfg["install_root"]) / "reports" / "worker-events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

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

def comment(repo: str, number: int, body: str):
    run(["gh", "issue", "comment", str(number), "--repo", repo, "--body", body])

def _normalize_repo_path(value: str) -> str:
    norm = str(value).replace("\\", "/").strip().lstrip("./")
    if not norm or norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        raise ValueError(f"invalid repository path: {value!r}")
    parts = [p for p in norm.split("/") if p]
    if any(p == ".." for p in parts):
        raise ValueError(f"path traversal is not allowed: {value!r}")
    return "/".join(parts)

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
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{5,127}", str(spec["front_id"])):
        raise ValueError("invalid front_id")
    if spec["repo"] != cfg["repo"] or spec["owner"] != cfg["owner"]:
        raise ValueError("repo/owner mismatch")
    if spec["base_branch"] != cfg["base_branch"]:
        raise ValueError("base branch mismatch")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", str(spec["expected_base_sha"])):
        raise ValueError("expected_base_sha must be a full 40-character commit SHA")
    if not spec["work_branch"].startswith("agent/pilot-"):
        raise ValueError("pilot worker only accepts agent/pilot-* branches")
    profile = str(spec["test_profile"])
    if profile not in cfg["test_profiles"] or profile not in PROFILE_ALLOWED_PATHS:
        raise ValueError("unknown test profile")
    if not (1 <= int(spec["max_kimi_cycles"]) <= int(cfg["max_kimi_cycles_default"])):
        raise ValueError("invalid max cycles")
    if not isinstance(spec["allowed_paths"], list) or not all(isinstance(x, str) for x in spec["allowed_paths"]):
        raise ValueError("allowed_paths must be a string list")
    if not isinstance(spec["forbidden_paths"], list) or not all(isinstance(x, str) for x in spec["forbidden_paths"]):
        raise ValueError("forbidden_paths must be a string list")
    allowed = {_normalize_repo_path(x) for x in spec["allowed_paths"]}
    expected_allowed = PROFILE_ALLOWED_PATHS[profile]
    if allowed != expected_allowed:
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

def opencode_env(cfg: dict, repo_dir: Path) -> dict[str,str]:
    model = cfg["opencode_model"]
    # Preserve the user's existing OpenCode provider/auth configuration.
    # Override only the selected model and the worker permission boundary.
    strict_permissions = {
        "read":"allow", "edit":"allow", "glob":"allow", "grep":"allow", "list":"allow",
        "bash":"deny", "task":"deny", "external_directory":"deny", "webfetch":"deny",
        "websearch":"deny", "lsp":"deny", "skill":"deny", "question":"deny", "todowrite":"deny"
    }
    conf = {
        "$schema":"https://opencode.ai/config.json",
        "model":model,
        "permission":strict_permissions,
        "agent":{
            "brain-kimi-executor":{
                "description":"Writes one exact allowlisted pilot artifact in a detached workspace.",
                "mode":"primary", "steps":30, "temperature":0.1, "model":model,
                "prompt":"Follow the user prompt exactly. Never use shell, network, subagents, skills, LSP, or external paths.",
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
    base = f"""You are the Kimi executor for {spec['front_id']}.
Work only in the detached model workspace. It contains no Git metadata and no credentials.
Do not invoke a shell, commit, push, use gh, merge, or access external directories.
Objective: {spec['objective']}
Allowed output path: docs/agent_loop/pilot/PILOT_MARKER.md
Pilot requirement: write that file with exactly this UTF-8 text:\n---\n{PILOT_MARKER_TEXT}---
Do not create or edit EXECUTOR_REPORT.json; the trusted worker writes it after validation.
Do not change the local agent policy or create any other file. This is cycle {cycle}.
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
        if path.is_symlink():
            raise RuntimeError(f"MODEL_WORKSPACE_SYMLINK_DENIED:{path}")
        if path.is_file():
            files.append(path.relative_to(root).as_posix())
    return sorted(files)

def prepare_model_workspace(repo_dir: Path, spec: dict, cycle: int) -> tuple[Path, dict[str, str]]:
    """Create a no-.git workspace for Kimi and seed only trusted, non-secret files."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    model_dir = repo_dir.parent / f"model-cycle-{cycle}-{stamp}-{os.getpid()}"
    model_dir.mkdir(parents=True, exist_ok=False)
    seed_hashes: dict[str, str] = {}
    for rel in sorted(MODEL_SEED_PATHS):
        src = repo_dir / rel
        if not src.is_file():
            raise RuntimeError(f"MODEL_SEED_MISSING:{rel}")
        dst = model_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        seed_hashes[rel] = sha256_file(dst)
    marker_rel = "docs/agent_loop/pilot/PILOT_MARKER.md"
    marker_src = repo_dir / marker_rel
    if marker_src.is_file():
        marker_dst = model_dir / marker_rel
        marker_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(marker_src, marker_dst)
    if (model_dir / ".git").exists():
        raise RuntimeError("MODEL_WORKSPACE_GIT_METADATA_PRESENT")
    return model_dir, seed_hashes

def audit_and_sync_model_workspace(model_dir: Path, repo_dir: Path, seed_hashes: dict[str, str]) -> list[str]:
    """Reject metadata/extra writes, verify exact output, then copy only allowlisted output."""
    if (model_dir / ".git").exists():
        raise RuntimeError("MODEL_WORKSPACE_GIT_METADATA_DENIED")
    files = set(_walk_workspace_files(model_dir))
    marker_rel = "docs/agent_loop/pilot/PILOT_MARKER.md"
    expected = set(MODEL_SEED_PATHS) | {marker_rel}
    extra = sorted(files - expected)
    missing = sorted(expected - files)
    if extra or missing:
        raise RuntimeError(f"MODEL_WORKSPACE_BOUNDARY_FAILED extra={extra} missing={missing}")
    for rel, expected_hash in seed_hashes.items():
        if sha256_file(model_dir / rel) != expected_hash:
            raise RuntimeError(f"MODEL_SEED_MODIFIED:{rel}")
    marker = model_dir / marker_rel
    content = marker.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if content != PILOT_MARKER_TEXT:
        raise RuntimeError("PILOT_MARKER_CONTENT_MISMATCH")
    destination = repo_dir / marker_rel
    current = repo_dir
    for part in Path(marker_rel).parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise RuntimeError(f"TRUSTED_OUTPUT_PARENT_SYMLINK_DENIED:{current}")
    if destination.exists() and destination.is_symlink():
        raise RuntimeError(f"TRUSTED_OUTPUT_SYMLINK_DENIED:{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(marker, destination)
    return [marker_rel]

def run_kimi(cfg, spec, model_dir, issue_no, cycle, feedback=None, session_id=None):
    report_dir = Path(cfg["install_root"]) / "reports"
    log = report_dir / f"issue-{issue_no}-cycle-{cycle}-opencode.jsonl"
    title = f"AI_Vault {spec['front_id']}"
    cmd = ["opencode","run","--dir",str(model_dir),"--model",cfg["opencode_model"],
           "--agent","brain-kimi-executor","--format","json",
           "--title",title]
    if opencode_run_supports("--auto", cwd=model_dir):
        cmd.append("--auto")
    if session_id: cmd += ["--session", session_id]
    cmd.append(make_prompt(spec, cycle, feedback))
    p = subprocess.run(command_for_subprocess(cmd), cwd=str(model_dir), env=opencode_env(cfg, model_dir), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text(p.stdout, encoding="utf-8")
    if p.returncode != 0:
        low = p.stdout.lower()
        if "context" in low or "token" in low or "rate limit" in low:
            raise RuntimeError("TOKEN_EXHAUSTED:" + p.stdout[-3000:])
        raise CmdError(cmd, p.returncode, p.stdout)
    return log, discover_session_id(model_dir, title)

def run_profile(cfg, spec, repo_dir) -> tuple[bool,str]:
    cmd = [str(x) for x in cfg["test_profiles"][spec["test_profile"]]]
    p = subprocess.run(command_for_subprocess(cmd), cwd=str(repo_dir), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode == 0, p.stdout

def write_executor_report(cfg, spec, repo_dir, issue_no, cycle, changes, test_ok, test_out, log_path):
    p = repo_dir / "docs/agent_loop/pilot/EXECUTOR_REPORT.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version":1,"worker_version":WORKER_VERSION,"front_id":spec["front_id"],"issue_number":issue_no,
        "cycle":cycle,"executor":"Kimi via OpenCode/Ollama","model":cfg["opencode_model"],
        "base_sha":spec["expected_base_sha"],"changed_files":sorted(set(changes) | {"docs/agent_loop/pilot/EXECUTOR_REPORT.json"}),
        "local_test_profile":spec["test_profile"],"local_test_passed":test_ok,
        "local_test_tail":test_out[-3000:],"opencode_log_local":str(log_path),
        "generated_utc":utc(),"merge_performed":False,"canonical_local_sync":False
    }
    save_json(p, data)

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
    for name in ("git", "gh", "python", "opencode"):
        resolved = shutil.which(name) or shutil.which(name + ".cmd") or shutil.which(name + ".exe")
        checks[name] = {"ok": bool(resolved), "path": resolved}
    gh_status = subprocess.run(command_for_subprocess(["gh", "auth", "status"]), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    checks["gh_auth"] = {"ok": gh_status.returncode == 0, "tail": gh_status.stdout[-1000:]}
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
    st["last_error"] = str(exc)[-5000:]
    st["updated_utc"] = utc()
    if classification == "RETRY" and retries <= max_retries:
        st["status"] = "LOCAL_RETRY"
        save_json(state_path, st)
        event(cfg, "state_retry_scheduled", state=str(state_path), issue=issue, retry=retries, max_retries=max_retries, error=str(exc))
        return
    phase = classification if classification != "RETRY" else "loop:blocked"
    st["status"] = phase
    save_json(state_path, st)
    set_phase(cfg["repo"], issue, phase)
    if st.get("pr_number"):
        set_phase(cfg["repo"], int(st["pr_number"]), phase)
    if not st.get("terminal_notified"):
        comment(cfg["repo"], st.get("pr_number") or issue,
                f"[AGENT-LOOP][{phase.split(':')[-1].upper()}]\n\n@{cfg['owner']} {str(exc)[-4000:]}")
        st["terminal_notified"] = True
        save_json(state_path, st)
    event(cfg, "state_terminalized", state=str(state_path), issue=issue, phase=phase, error=str(exc))

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
    run(["git","config","user.name","AI Vault Kimi Worker"],cwd=repo_dir)
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
        p = subprocess.run(["gh","run","download",run_id,"--repo",repo,"--name","codex-supervisor-report","--dir",str(temp)],
                           text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
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

Automated pilot. No auto-merge. Kimi writes; Codex supervises read-only; human audit is final.
"""
    url = run(["gh","pr","create","--repo",cfg["repo"],"--base",spec["base_branch"],"--head",spec["work_branch"],
               "--draft","--title",f"test(agent-loop): {spec['front_id']}","--body",body],cwd=repo_dir).strip()
    pr = gh_json(["pr","view",url,"--repo",cfg["repo"],"--json","number,url,headRefOid"])
    return pr

def execute_initial(cfg, issue, spec, state_path):
    n = issue["number"]
    set_phase(cfg["repo"], n, "loop:executing")
    repo_dir = prepare_repo(cfg,spec,n)
    feedback = None
    session_id = None
    for cycle in range(1,int(spec["max_kimi_cycles"])+1):
        event(cfg,"kimi_cycle_start",issue=n,cycle=cycle,front=spec["front_id"])
        model_dir, seed_hashes = prepare_model_workspace(repo_dir, spec, cycle)
        log, discovered_session = run_kimi(cfg,spec,model_dir,n,cycle,feedback,session_id)
        if discovered_session: session_id = discovered_session
        try:
            audit_and_sync_model_workspace(model_dir, repo_dir, seed_hashes)
        except Exception as exc:
            feedback = str(exc)
            event(cfg,"kimi_cycle_repair_needed",issue=n,cycle=cycle,bad=[str(exc)],test_ok=False)
            continue
        changes = changed_files(repo_dir,spec["expected_base_sha"])
        bad = [p for p in changes if not path_allowed(p,spec["allowed_paths"],spec["forbidden_paths"])]
        # Worker owns executor report, so add it after initial path check.
        test_ok, test_out = run_profile(cfg,spec,repo_dir)
        if bad or not test_ok:
            feedback = ("Out-of-scope files: " + json.dumps(bad) + "\n" if bad else "") + ("Test output:\n" + test_out[-4000:] if not test_ok else "")
            event(cfg,"kimi_cycle_repair_needed",issue=n,cycle=cycle,bad=bad,test_ok=test_ok)
            continue
        write_executor_report(cfg,spec,repo_dir,n,cycle,changes,test_ok,test_out,log)
        final_changes = changed_files(repo_dir,spec["expected_base_sha"])
        bad2 = [p for p in final_changes if not path_allowed(p,spec["allowed_paths"],spec["forbidden_paths"])]
        if bad2: raise RuntimeError(f"worker report path not allowlisted or extra changes: {bad2}")
        run(["git","add","--all"],cwd=repo_dir)
        run(["git","commit","-m",f"test(agent-loop): complete {spec['front_id']}"] ,cwd=repo_dir)
        pr = create_pr(cfg,spec,n,repo_dir)
        final_report = write_final_local_report(cfg, spec, n, cycle, repo_dir, pr)
        state={"issue_number":n,"front":spec["front_id"],"spec":spec,"repo_dir":str(repo_dir),"pr_number":pr["number"],
               "pr_url":pr["url"],"cycles":cycle,"last_head_sha":pr["headRefOid"],"opencode_session_id":session_id,
               "status":"WAITING_GITHUB","final_local_report":str(final_report),"worker_version":WORKER_VERSION,"updated_utc":utc()}
        save_json(state_path,state)
        set_phase(cfg["repo"], n, "loop:ci")
        event(cfg,"pr_created",issue=n,pr=pr["number"],sha=pr["headRefOid"])
        return
    raise RuntimeError("MAX_CYCLES_EXHAUSTED: initial candidate did not pass local gates")

def process_state(cfg, state_path):
    st=load_json(state_path); issue=st["issue_number"]; spec=st["spec"]
    if st.get("status") in TERMINAL_LABELS:
        return
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
            save_json(state_path, st)
            set_phase(cfg["repo"], issue, phase)
        return
    if "loop:repairing" not in labs: return
    if pr["headRefOid"] != st.get("last_head_sha"):
        # A new head may already be under review; avoid duplicate repair.
        st["last_head_sha"]=pr["headRefOid"]; save_json(state_path,st); return
    if st["cycles"] >= int(spec["max_kimi_cycles"]):
        set_phase(cfg["repo"], prn, "loop:token-exhausted")
        comment(cfg["repo"],prn,f"[AGENT-LOOP][TOKEN_EXHAUSTED]\n\n@{cfg['owner']} Maximum Kimi cycles reached. Human audit required.")
        return
    feedback=latest_feedback(cfg["repo"],prn,spec,pr["headRefOid"],cfg["install_root"])
    repo_dir=Path(st["repo_dir"])
    run(["git","fetch","origin",spec["work_branch"]],cwd=repo_dir)
    run(["git","checkout",spec["work_branch"]],cwd=repo_dir)
    run(["git","reset","--hard",f"origin/{spec['work_branch']}"],cwd=repo_dir)
    cycle=st["cycles"]+1
    model_dir, seed_hashes = prepare_model_workspace(repo_dir, spec, cycle)
    log, discovered_session=run_kimi(cfg,spec,model_dir,issue,cycle,feedback,st.get("opencode_session_id"))
    if discovered_session: st["opencode_session_id"] = discovered_session
    audit_and_sync_model_workspace(model_dir, repo_dir, seed_hashes)
    changes=changed_files(repo_dir,spec["expected_base_sha"])
    bad=[p for p in changes if not path_allowed(p,spec["allowed_paths"],spec["forbidden_paths"])]
    ok,out=run_profile(cfg,spec,repo_dir)
    if bad or not ok:
        st["cycles"]=cycle; st["updated_utc"]=utc(); save_json(state_path,st)
        event(cfg,"repair_local_gate_failed",issue=issue,pr=prn,cycle=cycle,bad=bad,test_ok=ok)
        return
    write_executor_report(cfg,spec,repo_dir,issue,cycle,changes,ok,out,log)
    run(["git","add","--all"],cwd=repo_dir)
    run(["git","commit","-m",f"fix(agent-loop): address supervisor findings cycle {cycle}"],cwd=repo_dir)
    run(["git","push","origin",spec["work_branch"]],cwd=repo_dir)
    newsha=run(["git","rev-parse","HEAD"],cwd=repo_dir).strip()
    pr_after = gh_json(["pr","view",str(prn),"--repo",cfg["repo"],"--json","number,url,headRefOid"])
    final_report = write_final_local_report(cfg, spec, issue, cycle, repo_dir, pr_after)
    st.update(cycles=cycle,last_head_sha=newsha,status="WAITING_GITHUB",final_local_report=str(final_report),worker_version=WORKER_VERSION,updated_utc=utc()); save_json(state_path,st)
    set_phase(cfg["repo"], prn, "loop:ci")

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
            if not str(s.get("status","")).startswith("loop:"): nonterm.append(p)
        except Exception: pass
    if nonterm: return
    issues=gh_json(["issue","list","--repo",cfg["repo"],"--state","open","--label","agent:queued","--limit","10",
                    "--json","number,title,body,author,labels,url"])
    for issue in issues:
        state_path=state_dir/f"issue-{issue['number']}.json"
        spec = None
        try:
            spec=parse_spec(issue,cfg)
            save_json(state_path,{"issue_number":issue["number"],"front":spec["front_id"],"spec":spec,"status":"LOCAL_EXECUTION","updated_utc":utc()})
            execute_initial(cfg,issue,spec,state_path)
        except Exception as e:
            msg=str(e)
            label="loop:token-exhausted" if ("TOKEN_EXHAUSTED" in msg or "MAX_CYCLES" in msg) else "loop:blocked"
            set_phase(cfg["repo"], issue["number"], label)
            save_json(state_path,{"issue_number":issue["number"],"front":spec.get("front_id") if isinstance(spec, dict) else None,"spec":spec if isinstance(spec, dict) else {},"status":label,"worker_version":WORKER_VERSION,"error":msg[-5000:],"updated_utc":utc()})
            comment(cfg["repo"],issue["number"],f"[AGENT-LOOP][BLOCKED]\n\n@{cfg['owner']} {msg[-5000:]}")
            event(cfg,"issue_blocked",issue=issue["number"],error=msg,trace=traceback.format_exc()[-5000:])
        break

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
        except Exception:
            self.handle.close(); raise RuntimeError("another worker instance is already running")
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
    ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); ap.add_argument("--once",action="store_true")
    args=ap.parse_args(); cfg=load_json(Path(args.config)); Path(cfg["install_root"]).mkdir(parents=True,exist_ok=True)
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
