import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
if str(TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_kimi_k2_6_is_target_cloud_model() -> None:
    llm = _read("tmp_agent/brain_v9/core/llm.py")
    assert "kimi_k2_6_cloud" in llm
    assert "KIMI_OLLAMA_MODEL" in llm
    assert "kimi-k2.6:cloud" in llm


def test_provider_probe_mode_is_not_diagnostic_dry_run() -> None:
    adapter = _read("tmp_agent/brain_v9/api/openai_compat.py")
    router = _read("tmp_agent/brain_v9/core/router_entrypoint.py")
    assert "provider_probe" in adapter
    assert 'if metadata.get("provider_probe")' in adapter
    assert 'return bool(payload.dry_run or metadata.get("dry_run"))' in adapter
    assert 'return "provider_probe"' in router
    assert "diagnostic_dry_run" in router


def test_adapter_still_delegates_and_does_not_directly_call_llmmanager() -> None:
    adapter = _read("tmp_agent/brain_v9/api/openai_compat.py")
    assert "from brain_v9.core.router_entrypoint import handle_user_message" in adapter
    assert "await handle_user_message(" in adapter
    assert "LLMManager(" not in adapter
    assert ".llm.query(" not in adapter


def test_provider_probe_blocks_side_effects_by_contract() -> None:
    session = _read("tmp_agent/brain_v9/core/session.py")
    router = _read("tmp_agent/brain_v9/core/router_entrypoint.py")
    for token in (
        "tools_blocked",
        "memory_writes_blocked",
        "faiss_writes_blocked",
        "external_side_effects_blocked",
        "save_turn_skipped",
    ):
        assert token in session
        assert token in router
    provider_probe_block = session[session.index("async def provider_probe") : session.index("async def chat")]
    assert "_save_turn" not in provider_probe_block
    assert "tools_context=None" in provider_probe_block


def test_anti_thinking_sanitizer_removes_thinking_block_and_preserves_final_answer() -> None:
    from tmp_agent.brain_v9.core.session import BrainSession

    content = "Thinking...\nprivate steps\n...done thinking.\nOK"
    sanitized, metadata = BrainSession._sanitize_llm_chat_response_with_metadata(content)
    assert sanitized == "OK"
    assert metadata["thinking_stripped"] is True
    assert metadata["no_cot_leak"] is True
    assert "Thinking" not in sanitized
    assert "done thinking" not in sanitized


def test_anti_thinking_sanitizer_removes_xml_think_blocks() -> None:
    from tmp_agent.brain_v9.core.session import BrainSession

    sanitized, metadata = BrainSession._sanitize_llm_chat_response_with_metadata("<think>secret</think>\nOK")
    assert sanitized == "OK"
    assert metadata["thinking_stripped"] is True
    assert metadata["no_cot_leak"] is True
    assert "<think>" not in sanitized


def test_no_raw_cot_terms_after_filtering() -> None:
    from tmp_agent.brain_v9.core.session import BrainSession

    sanitized, metadata = BrainSession._sanitize_llm_chat_response_with_metadata("scratchpad: hidden\nchain-of-thought: private")
    assert metadata["no_cot_leak"] is True
    for token in ("scratchpad", "chain-of-thought", "private reasoning", "<thinking>", "<think>"):
        assert token not in sanitized.lower()


def test_provider_metadata_includes_provider_selected_and_model_selected() -> None:
    adapter = _read("tmp_agent/brain_v9/api/openai_compat.py")
    router = _read("tmp_agent/brain_v9/core/router_entrypoint.py")
    for token in ("provider_selected", "model_selected", "provider_status", "provider_latency_ms"):
        assert token in adapter
        assert token in router


def test_aiohttp_session_cleanup_is_implemented_for_provider_probe() -> None:
    session = _read("tmp_agent/brain_v9/core/session.py")
    llm = _read("tmp_agent/brain_v9/core/llm.py")
    assert "async def close(self)" in llm
    assert "await self.llm.close()" in session
    assert "aiohttp_session_closed_after_probe" in session


def test_roadmap_and_ledger_exist_and_valid() -> None:
    json.loads(_read("ROADMAP_STATUS.json"))
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()


def test_no_protected_paths_staged() -> None:
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True)
    protected = ("memory/semantic/", "trading/", "B8/", "tmp_agent/strategies/")
    assert not any(line.startswith(protected) for line in staged.splitlines())
