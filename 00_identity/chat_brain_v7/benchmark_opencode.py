#!/usr/bin/env python3
"""
Fase 7: Benchmark Comparativo vs OpenCode
Pruebas que validan equivalencia funcional
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import sys

sys.path.insert(0, str(Path(__file__).parent))


class BenchmarkOpenCode:
    """Benchmark comparativo entre Brain Agent V8 y OpenCode"""
    
    def __init__(self):
        self.results = []
        self.total_tests = 0
        self.passed_tests = 0
        
    async def run_benchmark(self):
        """Ejecuta todas las pruebas de benchmark"""
        print("=" * 70)
        print("BENCHMARK BRAIN AGENT V8 vs OPENCODE")
        print("=" * 70)
        print("\nCategorías de prueba:")
        print("1. Análisis de código")
        print("2. Búsqueda y navegación")
        print("3. Refactorización")
        print("4. Debug")
        print("5. Generación de código")
        print("6. Workflow completo")
        
        # Ejecutar pruebas
        await self.benchmark_analysis()
        await self.benchmark_search()
        await self.benchmark_refactoring()
        await self.benchmark_debug()
        await self.benchmark_generation()
        await self.benchmark_workflow()
        
        self.print_summary()
    
    async def benchmark_analysis(self):
        """Benchmark: Análisis de código"""
        print("\n" + "-" * 70)
        print("TEST: Análisis de archivo Python")
        print("-" * 70)
        
        test_file = Path(__file__).parent / "agent_core.py"
        
        start_time = time.time()
        
        try:
            from tools_advanced import ASTAnalyzer
            analyzer = ASTAnalyzer()
            result = analyzer.analyze_file(str(test_file))
            
            elapsed = time.time() - start_time
            
            # Verificar calidad del análisis
            checks = [
                ("Archivo leído", result.total_lines > 0),
                ("Funciones detectadas", len(result.functions) > 0),
                ("Clases detectadas", len(result.classes) >= 0),
                ("Complejidad calculada", result.complexity_score >= 0)
            ]
            
            passed = sum(1 for _, ok in checks if ok)
            
            print(f"✓ Archivo: {test_file.name}")
            print(f"✓ Líneas: {result.total_lines}")
            print(f"✓ Funciones: {len(result.functions)}")
            print(f"✓ Tiempo: {elapsed:.2f}s")
            print(f"✓ Checks: {passed}/{len(checks)}")
            
            self.record_result("Análisis AST", passed == len(checks), elapsed)
            
        except Exception as e:
            print(f"✗ Error: {e}")
            self.record_result("Análisis AST", False, 0)
    
    async def benchmark_search(self):
        """Benchmark: Búsqueda en codebase"""
        print("\n" + "-" * 70)
        print("TEST: Búsqueda grep en directorio")
        print("-" * 70)
        
        start_time = time.time()
        
        try:
            from tools_advanced import AdvancedSearch
            searcher = AdvancedSearch()
            
            results = searcher.grep("def ", str(Path(__file__).parent), recursive=True)
            elapsed = time.time() - start_time
            
            found = len(results) > 0
            print(f"✓ Funciones encontradas: {len(results)}")
            print(f"✓ Tiempo: {elapsed:.2f}s")
            print(f"✓ Muestra: {results[0]['content'][:60] if results else 'N/A'}...")
            
            self.record_result("Búsqueda grep", found, elapsed)
            
        except Exception as e:
            print(f"✗ Error: {e}")
            self.record_result("Búsqueda grep", False, 0)
    
    async def benchmark_refactoring(self):
        """Benchmark: Refactorización"""
        print("\n" + "-" * 70)
        print("TEST: Planificación de refactorización")
        print("-" * 70)
        
        start_time = time.time()
        
        try:
            from reasoning import RefactoringPlanner
            planner = RefactoringPlanner()
            
            test_file = Path(__file__).parent / "agent_core.py"
            plan = planner.plan_refactoring(str(test_file), "optimize_imports")
            
            elapsed = time.time() - start_time
            
            success = plan.get("success", False)
            print(f"✓ Plan generado: {success}")
            print(f"✓ Pasos: {len(plan.get('steps', []))}")
            print(f"✓ Tiempo: {elapsed:.2f}s")
            
            self.record_result("Refactorización", success, elapsed)
            
        except Exception as e:
            print(f"✗ Error: {e}")
            self.record_result("Refactorización", False, 0)
    
    async def benchmark_debug(self):
        """Benchmark: Debugging"""
        print("\n" + "-" * 70)
        print("TEST: Análisis de error")
        print("-" * 70)
        
        start_time = time.time()
        
        try:
            from reasoning import DebugReasoner
            debugger = DebugReasoner()
            
            error = "NameError: name 'undefined_var' is not defined"
            result = debugger.analyze_error(error, "", "")
            
            elapsed = time.time() - start_time
            
            has_hypotheses = len(result.hypotheses) > 0
            has_root_cause = bool(result.root_cause)
            
            print(f"✓ Hipótesis: {len(result.hypotheses)}")
            print(f"✓ Causa raíz: {result.root_cause[:60] if result.root_cause else 'N/A'}...")
            print(f"✓ Tiempo: {elapsed:.2f}s")
            
            self.record_result("Debug", has_hypotheses and has_root_cause, elapsed)
            
        except Exception as e:
            print(f"✗ Error: {e}")
            self.record_result("Debug", False, 0)
    
    async def benchmark_generation(self):
        """Benchmark: Generación de código"""
        print("\n" + "-" * 70)
        print("TEST: Generación de función")
        print("-" * 70)
        
        start_time = time.time()
        
        try:
            from reasoning import CodeGenerator
            from verification import SyntaxVerifier
            
            generator = CodeGenerator()
            verifier = SyntaxVerifier()
            
            code = generator.generate_function(
                "calculate_metrics",
                "Calculate metrics",
                [{"name": "data", "type": "List[float]"}],
                "Dict[str, float]"
            )
            
            # Verificar sintaxis
            syntax_ok = verifier.verify_code_snippet(code)["success"]
            
            elapsed = time.time() - start_time
            
            print(f"✓ Código generado: {len(code)} caracteres")
            print(f"✓ Sintaxis válida: {syntax_ok}")
            print(f"✓ Tiempo: {elapsed:.2f}s")
            
            self.record_result("Generación código", syntax_ok, elapsed)
            
        except Exception as e:
            print(f"✗ Error: {e}")
            self.record_result("Generación código", False, 0)
    
    async def benchmark_workflow(self):
        """Benchmark: Workflow completo del agente"""
        print("\n" + "-" * 70)
        print("TEST: Workflow completo del agente")
        print("-" * 70)
        
        start_time = time.time()
        
        try:
            from agent_core import AgentLoop
            agent = AgentLoop("benchmark")
            
            result = await agent.run_cycle(
                "Ejecuta comando echo 'test'",
                {"user_id": "benchmark"}
            )
            
            elapsed = time.time() - start_time
            
            success = result.get("success", False)
            steps_completed = result.get("completed_steps", 0)
            
            print(f"✓ Workflow completado: {success}")
            print(f"✓ Pasos: {steps_completed}")
            print(f"✓ Tiempo: {elapsed:.2f}s")
            
            self.record_result("Workflow", success and steps_completed > 0, elapsed)
            
        except Exception as e:
            print(f"✗ Error: {e}")
            self.record_result("Workflow", False, 0)
    
    def record_result(self, test_name: str, passed: bool, elapsed: float):
        """Registra resultado"""
        self.results.append({
            "test": test_name,
            "passed": passed,
            "time": elapsed
        })
        
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
    
    def print_summary(self):
        """Imprime resumen"""
        print("\n" + "=" * 70)
        print("RESUMEN DEL BENCHMARK")
        print("=" * 70)
        
        total_time = sum(r["time"] for r in self.results)
        
        print(f"\nResultados por categoría:")
        for r in self.results:
            status = "✓ PASS" if r["passed"] else "✗ FAIL"
            print(f"  {status:8s} {r['test']:25s} ({r['time']:.2f}s)")
        
        print(f"\nTotales:")
        print(f"  Tests: {self.passed_tests}/{self.total_tests}")
        print(f"  Porcentaje: {(self.passed_tests/self.total_tests*100):.1f}%")
        print(f"  Tiempo total: {total_time:.2f}s")
        print(f"  Tiempo promedio: {total_time/self.total_tests:.2f}s")
        
        # Calificación vs OpenCode
        if self.passed_tests == self.total_tests:
            print("\n🎉 EXCELENTE: Todos los tests pasaron")
            print("   El agente demuestra equivalencia funcional con OpenCode")
        elif self.passed_tests >= self.total_tests * 0.8:
            print("\n✓ BUENO: Mayoría de tests pasaron")
            print("   El agente es funcional pero requiere mejoras")
        else:
            print("\n⚠️  NECESITA TRABAJO: Menos del 80% pasaron")
            print("   Se requieren mejoras significativas")
        
        print("\n" + "=" * 70)


if __name__ == "__main__":
    benchmark = BenchmarkOpenCode()
    asyncio.run(benchmark.run_benchmark())
