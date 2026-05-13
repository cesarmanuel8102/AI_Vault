"""
Fase 1: Agent Core - Núcleo del Agente Autónomo
Implementa el ciclo fundamental: Observe → Reason → Act → Verify
"""

import json
import os
import sys
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
import urllib.request
import urllib.error

# Añadir path para imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from brain_chat_v8_ui import BrainChatV8
    BRAIN_CHAT_AVAILABLE = True
except ImportError as e:
    print(f"[WARNING] No se pudo importar BrainChatV8: {e}")
    BrainChatV8 = None
    BRAIN_CHAT_AVAILABLE = False


class StepStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Observation:
    """Observación del estado actual"""
    timestamp: str
    context: Dict[str, Any]
    user_input: str = ""
    system_state: Dict = field(default_factory=dict)
    previous_actions: List = field(default_factory=list)
    errors: List = field(default_factory=list)


@dataclass
class Step:
    """Paso individual de un plan"""
    id: int
    action: str
    params: Dict[str, Any]
    description: str
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    verification: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "action": self.action,
            "params": self.params,
            "description": self.description,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "verification": self.verification
        }


@dataclass
class Plan:
    """Plan de ejecución"""
    objective: str
    steps: List[Step]
    created_at: str
    current_step: int = 0
    status: str = "pending"
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "objective": self.objective,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "current_step": self.current_step,
            "status": self.status,
            "metadata": self.metadata
        }


class LLMReasoner:
    """Razonador usando LLM local (Ollama)"""
    
    def __init__(self, model: str = "qwen2.5:14b", timeout: int = 30):
        self.model = model
        self.timeout = timeout
        self.ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
    
    async def generate_plan(self, objective: str, context: Dict) -> Plan:
        """Genera un plan a partir de un objetivo"""
        
        prompt = f"""Eres un agente de software engineering diseñado para operar en C:\\AI_VAULT.
Tu tarea es descomponer objetivos en pasos ejecutables.

CONTEXTO DEL SISTEMA:
- Trabajas en C:\\AI_VAULT\00_identity\chat_brain_v7
- Herramientas disponibles: read_file, write_file, edit_file, search_files, execute_command, analyze_code, list_directory
- Eres Brain Chat V8.0, parte del sistema AI_VAULT
- Puedes ejecutar comandos shell, leer/escribir archivos, analizar código

OBJETIVO DEL USUARIO: {objective}

ESTADO ACTUAL DEL SISTEMA:
{json.dumps(context.get('system_state', {}), indent=2)}

Genera un plan JSON con pasos específicos. Cada paso debe:
1. Ser atómico (una sola acción)
2. Ser verificable (cómo sé que se completó)
3. Tener manejo de errores
4. Incluir parámetros específicos

Responde SOLO con un JSON válido en este formato exacto:
{{
  "objective": "descripción corta",
  "steps": [
    {{
      "id": 1,
      "action": "nombre_herramienta",
      "params": {{"param1": "valor1"}},
      "description": "qué hacer",
      "verification": "cómo verificar"
    }}
  ],
  "metadata": {{"estimated_time": "tiempo estimado"}}
}}

Plan:"""
        
        try:
            # Llamar a Ollama
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 1500
                }
            }
            
            req = urllib.request.Request(
                self.ollama_url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode())
                response_text = result.get("response", "")
                
                # Extraer JSON de la respuesta
                try:
                    # Buscar JSON en la respuesta
                    start_idx = response_text.find("{")
                    end_idx = response_text.rfind("}")
                    if start_idx != -1 and end_idx != -1:
                        json_str = response_text[start_idx:end_idx+1]
                        plan_data = json.loads(json_str)
                    else:
                        # Fallback: retornar plan simple directamente
                        return self._create_simple_plan(objective)
                    
                    # Convertir a objeto Plan
                    steps = []
                    for step_data in plan_data.get("steps", []):
                        steps.append(Step(
                            id=step_data.get("id", 1),
                            action=step_data.get("action", "unknown"),
                            params=step_data.get("params", {}),
                            description=step_data.get("description", "Sin descripcion"),
                            verification=step_data.get("verification", "Manual verification")
                        ))
                    
                    return Plan(
                        objective=plan_data.get("objective", objective),
                        steps=steps,
                        created_at=datetime.now().isoformat(),
                        metadata=plan_data.get("metadata", {})
                    )
                    
                except json.JSONDecodeError as e:
                    print(f"[ERROR] No se pudo parsear JSON del LLM: {e}")
                    return self._create_simple_plan(objective)
                    
        except Exception as e:
            print(f"[ERROR] LLM no responde: {e}")
            return self._create_simple_plan(objective)
    
    def _create_simple_plan(self, objective: str) -> Plan:
        """Crea un plan simple cuando el LLM falla"""
        return Plan(
            objective=objective,
            steps=[
                Step(
                    id=1,
                    action="execute_command",
                    params={"command": f"echo 'Procesando: {objective}'"},
                    description=f"Procesar objetivo: {objective}",
                    verification="Comando ejecuta sin error"
                )
            ],
            created_at=datetime.now().isoformat()
        )


