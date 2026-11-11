# Validacion de la idea de "primer rebote" de Yoel Sardinas

Fecha: 2026-10-25  
Periodo fuera de muestra unico: 2020-01-01 a 2025-12-31  
Capital inicial: USD 100,000  
Plataforma: QuantConnect Cloud / LEAN

## Veredicto

La formulacion estudiada **no queda demostrada como estrategia rentable y robusta**.
El patron tiene algo de informacion economica en acciones y opciones largas, pero la
rentabilidad es demasiado baja, inestable y concentrada para superar el gate
preregistrado. Los spreads debit enviados a mercado son directamente inoperables.

## Hipotesis congelada antes del test

Se probo el primer toque/rebote de SMA20, SMA40, SMA100 o SMA200 dentro de una
alineacion tendencial horaria, confirmada por tendencia diaria, pendiente de SMA20,
Bollinger, vela de rechazo y volumen relativo. Cada media podia disparar una sola vez
por regimen. No se permitio promediar ni reforzar posiciones.

Vehiculos:

1. Accion: riesgo 0.5%, stop 0.5 ATR detras de la media, objetivo 2R y salida a cinco sesiones.
2. Opcion larga: ligeramente ITM, 21-45 DTE, riesgo de prima 1%, objetivo 30% y las mismas invalidaciones.
3. Spread debit: misma opcion larga mas la primera pata OTM, mismo vencimiento y reglas de salida.

Gate: retorno y CAGR positivos; Sharpe >= 0.75; profit factor >= 1.20;
drawdown <= 20%; al menos 150 operaciones; 4/6 anos positivos; 55% de
subyacentes positivos; ningun activo > 35% del beneficio bruto.

## Resultados

| Vehiculo | Retorno | CAGR | Sharpe | Drawdown | PF neto | Entradas | Anos + | Activos + | Estado |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Acciones | +6.13% | +1.00% | -1.03 | 4.60% | 1.17 | 284 | 3/6 | 7/15 | NO-GO |
| Opcion larga | +1.33% | +0.22% | -0.48 | 13.10% | 1.05 | 197 | 4/6 | 5/13 | NO-GO |
| Spread debit a mercado | -104.67% | 0.00% | -0.73 | 104.70% | 0.58 | 88 | 0/3 | 0/15 | INVALIDO/NO-GO |

El spread consumio el capital durante 2022, produjo 200 rechazos de cierre y termino
con exposicion residual. El mecanismo combo atomico corrigio el problema inicial de
patas independientes, pero no el coste extremo de cruzar mercados de opciones poco
liquidas. No debe considerarse una implementacion operable.

## Atribucion

Acciones por ano, PnL neto:

- 2020: +2,065.69
- 2021: -1,112.69
- 2022: +6,067.47
- 2023: -81.72
- 2024: -1,009.39
- 2025: +146.50

Opciones largas por ano, PnL neto:

- 2020: -478.61
- 2021: -3,622.17
- 2022: +648.28
- 2023: +1,511.56
- 2024: +1,524.65
- 2025: +1,747.43

La opcion larga depende principalmente de XPEV (+6,871.79) y META/FB
(+2,523.34). Solo cinco de trece subyacentes fueron positivos. Sin XPEV, la
variante habria perdido dinero. En acciones ocurre una concentracion parecida:
XPEV y NIO explican mas que el beneficio neto total y compensan numerosos activos
negativos.

## Que queda rescatable

1. El concepto de rebote en tendencia puede servir como **feature contextual**, no como sistema completo.
2. La expresion en acciones fue mucho menos fragil que las opciones y preservo capital.
3. Las opciones largas mejoraron desde 2022, pero no compensaron theta, spreads y baja tasa de acierto.
4. SMA20 genero la mayoria de senales; SMA200 no genero ninguna bajo la definicion estricta. La teoria de cuatro medias no recibio apoyo uniforme.

## Decision

No desplegar esta estrategia ni seguir ajustandola sobre 2020-2025. Hacerlo ahora
seria optimizacion sobre el conjunto de prueba. Si se desea continuar la linea de
investigacion, el siguiente experimento debe formular una hipotesis nueva y evaluarla
en datos no usados, por ejemplo 2010-2019 o un walk-forward posterior, usando el
rebote solo como una variable dentro de un modelo de regimen/catalizador. No usar
spreads a mercado; cualquier estudio futuro de spreads debe usar combos limitados,
liquidez minima y un modelo explicito de probabilidad de fill.

## Artefactos

- `FIRST_REBOUND_SPEC.md`: preregistro.
- `first_rebound_stock_raw.json`: resultado QC de acciones.
- `first_rebound_long_option_raw.json`: resultado QC de opcion larga.
- `first_rebound_debit_spread_raw.json`: resultado QC del spread.
- `first_rebound_summary.json`: resumen reproducible.
- `analyze_first_rebound.py`: consolidacion y gates.
