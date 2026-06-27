"""
Repo root helper for CI portability.
Resolves repository root from current file or GITHUB_WORKSPACE.
Use this instead of hardcoded C:\AI_VAULT_CANONICAL.
"""
import os
from pathlib import Path


def get_repo_root() -> Path:
    """Return absolute Path to repository root."""
    # CI environment variable
    if os.environ.get("GITHUB_WORKSPACE"):
        return Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    # Fallback: traverse from this file (tests/_repo_root.py)
    # tests/ is one level below repo root
    return Path(__file__).resolve().parent.parent


REPO_ROOT: Path = get_repo_root()