class ExecutionMemory:
    """Memoria de ejecución para mantener contexto entre pasos"""
    
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.variables: Dict[str, Any] = {}
        self.history: List[Dict] = []
        self.current_plan: Optional[Plan] = None
    
    def set(self, key: str, value: Any):
        """Guarda una variable"""
        self.variables[key] = value
        self._log("set", {"key": key, "value_type": type(value).__name__})
    
    def get(self, key: str, default=None) -> Any:
        """Recupera una variable"""
        return self.variables.get(key, default)
    
    def set_plan(self, plan: Plan):
        """Establece el plan actual"""
        self.current_plan = plan
        self._log("plan_set", {"objective": plan.objective, "steps_count": len(plan.steps)})
    
    def get_plan(self) -> Optional[Plan]:
        """Obtiene el plan actual"""
        return self.current_plan
    
    def log_step_result(self, step_id: int, result: Any, error: Optional[str] = None):
        """Registra el resultado de un paso"""
        self._log("step_result", {
            "step_id": step_id,
            "success": error is None,
            "error": error
        })
    
    def _log(self, event_type: str, data: Dict):
        """Registra un evento"""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "data": data
        })
    
    def save_to_disk(self, path: Optional[str] = None):
        """Guarda memoria a disco"""
        if path is None:
            path = f"C:\\AI_VAULT\\tmp_agent\\state\\memory\\agent_{self.session_id}.json"
        
        try:
            data = {
                "session_id": self.session_id,
                "variables": self.variables,
                "history": self.history,
                "current_plan": self.current_plan.to_dict() if self.current_plan else None,
                "saved_at": datetime.now().isoformat()
            }
            
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"[ERROR] No se pudo guardar memoria: {e}")
    
    def load_from_disk(self, path: Optional[str] = None):
        """Carga memoria desde disco"""
        if path is None:
            path = f"C:\\AI_VAULT\\tmp_agent\\state\\memory\\agent_{self.session_id}.json"
        
        try:
            if Path(path).exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.variables = data.get("variables", {})
                    self.history = data.get("history", [])
                    # Restaurar plan si existe
                    plan_data = data.get("current_plan")
                    if plan_data:
                        # Reconstruir Plan object
                        pass
        except Exception as e:
            print(f"[WARNING] No se pudo cargar memoria: {e}")


