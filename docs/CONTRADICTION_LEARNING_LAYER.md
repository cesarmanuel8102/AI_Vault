# Contradiction Learning Layer (CLL)
## Sistema de Aprendizaje Estadístico de Contradicciones

**Fecha:** 2025-01-09  
**Autor:** Claude Code  
**Status:** ✅ IMPLEMENTADO

---

## 1. Resumen Ejecutivo

La **Contradiction Learning Layer** es un sistema estadístico que aprende de las contradicciones detectadas para mejorar la calidad del routing. A diferencia de los sistemas anteriores que solo **detectan** contradicciones, este sistema **aprende** patrones estadísticos y genera métricas accionables.

**Características principales:**
- ✅ Route Reliability Scoring
- ✅ Guard Effectiveness Scoring  
- ✅ False Positive Tracking
- ✅ Semantic Drift Detection
- ✅ Comprehensive Learning Summary

**Método:** Observabilidad + Analytics (NO cambia comportamiento)
**Tests:** 20/20 passing (100%)

---

## 2. Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│         CONTRADICTION LEARNING LAYER (CLL)                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Input: Routing outcomes with metadata                      │
│         ↓                                                   │
│  ┌─────────────────────────────────────┐                   │
│  │    record_routing_outcome()        │                   │
│  │                                     │                   │
│  │ • route_selected                   │                   │
│  │ • success/failure                  │                   │
│  │ • contradiction detected           │                   │
│  │ • coherence score                  │                   │
│  │ • guards triggered                 │                   │
│  │ • false positive flag              │                   │
│  └─────────────────┬──────────────────┘                   │
│                    ↓                                        │
│  ┌─────────────────────────────────────┐                   │
│  │    Statistical Learning Layer      │                   │
│  │                                     │                   │
│  │ ┌──────────────────────────────┐   │                   │
│  │ │ Route Reliability Scoring    │   │                   │
│  │ │ • Total uses per route       │   │                   │
│  │ │ • Success rate                 │   │                   │
│  │ │ • Contradiction rate           │   │                   │
│  │ │ • Risk score                   │   │                   │
│  │ └──────────────────────────────┘   │                   │
│  │                                     │                   │
│  │ ┌──────────────────────────────┐   │                   │
│  │ │ Guard Effectiveness Scoring  │   │                   │
│  │ │ • Total triggers             │   │                   │
│  │ │ • Prevented contradictions   │   │                   │
│  │ │ • False positive rate          │   │                   │
│  │ │ • Effectiveness score          │   │                   │
│  │ └──────────────────────────────┘   │                   │
│  │                                     │                   │
│  │ ┌──────────────────────────────┐   │                   │
│  │ │ False Positive Analytics     │   │                   │
│  │ │ • FP rate per route            │   │                   │
│  │ │ • Problematic routes           │   │                   │
│  │ └──────────────────────────────┘   │                   │
│  │                                     │                   │
│  │ ┌──────────────────────────────┐   │                   │
│  │ │ Semantic Drift Detection     │   │                   │
│  │ │ • Diversity scoring            │   │                   │
│  │ │ • Jaccard similarity           │   │                   │
│  │ │ • Drift indicators             │   │                   │
│  │ └──────────────────────────────┘   │                   │
│  └─────────────────┬──────────────────┘                   │
│                    ↓                                        │
│  ┌─────────────────────────────────────┐                   │
│  │    get_contradiction_learning_      │                   │
│  │           summary()                 │                   │
│  │                                     │                   │
│  │ • System health metrics             │                   │
│  │ • Risk assessment                   │                   │
│  │ • Actionable recommendations        │                   │
│  └─────────────────────────────────────┘                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Métricas Generadas

### 3.1 System Health Metrics

| Métrica | Descripción | Fórmula |
|---------|-------------|---------|
| **contradiction_rate** | % de routings con contradicciones | contradictions / total * 100 |
| **false_positive_rate** | % de falsos positivos | false_positives / total * 100 |
| **avg_coherence** | Coherencia promedio | sum(coherence_scores) / total |
| **routes_learned** | Número de routes analizados | count(unique_routes) |
| **guards_learned** | Número de guards analizados | count(unique_guards) |

### 3.2 Route Reliability Metrics

