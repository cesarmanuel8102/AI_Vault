"""Tests for is_agent_execution_failure extracted from BrainSession.

Front: FRONT-B7-SESSION-STRANGLER-OBSERVABILITY-DETECTORS-03A
Verifies the extracted failure detector produces correct results
without requiring BrainSession.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tmp_agent.brain_v9.core.session_agent_render import is_agent_execution_failure


def test_non_dict_input():
    assert is_agent_execution_failure(None) is False
    assert is_agent_execution_failure("string") is False
    assert is_agent_execution_failure(42) is False
    assert is_agent_execution_failure([]) is False


def test_ghost_completion():
    assert is_agent_execution_failure({"status": "ghost_completion", "success": False}) is True


def test_timeout():
    assert is_agent_execution_failure({"status": "timeout", "success": False}) is True


def test_max_steps_reached():
    assert is_agent_execution_failure({"status": "max_steps_reached", "success": False}) is True


def test_llm_pool_unavailable():
    assert is_agent_execution_failure({"status": "llm_pool_unavailable", "success": False}) is True


def test_retry_exhausted():
    assert is_agent_execution_failure({"status": "retry_exhausted", "success": False}) is True


def test_success_false_failed_status():
    assert is_agent_execution_failure({"status": "failed", "success": False}) is False


def test_success_false_ok_status():
    assert is_agent_execution_failure({"status": "ok", "success": False}) is False


def test_success_true_ok_status():
    assert is_agent_execution_failure({"status": "ok", "success": True}) is False


def test_empty_dict():
    assert is_agent_execution_failure({}) is False


def test_success_absent_defaults_true():
    assert is_agent_execution_failure({"status": "timeout"}) is False


def test_status_absent():
    assert is_agent_execution_failure({"success": False}) is False


def test_status_case_insensitive():
    assert is_agent_execution_failure({"status": "Timeout", "success": False}) is True
    assert is_agent_execution_failure({"status": "GHOST_COMPLETION", "success": False}) is True


def test_module_does_not_import_session():
    import inspect
    import tmp_agent.brain_v9.core.session_agent_render as mod
    src = inspect.getsource(mod)
    lines = [l for l in src.splitlines() if l.strip().startswith("import ") or l.strip().startswith("from ")]
    for line in lines:
        assert "brain_v9.core.session" not in line, f"session_agent_render must NOT import session.py, found: {line.strip()}"


if __name__ == "__main__":
    tests = [
        test_non_dict_input,
        test_ghost_completion,
        test_timeout,
        test_max_steps_reached,
        test_llm_pool_unavailable,
        test_retry_exhausted,
        test_success_false_failed_status,
        test_success_false_ok_status,
        test_success_true_ok_status,
        test_empty_dict,
        test_success_absent_defaults_true,
        test_status_absent,
        test_status_case_insensitive,
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