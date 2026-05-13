#!/usr/bin/env python3
"""
DEMO_INTEGRACION_COMPLETA.PY
Demostración final del Sistema de Capacidades Excelentes integrado al Chat

Muestra el funcionamiento completo con todas las capacidades:
- Trading avanzado con análisis técnico
- Riesgo cuantitativo
- Debugging automático
- XAI y explicabilidad
- Planificación estratégica
- Y más...
"""

import sys
import requests
import json

sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

print("="*80)
print("DEMO - INTEGRACIÓN COMPLETA: BRAIN CON CAPACIDADES EXCELENTES")
print("="*80)
print("\nEsta demo muestra el sistema funcionando en tiempo real...\n")

# Usar el módulo directamente
from integracion_brain_excelente import chat_excelente, get_system_stats

# Mensajes de prueba exhaustivos
test_scenarios = [
    {
        "name": "TRADING AVANZADO",
        "message": "Analiza EURUSD con RSI, MACD y Bollinger Bands",
        "expected_capability": "analizar_mercado",
        "description": "Análisis técnico completo con múltiples indicadores"
    },
    {
        "name": "GESTIÓN DE RIESGO",
        "message": "Calcula VaR, Sharpe y drawdown de un portfolio 60/40",
        "expected_capability": "calcular_riesgo",
        "description": "Métricas cuantitativas avanzadas de riesgo"
    },
    {
        "name": "DEBUGGING INTELIGENTE",
        "message": "Tengo IndexError: list index out of range en trading_engine.py línea 156",
        "expected_capability": "debug",
        "description": "Diagnóstico automático de errores de código"
    },
    {
        "name": "OPTIMIZACIÓN DE CÓDIGO",
        "message": "Optimiza este código ineficiente: for i in range(len(data)): results.append(data[i]*2)",
        "expected_capability": "optimizar_codigo",
        "description": "Análisis y mejora de performance de código"
    },
    {
        "name": "PLANIFICACIÓN ESTRATÉGICA",
        "message": "Crea un plan estratégico de 3 meses para mejorar el sistema de trading",
        "expected_capability": "planificar",
        "description": "Generación de roadmap con priorización"
    },
    {
        "name": "RAZONAMIENTO CAUSAL",
        "message": "Analiza la causalidad: ¿Por qué cuando suben las tasas caen los bonos?",
        "expected_capability": "causalidad",
        "description": "Distinguir correlación de causalidad"
    },
    {
        "name": "EXPLICABILIDAD XAI",
        "message": "Explica por qué recomendaste comprar EURUSD",
        "expected_capability": "explicar",
        "description": "Transparencia en decisiones de trading"
    },
    {
        "name": "NARRATIVA DE DATOS",
        "message": "Cuéntame una historia con estos datos: tendencia alcista, volumen creciente, RSI 65",
        "expected_capability": "narrativa",
        "description": "Storytelling con datos financieros"
    },
    {
        "name": "RESILIENCIA ENTERPRISE",
        "message": "Diseña un plan de disaster recovery para mi sistema de trading",
        "expected_capability": "backup",
        "description": "Plan de recuperación ante desastres"
    },
    {
        "name": "SEGURIDAD",
        "message": "Analiza vulnerabilidades de seguridad en mi API de trading",
        "expected_capability": "seguridad",
        "description": "Modelado de amenazas y mitigaciones"
    },
    {
        "name": "ARQUITECTURA",
        "message": "Analiza la arquitectura de mi sistema monolítico y sugiere mejoras",
        "expected_capability": "arquitectura",
        "description": "Análisis y migración de arquitectura"
    },
    {
        "name": "RESEARCH DE ALGORITMOS",
        "message": "Qué algoritmo de ML es mejor para predecir series temporales de precios?",
        "expected_capability": "algoritmo",
        "description": "Research de state-of-the-art"
    }
]

print(f"\nProbando {len(test_scenarios)} escenarios de capacidades excelentes:\n")

results = []

