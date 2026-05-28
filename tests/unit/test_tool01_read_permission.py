"""
Unit tests para TOOL-01 read_file permission-gated.
FASE 5
"""
import pytest, re, sys, os
from pathlib import Path
sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))

from brain_v9.core.session import BrainSession

BASE_PATH = Path("C:/AI_VAULT")


@pytest.fixture
def session():
    s = BrainSession(session_id="test_read")
    return s


def test_read_file_pattern_exists(session):
    patterns = session._TOOL01_ROUTER_PATTERNS.get("read_file", [])
    assert any(re.search(p, "read file", re.IGNORECASE) for p in patterns)


def test_read_file_approval_preserves_original_message(session):
    msg = "read file C:\\AI_VAULT\\tmp_agent\\workspace\\test.txt"
    perm = session._tool01_request_permission("read_file", "test reason", original_message=msg)
    assert perm["original_message"] == msg


def test_read_file_extract_path(session):
    msg = "read file C:\\AI_VAULT\\tmp_agent\\workspace\\vtc_permission_test_chat_ui.txt"
    path = session._tool01_extract_path(msg, "tmp_agent/brain_v9/core/llm.py", require_file=True)
    assert "vtc_permission_test_chat_ui.txt" in path


def test_read_file_execute_branch_returns_success_or_error(session):
    # Con grant allow_session, read_file ejecutará
    session._tool01_permission_grants["read_file"] = {"granted": True, "grant_type": "allow_session"}
    import asyncio
    result = asyncio.run(session._tool01_execute("read_file", "read file tmp_agent/brain_v9/core/llm.py"))
    # Debe devolver success=True con contenido, o success=False con error explícito
    assert result.get("success") is not None
    if result["success"]:
        assert result.get("content") is not None or result.get("preview") is not None
    else:
        assert result.get("error") is not None


def test_read_file_result_includes_path_preview_or_content(session):
    session._tool01_permission_grants["read_file"] = {"granted": True, "grant_type": "allow_session"}
    import asyncio
    result = asyncio.run(session._tool01_execute("read_file", "read file tmp_agent/brain_v9/core/llm.py"))
    if result.get("success"):
        assert result.get("path") is not None
        assert result.get("content") is not None or result.get("preview") is not None


def test_no_silent_success_false_error_null(session):
    session._tool01_permission_grants["read_file"] = {"granted": True, "grant_type": "allow_session"}
    import asyncio
    result = asyncio.run(session._tool01_execute("read_file", "read file tmp_agent/brain_v9/core/llm.py"))
    if not result.get("success"):
        assert result.get("error") is not None
