"""
FRONT-INFRA-02: Minimal .env.example creation — validation smoke test.

Checks:
1. .env.example exists at repo root
2. BRAIN_CHAT_DEV_MODE=false
3. BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS=false
4. No real secrets / tokens with non-placeholder values
5. Real-write flags are false
6. .env is in .gitignore (so real .env won't be committed)
7. Host/port documented
8. Secret regex does not cross newlines (line-by-line parse)
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

SECRET_KEYS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GITHUB_TOKEN",
    "FRED_API_KEY",
    "BRAIN_ADMIN_TOKEN",
    "BRAIN_APPROVAL_4D_DRY_GATE_TOKEN",
}

ALLOWED_SECRET_VALUES = {
    "",
    "CHANGE_ME_NOT_A_SECRET",
    "placeholder",
    "your_key_here",
    "sk-xxxxxxxx",
}

REAL_SECRET_RE = re.compile(
    r"^(sk-|ghp_|github_pat_|xoxb-|Bearer\s|token|secret|key|pwd|pass)",
    re.IGNORECASE,
)


def _parse_env_example() -> dict[str, str]:
    """Parse .env.example line-by-line; never cross newlines."""
    env: dict[str, str] = {}
    if not ENV_EXAMPLE_PATH.exists():
        return env
    for raw in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


class TestFrontInfra02EnvExample:
    """Smoke tests for FRONT-INFRA-02 .env.example."""

    def test_env_example_exists(self):
        assert ENV_EXAMPLE_PATH.exists(), f".env.example not found at {ENV_EXAMPLE_PATH}"

    def test_brain_chat_dev_mode_false(self):
        env = _parse_env_example()
        assert "BRAIN_CHAT_DEV_MODE" in env, "BRAIN_CHAT_DEV_MODE not found in .env.example"
        assert env["BRAIN_CHAT_DEV_MODE"].lower() == "false", (
            f"BRAIN_CHAT_DEV_MODE must be false, got {env['BRAIN_CHAT_DEV_MODE']}"
        )

    def test_brain_enable_unsafe_dev_endpoints_false(self):
        env = _parse_env_example()
        assert "BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS" in env, (
            "BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS not found in .env.example"
        )
        assert env["BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS"].lower() == "false", (
            f"BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS must be false, got {env['BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS']}"
        )

    def test_real_write_flags_false(self):
        """Any flag that activates trading or dangerous operations must be false."""
        env = _parse_env_example()
        real_write_vars = [
            "BRAIN_ENABLE_FINANCIAL_AUTOCYCLE",
            "BRAIN_START_AUTONOMY",
            "BRAIN_START_PROACTIVE",
            "BRAIN_START_SELF_DIAGNOSTIC",
            "BRAIN_START_QC_LIVE_MONITOR",
            "BRAIN_WARMUP_MODEL",
        ]
        for var in real_write_vars:
            if var in env:
                assert env[var].lower() == "false", (
                    f"{var} must be false in .env.example, got {env[var]}"
                )

    def test_no_real_secrets(self):
        """Ensure no API keys or tokens have real-looking values."""
        env = _parse_env_example()
        for key in SECRET_KEYS:
            if key not in env:
                continue
            value = env[key]
            if not value:
                continue  # empty is OK
            if value in ALLOWED_SECRET_VALUES:
                continue
            # Reject anything that looks like a real secret pattern
            if REAL_SECRET_RE.search(value):
                pytest.fail(f"Potential real secret found for {key}: {value[:10]}...")

    def test_empty_secret_values_are_allowed(self):
        """All secret keys must either be absent or have an empty/placeholder value."""
        env = _parse_env_example()
        for key in SECRET_KEYS:
            if key not in env:
                continue
            value = env[key]
            assert not value or value in ALLOWED_SECRET_VALUES, (
                f"{key} must be empty or a placeholder, got: {value}"
            )

    def test_secret_regex_does_not_cross_newlines(self):
        """Parser must handle line-by-line without multi-line leakage."""
        env = _parse_env_example()
        for key, value in env.items():
            assert "\n" not in value, (
                f"Value for {key} contains a newline — parser leaked across lines"
            )

    def test_paper_only_true(self):
        """Trading safety gate must be true by default."""
        env = _parse_env_example()
        assert "PAPER_ONLY" in env, "PAPER_ONLY not found in .env.example"
        assert env["PAPER_ONLY"].lower() == "true", (
            f"PAPER_ONLY must be true, got {env['PAPER_ONLY']}"
        )

    def test_host_port_documented(self):
        """Server binding must be documented."""
        env = _parse_env_example()
        assert "BRAIN_HOST" in env, "BRAIN_HOST not documented"
        assert "BRAIN_PORT" in env, "BRAIN_PORT not documented"
        assert re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", env["BRAIN_HOST"]), (
            f"BRAIN_HOST does not look like an IP: {env['BRAIN_HOST']}"
        )
        assert env["BRAIN_PORT"].isdigit(), (
            f"BRAIN_PORT must be numeric, got {env['BRAIN_PORT']}"
        )

    def test_env_in_gitignore(self):
        """Ensure .env is ignored so real secrets are never committed."""
        assert GITIGNORE_PATH.exists(), ".gitignore not found"
        gitignore = GITIGNORE_PATH.read_text(encoding="utf-8")
        # Must contain .env but NOT exclude .env.example
        assert re.search(r"^\.env\s*$", gitignore, re.MULTILINE), ".env not in .gitignore"
        # Ensure .env.example is not ignored
        assert not re.search(r"^\.env\.example\s*$", gitignore, re.MULTILINE), (
            ".env.example is incorrectly ignored"
        )
        # Check for the explicit un-ignore
        assert "!.env.example" in gitignore, (
            ".gitignore must contain '!.env.example' to allow the example file"
        )
