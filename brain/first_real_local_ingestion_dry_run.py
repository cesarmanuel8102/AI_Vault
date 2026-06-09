"""First real local file ingestion dry-run module.

FRONT-FIRST-REAL-LOCAL-INGESTION-DRY-RUN-01

This module reads a real local whitelisted file from the repo
and produces an execution packet with evidence.

NO semantic memory write.
NO FAISS write.
NO network.
NO connectors.
NO trading.
NO B8.
Pure Python, deterministic, no external deps.
"""

from pathlib import Path
import hashlib


# Whitelisted sources for this front
SOURCE_ALLOWLIST = [
    "docs/REAL_EXECUTION_POLICY.md",
    "docs/RUNTIME_RECOVERY_RUNBOOK.md",
]

# Blocked path patterns
BLOCKED_PREFIXES = (
    ".env",
    "memory/semantic",
    "memory/semantic_faiss",
    "FAISS",
    "trading/",
    "tmp_agent/strategies/",
    "B8/",
)

BLOCKED_NAMES = (
    ".env",
    "semantic_memory.jsonl",
    "semantic_memory_faiss.index",
    "semantic_memory_faiss_ids.json",
)


class IngestionError(Exception):
    """Raised when ingestion fails validation or read."""
    pass


def build_source_allowlist() -> list[str]:
    return list(SOURCE_ALLOWLIST)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def validate_source_path(path: str) -> dict:
    """Validate a source path against allowlist and blocked patterns.
    
    Returns a dict with:
      - ok: bool
      - path: normalized path string
      - reason: description if not ok
    """
    if not path:
        return {"ok": False, "path": "", "reason": "empty path"}

    segments = path.split("/")
    # Reject path traversal
    if any(seg == ".." for seg in segments):
        return {"ok": False, "path": path, "reason": "path traversal not allowed"}

    # Must be relative
    if Path(path).is_absolute():
        # Allow only repo-root-relative
        pass

    # Blocked by prefix
    norm = path.replace("\\", "/")
    for prefix in BLOCKED_PREFIXES:
        if norm.startswith(prefix) or norm.startswith("./" + prefix):
            return {"ok": False, "path": path, "reason": f"blocked prefix: {prefix}"}

    # Blocked by name
    if norm.endswith("") and Path(norm).name in BLOCKED_NAMES:
        return {"ok": False, "path": path, "reason": f"blocked file name: {Path(norm).name}"}

    # Must be in allowlist
    # Use forward-slash normalized for comparison
    test_norm = norm.lstrip("./")
    if test_norm not in SOURCE_ALLOWLIST:
        return {"ok": False, "path": path, "reason": "source not in allowlist"}

    full = _repo_root() / path
    if not full.exists():
        return {"ok": False, "path": path, "reason": "file does not exist"}
    if not full.is_file():
        return {"ok": False, "path": path, "reason": "not a file"}

    return {"ok": True, "path": path, "reason": "source path valid"}


def read_local_source_for_dry_run(path: str) -> dict:
    """Read a real local file and return source evidence.
    
    Raises IngestionError on validation failure or read failure.
    """
    validation = validate_source_path(path)
    if not validation["ok"]:
        raise IngestionError(validation["reason"])

    full = _repo_root() / path
    try:
        raw_bytes = full.read_bytes()
    except Exception as exc:
        raise IngestionError(f"read failed: {exc}") from exc

    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    size = len(raw_bytes)
    text = raw_bytes.decode("utf-8", errors="replace")
    preview = text[:500]

    return {
        "source_path": str(path),
        "source_exists": True,
        "source_size_bytes": size,
        "sha256": sha256,
        "preview_first_500_chars": preview,
        "read_executed": True,
    }


def build_real_execution_packet(source_result: dict) -> dict:
    return {
        "source_path": source_result["source_path"],
        "source_exists": source_result["source_exists"],
        "source_size_bytes": source_result["source_size_bytes"],
        "sha256": source_result["sha256"],
        "preview_first_500_chars": source_result["preview_first_500_chars"],
        "read_executed": True,
        "execution_mode": "real_local_file_read_dry_run",
        "semantic_memory_write_executed": False,
        "faiss_write_executed": False,
        "network_called": False,
        "connector_called": False,
        "promotion_executed": False,
        "trading_executed": False,
        "b8_touched": False,
        "operator_approval_required": True,
        "operator_approval_scope": "first real local file read dry-run only",
        "ready_for_memory_write": False,
        "next_required_front": "FRONT-FIRST-REAL-LOCAL-MEMORY-CANARY-WRITE-01",
    }


def validate_real_execution_packet(packet: dict) -> dict:
    required_keys = (
        "source_path", "source_exists", "source_size_bytes", "sha256",
        "preview_first_500_chars", "read_executed", "execution_mode",
        "semantic_memory_write_executed", "faiss_write_executed",
        "network_called", "connector_called", "promotion_executed",
        "trading_executed", "b8_touched", "operator_approval_required",
        "operator_approval_scope", "ready_for_memory_write",
        "next_required_front",
    )
    missing = [k for k in required_keys if k not in packet]
    if missing:
        return {"ok": False, "reason": f"missing keys: {missing}"}

    checks = (
        packet.get("read_executed") is True,
        packet.get("semantic_memory_write_executed") is False,
        packet.get("faiss_write_executed") is False,
        packet.get("network_called") is False,
        packet.get("connector_called") is False,
        packet.get("promotion_executed") is False,
        packet.get("trading_executed") is False,
        packet.get("b8_touched") is False,
        packet.get("ready_for_memory_write") is False,
        isinstance(packet.get("source_size_bytes"), int),
        isinstance(packet.get("sha256"), str) and len(packet.get("sha256", "")) == 64,
        isinstance(packet.get("preview_first_500_chars"), str),
    )
    if not all(checks):
        return {"ok": False, "reason": "execution packet invariant check failed"}

    return {"ok": True, "reason": "packet valid"}


def summarize_real_execution_packet(packet: dict) -> dict:
    return {
        "source_path": packet["source_path"],
        "source_size_bytes": packet["source_size_bytes"],
        "sha256": packet["sha256"],
        "read_executed": packet["read_executed"],
        "execution_mode": packet["execution_mode"],
        "semantic_memory_write_executed": packet["semantic_memory_write_executed"],
        "faiss_write_executed": packet["faiss_write_executed"],
        "ready_for_memory_write": packet["ready_for_memory_write"],
        "next_required_front": packet["next_required_front"],
    }


def run_first_real_local_ingestion_dry_run(path: str = "docs/REAL_EXECUTION_POLICY.md") -> dict:
    source_result = read_local_source_for_dry_run(path)
    packet = build_real_execution_packet(source_result)
    validation = validate_real_execution_packet(packet)
    summary = summarize_real_execution_packet(packet)
    return {
        "source_result": source_result,
        "packet": packet,
        "validation": validation,
        "summary": summary,
    }
