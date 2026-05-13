# Guía Explicativa de la Estrategia (Para Auditorio Sin Experiencia en Trading)

## 1) Objetivo de este documento

Este documento explica, en lenguaje simple:

1. Qué instrumento usa la estrategia y por qué.
2. Cómo decide cuándo invertir más o menos.
3. Cómo gana dinero y cómo puede perderlo.
4. Cómo se protege para evitar daños grandes.

La idea es que alguien sin experiencia financiera pueda entender el funcionamiento general.

---

## 2) ¿Qué es una estrategia algorítmica?

Es un sistema automático con reglas fijas.
No opera por intuición ni por emociones.

Piensa en un piloto automático:

- Si el clima está favorable, avanza más.
- Si detecta turbulencia, reduce velocidad.
- Si detecta peligro, activa frenos.

Eso mismo hace esta estrategia con el mercado.

---

## 3) ETFs, Futuros y Microfuturos: diferencia simple

### A) ETF (lo que usa este modelo promovido)

Un ETF es un “paquete” de activos que cotiza como una acción.
Ejemplo: `SPY` representa al índice S&P 500.

- Riesgo por unidad: moderado
- Uso: inversión y trading sistemático más estable
- Vencimiento: no tiene vencimiento como contrato

### B) Futuro

Es un contrato derivado sobre un activo (índice, petróleo, etc.).
Suele mover más dinero por contrato.

- Riesgo por contrato: alto
- Apalancamiento: alto
- Vencimiento: sí, por fecha de contrato

### C) Microfuturo

Es la versión pequeña del futuro (por ejemplo, 1/10 del tamaño).

- Riesgo por contrato: menor que el futuro grande
- Apalancamiento: sigue existiendo, pero más controlable
- Vencimiento: sí

### Resumen para auditorio

- Futuro = motor grande (más potencia, más riesgo)
- Microfuturo = motor mediano (más control)
- ETF = conducción más estable y simple

**Este documento describe la versión promovida que opera ETFs.**

---

## 4) ¿Qué activos opera esta estrategia?

Trabaja con tres bloques:

1. **Núcleo (core)**: activos principales de crecimiento/diversificación.
   - `SPY`, `QQQ`, `IWM`, `EFA`, `EEM`, `TLT`, `IEF`, `GLD`, `DBC`, `UUP`

2. **Defensivos (safe)**: para proteger capital cuando hay ruido o estrés.
   - `SHY`, `IEF`, `GLD`, `TLT`

3. **Agresivos (turbo)**: para acelerar cuando el mercado acompaña.
   - `TQQQ`, `SOXL`, `UPRO`, `TECL`

No compra todo al mismo tiempo. Selecciona según reglas de calidad y riesgo.

---

## 5) ¿Cómo “lee” el mercado?

Cada día clasifica el mercado en un estado (“régimen”):

1. `BULL_TREND` (alcista)
2. `STRESS_UPTREND` (alcista pero volátil)
3. `CHOP` (lateral, sin dirección clara)
4. `BEAR` (bajista)
5. `NEUTRAL` (intermedio)

Para decidir ese estado usa:

- Tendencia de precio frente a media de largo plazo
- Momentum (fuerza de subida/bajada)
- Señal de estrés (`VIXY`)

Importante: evita cambiar de estado por “ruido” de un solo día.

---

## 6) ¿Qué hace en cada estado?

- **BULL_TREND**: mayor exposición para capturar crecimiento.
- **STRESS_UPTREND**: sigue participando, pero con más control.
- **CHOP**: reduce exposición para evitar desgaste.
- **BEAR**: minimiza exposición direccional para proteger capital.
- **NEUTRAL**: nivel intermedio.

Esto evita usar la misma agresividad en todo momento.

---

## 7) ¿Cómo gana dinero la estrategia?

Gana dinero cuando se cumple esta secuencia:

