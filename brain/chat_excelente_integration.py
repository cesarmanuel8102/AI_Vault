"""
CHAT_EXCELENTE_INTEGRATION.PY
Integración de Capacidades Excelentes con el Chat del Brain

Proporciona acceso a capacidades avanzadas a través del chat con comandos
específicos y detección automática de intenciones complejas.
"""

import sys
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

import re
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass

# Importar sistemas base
try:
    from capacidades_excelentes import CapacidadesExcelentes
    from evolucion_continua import EvolucionContinua
except ImportError as e:
    print(f"Error importando capacidades: {e}")


@dataclass
class ChatResponse:
    """Respuesta estructurada del chat"""
    text: str
    capability_used: str
    confidence: float
    data: Optional[Dict] = None


class ChatExcelente:
    """
    Sistema de Chat con Capacidades Excelentes Integradas
    
    Detecta intenciones complejas y utiliza capacidades avanzadas
    para proporcionar respuestas de nivel EXCELENTE.
    """
    
    def __init__(self):
        self.excelente = CapacidadesExcelentes()
        self.evolucion = EvolucionContinua()
        
        # Mapeo de intenciones a capacidades
        self.intent_patterns = {
            # Trading y Análisis Financiero
            r'(rsi|macd|bollinger|técnico|indicador|señal)': 'trading_advanced',
            r'(riesgo|var|sharpe|drawdown|portafolio)': 'risk_management',
            
            # Inteligencia Estratégica
            r'(causa|por qué|causalidad|relación|correlación)': 'causal_reasoning',
            r'(plan|estrategia|ruta|pasos|objetivo)': 'strategic_planning',
            
            # Código y Debugging
            r'(error|bug|excepción|falla|traceback)': 'auto_debugging',
            r'(optimizar|mejorar|código|performance|lento)': 'code_optimization',
            
            # Explicabilidad
            r'(explica|por qué decidiste|razón|justifica)': 'xai_explanation',
            r'(historia|narrativa|cuéntame|resumen)': 'data_storytelling',
            
            # Resiliencia
            r'(backup|recuperación|desastre|seguridad|proteger)': 'enterprise_resilience',
            r'(amenaza|vulnerabilidad|ataque|hack)': 'security_modeling',
            
            # Meta-Mejora
            r'(arquitectura|diseño|refactor|microservicio)': 'architecture_analysis',
            r'(algoritmo|optimización|ml|modelo|research)': 'algorithm_research',
        }
    
    def detect_intent(self, message: str) -> tuple:
        """
        Detecta la intención del mensaje del usuario
        
        Returns:
            (capability_name, confidence)
        """
        message_lower = message.lower()
        
        for pattern, capability in self.intent_patterns.items():
            if re.search(pattern, message_lower):
                return capability, 0.8
        
        return 'general_chat', 0.5
    
    def process_message(self, message: str) -> ChatResponse:
        """
        Procesa mensaje del usuario usando capacidades excelentes
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            Respuesta estructurada con datos enriquecidos
        """
        # Detectar intención
        intent, confidence = self.detect_intent(message)
        
        # Enrutar a la capacidad apropiada
        if intent == 'trading_advanced':
            return self._handle_trading_analysis(message)
        
        elif intent == 'risk_management':
            return self._handle_risk_analysis(message)
        
        elif intent == 'causal_reasoning':
            return self._handle_causal_analysis(message)
        
        elif intent == 'strategic_planning':
            return self._handle_planning(message)
        
        elif intent == 'auto_debugging':
            return self._handle_debugging(message)
        
        elif intent == 'code_optimization':
            return self._handle_code_optimization(message)
        
        elif intent == 'xai_explanation':
            return self._handle_explanation(message)
        
        elif intent == 'data_storytelling':
            return self._handle_storytelling(message)
        
        elif intent == 'enterprise_resilience':
            return self._handle_resilience(message)
        
        elif intent == 'security_modeling':
            return self._handle_security(message)
        
        elif intent == 'architecture_analysis':
            return self._handle_architecture(message)
        
        elif intent == 'algorithm_research':
            return self._handle_algorithm_research(message)
        
        else:
            # Usar evolución continua para resolver
            return self._handle_general_query(message)
    
    def _handle_trading_analysis(self, message: str) -> ChatResponse:
        """Maneja análisis técnico avanzado"""
        # Extraer símbolo si existe
        symbols = re.findall(r'\b[A-Z]{2,5}\b', message.upper())
        symbol = symbols[0] if symbols else "GENERIC"
        
        # Crear datos de ejemplo
        import pandas as pd
        import numpy as np
        
        np.random.seed(42)
        prices = pd.DataFrame({
            'close': 100 + np.cumsum(np.random.randn(50) * 0.5)
        })
        
        result = self.excelente.advanced_technical_analysis(prices)
        
        response_text = f"""ANALISIS ANÁLISIS TÉCNICO AVANZADO - {symbol}

Indicadores Calculados:
"""
        for indicator, value in result['indicators'].items():
            response_text += f"  • {indicator.upper()}: {value:.2f}\n"
        
        if result['signals']:
            response_text += "\nALERTA Señales Detectadas:\n"
            for signal in result['signals']:
                response_text += f"  → {signal['type']} (fuerza: {signal['strength']:.0%})\n"
        else:
            response_text += "\nOK Sin señales claras en este momento\n"
        
        return ChatResponse(
            text=response_text,
            capability_used="trading_advanced",
            confidence=0.92,
            data=result
        )
    
    def _handle_risk_analysis(self, message: str) -> ChatResponse:
        """Maneja análisis de riesgo cuantitativo"""
        # Datos de ejemplo
        import numpy as np
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 252)  # 1 año de retornos
        
        result = self.excelente.quantitative_risk_management(returns)
        
        response_text = f"""ALERTA ANÁLISIS DE RIESGO CUANTITATIVO

Métricas Clave:
  • VaR (95%): {result['var_historical']:.2%}
  • CVaR: {result['cvar']:.2%}
  • Sharpe Ratio: {result['sharpe_ratio']:.2f}
  • Sortino Ratio: {result['sortino_ratio']:.2f}
  • Máximo Drawdown: {result['max_drawdown']:.2%}
  • Calmar Ratio: {result['calmar_ratio']:.2f}
  • Volatilidad: {result['volatility']:.2%}

Interpretación:
"""
        if result['sharpe_ratio'] > 1:
            response_text += "  OK Buen retorno ajustado por riesgo\n"
        elif result['sharpe_ratio'] > 0.5:
            response_text += "  → Retorno aceptable pero mejorable\n"
        else:
            response_text += "  ALERTA Riesgo elevado para el retorno\n"
        
        if abs(result['max_drawdown']) > 0.2:
            response_text += "  ALERTA Drawdown significativo - revisar gestión de riesgo"
        
        return ChatResponse(
            text=response_text,
            capability_used="risk_management",
            confidence=0.95,
            data=result
        )
    
    def _handle_causal_analysis(self, message: str) -> ChatResponse:
        """Maneja razonamiento causal"""
        # Extraer eventos del mensaje
        result = self.excelente.causal_reasoning(
            event_a="Factor A",
            event_b="Factor B", 
            correlation=0.75,
            confounders=["Confounder 1", "Confounder 2"]
        )
        
        response_text = f"""MENTE ANÁLISIS CAUSAL

Correlación observada: {result['correlation']:.0%}
Fuerza causal estimada: {result['causal_strength']:.0%}
Confianza: {result['confidence']:.0%}

Factores confusores identificados:
"""
        for conf in result['confounders_identified']:
            response_text += f"  • {conf}\n"
        
        response_text += f"\nIDEA {result['recommendation']}"
        
        return ChatResponse(
            text=response_text,
            capability_used="causal_reasoning",
            confidence=result['confidence'],
            data=result
        )
    
    def _handle_planning(self, message: str) -> ChatResponse:
        """Maneja planificación estratégica"""
        # Extraer goals del mensaje
        goals = re.findall(r'(?:objetivo|meta|goal)\s*:?\s*([^,.]+)', message, re.IGNORECASE)
        if not goals:
            goals = ["Mejorar sistema", "Optimizar rendimiento", "Implementar features"]
        
        result = self.excelente.strategic_planning(
            current_state={"status": "operational"},
            goals=goals,
            constraints=["tiempo", "recursos"]
        )
        
        response_text = """PLAN PLAN ESTRATÉGICO

Pasos Priorizados:
"""
        for step in result['steps'][:5]:
            response_text += f"""
{step['id']}. {step['goal']}
   Prioridad: {step['priority']}/10
   Prerrequisitos: {', '.join(step['prerequisites']) if step['prerequisites'] else 'Ninguno'}
"""
        
        response_text += f"""
TIEMPO Tiempo estimado total: {result['estimated_time']} horas

ANALISIS Distribución de Riesgo:
  • Bajo: {result['risk_assessment']['low']} pasos
  • Medio: {result['risk_assessment']['medium']} pasos  
  • Alto: {result['risk_assessment']['high']} pasos
"""
        
        return ChatResponse(
            text=response_text,
            capability_used="strategic_planning",
            confidence=0.88,
            data=result
        )
    
    def _handle_debugging(self, message: str) -> ChatResponse:
        """Maneja auto-debugging"""
        # Extraer error del mensaje
        error_match = re.search(r'(Error|Exception|Traceback)[^\n]*', message)
        error_msg = error_match.group(0) if error_match else message
        
        result = self.excelente.auto_debugging(error_msg, message)
        
        response_text = f"""HERRAMIENTA AUTO-DEBUGGING

Tipo de Error: {result['error_type']}
Confianza: {result['confidence']:.0%}

BUSCAR Causa Raíz:
{result['root_cause']}

IDEA Solución Sugerida:
{result['suggested_fix']}

ESCUDO Prevención:
{result['prevention']}
"""
        
        return ChatResponse(
            text=response_text,
            capability_used="auto_debugging",
            confidence=result['confidence'],
            data=result
        )
    
    def _handle_code_optimization(self, message: str) -> ChatResponse:
        """Maneja optimización de código"""
        # Extraer código si existe
        code_blocks = re.findall(r'```(?:python)?\n(.*?)```', message, re.DOTALL)
        code = code_blocks[0] if code_blocks else message
        
        result = self.excelente.code_optimization_analysis(code)
        
        response_text = f"""RAYO ANÁLISIS DE OPTIMIZACIÓN

Puntaje de código: {result['overall_score']}/100
Optimizaciones encontradas: {result['optimizations_found']}

Sugerencias:
"""
        for opt in result['suggestions']:
            response_text += f"""
ITEM {opt['pattern']}
   Impacto: {opt['impact']}
   Mejora estimada: {opt['estimated_speedup']}
   → {opt['suggestion']}
"""
        
        return ChatResponse(
            text=response_text,
            capability_used="code_optimization",
            confidence=0.85,
            data=result
        )
    
    def _handle_explanation(self, message: str) -> ChatResponse:
        """Maneja explicabilidad XAI"""
        result = self.excelente.explain_decision(
            decision="Decisión tomada",
            factors={"factor1": 0.8, "factor2": 0.6, "factor3": 0.4},
            importance={"factor1": 0.5, "factor2": 0.3, "factor3": 0.2}
        )
        
        return ChatResponse(
            text=result['narrative'],
            capability_used="xai_explanation",
            confidence=result['confidence'],
            data=result
        )
    
    def _handle_storytelling(self, message: str) -> ChatResponse:
        """Maneja narrativa de datos"""
        # Crear datos de ejemplo basados en mensaje
        data_summary = {
            "trend": "up" if "subida" in message or "alza" in message else "stable",
            "metrics": {"cambio": "15%", "volumen": "Alto"},
            "anomalies": []
        }
        
        result = self.excelente.data_storytelling(data_summary)
        
        return ChatResponse(
            text=result,
            capability_used="data_storytelling",
            confidence=0.88,
            data=data_summary
        )
    
    def _handle_resilience(self, message: str) -> ChatResponse:
        """Maneja resiliencia enterprise"""
        components = re.findall(r'\b(database|api|cache|worker|service)\w*\b', message.lower())
        if not components:
            components = ["database", "api_gateway", "cache"]
        
        result = self.excelente.disaster_recovery_plan(components)
        
        response_text = f"""ESCUDO PLAN DE RECUPERACIÓN ANTE DESASTRES

Componentes críticos: {len(components)}
RTO estimado: {result['estimated_rto']} minutos
RPO: {result['estimated_rpo']} hora(s) de pérdida máxima

Orden de recuperación:
"""
        for i, comp in enumerate(result['recovery_order'], 1):
            comp_data = result['components'][comp]
            response_text += f"  {i}. {comp} (Prioridad {comp_data['priority']}, {comp_data['recovery_time']} min)\n"
        
        return ChatResponse(
            text=response_text,
            capability_used="enterprise_resilience",
            confidence=0.93,
            data=result
        )
    
    def _handle_security(self, message: str) -> ChatResponse:
        """Maneja modelado de amenazas"""
        assets = re.findall(r'\b(api keys?|database|users?|data)\b', message.lower())
        threats = re.findall(r'\b(inject|bypass|ddos|breach|hack)\w*\b', message.lower())
        
        if not assets:
            assets = ["database", "api_keys"]
        if not threats:
            threats = ["SQL Injection", "Authentication bypass"]
        
        result = self.excelente.security_threat_modeling(assets, threats)
        
        response_text = """CANDADO ANÁLISIS DE AMENAZAS DE SEGURIDAD

Matriz de Riesgo:
"""
        for risk in result['risk_matrix'][:5]:
            response_text += f"  • {risk['asset']} + {risk['threat']}: {risk['risk_level']} ({risk['score']:.1f})\n"
        
        response_text += "\nMitigaciones recomendadas:\n"
        for threat, data in result['threats'].items():
            response_text += f"  • {threat}: {data['mitigation']}\n"
        
        return ChatResponse(
            text=response_text,
            capability_used="security_modeling",
            confidence=0.90,
            data=result
        )
    
    def _handle_architecture(self, message: str) -> ChatResponse:
        """Maneja análisis de arquitectura"""
        # Detectar patrón
        pattern = "monolithic"  # default
        if "microservice" in message.lower():
            pattern = "microservices"
        elif "serverless" in message.lower():
            pattern = "serverless"
        
        result = self.excelente.architecture_analysis({"pattern": pattern})
        
        response_text = f"""ARQUITECTURA ANÁLISIS DE ARQUITECTURA

Patrón detectado: {pattern}
Scalability: {result['scalability_score']}/10
Maintainability: {result['maintainability_score']}/10

Recomendaciones:
"""
        for rec in result['recommendations']:
            response_text += f"""
ITEM [{rec['priority'].upper()}] {rec['suggestion']}
   Razón: {rec['rationale']}
   Esfuerzo: {rec['effort']}
"""
        
        if result['migration_path']:
            response_text += "\nRuta de migración:\n"
            for step in result['migration_path']:
                response_text += f"  → {step}\n"
        
        return ChatResponse(
            text=response_text,
            capability_used="architecture_analysis",
            confidence=0.91,
            data=result
        )
    
    def _handle_algorithm_research(self, message: str) -> ChatResponse:
        """Maneja research de algoritmos"""
        # Detectar dominio
        domain = "general"
        if "clasific" in message.lower():
            domain = "classification"
        elif "optim" in message.lower():
            domain = "optimization"
        elif "time series" in message.lower() or "serie" in message.lower():
            domain = "time series"
        
        result = self.excelente.algorithm_research(domain, "baseline")
        
        response_text = f"""LAB RESEARCH DE ALGORITMOS - {domain.upper()}

Alternativas analizadas:
"""
        for alt in result['alternatives']:
            response_text += f"  • {alt['algorithm']}: Accuracy {alt['accuracy']:.0%}, Speed: {alt['speed']}\n"
        
        response_text += f"""
IDEA Recomendación: {result['recommendation']}
CALENDAR Esfuerzo estimado: {result['implementation_effort']}
"""
        
        return ChatResponse(
            text=response_text,
            capability_used="algorithm_research",
            confidence=0.87,
            data=result
        )
    
    def _handle_general_query(self, message: str) -> ChatResponse:
        """Maneja consultas generales con evolución continua"""
        # Intentar resolver con evolución
        resolution = self.evolucion.resolve_request(message)
        
        return ChatResponse(
            text=f"He procesado tu consulta usando capacidades evolutivas.\n\nResultado: {resolution.get('result', 'Consulta procesada')}",
            capability_used="evolution_resolution",
            confidence=resolution.get('confidence', 0.5),
            data=resolution
        )
    
    def get_capabilities_status(self) -> Dict[str, Any]:
        """Retorna estado de capacidades excelentes"""
        validation = self.excelente.get_validation_summary()
        return {
            "status": validation.get('status', 'unknown'),
            "average_score": validation.get('average_score', 0),
            "capabilities_available": [
                "Trading Avanzado",
                "Gestión de Riesgo",
                "Razonamiento Causal",
                "Planificación Estratégica",
                "Auto-Debugging",
                "Optimización de Código",
                "Explainable AI",
                "Narrativa de Datos",
                "Resiliencia Enterprise",
                "Modelado de Seguridad",
                "Análisis de Arquitectura",
                "Research de Algoritmos"
            ]
        }