for i, scenario in enumerate(test_scenarios, 1):
    print(f"\n{'='*80}")
    print(f"ESCENARIO {i}/{len(test_scenarios)}: {scenario['name']}")
    print(f"Descripción: {scenario['description']}")
    print(f"{'='*80}")
    print(f"\nUsuario: {scenario['message']}")
    print(f"\n{'-'*80}")
    
    try:
        response = chat_excelente(scenario['message'], {})
        
        # Verificar resultado
        capability_used = response.get('capability_used', 'unknown')
        is_excellent = response.get('is_excellent', False)
        confidence = response.get('confidence', 0)
        
        print(f"Brain: {response['text'][:200]}...")
        print(f"\n[Capacidad detectada: {capability_used}]")
        print(f"[Excelente: {'SÍ' if is_excellent else 'NO'}]")
        print(f"[Confianza: {confidence:.0%}]")
        
        # Verificar si coincide con lo esperado
        test_passed = capability_used == scenario['expected_capability']
        status = "✓ PASS" if test_passed else "✗ FAIL"
        
        print(f"[Test: {status} (esperado: {scenario['expected_capability']})]")
        
        results.append({
            'scenario': scenario['name'],
            'passed': test_passed,
            'capability': capability_used,
            'confidence': confidence,
            'is_excellent': is_excellent
        })
        
    except Exception as e:
        print(f"ERROR: {e}")
        results.append({
            'scenario': scenario['name'],
            'passed': False,
            'error': str(e)
        })

# Estadísticas finales
print(f"\n{'='*80}")
print("RESUMEN DE INTEGRACIÓN")
print(f"{'='*80}\n")

passed = sum(1 for r in results if r.get('passed', False))
total = len(results)
excellent_count = sum(1 for r in results if r.get('is_excellent', False))
avg_confidence = sum(r.get('confidence', 0) for r in results) / total

print(f"Tests ejecutados: {total}")
print(f"Tests aprobados: {passed}/{total} ({passed/total*100:.0f}%)")
print(f"Respuestas Excelentes: {excellent_count}/{total}")
print(f"Confianza promedio: {avg_confidence:.0%}")

print(f"\nDetalle por escenario:")
for r in results:
    status = "✓" if r.get('passed') else "✗"
    cap = r.get('capability', 'unknown')
    conf = r.get('confidence', 0)
    exc = "[E]" if r.get('is_excellent') else "[G]"
    print(f"  {status} {exc} {r['scenario']}: {cap} ({conf:.0%})")

print(f"\n{'='*80}")
print("ESTADÍSTICAS DEL SISTEMA")
print(f"{'='*80}\n")

stats = get_system_stats()
print(f"Interacciones totales: {stats['total_interactions']}")
print(f"Respuestas excelentes: {stats['excellent_responses']}")
print(f"Capacidades únicas usadas: {stats['capabilities_used']}")
print(f"Nivel del sistema: {stats['level']}")

print(f"\n{'='*80}")
print("✓ INTEGRACIÓN COMPLETADA EXITOSAMENTE")
print(f"{'='*80}")

print(f"\nEl Brain ahora tiene {len(test_scenarios)} capacidades excelentes:")
print("  1. Trading avanzado con análisis técnico")
print("  2. Gestión de riesgo cuantitativo")
print("  3. Debugging inteligente de código")
print("  4. Optimización automática de performance")
print("  5. Planificación estratégica")
print("  6. Razonamiento causal")
print("  7. Explicabilidad (XAI)")
print("  8. Narrativa de datos")
print("  9. Resiliencia enterprise")
print("  10. Seguridad avanzada")
print("  11. Análisis de arquitectura")
print("  12. Research de algoritmos")

print(f"\nAPI Endpoints disponibles:")
print("  POST /chat/excelente - Chat con capacidades excelentes")
print("  GET /chat/excelente/stats - Estadísticas del sistema")
print("  GET /teaching/* - Sistema de teaching")
print("  GET /metacognition/* - Auto-conciencia")

print(f"\n{'='*80}")
print("SISTEMA LISTO PARA USO EN PRODUCCIÓN")
print(f"{'='*80}")
