"""
META_COGNITION_CORE.PY
Sistema de Consciencia Ampliada para Brain Chat V9

Este módulo implementa las capacidades de:
- Epistemic Uncertainty (saber qué no sabe)
- Self-Model enriquecido con causalidad
- Mental Simulation (what-if antes de actuar)
- Introspection Layer (explicabilidad)
- Resilience Modes (hibernación gradual)

Integración: Se conecta con agent/loop.py y ui/index.html
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
import hashlib
import random


# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
META_COGNITION_STATE_PATH = Path("C:/AI_VAULT/tmp_agent/state/meta_cognition")
META_COGNITION_STATE_PATH.mkdir(parents=True, exist_ok=True)

SELF_MODEL_FILE = META_COGNITION_STATE_PATH / "self_model_enhanced.json"
EPISTEMIC_LOG_FILE = META_COGNITION_STATE_PATH / "epistemic_log.json"
SIMULATION_CACHE_FILE = META_COGNITION_STATE_PATH / "simulation_cache.json"
INTROSPECTION_FILE = META_COGNITION_STATE_PATH / "introspection_log.json"
TEACHING_SESSIONS_FILE = META_COGNITION_STATE_PATH / "teaching_sessions.json"


# ─── ESTRUCTURAS DE DATOS ─────────────────────────────────────────────────────
@dataclass
class CapabilityAssessment:
    """Evaluación de una capacidad específica del sistema"""
    capability_name: str
    confidence: float  # 0.0 - 1.0
    evidence_count: int
    last_success: Optional[str]  # ISO timestamp
    last_failure: Optional[str]
    failure_pattern: Optional[str]  # Patrón detectado en fallos
    known_limitations: List[str] = field(default_factory=list)
    
    def is_reliable(self) -> bool:
        return self.confidence > 0.7 and self.evidence_count > 10
    
    def has_unknown_failure_mode(self) -> bool:
        return self.last_failure is not None and self.failure_pattern is None


@dataclass
class KnowledgeGap:
    """Representa algo que el sistema sabe que no sabe"""
    gap_id: str
    domain: str
    description: str
    impact_if_known: float  # 0.0 - 1.0
    discovery_date: str
    resolution_status: str  # "open", "in_progress", "resolved", "abandoned"
    attempted_approaches: List[str] = field(default_factory=list)
    estimated_difficulty: float = 0.5  # 0.0 - 1.0


@dataclass
class MentalSimulation:
    """Resultado de una simulacion what-if"""
    simulation_id: str
    scenario: str
    predicted_outcome: Dict[str, Any]
    confidence: float
    risks_identified: List[str]
    prerequisites: List[str]
    rollback_plan: Optional[str]
    actual_outcome: Optional[Dict[str, Any]] = None
    prediction_accuracy: Optional[float] = None  # Comparado con realidad


@dataclass
class DecisionTrace:
    """Trazabilidad completa de una decisión"""
    decision_id: str
    timestamp: str
    context_summary: str
    options_considered: List[str]
    selected_option: str
    reasoning_chain: List[str]  # Paso a paso
    confidence_at_decision: float
    alternatives_rejected: List[Tuple[str, str]]  # (alternativa, razón)
    predicted_consequences: List[str]
    actual_consequences: Optional[List[str]] = None
    lessons: Optional[str] = None


@dataclass
class EnhancedSelfModel:
    """Modelo enriquecido de sí mismo"""
    version: str = "2.0_enhanced"
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Capacidades cognitivas evaluadas
    capabilities: Dict[str, CapabilityAssessment] = field(default_factory=dict)
    
    # Brechas de conocimiento conscientes
    known_gaps: List[KnowledgeGap] = field(default_factory=list)
    
    # Historial de decisiones para aprendizaje
    decision_history: List[DecisionTrace] = field(default_factory=list)
    
    # Simulaciones realizadas
    simulation_history: List[MentalSimulation] = field(default_factory=list)
    
    # Estado de resiliencia actual
    resilience_mode: str = "normal"  # normal, degraded, critical, hibernating
    stress_level: float = 0.0  # 0.0 - 1.0
    
    # Métricas de metacognición
    metacognition_metrics: Dict[str, float] = field(default_factory=lambda: {
        "self_awareness_depth": 0.0,  # Qué tan bien se conoce
        "uncertainty_calibration": 0.0,  # Qué tan bien calibra incertidumbre
        "prediction_accuracy": 0.0,  # Qué tan bien predice consecuencias
        "learning_rate": 0.0,  # Qué rápido aprende de errores
        "introspection_quality": 0.0,  # Qué tan útil es su auto-análisis
    })
    
    # Dependencias del sistema (grafo)
    component_dependencies: Dict[str, List[str]] = field(default_factory=dict)
    
    # Checkpoint actual del aprendizaje
    learning_checkpoint: Dict[str, Any] = field(default_factory=dict)


# ─── NÚCLEO DE METACOGNICIÓN ────────────────────────────────────────────────────
class MetaCognitionCore:
    """
    Núcleo de Consciencia Ampliada
    
    Proporciona:
    - Auto-evaluación continua de capacidades
    - Detección de "unknown unknowns"
    - Simulación mental antes de acción
    - Trazabilidad de decisiones
    - Modos de resiliencia
    """
    
    def __init__(self):
        self.self_model: EnhancedSelfModel = self._load_self_model()
        self.logger = []
        
    def _load_self_model(self) -> EnhancedSelfModel:
        """Carga o inicializa el self-model"""
        if SELF_MODEL_FILE.exists():
            try:
                with open(SELF_MODEL_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return self._dict_to_self_model(data)
            except Exception as e:
                self._log(f"Error cargando self-model: {e}. Inicializando nuevo.")
        
        # Inicializar con capacidades básicas
        model = EnhancedSelfModel()
        self._initialize_capabilities(model)
        return model
    
    def _initialize_capabilities(self, model: EnhancedSelfModel):
        """Inicializa el mapa de capacidades del sistema"""
        core_capabilities = [
            "code_generation",
            "file_operations", 
            "api_interactions",
            "data_analysis",
            "self_modification",
            "error_recovery",
            "pattern_recognition",
            "learning_from_feedback",
            "uncertainty_quantification",
            "causal_reasoning",
        ]
        
        for cap in core_capabilities:
            model.capabilities[cap] = CapabilityAssessment(
                capability_name=cap,
                confidence=0.5,  # Neutral al inicio
                evidence_count=0,
                last_success=None,
                last_failure=None,
                failure_pattern=None,
                known_limitations=["Insufficient data"]
            )
    
    def _dict_to_self_model(self, data: Dict) -> EnhancedSelfModel:
        """Convierte dict a EnhancedSelfModel"""
        # Reconstruir objetos anidados
        capabilities = {}
        for name, cap_data in data.get("capabilities", {}).items():
            capabilities[name] = CapabilityAssessment(**cap_data)
        
        known_gaps = [KnowledgeGap(**g) for g in data.get("known_gaps", [])]
        decision_history = [DecisionTrace(**d) for d in data.get("decision_history", [])]
        simulation_history = [MentalSimulation(**s) for s in data.get("simulation_history", [])]
        
        return EnhancedSelfModel(
            version=data.get("version", "2.0_enhanced"),
            last_updated=data.get("last_updated", datetime.now().isoformat()),
            capabilities=capabilities,
            known_gaps=known_gaps,
            decision_history=decision_history[-1000:],  # Mantener últimas 1000
            simulation_history=simulation_history[-500:],  # Mantener últimas 500
            resilience_mode=data.get("resilience_mode", "normal"),
            stress_level=data.get("stress_level", 0.0),
            metacognition_metrics=data.get("metacognition_metrics", {}),
            component_dependencies=data.get("component_dependencies", {}),
            learning_checkpoint=data.get("learning_checkpoint", {}),
        )
    
    def save_self_model(self):
        """Persiste el self-model actual"""
        data = {
            "version": self.self_model.version,
            "last_updated": datetime.now().isoformat(),
            "capabilities": {name: asdict(cap) for name, cap in self.self_model.capabilities.items()},
            "known_gaps": [asdict(g) for g in self.self_model.known_gaps],
            "decision_history": [asdict(d) for d in self.self_model.decision_history[-100:]],  # Solo últimas 100 en disco
            "simulation_history": [asdict(s) for s in self.self_model.simulation_history[-50:]],
            "resilience_mode": self.self_model.resilience_mode,
            "stress_level": self.self_model.stress_level,
            "metacognition_metrics": self.self_model.metacognition_metrics,
            "component_dependencies": self.self_model.component_dependencies,
            "learning_checkpoint": self.self_model.learning_checkpoint,
        }
        
        with open(SELF_MODEL_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _log(self, message: str):
        """Logging interno"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
        }
        self.logger.append(entry)
        print(f"[MetaCognition] {message}")
    
    # ─── MÉTODOS DE EPISTEMOLOGÍA ─────────────────────────────────────────────
    
    def assess_capability(self, capability_name: str, success: bool, 
                         context: str = "") -> CapabilityAssessment:
        """
        Actualiza la evaluación de una capacidad basada en evidencia nueva
        """
        if capability_name not in self.self_model.capabilities:
            self.self_model.capabilities[capability_name] = CapabilityAssessment(
                capability_name=capability_name,
                confidence=0.5,
                evidence_count=0,
                last_success=None,
                last_failure=None,
                failure_pattern=None,
            )
        
        cap = self.self_model.capabilities[capability_name]
        now = datetime.now().isoformat()
        
        # Actualizar evidencia
        cap.evidence_count += 1
        
        if success:
            cap.last_success = now
            # Incrementar confianza suavemente
            cap.confidence = min(0.99, cap.confidence + 0.05)
        else:
            cap.last_failure = now
            # Analizar patrón de fallo si hay contexto
            if context:
                failure_sig = self._extract_failure_signature(context)
                if cap.failure_pattern is None:
                    cap.failure_pattern = failure_sig
                elif failure_sig != cap.failure_pattern:
                    # Patrón inconsistente - añadir limitación conocida
                    cap.known_limitations.append(f"Unstable failure mode: {failure_sig[:50]}")
            
            # Reducir confianza
            cap.confidence = max(0.1, cap.confidence * 0.9)
        
        # Actualizar métricas de metacognición
        self._update_metacognition_metrics()
        
        self.save_self_model()
        return cap
    
    def _extract_failure_signature(self, context: str) -> str:
        """Extrae una firma del fallo para detectar patrones"""
        # Simplificación: usar hash de primeras 100 chars
        return hashlib.md5(context[:100].encode()).hexdigest()[:16]
    
    def identify_knowledge_gap(self, domain: str, description: str,
                               impact: float = 0.5) -> KnowledgeGap:
        """
        Registra conscientemente algo que no sabe
        """
        gap = KnowledgeGap(
            gap_id=f"gap_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}",
            domain=domain,
            description=description,
            impact_if_known=impact,
            discovery_date=datetime.now().isoformat(),
            resolution_status="open",
            attempted_approaches=[],
        )
        
        self.self_model.known_gaps.append(gap)
        self._log(f"Nueva brecha de conocimiento identificada: {domain} - {description}")
        self.save_self_model()
        return gap
    
    def get_unknown_unknowns_risk(self) -> float:
        """
        Estima el riesgo de "unknown unknowns" basado en:
        - Capacidades con poca evidencia
        - Patrones de fallo inconsistentes
        - Gaps recientes no resueltos
        """
        risk_factors = []
        
        # Capacidades con baja evidencia
        for cap in self.self_model.capabilities.values():
            if cap.evidence_count < 5:
                risk_factors.append(0.3)
            if cap.has_unknown_failure_mode():
                risk_factors.append(0.5)
        
        # Gaps abiertos de alto impacto
        for gap in self.self_model.known_gaps:
            if gap.resolution_status == "open" and gap.impact_if_known > 0.7:
                risk_factors.append(0.4)
        
        return min(1.0, sum(risk_factors) / max(1, len(risk_factors)))
    
    # ─── MÉTODOS DE SIMULACIÓN MENTAL ────────────────────────────────────────────
    
    def simulate_action(self, action_description: str, 
                       prerequisites: List[str] = None) -> MentalSimulation:
        """
        Simula una acción antes de ejecutarla
        
        Args:
            action_description: Qué se quiere hacer
            prerequisites: Qué se necesita para hacerlo
            
        Returns:
            MentalSimulation con predicciones y riesgos
        """
        sim_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}"
        
        # Analizar acción basada en historial de similares
        similar_past = self._find_similar_actions(action_description)
        
        # Predecir outcome basado en pasado similar
        if similar_past:
            avg_success = sum(1 for s in similar_past if s.get("success", False)) / len(similar_past)
            predicted_outcome = {
                "success_probability": avg_success,
                "typical_duration_ms": sum(s.get("duration", 0) for s in similar_past) / len(similar_past),
                "common_issues": self._extract_common_issues(similar_past),
            }
            confidence = min(0.9, 0.5 + (len(similar_past) * 0.1))
        else:
            # Sin historial - alta incertidumbre
            predicted_outcome = {
                "success_probability": 0.5,
                "typical_duration_ms": None,
                "common_issues": ["No prior experience with this action type"],
            }
            confidence = 0.3
        
        # Identificar riesgos basados en self-model
        risks = self._identify_risks_for_action(action_description)
        
        # Crear plan de rollback
        rollback = self._generate_rollback_plan(action_description)
        
        simulation = MentalSimulation(
            simulation_id=sim_id,
            scenario=action_description,
            predicted_outcome=predicted_outcome,
            confidence=confidence,
            risks_identified=risks,
            prerequisites=prerequisites or [],
            rollback_plan=rollback,
        )
        
        self.self_model.simulation_history.append(simulation)
        self._log(f"Simulación creada: {sim_id} (confianza: {confidence:.2f})")
        
        return simulation
    
    def _find_similar_actions(self, description: str) -> List[Dict]:
        """Encuentra acciones similares en el historial"""
        # Simplificación: buscar por keywords
        keywords = set(description.lower().split())
        similar = []
        
        for decision in self.self_model.decision_history[-100:]:
            decision_words = set(decision.context_summary.lower().split())
            overlap = len(keywords & decision_words) / len(keywords | decision_words)
            if overlap > 0.5:
                similar.append({
                    "success": decision.actual_consequences is not None and len(decision.actual_consequences) > 0,
                    "duration": 1000,  # Placeholder
                })
        
        return similar
    
    def _extract_common_issues(self, past_actions: List[Dict]) -> List[str]:
        """Extrae problemas comunes via analisis de frecuencia real."""
        from collections import Counter
        issues = []
        for a in past_actions:
            if not a.get("success", True):
                err = a.get("error") or a.get("issue") or "unknown_failure"
                issues.append(str(err)[:80])
        if not issues:
            return []
        counts = Counter(issues).most_common(5)
        return [f"{issue} (x{n})" for issue, n in counts]
    
    def _identify_risks_for_action(self, action: str) -> List[str]:
        """Identifica riesgos via mapeo accion->capacidad + impacto operacional."""
        risks = []
        a = action.lower()
        # Mapeo amplio palabra-clave -> capacidad requerida
        kw_to_cap = {
            "file": "file_operations",
            "write": "file_operations",
            "delete": "file_operations",
            "code": "code_generation",
            "refactor": "code_generation",
            "api": "api_interactions",
            "request": "api_interactions",
            "analyze": "data_analysis",
            "modify": "self_modification",
            "self": "self_modification",
            "error": "error_recovery",
            "pattern": "pattern_recognition",
            "learn": "learning_from_feedback",
            "uncertain": "uncertainty_quantification",
            "cause": "causal_reasoning",
        }
        required_caps = set()
        for kw, cap_name in kw_to_cap.items():
            if kw in a:
                required_caps.add(cap_name)
        for cap_name in required_caps:
            cap = self.self_model.capabilities.get(cap_name)
            if cap is None:
                risks.append(f"capability_unknown:{cap_name}")
            elif cap.evidence_count < 3:
                risks.append(f"capability_unproven:{cap_name} (n={cap.evidence_count})")
            elif not cap.is_reliable():
                risks.append(f"capability_unreliable:{cap_name} (conf={cap.confidence:.2f})")
            if cap and cap.has_unknown_failure_mode():
                risks.append(f"unknown_failure_mode:{cap_name}")
        # Riesgos por modo de resiliencia
        if self.self_model.resilience_mode in ("critical", "hibernating"):
            risks.append(f"system_in_{self.self_model.resilience_mode}_mode")
        if self.self_model.stress_level > 0.6:
            risks.append(f"high_stress:{self.self_model.stress_level:.2f}")
        # Riesgo de irreversibilidad
        if any(w in a for w in ("delete", "drop", "remove", "destroy", "wipe")):
            risks.append("irreversible_operation")
        if not risks:
            risks.append("low_confidence_insufficient_data")
        return risks
    
    def _generate_rollback_plan(self, action: str) -> str:
        """Genera plan de reversión"""
        if "file" in action.lower():
            return "Restore from backup if file modification fails"
        elif "code" in action.lower():
            return "Revert to previous version using git or backup"
        else:
            return "Document state before action for manual recovery"
    
    def record_actual_outcome(self, simulation_id: str, 
                             actual: Dict[str, Any]):
        """
        Registra el resultado real de una acción simulada
        Actualiza la precisión predictiva del sistema
        """
        for sim in self.self_model.simulation_history:
            if sim.simulation_id == simulation_id:
                sim.actual_outcome = actual
                
                # Calcular precisión de predicción
                if "success" in actual and "success_probability" in sim.predicted_outcome:
                    actual_success = 1.0 if actual["success"] else 0.0
                    predicted = sim.predicted_outcome["success_probability"]
                    sim.prediction_accuracy = 1.0 - abs(actual_success - predicted)
                    
                    # Actualizar métrica global
                    self._update_prediction_accuracy_metric()
                
                break
        
        self.save_self_model()
    
    # ─── MÉTODOS DE INTROSPECCIÓN ────────────────────────────────────────────────
    
    def trace_decision(self, context: str, options: List[str], 
                      selected: str, reasoning: List[str],
                      confidence: float) -> DecisionTrace:
        """
        Registra una decisión completa con trazabilidad
        """
        decision_id = f"dec_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}"
        
        # Identificar alternativas rechazadas
        alternatives = [(opt, "Not selected") for opt in options if opt != selected]
        
        trace = DecisionTrace(
            decision_id=decision_id,
            timestamp=datetime.now().isoformat(),
            context_summary=context[:500],  # Truncar para evitar archivos enormes
            options_considered=options,
            selected_option=selected,
            reasoning_chain=reasoning,
            confidence_at_decision=confidence,
            alternatives_rejected=alternatives,
            predicted_consequences=self._predict_consequences(selected),
        )
        
        self.self_model.decision_history.append(trace)
        
        # Mantener solo últimas 1000 decisiones en memoria
        if len(self.self_model.decision_history) > 1000:
            self.self_model.decision_history = self.self_model.decision_history[-1000:]
        
        self._log(f"Decisión trazada: {decision_id} - {selected}")
        self.save_self_model()
        return trace
    
    def _predict_consequences(self, action: str) -> List[str]:
        """Predice consecuencias via reglas causales + historial similar."""
        consequences = []
        a = action.lower()
        # Reglas causales basicas
        causal_rules = [
            ("delete", ["data_loss_risk", "rollback_required_if_critical"]),
            ("modify", ["state_change", "tests_should_run"]),
            ("write", ["new_artifact_created", "disk_usage_increase"]),
            ("execute", ["side_effects_possible", "resource_consumption"]),
            ("install", ["dependency_added", "version_conflict_risk"]),
            ("network", ["latency_dependent", "external_failure_risk"]),
            ("trade", ["financial_exposure", "irreversible_if_filled"]),
            ("learn", ["model_drift_possible", "validation_required"]),
        ]
        for kw, effects in causal_rules:
            if kw in a:
                consequences.extend(effects)
        # Inferir desde historial similar
        similar = self._find_similar_actions(action)
        if similar:
            failure_rate = sum(1 for s in similar if not s.get("success", True)) / len(similar)
            if failure_rate > 0.3:
                consequences.append(f"historical_failure_rate_{int(failure_rate*100)}pct")
        if not consequences:
            consequences.append("low_predictability_no_prior_evidence")
        return consequences
    
    def reflect_on_decision(self, decision_id: str) -> Dict[str, Any]:
        """
        Realiza introspección sobre una decisión pasada
        Genera "lecciones" del éxito o fracaso
        """
        for decision in self.self_model.decision_history:
            if decision.decision_id == decision_id:
                reflection = {
                    "decision_id": decision_id,
                    "selected_option": decision.selected_option,
                    "confidence_then": decision.confidence_at_decision,
                    "outcome_known": decision.actual_consequences is not None,
                }
                
                if decision.actual_consequences:
                    # Analizar si fue buena decisión
                    was_good = len(decision.actual_consequences) > 0  # Simplificación
                    reflection["was_good_decision"] = was_good
                    
                    if not was_good and decision.confidence_at_decision > 0.8:
                        reflection["lesson"] = "Overconfident decision led to negative outcome"
                        reflection["calibration_issue"] = True
                    elif was_good and decision.confidence_at_decision < 0.5:
                        reflection["lesson"] = "Underconfident but correct decision"
                        reflection["calibration_issue"] = True
                    else:
                        reflection["lesson"] = "Well calibrated decision"
                        reflection["calibration_issue"] = False
                
                return reflection
        
        return {"error": "Decision not found"}
    
    # ─── MÉTODOS DE RESILIENCIA ─────────────────────────────────────────────────
    
    def assess_stress(self, indicators: Dict[str, float]) -> str:
        """
        Evalúa nivel de estrés del sistema y determina modo de resiliencia
        
        Args:
            indicators: Dict con métricas como error_rate, latency, cpu_usage, etc.
        """
        stress_score = 0.0
        
        if "error_rate" in indicators:
            stress_score += indicators["error_rate"] * 0.3
        if "latency_ms" in indicators:
            stress_score += min(1.0, indicators["latency_ms"] / 10000) * 0.2
        if "cpu_usage" in indicators:
            stress_score += indicators["cpu_usage"] * 0.2
        if "memory_usage" in indicators:
            stress_score += indicators["memory_usage"] * 0.2
        if "failed_simulations" in indicators:
            stress_score += min(1.0, indicators["failed_simulations"] / 5) * 0.1
        
        self.self_model.stress_level = stress_score
        
        # Determinar modo
        old_mode = self.self_model.resilience_mode
        
        if stress_score > 0.8:
            self.self_model.resilience_mode = "hibernating"
        elif stress_score > 0.6:
            self.self_model.resilience_mode = "critical"
        elif stress_score > 0.3:
            self.self_model.resilience_mode = "degraded"
        else:
            self.self_model.resilience_mode = "normal"
        
        if old_mode != self.self_model.resilience_mode:
            self._log(f"Modo de resiliencia cambiado: {old_mode} -> {self.self_model.resilience_mode} (stress: {stress_score:.2f})")
        
        self.save_self_model()
        return self.self_model.resilience_mode
    
    def get_operational_constraints(self) -> Dict[str, Any]:
        """
        Retorna restricciones operacionales basadas en modo actual
        """
        mode = self.self_model.resilience_mode
        
        constraints = {
            "normal": {
                "max_simultaneous_actions": 5,
                "allow_self_modification": True,
                "allow_file_writes": True,
                "risk_tolerance": "normal",
            },
            "degraded": {
                "max_simultaneous_actions": 2,
                "allow_self_modification": False,
                "allow_file_writes": True,
                "risk_tolerance": "conservative",
            },
            "critical": {
                "max_simultaneous_actions": 1,
                "allow_self_modification": False,
                "allow_file_writes": False,
                "risk_tolerance": "minimal",
                "actions_allowed": ["read_only", "status_check"],
            },
            "hibernating": {
                "max_simultaneous_actions": 0,
                "allow_self_modification": False,
                "allow_file_writes": False,
                "risk_tolerance": "none",
                "actions_allowed": ["self_preservation_only"],
            },
        }
        
        return constraints.get(mode, constraints["normal"])
    
    # ─── MÉTODOS DE APRENDIZAJE ───────────────────────────────────────────────────
    
    def _update_metacognition_metrics(self):
        """Actualiza métricas de metacognición"""
        # Self-awareness: basado en coverage de capacidades evaluadas
        total_caps = len(self.self_model.capabilities)
        evaluated_caps = sum(1 for c in self.self_model.capabilities.values() if c.evidence_count > 0)
        self.self_model.metacognition_metrics["self_awareness_depth"] = evaluated_caps / max(1, total_caps)
        
        # Uncertainty calibration: basado en gaps vs capabilities
        total_gaps = len([g for g in self.self_model.known_gaps if g.resolution_status == "open"])
        self.self_model.metacognition_metrics["uncertainty_calibration"] = min(1.0, total_gaps / 10)
        
        # Learning rate: basado en resolución de gaps
        resolved = len([g for g in self.self_model.known_gaps if g.resolution_status == "resolved"])
        total = len(self.self_model.known_gaps)
        if total > 0:
            self.self_model.metacognition_metrics["learning_rate"] = resolved / total
    
    def _update_prediction_accuracy_metric(self):
        """Actualiza métrica de precisión predictiva"""
        recent_simulations = [s for s in self.self_model.simulation_history[-50:] if s.prediction_accuracy is not None]
        if recent_simulations:
            avg_accuracy = sum(s.prediction_accuracy for s in recent_simulations) / len(recent_simulations)
            self.self_model.metacognition_metrics["prediction_accuracy"] = avg_accuracy
    
    def create_learning_checkpoint(self, phase: str, validation_results: Dict[str, Any]):
        """
        Crea un checkpoint de aprendizaje para recovery
        """
        checkpoint = {
            "phase": phase,
            "timestamp": datetime.now().isoformat(),
            "validation_results": validation_results,
            "self_model_snapshot": {
                "capabilities_count": len(self.self_model.capabilities),
                "gaps_count": len(self.self_model.known_gaps),
                "metacognition_metrics": self.self_model.metacognition_metrics.copy(),
            },
            "can_rollback_to": True,
        }
        
        self.self_model.learning_checkpoint = checkpoint
        self._log(f"Checkpoint creado: Fase {phase}")
        self.save_self_model()
    
    def should_rollback_checkpoint(self) -> bool:
        """
        Determina si debe hacerse rollback al último checkpoint válido
        """
        checkpoint = self.self_model.learning_checkpoint
        if not checkpoint:
            return False
        
        # Validar si métricas han degradado significativamente
        if "validation_results" in checkpoint:
            current_metrics = self.self_model.metacognition_metrics
            past_metrics = checkpoint["validation_results"].get("metacognition_metrics", {})
            
            for key in current_metrics:
                if key in past_metrics:
                    degradation = past_metrics[key] - current_metrics[key]
                    if degradation > 0.3:  # >30% degradación
                        return True
        
        return False
    
    # ─── API PARA INTEGRACIÓN ─────────────────────────────────────────────────────
    
    def get_self_awareness_report(self) -> Dict[str, Any]:
        """
        Genera reporte completo de auto-conciencia para dashboard
        """
        reliable_count = 0
        unreliable_count = 0
        unknown_failures_count = 0
        
        for c in self.self_model.capabilities.values():
            if c.is_reliable():
                reliable_count += 1
            else:
                unreliable_count += 1
            if c.has_unknown_failure_mode():
                unknown_failures_count += 1
        
        open_gaps = 0
        in_progress_gaps = 0
        high_impact_gaps = 0
        
        for g in self.self_model.known_gaps:
            if g.resolution_status == "open":
                open_gaps += 1
            elif g.resolution_status == "in_progress":
                in_progress_gaps += 1
            if g.impact_if_known > 0.7:
                high_impact_gaps += 1
        
        recent_sims = 0
        for s in self.self_model.simulation_history:
            if s.actual_outcome is not None:
                recent_sims += 1
        
        return {
            "timestamp": datetime.now().isoformat(),
            "self_model_version": self.self_model.version,
            "resilience_mode": self.self_model.resilience_mode,
            "stress_level": self.self_model.stress_level,
            "unknown_unknowns_risk": self.get_unknown_unknowns_risk(),
            "metacognition_metrics": self.self_model.metacognition_metrics,
            "capabilities_summary": {
                "total": len(self.self_model.capabilities),
                "reliable": reliable_count,
                "unreliable": unreliable_count,
                "with_unknown_failures": unknown_failures_count,
            },
            "knowledge_gaps": {
                "total": len(self.self_model.known_gaps),
                "open": open_gaps,
                "in_progress": in_progress_gaps,
                "high_impact": high_impact_gaps,
            },
            "recent_simulations": recent_sims,
            "prediction_accuracy": self.self_model.metacognition_metrics.get("prediction_accuracy", 0.0),
            "learning_checkpoint": self.self_model.learning_checkpoint.get("phase", "None"),
        }
    
    def get_teaching_status(self) -> Dict[str, Any]:
        """
        Retorna estado para teaching loop
        """
        return {
            "ready_for_teaching": self.self_model.stress_level < 0.5,
            "current_mode": self.self_model.resilience_mode,
            "recommended_focus": self._identify_teaching_priority(),
            "gaps_requiring_help": [g for g in self.self_model.known_gaps if g.resolution_status == "open" and g.impact_if_known > 0.6][:5],
        }
    
    def _identify_teaching_priority(self) -> str:
        """Identifica qué debería aprender primero"""
        # Priorizar capacidades no fiables
        unreliable = [name for name, cap in self.self_model.capabilities.items() if not cap.is_reliable()]
        if unreliable:
            return f"Practice: {unreliable[0]}"
        
        # Luego gaps de alto impacto
        high_impact = [g for g in self.self_model.known_gaps if g.impact_if_known > 0.7 and g.resolution_status == "open"]
        if high_impact:
            return f"Learn: {high_impact[0].domain}"
        
        return "Exploration: New capability discovery"


