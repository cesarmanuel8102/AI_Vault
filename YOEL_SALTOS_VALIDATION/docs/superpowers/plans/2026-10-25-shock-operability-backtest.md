# Shock Operability Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar y ejecutar backtests reproducibles que determinen si la continuacion o reversion posterior a un shock tiene ventaja economica neta.

**Architecture:** Un nucleo puro calcula senales y estadisticas, un backtest independiente hace el barrido congelado y un algoritmo LEAN reproduce las familias finalistas en QuantConnect. La promocion a opciones depende del criterio GO del subyacente.

**Tech Stack:** Python, pandas/numpy, pytest, QuantConnect LEAN cloud.

**Spec:** `C:/AI_VAULT/YOEL_SALTOS_VALIDATION/OPERABILITY_SPEC.md`

## Global Constraints

- No look-ahead, costos no nulos y parametros congelados antes de OOS.
- No promedios a la baja.
- No estudiar opciones si las acciones no pasan GO.

## Review Focus

- Ajustes corporativos y barras ausentes no pueden crear gaps falsos.
- La senal de 30 minutos solo usa datos disponibles al entrar.
- Posiciones solapadas respetan limites de capital.
- Costos y slippage se aplican en entrada y salida.
- Resultados vacios o muestras pequenas deben producir NO_GO.

---

### Task 1: Nucleo de senales y metricas

**Files:**
- Create: `operability_core.py`
- Create: `test_operability_core.py`

- [ ] Escribir pruebas de normalizacion ATR, confirmacion intradia, sizing y criterio GO.
- [ ] Ejecutar pytest y observar RED.
- [ ] Implementar funciones puras minimas.
- [ ] Ejecutar pytest y observar GREEN.

### Task 2: Backtest independiente congelado

**Files:**
- Create: `independent_operability.py`
- Create: `operability_results.json`
- Create: `operability_trades.csv`

- [ ] Descargar/reutilizar datos ajustados y construir las tres familias.
- [ ] Aplicar costos, stops, objetivos, horizontes y limites de cartera.
- [ ] Calcular IS, validacion y OOS por familia/parametro.
- [ ] Congelar finalistas usando solo IS+validacion y evaluar OOS una vez.

### Task 3: Reproduccion QuantConnect

**Files:**
- Create: `Yoel Shock Operability 20261025/main.py`
- Create: `Yoel Shock Operability 20261025/config.json`

- [ ] Implementar en LEAN la mejor familia elegible o el control menos malo.
- [ ] Ejecutar cloud backtest y conservar ID, metricas, ordenes y logs.
- [ ] Comparar direccion y magnitud con el motor independiente.

### Task 4: Veredicto

**Files:**
- Create: `INFORME_OPERABILIDAD_2026-10-25.md`

- [ ] Aplicar literalmente el criterio GO.
- [ ] Documentar estabilidad, costos, sesgos y discrepancias.
- [ ] Decidir si procede una prueba de opciones, sin reinterpretar OOS.
