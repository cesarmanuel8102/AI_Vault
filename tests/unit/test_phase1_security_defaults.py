"""
FASE-1-BASELINE / Test 2
========================
Security-default invariants:
- BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS defaults to False when env var absent.
- .dev_auth/ is not tracked by git (no ls-files output).

Does not read any file inside .dev_auth/.
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TMP = _ROOT / "tmp_agent"
for p in (_ROOT, _TMP):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


def test_unsafe_dev_endpoints_default_off_when_env_absent():
    os.environ.pop("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", None)
    if "brain_v9.config" in sys.modules:
        cfg = importlib.reload(sys.modules["brain_v9.config"])
    else:
        cfg = importlib.import_module("brain_v9.config")
    assert cfg.BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS is False, (
        "Default must be False when env var is absent"
    )


def test_dev_auth_not_tracked_by_git():
    """git ls-files .dev_auth must return empty output."""
    res = subprocess.run(
        ["git", "ls-files", ".dev_auth"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"git ls-files failed: {res.stderr!r}"
    out = (res.stdout or "").strip()
    assert out == "", (
        "Expected NO tracked files under .dev_auth/, found: "
        + ", ".join(out.splitlines())
    )


if __name__ == "__main__":
    test_unsafe_dev_endpoints_default_off_when_env_absent()
    test_dev_auth_not_tracked_by_git()
    print("OK: test_phase1_security_defaults")
