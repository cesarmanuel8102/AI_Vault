from __future__ import annotations
from pathlib import Path
from .state import FORBIDDEN_PATH_PARTS, RAW_COT_MARKERS
from .schemas import LEGACY_MODE_MAP


MODE_COMMAND_PATTERNS = [
    # Spanish patterns
    ("build", ["hazlo en build", "modo build", "eleva a build", "pon en build", "activa build", "switch a build", "cambia a build", "enable build mode"]),
    ("read_only", ["modo read", "modo lectura", "modo solo lectura", "read mode", "modo read only", "pon en read", "hazlo en read", "eleva a read", "cambia a read"]),
    ("auto", ["modo auto", "automatico", "modo automatico", "pon en auto", "hazlo en auto", "switch a auto", "cambia a auto", "enable auto mode"]),
]

WRITE_INTENT_KEYWORDS = [
    "fix", "patch", "edit", "modify", "change", "update", "refactor",
    "rewrite", "create", "add", "remove", "delete", "rename", "move",
    "commit", "push", "merge", "pull", "deploy", "build", "install",
    "configure", "setup", "hack", "adjust", "tune", "optimize",
]

WRITE_TOOL_NAMES = {
    "file_patch_dry_run", "file_patch_apply_approval_required",
    "git_commit_approval_required", "report_writer",
}

READ_ONLY_TOOL_NAMES = {
    "repo_status_read", "repo_history_read", "repo_diff_read",
    "grep_search", "file_read", "route_probe", "semantic_retrieve",
    "smoke_test_readonly",
}


def normalize_path(path: str) -> str:
    return str(path or "").replace("\\", "/")


def path_is_blocked(path: str) -> bool:
    p = normalize_path(path).lower()
    return any(part.lower() in p for part in FORBIDDEN_PATH_PARTS)


def contains_raw_cot(text: str) -> bool:
    t = (text or "").lower()
    return any(marker in t for marker in RAW_COT_MARKERS)


def parse_mode_from_message(message: str) -> str | None:
    """Parse natural-language mode switch commands from user message."""
    m = (message or "").lower()
    # Direct mode keywords first (shortest wins)
    for keyword in ["read_only", "build", "auto"]:
        if keyword in m:
            return keyword
    # Pattern matching
    for mode, patterns in MODE_COMMAND_PATTERNS:
        for pat in patterns:
            if pat in m:
                return mode
    return None


def validate_mode(mode: str) -> str:
    """Normalize mode to one of read_only, build, auto."""
    if mode in {"read_only", "build", "auto"}:
        return mode
    return LEGACY_MODE_MAP.get(mode, "read_only")


def infer_auto_decision(goal: str) -> str:
    """Infer whether an auto-mode goal requires build or is read-only."""
    g = (goal or "").lower()
    if any(kw in g for kw in WRITE_INTENT_KEYWORDS):
        return "build_required"
    return "read"


def mode_requires_escalation(goal: str, mode: str, scheduled_tools: list[str]) -> bool:
    """Check if the current mode requires escalation to build."""
    effective_mode = validate_mode(mode)

    if effective_mode == "build":
        return False

    if effective_mode == "read_only":
        # Check if any scheduled tools are write tools
        if any(t in WRITE_TOOL_NAMES for t in scheduled_tools):
            return True
        # Check if goal implies build intent
        if infer_auto_decision(goal) == "build_required":
            return True
        return False

    if effective_mode == "auto":
        return infer_auto_decision(goal) == "build_required"

    return False


def write_allowed(mode: str, approval_token: str | None = None) -> bool:
    """Check if write is allowed with valid approval token."""
    return mode == "build" and bool(approval_token and approval_token.startswith("AGENTV2_APPROVED_"))
