"""
brain/semantic_memory_canary_lookup_read_only.py
FRONT-REAL-READ-LOOKUP-ADAPTER-01

Strictly read-only adapter that locates and validates the canary record
inside memory/semantic/semantic_memory.jsonl.

Guarantees:
- No file writes.
- No FAISS import or index modification.
- No server start or network access.
- Only stdlib.
"""

from pathlib import Path
import hashlib
import json
import os
from typing import Dict, List, Any, Optional


DEFAULT_CANARY_ID = "canary-00000000-0000-0000-0000-000000000001"
DEFAULT_TARGET_PATH = "memory/semantic/semantic_memory.jsonl"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str) -> str:
    """Return SHA-256 of file contents."""
    with open(path, "rb") as f:
        return _sha256_bytes(f.read())


def lookup_canary_record(
    target_path: str = DEFAULT_TARGET_PATH,
    canary_id: str = DEFAULT_CANARY_ID,
) -> Dict[str, Any]:
    """
    Read-only lookup of a canary record inside a JSONL file.
    Returns structured result without writing anything.
    """
    result: Dict[str, Any] = {
        "found": False,
        "count": 0,
        "line_number": None,
        "total_lines": 0,
        "is_last_line": False,
        "record": None,
        "validation": None,
        "no_write": True,
        "faiss_used": False,
        "errors": [],
    }

    resolved = Path(target_path).resolve()
    if not resolved.is_file():
        result["errors"].append(f"target_missing: {target_path}")
        return result

    results: List[Dict[str, Any]] = []
    line_number = 0
    try:
        with open(resolved, "r", encoding="utf-8") as fh:
            for idx, raw in enumerate(fh, start=1):
                line_number = idx
                if not raw.strip():
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError as exc:
                    result["errors"].append(f"invalid_jsonl_at_line_{idx}: {exc}")
                    result["total_lines"] = idx
                    return result

                if obj.get("id") == canary_id:
                    results.append(obj)
                    result["line_number"] = idx
    except Exception as exc:
        result["errors"].append(f"read_error: {exc}")
        return result

    result["total_lines"] = line_number
    result["count"] = len(results)

    if len(results) == 0:
        result["found"] = False
        result["errors"].append(f"canary_id_not_found: {canary_id}")
        return result

    if len(results) > 1:
        result["found"] = True
        result["errors"].append(f"duplicate_canary_id: {canary_id} appears {len(results)} times")
        return result

    record = results[0]
    result["found"] = True
    result["record"] = record
    result["is_last_line"] = (result["line_number"] == result["total_lines"])
    result["validation"] = validate_canary_record(record)
    return result


def validate_canary_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the canary record structure and metadata flags.
    """
    valid = True
    errors: List[str] = []

    if record.get("id") != DEFAULT_CANARY_ID:
        valid = False
        errors.append("id_mismatch")

    if record.get("kind") != "canary":
        valid = False
        errors.append("kind_not_canary")

    if record.get("source") != "front_real_canary_exec_01":
        valid = False
        errors.append("source_mismatch")

    meta = record.get("metadata", {})
    checks = [
        ("metadata.canary", meta.get("canary") is True),
        ("metadata.front", meta.get("front") == "FRONT-REAL-CANARY-EXEC-01"),
        ("metadata.single_record_canary", meta.get("single_record_canary") is True),
        ("metadata.faiss_write", meta.get("faiss_write") is False),
        ("metadata.promotion", meta.get("promotion") is False),
        ("metadata.patch_application", meta.get("patch_application") is False),
        ("metadata.trading", meta.get("trading") is False),
        ("metadata.b8", meta.get("b8") is False),
    ]

    for name, ok in checks:
        if not ok:
            valid = False
            errors.append(f"{name}_failed")

    return {
        "valid": valid,
        "errors": errors,
        "required_keys_present": all(k in record for k in
            ("created_utc", "id", "kind", "metadata", "session_id", "source", "text")),
    }
