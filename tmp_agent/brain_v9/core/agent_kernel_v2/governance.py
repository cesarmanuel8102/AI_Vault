from __future__ import annotations
from pathlib import Path
from .state import FORBIDDEN_PATH_PARTS, RAW_COT_MARKERS
from .schemas import LEGACY_MODE_MAP


MODE_COMMAND_PATTERNS = [
    # Spanish patterns
    ("build", ["hazlo en build", "modo build", "eleva a build", "pon en build", "activa build", "switch a build", "cambia a build", "enable build mode", "apruebo build"]),
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
    "repo_file_search", "repo_file_read", "memory_structure_inspect",
    "semantic_memory_status", "promotion_queue_status", "capability_registry_read",
}

# Governance-critical files that self-dev tools must not modify without explicit governance approval
GOVERNANCE_PROTECTED_PATHS = {
    "tmp_agent/brain_v9/api_security.py",
    "tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py",
    "tmp_agent/brain_v9/core/agent_kernel_v2/governance.py",
    "scripts/git_hygiene/check_no_sensitive_paths_staged.py",
    "tests/smoke/_accepted_runtime_baseline.py",
    "tests/smoke/test_agent_v2_auth_endpoints_01.py",
    "tests/smoke/test_governance_rbac_dev_god_hardening_01.py",
    ".gitignore",
}

FORBIDDEN_REQUEST_FIELDS = {
    "god", "god_mode", "safe_mode", "override_governance",
    "bypass_auth", "bypass_rbac", "mode",  # mode values god/build/execute blocked in specific validators
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
    """Parse natural-language mode switch commands from user message.

    Logic:
    1. Explicit Spanish/English phrase patterns (modo build, hazlo en auto, etc.).
    2. Whole-word 'read_only' keyword (safe because it is not a common English word).
    3. Do NOT match standalone English words 'build' or 'auto' — these appear in normal
       sentences ('build pipeline', 'autonomous promotion') and must NOT trigger mode
       switches unless paired with an explicit command phrase.
    """
    import re
    m = (message or "").lower()
    # 1. Explicit phrase patterns from MODE_COMMAND_PATTERNS
    for mode, patterns in MODE_COMMAND_PATTERNS:
        for pat in patterns:
            if pat in m:
                return mode
    # 2. Whole-word 'read_only' keyword (rare in normal text, safe to match standalone)
    if re.search(r'\bread_only\b', m):
        return "read_only"
    return None


def infer_auto_decision(goal: str) -> str:
    """Infer whether an auto-mode goal requires build or is read-only."""
    g = (goal or "").lower()
    if any(kw in g for kw in WRITE_INTENT_KEYWORDS):
        return "build_required"
    return "read"


def validate_mode(mode: str) -> str:
    """Normalize mode to one of read_only, build, auto. Reject dangerous modes like god."""
    if mode in {"read_only", "build", "auto"}:
        return mode
    # Reject dangerous modes regardless of token
    lower = str(mode).lower().strip()
    if lower in {"god", "god_mode", "execute", "unsafe", "superuser"}:
        return "read_only"  # Fallback to safe default
    return LEGACY_MODE_MAP.get(mode, "read_only")


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


def escalate_auto_mode_effective(mode_requested: str, escalation_required: bool, goal: str) -> str:
    """Return the effective mode for an auto request after escalation analysis.

    If the user explicitly requested auto but governance detects write/build intent,
    the effective mode should reflect that the run is blocked/pending approval rather
    than misleadingly staying 'auto'. For read_only or build modes the requested mode
    is returned unchanged.
    """
    if mode_requested == "auto" and escalation_required:
        return "approval_required"
    return mode_requested


def write_allowed(mode: str, approval_token: str | None = None) -> bool:
    """Check if write is allowed with valid approval token."""
    return mode == "build" and bool(approval_token and approval_token.startswith("AGENTV2_APPROVED_"))


def selfdev_governance_blocked(path: str) -> bool:
    """Check if a self-dev path targets governance-critical files."""
    p = normalize_path(path)
    return any(protected in p for protected in GOVERNANCE_PROTECTED_PATHS)


def contains_forbidden_request_fields(args: dict) -> bool:
    """Check if request args contain forbidden bypass/override fields."""
    if not args:
        return False
    lower_keys = {str(k).lower().strip() for k in args.keys()}
    forbidden = {"god", "god_mode", "safe_mode", "override_governance", "bypass_auth", "bypass_rbac"}
    return bool(lower_keys & forbidden)
