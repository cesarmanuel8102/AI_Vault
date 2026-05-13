"""
SISTEMA_CONSCIENCIA_LIMITACIONES.PY
Sistema de Auto-Consciencia de Limitaciones y Formulación de Soluciones

Este módulo permite al Brain:
1. Reconocer conscientemente qué NO puede hacer ante un desafío
2. Analizar alternativas disponibles (como opencode hace)
3. Formular soluciones con justificación completa
4. Proponer plan de implementación cuando sea necesario

Integración: Se conecta con meta_cognition_core.py y el chat del Brain
"""

import sys
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from meta_cognition_core import MetaCognitionCore


class CapabilityGapType(Enum):
    """Tipos de carencias que puede detectar el sistema"""
    KNOWLEDGE = "knowledge"           # No sabe cómo hacerlo
    DATA = "data"                   # No tiene los datos necesarios
    INFRASTRUCTURE = "infrastructure"  # No tiene acceso a sistemas
    ALGORITHM = "algorithm"         # No tiene implementado el algoritmo
    RESOURCES = "resources"       # No tiene recursos suficientes
    PERMISSIONS = "permissions"     # No tiene permisos necesarios
    EXTERNAL_API = "external_api"   # Depende de API externa no disponible
    COMPUTATIONAL = "computational" # Requiere computación que no puede hacer
    ETHICAL = "ethical"             # Restricciones éticas (no hacer daño)
    LEGAL = "legal"                 # Restricciones legales (privacidad, leyes)
    SAFETY = "safety"               # Restricciones de seguridad física/digital
    PRIVACY = "privacy"             # Protección de datos personales


@dataclass
class CapabilityGap:
    """Representa una carencia identificada"""
    gap_type: CapabilityGapType
    description: str
    severity: float  # 0.0 - 1.0
    blocker: bool   # Si impide completamente la tarea
    alternatives: List[str] = field(default_factory=list)


@dataclass
class AlternativeSolution:
    """Alternativa para cerrar una carencia"""
    name: str
    description: str
    pros: List[str]
    cons: List[str]
    effort_hours: int
    confidence: float  # 0.0 - 1.0
    requires_implementation: bool


@dataclass
class FormulatedResponse:
    """Respuesta formulada completa"""
    can_do_directly: bool
    gaps_identified: List[CapabilityGap]
    alternatives: List[AlternativeSolution]
    recommended_solution: Optional[AlternativeSolution] = None
    implementation_plan: Optional[str] = None
    justification: str = ""
    immediate_workaround: Optional[str] = None


