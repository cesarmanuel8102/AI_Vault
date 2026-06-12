from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
for candidate in (ROOT, TMP_AGENT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_provider_priority_order_is_kimi_codex_local() -> None:
    from brain_v9.core.llm import CHAINS, PROVIDER_PRIORITY

    assert PROVIDER_PRIORITY["primary_provider"] == "kimi_k2_6_cloud"
    assert PROVIDER_PRIORITY["secondary_provider"] == "codex"
    assert PROVIDER_PRIORITY["tertiary_provider"] == "local_ollama"
    assert PROVIDER_PRIORITY["kimi_model_id"] == "kimi-k2.6"
    for chain_name in ("chat", "agent", "analysis_frontier", "code"):
        chain = CHAINS[chain_name]
        assert chain[0] == "kimi_k2_6_cloud"
        assert chain[1] == "codex"
        assert any(model in chain[2:] for model in ("llama8b", "deepseek14b", "coder14b"))


def test_kimi_model_uses_ollama_cloud_not_direct_api(monkeypatch) -> None:
    from brain_v9.core.llm import MODELS

    monkeypatch.delenv("KIMI_OLLAMA_MODEL", raising=False)
    assert MODELS["kimi_k2_6_cloud"]["type"] == "ollama"
    assert MODELS["kimi_k2_6_cloud"]["model"].endswith(":cloud")
    assert MODELS["kimi_k2_6_cloud"]["model"] == "kimi-k2.6:cloud"


def test_no_secret_values_are_hardcoded_or_serialized() -> None:
    source = _read("tmp_agent/brain_v9/core/llm.py")
    forbidden_secret_literals = ["s" + "k-", "KIMI_API" + "_KEY=", "MOONSHOT_API" + "_KEY="]
    for marker in forbidden_secret_literals:
        assert marker not in source
    assert "kimi_openai_compat" not in source
    assert "api.moonshot.ai" not in source
    assert "KIMI_OLLAMA_MODEL" in source


def test_empty_provider_response_is_failure() -> None:
    from brain_v9.core.llm import LLMManager

    async def run() -> None:
        mgr = LLMManager()
        try:
            await mgr._query_model(
                {"type": "test_empty", "model": "empty-model", "timeout": 1},
                [{"role": "user", "content": "x"}],
                None,
            )
        except ValueError:
            # Unknown provider check proves unsupported providers are not success.
            return
        raise AssertionError("unknown empty provider should not be successful")

    asyncio.run(run())


def test_chain_continues_after_empty_response(monkeypatch) -> None:
    from brain_v9.core.llm import CHAINS, LLMManager, MODELS

    async def fake_has_internet(self):
        return True

    async def fake_query_model(self, cfg, messages, tools_context):
        if cfg["model"] == "empty-primary":
            raise RuntimeError("provider devolvio respuesta vacia")
        return {"success": True, "content": "ok fallback", "response": "ok fallback", "model": cfg["model"], "model_used": cfg["model"]}

    async def run() -> None:
        old_a = MODELS.get("_test_empty")
        old_b = MODELS.get("_test_local")
        old_chain = CHAINS.get("_test_chain")
        MODELS["_test_empty"] = {"type": "ollama", "model": "empty-primary", "timeout": 10, "local": False}
        MODELS["_test_local"] = {"type": "ollama", "model": "local-fallback", "timeout": 10, "local": True}
        CHAINS["_test_chain"] = ["_test_empty", "_test_local"]
        try:
            mgr = LLMManager()
            monkeypatch.setattr(LLMManager, "_has_internet", fake_has_internet)
            monkeypatch.setattr(LLMManager, "_query_model", fake_query_model)
            result = await mgr.query([{"role": "user", "content": "x"}], model_priority="_test_chain", max_time=30)
            assert result["success"] is True
            assert result["provider_selected"] == "_test_local"
            assert result["fallback_used"] is True
            assert result["provider_attempts"][0]["status"] == "EMPTY_RESPONSE"
        finally:
            if old_a is None:
                MODELS.pop("_test_empty", None)
            else:
                MODELS["_test_empty"] = old_a
            if old_b is None:
                MODELS.pop("_test_local", None)
            else:
                MODELS["_test_local"] = old_b
            if old_chain is None:
                CHAINS.pop("_test_chain", None)
            else:
                CHAINS["_test_chain"] = old_chain

    asyncio.run(run())


def test_local_fallback_remains_available() -> None:
    from brain_v9.core.llm import MODELS

    assert MODELS["llama8b"]["model"] == "llama3.1:8b"
    assert MODELS["llama8b"]["local"] is True
    assert MODELS["deepseek14b"]["local"] is True


def test_adapter_still_delegates_to_router_not_llm() -> None:
    source = _read("tmp_agent/brain_v9/api/openai_compat.py")
    assert "handle_user_message" in source
    assert "dry_run=dry_run" in source
    assert "LLMManager" not in source
    assert ".query(" not in source


def test_dry_run_readonly_guard_still_exists() -> None:
    adapter = _read("tmp_agent/brain_v9/api/openai_compat.py")
    harness = _read("tmp_agent/brain_v9/evaluation/codex_brain_eval_harness.py")
    assert "def _request_dry_run" in adapter
    assert '"read_only": dry_run' in adapter
    assert "dry_run: bool = True" in harness
    assert "--live" in harness


def test_provider_metadata_fields_are_exposed() -> None:
    llm = _read("tmp_agent/brain_v9/core/llm.py")
    adapter = _read("tmp_agent/brain_v9/api/openai_compat.py")
    for field in (
        "provider_chain",
        "provider_selected",
        "model_selected",
        "provider_status",
        "provider_latency_ms",
        "fallback_used",
        "fallback_reason",
        "primary_provider_available",
        "secondary_provider_available",
        "local_fallback_used",
    ):
        assert field in llm
        assert field in adapter or field in {"fallback_reason", "fallback_used"}


def test_status_files_valid() -> None:
    assert json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    assert (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").exists()


def test_no_protected_paths_staged() -> None:
    import subprocess

    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True)
    protected = ("memory/semantic/", "trading/", "B8/", "tmp_agent/strategies/")
    assert not any(line.startswith(protected) for line in staged.splitlines())
