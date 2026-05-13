#!/usr/bin/env python3
"""
Brain Agent V8 - Version Final Integrada
Fases 0-5 Completas: Agente Autonomo + Brain Lab Integration
"""

import asyncio
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# Configuracion
PORT = 8090
BASE_DIR = Path("C:/AI_VAULT")

# Importar modulos propios
sys.path.insert(0, str(Path(__file__).parent))

try:
    from agent_core import AgentLoop, Plan, Step
    from tools_advanced import ASTAnalyzer, AdvancedSearch
    from reasoning import DebugReasoner, CodeGenerator, RefactoringPlanner
    from verification import SyntaxVerifier, ChangeVerifier
    from brain_lab_integration import BrainLabConnector, RSIManager, DashboardReporter
    ALL_MODULES_AVAILABLE = True
except ImportError as e:
    print(f"[WARNING] Algunos modulos no disponibles: {e}")
    ALL_MODULES_AVAILABLE = False


class BrainAgentV8Final:
    """
    Agente Autonomo Final V8
    Integra todas las capacidades: Core, Tools, Reasoning, Verification, Brain Lab
    """
    
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.start_time = datetime.now()
        self.conversation_count = 0
        self.memory = []
        
        # Inicializar componentes
        self.agent = AgentLoop(session_id) if ALL_MODULES_AVAILABLE else None
        self.ast_analyzer = ASTAnalyzer() if ALL_MODULES_AVAILABLE else None
        self.searcher = AdvancedSearch() if ALL_MODULES_AVAILABLE else None
        self.debugger = DebugReasoner() if ALL_MODULES_AVAILABLE else None
        self.generator = CodeGenerator() if ALL_MODULES_AVAILABLE else None
        self.verifier = SyntaxVerifier() if ALL_MODULES_AVAILABLE else None
        self.brain_connector = BrainLabConnector() if ALL_MODULES_AVAILABLE else None
        self.rsi_manager = RSIManager() if ALL_MODULES_AVAILABLE else None
        self.reporter = DashboardReporter() if ALL_MODULES_AVAILABLE else None
        
        print(f"[BrainAgentV8] Inicializado - Modulos: {'OK' if ALL_MODULES_AVAILABLE else 'PARCIAL'}")
    
    def detect_intent(self, message: str) -> Tuple[str, float]:
        """Detecta intencion del usuario"""
        msg_lower = message.lower().strip()
        
        # Intenciones de agente autonomo
        if any(kw in msg_lower for kw in ['agente', 'planifica', 'ejecuta plan']):
            return "AGENT", 0.95
        elif any(kw in msg_lower for kw in ['debug', 'error', 'falla', 'bug']):
            return "DEBUG", 0.90
        elif any(kw in msg_lower for kw in ['genera', 'crea funcion', 'crea clase']):
            return "GENERATE", 0.90
        elif any(kw in msg_lower for kw in ['refactoriza', 'mejora codigo']):
            return "REFACTOR", 0.88
        elif any(kw in msg_lower for kw in ['analiza', 'revisa', 'examina']):
            return "ANALYSIS", 0.88
        elif any(kw in msg_lower for kw in ['busca', 'grep', 'find']):
            return "SEARCH", 0.90
        elif any(kw in msg_lower for kw in ['verifica', 'valida', 'testea']):
            return "VERIFY", 0.90
        elif any(kw in msg_lower for kw in ['rsi', 'brechas', 'estado sistema']):
            return "RSI", 0.95
        elif any(kw in msg_lower for kw in ['ejecuta', 'run', 'comando']):
            return "COMMAND", 0.95
        elif any(kw in msg_lower for kw in ['lista', 'dir', 'muestra']):
            return "QUERY", 0.85
        else:
            return "CONVERSATION", 0.60
    
    async def process_message(self, message: str, user_id: str = "anonymous") -> Dict:
        """
        Procesa mensaje del usuario con todas las capacidades
        """
        start_time = datetime.now()
        self.conversation_count += 1
        
        intent, confidence = self.detect_intent(message)
        self.memory.append({
            "role": "user",
            "content": message,
            "intent": intent,
            "timestamp": datetime.now().isoformat()
        })
        
        print(f"[BrainAgentV8] Procesando: {message[:60]}... | Intent: {intent}")
        
        # Manejar intenciones especificas
        try:
            if intent == "AGENT" and self.agent:
                return await self._handle_agent_task(message, user_id)
            elif intent == "DEBUG" and self.debugger:
                return await self._handle_debug(message)
            elif intent == "GENERATE" and self.generator:
                return await self._handle_generate(message)
            elif intent == "REFACTOR" and ALL_MODULES_AVAILABLE:
                return await self._handle_refactor(message)
            elif intent == "ANALYSIS" and self.ast_analyzer:
                return await self._handle_analysis(message)
            elif intent == "SEARCH" and self.searcher:
                return await self._handle_search(message)
            elif intent == "VERIFY" and self.verifier:
                return await self._handle_verify(message)
            elif intent == "RSI" and self.rsi_manager:
                return await self._handle_rsi()
            elif intent == "COMMAND":
                return await self._handle_command(message)
            elif intent == "QUERY":
                return await self._handle_query(message)
            else:
                return await self._handle_conversation(message)
                
        except Exception as e:
            print(f"[ERROR] {e}")
            return {
                "success": False,
                "message": f"Error procesando solicitud: {str(e)}",
                "error": str(e),
                "metadata": {"intent": intent}
            }
    
    async def _handle_agent_task(self, message: str, user_id: str) -> Dict:
        """Maneja tarea de agente autonomo"""
        result = await self.agent.run_cycle(message, {"user_id": user_id})
        
        # Reportar al dashboard
        if self.reporter:
            self.reporter.report_agent_activity("autonomous_task", {
                "objective": message,
                "success": result.get("success"),
                "steps": result.get("completed_steps", 0)
            })
        
        return {
            "success": True,
            "message": f"Agente ejecuto tarea:\n{json.dumps(result, indent=2)[:1500]}",
            "metadata": {"tool": "agent_loop", "result": result}
        }
    
    async def _handle_debug(self, message: str) -> Dict:
        """Maneja solicitud de debug"""
        # Extraer error del mensaje
        lines = message.split('\n')
        error_line = lines[0] if lines else message
        
        result = self.debugger.analyze_error(error_line, "", "")
        
        response = f"Analisis de Error:\n"
        response += f"Causa raiz: {result.root_cause}\n\n"
        response += f"Hipotesis ({len(result.hypotheses)}):\n"
        for i, hyp in enumerate(result.hypotheses[:3], 1):
            response += f"  {i}. [{hyp.confidence:.0%}] {hyp.description}\n"
        
        return {"success": True, "message": response, "metadata": {"tool": "debugger"}}
    
    async def _handle_generate(self, message: str) -> Dict:
        """Maneja generacion de codigo"""
        # Extraer tipo y nombre
        if "funcion" in message.lower():
            code = self.generator.generate_function(
                "generated_func",
                "Funcion generada automaticamente",
                [{"name": "param1", "type": "Any"}],
                "Any"
            )
        elif "clase" in message.lower():
            code = self.generator.generate_class(
                "GeneratedClass",
                "Clase generada automaticamente",
                [],
                []
            )
        else:
            code = "# Especifica 'funcion' o 'clase' en tu mensaje"
        
        # Verificar sintaxis
        verify_result = self.verifier.verify_code_snippet(code)
        
        response = f"Codigo generado:\n```python\n{code}\n```\n"
        response += f"Sintaxis: {'Valida' if verify_result['success'] else 'Invalida'}"
        
        return {"success": True, "message": response, "metadata": {"tool": "code_generator"}}
    
    async def _handle_refactor(self, message: str) -> Dict:
        """Maneja refactorizacion"""
        # Extraer archivo
        match = re.search(r'(?:archivo|file)\s+(\S+\.py)', message, re.IGNORECASE)
        if match:
            file_path = match.group(1)
            planner = RefactoringPlanner()
            plan = planner.plan_refactoring(file_path, "optimize_imports")
            
            response = f"Plan de refactorizacion para {file_path}:\n"
            if plan.get('success'):
                for step in plan.get('steps', []):
                    response += f"  - {step['description']}\n"
            else:
                response += f"Error: {plan.get('error')}"
            
            return {"success": plan.get('success', False), "message": response}
        else:
            return {"success": False, "message": "Especifica archivo .py para refactorizar"}
    
    async def _handle_analysis(self, message: str) -> Dict:
        """Maneja analisis de codigo"""
        match = re.search(r'(?:archivo|file)\s+(\S+\.py)', message, re.IGNORECASE)
        if match:
            file_path = match.group(1)
            if Path(file_path).exists():
                result = self.ast_analyzer.analyze_file(file_path)
                
                response = f"Analisis de {file_path}:\n"
                response += f"  Lineas: {result.total_lines}\n"
                response += f"  Funciones: {len(result.functions)}\n"
                response += f"  Clases: {len(result.classes)}\n"
                response += f"  Complejidad: {result.complexity_score}\n"
                
                if result.functions:
                    response += "\nFunciones principales:\n"
                    for func in result.functions[:5]:
                        response += f"  - {func.name} (linea {func.line_start})\n"
                
                return {"success": True, "message": response}
            else:
                return {"success": False, "message": f"Archivo no encontrado: {file_path}"}
        else:
            return {"success": False, "message": "Especifica archivo .py para analizar"}
    
    async def _handle_search(self, message: str) -> Dict:
        """Maneja busqueda en codebase"""
        match = re.search(r'busca\s+(\S+)', message, re.IGNORECASE)
        if match:
            pattern = match.group(1)
            results = self.searcher.grep(pattern, str(BASE_DIR))
            
            response = f"Busqueda '{pattern}': {len(results)} resultados\n"
            for i, r in enumerate(results[:10], 1):
                response += f"{i}. {r['file']}:{r['line']}: {r['content'][:60]}\n"
            
            return {"success": True, "message": response}
        else:
            return {"success": False, "message": "Especifica patron de busqueda"}
    
    async def _handle_verify(self, message: str) -> Dict:
        """Maneja verificacion"""
        match = re.search(r'verifica\s+(\S+\.py)', message, re.IGNORECASE)
        if match:
            file_path = match.group(1)
            if Path(file_path).exists():
                result = self.verifier.verify_file(file_path)
                
                response = f"Verificacion de {file_path}:\n"
                response += f"Sintaxis valida: {result['syntax_valid']}\n"
                if result.get('errors'):
                    response += f"Errores: {len(result['errors'])}\n"
                    for err in result['errors'][:3]:
                        response += f"  - {err}\n"
                
                return {"success": result['success'], "message": response}
            else:
                return {"success": False, "message": f"Archivo no encontrado: {file_path}"}
        else:
            return {"success": False, "message": "Especifica archivo .py para verificar"}
    
    async def _handle_rsi(self) -> Dict:
        """Maneja consulta RSI"""
        status = self.brain_connector.get_full_status()
        breaches = self.rsi_manager.analyze_and_prioritize()
        
        response = "Estado Brain Lab:\n"
        response += f"Dashboard: {'ONLINE' if status['services']['dashboard']['success'] else 'OFFLINE'}\n"
        response += f"API: {'ONLINE' if status['services']['api']['success'] else 'OFFLINE'}\n"
        response += f"RSI: {'ONLINE' if status['services']['rsi']['success'] else 'OFFLINE'}\n"
        response += f"Salud: {status['summary']['health_percentage']:.0f}%\n\n"
        response += f"Brechas activas: {len(breaches)}\n"
        
        return {"success": True, "message": response}
    
    async def _handle_command(self, message: str) -> Dict:
        """Maneja comando del sistema"""
        match = re.search(r'(?:ejecuta|run|comando)\s*:?\s*(.+)', message, re.IGNORECASE)
        if match:
            cmd = match.group(1).strip()
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, 
                                       text=True, timeout=10, cwd=str(BASE_DIR))
                
                response = f"Comando: {cmd}\n"
                response += f"Salida:\n{result.stdout[:1000]}\n"
                if result.stderr:
                    response += f"Errores:\n{result.stderr[:500]}\n"
                response += f"Codigo retorno: {result.returncode}"
                
                return {"success": result.returncode == 0, "message": response}
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "Timeout (10s)"}
            except Exception as e:
                return {"success": False, "message": f"Error: {e}"}
        else:
            return {"success": False, "message": "Especifica comando a ejecutar"}
    
    async def _handle_query(self, message: str) -> Dict:
        """Maneja consulta de directorio"""
        match = re.search(r'(?:lista|dir)\s+(?:directorio|folder)?\s*:?\s*([A-Z]:[/\\]\S*)', 
                         message, re.IGNORECASE)
        if match:
            path = match.group(1).replace('/', '\\')
            dir_path = Path(path)
            if dir_path.exists():
                files = [f.name for f in dir_path.iterdir() if f.is_file()]
                dirs = [d.name for d in dir_path.iterdir() if d.is_dir()]
                
                response = f"Directorio: {path}\n"
                response += f"Archivos: {len(files)}\n"
                response += f"Directorios: {len(dirs)}\n\n"
                response += "Primeros 20 archivos:\n"
                for f in files[:20]:
                    response += f"  📄 {f}\n"
                
                return {"success": True, "message": response}
            else:
                return {"success": False, "message": f"Directorio no encontrado: {path}"}
        else:
            # Default a AI_VAULT
            return await self._handle_query(f"lista {BASE_DIR}")
    
    async def _handle_conversation(self, message: str) -> Dict:
        """Maneja conversacion general"""
        response = f"Entendido: '{message[:50]}...'\n\n"
        response += "Soy Brain Agent V8 con capacidades:\n"
        response += "- Analisis de codigo (AST)\n"
        response += "- Busqueda (grep/glob)\n"
        response += "- Debugging automatico\n"
        response += "- Generacion de codigo\n"
        response += "- Refactorizacion\n"
        response += "- Verificacion de cambios\n"
        response += "- Integracion Brain Lab\n\n"
        response += "Prueba: 'analiza archivo.py' o 'busca patron' o 'debug error'"
        
        return {"success": True, "message": response}


# Funcion principal para uso como modulo
async def process_agent_request(message: str, user_id: str = "anonymous") -> Dict:
    """Procesa solicitud al agente"""
    agent = BrainAgentV8Final()
    return await agent.process_message(message, user_id)


if __name__ == "__main__":
    # Test
    print("=" * 70)
    print("Brain Agent V8 - Version Final")
    print("=" * 70)
    
    async def test():
        agent = BrainAgentV8Final("test_session")
        
        # Test 1: Analisis
        print("\nTest 1: Analisis de codigo")
        result = await agent.process_message("analiza agent_core.py")
        print(f"Resultado: {result['message'][:200]}...")
        
        # Test 2: Busqueda
        print("\nTest 2: Busqueda")
        result = await agent.process_message("busca class AgentLoop")
        print(f"Encontrados: {len(result['message'])} chars")
        
        # Test 3: RSI
        print("\nTest 3: Estado RSI")
        result = await agent.process_message("rsi")
        print(result['message'])
    
    asyncio.run(test())
    
    print("\n" + "=" * 70)
    print("Test completado")
    print("=" * 70)
