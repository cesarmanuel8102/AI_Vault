"""
Cloud-First Model Policy Tests (BOR-4A)

Validar que las cadenas LLM priorizan modelos cloud rápidos
sobre modelos Ollama locales en el camino crítico.

No requiere runtime: usa parsing estático de CHAINS en llm.py.
"""

import ast
from pathlib import Path
import pytest

LLM_PY = Path(__file__).resolve().parents[2] / "tmp_agent" / "brain_v9" / "core" / "llm.py"


def _parse_chains() -> dict:
    """Extraer diccionario CHAINS de llm.py via AST."""
    assert LLM_PY.exists(), f"llm.py no encontrado en {LLM_PY}"
    src = LLM_PY.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CHAINS":
                    return ast.literal_eval(node.value)
    pytest.fail("No se encontró CHAINS en llm.py")


@pytest.fixture(scope="module")
def chains():
    return _parse_chains()


class TestCloudFirstPolicy:
    """Verificar que Ollama local NO bloquea el camino crítico."""

    def test_chat_chain_starts_with_cloud(self, chains):
        """chat debe empezar con cloud (kimi_cloud o codex), NO deepseek14b/llama8b."""
        chat = chains.get("chat", [])
        assert len(chat) >= 2, "chat chain muy corta"
        assert chat[0] in ("kimi_cloud", "codex"), \
            f"chat[0]={chat[0]!r} debe ser cloud primero"
        assert chat[1] in ("kimi_cloud", "codex", "gpt4", "claude"), \
            f"chat[1]={chat[1]!r} debe ser cloud o calidad"

    def test_code_chain_starts_with_cloud_or_codex(self, chains):
        """code debe empezar con codex o cloud, NO deepseek14b/llama8b."""
        code = chains.get("code", [])
        assert len(code) >= 2
        assert code[0] in ("codex", "coder14b"), \
            f"code[0]={code[0]!r} debe ser codex/coder primero"
        assert code[1] in ("codex", "coder14b", "kimi_cloud"), \
            f"code[1]={code[1]!r} no debe ser local puro"

    def test_agent_chain_prefers_cloud(self, chains):
        """agent debe preferir cloud antes que local."""
        agent = chains.get("agent", [])
        assert len(agent) >= 2
        assert agent[0] in ("kimi_cloud", "codex", "gpt4", "claude"), \
            f"agent[0]={agent[0]!r} debe ser cloud"

    def test_agent_frontier_prefers_cloud(self, chains):
        """agent_frontier debe empezar con cloud."""
        af = chains.get("agent_frontier", [])
        assert len(af) >= 2
        assert af[0] in ("kimi_cloud", "codex", "gpt4", "claude"), \
            f"agent_frontier[0]={af[0]!r} debe ser cloud"

    def test_analysis_frontier_prefers_codex_or_cloud(self, chains):
        """analysis_frontier debe empezar con codex o cloud."""
        an = chains.get("analysis_frontier", [])
        assert len(an) >= 2
        assert an[0] in ("codex", "kimi_cloud", "gpt4", "claude"), \
            f"analysis_frontier[0]={an[0]!r} debe ser codex/cloud"

    def test_offline_chain_is_local_only(self, chains):
        """offline debe contener solo modelos locales (deepseek14b, llama8b, coder14b)."""
        off = chains.get("offline", [])
        assert len(off) >= 1
        all_local = {"deepseek14b", "llama8b", "coder14b"}
        for m in off:
            assert m in all_local, \
                f"offline contiene modelo no-local {m!r}"

    def test_ollama_chain_not_blocked_by_local(self, chains):
        """ollama (legacy explicito) NO debe empezar con local."""
        oll = chains.get("ollama", [])
        assert len(oll) >= 2
        assert oll[0] in ("kimi_cloud", "codex", "gpt4", "claude"), \
            f"ollama[0]={oll[0]!r} debe ser cloud primero"

    def test_local_models_not_removed(self, chains):
        """deepseek14b y llama8b deben seguir existiendo en CHAINS."""
        all_models = set()
        for c in chains.values():
            all_models.update(c)
        assert "deepseek14b" in all_models, "deepseek14b removido de CHAINS"
        assert "llama8b" in all_models, "llama8b removido de CHAINS"
        assert "coder14b" in all_models, "coder14b removido de CHAINS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
