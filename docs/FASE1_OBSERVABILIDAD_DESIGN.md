# Fase 1 - Observabilidad del Routing: Diseño Técnico

## Fecha: 2025-01-09
## Status: EN IMPLEMENTACIÓN
## Autor: Claude Code

## 1. Objetivo

Implementar observabilidad completa del sistema de routing sin alterar decisiones de routing existentes.

## 2. Cambios Realizados

### 2.1 ChatMetrics Extended (✅ IMPLEMENTADO)

**Archivo:** `tmp_agent/brain_v9/core/session.py`

#### Nuevos campos en `self.data`:
```python
"routing_log": []  # Last 100 routing decisions
```

#### Nuevos métodos:

**`record_routing_decision()`**
- Registra cada decisión de routing con candidatos evaluados
- Mantiene buffer circular de 100 entradas
- Persiste últimas 10 decisiones a `routing_log_recent.json`

**`get_routing_stats()`**
- Calcula estadísticas de routing
- Detecta patrones de overfire
- Retorna: route_distribution, guard_frequency, suspicious patterns

**`_detect_overfire_candidates()`**
- Detecta 3 patrones sospechosos:
  1. `trading_hijack`: Trading fastpath con términos de routing
  2. `high_score_blocked`: Candidato alto score fue bloqueado
  3. `ui_edit_overfire`: UI edit en solicitud de análisis

### 2.2 Instrumentación de chat() (🔄 EN PROGRESO)

**Modificaciones necesarias en cada punto de decisión:**

```python
# Ejemplo para cada route en chat():

# 1. Empty message
_routing_candidates.append({
    "name": "empty_message",
    "score": 1.0 if not msg_stripped else 0.0,
    "blocked": bool(msg_stripped),
    "reason": "message_not_empty" if msg_stripped else None
})

# 2. Slash commands  
_routing_candidates.append({
    "name": "slash_command",
    "score": 1.0 if msg_stripped.startswith("/") else 0.0,
    "blocked": not msg_stripped.startswith("/"),
    "reason": "not_slash_command" if not msg_stripped.startswith("/") else None
})

# Similar para cada ruta...
```

## 3. Tests Planificados

### 3.1 Tests de ChatMetrics Extended

```python
# test_chat_metrics_routing_log.py

def test_record_routing_decision_creates_entry():
    """Verify routing decision is recorded with all fields."""
    
def test_routing_log_circular_buffer_limits_to_100():
    """Verify only last 100 decisions are kept."""
    
def test_get_routing_stats_returns_valid_structure():
    """Verify stats dict has expected keys."""
    
def test_detect_overfire_finds_trading_hijack():
    """Verify trading hijack pattern is detected."""
    
def test_detect_overfire_finds_ui_edit_overfire():
    """Verify UI edit overfire pattern is detected."""
```

### 3.2 Tests de Instrumentación

```python
# test_chat_routing_instrumentation.py

def test_empty_message_records_routing_decision():
    """Verify empty message route is logged."""
    
def test_slash_command_records_candidates():
    """Verify slash command decision logs all candidates."""
    
def test_fastpath_records_negative_guards():
    """Verify fastpath negative guards are logged."""
    
def test_agent_route_records_intent_confidence():
    """Verify agent route logs intent and confidence."""
```

## 4. Archivos a Modificar

1. ✅ `tmp_agent/brain_v9/core/session.py` - ChatMetrics extended
2. 🔄 `tmp_agent/brain_v9/core/session.py` - chat() instrumentation
3. ⏳ `tests/unit/test_chat_metrics_extended.py` - Nuevos tests
4. ⏳ `tests/unit/test_routing_instrumentation.py` - Tests de integración

## 5. Riesgos Mitigados

| Riesgo | Mitigación |
|--------|-----------|
| Performance | Buffer circular limitado, persistencia async |
| Privacidad | Message preview truncado a 200 chars |
| Breaking changes | Solo agrega datos, no modifica lógica |
| Storage | Archivo separado, 10 últimas decisiones |

## 6. Métricas Esperadas

Post-implementación, el sistema debería poder responder:

- ¿Cuántas veces se activó cada ruta en las últimas 100 decisiones?
- ¿Qué guards negativos se activaron con más frecuencia?
- ¿Cuántos candidatos se evaluaron por decisión en promedio?
- ¿Existen patrones de overfire (trading_hijack, ui_edit_overfire)?
- ¿Cuál es la distribución de latencias de decisión?

## 7. Próximos Pasos

### Fase 1.3: Tests exhaustivos
- Implementar tests unitarios para ChatMetrics extended
- Implementar tests de integración para instrumentación
- Verificar no regressions en routing existente

### Fase 2: Overfire Analytics
- Dashboard de routing patterns
- Alertas de overfire detection
- Trend analysis

### Fase 3: Arbitration Advisory
- Warnings sin cambio de route
- Score visualization
- Recommendation engine

### Fase 4: Soft Arbitration (si se justifica)
- Reranking basado en evidence
- Override condicional
- A/B testing de routes

## 8. Checklist de Implementación

- [x] Diseño técnico documentado
- [x] ChatMetrics extended con routing_log
- [ ] chat() instrumentado con candidate tracking
- [ ] Tests unitarios pasando
- [ ] Tests de integración pasando
- [ ] Documentación actualizada
- [ ] Performance validada
- [ ] Sin breaking changes

## 9. Decision Log

**2025-01-09 14:30 UTC**: Decidido implementar Fase 1 completa antes de continuar a Fase 2.
**2025-01-09 14:35 UTC**: ChatMetrics extended implementado sin errores de sintaxis.
**2025-01-09 14:40 UTC**: En progreso: instrumentación de chat().

---

**Nota**: Este documento es un living document y se actualizará conforme avance la implementación.
