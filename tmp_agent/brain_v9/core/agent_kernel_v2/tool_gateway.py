from __future__ import annotations
import json, re, subprocess, urllib.request
from pathlib import Path
from typing import Any, Dict, List
from .governance import path_is_blocked, validate_mode, write_allowed
from .schemas import AgentCapability, ToolCallRequest, ToolCallResult, to_dict

ROOT = Path(__file__).resolve().parents[4]
MAX_FILE_READ_BYTES = 128_000
SAFE_POST_PATHS = {"/v2/agent/runs", "/v2/chat/agent"}
SMOKE_ALLOWLIST = {
    "tests/smoke/smoke_front_brain_agent_full_rebuild_langgraph_recursive_closeout_01.py",
    "tests/smoke/smoke_front_brain_agent_v2_total_operational_excellence_closeout_01.py",
}


class ToolGatewayV2:
    def __init__(self):
        self.capabilities = [
            AgentCapability("repo_status_read", "Read git status and HEAD", "low", True, False, ["read_only", "dry_run", "approval_required", "write_allowed"]),
            AgentCapability("file_read", "Read a safe text file", "low", True, False, ["read_only", "dry_run"]),
            AgentCapability("grep_search", "Search repository text with rg", "low", True, False, ["read_only", "dry_run"]),
            AgentCapability("route_probe", "Probe a local HTTP route", "low", True, False, ["read_only", "dry_run"]),
            AgentCapability("semantic_retrieve", "Read-only semantic retrieval", "low", True, False, ["read_only", "dry_run"]),
            AgentCapability("repo_history_read", "Read recent git commit history", "low", True, False, ["read_only", "dry_run"]),
            AgentCapability("smoke_test_readonly", "Run a focused read-only smoke test", "medium", True, False, ["read_only", "dry_run"]),
            AgentCapability("report_writer", "Write run-local artifacts only", "medium", False, False, ["dry_run", "approval_required", "write_allowed"]),
            AgentCapability("file_patch_dry_run", "Preview a file patch", "medium", False, False, ["dry_run", "approval_required"]),
            AgentCapability("file_patch_apply_approval_required", "Apply a patch only with approval", "high", False, True, ["approval_required", "write_allowed"]),
            AgentCapability("git_commit_approval_required", "Commit only with approval", "high", False, True, ["approval_required", "write_allowed"]),
        ]

    def list_capabilities(self) -> List[Dict[str, Any]]:
        return [to_dict(c) for c in self.capabilities]

    def call(self, req: ToolCallRequest) -> ToolCallResult:
        from .governance import validate_mode, READ_ONLY_TOOL_NAMES, WRITE_TOOL_NAMES
        mode = validate_mode(req.mode)
        name = req.tool_name

        # Block write tools in read_only mode
        if mode == "read_only" and name in WRITE_TOOL_NAMES:
            return ToolCallResult(name, ok=False, blocked=True, error="write_tool_blocked_in_read_only_mode")

        # Block write tools in auto mode without explicit approval
        if mode == "auto" and name in WRITE_TOOL_NAMES:
            return ToolCallResult(name, ok=False, blocked=True, approval_required=True, error="build_requires_explicit_approval")

        # Require approval for approval-required tools in build mode
        if name in {"file_patch_apply_approval_required", "git_commit_approval_required"}:
            if mode not in {"build", "write_allowed"}:
                return ToolCallResult(name, ok=False, blocked=True, approval_required=True, error="build_mode_required")
            if not write_allowed(mode, req.approval_token):
                return ToolCallResult(name, ok=False, blocked=True, approval_required=True, error="approval_required")

        if name == "repo_status_read":
            return self._repo_status(name)
        if name == "repo_history_read":
            return self._repo_history(name, req.args)
        if name == "file_read":
            return self._file_read(name, req.args)
        if name == "grep_search":
            return self._grep(name, req.args)
        if name == "route_probe":
            return self._route_probe(name, req.args)
        if name == "semantic_retrieve":
            from .memory_gateway import MemoryGatewayV2
            return ToolCallResult(name, ok=True, result=MemoryGatewayV2().semantic_retrieve(req.args.get("query", ""), int(req.args.get("top_k", 3))))
        if name == "smoke_test_readonly":
            return self._smoke(name, req.args)
        if name in {"report_writer", "file_patch_dry_run"}:
            return ToolCallResult(name, ok=True, result={"dry_run": mode != "build", "preview": req.args})
        return ToolCallResult(name, ok=False, error="unknown_tool")

    def _repo_history(self, name, args):
        def run(cmd):
            p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace")
            return p.stdout.strip().splitlines()
        limit = int(args.get("limit", 10))
        return ToolCallResult(name, ok=True, result={
            "log": run(["git", "log", f"-{limit}", "--oneline"]),
            "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
            "head": run(["git", "rev-parse", "--short", "HEAD"]),
        })

    def _repo_status(self, name):
        def run(cmd):
            p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace")
            return p.stdout.strip().splitlines()
        return ToolCallResult(name, ok=True, result={"head": run(["git", "rev-parse", "--short", "HEAD"]), "status": run(["git", "status", "--short", "--untracked-files=no"])})

    def _file_read(self, name, args):
        path = str(args.get("path", ""))
        if path_is_blocked(path):
            return ToolCallResult(name, ok=False, blocked=True, error="path_blocked")
        p = (ROOT / path).resolve()
        if not str(p).startswith(str(ROOT)) or not p.exists() or p.is_dir():
            return ToolCallResult(name, ok=False, error="not_found_or_outside_repo")
        if p.stat().st_size > MAX_FILE_READ_BYTES:
            return ToolCallResult(name, ok=False, blocked=True, error="file_too_large")
        sample = p.read_bytes()[:2048]
        if b"\x00" in sample:
            return ToolCallResult(name, ok=False, blocked=True, error="binary_file_blocked")
        return ToolCallResult(name, ok=True, result={"path": path, "text": p.read_text(encoding="utf-8", errors="replace")[:4000]})

    def _grep(self, name, args):
        pattern = str(args.get("pattern", "agent"))
        glob = str(args.get("glob", "*.py"))
        cmd = [
            "rg", "-n", pattern, "-g", glob,
            "-g", "!memory/semantic/**", "-g", "!tmp_agent/strategies/**",
            "-g", "!.git/**", "-g", "!node_modules/**", "-g", "!**/__pycache__/**",
        ]
        p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace", timeout=10)
        return ToolCallResult(name, ok=True, result={"returncode": p.returncode, "matches": p.stdout.splitlines()[:50]})

    def _route_probe(self, name, args):
        raw_url = str(args.get("url", "http://127.0.0.1:8091/health"))
        method = str(args.get("method", "GET")).upper()

        # Port-safe: preserve explicit user-provided URLs/ports.
        # Only normalize bare relative paths to correct base URLs.
        url = raw_url
        if not (url.startswith("http://") or url.startswith("https://")):
            if url.startswith("/v2/") or url.startswith("/agent/"):
                url = "http://127.0.0.1:8091" + url
            elif url.startswith("/brain-dashboard/"):
                url = "http://127.0.0.1:8092" + url
            elif url.startswith("/"):
                url = "http://127.0.0.1:8091" + url
            elif url.isdigit() or re.match(r'^\d{1,5}$', url):
                # Bare port number preserved
                url = f"http://127.0.0.1:{url}/health"
            else:
                return ToolCallResult(name, ok=False, blocked=True, error="invalid_route_probe_url")

        if not (url.startswith("http://127.0.0.1") or url.startswith("http://localhost")):
            return ToolCallResult(name, ok=False, blocked=True, error="only_local_routes_allowed")
        if method not in {"GET", "POST"}:
            return ToolCallResult(name, ok=False, blocked=True, error="method_blocked")
        if method == "POST":
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.path not in SAFE_POST_PATHS:
                return ToolCallResult(name, ok=False, blocked=True, error="post_path_not_allowlisted")
        try:
            if method == "POST":
                data = json.dumps(args.get("json") or {"goal": "Agent V2 safe route probe", "mode": "read_only"}).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            else:
                req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return ToolCallResult(name, ok=True, result={"url": url, "status": resp.status, "body": resp.read(800).decode("utf-8", "replace")})
        except Exception as exc:
            return ToolCallResult(name, ok=False, result={"url": url}, error=str(exc)[:200])

    def _smoke(self, name, args):
        target = str(args.get("target", "tests/smoke/smoke_front_brain_agent_full_rebuild_langgraph_recursive_closeout_01.py"))
        if path_is_blocked(target) or target not in SMOKE_ALLOWLIST:
            return ToolCallResult(name, ok=False, blocked=True, error="target_blocked")
        p = subprocess.run(["python", "-m", "pytest", target, "-q"], cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace", timeout=60)
        return ToolCallResult(name, ok=p.returncode == 0, result={"returncode": p.returncode, "stdout": p.stdout[-2000:], "stderr": p.stderr[-1000:]})
