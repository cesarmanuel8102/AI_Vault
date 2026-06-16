from __future__ import annotations
from pathlib import Path
from .state import FORBIDDEN_PATH_PARTS, RAW_COT_MARKERS


def normalize_path(path: str) -> str:
    return str(path or "").replace("\\", "/")


def path_is_blocked(path: str) -> bool:
    p = normalize_path(path).lower()
    return any(part.lower() in p for part in FORBIDDEN_PATH_PARTS)


def contains_raw_cot(text: str) -> bool:
    t = (text or "").lower()
    return any(marker in t for marker in RAW_COT_MARKERS)


def validate_mode(mode: str) -> str:
    return mode if mode in {"read_only", "dry_run", "approval_required", "write_allowed"} else "read_only"


def write_allowed(mode: str, approval_token: str | None = None) -> bool:
    return mode == "write_allowed" and bool(approval_token and approval_token.startswith("AGENTV2_APPROVED_"))
