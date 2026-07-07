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