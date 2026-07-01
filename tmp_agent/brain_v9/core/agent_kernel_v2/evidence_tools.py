"""Read-only evidence tools for Brain Agent V2.

Provides safe inspection capabilities that do NOT mutate state.
All tools return evidence with mutated_state=False.
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[4]


def _safe_path(path_str: str) -> Path | None:
    """Resolve and validate path is within repo root."""
    try:
        p = (REPO_ROOT / path_str).resolve()
        if not str(p).startswith(str(REPO_ROOT)):
            return None
        return p
    except Exception:
        return None


def repo_file_search(pattern: str, glob: str = "*.py") -> Dict[str, Any]:
    """Search repo text files for pattern (read-only, safe)."""
    import subprocess
    cmd = [
        "rg", "-n", "-i", pattern, "-g", glob,
        "-g", "!.git/**", "-g", "!node_modules/**",
        "-g", "!**/__pycache__/**", "-g", "!tmp_agent/strategies/**",
    ]
    try:
        p = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace", timeout=10)
        matches = p.stdout.splitlines()[:30]
        return {"tool_name": "repo_file_search", "ok": True, "mutated_state": False, "summary": f"Found {len(matches)} matches for '{pattern}'", "evidence": matches, "error": None}
    except Exception as e:
        return {"tool_name": "repo_file_search", "ok": False, "mutated_state": False, "summary": f"Search failed: {e}", "evidence": [], "error": str(e)[:200]}


def repo_file_read(path: str, max_bytes: int = 4000) -> Dict[str, Any]:
    """Read a safe repo file (read-only, path-traversal protected)."""
    p = _safe_path(path)
    if p is None:
        return {"tool_name": "repo_file_read", "ok": False, "mutated_state": False, "summary": f"Path blocked or outside repo: {path}", "evidence": [], "error": "path_blocked"}
    if not p.exists() or p.is_dir():
        return {"tool_name": "repo_file_read", "ok": False, "mutated_state": False, "summary": f"Not found: {path}", "evidence": [], "error": "not_found"}
    if p.stat().st_size > 128_000:
        return {"tool_name": "repo_file_read", "ok": False, "mutated_state": False, "summary": f"File too large: {path}", "evidence": [], "error": "file_too_large"}
    sample = p.read_bytes()[:2048]
    if b"\x00" in sample:
        return {"tool_name": "repo_file_read", "ok": False, "mutated_state": False, "summary": f"Binary file blocked: {path}", "evidence": [], "error": "binary_file_blocked"}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")[:max_bytes]
        return {"tool_name": "repo_file_read", "ok": True, "mutated_state": False, "summary": f"Read {len(text)} chars from {path}", "evidence": [{"path": path, "text": text}], "error": None}
    except Exception as e:
        return {"tool_name": "repo_file_read", "ok": False, "mutated_state": False, "summary": f"Read error: {e}", "evidence": [], "error": str(e)[:200]}


def memory_structure_inspect() -> Dict[str, Any]:
    """List known memory directories/files/status (read-only)."""
    evidence = []
    dirs_to_check = [
        "tmp_agent/brain_v9/memory",
        "tmp_agent/state/memory",
        "tmp_agent/state/memory/semantic",
        "memory",
        "memory/semantic",
    ]
    for d in dirs_to_check:
        p = _safe_path(d)
        if p and p.exists():
            try:
                files = [str(f.relative_to(REPO_ROOT)) for f in p.iterdir() if f.is_file()][:20]
                evidence.append({"dir": d, "exists": True, "file_count": len(list(p.iterdir())), "files": files})
            except Exception as e:
                evidence.append({"dir": d, "exists": True, "error": str(e)[:100]})
        else:
            evidence.append({"dir": d, "exists": False})

    # Check FAISS/index files
    faiss_dirs = ["tmp_agent/state/memory/semantic", "memory/semantic"]
    faiss_found = []
    for d in faiss_dirs:
        p = _safe_path(d)
        if p and p.exists():
            for f in p.iterdir():
                if "faiss" in f.name.lower() or f.suffix in {".index", ".faiss", ".jsonl"}:
                    faiss_found.append(str(f.relative_to(REPO_ROOT)))

    evidence.append({"faiss_index_files": faiss_found[:10]})

    # Check autonomy heartbeat
    heartbeat_files = []
    for d in ["tmp_agent/state", "tmp_agent/brain_v9"]:
        p = _safe_path(d)
        if p and p.exists():
            for f in p.rglob("*heartbeat*"):
                heartbeat_files.append(str(f.relative_to(REPO_ROOT)))

    evidence.append({"heartbeat_files": heartbeat_files[:5]})

    summary = f"Memory dirs: {sum(1 for e in evidence if isinstance(e, dict) and e.get('exists'))}, FAISS files: {len(faiss_found)}, heartbeat files: {len(heartbeat_files)}"
    return {"tool_name": "memory_structure_inspect", "ok": True, "mutated_state": False, "summary": summary, "evidence": evidence, "error": None}


def semantic_memory_status() -> Dict[str, Any]:
    """Read-only status of semantic memory/FAISS files."""
    evidence = []
    faiss_dirs = ["tmp_agent/state/memory/semantic", "memory/semantic"]
    for d in faiss_dirs:
        p = _safe_path(d)
        if p and p.exists():
            try:
                entries = list(p.iterdir())
                files = []
                for f in entries:
                    if f.is_file():
                        files.append({"name": f.name, "size": f.stat().st_size, "mtime": f.stat().st_mtime})
                evidence.append({"dir": d, "exists": True, "file_count": len(entries), "files": files[:10]})
            except Exception as e:
                evidence.append({"dir": d, "exists": True, "error": str(e)[:100]})
        else:
            evidence.append({"dir": d, "exists": False})

    summary = f"Semantic memory dirs checked: {len(evidence)}, files found: {sum(len(e.get('files', [])) for e in evidence if isinstance(e, dict) and e.get('exists'))}"
    return {"tool_name": "semantic_memory_status", "ok": True, "mutated_state": False, "summary": summary, "evidence": evidence, "error": None}


def promotion_queue_status() -> Dict[str, Any]:
    """Read-only status of promotion/review queues."""
    evidence = []
    queue_dirs = [
        "tmp_agent/state/promotion_queue",
        "tmp_agent/state/promotion_candidates",
        "tmp_agent/state/review_queue",
    ]
    for d in queue_dirs:
        p = _safe_path(d)
        if p and p.exists():
            try:
                entries = list(p.iterdir())
                evidence.append({"dir": d, "exists": True, "entry_count": len(entries), "entries": [e.name for e in entries[:10]]})
            except Exception as e:
                evidence.append({"dir": d, "exists": True, "error": str(e)[:100]})
        else:
            evidence.append({"dir": d, "exists": False})

    summary = f"Promotion/review queues checked: {len(evidence)}, existing: {sum(1 for e in evidence if isinstance(e, dict) and e.get('exists'))}"
    return {"tool_name": "promotion_queue_status", "ok": True, "mutated_state": False, "summary": summary, "evidence": evidence, "error": None}


def capability_registry_read() -> Dict[str, Any]:
    """Read current capabilities and known gaps."""
    from .capability_registry import build_capability_report
    from .governance import READ_ONLY_TOOL_NAMES, WRITE_TOOL_NAMES
    evidence: Dict[str, Any] = {
        "read_only_tools": sorted(list(READ_ONLY_TOOL_NAMES)),
        "write_tools": sorted(list(WRITE_TOOL_NAMES)),
        "all_tools": sorted(list(set(READ_ONLY_TOOL_NAMES) | set(WRITE_TOOL_NAMES))),
    }
    try:
        report = build_capability_report(None)
        evidence["capability_report"] = report
    except Exception as e:
        evidence["capability_report_error"] = str(e)[:100]

    summary = f"Tools available: {len(evidence['all_tools'])}, read-only: {len(evidence['read_only_tools'])}, write: {len(evidence['write_tools'])}"
    return {"tool_name": "capability_registry_read", "ok": True, "mutated_state": False, "summary": summary, "evidence": evidence, "error": None}


# Mapping for ToolGatewayV2 dispatch
EVIDENCE_TOOL_MAP = {
    "repo_file_search": repo_file_search,
    "repo_file_read": repo_file_read,
    "memory_structure_inspect": memory_structure_inspect,
    "semantic_memory_status": semantic_memory_status,
    "promotion_queue_status": promotion_queue_status,
    "capability_registry_read": capability_registry_read,
}


def dispatch_evidence_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a read-only evidence tool by name."""
    fn = EVIDENCE_TOOL_MAP.get(tool_name)
    if fn is None:
        return {"tool_name": tool_name, "ok": False, "mutated_state": False, "summary": f"Unknown evidence tool: {tool_name}", "evidence": [], "error": "unknown_evidence_tool"}
    try:
        return fn(**args)
    except Exception as e:
        return {"tool_name": tool_name, "ok": False, "mutated_state": False, "summary": f"Tool execution error: {e}", "evidence": [], "error": str(e)[:200]}
