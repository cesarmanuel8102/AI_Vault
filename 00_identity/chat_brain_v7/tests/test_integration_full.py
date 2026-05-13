#!/usr/bin/env python3
"""
Tests de Integración Completa - Sistema Brain Chat V8.1
Verifica que todos los componentes trabajan juntos correctamente
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from agent_core import AgentLoop
    AGENT_OK = True
except ImportError:
    AGENT_OK = False

try:
    from tools_advanced import ASTAnalyzer, AdvancedSearch
    TOOLS_OK = True
except ImportError:
    TOOLS_OK = False

try:
    from reasoning import DebugReasoner, CodeGenerator
    REASONING_OK = True
except ImportError:
    REASONING_OK = False

try:
    from verification import SyntaxVerifier, ChangeVerifier
    VERIFY_OK = True
except ImportError:
    VERIFY_OK = False


class TestIntegration:
    """Tests de integración completa"""
    
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
    
    async def test_agent_with_tools(self):
        """Test 1: Agente usa herramientas avanzadas"""
        if not AGENT_OK or not TOOLS_OK:
            self.log_skip("Test 1", "Agent or tools not available")
            return
        
        try:
            agent = AgentLoop("test_integration")
            
            # Tarea simple que no requiere LLM timeout
            result = await agent.run_cycle(
                "Ejecuta comando echo 'Test integracion'",
                {"user_id": "test"}
            )
            
            assert result["success"], "Agent execution failed"
            assert "plan" in result, "No plan in result"
            
            self.log_pass("Test 1", "Agent ejecutado con herramientas")
        except Exception as e:
            self.log_fail("Test 1", f"Error: {e}")
    
    async def test_reasoning_with_verification(self):
        """Test 2: Razonamiento con verificación"""
        if not REASONING_OK or not VERIFY_OK:
            self.log_skip("Test 2", "Reasoning or verification not available")
            return
        
        try:
            # Generar código
            generator = CodeGenerator()
            code = generator.generate_function(
                "test_func",
                "Test function",
                [{"name": "x", "type": "int"}],
                "int"
            )
            
            # Verificar sintaxis
            verifier = SyntaxVerifier()
            result = verifier.verify_code_snippet(code)
            
            assert result["success"], "Generated code has syntax errors"
            assert result["syntax_valid"], "Syntax verification failed"
            
            self.log_pass("Test 2", "Código generado pasa verificación")
        except Exception as e:
            self.log_fail("Test 2", f"Error: {e}")
    
    async def test_debug_and_fix(self):
        """Test 3: Debug identifica y propone fix"""
        if not REASONING_OK:
            self.log_skip("Test 3", "Reasoning not available")
            return
        
        try:
            debugger = DebugReasoner()
            
            # Analizar error típico
            result = debugger.analyze_error(
                "NameError: name 'undefined_var' is not defined",
                "File \"test.py\", line 10, in test_func",
                "test.py"
            )
            
            assert len(result.hypotheses) > 0, "No hypotheses generated"
            assert result.root_cause, "No root cause identified"
            
            self.log_pass("Test 3", f"Debug: {len(result.hypotheses)} hipótesis generadas")
        except Exception as e:
            self.log_fail("Test 3", f"Error: {e}")
    
    async def test_ast_analysis_with_search(self):
        """Test 4: AST + Búsqueda trabajan juntos"""
        if not TOOLS_OK:
            self.log_skip("Test 4", "Tools not available")
            return
        
        try:
            # Buscar archivos Python
            searcher = AdvancedSearch()
            files = searcher.glob_files("*.py", str(Path(__file__).parent.parent))
            
            assert len(files) > 0, "No Python files found"
            
            # Analizar primer archivo
            analyzer = ASTAnalyzer()
            analysis = analyzer.analyze_file(files[0])
            
            assert analysis.total_lines > 0, "Analysis failed"
            
            self.log_pass("Test 4", f"AST+Search: {len(files)} archivos, analizado {files[0]}")
        except Exception as e:
            self.log_fail("Test 4", f"Error: {e}")
    
    async def test_end_to_end_workflow(self):
        """Test 5: Flujo completo end-to-end"""
        if not AGENT_OK:
            self.log_skip("Test 5", "Agent not available")
            return
        
        try:
            # Workflow: Agente recibe tarea -> Planifica -> Ejecuta -> Verifica
            agent = AgentLoop("test_e2e")
            
            result = await agent.run_cycle(
                "Ejecuta comando 'echo Hello from integration test'",
                {"user_id": "test"}
            )
            
            assert result["success"], "End-to-end workflow failed"
            assert result.get("completed_steps", 0) >= 0, "No steps completed"
            
            self.log_pass("Test 5", "Flujo end-to-end completado")
        except Exception as e:
            self.log_fail("Test 5", f"Error: {e}")
    
    def test_component_availability(self):
        """Test 6: Verificar componentes disponibles"""
        components = {
            "Agent Core": AGENT_OK,
            "Advanced Tools": TOOLS_OK,
            "Reasoning": REASONING_OK,
            "Verification": VERIFY_OK
        }
        
        available = sum(1 for v in components.values() if v)
        total = len(components)
        
        if available == total:
            self.log_pass("Test 6", f"Todos los componentes disponibles ({available}/{total})")
        else:
            self.log_fail("Test 6", f"Faltan componentes: {available}/{total}")
            for name, ok in components.items():
                if not ok:
                    print(f"  - {name}: NO disponible")
    
    async def test_error_recovery(self):
        """Test 7: Recuperación ante errores"""
        if not AGENT_OK:
            self.log_skip("Test 7", "Agent not available")
            return
        
        try:
            agent = AgentLoop("test_recovery")
            
            # Tarea que puede fallar
            result = await agent.run_cycle(
                "Ejecuta comando 'comando_inexistente_12345'",
                {"user_id": "test"}
            )
            
            # Debe reportar el error pero no crashear
            assert "results" in result, "No results in failed execution"
            
            self.log_pass("Test 7", "Recuperación de errores funciona")
        except Exception as e:
            self.log_fail("Test 7", f"Error: {e}")
    
    def log_pass(self, test_name, message):
        self.results.append(f"[PASS] {test_name}: {message}")
        self.passed += 1
    
    def log_fail(self, test_name, message):
        self.results.append(f"[FAIL] {test_name}: {message}")
        self.failed += 1
    
    def log_skip(self, test_name, message):
        self.results.append(f"[SKIP] {test_name}: {message}")
    
    async def run_all(self):
        """Ejecutar todos los tests"""
        print("=" * 70)
        print("TESTS DE INTEGRACIÓN COMPLETA - Brain Chat V8.1")
        print("=" * 70)
        print()
        
        # Test de disponibilidad primero
        self.test_component_availability()
        
        # Tests async
        await self.test_agent_with_tools()
        await self.test_reasoning_with_verification()
        await self.test_debug_and_fix()
        await self.test_ast_analysis_with_search()
        await self.test_end_to_end_workflow()
        await self.test_error_recovery()
        
        print()
        print("=" * 70)
        print("RESULTADOS")
        print("=" * 70)
        for result in self.results:
            print(result)
        print()
        print(f"Total: {self.passed + self.failed} tests")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Success Rate: {self.passed/(self.passed + self.failed)*100:.1f}%" if (self.passed + self.failed) > 0 else "N/A")
        print()
        
        if self.failed == 0 and self.passed > 0:
            print("INTEGRACION COMPLETA - Todos los componentes funcionan juntos")
            return 0
        else:
            print("ALGUNOS TESTS FALLARON - Revisar integracion")
            return 1


if __name__ == "__main__":
    tester = TestIntegration()
    exit_code = asyncio.run(tester.run_all())
    sys.exit(exit_code)
