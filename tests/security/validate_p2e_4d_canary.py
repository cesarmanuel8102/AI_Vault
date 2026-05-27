"""
AST Security Validation for P2-E Commit 4D-RealWriteCanaryPlan
Validates module safety invariants.
Must print: SECURITY_VALIDATION_OK
"""

import ast
import inspect
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from brain import semantic_memory_real_write_canary_plan as module


def validate_no_subprocess():
    """Validate no subprocess import."""
    source = inspect.getsource(module)
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    return False, "subprocess import found"
        elif isinstance(node, ast.ImportFrom):
            if node.module == "subprocess":
                return False, "subprocess import from found"
    
    return True, "No subprocess"


def validate_no_faiss():
    """Validate no faiss import."""
    source = inspect.getsource(module)
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "faiss" in alias.name.lower():
                    return False, f"faiss import found: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module and "faiss" in node.module.lower():
                return False, f"faiss import from found: {node.module}"
    
    return True, "No FAISS"


def validate_no_semantic_memory_bridge():
    """Validate no semantic_memory_bridge import."""
    source = inspect.getsource(module)
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "semantic_memory_bridge":
                return False, "semantic_memory_bridge import found"
            if node.module and "semantic_memory_bridge" in node.module:
                return False, f"semantic_memory_bridge import found: {node.module}"
    
    return True, "No semantic_memory_bridge"


def validate_no_add_memory_calls():
    """Validate no add_memory function calls."""
    source = inspect.getsource(module)
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "add_memory":
                return False, "add_memory function call found"
            if isinstance(node.func, ast.Attribute) and node.func.attr == "add_memory":
                return False, "add_memory method call found"
    
    return True, "No add_memory calls"


def validate_no_write_operations():
    """Validate no write file operations."""
    source = inspect.getsource(module)
    tree = ast.parse(source)
    
    forbidden = ["write_text", "write_bytes", "open", "unlink", "remove", "rmdir"]
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in forbidden:
                    return False, f"{node.func.attr} call found"
    
    return True, "No write operations"


def validate_no_shutil():
    """Validate no shutil import."""
    source = inspect.getsource(module)
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "shutil":
                    return False, "shutil import found"
        elif isinstance(node, ast.ImportFrom):
            if node.module == "shutil":
                return False, "shutil import from found"
    
    return True, "No shutil"


def validate_no_copy_calls():
    """Validate no .copy() calls."""
    source = inspect.getsource(module)
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "copy":
                    return False, ".copy() call found"
    
    return True, "No .copy() calls"


def validate_no_os_system():
    """Validate no os.system or os.popen calls."""
    source = inspect.getsource(module)
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in ["system", "popen", "spawn"]:
                    return False, f"os.{node.func.attr} call found"
    
    return True, "No os.system/os.popen"


def validate_invariants():
    """Validate module invariants."""
    # Check class exists
    if not hasattr(module, 'SemanticMemoryRealWriteCanaryPlan'):
        return False, "SemanticMemoryRealWriteCanaryPlan class not found"
    
    plan_class = module.SemanticMemoryRealWriteCanaryPlan
    
    # Check default invariants in docstring
    if hasattr(plan_class, '__doc__'):
        doc = plan_class.__doc__ or ""
        if "allow_real_write" not in doc.lower():
            return False, "allow_real_write not in class docstring"
    
    return True, "Invariants validated"


def run_validation():
    """Run all security validations."""
    validations = [
        validate_no_subprocess,
        validate_no_faiss,
        validate_no_semantic_memory_bridge,
        validate_no_add_memory_calls,
        validate_no_write_operations,
        validate_no_shutil,
        validate_no_copy_calls,
        validate_no_os_system,
        validate_invariants,
    ]
    
    all_passed = True
    results = []
    
    for validator in validations:
        try:
            passed, message = validator()
            results.append((validator.__name__, passed, message))
            if not passed:
                all_passed = False
        except Exception as e:
            results.append((validator.__name__, False, str(e)))
            all_passed = False
    
    return all_passed, results


if __name__ == "__main__":
    passed, results = run_validation()
    
    for name, result, message in results:
        status = "PASS" if result else "FAIL"
        print(f"[{status}] {name}: {message}")
    
    if passed:
        print("SECURITY_VALIDATION_OK")
        sys.exit(0)
    else:
        print("SECURITY_VALIDATION_FAILED")
        sys.exit(1)