| Métrica | Descripción | Rango |
|---------|-------------|-------|
| **success_rate** | Tasa de éxito del route | 0.0 - 1.0 |
| **contradiction_rate** | Tasa de contradicciones | 0% - 100% |
| **avg_coherence** | Coherencia promedio | 0.0 - 1.0 |
| **reliability_score** | Score compuesto | 0.0 - 1.0 |
| **risk_score** | Score de riesgo | 0.0 - 2.0 |

### 3.3 Guard Effectiveness Metrics

| Métrica | Descripción | Rango |
|---------|-------------|-------|
| **total_triggers** | Veces que se activó | int |
| **prevented_contradictions** | Contradicciones prevenidas | int |
| **false_positives** | Falsos positivos | int |
| **effectiveness** | Efectividad | 0.0 - 1.0 |
| **false_positive_rate** | Tasa de FP | 0% - 100% |
| **block_rate** | Frecuencia de bloqueo | 0% - 100% |

### 3.4 Semantic Drift Indicators

| Métrica | Descripción | Interpretación |
|---------|-------------|----------------|
| **diversity_score** | Diversidad semántica | Alto = posible drift |
| **avg_similarity** | Similaridad promedio | Bajo = posible drift |
| **drift_detected** | Boolean de drift | True si diversity > 0.6 |
| **drift_level** | Nivel de drift | low/medium/high |

---

## 4. API de Learning

### 4.1 `record_routing_outcome()`

```python
def record_routing_outcome(
    self,
    route: str,
    success: bool,
    contradiction_detected: bool,
    coherence_score: float,
    guards_triggered: List[str],
    false_positive: bool = False,
) -> None:
```

**Registra un outcome de routing para aprendizaje estadístico.**

### 4.2 `get_route_reliability_scores()`

```python
def get_route_reliability_scores(self) -> Dict[str, Dict]:
```

**Retorna reliability scores para cada route.**

Ejemplo de retorno:
```python
{
    "trading_analysis": {
        "route": "trading_analysis",
        "total_uses": 50,
        "success_rate": 0.98,
        "contradiction_rate": 20.0,  # 20% of routings had contradictions
        "avg_coherence": 0.75,
        "reliability_score": 0.82,  # Combined metric
        "risk_score": 0.36,  # Higher = more risky
        "recommendation": "Route is moderately reliable - consider refinement",
    }
}
```

### 4.3 `get_guard_effectiveness_scores()`

```python
def get_guard_effectiveness_scores(self) -> Dict[str, Dict]:
```

**Retorna effectiveness scores para cada guard.**

Ejemplo:
```python
{
    "prefers_no_tools": {
        "guard": "prefers_no_tools",
        "total_triggers": 30,
        "prevented_contradictions": 25,
        "false_positives": 2,
        "effectiveness": 0.83,
        "false_positive_rate": 6.67,
        "block_rate": 15.0,
        "recommendation": "Guard is effective - monitor for false positives",
    }
}
```

### 4.4 `get_false_positive_analytics()`

```python
def get_false_positive_analytics(self, window_size: int = 100) -> Dict:
```

**Analiza patrones de falsos positivos.**

Ejemplo:
```python
{
    "status": "ok",
    "window_size": 100,
    "false_positive_rate": 15.0,  # 15% FP rate
    "total_false_positives": 15,
    "problematic_routes": [
        {"route": "agent", "fp_rate": 25.0, "count": 20},
    ],
    "recommendation": "Review routes with >30% FP rate",
}
```

### 4.5 `get_semantic_drift_indicators()`

```python
def get_semantic_drift_indicators(self, window_size: int = 100) -> Dict:
```

**Detecta drift semántico en el uso de routes.**

Ejemplo:
```python
{
    "status": "ok",
    "routes_analyzed": 5,
    "high_drift_detected": 2,
    "drift_indicators": {
        "fastpath": {
            "route": "fastpath",
            "diversity_score": 0.75,  # High diversity
            "avg_similarity": 0.25,  # Low similarity
            "drift_detected": True,
            "drift_level": "high",
            "recommendation": "Route keywords may be too broad",
        }
    },
}
```

### 4.6 `get_contradiction_learning_summary()`

```python
def get_contradiction_learning_summary(self) -> Dict:
```

**Genera un resumen comprensivo de todo el learning.**

