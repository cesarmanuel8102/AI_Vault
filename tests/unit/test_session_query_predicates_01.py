"""Tests for session_query_predicates extracted from BrainSession.

Front: FRONT-B7-SESSION-STRANGLER-QUERY-DETECTORS-02A
Verifies extracted predicates produce correct results without BrainSession.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tmp_agent.brain_v9.core.session_query_predicates import (
    contains_raw_tool_markup,
    is_manual_confirmation_step,
    is_continue_sequence_message,
    is_confirmation,
    is_greeting_query,
    is_temporal_query,
    is_last_result_followup,
    LAST_RESULT_FOLLOWUP_PATTERNS,
)


def test_contains_raw_tool_markup_function_calls():
    assert contains_raw_tool_markup("<function_calls>") is True
    assert contains_raw_tool_markup("<invoke name='read_file'>") is True
    assert contains_raw_tool_markup("hello world") is False
    assert contains_raw_tool_markup("") is False
    assert contains_raw_tool_markup(None) is False


def test_is_manual_confirmation_step_yes():
    assert is_manual_confirmation_step("dale") is True
    assert is_manual_confirmation_step("confirmo") is True
    assert is_manual_confirmation_step("sigue") is True
    assert is_manual_confirmation_step("next") is True
    assert is_manual_confirmation_step("aprueba") is True


def test_is_manual_confirmation_step_no():
    assert is_manual_confirmation_step("hola") is False
    assert is_manual_confirmation_step("ejecuta el tool") is False
    assert is_manual_confirmation_step("") is False


def test_is_continue_sequence_message_yes():
    assert is_continue_sequence_message("continua") is True
    assert is_continue_sequence_message("sigue") is True
    assert is_continue_sequence_message("next") is True
    assert is_continue_sequence_message("dale") is True
    assert is_continue_sequence_message("adelante") is True


def test_is_continue_sequence_message_no():
    assert is_continue_sequence_message("hola") is False
    assert is_continue_sequence_message("ejecuta el tool") is False
    assert is_continue_sequence_message("") is False
    assert is_continue_sequence_message("continua con el analisis del brain") is False


def test_is_confirmation_yes():
    assert is_confirmation("si") is True
    assert is_confirmation("ok") is True
    assert is_confirmation("dale") is True
    assert is_confirmation("yes") is True


def test_is_confirmation_no():
    assert is_confirmation("hola") is False
    assert is_confirmation("no quiero") is False
    assert is_confirmation("este es un mensaje muy largo que no es confirmacion") is False


def test_is_greeting_query_yes():
    assert is_greeting_query("hola") is True
    assert is_greeting_query("hello") is True
    assert is_greeting_query("buenas") is True


def test_is_greeting_query_no():
    assert is_greeting_query("hola como estas") is False
    assert is_greeting_query("") is False


def test_is_temporal_query_yes():
    assert is_temporal_query("que has hecho hoy") is True
    assert is_temporal_query("ultimo estado del brain") is True
    assert is_temporal_query("status actual") is True


def test_is_temporal_query_no():
    assert is_temporal_query("hola") is False
    assert is_temporal_query("ejecuta el tool") is False


def test_module_does_not_import_session():
    import inspect
    import tmp_agent.brain_v9.core.session_query_predicates as mod
    src = inspect.getsource(mod)
    lines = [l for l in src.splitlines() if l.strip().startswith("import ") or l.strip().startswith("from ")]
    for line in lines:
        assert "brain_v9.core.session" not in line, f"session_query_predicates must NOT import session.py, found: {line.strip()}"


# --- is_last_result_followup tests ---

def test_last_result_followup_short_keyword_resultados():
    assert is_last_result_followup("resultados") is True


def test_last_result_followup_short_keyword_resumen():
    assert is_last_result_followup("resumen") is True


def test_last_result_followup_short_no_match():
    assert is_last_result_followup("hola") is False


def test_last_result_followup_empty():
    assert is_last_result_followup("") is False


def test_last_result_followup_long_no_match():
    assert is_last_result_followup("revisa los cambios del repo y listalos por importancia") is False


def test_last_result_followup_long_regex_match():
    assert is_last_result_followup("se realizaron cambios en session.py") is True


def test_last_result_followup_long_y_prefix_match():
    assert is_last_result_followup("y los resultados?") is True


def test_last_result_followup_custom_patterns():
    custom = (r"^custommatch$",)
    assert is_last_result_followup("custommatch", patterns=custom) is True
    assert is_last_result_followup("hola", patterns=custom) is False


def test_last_result_followup_parity_with_shim():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))
    try:
        from brain_v9.core.session import BrainSession
    finally:
        pass

    class FakeSession:
        _LAST_RESULT_FOLLOWUP_PATTERNS = BrainSession._LAST_RESULT_FOLLOWUP_PATTERNS
        _is_last_result_followup = BrainSession._is_last_result_followup

    fake = FakeSession()
    test_msgs = [
        "resultados",
        "resumen",
        "hola",
        "",
        "se realizaron cambios en session.py",
        "y los resultados?",
        "revisa los cambios del repo y listalos por importancia",
    ]
    for msg in test_msgs:
        shim_result = fake._is_last_result_followup(msg)
        direct_result = is_last_result_followup(msg, patterns=LAST_RESULT_FOLLOWUP_PATTERNS)
        assert shim_result == direct_result, f"parity mismatch for: {msg!r}"


def test_last_result_followup_class_attr_alias():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))
    try:
        from brain_v9.core.session import BrainSession
    finally:
        pass
    assert hasattr(BrainSession, "_LAST_RESULT_FOLLOWUP_PATTERNS")
    assert BrainSession._LAST_RESULT_FOLLOWUP_PATTERNS == LAST_RESULT_FOLLOWUP_PATTERNS


def test_last_result_followup_shim_is_thin():
    import ast
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "tmp_agent" / "brain_v9" / "core" / "session.py"
    txt = p.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(txt)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")
    methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    assert "_is_last_result_followup" in methods
    src = ast.get_source_segment(txt, methods["_is_last_result_followup"])
    assert "_qp.is_last_result_followup" in src
    assert "self._LAST_RESULT_FOLLOWUP_PATTERNS" in src

    forbidden = [
        "keywords = [",
        "for pat in self._LAST_RESULT_FOLLOWUP_PATTERNS",
        "msg_lower = message.lower",
    ]
    for token in forbidden:
        assert token not in src, f"forbidden token in _is_last_result_followup: {token}"


if __name__ == "__main__":
    tests = [
        test_contains_raw_tool_markup_function_calls,
        test_is_manual_confirmation_step_yes,
        test_is_manual_confirmation_step_no,
        test_is_continue_sequence_message_yes,
        test_is_continue_sequence_message_no,
        test_is_confirmation_yes,
        test_is_confirmation_no,
        test_is_greeting_query_yes,
        test_is_greeting_query_no,
        test_is_temporal_query_yes,
        test_is_temporal_query_no,
        test_module_does_not_import_session,
        test_last_result_followup_short_keyword_resultados,
        test_last_result_followup_short_keyword_resumen,
        test_last_result_followup_short_no_match,
        test_last_result_followup_empty,
        test_last_result_followup_long_no_match,
        test_last_result_followup_long_regex_match,
        test_last_result_followup_long_y_prefix_match,
        test_last_result_followup_custom_patterns,
        test_last_result_followup_parity_with_shim,
        test_last_result_followup_class_attr_alias,
        test_last_result_followup_shim_is_thin,
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