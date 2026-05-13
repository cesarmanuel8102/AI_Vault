import pytest


@pytest.mark.unit
def test_grounded_code_analysis_query_detects_file_inspection():
    from brain_v9.core.session import BrainSession

    msg = r"revisa C:\AI_VAULT\tmp_agent\brain_v9\core\session.py y explica la condicion exacta"
    assert BrainSession._is_grounded_code_analysis_query(msg) is True


@pytest.mark.unit
def test_extract_candidate_paths_resolves_repo_files():
    from brain_v9.core.session import BrainSession

    msg = r"lee C:\AI_VAULT\tmp_agent\brain_v9\core\llm.py y resume"
    paths = BrainSession._extract_candidate_paths(msg)
    assert paths
    assert str(paths[0]).lower().endswith(r"tmp_agent\brain_v9\core\llm.py")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_grounded_code_fastpath_uses_code_chain(monkeypatch):
    from brain_v9.core.session import BrainSession

    session = BrainSession("test_grounded_code_fastpath")

    async def fake_query(messages, model_priority="chat", max_time=None, tools_context=None):
        assert model_priority == "code"
        assert max_time == 180
        assert "EVIDENCIA:" in messages[0]["content"]
        return {
            "success": True,
            "content": "analisis grounded",
            "response": "analisis grounded",
            "model": "gpt-5.5",
            "model_used": "gpt-5.5",
            "model_key": "codex",
        }

    monkeypatch.setattr(session.llm, "query", fake_query)

    result = await session._maybe_grounded_code_analysis_fastpath(
        r"lee C:\AI_VAULT\tmp_agent\brain_v9\core\llm.py y resume el fallback"
    )
    await session.close()

    assert result is not None
    assert result["success"] is True
    assert result["model_used"] == "gpt-5.5"
    assert "analisis grounded" in result["content"]