Ejemplo:
```python
{
    "status": "ok",
    "total_recorded": 500,
    "system_health": {
        "contradiction_rate": 12.5,
        "false_positive_rate": 8.0,
        "avg_coherence": 0.82,
        "routes_learned": 8,
        "guards_learned": 5,
    },
    "route_reliability": {...},
    "guard_effectiveness": {...},
    "false_positive_analytics": {...},
    "semantic_drift": {...},
    "risk_assessment": {
        "level": "medium",
        "high_risk_routes": 2,
        "ineffective_guards": 1,
        "recommendations": [
            "Review 2 high-risk routes",
            "Refine 1 ineffective guards",
        ]
    }
}
```

---

## 5. Implementación

### 5.1 Ubicación

**Archivo:** `tmp_agent/brain_v9/core/session.py`  
**Clase:** `ChatMetrics`  
**Líneas:** ~1425-1700 (aproximadamente)

### 5.2 Data Structures

```python
self.data["contradiction_learning"] = [
    {
        "timestamp": "2025-01-09T14:30:00",
        "route": "agent",
        "success": True,
        "contradiction_detected": True,
        "coherence_score": 0.6,
        "guards_triggered": ["prefers_no_tools"],
        "false_positive": False,
    }
]  # Buffer circular: últimos 500

self.data["route_reliability"] = {
    "agent": {
        "total_uses": 100,
        "successes": 95,
        "contradictions": 20,
        "coherence_scores": [0.9, 0.8, 0.6, ...],  # últimos 100
    }
}

self.data["guard_effectiveness"] = {
    "prefers_no_tools": {
        "total_triggers": 50,
        "prevented_contradictions": 45,
        "false_positives": 5,
        "block_rate": 0.0,  # Calculado
        "effectiveness": 0.0,  # Calculado
    }
}
```

---

## 6. Tests

### 6.1 Suite de Tests

**Archivo:** `tests/unit/test_contradiction_learning_layer.py`  
**Tests:** 20 tests, 100% passing

### 6.2 Categorías

#### Route Reliability Tests (5)
- ✅ `test_route_reliability_empty_data`
- ✅ `test_route_reliability_single_success`
- ✅ `test_route_reliability_with_contradiction`
- ✅ `test_route_reliability_low_success`
- ✅ `test_route_reliability_multiple_routes`

#### Guard Effectiveness Tests (4)
- ✅ `test_guard_effectiveness_empty_data`
- ✅ `test_guard_effectiveness_highly_effective`
- ✅ `test_guard_effectiveness_prevented_contradiction`
- ✅ `test_guard_effectiveness_false_positive`

#### False Positive Tests (3)
- ✅ `test_false_positive_empty_data`
- ✅ `test_false_positive_rate_calculation`
- ✅ `test_false_positive_problematic_routes`

#### Semantic Drift Tests (3)
- ✅ `test_semantic_drift_insufficient_data`
- ✅ `test_semantic_drift_no_drift`
- ✅ `test_semantic_drift_high_diversity`

#### Learning Summary Tests (2)
- ✅ `test_learning_summary_empty_data`
- ✅ `test_learning_summary_comprehensive`

#### Real World Tests (3)
- ✅ `test_learning_trading_hijack_pattern`
- ✅ `test_learning_guard_effectiveness_over_time`
- ✅ `test_learning_false_positive_reduction`

---

## 7. Casos de Uso Reales

### Caso 1: Trading Hijack Learning

```python
# Después de 50 usos de trading_analysis
{
    "route": "trading_analysis",
    "total_uses": 50,
    "contradiction_rate": 40.0,  # 40% had contradictions!
    "risk_score": 0.72,
    "recommendation": "Route has issues - review and strengthen guards"
}

# Acción recomendada: Agregar más guards a trading fastpath
```

### Caso 2: Guard Effectiveness

```python
# Guard "prefers_no_tools" después de 100 usos
{
    "guard": "prefers_no_tools",
    "total_triggers": 100,
    "prevented_contradictions": 90,
    "false_positives": 5,
    "effectiveness": 0.90,  # 90% effective!
    "false_positive_rate": 5.0,
    "recommendation": "Guard is highly effective - keep as is"
}

# Acción: Mantener guard, monitorear FP rate
```

### Caso 3: False Positive Detection

```python
# Análisis de FP
{
    "false_positive_rate": 25.0,  # Alto!
    "problematic_routes": [
        {"route": "agent", "fp_rate": 30.0, "count": 40}
    ],
    "recommendation": "Review routes with >30% FP rate"
}

# Acción: Refinar guards en route "agent"
```

### Caso 4: Semantic Drift