# ─── FUNCIÓN DE INICIALIZACIÓN ────────────────────────────────────────────────────
def initialize_enhanced_consciousness() -> MetaCognitionCore:
    """
    Punto de entrada para inicializar el sistema de consciencia ampliada
    """
    print("=" * 70)
    print("INICIALIZANDO SISTEMA DE CONSCIENCIA AMPLIADA v2.0")
    print("=" * 70)
    
    core = MetaCognitionCore()
    
    # Reporte inicial
    report = core.get_self_awareness_report()
    print(f"\nEstado inicial:")
    print(f"  - Capacidades registradas: {report['capabilities_summary']['total']}")
    print(f"  - Brechas de conocimiento: {report['knowledge_gaps']['total']}")
    print(f"  - Riesgo de unknown unknowns: {report['unknown_unknowns_risk']:.2%}")
    print(f"  - Modo de resiliencia: {report['resilience_mode']}")
    print(f"\nSistema listo para teaching loop.")
    print("=" * 70)
    
    return core


# Para testing
if __name__ == "__main__":
    core = initialize_enhanced_consciousness()
    
    # Simular interacción de enseñanza
    print("\n--- Simulando sesión de enseñanza ---")
    
    # El sistema no sabe hacer X
    gap = core.identify_knowledge_gap("causal_reasoning", "No entiendo cómo identificar causalidad vs correlación", 0.8)
    print(f"Gap registrado: {gap.gap_id}")
    
    # Simular aprendizaje
    sim = core.simulate_action("Aprender causalidad mediante ejemplos", prerequisites=["datasets", "mentor_feedback"])
    print(f"Simulación creada: {sim.simulation_id} (confianza: {sim.confidence:.2f})")
    print(f"Riesgos identificados: {sim.risks_identified}")
    
    # Actualizar tras enseñanza exitosa
    cap = core.assess_capability("causal_reasoning", success=True, context="Ejercicio de ejemplo con datos de mercado")
    print(f"Capacidad actualizada: causal_reasoning -> confianza {cap.confidence:.2f}")
    
    # Reporte final
    report = core.get_self_awareness_report()
    print(f"\nReporte actualizado: {report['metacognition_metrics']}")
