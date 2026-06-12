from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RUNBOOK = ROOT / "docs/KIMI_K2_6_CLOUD_PROVIDER_SETUP_RUNBOOK.md"
SETUP_SCRIPT = ROOT / "tools/setup_kimi_k2_6_provider_user_env.ps1"
VERIFY_SCRIPT = ROOT / "tools/verify_kimi_k2_6_provider_config.ps1"
LLM = ROOT / "tmp_agent/brain_v9/core/llm.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_runbook_exists_and_mentions_kimi_ollama_cloud() -> None:
    text = _read(RUNBOOK)
    assert "Kimi K2.6 cloud" in text
    assert "Ollama Cloud" in text
    assert "kimi-k2.6:cloud" in text


def test_runbook_mentions_provider_chain() -> None:
    text = _read(RUNBOOK)
    assert "Kimi K2.6 cloud" in text
    assert "Codex" in text
    assert "Local Ollama" in text or "local Ollama" in text


def test_setup_and_verify_scripts_exist() -> None:
    assert SETUP_SCRIPT.exists()
    assert VERIFY_SCRIPT.exists()


def test_scripts_do_not_contain_real_secret_patterns() -> None:
    combined = _read(SETUP_SCRIPT) + "\n" + _read(VERIFY_SCRIPT) + "\n" + _read(RUNBOOK)
    forbidden = ["s" + "k-", "Bearer " + "s" + "k-", "KIMI_API" + "_KEY=", "MOONSHOT_API" + "_KEY="]
    for marker in forbidden:
        assert marker not in combined


def test_scripts_do_not_write_env_files() -> None:
    combined = (_read(SETUP_SCRIPT) + "\n" + _read(VERIFY_SCRIPT)).lower()
    assert ".env" not in combined
    assert "set-content -path .env" not in combined
    assert "add-content .env" not in combined


def test_scripts_do_not_print_secret_values() -> None:
    combined = _read(SETUP_SCRIPT) + "\n" + _read(VERIFY_SCRIPT)
    assert "value_redacted" in combined
    assert "secrets_exposed = $false" in combined or "secrets_exposed = false" in combined
    assert "headers_printed" in combined


def test_verify_script_redacts_key_output() -> None:
    text = _read(VERIFY_SCRIPT)
    assert "KIMI_API_KEY" in text
    assert "MOONSHOT_API_KEY" in text
    assert "value_redacted" in text
    assert "Authorization" not in text


def test_llm_uses_kimi_ollama_cloud_provider_id() -> None:
    text = _read(LLM)
    assert "kimi_k2_6_cloud" in text
    assert "kimi-k2.6:cloud" in text
    assert "KIMI_OLLAMA_MODEL" in text
    assert "kimi_openai_compat" not in text
    assert "api.moonshot.ai" not in text


def test_roadmap_and_ledger_exist() -> None:
    assert json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    assert (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").exists()


def test_no_protected_paths_staged() -> None:
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True)
    protected = ("memory/semantic/", "trading/", "B8/", "tmp_agent/strategies/")
    assert not any(line.startswith(protected) for line in staged.splitlines())


def test_setup_script_status_mode_static_contract() -> None:
    text = _read(SETUP_SCRIPT)
    assert "Mode = \"Status\"" in text
    assert "KIMI_OLLAMA_MODEL" in text
    assert "RemoveUser" in text
    assert "Process" in text
    assert "User" in text


def test_verify_script_outputs_evidence_paths() -> None:
    text = _read(VERIFY_SCRIPT)
    assert "provider_config_verify.json" in text
    assert "provider_config_verify.md" in text
    assert "tmp_agent/front_kimi_k2_6_cloud_provider_config_runbook_01" in text
