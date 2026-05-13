#!/usr/bin/env python3
"""
Tests Unitarios - AST Analyzer
Cobertura completa del módulo de análisis AST
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools_advanced import ASTAnalyzer, ASTAnalysis


class TestASTAnalyzer:
    """Tests unitarios para ASTAnalyzer"""
    
    def __init__(self):
        self.analyzer = ASTAnalyzer()
        self.passed = 0
        self.failed = 0
    
    def test_analyze_simple_file(self):
        """Test: Analizar archivo simple"""
        try:
            # Crear archivo temporal
            test_code = """
def test_func():
    pass

class TestClass:
    def method(self):
        pass
"""
            temp_file = Path("C:/AI_VAULT/tmp_agent/test_ast.py")
            temp_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file.write_text(test_code)
            
            result = self.analyzer.analyze_file(str(temp_file))
            
            assert result.total_lines > 0
            assert len(result.functions) == 1
            assert len(result.classes) == 1
            assert result.classes[0].methods[0].name == "method"
            
            print("[PASS] test_analyze_simple_file")
            self.passed += 1
            return True
        except Exception as e:
            print(f"[FAIL] test_analyze_simple_file: {e}")
            self.failed += 1
            return False
    
    def test_find_function(self):
        """Test: Buscar función específica"""
        try:
            test_code = """
def target_function(x, y):
    return x + y

def other_func():
    pass
"""
            temp_file = Path("C:/AI_VAULT/tmp_agent/test_find.py")
            temp_file.write_text(test_code)
            
            result = self.analyzer.analyze_file(str(temp_file))
            
            target = [f for f in result.functions if f.name == "target_function"]
            assert len(target) == 1
            assert "x" in target[0].args
            assert "y" in target[0].args
            
            print("[PASS] test_find_function")
            self.passed += 1
            return True
        except Exception as e:
            print(f"[FAIL] test_find_function: {e}")
            self.failed += 1
            return False
    
    def test_complexity_calculation(self):
        """Test: Cálculo de complejidad"""
        try:
            test_code = """
def complex_func(x):
    if x > 0:
        if x < 10:
            return x
        else:
            return 10
    return 0
"""
            temp_file = Path("C:/AI_VAULT/tmp_agent/test_complexity.py")
            temp_file.write_text(test_code)
            
            result = self.analyzer.analyze_file(str(temp_file))
            
            # Complejidad debe ser > 1 por los ifs
            assert result.complexity_score > 1
            
            print("[PASS] test_complexity_calculation")
            self.passed += 1
            return True
        except Exception as e:
            print(f"[FAIL] test_complexity_calculation: {e}")
            self.failed += 1
            return False
    
    def test_file_not_found(self):
        """Test: Manejo de archivo no existente"""
        try:
            result = self.analyzer.analyze_file("/nonexistent/file.py")
            assert result.total_lines == 0
            assert result.complexity_score == -2  # Error
            
            print("[PASS] test_file_not_found")
            self.passed += 1
            return True
        except Exception as e:
            print(f"[FAIL] test_file_not_found: {e}")
            self.failed += 1
            return False
    
    def test_syntax_error(self):
        """Test: Manejo de error de sintaxis"""
        try:
            test_code = "def broken(: pass"
            temp_file = Path("C:/AI_VAULT/tmp_agent/test_syntax.py")
            temp_file.write_text(test_code)
            
            result = self.analyzer.analyze_file(str(temp_file))
            
            assert result.complexity_score == -1  # Syntax error
            
            print("[PASS] test_syntax_error")
            self.passed += 1
            return True
        except Exception as e:
            print(f"[FAIL] test_syntax_error: {e}")
            self.failed += 1
            return False
    
    def run_all(self):
        """Ejecuta todos los tests"""
        print("=" * 60)
        print("TESTS UNITARIOS - AST ANALYZER")
        print("=" * 60)
        
        self.test_analyze_simple_file()
        self.test_find_function()
        self.test_complexity_calculation()
        self.test_file_not_found()
        self.test_syntax_error()
        
        print("=" * 60)
        print(f"RESULTADO: {self.passed}/{self.passed + self.failed} ({self.passed/(self.passed + self.failed)*100:.0f}%)")
        print("=" * 60)


if __name__ == "__main__":
    tester = TestASTAnalyzer()
    tester.run_all()