```python
# Drift detection
{
    "route": "fastpath",
    "diversity_score": 0.75,  # Alta diversidad
    "drift_detected": True,
    "drift_level": "high",
    "recommendation": "Route keywords may be too broad"
}

# Acción: Especificar más keywords de fastpath
```

---

## 8. Integración con Sistema

### 8.1 Flujo de Integración

```python
# En chat() después de routing:
route_selected = self._maybe_fastpath(...) or self._route_to_llm(...)

# POST-ROUTING: Validar coherencia
coherence_report = self.chat_metrics.validate_semantic_coherence(...)

# POST-RESPONSE: Registrar para learning
self.chat_metrics.record_routing_outcome(
    route=route_selected,
    success=result.get("success", False),
    contradiction_detected=coherence_report["contradictions_detected"] > 0,
    coherence_score=coherence_report["coherence_score"],
    guards_triggered=guards_triggered,
    false_positive=is_false_positive,
)

# PERIÓDICAMENTE: Generar reporte de learning
learning_summary = self.chat_metrics.get_contradiction_learning_summary()
if learning_summary["risk_assessment"]["level"] == "high":
    send_alert("High risk routing patterns detected")
```

---

## 9. Zero Breaking Changes

### 9.1 Confirmación

- ✅ **Additive Only**: Solo métodos nuevos
- ✅ **No Modification**: No cambia lógica existente
- ✅ **Optional**: Learning es opt-in (llamada explícita)
- ✅ **Non-Destructive**: Solo observabilidad y analytics
- ✅ **Bounded Memory**: Buffer circular de 500 entries

### 9.2 Performance

- ✅ **O(1) Recording**: Append a lista
- ✅ **O(n) Analytics**: n = buffer size (max 500)
- ✅ **Lazy Evaluation**: Solo cuando se llama
- ✅ **No LLM Calls**: Solo operaciones aritméticas

---

## 10. Próximos Pasos Sugeridos

### Opción A: Dashboard de Learning
```python
GET /brain/learning/summary

Retorna:
{
    "system_health": {...},
    "risk_assessment": {...},
    "recommendations": [...]
}
```

### Opción B: Alertas Automáticas
```python
if risk_assessment["level"] == "high":
    send_alert(
        f"{risk_assessment['high_risk_routes']} high-risk routes detected",
        priority="high"
    )
```

### Opción C: Auto-Calibration (Futuro)
```python
# Basado en learning, sugerir calibraciones:
suggestions = generate_calibration_suggestions(learning_summary)
# Ejemplo: "Consider lowering threshold for trading_analysis"
```

---

## 11. Riesgos y Mitigaciones

| Riesgo | Mitigación | Status |
|--------|-----------|--------|
| Data bloat | Buffer circular (500 entries) | ✅ Mitigado |
| Performance | Lazy evaluation, O(n) | ✅ Mitigado |
| Overfitting | Window-based analysis | ✅ Mitigado |
| False conclusions | Confidence thresholds | ✅ Mitigado |

---

## 12. Archivos Entregados

1. ✅ `tmp_agent/brain_v9/core/session.py` - CLL implementado
2. ✅ `tests/unit/test_contradiction_learning_layer.py` - 20 tests
3. ✅ `docs/CONTRADICTION_LEARNING_LAYER.md` - Este documento

---

## 13. Checklist Final

- [x] Diseño técnico documentado
- [x] Route reliability scoring
- [x] Guard effectiveness scoring
- [x] False positive tracking
- [x] Semantic drift detection
- [x] Comprehensive learning summary
- [x] 20 tests unitarios, 100% passing
- [x] Tests de ejemplos reales
- [x] Zero breaking changes
- [x] NO auto-modificación de routing
- [x] Soft arbitration sigue OFF
- [x] Documentación completa

---

## 14. Conclusión

La **Contradiction Learning Layer** está **completamente implementada y probada**.

**Valor inmediato:**
- Aprende estadísticamente qué routes son confiables
- Identifica guards efectivos vs problemáticos
- Detecta falsos positivos y semantic drift
- Genera recommendations accionables

**Sin riesgo:**
- Solo observabilidad y analytics
- No modifica comportamiento
- Performance negligible
- Zero breaking changes

**Listo para:**
- Dashboard de learning
- Alertas de risk assessment
- Auto-calibration futuro

---

**Implementado por:** Claude Code  
**Fecha:** 2025-01-09  
**Status:** ✅ Producción-ready (observability mode)