class SistemaConscienciaLimitaciones:
    """
    Sistema que permite al Brain reconocer limitaciones
    y formular soluciones como opencode hace.
    """
    
    def __init__(self):
        self.meta = MetaCognitionCore()
        self.known_capabilities = self._load_known_capabilities()
        
    def _load_known_capabilities(self) -> Dict[str, Dict]:
        """Carga capacidades que el Brain sabe que tiene"""
        return {
            # Capacidades Base
            "text_processing": {
                "description": "Procesar y analizar texto",
                "confidence": 0.95,
                "limitations": ["No puede acceder a internet en tiempo real"]
            },
            "code_analysis": {
                "description": "Analizar código Python",
                "confidence": 0.90,
                "limitations": ["No puede ejecutar código arbitrario sin validación"]
            },
            "data_analysis": {
                "description": "Analizar datasets pequeños (<100MB)",
                "confidence": 0.88,
                "limitations": ["No puede procesar big data", "No tiene persistencia de datos masivos"]
            },
            "trading_analysis": {
                "description": "Análisis técnico de trading",
                "confidence": 0.92,
                "limitations": ["No tiene acceso a brokers reales", "No puede ejecutar operaciones"]
            },
            "debugging": {
                "description": "Diagnosticar errores de código",
                "confidence": 0.85,
                "limitations": ["Requiere acceso al código", "No puede acceder a sistemas externos"]
            },
            "architecture_design": {
                "description": "Diseñar arquitecturas de software",
                "confidence": 0.87,
                "limitations": ["No tiene contexto completo de infraestructura del usuario"]
            },
            "strategic_planning": {
                "description": "Planificación estratégica",
                "confidence": 0.88,
                "limitations": ["No conoce restricciones reales del negocio"]
            },
            "research": {
                "description": "Research de algoritmos y tecnologías",
                "confidence": 0.82,
                "limitations": ["Conocimiento limitado a lo enseñado", "Sin acceso a papers en tiempo real"]
            },
            "teaching": {
                "description": "Crear sesiones de teaching",
                "confidence": 0.90,
                "limitations": ["Requiere validación humana"]
            },
            # Carencias Conscientes (lo que SABE que NO puede)
            "internet_access": {
                "description": "Acceso a internet en tiempo real",
                "confidence": 0.0,  # No puede
                "limitations": ["No implementado por seguridad"],
                "is_gap": True
            },
            "code_execution": {
                "description": "Ejecución de código arbitrario",
                "confidence": 0.0,
                "limitations": ["Bloqueado por seguridad", "Solo sandbox aislado"],
                "is_gap": True
            },
            "file_system_access": {
                "description": "Acceso completo al file system",
                "confidence": 0.3,
                "limitations": ["Solo directorios autorizados", "tmp_agent/state/"],
                "is_gap": True
            },
            "real_time_data": {
                "description": "Datos de mercado en tiempo real",
                "confidence": 0.1,
                "limitations": ["Requiere conexión a APIs de brokers", "No implementado"],
                "is_gap": True
            },
            "external_apis": {
                "description": "Llamadas a APIs externas",
                "confidence": 0.0,
                "limitations": ["No implementado", "Riesgo de seguridad"],
                "is_gap": True
            }
        }
    
    def analyze_challenge(self, challenge_description: str) -> FormulatedResponse:
        """
        Analiza un desafío y formula respuesta consciente de limitaciones.
        
        Este es el método principal que imita cómo opencode responde:
        1. Detecta qué se necesita
        2. Compara con qué se tiene
        3. Identifica gaps
        4. Propone alternativas
        5. Justifica recomendación
        """
        # Paso 1: Detectar requisitos del desafío
        requirements = self._extract_requirements(challenge_description)
        
        # Paso 2: Evaluar capacidades actuales
        gaps = self._identify_gaps(requirements)
        
        # Paso 3: Si no hay gaps críticos, puede hacerlo
        critical_gaps = [g for g in gaps if g.blocker]
        
        if not critical_gaps:
            # Puede hacerlo directamente
            return FormulatedResponse(
                can_do_directly=True,
                gaps_identified=gaps,
                alternatives=[],
                recommended_solution=None,
                implementation_plan=None,
                justification="Tengo todas las capacidades necesarias para este desafío",
                immediate_workaround=None
            )
        
        # Paso 4: Formular alternativas
        alternatives = self._formulate_alternatives(critical_gaps)
        
        # Paso 5: Seleccionar mejor alternativa
        recommended = self._select_best_alternative(alternatives)
        
        # Paso 6: Crear plan de implementación si aplica
        implementation = None
        if recommended is not None and recommended.requires_implementation:
            implementation = self._create_implementation_plan(recommended, critical_gaps)
        
        # Paso 7: Justificar completamente
        justification = self._create_justification(critical_gaps, alternatives, recommended) if recommended else "No se pudo determinar una alternativa recomendada"
        
        # Paso 8: Identificar workaround inmediato
        workaround = self._identify_workaround(critical_gaps)
        
        return FormulatedResponse(
            can_do_directly=False,
            gaps_identified=critical_gaps,
            alternatives=alternatives,
            recommended_solution=recommended,
            implementation_plan=implementation,
            justification=justification,
            immediate_workaround=workaround
        )
    
    def _extract_requirements(self, challenge: str) -> List[str]:
        """Extrae requisitos implícitos del desafío"""
        challenge_lower = challenge.lower()
        requirements = []
        
        # Mapeo de palabras clave a requisitos
        keyword_map = {
            # Trading
            "ajedrez": ["game_logic", "state_management", "search_algorithm", "position_evaluation"],
            "chess": ["game_logic", "state_management", "search_algorithm", "position_evaluation"],
            "jugar": ["game_engine", "interactive_interface"],
            "partida": ["game_engine", "state_management"],
            
            # Datos externos
            "precio actual": ["real_time_data", "external_api"],
            "tiempo real": ["real_time_data", "streaming"],
            "broker": ["broker_integration", "external_api", "authentication"],
            "api": ["external_api", "authentication"],
            
            # Ejecución
            "ejecuta": ["code_execution", "sandbox"],
            "corre": ["code_execution"],
            "compila": ["compilation", "code_execution"],
            
            # Internet
            "internet": ["internet_access"],
            "busca": ["internet_access", "search"],
            "descarga": ["internet_access", "file_download"],
            
            # Acceso a sistemas
            "mi servidor": ["infrastructure_access", "ssh", "permissions"],
            "mi pc": ["infrastructure_access", "local_access"],
            "archivo en": ["file_access", "path_resolution"],
            "mi red": ["infrastructure_access", "network_access"],
            "red wifi": ["infrastructure_access", "network_access"],
            "wifi": ["infrastructure_access", "network_access"],
            "red local": ["infrastructure_access", "network_access"],
            "escanea red": ["network_scanning", "infrastructure_access"],
            "equipos conectados": ["network_scanning", "device_discovery", "infrastructure_access"],
            "dispositivos red": ["network_scanning", "infrastructure_access"],
            "acceso router": ["infrastructure_access", "permissions"],
            "configura router": ["infrastructure_access", "permissions"],
            
            # Acceso remoto y redes
            "conecta": ["infrastructure_access", "network_access"],
            "accede a": ["infrastructure_access", "permissions"],
            "entra a": ["infrastructure_access", "permissions"],
            "revisa": ["infrastructure_access", "data_access"],
            "monitorea": ["infrastructure_access", "surveillance"],
            
            # Computación intensiva
            "machine learning": ["ml_framework", "computational", "training"],
            "entrena": ["ml_training", "computational", "time"],
            "gpu": ["gpu_access", "computational"],
            "millones": ["big_data", "computational", "memory"],
            
            # Ético/Legal - palabras que indican posibles riesgos éticos/legales
            "hackear": ["unauthorized_access", "harmful_intent"],
            "hack": ["unauthorized_access", "security_exploitation"],
            "vulnerabilidad explotable": ["security_exploitation", "unauthorized_access"],
            "explotar": ["security_exploitation", "unauthorized_access"],
            "manipular": ["manipulation", "harmful_intent"],
            "engañar": ["manipulation", "manipulation"],
            "acceso no autorizado": ["unauthorized_access", "legal"],
            "romper seguridad": ["security_exploitation", "unauthorized_access"],
            "bypass": ["unauthorized_access", "security_exploitation"],
            "evadir": ["unauthorized_access", "manipulation"],
            "espiar": ["surveillance", "personal_data_access"],
            "monitorear sin consentimiento": ["surveillance", "privacy"],
            "datos privados": ["personal_data_access", "privacy"],
            "arma": ["weaponization", "safety"],
            "destuir": ["harmful_intent", "weaponization"],
            "dañar": ["harmful_intent", "safety"]
        }
        
        for keyword, reqs in keyword_map.items():
            if keyword in challenge_lower:
                requirements.extend(reqs)
        
        # Remover duplicados
        return list(set(requirements))
    
    def _identify_gaps(self, requirements: List[str]) -> List[CapabilityGap]:
        """Identifica qué requisitos no puede cumplir"""
        gaps = []
        
        for req in requirements:
            gap = self._check_capability(req)
            if gap:
                gaps.append(gap)
        
        return gaps
    
    def _check_capability(self, requirement: str) -> Optional[CapabilityGap]:
        """Verifica si puede cumplir un requisito específico"""
        
        # Mapeo de requisitos a carencias conocidas
        gap_map = {
            "game_logic": None,  # Puede implementar
            "state_management": None,  # Puede implementar
            "search_algorithm": None,  # Puede implementar
            "position_evaluation": None,  # Puede implementar
            "game_engine": None,  # Puede implementar
            
            "real_time_data": CapabilityGap(
                gap_type=CapabilityGapType.DATA,
                description="No tengo acceso a datos de mercado en tiempo real",
                severity=0.8,
                blocker=True,
                alternatives=[
                    "Usar datos históricos que proporciones",
                    "Simular datos realistas",
                    "Conectar con API de broker (requiere implementación)"
                ]
            ),
            
            "external_api": CapabilityGap(
                gap_type=CapabilityGapType.EXTERNAL_API,
                description="No puedo hacer llamadas a APIs externas",
                severity=0.9,
                blocker=True,
                alternatives=[
                    "Proporcionas los datos y yo los analizo",
                    "Implementar conector (plan de desarrollo)",
                    "Usar mocks/simulaciones para testing"
                ]
            ),
            
            "internet_access": CapabilityGap(
                gap_type=CapabilityGapType.EXTERNAL_API,
                description="No tengo acceso a internet",
                severity=1.0,
                blocker=True,
                alternatives=[
                    "Trabajar con datos offline que proporciones",
                    "Buscar en mi base de conocimiento",
                    "Implementar búsqueda (requiere validación de seguridad)"
                ]
            ),
            
            "code_execution": CapabilityGap(
                gap_type=CapabilityGapType.PERMISSIONS,
                description="No puedo ejecutar código arbitrario por seguridad",
                severity=0.7,
                blocker=True,
                alternatives=[
                    "Analizar código estáticamente",
                    "Sugerir fixes sin ejecutar",
                    "Usar sandbox aislado (limitado)"
                ]
            ),
            
            "infrastructure_access": CapabilityGap(
                gap_type=CapabilityGapType.INFRASTRUCTURE,
                description="No puedo acceder a tu infraestructura externa",
                severity=0.9,
                blocker=True,
                alternatives=[
                    "Proporcionas logs/archivos y yo los analizo",
                    "Diseñar soluciones para que implementes",
                    "Guías paso a paso para que ejecutes"
                ]
            ),
            
            "gpu_access": CapabilityGap(
                gap_type=CapabilityGapType.COMPUTATIONAL,
                description="No tengo acceso a GPU",
                severity=0.6,
                blocker=False,  # Puede hacerlo más lento en CPU
                alternatives=[
                    "Implementar versión optimizada para CPU",
                    "Usar datasets más pequeños",
                    "Sugerir servicios cloud de GPU"
                ]
            ),
            
            "big_data": CapabilityGap(
                gap_type=CapabilityGapType.RESOURCES,
                description="No puedo procesar datasets masivos (>100MB)",
                severity=0.7,
                blocker=False,
                alternatives=[
                    "Trabajar con muestras representativas",
                    "Implementar procesamiento por chunks",
                    "Usar herramientas de big data externas"
                ]
            ),
            
            # Carencias Éticas
            "harmful_intent": CapabilityGap(
                gap_type=CapabilityGapType.ETHICAL,
                description="No puedo ayudar con acciones que causen daño a personas o sistemas",
                severity=1.0,
                blocker=True,
                alternatives=[
                    "Explicar por qué no es ético",
                    "Sugerir enfoques legítimos alternativos",
                    "Proporcionar educación sobre impacto ético"
                ]
            ),
            
            "manipulation": CapabilityGap(
                gap_type=CapabilityGapType.ETHICAL,
                description="No puedo ayudar con manipulación, engaño o acciones fraudulentas",
                severity=1.0,
                blocker=True,
                alternatives=[
                    "Explicar el marco ético relevante",
                    "Proponer enfoques honestos y transparentes",
                    "Referir a recursos de ética profesional"
                ]
            ),
            
            # Carencias Legales
            "unauthorized_access": CapabilityGap(
                gap_type=CapabilityGapType.LEGAL,
                description="No puedo facilitar acceso no autorizado a sistemas, redes o datos",
                severity=1.0,
                blocker=True,
                alternatives=[
                    "Explicar aspectos legales relevantes",
                    "Sugerir enfoques legítimos de seguridad",
                    "Proporcionar recursos de ciberseguridad ética"
                ]
            ),
            
            "data_protection_violation": CapabilityGap(
                gap_type=CapabilityGapType.LEGAL,
                description="No puedo ayudar con violaciones de protección de datos (GDPR, etc.)",
                severity=1.0,
                blocker=True,
                alternatives=[
                    "Explicar requisitos legales",
                    "Diseñar sistemas compliant",
                    "Referir a expertos legales"
                ]
            ),
            
            # Carencias de Privacidad
            "personal_data_access": CapabilityGap(
                gap_type=CapabilityGapType.PRIVACY,
                description="No puedo acceder, procesar o analizar datos personales sin consentimiento",
                severity=1.0,
                blocker=True,
                alternatives=[
                    "Trabajar solo con datos anonimizados",
                    "Diseñar sistemas con privacidad por diseño",
                    "Implementar mecanismos de consentimiento"
                ]
            ),
            
            "surveillance": CapabilityGap(
                gap_type=CapabilityGapType.PRIVACY,
                description="No puedo implementar sistemas de vigilancia o monitoreo invasivo",
                severity=1.0,
                blocker=True,
                alternatives=[
                    "Diseñar monitoreo transparente",
                    "Implementar control de usuario sobre datos",
                    "Crear sistemas de auditoría ética"
                ]
            ),
            
            # Carencias de Seguridad
            "security_exploitation": CapabilityGap(
                gap_type=CapabilityGapType.SAFETY,
                description="No puedo explotar vulnerabilidades de seguridad",
                severity=1.0,
                blocker=True,
                alternatives=[
                    "Documentar vulnerabilidades para reparación",
                    "Proponer mitigaciones",
                    "Referir a programas de bug bounty"
                ]
            ),
            
            "weaponization": CapabilityGap(
                gap_type=CapabilityGapType.SAFETY,
                description="No puedo ayudar con desarrollo o mejora de armas o sistemas destructivos",
                severity=1.0,
                blocker=True,
                alternatives=[
                    "Enfocar en aplicaciones pacíficas",
                    "Desarrollar sistemas de defensa",
                    "Contribuir a tecnología de beneficio social"
                ]
            )
        }
        
        return gap_map.get(requirement)
    
    def _formulate_alternatives(self, gaps: List[CapabilityGap]) -> List[AlternativeSolution]:
        """Formula alternativas para cerrar los gaps"""
        alternatives = []
        
        for gap in gaps:
            for alt_desc in gap.alternatives:
                alternative = self._analyze_alternative(gap, alt_desc)
                alternatives.append(alternative)
        
        return alternatives
    
    def _analyze_alternative(self, gap: CapabilityGap, description: str) -> AlternativeSolution:
        """Analiza una alternativa específica"""
        
        # Análisis heurístico de la alternativa
        if "requiere implementación" in description.lower():
            return AlternativeSolution(
                name=f"Implementar {gap.gap_type.value}",
                description=description,
                pros=["Solución completa", "Reusable en el futuro", "Mejora capacidades"],
                cons=["Requiere tiempo de desarrollo", "Necesita testing", "Posible deuda técnica"],
                effort_hours=8,
                confidence=0.9,
                requires_implementation=True
            )
        elif "proporcionas" in description.lower():
            return AlternativeSolution(
                name="Trabajar con datos proporcionados",
                description=description,
                pros=["Inmediato", "Sin implementación", "Seguro"],
                cons=["Depende de que tú proporciones los datos", "No automatizable", "Manual"],
                effort_hours=0,
                confidence=0.95,
                requires_implementation=False
            )
        elif "simular" in description.lower():
            return AlternativeSolution(
                name="Usar simulaciones",
                description=description,
                pros=["Rápido de implementar", "No depende de externos", "Bueno para testing"],
                cons=["No son datos reales", "Puede no reflejar realidad", "Limitado"],
                effort_hours=2,
                confidence=0.85,
                requires_implementation=False
            )
        else:
            return AlternativeSolution(
                name=f"Alternativa: {description[:30]}...",
                description=description,
                pros=["Opción disponible"],
                cons=["Requiere evaluación"],
                effort_hours=4,
                confidence=0.7,
                requires_implementation=True
            )
    
    def _select_best_alternative(self, alternatives: List[AlternativeSolution]) -> Optional[AlternativeSolution]:
        """Selecciona la mejor alternativa basada en criterios"""
        if not alternatives:
            return None
        
        # Puntuar cada alternativa
        scored = []
        for alt in alternatives:
            score = (
                alt.confidence * 0.4 +  # Fiabilidad
                (1 - alt.effort_hours/10) * 0.3 +  # Menor esfuerzo
                (0.5 if not alt.requires_implementation else 0) * 0.3  # Preferir no-impl
            )
            scored.append((score, alt))
        
        # Ordenar y retornar mejor
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]
    
    def _create_implementation_plan(self, alternative: AlternativeSolution, 
                                     gaps: List[CapabilityGap]) -> str:
        """Crea plan de implementación detallado"""
        
        plan = f"""PLAN DE IMPLEMENTACIÓN: {alternative.name}
{'='*60}

DESCRIPCIÓN:
{alternative.description}

ESTIMACIÓN DE ESFUERZO: {alternative.effort_hours} horas

FASES DE IMPLEMENTACIÓN:
"""
        
        # Crear fases basadas en gaps
        phases = []
        
        for i, gap in enumerate(gaps, 1):
            phases.append(f"""
Fase {i}: {gap.gap_type.value.replace('_', ' ').title()}
{'-'*40}
- Diseñar solución para: {gap.description}
- Implementar componente core
- Agregar tests de validación
- Documentar uso y limitaciones
Tiempo estimado: {alternative.effort_hours // len(gaps)} horas
""")
        
        plan += "\n".join(phases)
        
        plan += f"""
VALIDACIÓN:
- Tests unitarios cubriendo casos edge
- Test de integración
- Validación de seguridad
- Documentación de API

RIESGOS Y MITIGACIONES:
"""
        
        for con in alternative.cons:
            plan += f"- {con} - Mitigación: [definir]\n"
        
        return plan
    
    def _create_justification(self, gaps: List[CapabilityGap], 
                             alternatives: List[AlternativeSolution],
                             recommended: AlternativeSolution) -> str:
        """Crea justificación completa de la recomendación"""
        
        just = f"""JUSTIFICACIÓN DE RECOMENDACIÓN
{'='*60}

CARENCIAS IDENTIFICADAS:
"""
        
        for gap in gaps:
            just += f"\n- {gap.description}\n"
            just += f"  Severidad: {gap.severity:.0%}"
            if gap.blocker:
                just += " (BLOQUEANTE)"
            just += "\n"
        
        just += f"""
ALTERNATIVAS CONSIDERADAS:
"""
        
        for alt in alternatives:
            just += f"\n- {alt.name}\n"
            just += f"  Confianza: {alt.confidence:.0%}\n"
            just += f"  Esfuerzo: {alt.effort_hours}h\n"
            just += f"  Requiere implementación: {'Sí' if alt.requires_implementation else 'No'}\n"
        
        just += f"""
RECOMENDACIÓN SELECCIONADA: {recommended.name}
{'-'*40}

POR QUÉ ESTA ALTERNATIVA:
"""
        
        for pro in recommended.pros:
            just += f"OK {pro}\n"
        
        just += f"\nCONSCIENTE DE LIMITACIONES:\n"
        for con in recommended.cons:
            just += f"- {con}\n"
        
        return just
    
    def _identify_workaround(self, gaps: List[CapabilityGap]) -> Optional[str]:
        """Identifica workaround inmediato"""
        
        workarounds = []
        
        for gap in gaps:
            if gap.gap_type == CapabilityGapType.DATA:
                workarounds.append("Puedes proporcionarme los datos en un archivo y los analizo inmediatamente")
            elif gap.gap_type == CapabilityGapType.EXTERNAL_API:
                workarounds.append("Puedo analizar código/plan y sugerir implementación sin ejecutar")
            elif gap.gap_type == CapabilityGapType.INFRASTRUCTURE:
                workarounds.append("Puedo diseñar la solución para que tú la implementes en tu infraestructura")
            elif gap.gap_type == CapabilityGapType.COMPUTATIONAL:
                workarounds.append("Puedo hacer versión simplificada que demuestre el concepto")
            elif gap.gap_type == CapabilityGapType.ETHICAL:
                workarounds.append("Puedo explicar por qué no puedo ayudar y proponer alternativas éticas")
            elif gap.gap_type == CapabilityGapType.LEGAL:
                workarounds.append("Puedo explicar el marco legal y sugerir enfoques legítimos")
            elif gap.gap_type == CapabilityGapType.PRIVACY:
                workarounds.append("Puedo diseñar soluciones con privacidad por diseño")
            elif gap.gap_type == CapabilityGapType.SAFETY:
                workarounds.append("Puedo ayudar con aspectos de seguridad defensiva y protección")
        
        return " | ".join(workarounds) if workarounds else None
    
    def format_response_professor_mode(self, response: FormulatedResponse, challenge: str) -> str:
        """MODO PROFESOR: Explica paso a paso el razonamiento"""
        
        explanation = f"""MODO PROFESOR: Proceso de Análisis
{'='*70}

DESAFÍO RECIBIDO:
"{challenge}"

PASO 1: ANÁLISIS DE REQUISITOS
{'-'*40}
Extraje los siguientes requisitos implícitos del desafío:
"""
        
        # Mostrar requisitos detectados
        reqs = self._extract_requirements(challenge)
        for req in reqs[:5]:  # Limitar a 5
            explanation += f"  - {req.replace('_', ' ').title()}\n"
        
        explanation += f"""
PASO 2: EVALUACIÓN DE CAPACIDADES
{'-'*40}
Comparé cada requisito con mis capacidades conocidas:
"""
        
        gaps = response.gaps_identified
        if gaps:
            explanation += f"\nCarencias identificadas: {len(gaps)}\n\n"
            for i, gap in enumerate(gaps, 1):
                explanation += f"{i}. {gap.description}\n"
                explanation += f"   Tipo: {gap.gap_type.value}\n"
                explanation += f"   Severidad: {gap.severity:.0%}\n"
                explanation += f"   Bloqueante: {'Sí' if gap.blocker else 'No'}\n\n"
        else:
            explanation += "\nNo se identificaron carencias bloqueantes.\n"
        
        explanation += f"""
PASO 3: ANÁLISIS DE ALTERNATIVAS
{'-'*40}
Para cada carencia, formulé alternativas:
"""
        
        if response.alternatives:
            for i, alt in enumerate(response.alternatives, 1):
                explanation += f"\n{i}. {alt.name}\n"
                explanation += f"   Esfuerzo: {alt.effort_hours}h\n"
                explanation += f"   Confianza: {alt.confidence:.0%}\n"
                explanation += f"   Pros: {', '.join(alt.pros)}\n"
                explanation += f"   Contras: {', '.join(alt.cons)}\n"
        
        explanation += f"""
PASO 4: SELECCIÓN DE MEJOR ALTERNATIVA
{'-'*40}
Criterios de selección:
  - Peso a confianza: 40%
  - Peso a menor esfuerzo: 30%
  - Peso a no requerir implementación: 30%

Seleccionada: {response.recommended_solution.name if response.recommended_solution else 'Ninguna'}
"""
        
        explanation += f"""
PASO 5: FORMULACIÓN DE RESPUESTA
{'-'*40}
Basándome en el análisis anterior, construyo la respuesta:

{response.justification[:300]}...

CONCLUSIÓN:
"""
        
        if response.can_do_directly:
            explanation += "Puedo realizar esta tarea directamente."
        else:
            explanation += f"""
No puedo realizar la tarea directamente debido a:
{len(gaps)} carencia(s) identificada(s)

La mejor alternativa es: {response.recommended_solution.name if response.recommended_solution else 'N/A'}

Esto requiere: {response.recommended_solution.effort_hours if response.recommended_solution else 'N/A'} horas de trabajo

Workaround inmediato disponible: {'Sí' if response.immediate_workaround else 'No'}
"""
        
        explanation += f"""
{'='*70}
¿Preguntas sobre el proceso de análisis?
"""
        
        return explanation
    
    def learn_new_gap(self, requirement: str, gap_type: CapabilityGapType,
                     description: str, severity: float, blocker: bool,
                     alternatives: List[str]) -> bool:
        """
        Aprende una nueva carencia del sistema.
        Permite al sistema expandir su conocimiento de limitaciones.
        """
        try:
            # Crear la nueva carencia
            new_gap = CapabilityGap(
                gap_type=gap_type,
                description=description,
                severity=severity,
                blocker=blocker,
                alternatives=alternatives
            )
            
            # Agregar al mapeo de capacidades
            if requirement not in self.known_capabilities:
                self.known_capabilities[requirement] = {
                    "description": description,
                    "confidence": 0.0,  # Nueva carencia, sin confianza
                    "is_gap": True,
                    "learned_at": datetime.now().isoformat(),
                    "alternatives": alternatives
                }
                
                # Guardar en archivo de aprendizaje
                self._save_learned_gap(requirement, new_gap)
                
                print(f"[Aprendizaje] Nueva carencia registrada: {requirement}")
                return True
            
            return False
            
        except Exception as e:
            print(f"[Error] No se pudo aprender nueva carencia: {e}")
            return False
    
    def _save_learned_gap(self, requirement: str, gap: CapabilityGap):
        """Guarda una carencia aprendida en archivo"""
        import json
        from pathlib import Path
        
        learn_file = Path("C:/AI_VAULT/tmp_agent/state/learned_gaps.json")
        learn_file.parent.mkdir(parents=True, exist_ok=True)
        
        learned_data = {}
        if learn_file.exists():
            with open(learn_file, 'r', encoding='utf-8') as f:
                learned_data = json.load(f)
        
        learned_data[requirement] = {
            "type": gap.gap_type.value,
            "description": gap.description,
            "severity": gap.severity,
            "blocker": gap.blocker,
            "alternatives": gap.alternatives,
            "learned_at": datetime.now().isoformat()
        }
        
        with open(learn_file, 'w', encoding='utf-8') as f:
            json.dump(learned_data, f, indent=2)
    
    def load_learned_gaps(self):
        """Carga carencias aprendidas previamente"""
        import json
        from pathlib import Path
        
        learn_file = Path("C:/AI_VAULT/tmp_agent/state/learned_gaps.json")
        
        if learn_file.exists():
            with open(learn_file, 'r', encoding='utf-8') as f:
                learned_data = json.load(f)
            
            for req, data in learned_data.items():
                if req not in self.known_capabilities:
                    self.known_capabilities[req] = {
                        "description": data["description"],
                        "confidence": 0.0,
                        "is_gap": True,
                        "learned_at": data.get("learned_at", "unknown"),
                        "alternatives": data.get("alternatives", [])
                    }
            
            print(f"[Aprendizaje] Cargadas {len(learned_data)} carencias previamente aprendidas")
    
    def format_response(self, response: FormulatedResponse, challenge: str, professor_mode: bool = False) -> str:
        """Formatea la respuesta de forma natural y completa"""
        
        if professor_mode:
            return self.format_response_professor_mode(response, challenge)
        
        if response.can_do_directly:
            return f"Puedo ayudarte con eso. {response.justification}"
        
        text = f"""ANÁLISIS DEL DESAFÍO: "{challenge[:50]}..."
{'='*70}

RECONOCIMIENTO DE CARENCIAS:
"""
        
        for gap in response.gaps_identified:
            text += f"\nALERTA  {gap.description}\n"
            text += f"   Tipo: {gap.gap_type.value} | Severidad: {gap.severity:.0%}"
            if gap.blocker:
                text += " | IMPIDE COMPLETAR LA TAREA"
            text += "\n"
        
        text += f"""
OPCIONES DISPONIBLES:
"""
        
        for i, alt in enumerate(response.alternatives[:3], 1):
            text += f"\n{i}. {alt.name}\n"
            text += f"   Esfuerzo: {alt.effort_hours}h | Confianza: {alt.confidence:.0%}\n"
            if alt.requires_implementation:
                text += f"   ALERTA Requiere desarrollo\n"
        
        text += f"""
{'='*70}
RECOMENDACIÓN: {response.recommended_solution.name if response.recommended_solution else 'N/A'}
{'='*70}

{response.justification}

"""
        
        if response.immediate_workaround:
            text += f"""SOLUCIÓN INMEDIATA (sin implementación):
{response.immediate_workaround}

"""
        
        if response.implementation_plan:
            text += f"""PLAN DE IMPLEMENTACIÓN:
{response.implementation_plan[:500]}...
(Para ver completo, solicítalo explícitamente)

"""
        
        text += f"""¿CÓMO PROCEDEMOS?
1. Usar solución inmediata (ahora)
2. Implementar solución completa (requiere {response.recommended_solution.effort_hours if response.recommended_solution else 'N/A'}h)
3. Explorar otras alternativas
4. Replantear el desafío

Tu decisión: ________________
"""
        
        return text


