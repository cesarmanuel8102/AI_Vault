"""
TEACHING_INTERFACE.PY
Sistema de Teaching Loop para Brain Chat V9

Implementa la metodología de:
- Ingesta de información
- Prueba y validación
- Resultados y evaluación
- Mejora iterativa
- Checkpoint validation

Integración: Chat modo agente + Dashboard
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
import uuid

from brain.meta_cognition_core import MetaCognitionCore, initialize_enhanced_consciousness


# ─── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
TEACHING_STATE_PATH = Path("C:/AI_VAULT/tmp_agent/state/teaching")
TEACHING_STATE_PATH.mkdir(parents=True, exist_ok=True)

SESSIONS_FILE = TEACHING_STATE_PATH / "sessions.json"
PROGRESS_FILE = TEACHING_STATE_PATH / "progress.json"
VALIDATION_RESULTS_FILE = TEACHING_STATE_PATH / "validation_results.json"


# ─── ESTRUCTURAS DE TEACHING ───────────────────────────────────────────────────
@dataclass
class LearningObjective:
    """Objetivo de aprendizaje específico"""
    objective_id: str
    description: str
    domain: str
    difficulty: float  # 0.0 - 1.0
    prerequisites: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, completed, failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    validation_results: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TeachingSession:
    """Sesión de enseñanza completa"""
    session_id: str
    created_at: str
    updated_at: str
    
    # Fases de teaching loop
    phase: str = "ingesta"  # ingesta, prueba, resultados, evaluacion, mejora
    phase_status: str = "active"  # active, completed, blocked
    
    # Objetivos de la sesión
    objectives: List[LearningObjective] = field(default_factory=list)
    current_objective_index: int = 0
    
    # Progreso
    completion_percentage: float = 0.0
    validation_passed: bool = False
    
    # Checkpoint
    checkpoint_data: Dict[str, Any] = field(default_factory=dict)
    can_rollback: bool = False
    
    # Métricas
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    
    # Notas del mentor
    mentor_notes: List[str] = field(default_factory=list)
    
    # Estado para UI
    chat_messages: List[Dict[str, Any]] = field(default_factory=list)
    dashboard_state: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class ValidationCheckpoint:
    """Punto de validación del aprendizaje"""
    checkpoint_id: str
    session_id: str
    phase: str
    criteria: List[str]
    results: Dict[str, Any] = field(default_factory=dict)
    passed: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    requires_human_approval: bool = True
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


# ─── NÚCLEO DE TEACHING LOOP ────────────────────────────────────────────────────
class TeachingInterface:
    """
    Interfaz de Teaching Loop para Brain Chat V9
    
    Implementa metodología iterativa:
    1. INGESTA: Recibir información/teoría
    2. PRUEBA: Ejercitar/aplicar
    3. RESULTADOS: Obtener outcome
    4. EVALUACIÓN: Analizar vs criterios
    5. MEJORA: Iterar o avanzar
    
    Integra con MetaCognitionCore para tracking de aprendizaje
    """
    
    def __init__(self):
        self.meta_cognition: MetaCognitionCore = initialize_enhanced_consciousness()
        self.current_session: Optional[TeachingSession] = None
        self.sessions_history: List[TeachingSession] = self._load_sessions()
        self.validation_results: Dict[str, Any] = self._load_validation_results()
        
    def _load_sessions(self) -> List[TeachingSession]:
        """Carga historial de sesiones"""
        if SESSIONS_FILE.exists():
            try:
                with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [self._dict_to_session(s) for s in data.get("sessions", [])]
            except Exception as e:
                print(f"[Teaching] Error cargando sesiones: {e}")
        return []
    
    def _load_validation_results(self) -> Dict[str, Any]:
        """Carga resultados de validación"""
        if VALIDATION_RESULTS_FILE.exists():
            try:
                with open(VALIDATION_RESULTS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def _dict_to_session(self, data: Dict) -> TeachingSession:
        """Convierte dict a TeachingSession"""
        objectives = [LearningObjective(**o) for o in data.get("objectives", [])]
        return TeachingSession(
            session_id=data["session_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            phase=data.get("phase", "ingesta"),
            phase_status=data.get("phase_status", "active"),
            objectives=objectives,
            current_objective_index=data.get("current_objective_index", 0),
            completion_percentage=data.get("completion_percentage", 0.0),
            validation_passed=data.get("validation_passed", False),
            checkpoint_data=data.get("checkpoint_data", {}),
            can_rollback=data.get("can_rollback", False),
            attempts=data.get("attempts", 0),
            successes=data.get("successes", 0),
            failures=data.get("failures", 0),
            mentor_notes=data.get("mentor_notes", []),
            chat_messages=data.get("chat_messages", []),
            dashboard_state=data.get("dashboard_state", {}),
        )
    
    def save_sessions(self):
        """Persiste sesiones"""
        data = {
            "last_updated": datetime.now().isoformat(),
            "sessions": [asdict(s) for s in self.sessions_history[-50:]],  # Últimas 50
        }
        with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def save_validation_results(self):
        """Persiste resultados de validación"""
        with open(VALIDATION_RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.validation_results, f, indent=2, ensure_ascii=False)
    
    # ─── INICIO DE SESIÓN ────────────────────────────────────────────────────────
    
    def create_teaching_session(self, topic: str, objectives: List[str] = None) -> TeachingSession:
        """
        Crea nueva sesión de enseñanza
        
        Args:
            topic: Tema principal a aprender
            objectives: Lista de objetivos específicos
        """
        session_id = f"teach_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        
        # Crear objetivos por defecto si no se especifican
        if not objectives:
            objectives = [f"Comprender conceptos fundamentales de {topic}"]
        
        learning_objectives = []
        for idx, obj_desc in enumerate(objectives):
            learning_objectives.append(LearningObjective(
                objective_id=f"obj_{session_id}_{idx}",
                description=obj_desc,
                domain=topic,
                difficulty=0.5,  # Inicialmente neutral
                prerequisites=[] if idx == 0 else [objectives[idx-1]],
                success_criteria=["Puede explicar el concepto", "Puede aplicarlo en ejemplo simple"],
            ))
        
        session = TeachingSession(
            session_id=session_id,
            created_at=now,
            updated_at=now,
            phase="ingesta",
            phase_status="active",
            objectives=learning_objectives,
            chat_messages=[{
                "role": "system",
                "content": f"🎓 Sesión de enseñanza iniciada: {topic}\n\nFase actual: INGESTA\nObjetivo: {objectives[0] if objectives else 'Aprendizaje general'}",
                "timestamp": now,
            }],
        )
        
        self.current_session = session
        self.sessions_history.append(session)
        self.save_sessions()
        
        print(f"[Teaching] Sesión creada: {session_id}")
        return session
    
    # ─── FASES DEL TEACHING LOOP ───────────────────────────────────────────────────
    
    def process_ingesta(self, content: str, source: str = "mentor") -> Dict[str, Any]:
        """
        FASE 1: INGESTA
        Recibe y procesa nueva información
        """
        if not self.current_session:
            return {"error": "No active session"}
        
        if self.current_session.phase != "ingesta":
            return {"error": f"Wrong phase. Current: {self.current_session.phase}"}
        
        now = datetime.now().isoformat()
        
        # Registrar mensaje
        self.current_session.chat_messages.append({
            "role": "mentor" if source == "mentor" else "user",
            "content": content,
            "timestamp": now,
            "phase": "ingesta",
        })
        
        # Simular procesamiento de ingesta
        # En implementación real, esto analizaría el contenido
        processing_result = {
            "concepts_identified": content.split()[:5],  # Placeholder
            "complexity_estimate": 0.5,
            "questions_generated": [f"What is {word}?" for word in content.split()[:3]],
        }
        
        # Respuesta del sistema
        response = {
            "status": "ingesting",
            "message": f"📥 Procesando información...\n\nConceptos identificados: {len(processing_result['concepts_identified'])}\nComplejidad estimada: {processing_result['complexity_estimate']:.0%}\n\nPreguntas para validar comprensión:",
            "questions": processing_result["questions_generated"],
            "next_phase": "prueba",
            "can_proceed": True,
        }
        
        self.current_session.chat_messages.append({
            "role": "agent",
            "content": response["message"],
            "timestamp": now,
        })
        
        self._update_session()
        return response
    
    def process_prueba(self, exercise_type: str = "conceptual") -> Dict[str, Any]:
        """
        FASE 2: PRUEBA
        Genera ejercicios para validar comprensión
        """
        if not self.current_session:
            return {"error": "No active session"}
        
        if self.current_session.phase != "prueba":
            # Auto-avanzar si estaba en ingesta
            if self.current_session.phase == "ingesta":
                self.current_session.phase = "prueba"
                self.current_session.phase_status = "active"
            else:
                return {"error": f"Wrong phase. Current: {self.current_session.phase}"}
        
        now = datetime.now().isoformat()
        current_obj = self.current_session.objectives[self.current_session.current_objective_index]
        
        # Generar ejercicio basado en objetivo
        exercise = self._generate_exercise(current_obj, exercise_type)
        
        self.current_session.chat_messages.append({
            "role": "system",
            "content": f"📝 FASE PRUEBA: {exercise['title']}\n\n{exercise['description']}",
            "timestamp": now,
        })
        
        response = {
            "status": "testing",
            "phase": "prueba",
            "exercise": exercise,
            "objective": current_obj.description,
            "instructions": "Responde o realiza la tarea para validar tu comprensión.",
        }
        
        self.current_session.attempts += 1
        self._update_session()
        return response
    
    def _generate_exercise(self, objective: LearningObjective, exercise_type: str) -> Dict[str, Any]:
        """Genera ejercicio basado en objetivo"""
        templates = {
            "conceptual": {
                "title": "Ejercicio de Comprensión Conceptual",
                "description": f"Explica con tus propias palabras: {objective.description}\n\nCriterios:\n- Claridad de explicación\n- Uso correcto de terminología\n- Ejemplos concretos",
                "validation_method": "mentor_review",
            },
            "aplicacion": {
                "title": "Ejercicio de Aplicación",
                "description": f"Aplica el concepto '{objective.description}' en un escenario práctico.",
                "validation_method": "outcome_check",
            },
            "analisis": {
                "title": "Ejercicio de Análisis",
                "description": f"Analiza las implicaciones de: {objective.description}",
                "validation_method": "structured_evaluation",
            },
        }
        
        return templates.get(exercise_type, templates["conceptual"])
    
    def submit_prueba_result(self, attempt_result: str, self_assessment: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Recibe resultado del intento de prueba
        """
        if not self.current_session:
            return {"error": "No active session"}
        
        now = datetime.now().isoformat()
        
        # Registrar intento
        self.current_session.chat_messages.append({
            "role": "user",
            "content": f"[Intento] {attempt_result[:200]}...",
            "timestamp": now,
        })
        
        # Simular evaluación (en realidad usaría criterios definidos)
        # Para MVP, requiere validación humana
        evaluation = {
            "status": "pending_validation",
            "message": "⏳ Resultado enviado. Esperando validación del mentor...",
            "auto_assessment": self_assessment or {},
            "next_phase": "resultados",
        }
        
        self.current_session.phase = "resultados"
        self.current_session.phase_status = "pending_validation"
        
        self.current_session.chat_messages.append({
            "role": "agent",
            "content": evaluation["message"],
            "timestamp": now,
        })
        
        self._update_session()
        return evaluation
    
    def process_resultados(self, validation_outcome: Dict[str, Any]) -> Dict[str, Any]:
        """
        FASE 3: RESULTADOS
        Procesa outcome de la prueba
        """
        if not self.current_session:
            return {"error": "No active session"}
        
        now = datetime.now().isoformat()
        
        passed = validation_outcome.get("passed", False)
        feedback = validation_outcome.get("feedback", "")
        score = validation_outcome.get("score", 0.0)
        
        if passed:
            self.current_session.successes += 1
            status_msg = f"✅ PRUEBA SUPERADA (Score: {score:.0%})"
        else:
            self.current_session.failures += 1
            status_msg = f"❌ PRUEBA NO SUPERADA (Score: {score:.0%})\n\nFeedback: {feedback}"
        
        self.current_session.chat_messages.append({
            "role": "system",
            "content": status_msg,
            "timestamp": now,
        })
        
        # Actualizar objetivo actual
        current_obj = self.current_session.objectives[self.current_session.current_objective_index]
        current_obj.validation_results = validation_outcome
        
        response = {
            "status": "results_processed",
            "passed": passed,
            "score": score,
            "feedback": feedback,
            "next_phase": "evaluacion",
        }
        
        self.current_session.phase = "evaluacion"
        self._update_session()
        return response
    
    def process_evaluacion(self, mentor_evaluation: str = None) -> Dict[str, Any]:
        """
        FASE 4: EVALUACIÓN
        Analiza aprendizaje y determina siguiente paso
        """
        if not self.current_session:
            return {"error": "No active session"}
        
        now = datetime.now().isoformat()
        current_obj = self.current_session.objectives[self.current_session.current_objective_index]
        
        # Determinar si objetivo está completo
        obj_completed = current_obj.validation_results.get("passed", False)
        
        if obj_completed:
            current_obj.status = "completed"
            current_obj.completed_at = now
            
            # Verificar si hay más objetivos
            if self.current_session.current_objective_index < len(self.current_session.objectives) - 1:
                self.current_session.current_objective_index += 1
                next_obj = self.current_session.objectives[self.current_session.current_objective_index]
                
                evaluation_msg = f"📊 EVALUACIÓN: Objetivo completado.\n\nPróximo objetivo: {next_obj.description}\n\n¿Continuar con siguiente objetivo o iterar más en el actual?"
                recommendation = "proceed_to_next"
            else:
                # Todos los objetivos completados
                self.current_session.completion_percentage = 100.0
                evaluation_msg = "🎉 ¡Todos los objetivos completados!\n\nSesión lista para checkpoint final."
                recommendation = "complete_session"
        else:
            current_obj.status = "in_progress"
            evaluation_msg = f"📊 EVALUACIÓN: Se requiere más práctica.\n\nIteración #{self.current_session.attempts + 1} recomendada."
            recommendation = "iterate"
        
        if mentor_evaluation:
            self.current_session.mentor_notes.append(mentor_evaluation)
        
        self.current_session.chat_messages.append({
            "role": "system",
            "content": evaluation_msg,
            "timestamp": now,
        })
        
        response = {
            "status": "evaluated",
            "current_objective_completed": obj_completed,
            "completion_percentage": self.current_session.completion_percentage,
            "recommendation": recommendation,
            "next_phase": "mejora",
        }
        
        self.current_session.phase = "mejora"
        self._update_session()
        return response
    
    def process_mejora(self, action: str = "auto") -> Dict[str, Any]:
        """
        FASE 5: MEJORA
        Itera o avanza según evaluación
        """
        if not self.current_session:
            return {"error": "No active session"}
        
        now = datetime.now().isoformat()
        
        if action == "iterate":
            # Volver a prueba con mismo objetivo
            self.current_session.phase = "prueba"
            self.current_session.phase_status = "active"
            
            msg = "🔄 MEJORA: Preparando nueva iteración de práctica..."
        elif action == "proceed":
            # Avanzar al siguiente objetivo
            self.current_session.phase = "ingesta"
            self.current_session.phase_status = "active"
            
            current_obj = self.current_session.objectives[self.current_session.current_objective_index]
            msg = f"➡️ MEJORA: Avanzando al siguiente objetivo:\n{current_obj.description}"
        elif action == "complete":
            # Finalizar sesión
            self.current_session.phase = "checkpoint"
            self.current_session.phase_status = "pending_validation"
            
            msg = "✅ MEJORA: Sesión completada. Creando checkpoint de validación..."
        else:
            msg = "⚠️ MEJORA: Esperando decisión del mentor (iterate/proceed/complete)"
        
        self.current_session.chat_messages.append({
            "role": "system",
            "content": msg,
            "timestamp": now,
        })
        
        self._update_session()
        return {
            "status": "improvement_phase",
            "action_taken": action,
            "current_phase": self.current_session.phase,
        }
    
    # ─── SISTEMA DE CHECKPOINT ────────────────────────────────────────────────────
    
    def create_checkpoint(self) -> ValidationCheckpoint:
        """
        Crea checkpoint de validación de sesión completa
        """
        if not self.current_session:
            return None
        
        checkpoint_id = f"chk_{uuid.uuid4().hex[:12]}"
        
        # Definir criterios de validación
        criteria = [
            "Todos los objetivos completados",
            "Score promedio > 70%",
            "Feedback del mentor positivo",
            "Sistema puede aplicar conocimiento en nuevo contexto",
        ]
        
        # Calcular resultados
        completed_objs = sum(1 for o in self.current_session.objectives if o.status == "completed")
        total_objs = len(self.current_session.objectives)
        avg_score = sum(o.validation_results.get("score", 0) for o in self.current_session.objectives) / max(1, total_objs)
        
        results = {
            "objectives_completed": completed_objs,
            "total_objectives": total_objs,
            "average_score": avg_score,
            "attempts_total": self.current_session.attempts,
            "success_rate": self.current_session.successes / max(1, self.current_session.attempts),
        }
        
        checkpoint = ValidationCheckpoint(
            checkpoint_id=checkpoint_id,
            session_id=self.current_session.session_id,
            phase="session_completion",
            criteria=criteria,
            results=results,
            passed=False,  # Requiere aprobación humana
            requires_human_approval=True,
        )
        
        self.current_session.checkpoint_data = asdict(checkpoint)
        self.current_session.can_rollback = True
        
        # Guardar en meta_cognition
        self.meta_cognition.create_learning_checkpoint(
            phase=f"teaching_session_{self.current_session.session_id}",
            validation_results=results,
        )
        
        self._update_session()
        self.save_validation_results()
        
        return checkpoint
    
    def approve_checkpoint(self, checkpoint_id: str, approver: str) -> Dict[str, Any]:
        """
        Mentor aprueba checkpoint
        """
        if not self.current_session:
            return {"error": "No active session"}
        
        now = datetime.now().isoformat()
        
        self.current_session.validation_passed = True
        self.current_session.phase_status = "completed"
        
        # Actualizar checkpoint
        if self.current_session.checkpoint_data:
            self.current_session.checkpoint_data["passed"] = True
            self.current_session.checkpoint_data["approved_by"] = approver
            self.current_session.checkpoint_data["approved_at"] = now
        
        self.current_session.chat_messages.append({
            "role": "system",
            "content": f"✅ CHECKPOINT APROBADO por {approver}\n\nConocimiento integrado al sistema. Puede aplicarse en nuevos contextos.",
            "timestamp": now,
        })
        
        self._update_session()
        
        return {
            "status": "checkpoint_approved",
            "checkpoint_id": checkpoint_id,
            "approved_by": approver,
            "knowledge_integrated": True,
        }
    
    def rollback_checkpoint(self) -> Dict[str, Any]:
        """
        Revierte al checkpoint anterior si algo salió mal
        """
        if not self.current_session or not self.current_session.can_rollback:
            return {"error": "No checkpoint available for rollback"}
        
        # Restaurar estado anterior
        self.current_session.phase = "ingesta"
        self.current_session.phase_status = "active"
        self.current_session.current_objective_index = 0
        
        # Resetear objetivos
        for obj in self.current_session.objectives:
            obj.status = "pending"
            obj.validation_results = {}
        
        self.current_session.chat_messages.append({
            "role": "system",
            "content": "⏮️ ROLLBACK ejecutado. Volviendo al inicio de la sesión para re-aprendizaje.",
            "timestamp": datetime.now().isoformat(),
        })
        
        self._update_session()
        
        return {
            "status": "rolled_back",
            "session_reset": True,
            "message": "Sesión reiniciada. Recomendado cambiar enfoque de enseñanza.",
        }
    
    # ─── API PARA CHAT Y DASHBOARD ──────────────────────────────────────────────
    
    def get_chat_state(self) -> Dict[str, Any]:
        """
        Retorna estado actual para el chat
        """
        if not self.current_session:
            return {
                "active": False,
                "message": "No hay sesión activa. Usa /teaching start <tema> para iniciar.",
            }
        
        current_obj = self.current_session.objectives[self.current_session.current_objective_index]
        
        return {
            "active": True,
            "session_id": self.current_session.session_id,
            "phase": self.current_session.phase,
            "phase_status": self.current_session.phase_status,
            "current_objective": current_obj.description,
            "objective_progress": f"{self.current_session.current_objective_index + 1}/{len(self.current_session.objectives)}",
            "completion_percentage": self.current_session.completion_percentage,
            "messages": self.current_session.chat_messages[-10:],  # Últimos 10 mensajes
            "can_rollback": self.current_session.can_rollback,
        }
    
    def get_dashboard_state(self) -> Dict[str, Any]:
        """
        Retorna estado completo para el dashboard
        """
        meta_report = self.meta_cognition.get_self_awareness_report()
        
        if not self.current_session:
            return {
                "meta_cognition": meta_report,
                "teaching_session": None,
                "overall_status": "standby",
            }
        
        # Calcular métricas de progreso
        completed = sum(1 for o in self.current_session.objectives if o.status == "completed")
        total = len(self.current_session.objectives)
        progress = (completed / total * 100) if total > 0 else 0
        
        return {
            "meta_cognition": meta_report,
            "teaching_session": {
                "session_id": self.current_session.session_id,
                "phase": self.current_session.phase,
                "status": self.current_session.phase_status,
                "progress_percentage": progress,
                "objectives_total": total,
                "objectives_completed": completed,
                "attempts": self.current_session.attempts,
                "successes": self.current_session.successes,
                "failures": self.current_session.failures,
                "success_rate": self.current_session.successes / max(1, self.current_session.attempts),
                "mentor_notes_count": len(self.current_session.mentor_notes),
                "can_rollback": self.current_session.can_rollback,
                "validation_pending": self.current_session.phase == "checkpoint",
            },
            "overall_status": "learning" if self.current_session.phase != "checkpoint" else "validation_pending",
        }
    
    def handle_chat_command(self, command: str, args: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Procesa comandos del chat para teaching
        
        Comandos disponibles:
        - /teaching start <tema> [objetivos...]
        - /teaching status
        - /teaching phase <ingesta/prueba/resultados/evaluacion/mejora>
        - /teaching validate <score> <feedback>
        - /teaching checkpoint
        - /teaching approve <checkpoint_id>
        - /teaching rollback
        - /teaching end
        """
        args = args or {}
        
        if command == "start":
            topic = args.get("topic", "Aprendizaje general")
            objectives = args.get("objectives", [])
            session = self.create_teaching_session(topic, objectives)
            return {
                "status": "session_created",
                "session_id": session.session_id,
                "message": f"🎓 Sesión iniciada: {topic}\n\nFase: INGESTA\nEscribe o pega el material de estudio.",
            }
        
        elif command == "status":
            return self.get_chat_state()
        
        elif command == "phase":
            phase = args.get("phase", "")
            if phase == "ingesta":
                content = args.get("content", "")
                return self.process_ingesta(content)
            elif phase == "prueba":
                return self.process_prueba(args.get("type", "conceptual"))
            elif phase == "resultados":
                return self.submit_prueba_result(args.get("result", ""), args.get("self_assessment"))
            elif phase == "evaluacion":
                return self.process_evaluacion(args.get("mentor_notes"))
            elif phase == "mejora":
                return self.process_mejora(args.get("action", "auto"))
        
        elif command == "validate":
            outcome = {
                "passed": args.get("passed", False),
                "score": args.get("score", 0.0),
                "feedback": args.get("feedback", ""),
            }
            return self.process_resultados(outcome)
        
        elif command == "checkpoint":
            checkpoint = self.create_checkpoint()
            return {
                "status": "checkpoint_created",
                "checkpoint_id": checkpoint.checkpoint_id if checkpoint else None,
                "requires_approval": True,
                "message": "Checkpoint creado. Esperando validación del mentor.",
            }
        
        elif command == "approve":
            return self.approve_checkpoint(args.get("checkpoint_id", ""), args.get("approver", "mentor"))
        
        elif command == "rollback":
            return self.rollback_checkpoint()
        
        elif command == "end":
            if self.current_session:
                self.current_session.phase_status = "ended"
                self._update_session()
            return {
                "status": "session_ended",
                "message": "Sesión finalizada. Progreso guardado.",
            }
        
        else:
            return {
                "error": "Unknown command",
                "available_commands": ["start", "status", "phase", "validate", "checkpoint", "approve", "rollback", "end"],
            }
    
    def _update_session(self):
        """Actualiza timestamp y guarda"""
        if self.current_session:
            self.current_session.updated_at = datetime.now().isoformat()
            self.save_sessions()


# ─── FUNCIÓN DE INICIALIZACIÓN ─────────────────────────────────────────────────
def initialize_teaching_system() -> TeachingInterface:
    """Punto de entrada para inicializar sistema de teaching"""
    print("=" * 70)
    print("INICIALIZANDO SISTEMA DE TEACHING LOOP")
    print("=" * 70)
    
    interface = TeachingInterface()
    
    print(f"\nSistema listo.")
    print(f"  - Sesiones previas: {len(interface.sessions_history)}")
    print(f"  - Meta-cognición: Activa")
    print("\nUsa /teaching start <tema> para comenzar.")
    print("=" * 70)
    
    return interface


# Para testing
if __name__ == "__main__":
    teaching = initialize_teaching_system()
    
    # Simular sesión
    print("\n--- Simulando sesión de teaching ---")
    
    # Iniciar
    result = teaching.handle_chat_command("start", {
        "topic": "Causalidad en Trading",
        "objectives": ["Distinguir correlación de causalidad", "Identificar confounders"],
    })
    print(f"\n{result['message']}")
    
    # Ingesta
    result = teaching.handle_chat_command("phase", {
        "phase": "ingesta",
        "content": "La causalidad implica que X causa Y, no solo que están correlacionados...",
    })
    print(f"\n{result['message']}")
    
    # Prueba
    result = teaching.handle_chat_command("phase", {"phase": "prueba"})
    print(f"\nEjercicio: {result['exercise']['title']}")
    
    # Estado del dashboard
    dashboard = teaching.get_dashboard_state()
    print(f"\nDashboard: {dashboard['overall_status']}")
    print(f"Meta-cognición: {dashboard['meta_cognition']['metacognition_metrics']}")