1. Detecta correctamente un entorno favorable.
2. Asigna más peso a activos con mejor comportamiento relativo.
3. Esos activos suben durante el periodo en que están en cartera.
4. Al rebalancear, conserva ganadores y reduce lo que pierde fuerza.

### Ejemplo simple

- Semana 1: detecta régimen alcista.
- Aumenta peso en `SPY/QQQ` y algo de bloque turbo.
- Mercado sube.
- El valor de la cartera sube.

La ganancia no viene de “adivinar una vela”, sino de:

- Estar en los activos más fuertes,
- en el régimen correcto,
- con tamaño de posición adecuado.

---

## 8) ¿Cómo pierde dinero la estrategia?

Pierde dinero cuando ocurre una o varias de estas situaciones:

1. **Cambio de régimen brusco**
   - El mercado gira rápido y el sistema tarda en ajustar.

2. **Falsas señales**
   - Parece inicio de tendencia, pero el precio se revierte.

3. **Mercado lateral con ruido**
   - Muchos movimientos pequeños que desgastan resultados.

4. **Costos de ejecución**
   - Comisiones, slippage y fricción real reducen retorno neto.

### Ejemplo simple

- El sistema entra en modo de crecimiento.
- El mercado da un giro inesperado.
- Parte de la cartera cae antes del siguiente ajuste.

Por eso existen reglas de protección (sección siguiente).

---

## 9) ¿Cómo se protege para no “romper” la cuenta?

La estrategia usa varias capas de seguridad:

1. **Circuit breaker de drawdown**
   - Si la caída acumulada supera umbral, reduce/cierra riesgo y entra en cooldown.

2. **Límite de pérdida diaria (condicional por régimen)**
   - Si el día empeora más de lo permitido, bloquea nuevas acciones de riesgo.

3. **Throttle mensual (condicional por régimen)**
   - Si el mes entra en daño relevante, baja exposición automáticamente.

4. **Límite de cambio por rebalance**
   - Evita saltar de una posición a otra de forma extrema en un solo ajuste.

Objetivo: perder menos en escenarios malos y sobrevivir para capturar escenarios buenos.

---

## 10) Frecuencia operativa (qué tan seguido opera)

Para el modelo promovido actual (`V12F2_A_C30_W100`), la frecuencia observada fue:

- Aproximadamente **6 a 8 trades cerrados por mes**
- (y más órdenes técnicas de ajuste por rebalance)

Es un sistema activo, pero no de alta frecuencia extrema.

---

## 11) Rendimiento observado (histórico validado)

Métrica mostrada: **m_eq** (equivalente mensual del periodo evaluado)

- FULL: **1.94%/mes**
- OOS: **3.69%/mes**
- RECENT: **6.25%/mes**
- STRESS: **4.78%/mes**
- BEAR: **-0.11%/mes**

Lectura simple para auditorio:

- En entornos favorables recientes, acelera bien.
- En entornos bajistas puros, prioriza defensa (cerca de equilibrio, no de máxima ganancia).

**Nota obligatoria:** resultados pasados no garantizan resultados futuros.

---

## 12) Qué NO hace esta estrategia

- No garantiza ganancias todos los meses.
- No elimina el riesgo.
- No evita todas las pérdidas.
- No sustituye buena gestión de capital.

Es un sistema de probabilidad y disciplina, no una promesa fija.

---

## 13) Explicación final en una frase

> La estrategia busca estar más invertida cuando el mercado tiene mejores probabilidades y reducir exposición cuando el entorno se vuelve peligroso, para crecer de forma sostenida y controlar caídas.

---

## 14) Glosario rápido (30 segundos)

- **Régimen**: estado del mercado (alcista, bajista, etc.).
- **Drawdown**: caída desde el máximo alcanzado.
- **Rebalanceo**: ajuste de pesos de la cartera.
- **Slippage**: diferencia entre precio esperado y precio real de ejecución.
- **Momentum**: fuerza reciente del movimiento de precio.
