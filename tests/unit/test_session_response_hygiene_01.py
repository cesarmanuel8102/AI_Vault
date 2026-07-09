"""Tests for session_response_hygiene extracted helpers.

Front: FRONT-B7-SESSION-STRANGLER-RESPONSE-HYGIENE-04B
Verifies sanitize_memory_content and extract_numbered_sequence
produce correct results without requiring BrainSession.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tmp_agent.brain_v9.core.session_response_hygiene import (
    sanitize_memory_content,
    extract_numbered_sequence,
    sanitize_llm_chat_response_with_metadata,
    agent_failure_notice,
)


# --- sanitize_memory_content tests ---

def test_sanitize_removes_agent_orav_lines():
    text = "*[Agente ORAV iniciando escaneo]\nLinea buena\nOtra linea"
    result = sanitize_memory_content(text)
    assert "*[Agente ORAV" not in result
    assert "Linea buena" in result
    assert "Otra linea" in result


def test_sanitize_removes_dev_markers():
    text = "--- [DEV] algo ---\nLinea buena"
    result = sanitize_memory_content(text)
    assert "[DEV]" not in result
    assert "Linea buena" in result


def test_sanitize_removes_function_calls_markup():
    text = "<function_calls>\n<invoke name='read'>\ncontenido\n</invoke>\n</function_calls>\nLinea buena"
    result = sanitize_memory_content(text)
    assert "<function_calls" not in result
    assert "</function_calls>" not in result
    assert "<invoke " not in result
    assert "</invoke>" not in result
    assert "Linea buena" in result


def test_sanitize_removes_extractive_summary_markers():
    text = "*[Resumen extractivo de la sesion]\nLinea buena"
    result = sanitize_memory_content(text)
    assert "*[Resumen extractivo" not in result
    assert "Linea buena" in result


def test_sanitize_removes_internal_state_prefix():
    text = "(estado interno: revisando metricas)\nLinea buena"
    result = sanitize_memory_content(text)
    assert "(estado interno:" not in result
    assert "Linea buena" in result


def test_sanitize_preserves_clean_text():
    text = "Linea 1\nLinea 2\nLinea 3"
    result = sanitize_memory_content(text)
    assert result == "Linea 1\nLinea 2\nLinea 3"


def test_sanitize_empty_returns_empty():
    assert sanitize_memory_content("") == ""
    assert sanitize_memory_content(None) is None


def test_sanitize_strips_trailing_whitespace():
    text = "Linea buena\n\n\n"
    result = sanitize_memory_content(text)
    assert result == "Linea buena"


def test_sanitize_memory_content_parity_with_shim():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))
    try:
        from brain_v9.core.session import BrainSession
    finally:
        pass
    test_inputs = [
        "*[Agente ORAV test]\nClean line",
        "<function_calls>stuff</function_calls>\nClean",
        "Just clean text",
        "",
    ]
    for text in test_inputs:
        assert BrainSession._sanitize_memory_content(text) == sanitize_memory_content(text)


# --- extract_numbered_sequence tests ---

def test_extract_numbered_list_simple():
    result = extract_numbered_sequence("1. uno\n2. dos\n3. tres")
    assert result == ["uno", "dos", "tres"]


def test_extract_numbered_list_with_spaces():
    result = extract_numbered_sequence("1.   paso uno\n2.   paso dos")
    assert result is not None
    assert len(result) == 2
    assert "paso uno" in result[0]


def test_extract_inline_numbered_list():
    result = extract_numbered_sequence("1. first 2. second 3. third")
    assert result == ["first", "second", "third"]


def test_extract_no_numbered_returns_none():
    result = extract_numbered_sequence("This is just text without numbers")
    assert result is None


def test_extract_empty_returns_none():
    assert extract_numbered_sequence("") is None


def test_extract_bullet_list_fallback():
    result = extract_numbered_sequence("- item one\n- item two\n- item three")
    assert result is not None
    assert len(result) == 3
    assert "item one" in result[0]


def test_extract_star_bullet_list_fallback():
    result = extract_numbered_sequence("* item one\n* item two")
    assert result is not None
    assert len(result) == 2
    assert "item one" in result[0]


def test_extract_numbered_sequence_parity_with_shim():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))
    try:
        from brain_v9.core.session import BrainSession
    finally:
        pass
    test_inputs = [
        "1. uno\n2. dos\n3. tres",
        "1. first 2. second",
        "No numbered list here",
        "",
        "- bullet one\n- bullet two",
    ]
    for text in test_inputs:
        assert BrainSession._extract_numbered_sequence(text) == extract_numbered_sequence(text)


# --- module import safety ---

def test_module_does_not_import_session():
    import inspect
    import tmp_agent.brain_v9.core.session_response_hygiene as mod
    src = inspect.getsource(mod)
    lines = [l for l in src.splitlines() if l.strip().startswith("import ") or l.strip().startswith("from ")]
    for line in lines:
        assert "brain_v9.core.session" not in line, f"session_response_hygiene must NOT import session.py, found: {line.strip()}"


# --- sanitize_llm_chat_response_with_metadata tests ---

def test_sanitize_metadata_clean_text():
    text = "This is a clean response."
    sanitized, meta = sanitize_llm_chat_response_with_metadata(text)
    assert "clean response" in sanitized
    assert meta["thinking_stripped"] is False
    assert meta["no_cot_leak"] is True


def test_sanitize_metadata_empty_text():
    sanitized, meta = sanitize_llm_chat_response_with_metadata("")
    assert meta["thinking_stripped"] is False
    assert meta["no_cot_leak"] is True


def test_sanitize_metadata_thinking_tag_stripped():
    text = "thinking... some reasoning ... done thinking. Final answer here."
    sanitized, meta = sanitize_llm_chat_response_with_metadata(text)
    assert meta["thinking_stripped"] is True


def test_sanitize_metadata_cot_marker_detected():
    text = "chain-of-thought: let me think about this"
    sanitized, meta = sanitize_llm_chat_response_with_metadata(text)
    assert meta["no_cot_leak"] is True
    assert "hidden reasoning" in sanitized


def test_sanitize_metadata_parity_with_shim():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))
    try:
        from brain_v9.core.session import BrainSession
    finally:
        pass
    test_inputs = [
        "Clean text response",
        "",
        "thinking... reasoning ... done thinking. Answer.",
    ]
    for text in test_inputs:
        shim_result = BrainSession._sanitize_llm_chat_response_with_metadata(text)
        direct_result = sanitize_llm_chat_response_with_metadata(text)
        assert shim_result == direct_result


# --- agent_failure_notice tests ---

def test_agent_failure_notice_timeout():
    result = agent_failure_notice("timeout")
    assert "timeout" in result
    assert "agent_status=timeout" in result
    assert "LLM" in result


def test_agent_failure_notice_ghost_completion():
    result = agent_failure_notice("ghost_completion")
    assert "ghost_completion" in result
    assert "agent_status=ghost_completion" in result


def test_agent_failure_notice_arbitrary_status():
    result = agent_failure_notice("some_error")
    assert "some_error" in result
    assert "agent_status=some_error" in result


def test_agent_failure_notice_parity_with_shim():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))
    try:
        from brain_v9.core.session import BrainSession
    finally:
        pass
    for status in ("timeout", "ghost_completion", "error"):
        shim_result = BrainSession._agent_failure_notice(object(), status)
        direct_result = agent_failure_notice(status)
        assert shim_result == direct_result


def test_brain_session_methods_are_thin_shims():
    """Structural test: verify BrainSession shims are thin delegates, not old code."""
    import ast
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "tmp_agent" / "brain_v9" / "core" / "session.py"
    txt = p.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(txt)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")

    methods = {
        n.name: n
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "_sanitize_memory_content" in methods
    assert "_extract_numbered_sequence" in methods

    sanitize_src = ast.get_source_segment(txt, methods["_sanitize_memory_content"])
    extract_src = ast.get_source_segment(txt, methods["_extract_numbered_sequence"])

    assert "_response_hygiene.sanitize_memory_content(text)" in sanitize_src
    assert "_response_hygiene.extract_numbered_sequence(message)" in extract_src

    forbidden_sanitize = [
        "for line in str(text).splitlines()",
        "stripped.startswith",
        "function_calls",
        "Agente ORAV",
        "estado interno",
    ]
    for token in forbidden_sanitize:
        assert token not in sanitize_src, f"forbidden token in _sanitize_memory_content: {token}"

    forbidden_extract = [
        "marker_re = re.compile",
        "markers = list",
        "for line in message.splitlines()",
        "re.match",
    ]
    for token in forbidden_extract:
        assert token not in extract_src, f"forbidden token in _extract_numbered_sequence: {token}"


def test_agent_result_normalizer_methods_are_thin_shims():
    """Structural test: verify new B7-STRANGLER-05B shims are thin delegates."""
    import ast
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "tmp_agent" / "brain_v9" / "core" / "session.py"
    txt = p.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(txt)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")

    methods = {
        n.name: n
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "_sanitize_llm_chat_response_with_metadata" in methods
    assert "_agent_failure_notice" in methods

    metadata_src = ast.get_source_segment(txt, methods["_sanitize_llm_chat_response_with_metadata"])
    notice_src = ast.get_source_segment(txt, methods["_agent_failure_notice"])

    assert "_response_hygiene.sanitize_llm_chat_response_with_metadata(content)" in metadata_src
    assert "_response_hygiene.agent_failure_notice(status)" in notice_src

    forbidden_metadata = [
        "cleaned = content",
        "thinking_stripped = False",
        "patterns = (",
        "raw_markers = re.compile",
    ]
    for token in forbidden_metadata:
        assert token not in metadata_src, f"forbidden token in _sanitize_llm_chat_response_with_metadata: {token}"

    forbidden_notice = [
        "No pude ejecutar herramientas",
        "Respondo con el modelo",
    ]
    for token in forbidden_notice:
        assert token not in notice_src, f"forbidden token in _agent_failure_notice: {token}"

    assert "def _agent_failure_notice(self" in notice_src, "must preserve self signature"


if __name__ == "__main__":
    tests = [
        test_sanitize_removes_agent_orav_lines,
        test_sanitize_removes_dev_markers,
        test_sanitize_removes_function_calls_markup,
        test_sanitize_removes_extractive_summary_markers,
        test_sanitize_removes_internal_state_prefix,
        test_sanitize_preserves_clean_text,
        test_sanitize_empty_returns_empty,
        test_sanitize_strips_trailing_whitespace,
        test_sanitize_memory_content_parity_with_shim,
        test_extract_numbered_list_simple,
        test_extract_numbered_list_with_spaces,
        test_extract_inline_numbered_list,
        test_extract_no_numbered_returns_none,
        test_extract_empty_returns_none,
        test_extract_bullet_list_fallback,
        test_extract_star_bullet_list_fallback,
        test_extract_numbered_sequence_parity_with_shim,
        test_module_does_not_import_session,
        test_sanitize_metadata_clean_text,
        test_sanitize_metadata_empty_text,
        test_sanitize_metadata_thinking_tag_stripped,
        test_sanitize_metadata_cot_marker_detected,
        test_sanitize_metadata_parity_with_shim,
        test_agent_failure_notice_timeout,
        test_agent_failure_notice_ghost_completion,
        test_agent_failure_notice_arbitrary_status,
        test_agent_failure_notice_parity_with_shim,
        test_brain_session_methods_are_thin_shims,
        test_agent_result_normalizer_methods_are_thin_shims,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")