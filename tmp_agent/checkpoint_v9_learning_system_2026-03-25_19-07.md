# Checkpoint: Sistema de Aprendizaje Brain V9

**Fecha:** 2026-03-25 19:07  
**Sesión:** Implementación de Sistema de Aprendizaje Real

## Resumen

Se implementó un sistema de aprendizaje que permite a Brain V9 realmente mejorar y ejecutar trades, en lugar de quedarse en estado "skipped" indefinidamente.

## Cambios Implementados

### 1. Archivos Creados

#### `brain_v9/util.py`
- **Funciones de skip counter:**
  - `get_consecutive_skips()`: Obtiene contador actual
  - `increment_skips_counter(reason)`: Incrementa y registra razón
  - `reset_skips_counter()`: Resetea a cero después de ejecución
  - `get_skip_status()`: Retorna estado completo con historial
- **Persistencia en:** `state/autonomy_skip_state.json`

#### `brain_v9/trading/utility_util.py`
- **Funciones de U history:**
  - `update_u_history(u_proxy_score, reason, trades_count, additional_data)`: Registra movimiento de U
  - `get_u_history(limit)`: Obtiene historial reciente
  - `get_u_trend(period)`: Calcula tendencia (1h, 24h, 7d)
  - `clear_u_history()`: Limpia historial (con precaución)
- **Persistencia en:** `state/utility_u_history.json`

### 2. Archivos Modificados

#### `brain_v9/config.py`
- Agregado `BRAIN_V9_PATH` para rutas de utilidades

#### `brain_v9/autonomy/action_executor.py`
**Cambios clave en `run_paper_trades()`:**
- ✅ Forzado de ejecución después de 3 skips consecutivos
- ✅ Registro automático de skips con razón
- ✅ Actualización de U history después de cada ejecución
- ✅ Reducción de threshold de calidad de muestra de 0.85 a 0.55
- ✅ Early return con información detallada cuando no hay ejecución

**Lógica de forzado:**
```python
if current_skips >= 3:
    should_execute = True
    execution_reason = f"Forzando ejecución por {current_skips} skips consecutivos"
```

#### `00_identity/autonomy_system/dashboard_server.py`
**Nuevos endpoints de datos:**
- Carga de `autonomy_skip_state.json` para métricas de skips
- Carga de `utility_u_history.json` para tendencias
- Conteo de trades de hoy desde scorecard
- `learning_metrics` en respuesta de autonomy_loop:
  - `consecutive_skips`: Número actual
  - `trades_today`: Conteo diario
  - `u_history_entries`: Total de registros U
  - `u_trend`: Tendencia calculada
  - `last_successful_trade`: Último trade exitoso

#### `00_identity/autonomy_system/unified_dashboard.html`
**Nuevas tarjetas en dashboard:**
1. **Skips Consecutivos**: Muestra contador actual con color de alerta
   - Verde: 0 skips
   - Naranja: 1-2 skips
   - Rojo: 3+ skips (forzando ejecución)

2. **Trades Hoy**: Contador diario con timestamp del último

3. **Estado Ejecución**: Indica si está PAUSADO o ejecutando
   - Muestra razón del skip si aplica
   - Muestra sample quality del candidato

**Sección Loop Autónomo mejorada:**
- Estado visual claro (Running/Stopped)
- Razones de skips visibles
- Información de candidato intentado
- Trades ejecutados hoy
- Último trade exitoso

## Lógica de Aprendizaje Implementada

### Flujo de Ejecución:

1. **Verificación normal:**
   - ¿Hay señal válida? → Ejecutar
   - ¿Sample quality < 0.55? → Ejecutar (necesita más muestras)

2. **Forzado por skips:**
   - Contador ≥ 3? → Forzar ejecución independientemente de condiciones
   - Ejecutar con estrategia disponible (aunque no sea óptima)
   - Resetear contador después de ejecución

3. **Registro de resultados:**
   - Si skip: Incrementar contador, registrar en U history con score 0
   - Si ejecución: Actualizar U history con score real y trades count

### Archivos de Estado:

```
tmp_agent/state/
├── autonomy_skip_state.json        # Contador de skips
├── utility_u_history.json          # Historial de U scores
└── ...
```

## Próximos Pasos Sugeridos

1. **Verificar funcionamiento:**
   - Reiniciar Brain V9
   - Monitorear dashboard para confirmar skips y ejecuciones forzadas
   - Verificar que U history se está actualizando

2. **Ajustes finos:**
   - Ajustar threshold de skips (actual: 3) según comportamiento
   - Ajustar sample quality threshold (actual: 0.55) si es necesario

3. **Extensiones futuras:**
   - Implementar ajuste automático de parámetros basado en historial
   - Agregar más métricas de aprendizaje (win rate, drawdown, etc.)

## Notas Técnicas

- **Sin breaking changes:** Todo el código es aditivo
- **Persistencia automática:** Los contadores se guardan en JSON
- **Resiliente:** Si archivos no existen, se crean automáticamente
- **Thread-safe:** Las funciones manejan estado en memoria + disco

## Testing

Para verificar el funcionamiento:

1. Dashboard en http://127.0.0.1:8070
2. Verificar nuevas tarjetas: "Skips Consecutivos", "Trades Hoy", "Estado Ejecución"
3. Sección "Loop Autónomo" debe mostrar:
   - Estado actual (Running/Stopped)
   - Razón de skips si aplica
   - Información de candidatos

---
**Checkpoint creado:** 2026-03-25 19:07 UTC  
**Versión:** Brain V9 + Sistema de Aprendizaje v1.0
