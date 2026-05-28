import re
import pathlib
import pytest
import sys

HTML = pathlib.Path("C:/AI_VAULT/tmp_agent/brain_v9/ui/index.html").read_text(encoding="utf-8")

def test_handleTool01PermissionAction_exists():
    assert "async function handleTool01PermissionAction(" in HTML

def test_calls_tool01_permission_approve():
    assert "api('/tool01/permission/approve'" in HTML

def test_sends_sessionId_permissionId_decision():
    assert "session_id: sessionId" in HTML
    assert "permission_id: permissionId" in HTML
    assert "decision: decision" in HTML

def test_has_finally_or_button_reset_in_catch():
    # Verificar que hay finally o que catch/finally restauran texto
    func_match = re.search(r'async function handleTool01PermissionAction\(.*?\{(.*?)\}\s*catch', HTML, re.DOTALL)
    assert func_match
    body = func_match.group(1)
    # Debe haber finally o catch manejando disabled + textContent
    assert ('finally' in body) or ('disabled = false' in body or 'btn.disabled = false' in HTML)

def test_renders_success_result():
    assert 'resultDiv.className' in HTML
    assert 'tool01-perm-result ok' in HTML

def test_renders_error_result():
    assert 'tool01-perm-result err' in HTML

def test_no_governance_gate_used_for_tool01():
    func = re.search(r'function handleTool01PermissionAction\(.*?\}\s*(?=function|</script>)', HTML, re.DOTALL)
    assert func
    assert '/gate/approve' not in func.group(0)
    assert 'governance_gate' not in func.group(0)

def test_no_raw_chain_of_thought():
    assert 'raw_chain_of_thought' not in HTML
