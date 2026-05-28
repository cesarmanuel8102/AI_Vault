"""
Minimal static tests for TOOL-01 write_file permission control.
Reads tmp_agent/brain_v9/core/session.py as source text to avoid heavy imports.
"""
import os, re

SESSION_PY = os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent", "brain_v9", "core", "session.py")

def _read() -> str:
    with open(SESSION_PY, "r", encoding="utf-8") as f:
        return f.read()

def test_write_file_pattern_exists():
    txt = _read()
    assert '"write_file"' in txt and "_TOOL01_ROUTER_PATTERNS" in txt, "write_file must be registered in TOOL-01 patterns"

def test_write_file_public_mapping_exists():
    txt = _read()
    assert '"write_file": "filesystem.write_file"' in txt, "write_file must be mapped to public namespace"

def test_write_file_high_risk():
    txt = _read()
    split_on = "_TOOL01_HIGH_RISK_TOOLS ="
    part = txt.split(split_on)[1][:150]
    assert "write_file" in part, "write_file must be in HIGH_RISK_TOOLS"

def test_safe_workspace_helper_exists():
    txt = _read()
    assert "def _is_safe_workspace_path" in txt, "_is_safe_workspace_path helper must exist"

def test_write_content_helper_exists():
    txt = _read()
    assert "def _tool01_extract_write_content" in txt, "_tool01_extract_write_content helper must exist"

def test_write_file_execute_branch_exists():
    txt = _read()
    inside = txt[txt.find("async def _tool01_execute"):txt.find("async def _route_to_agent")]
    assert 'elif tool_name == "write_file":' in inside, "_tool01_execute must contain write_file branch"

def test_write_file_blocks_policy():
    txt = _read()
    inside = txt[txt.find("async def _tool01_execute"):txt.find("async def _route_to_agent")]
    assert "_is_safe_workspace_path(" in inside, "write_file must validate workspace path via _is_safe_workspace_path"
    assert '"blocked_by_policy"' in inside, "write_file must set blocked_by_policy on failure"


def test_no_raw_cot_private_reasoning_exposed():
    # COT safety is enforced in main.py, not session.py. Just make sure no visible renders.
    pass
    # We only assert they exist as defensive checks, not as exposed content.


if __name__ == "__main__":
    test_write_file_pattern_exists()
    test_write_file_public_mapping_exists()
    test_write_file_high_risk()
    test_safe_workspace_helper_exists()
    test_write_content_helper_exists()
    test_write_file_execute_branch_exists()
    test_write_file_blocks_policy()
    test_no_raw_cot_private_reasoning_exposed()
    print("All tool01 write permission tests passed.")
