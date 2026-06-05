"""Smoke/static checks for explicit curated read-only chat command."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
SESSION_PY = ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py"

if str(TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain_v9.core.session import BrainSession  # noqa: E402


def _session_text() -> str:
    return SESSION_PY.read_text(encoding="utf-8")


def _method_block(name: str) -> str:
    text = _session_text()
    marker = f"    def {name}("
    start = text.find(marker)
    assert start >= 0, f"{name} not found"
    next_method = text.find("\n    def ", start + len(marker))
    next_async = text.find("\n    async def ", start + len(marker))
    candidates = [pos for pos in (next_method, next_async) if pos != -1]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


def _chat_prefix_before_tool01() -> str:
    text = _session_text()
    start = text.find("async def chat")
    route = text.find("curated_lookup_readonly", start)
    tool01 = text.find("await self._tool01_router", start)
    assert start >= 0 and route >= 0 and tool01 >= 0
    assert route < tool01
    return text[route:tool01]


def _bare_session() -> BrainSession:
    return BrainSession.__new__(BrainSession)


def test_session_contains_curated_parser():
    assert "def _parse_curated_lookup_command" in _session_text()


def test_supported_triggers_parse_query():
    session = _bare_session()
    cases = {
        "busca en conocimiento curado: phase0 security": "phase0 security",
        "qué aprendiste sobre promotion gate": "promotion gate",
        "que aprendiste sobre runtime lookup": "runtime lookup",
        "usa curated knowledge para responder endpoint readonly": "endpoint readonly",
        "usa conocimiento curado para responder semantic memory": "semantic memory",
    }
    for message, expected in cases.items():
        parsed = session._parse_curated_lookup_command(message)
        assert parsed is not None
        assert parsed["query"] == expected
        assert parsed["top_k"] == 5


def test_normal_commands_not_captured_by_curated_parser():
    session = _bare_session()
    for message in ("continua", "resultados", "ejecuta git status", "/status", "hola brain"):
        assert session._parse_curated_lookup_command(message) is None


def test_curated_route_exists():
    assert '"route": "curated_lookup_readonly"' in _session_text()


def test_visible_response_label_present():
    session = _bare_session()
    response = session._format_curated_lookup_chat_response("x", None)
    assert response.startswith("[verified_curated_readonly]")
    assert "Esto es conocimiento curado read-only. No está promovido a memoria real." in response


def test_empty_query_controlled_error():
    session = _bare_session()
    result = session._run_curated_lookup_command("   ")
    assert result["route"] == "curated_lookup_readonly"
    assert result["success"] is False
    assert result["metadata"]["label"] == "verified_curated_readonly"
    assert "query_required" in result["metadata"]["warnings"]
    assert "Consulta vacía" in result["content"]


def test_no_llm_fallback_in_curated_route():
    block = _chat_prefix_before_tool01()
    forbidden = ("_route_to_llm", "_route_to_agent", "self.llm.query", "session.chat")
    assert not any(term in block for term in forbidden)
    runner = _method_block("_run_curated_lookup_command")
    assert "llm_fallback_used" in runner
    assert '"llm_fallback_used": False' in runner


def test_no_writes_to_memory_or_semantic_in_curated_helpers():
    combined = (
        _method_block("_run_curated_lookup_command")
        + _method_block("_format_curated_lookup_chat_response")
        + _chat_prefix_before_tool01()
    )
    forbidden_patterns = (
        r"_save_turn",
        r"write_text",
        r"open\(.+['\"]w",
        r"ingest_text",
        r"semantic_memory_adapter_real",
        r"semantic_memory_bridge",
        r"memory/semantic",
    )
    assert not any(re.search(pattern, combined) for pattern in forbidden_patterns)


def test_no_faiss_writes_in_curated_helpers():
    combined = _method_block("_run_curated_lookup_command") + _chat_prefix_before_tool01()
    forbidden = ("SemanticMemoryFAISS", "faiss.write", "write_index", "ingest_text")
    assert not any(term in combined for term in forbidden)
    assert '"faiss_write_allowed": False' in _method_block("_run_curated_lookup_command")


def test_integration_point_before_tool01_and_llm():
    text = _session_text()
    chat_start = text.find("async def chat")
    curated = text.find("curated_lookup_command = self._parse_curated_lookup_command", chat_start)
    tool01 = text.find("await self._tool01_router", chat_start)
    llm_route = text.find("await self._route_to_llm", chat_start)
    assert chat_start >= 0 and curated >= 0 and tool01 >= 0 and llm_route >= 0
    assert curated < tool01 < llm_route


def test_formatter_includes_source_evidence_and_scores_terms():
    block = _method_block("_format_curated_lookup_chat_response")
    for term in ("source_id", "evidence_refs", "validation_score", "curation_score", "trust_score"):
        assert term in block


def test_no_automatic_context_injection_flag():
    runner = _method_block("_run_curated_lookup_command")
    assert "automatic_context_injection" in runner
    assert '"automatic_context_injection": False' in runner


def test_no_chain_of_thought_exposure_in_formatter():
    formatter = _method_block("_format_curated_lookup_chat_response")
    forbidden = ("chain-of-thought", "razonamiento interno", "analysis")
    assert not any(term in formatter.lower() for term in forbidden)
