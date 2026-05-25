"""
R1-A1b: Security Integration Tests for Strictly Protected Endpoints

Tests static signature verification for endpoints that should require StrictOperatorAccess.
No runtime server required - uses AST parsing to verify security decorators.
"""

import ast
import sys
from pathlib import Path
import pytest

# Path to repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PY = REPO_ROOT / "tmp_agent" / "brain_v9" / "main.py"
API_SECURITY_PY = REPO_ROOT / "tmp_agent" / "brain_v9" / "api_security.py"


def parse_file_ast(file_path: Path) -> ast.Module:
    """Parse a file and return AST."""
    if not file_path.exists():
        pytest.skip(f"File not found: {file_path}")
    source = file_path.read_text(encoding="utf-8", errors="replace")
    return ast.parse(source)


def get_function_by_name(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | None:
    """Find an async function by name in the AST."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def function_has_strict_operator_access_param(func: ast.AsyncFunctionDef) -> bool:
    """Check if function has _operator: StrictOperatorAccess parameter."""
    for param in func.args.args:
        if param.arg == "_operator":
            if param.annotation:
                if isinstance(param.annotation, ast.Name) and param.annotation.id == "StrictOperatorAccess":
                    return True
                if isinstance(param.annotation, ast.Subscript):
                    # Handle Annotated[None, Depends(...)] - check the annotation string
                    annotation_str = ast.unparse(param.annotation)
                    if "StrictOperatorAccess" in annotation_str:
                        return True
    return False


def function_has_operator_access_param(func: ast.AsyncFunctionDef) -> bool:
    """Check if function has _operator: OperatorAccess parameter."""
    for param in func.args.args:
        if param.arg == "_operator":
            if param.annotation:
                if isinstance(param.annotation, ast.Name) and param.annotation.id == "OperatorAccess":
                    return True
    return False


class TestStrictAuthFunctionExists:
    """Test that require_strict_operator_access exists in api_security.py."""
    
    def test_strict_function_exists(self):
        """require_strict_operator_access function must exist."""
        tree = parse_file_ast(API_SECURITY_PY)
        func = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "require_strict_operator_access":
                func = node
                break
        assert func is not None, "require_strict_operator_access function not found in api_security.py"
    
    def test_strict_operator_access_alias_exists(self):
        """StrictOperatorAccess alias must exist."""
        tree = parse_file_ast(API_SECURITY_PY)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "StrictOperatorAccess":
                        found = True
                        break
        assert found, "StrictOperatorAccess alias not found in api_security.py"
    
    def test_strict_function_has_no_localhost_bypass(self):
        """require_strict_operator_access must NOT allow localhost bypass."""
        tree = parse_file_ast(API_SECURITY_PY)
        func = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "require_strict_operator_access":
                func = node
                break
        assert func is not None, "require_strict_operator_access function not found"
        
        # Extract function body
        lines = API_SECURITY_PY.read_text(encoding="utf-8", errors="replace").splitlines()
        body = "\n".join(lines[func.lineno-1:func.end_lineno])
        
        assert "is_local_request" not in body, "require_strict_operator_access must NOT contain is_local_request"
        assert "127.0.0.1" not in body, "require_strict_operator_access must NOT contain 127.0.0.1"
        assert "localhost" not in body.lower(), "require_strict_operator_access must NOT contain localhost"
        assert "BRAIN_ADMIN_TOKEN" in body, "require_strict_operator_access must use BRAIN_ADMIN_TOKEN"
        assert "X-Brain-Token" in body or "x-brain-token" in body.lower(), "require_strict_operator_access must use X-Brain-Token"
        assert "HTTPException" in body, "require_strict_operator_access must raise HTTPException"


class TestIntrospectivoEndpointsRequireStrictAuth:
    """Test that introspectivo endpoints require StrictOperatorAccess."""
    
    def test_chat_introspectivo_debug_uses_strict_operator_access(self):
        """GET /chat/introspectivo/debug must require StrictOperatorAccess."""
        tree = parse_file_ast(MAIN_PY)
        func = get_function_by_name(tree, "chat_introspectivo_debug")
        assert func is not None, "chat_introspectivo_debug function not found"
        assert function_has_strict_operator_access_param(func), \
            "chat_introspectivo_debug must have _operator: StrictOperatorAccess parameter"
        assert not function_has_operator_access_param(func), \
            "chat_introspectivo_debug should NOT use OperatorAccess (must use StrictOperatorAccess)"
    
    def test_chat_introspectivo_uses_strict_operator_access(self):
        """POST /chat/introspectivo must require StrictOperatorAccess."""
        tree = parse_file_ast(MAIN_PY)
        func = get_function_by_name(tree, "chat_introspectivo")
        assert func is not None, "chat_introspectivo function not found"
        assert function_has_strict_operator_access_param(func), \
            "chat_introspectivo must have _operator: StrictOperatorAccess parameter"
        assert not function_has_operator_access_param(func), \
            "chat_introspectivo should NOT use OperatorAccess (must use StrictOperatorAccess)"


class TestGateEndpointsRequireStrictAuth:
    """Test that governance gate endpoints require StrictOperatorAccess."""
    
    def test_gate_approve_uses_strict_operator_access(self):
        """POST /gate/approve/{pending_id} must require StrictOperatorAccess."""
        tree = parse_file_ast(MAIN_PY)
        func = get_function_by_name(tree, "gate_approve")
        assert func is not None, "gate_approve function not found"
        assert function_has_strict_operator_access_param(func), \
            "gate_approve must have _operator: StrictOperatorAccess parameter"
        assert not function_has_operator_access_param(func), \
            "gate_approve should NOT use OperatorAccess (must use StrictOperatorAccess)"


class TestAgentEndpointRequiresStrictAuth:
    """Test that /agent endpoint requires StrictOperatorAccess."""
    
    def test_run_agent_uses_strict_operator_access(self):
        """POST /agent must require StrictOperatorAccess."""
        tree = parse_file_ast(MAIN_PY)
        func = get_function_by_name(tree, "run_agent")
        assert func is not None, "run_agent function not found"
        assert function_has_strict_operator_access_param(func), \
            "run_agent must have _operator: StrictOperatorAccess parameter"
        assert not function_has_operator_access_param(func), \
            "run_agent should NOT use OperatorAccess (must use StrictOperatorAccess)"


class TestChatEndpointRemainsPublic:
    """Verify /chat endpoint remains unprotected (intentional)."""
    
    def test_chat_endpoint_no_operator_access(self):
        """POST /chat should NOT require OperatorAccess or StrictOperatorAccess (public endpoint)."""
        tree = parse_file_ast(MAIN_PY)
        func = get_function_by_name(tree, "chat")
        assert func is not None, "chat function not found"
        assert not function_has_operator_access_param(func), \
            "chat must NOT have OperatorAccess (public endpoint)"
        assert not function_has_strict_operator_access_param(func), \
            "chat must NOT have StrictOperatorAccess (public endpoint)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
