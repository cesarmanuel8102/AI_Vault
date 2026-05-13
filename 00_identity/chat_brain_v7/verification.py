"""
Fase 4: Sistema de Verificación Automática
Verifica que cambios son válidos y no rompen el sistema
"""

import ast
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class VerificationResult:
    """Resultado de verificación"""
    success: bool
    checks_passed: int
    checks_failed: int
    errors: List[str]
    warnings: List[str]
    can_revert: bool = False


class SyntaxVerifier:
    """Verifica sintaxis de código Python"""
    
    def verify_file(self, file_path: str) -> Dict:
        """Verifica que un archivo tiene sintaxis válida"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Intentar parsear AST
            ast.parse(content)
            
            return {
                "success": True,
                "file": file_path,
                "syntax_valid": True,
                "errors": []
            }
            
        except SyntaxError as e:
            return {
                "success": False,
                "file": file_path,
                "syntax_valid": False,
                "errors": [f"Syntax error at line {e.lineno}: {e.msg}"]
            }
        except Exception as e:
            return {
                "success": False,
                "file": file_path,
                "syntax_valid": False,
                "errors": [str(e)]
            }
    
    def verify_code_snippet(self, code: str) -> Dict:
        """Verifica un snippet de código"""
        try:
            ast.parse(code)
            return {"success": True, "syntax_valid": True, "errors": []}
        except SyntaxError as e:
            return {
                "success": False,
                "syntax_valid": False,
                "errors": [f"Line {e.lineno}: {e.msg}"]
            }


class SemanticVerifier:
    """Verifica semántica del código"""
    
    def __init__(self):
        self.syntax_verifier = SyntaxVerifier()
    
    def verify_function_signature(self, file_path: str, function_name: str) -> Dict:
        """Verifica que una función mantiene su firma"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                    args = [arg.arg for arg in node.args.args]
                    return {
                        "success": True,
                        "function": function_name,
                        "args": args,
                        "has_return": any(isinstance(n, ast.Return) for n in ast.walk(node))
                    }
            
            return {"success": False, "error": f"Function {function_name} not found"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def check_imports_valid(self, file_path: str) -> Dict:
        """Verifica que todos los imports son válidos"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
            
            invalid_imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        try:
                            __import__(alias.name)
                        except ImportError:
                            invalid_imports.append(alias.name)
                
                elif isinstance(node, ast.ImportFrom):
                    module = node.module
                    if module:
                        try:
                            __import__(module)
                        except ImportError:
                            invalid_imports.append(module)
            
            return {
                "success": len(invalid_imports) == 0,
                "invalid_imports": invalid_imports,
                "message": f"Found {len(invalid_imports)} invalid imports" if invalid_imports else "All imports valid"
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


class TestRunner:
    """Ejecuta tests para validar cambios"""
    
    def run_pytest(self, test_path: str) -> Dict:
        """Ejecuta tests con pytest"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Parsear salida
            output = result.stdout + result.stderr
            
            # Extraer estadísticas
            passed = output.count("PASSED")
            failed = output.count("FAILED")
            errors = output.count("ERROR")
            
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "output": output[-2000:] if len(output) > 2000 else output
            }
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Tests timed out after 60s"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def run_unittest(self, test_file: str) -> Dict:
        """Ejecuta tests con unittest"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "unittest", test_file, "-v"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            output = result.stdout + result.stderr
            
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "output": output[-2000:] if len(output) > 2000 else output
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


class ChangeVerifier:
    """Verificador completo de cambios"""
    
    def __init__(self):
        self.syntax_verifier = SyntaxVerifier()
        self.semantic_verifier = SemanticVerifier()
        self.test_runner = TestRunner()
        self.backup_dir = None
    
    def create_backup(self, file_path: str) -> Optional[str]:
        """Crea backup antes de modificar"""
        try:
            self.backup_dir = tempfile.mkdtemp(prefix="brain_backup_")
            backup_path = Path(self.backup_dir) / Path(file_path).name
            shutil.copy2(file_path, backup_path)
            return str(backup_path)
        except Exception as e:
            print(f"[WARNING] Could not create backup: {e}")
            return None
    
    def verify_change(self, file_path: str, run_tests: bool = False,
                     test_path: Optional[str] = None) -> VerificationResult:
        """
        Verifica un cambio completamente
        
        Proceso:
        1. Verificar sintaxis
        2. Verificar imports válidos
        3. Ejecutar tests (si se solicita)
        4. Generar reporte
        """
        errors = []
        warnings = []
        checks_passed = 0
        checks_failed = 0
        can_revert = False
        
        # 1. Verificar sintaxis
        syntax_result = self.syntax_verifier.verify_file(file_path)
        if syntax_result["success"]:
            checks_passed += 1
        else:
            checks_failed += 1
            errors.extend(syntax_result.get("errors", []))
        
        # 2. Verificar imports (solo si sintaxis OK)
        if syntax_result["success"]:
            import_result = self.semantic_verifier.check_imports_valid(file_path)
            if import_result["success"]:
                checks_passed += 1
            else:
                checks_failed += 1
                warnings.append(import_result.get("message", "Import issues"))
        
        # 3. Ejecutar tests (opcional)
        if run_tests and test_path:
            test_result = self.test_runner.run_pytest(test_path)
            if test_result["success"]:
                checks_passed += 1
            else:
                checks_failed += 1
                errors.append(f"Tests failed: {test_result.get('failed', 0)} failed")
        
        # 4. Verificar si podemos revertir
        if self.backup_dir and Path(self.backup_dir).exists():
            can_revert = True
        
        return VerificationResult(
            success=checks_failed == 0,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            errors=errors,
            warnings=warnings,
            can_revert=can_revert
        )
    
    def revert_changes(self, file_path: str) -> bool:
        """Revierte cambios desde backup"""
        if not self.backup_dir:
            return False
        
        try:
            backup_file = Path(self.backup_dir) / Path(file_path).name
            if backup_file.exists():
                shutil.copy2(backup_file, file_path)
                return True
            return False
        except Exception as e:
            print(f"[ERROR] Could not revert: {e}")
            return False


# Funciones de conveniencia
def verify_file(file_path: str) -> Dict:
    """Verifica un archivo rápidamente"""
    verifier = SyntaxVerifier()
    return verifier.verify_file(file_path)


def verify_and_test(file_path: str, test_path: str) -> Dict:
    """Verifica archivo y ejecuta tests"""
    verifier = ChangeVerifier()
    result = verifier.verify_change(file_path, run_tests=True, test_path=test_path)
    
    return {
        "success": result.success,
        "checks": {
            "passed": result.checks_passed,
            "failed": result.checks_failed
        },
        "errors": result.errors,
        "warnings": result.warnings,
        "can_revert": result.can_revert
    }


__all__ = [
    'SyntaxVerifier',
    'SemanticVerifier',
    'TestRunner',
    'ChangeVerifier',
    'VerificationResult',
    'verify_file',
    'verify_and_test'
]


if __name__ == "__main__":
    # Test
    print("Testing verification module...")
    
    # Test syntax verification
    verifier = SyntaxVerifier()
    result = verifier.verify_code_snippet("def test(): pass")
    print(f"\nSyntax check: {result}")
    
    # Test invalid code
    result = verifier.verify_code_snippet("def test(: pass")
    print(f"Invalid syntax check: {result}")