class AgentLoop:
    """
    Núcleo del agente autónomo
    Implementa: Observe → Reason → Act → Verify
    """
    
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.memory = ExecutionMemory(session_id)
        self.reasoner = LLMReasoner()
        self.brain_chat = None
        if BrainChatV8:
            self.brain_chat = BrainChatV8()
        
        self.is_running = False
        self.current_step = 0
    
    async def observe(self, context: Dict) -> Observation:
        """
        OBSERVE: Recolecta información del estado actual
        """
        observation = Observation(
            timestamp=datetime.now().isoformat(),
            context=context,
            user_input=context.get("message", "") if context.get("message") else "Objetivo sin especificar",
            system_state={
                "session_id": self.session_id,
                "current_step": self.current_step,
                "variables": len(self.memory.variables),
                "has_plan": self.memory.current_plan is not None
            },
            previous_actions=self.memory.history[-5:] if self.memory.history else [],
            errors=[]
        )
        
        print(f"[AGENT] Observation: {len(self.memory.variables)} variables, plan={observation.system_state['has_plan']}")
        return observation
    
    async def reason(self, observation: Observation) -> Plan:
        """
        REASON: Genera un plan basado en observaciones
        """
        print(f"[AGENT] Reasoning about: {observation.user_input}")
        
        # Usar LLM para generar plan
        plan = await self.reasoner.generate_plan(
            observation.user_input,
            {"system_state": observation.system_state}
        )
        
        # Guardar en memoria
        self.memory.set_plan(plan)
        
        print(f"[AGENT] Plan generated: {len(plan.steps)} steps")
        for step in plan.steps:
            print(f"  [{step.id}] {step.action}: {step.description}")
        
        return plan
    
    async def act(self, step: Step) -> Tuple[bool, Any]:
        """
        ACT: Ejecuta un paso del plan
        """
        print(f"[AGENT] Acting on step {step.id}: {step.action}")
        
        step.started_at = datetime.now().isoformat()
        step.status = StepStatus.IN_PROGRESS
        
        try:
            # Ejecutar acción usando Brain Chat
            if self.brain_chat:
                # Construir mensaje para la herramienta
                if step.action == "execute_command":
                    cmd = step.params.get("command", "")
                    result = await self.brain_chat.execute_tool("execute_command", command=cmd)
                elif step.action == "read_file":
                    path = step.params.get("path", "")
                    result = await self.brain_chat.execute_tool("read_file", file_path=path)
                elif step.action == "write_file":
                    path = step.params.get("path", "")
                    content = step.params.get("content", "")
                    result = await self.brain_chat.execute_tool("write_file", file_path=path, content=content)
                elif step.action == "edit_file":
                    path = step.params.get("path", "")
                    old = step.params.get("old_string", "")
                    new = step.params.get("new_string", "")
                    result = await self.brain_chat.execute_tool("edit_file", file_path=path, old_string=old, new_string=new)
                elif step.action == "list_directory":
                    path = step.params.get("path", "")
                    result = await self.brain_chat.execute_tool("list_directory", path=path)
                elif step.action == "search_files":
                    pattern = step.params.get("pattern", "")
                    path = step.params.get("path", "")
                    result = await self.brain_chat.execute_tool("search_files", pattern=pattern, path=path)
                else:
                    # Herramienta no reconocida
                    result = {"success": False, "error": f"Unknown tool: {step.action}"}
            else:
                # Fallback: simular ejecución
                result = {"success": True, "message": f"Simulated execution of {step.action}"}
            
            # Verificar resultado
            success = result.get("success", False)
            
            if success:
                step.status = StepStatus.COMPLETED
                step.result = result
                step.completed_at = datetime.now().isoformat()
            else:
                step.status = StepStatus.FAILED
                step.error = result.get("error", "Unknown error")
            
            # Guardar en memoria
            self.memory.log_step_result(step.id, result, step.error)
            
            return success, result
            
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            self.memory.log_step_result(step.id, None, str(e))
            return False, {"error": str(e)}
    
    async def verify(self, step: Step) -> bool:
        """
        VERIFY: Verifica que el paso se completó correctamente
        """
        print(f"[AGENT] Verifying step {step.id}")
        
        # Verificación básica: el paso debe estar completado
        if step.status != StepStatus.COMPLETED:
            return False
        
        # Verificación adicional basada en el tipo de paso
        if step.action == "execute_command":
            # Verificar que no hubo errores en stderr
            result = step.result or {}
            if result.get("stderr"):
                # Si hay stderr, verificar si es crítico
                return result.get("returncode", 1) == 0
        
        return True
    
    async def run_cycle(self, task: str, context: Optional[Dict] = None) -> Dict:
        """
        Ejecuta un ciclo completo del agente
        """
        print(f"\n{'='*60}")
        print(f"AGENT CYCLE STARTED")
        print(f"Task: {task}")
        print(f"{'='*60}\n")
        
        self.is_running = True
        results = []
        
        try:
            # 1. OBSERVE
            if context is None:
                context = {"message": task}
            observation = await self.observe(context)
            
            # 2. REASON
            plan = await self.reason(observation)
            
            # 3. ACT (para cada paso)
            for i, step in enumerate(plan.steps):
                if not self.is_running:
                    break
                
                print(f"\n[AGENT] Executing step {i+1}/{len(plan.steps)}")
                success, result = await self.act(step)
                results.append({
                    "step_id": step.id,
                    "action": step.action,
                    "success": success,
                    "result": result
                })
                
                if not success:
                    print(f"[AGENT] Step {step.id} failed: {step.error}")
                    # Continuar con el siguiente paso o detener según política
                
                # 4. VERIFY
                verified = await self.verify(step)
                print(f"[AGENT] Step {step.id} verified: {verified}")
            
            # Guardar memoria
            self.memory.save_to_disk()
            
            return {
                "success": True,
                "plan": plan.to_dict(),
                "results": results,
                "completed_steps": len([r for r in results if r["success"]]),
                "failed_steps": len([r for r in results if not r["success"]])
            }
            
        except Exception as e:
            print(f"[AGENT] Cycle failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": results
            }
        finally:
            self.is_running = False
            print(f"\n{'='*60}")
            print(f"AGENT CYCLE COMPLETED")
            print(f"{'='*60}\n")


# Exportar clases principales
__all__ = [
    'AgentLoop',
    'Plan',
    'Step',
    'StepStatus',
    'Observation',
    'LLMReasoner',
    'ExecutionMemory'
]


if __name__ == "__main__":
    # Test básico del agente
    print("Testing Agent Loop...")
    
    async def test():
        agent = AgentLoop("test_session")
        result = await agent.run_cycle("Crea un archivo de test en C:/AI_VAULT/tmp_agent/test_output.txt con el texto 'Agent test successful'")
        print(f"\nResult: {json.dumps(result, indent=2)}")
    
    asyncio.run(test())
