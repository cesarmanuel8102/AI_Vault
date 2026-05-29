"""
trace_redactor.py — VTC-A1
Safe event redactor for Agent Visual Trace Console.
Removes blocked fields, scrubs secrets, redacts protected paths,
truncates strings, and limits data field size.
Never mutates the original event dict.
"""
import copy
import json
import re
from typing import Any, Dict, List, Optional, Union

BLOCKED_FIELDS = {
    "chain_of_thought",
    "reasoning",
    "scratchpad",
    "raw_prompt",
    "raw_completion",
    "api_key",
    "token",
    "password",
    "secret",
    "credential",
    "full_file_content",
    "memory_dump",
    "provider_internal_trace",
    "model_internals",
    "hidden_state",
    "embedding",
    "vector_dump",
    "private_notes",
    "internal_debug",
}

PROTECTED_PATHS = {
    "memory/semantic",
    "tmp_agent/strategies",
    "tmp_agent/reports",
    ".env",
    "credentials",
    "secrets",
    "keys",
    "config.json",
    "api_keys.json",
    "private_keys",
    "ssh_keys",
}

SECRET_PATTERNS = [
    # Assignment-style: field=value or field: value (whole assignment redacted)
    (
        re.compile(r"(?i)\b(password|token|api[_-]?key|secret|credential|auth[_-]?token|private[_-]?key)\b\s*[:=]\s*[^\s,;}\"'\]]+"),
        "[REDACTED_SECRET]",
    ),
    # HTTP header style: Authorization: Bearer <token>
    (
        re.compile(r"(?i)(Authorization\s*:\s*Bearer\s+)[a-zA-Z0-9_\-\.]{8,}"),
        r"\g<1>[REDACTED_SECRET]",
    ),
    # Bearer token inline
    (
        re.compile(r"(?i)\b(bearer)\s+[a-zA-Z0-9_\-\.]{8,}"),
        r"\g<1> [REDACTED_SECRET]",
    ),
    # Generic field-name patterns (replace whole match)
    (re.compile(r"(?i)\bapi[_-]?key\b"), "[REDACTED_SECRET]"),
    (re.compile(r"(?i)\bsecret[_-]?key\b"), "[REDACTED_SECRET]"),
    (re.compile(r"(?i)\bauth[_-]?token\b"), "[REDACTED_SECRET]"),
    (re.compile(r"(?i)\bpassword\b"), "[REDACTED_SECRET]"),
    (re.compile(r"(?i)\bprivate[_-]?key\b"), "[REDACTED_SECRET]"),
    # Known token prefixes (replace whole match)
    (re.compile(r"sk-[a-zA-Z0-9]{48,}"), "[REDACTED_SECRET]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36,}"), "[REDACTED_SECRET]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_SECRET]"),
]

MAX_LENGTHS = {
    "title": 120,
    "summary": 280,
    "text": 2000,
    "reason_summary": 200,
    "input_summary": 500,
    "output_summary": 500,
    "error_summary": 500,
}

DATA_FIELD_MAX_SERIALIZED = 10000


def _remove_blocked_fields(obj: Any) -> Any:
    """Recursively remove blocked keys from dicts."""
    if isinstance(obj, dict):
        return {
            k: _remove_blocked_fields(v)
            for k, v in obj.items()
            if k not in BLOCKED_FIELDS
        }
    elif isinstance(obj, list):
        return [_remove_blocked_fields(item) for item in obj]
    else:
        return obj


def _scrub_secrets(text: str) -> str:
    """Replace secret patterns with [REDACTED_SECRET]."""
    for pattern in SECRET_PATTERNS:
        if isinstance(pattern, tuple):
            regex, repl = pattern
            text = regex.sub(repl, text)
        else:
            text = pattern.sub("[REDACTED_SECRET]", text)
    return text


def _scrub_protected_paths(text: str) -> str:
    """Replace protected path substrings with [REDACTED_PATH]."""
    for path in PROTECTED_PATHS:
        text = text.replace(path, "[REDACTED_PATH]")
    return text


def _truncate_string(text: str, max_len: int) -> str:
    """Truncate string to max_len with ellipsis."""
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def _scrub_and_truncate_string(text: str, field_name: Optional[str] = None) -> str:
    """Apply secret scrubbing, path redaction, and length limits to a string."""
    text = _scrub_secrets(text)
    text = _scrub_protected_paths(text)
    if field_name is not None:
        max_len = MAX_LENGTHS.get(field_name, 2000)
    else:
        max_len = 2000
    return _truncate_string(text, max_len)


def _process_string_fields(obj: Any, field_name: Optional[str] = None) -> Any:
    """Recursively process string fields: scrub secrets, paths, truncate."""
    if isinstance(obj, str):
        return _scrub_and_truncate_string(obj, field_name)
    elif isinstance(obj, dict):
        return {
            k: _process_string_fields(v, k)
            for k, v in obj.items()
            if k not in BLOCKED_FIELDS
        }
    elif isinstance(obj, list):
        return [_process_string_fields(item, field_name) for item in obj]
    else:
        return obj


def _limit_data_size(event: Dict[str, Any]) -> Dict[str, Any]:
    """If data field serialized JSON exceeds limit, replace with redacted placeholder."""
    if "data" in event:
        serialized = json.dumps(event["data"], ensure_ascii=False, default=str)
        if len(serialized) > DATA_FIELD_MAX_SERIALIZED:
            event["data"] = {"_redacted": "large payload"}
    return event


def sanitize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a sanitized copy of the event.
    Removes blocked fields, scrubs secrets, redacts protected paths,
    truncates strings, and limits data size.
    Never mutates the original input dict.
    """
    safe = copy.deepcopy(event)
    safe = _remove_blocked_fields(safe)
    safe = _process_string_fields(safe)
    safe = _limit_data_size(safe)

    # If event is empty or only had blocked fields, return minimal redacted event
    if not safe or (len(safe) == 0):
        return {"type": "redacted", "title": "Redacted event"}

    return safe
