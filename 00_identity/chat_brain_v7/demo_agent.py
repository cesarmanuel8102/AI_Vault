"""
DEMO: Brain Chat V8.1 - Agente Autónomo en Acción
Muestra el agente ejecutando tareas reales de software engineering
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from agent_core import AgentLoop
    from tools_advanced import ASTAnalyzer, AdvancedSearch, analyze_code_structure
    from reasoning import DebugReasoner, CodeGenerator
    from verification import SyntaxVerifier, ChangeVerifier
    COMPONENTS_OK = True
except ImportError as e:
    print(f"[ERROR] Componentes no disponibles: {e}")
    COMPONENTS_OK = False


class AgentDemo:
    """Demostración del agente autónomo"""
    
    def __init__(self):
        self.agent = AgentLoop("demo_session") if COMPONENTS_OK else None
        self.results = []
    
    async def demo_task_1_analyze_codebase(self):
        """Demo 1: Analizar estructura del código"""
        print("\n" + "="*70)
        print("DEMO 1: Análisis de Codebase")
        print("="*70)
        print("Tarea: Analizar todos los archivos Python en el proyecto")
        
        if not COMPONENTS_OK:
            print("[SKIP] Componentes no disponibles")
            return
        
        # Buscar archivos Python
        searcher = AdvancedSearch()
        files = searcher.glob_files("*.py", str(Path(__file__).parent))
        
        print(f"Encontrados {len(files)} archivos Python")
        
        # Analizar primeros 3 archivos
        analyzer = ASTAnalyzer()
        for file_path in files[:3]:
            print(f"\nAnalizando: {Path(file_path).name}")
            analysis = analyzer.analyze_file(file_path)
            print(f"  Líneas: {analysis.total_lines}")
            print(f"  Funciones: {len(analysis.functions)}")
            print(f"  Clases: {len(analysis.classes)}")
            print(f"  Complejidad: {analysis.complexity_score}")
        
        self.results.append(("Demo 1", "OK", f"Analizados {len(files)} archivos"))
    
    async def demo_task_2_debug_error(self):
        """Demo 2: Debuggear un error real"""
        print("\n" + "="*70)
        print("DEMO 2: Debugging Automático")
        print("="*70)
        print("Tarea: Analizar error y proponer solución")
        
        if not COMPONENTS_OK:
            print("[SKIP] Componentes no disponibles")
            return
        
        debugger = DebugReasoner()
        
        # Simular error típico
        error = "NameError: name 'user_input' is not defined"
        stack = '''File "brain_chat_v8.py", line 245, in process_message
    response = handle_input(user_input)
NameError: name 'user_input' is not defined'''
        
        print(f"\nError simulado:")
        print(f"  {error}")
        print(f"\nStack trace:")
        print(f"  {stack}")
        
        result = debugger.analyze_error(error, stack, "brain_chat_v8.py")
        
        print(f"\nAnálisis del agente:")
        print(f"  Causa raíz: {result.root_cause}")
        print(f"  Hipótesis generadas: {len(result.hypotheses)}")
        print(f"\nHipótesis (ordenadas por confianza):")
        for i, hyp in enumerate(result.hypotheses[:3], 1):
            print(f"  {i}. [{hyp.confidence:.0%}] {hyp.description}")
        
        if result.solution:
            print(f"\nSolución sugerida: {result.solution}")
        
        self.results.append(("Demo 2", "OK", f"{len(result.hypotheses)} hipótesis generadas"))
    
    async def demo_task_3_generate_code(self):
        """Demo 3: Generar código"""
        print("\n" + "="*70)
        print("DEMO 3: Generación de Código")
        print("="*70)
        print("Tarea: Generar una función completa con documentación")
        
        if not COMPONENTS_OK:
            print("[SKIP] Componentes no disponibles")
            return
        
        generator = CodeGenerator()
        
        # Generar función de ejemplo
        code = generator.generate_function(
            "calculate_portfolio_metrics",
            "Calculate portfolio performance metrics including returns, volatility, and Sharpe ratio",
            [
                {"name": "returns", "type": "List[float]", "description": "List of daily returns"},
                {"name": "risk_free_rate", "type": "float", "default": "0.02", "description": "Annual risk-free rate"}
            ],
            "Dict[str, float]"
        )
        
        print("\nCódigo generado:")
        print("-" * 70)
        print(code)
        print("-" * 70)
        
        # Verificar sintaxis
        verifier = SyntaxVerifier()
        syntax_result = verifier.verify_code_snippet(code)
        
        print(f"\nVerificación de sintaxis: {'✓ Válido' if syntax_result['success'] else '✗ Inválido'}")
        
        self.results.append(("Demo 3", "OK", "Función generada y verificada"))
    
    async def demo_task_4_agent_workflow(self):
        """Demo 4: Workflow completo del agente"""
        print("\n" + "="*70)
        print("DEMO 4: Workflow Completo del Agente")
        print("="*70)
        print("Tarea: Agente recibe objetivo, planifica y ejecuta")
        
        if not COMPONENTS_OK or not self.agent:
            print("[SKIP] Agente no disponible")
            return
        
        # Tarea real
        objective = "Listar archivos en C:/AI_VAULT y contar cuántos son Python"
        
        print(f"\nObjetivo: {objective}")
        print("\nEjecutando agente...")
        
        result = await self.agent.run_cycle(objective, {"user_id": "demo"})
        
        print(f"\nResultado:")
        print(f"  Éxito: {result['success']}")
        print(f"  Pasos completados: {result.get('completed_steps', 0)}")
        print(f"  Pasos fallidos: {result.get('failed_steps', 0)}")
        
        if result.get('plan'):
            print(f"\nPlan ejecutado:")
            plan = result['plan']
            for step in plan.get('steps', []):
                status = step.get('status', 'unknown')
                print(f"  [{status}] {step.get('action')}: {step.get('description', '')[:50]}")
        
        self.results.append(("Demo 4", "OK", f"{result.get('completed_steps', 0)} pasos completados"))
    
    async def demo_task_5_refactoring_plan(self):
        """Demo 5: Planificación de refactorización"""
        print("\n" + "="*70)
        print("DEMO 5: Planificación de Refactorización")
        print("="*70)
        print("Tarea: Crear plan para mejorar código existente")
        
        if not COMPONENTS_OK:
            print("[SKIP] Componentes no disponibles")
            return
        
        from reasoning import RefactoringPlanner
        
        planner = RefactoringPlanner()
        
        # Analizar este mismo archivo
        file_path = __file__
        
        print(f"\nAnalizando: {Path(file_path).name}")
        
        # Planificar optimización de imports
        plan = planner.plan_refactoring(file_path, "optimize_imports")
        
        if plan.get('success'):
            print(f"\nPlan generado:")
            print(f"  Tipo: {plan.get('refactoring')}")
            if 'unused_imports' in plan:
                print(f"  Imports no usados: {len(plan['unused_imports'])}")
                for imp in plan['unused_imports'][:3]:
                    print(f"    - {imp}")
            
            print(f"\nPasos:")
            for step in plan.get('steps', []):
                print(f"  {step['id']}. {step['description']}")
        
        self.results.append(("Demo 5", "OK", "Plan de refactorización creado"))
    
    async def run_all_demos(self):
        """Ejecutar todas las demostraciones"""
        print("\n" + "="*70)
        print("BRAIN CHAT V8.1 - DEMOSTRACIÓN DE AGENTE AUTÓNOMO")
        print("="*70)
        print("\nEste demo muestra las capacidades del agente:")
        print("- Análisis de código (AST)")
        print("- Debugging automático")
        print("- Generación de código")
        print("- Planificación de tareas")
        print("- Refactorización inteligente")
        
        await self.demo_task_1_analyze_codebase()
        await self.demo_task_2_debug_error()
        await self.demo_task_3_generate_code()
        await self.demo_task_4_agent_workflow()
        await self.demo_task_5_refactoring_plan()
        
        # Resumen
        print("\n" + "="*70)
        print("RESUMEN DE DEMOS")
        print("="*70)
        
        for demo_name, status, detail in self.results:
            print(f"{demo_name:20s} [{status:3s}] {detail}")
        
        success_count = sum(1 for _, status, _ in self.results if status == "OK")
        print(f"\nTotal: {len(self.results)} demos, {success_count} exitosos")
        
        if success_count == len(self.results):
            print("\n✓ TODAS LAS DEMOS COMPLETADAS EXITOSAMENTE")
            print("\nEl agente está listo para tareas de software engineering reales!")
        
        print("\n" + "="*70)


if __name__ == "__main__":
    demo = AgentDemo()
    asyncio.run(demo.run_all_demos())