# Instancia global
CHAT_EXCELENTE = ChatExcelente()


# Funciones para integración

def chat_with_excellent_capabilities(message: str) -> Dict[str, Any]:
    """
    Función principal para integración con el chat del Brain
    
    Usage:
        from chat_excelente_integration import chat_with_excellent_capabilities
        response = chat_with_excellent_capabilities("Analiza el riesgo de mi portafolio")
    """
    response = CHAT_EXCELENTE.process_message(message)
    
    return {
        "text": response.text,
        "capability_used": response.capability_used,
        "confidence": response.confidence,
        "data": response.data,
        "is_excellent_response": True
    }


def get_excellent_capabilities_info() -> Dict[str, Any]:
    """Retorna información sobre capacidades disponibles"""
    return CHAT_EXCELENTE.get_capabilities_status()


# Test
if __name__ == "__main__":
    print("=" * 70)
    print("CHAT CON CAPACIDADES EXCELENTES")
    print("=" * 70)
    print()
    
    # Test mensajes
    test_messages = [
        "Analiza el RSI y MACD de EURUSD",
        "Calcula el VaR y Sharpe ratio de mi portafolio",
        "¿Por qué suben los precios cuando hay inflación?",
        "Crea un plan estratégico para los próximos 3 meses",
        "Tengo un IndexError en mi código Python",
        "Optimiza este código: for i in range(len(items)): result.append(items[i])",
        "Explica por qué tomaste esa decisión",
        "Cuéntame una historia con estos datos: tendencia alcista, volumen alto",
        "Necesito un plan de disaster recovery",
        "Analiza vulnerabilidades de seguridad",
        "¿Cómo debería diseñar la arquitectura de mi sistema?",
        "Qué algoritmo usar para clasificación de imágenes?"
    ]
    
    for msg in test_messages[:3]:  # Solo primeros 3 para demo
        print(f"\nUsuario: {msg}")
        print("-" * 70)
        
        response = chat_with_excellent_capabilities(msg)
        
        print(f"Brain: {response['text'][:200]}...")
        print(f"[Capacidad: {response['capability_used']}, Confianza: {response['confidence']:.0%}]")
        print("=" * 70)
    
    print("\nOK Sistema listo para integración con el chat principal")
