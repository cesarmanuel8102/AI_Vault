"""B7-STRANGLER-05 import-compat: BrainSession._sanitize_llm_chat_response shim integrity."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure tmp_agent is on sys.path (test runner default)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))


def test_module_import_and_callable():
    from brain_v9.core.session_response_hygiene import sanitize_llm_chat_response
    assert callable(sanitize_llm_chat_response)


def test_brain_session_class_attr_still_callable():
    from brain_v9.core.session import BrainSession
    assert callable(BrainSession._sanitize_llm_chat_response)


def test_brain_session_attr_is_extracted_function_identity():
    """Class-attribute access on a staticmethod descriptor returns the raw function.
    This is the contract main.py:1257 (instance-attr access) relies on."""
    from brain_v9.core.session import BrainSession
    from brain_v9.core import session_response_hygiene as srh
    assert BrainSession._sanitize_llm_chat_response is srh.sanitize_llm_chat_response


def test_brain_session_descriptor_is_staticmethod():
    """Verify the descriptor stored on the class is a staticmethod (not a bound method)."""
    from brain_v9.core.session import BrainSession
    raw = BrainSession.__dict__["_sanitize_llm_chat_response"]
    assert isinstance(raw, staticmethod), f"expected staticmethod, got {type(raw)!r}"


def test_instance_attr_call_pattern_works():
    """Mirror main.py:1257 usage: session._sanitize_llm_chat_response(content) on an instance."""
    from brain_v9.core.session import BrainSession
    inst = BrainSession.__new__(BrainSession)  # avoid __init__ side effects
    out = inst._sanitize_llm_chat_response("hola mundo")
    assert isinstance(out, str)
    assert "hola mundo" in out


def test_class_attr_call_pattern_works():
    from brain_v9.core.session import BrainSession
    out = BrainSession._sanitize_llm_chat_response("hola mundo")
    assert isinstance(out, str)
    assert "hola mundo" in out
