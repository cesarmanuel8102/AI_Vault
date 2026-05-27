"""
AST Validation for P2-E Commit 4D-EvidenceInjection
Validates security constraints via AST analysis.
"""

import ast
import sys
from pathlib import Path

# Files to validate for Commit 4D-EvidenceInjection
FILES_TO_VALIDATE = [
    "brain/semantic_memory_external_evidence_contract.py",
    "tests/unit/test_semantic_memory_external_evidence_contract.py",
    "tests/smoke/smoke_semantic_memory_external_evidence_contract.py",
]

def validate_file(filepath: str) -> tuple[bool, list[str]]:
    """Validate a single file for security constraints."""
    errors = []
    
    try:
        content = Path(filepath).read_text(encoding="utf-8")
        tree = ast.parse(content)
    except Exception as e:
        errors.append(f"Failed to parse {filepath}: {e}")
        return False, errors
    
    # Check imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ["subprocess", "faiss", "requests", "httpx", "shutil"]:
                    errors.append(f"{filepath}:{node.lineno}: Forbidden import '{alias.name}'")
        
        if isinstance(node, ast.ImportFrom):
            if node.module in ["subprocess", "faiss", "requests", "httpx", "shutil"]:
                errors.append(f"{filepath}:{node.lineno}: Forbidden import from '{node.module}'")
    
    # Check function calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check for open()
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                errors.append(f"{filepath}:{node.lineno}: Forbidden 'open()' call")
            
            # Check for subprocess calls
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in ["run", "call", "Popen", "check_output"]:
                    errors.append(f"{filepath}:{node.lineno}: Forbidden subprocess method '{node.func.attr}'")
            
            # Check for write operations
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in ["write_text", "write_bytes", "unlink", "remove", "rmdir", "copy"]:
                    errors.append(f"{filepath}:{node.lineno}: Forbidden file operation '{node.func.attr}'")
            
            # Check for add_memory calls
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "add_memory":
                    errors.append(f"{filepath}:{node.lineno}: Forbidden 'add_memory' call")
    
    # Check for allow_real_write=True in assignments
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "allow_real_write":
                    if isinstance(node.value, ast.Constant) and node.value.value is True:
                        errors.append(f"{filepath}:{node.lineno}: Forbidden 'allow_real_write = True'")
    
    # Check for allow_real_write=True in function arguments
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "allow_real_write":
                    if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        errors.append(f"{filepath}:{node.lineno}: Forbidden 'allow_real_write=True' in call")
    
    # Check content-level patterns (simple text search for patterns AST might miss)
    # But skip if the pattern is inside a string literal (e.g., in test assertions)
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        # Skip comment lines
        if line.strip().startswith('#'):
            continue
        
        # Check for allow_real_write = True (but skip if inside a string)
        if 'allow_real_write = True' in line:
            # Check if it's inside a string literal
            # Simple heuristic: count quotes before the pattern
            prefix = line.split('allow_real_write = True')[0]
            single_quotes = prefix.count("'")
            double_quotes = prefix.count('"')
            # If odd number of quotes, it's inside a string
            if single_quotes % 2 == 0 and double_quotes % 2 == 0:
                errors.append(f"{filepath}:{i}: Contains 'allow_real_write = True'")
        
        if 'allow_real_write=True' in line:
            # Skip if inside a string
            prefix = line.split('allow_real_write=True')[0]
            single_quotes = prefix.count("'")
            double_quotes = prefix.count('"')
            if single_quotes % 2 == 0 and double_quotes % 2 == 0:
                errors.append(f"{filepath}:{i}: Contains 'allow_real_write=True'")
    
    return len(errors) == 0, errors


def main():
    """Run AST validation on all target files."""
    all_passed = True
    all_errors = []
    
    print("=" * 70)
    print("P2-E Commit 4D-EvidenceInjection: AST Security Validation")
    print("=" * 70)
    print()
    
    for filepath in FILES_TO_VALIDATE:
        print(f"Validating: {filepath}")
        if not Path(filepath).exists():
            print(f"  [SKIP] File not found")
            continue
        
        passed, errors = validate_file(filepath)
        if passed:
            print(f"  [OK] No security violations found")
        else:
            all_passed = False
            for error in errors:
                print(f"  [VIOLATION] {error}")
                all_errors.append(error)
    
    print()
    print("=" * 70)
    
    if all_passed:
        print("SECURITY_VALIDATION_OK")
        print("All files passed AST security validation")
        return 0
    else:
        print("SECURITY_VALIDATION_FAILED")
        print(f"Found {len(all_errors)} security violations")
        return 1


if __name__ == "__main__":
    sys.exit(main())
