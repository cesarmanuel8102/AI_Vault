import pytest


@pytest.mark.unit
def test_extract_openai_responses_text_from_output_text():
    from brain_v9.core.llm import LLMManager

    payload = {"output_text": "respuesta codex"}

    assert LLMManager._extract_openai_responses_text(payload) == "respuesta codex"


@pytest.mark.unit
def test_extract_openai_responses_text_from_output_content():
    from brain_v9.core.llm import LLMManager

    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "linea 1"},
                    {"type": "output_text", "text": "linea 2"},
                ]
            }
        ]
    }

    assert LLMManager._extract_openai_responses_text(payload) == "linea 1\nlinea 2"


@pytest.mark.unit
def test_session_normalizes_codex_aliases():
    from brain_v9.core.session import BrainSession

    assert BrainSession._normalize_model_priority("codex") == "codex"
    assert BrainSession._normalize_model_priority("openai") == "codex"
    assert BrainSession._normalize_model_priority("frontier_legacy") == "agent_frontier_legacy"


@pytest.mark.unit
def test_build_codex_cli_prompt_includes_conversation():
    from brain_v9.core.llm import LLMManager

    prompt = LLMManager._build_codex_cli_prompt(
        [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "respuesta previa"},
            {"role": "user", "content": "haz analisis"},
        ],
        {"available_tools": [{"name": "scan_local_network", "description": "scan"}]},
    )

    assert "[user]" in prompt
    assert "[assistant]" in prompt
    assert "scan_local_network" in prompt
    assert "haz analisis" in prompt


@pytest.mark.unit
def test_build_codex_cli_command_uses_output_file():
    from brain_v9.core.llm import LLMManager

    cmd = LLMManager._build_codex_cli_command(r"C:\tmp\out.txt", model="gpt-5.5")

    assert cmd[0] in {"codex", "powershell"}
    assert "--output-last-message" in cmd
    assert r"C:\tmp\out.txt" in cmd
    assert "-m" in cmd
    assert "gpt-5.5" in cmd
    assert cmd[-1] in {"-", "gpt-5.5"}


@pytest.mark.unit
def test_cap_num_predict_for_short_prompt():
    from brain_v9.core.llm import LLMManager

    messages = [
        {"role": "system", "content": "sistema"},
        {"role": "user", "content": "Responde solo OK"},
    ]

    capped = LLMManager._cap_num_predict_for_prompt(messages, estimated_input=120, default_num_predict=4096)

    assert capped == 256


@pytest.mark.unit
def test_prepare_chat_messages_does_not_duplicate_existing_system_prompt():
    from brain_v9.core.llm import LLMManager

    llm = LLMManager()
    messages = [
        {"role": "system", "content": "sistema compacto"},
        {"role": "user", "content": "hola"},
    ]

    prepared = llm._prepare_chat_messages(messages, tools_context=None)

    assert len([m for m in prepared if m["role"] == "system"]) == 1
    assert prepared[0]["content"] == "sistema compacto"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_query_respects_direct_model_key(monkeypatch):
    from brain_v9.core.llm import LLMManager

    llm = LLMManager()

    async def fake_has_internet():
        return True

    async def fake_query_model(cfg, messages, tools_context):
        assert cfg["model"] == "llama3.1:8b"
        return {"success": True, "content": "ok", "response": "ok", "model": cfg["model"]}

    monkeypatch.setattr(llm, "_has_internet", fake_has_internet)
    monkeypatch.setattr(llm, "_query_model", fake_query_model)

    result = await llm.query(
        [{"role": "user", "content": "hola"}],
        model_priority="llama8b",
        max_time=120,
    )

    assert result["success"] is True
    assert result["model_key"] == "llama8b"
    assert result["model"] == "llama3.1:8b"
