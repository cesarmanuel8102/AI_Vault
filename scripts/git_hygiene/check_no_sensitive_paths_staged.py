"""
Git staging guard for sensitive/runtime paths.

Usage:
    python scripts/git_hygiene/check_no_sensitive_paths_staged.py

Exit 0 if safe; exit 1 and print blocking paths otherwise.

Policy:
- Staged deletions (status D) of sensitive paths are allowed because they
  remove runtime content from Git tracking.
- Staged additions, modifications, renames, or copies (A/M/R/C) of sensitive
  paths are blocked.
- Safe report artifacts under tmp_agent/front_* are allowed unless they
  are memory dumps.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path("C:/AI_VAULT_CANONICAL")

# (status_letter, path) status from git diff --cached --name-status
StagedFile = Tuple[str, str]


BLOCKED_PATH_PREFIXES = (
    "memory/semantic/",
    "memory/rollback_snapshots/",
    "memory/autonomous_journal.jsonl",
    "audit_reports/secrets_report.csv",
    ".env",
    ".env.",
    "*.key",
    "credentials.enc",
    ".dev_auth/",
)

BLOCKED_GLOBS = (
    "*.key",
    "credentials.enc",
)

ALLOWED_EXACT = (
    ".env.example",
)


def _is_blocked_path(status: str, path: str) -> bool:
    # Deletions are fine: they untrack sensitive paths.
    if status == "D":
        return False

    if path in ALLOWED_EXACT:
        return False

    norm = path.replace("\\", "/")

    # Secrets / env
    if norm.startswith(".env") and not norm.startswith(".env.example"):
        return True
    if any(norm.endswith(g) for g in BLOCKED_GLOBS):
        return True
    if norm.startswith(".dev_auth/"):
        return True

    # Runtime memory
    if norm.startswith("memory/semantic/"):
        return True
    if norm.startswith("memory/rollback_snapshots/"):
        return True
    if norm == "memory/autonomous_journal.jsonl":
        return True

    # Sensitive audit reports
    if norm == "audit_reports/secrets_report.csv":
        return True

    return False


def _load_staged_files() -> List[StagedFile]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    files: List[StagedFile] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[1]
        # Rename/copy lines look like "R100 old new" or "C100 old new"
        if status.startswith("R") or status.startswith("C"):
            pieces = path.split(maxsplit=1)
            if len(pieces) == 2:
                files.append((status[0], pieces[1]))
        else:
            files.append((status, path))
    return files


def main() -> int:
    staged = _load_staged_files()
    blocked = [(status, path) for status, path in staged if _is_blocked_path(status, path)]

    if not blocked:
        print("SAFE: no sensitive/runtime content staged as added/modified/copied.")
        return 0

    print("BLOCKED: sensitive/runtime paths are staged as content changes:")
    for status, path in blocked:
        print(f"  [{status}] {path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