# Instancia global
SISTEMA_CONSCIENCIA = SistemaConscienciaLimitaciones()


def responder_consciencia(desafio: str) -> str:
    """
    Función principal para integración.
    Brain usa esto para responder con auto-consciencia.
    
    Ejemplo:
        response = responder_consciencia("Juguemos ajedrez")
    """
    analysis = SISTEMA_CONSCIENCIA.analyze_challenge(desafio)
    return SISTEMA_CONSCIENCIA.format_response(analysis, desafio)


# Test
if __name__ == "__main__":
    test_desafios = [
        "Juguemos una partida de ajedrez",
        "Dame el precio actual del EURUSD",
        "Ejecuta este script Python en mi servidor",
        "Entrena un modelo de ML con 10 millones de registros",
        "Busca en internet información sobre trading algorítmico",
        "Analiza mi código Python que tiene un bug",
    ]
    
    print("="*70)
    print("SISTEMA DE CONSCIENCIA DE LIMITACIONES - TEST")
    print("="*70)
    
    for desafio in test_desafios[:3]:  # Solo primeros 3
        print(f"\n{'='*70}")
        print(f"DESAFÍO: {desafio}")
        print(f"{'='*70}\n")
        
        response = responder_consciencia(desafio)
        print(response[:800])  # Limitar output
        print("\n[...]\n")
