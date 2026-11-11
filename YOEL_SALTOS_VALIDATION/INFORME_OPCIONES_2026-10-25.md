# Validacion directa con opciones de los principios de Yoel Sardinas

Fecha: 2026-10-25  
Motor: QuantConnect LEAN Cloud  
Periodo congelado: 2022-01-01 a 2025-12-31  
Capital inicial: USD 100,000

## Pregunta

La prueba anterior operaba acciones. Esta prueba mantiene la misma senal
post-shock preseleccionada y cambia exclusivamente el vehiculo: compra opciones
semanales OTM de acuerdo con los principios explicitamente descritos en las
transcripciones.

Principios implementados:

- call cuando la senal es alcista y put cuando es bajista;
- vencimiento mas proximo util (2-10 dias, evitando 0DTE);
- strike OTM mas cercano;
- venta limit GTC al 35% sobre el costo medio real;
- sin stop discrecional;
- salida antes de expiracion o tras tres sesiones;
- variante separada con un unico refuerzo al caer la prima 80%, sin invertir en
  el refuerzo mas capital que en la entrada original.

Las ordenes utilizaron datos historicos reales de contratos, modelo de Interactive
Brokers, bid/ask disponible y USD 0.01 adicional de slippage por contrato. No se
fabricaron precios ni fills.

## Resultados

| Metrica | Opciones base | Opciones con refuerzo |
|---|---:|---:|
| Retorno total | **-3.407%** | **-7.927%** |
| CAGR | -0.862% | -2.043% |
| Sharpe oficial | -1.197 | -1.090 |
| Drawdown maximo | 10.1% | 13.5% |
| Posiciones cerradas | 63 | 63 |
| Win rate | 67% | 71% |
| Profit factor neto | 0.886 | 0.806 |
| Ratio ganancia/perdida | 0.45 | 0.32 |
| Objetivos +35% | 42 | 45 |
| Salidas por tiempo/DTE | 21 | 18 |
| Refuerzos | 0 | 13 |
| Comisiones | USD 1,343.60 | USD 2,762.10 |
| PnL neto | **-USD 3,406.66** | **-USD 7,926.72** |

Backtests reproducibles:

- Base: proyecto 38448505, backtest `98d525581ad60a57956e7f78a7d2e7eb`.
- Refuerzo: proyecto 38448505, backtest `3d366fa1b825428d629b847d1831a031`.

## Robustez temporal

| Ano | Base | Refuerzo |
|---|---:|---:|
| 2022 | +USD 3,444.46 | +USD 1,431.76 |
| 2023 | -USD 1,043.05 | -USD 1,119.02 |
| 2024 | -USD 2,297.70 | -USD 6,191.05 |
| 2025 | -USD 3,510.37 | -USD 2,048.41 |

Solo uno de cuatro anos fue positivo en ambas variantes. El resultado no es una
perdida aislada ni una mala fecha de inicio: la ventaja desaparece durante tres
anos consecutivos.

## Comparacion limpia con acciones

Al filtrar la prueba oficial de acciones al mismo universo de 15 subyacentes:

- acciones: 64 operaciones, aproximadamente **+USD 3,197.65** (+3.20%);
- opciones base: 63 operaciones, **-USD 3,406.66** (-3.41%);
- opciones con refuerzo: 63 posiciones, **-USD 7,926.72** (-7.93%).

La expresion en opciones no amplifico una ventaja economica; convirtio una senal
debilmente positiva en negativa.

## Por que falla aun con muchas operaciones ganadoras

El 35% se alcanza con frecuencia, pero el porcentaje de aciertos oculta una
asimetria desfavorable:

- En base, la ganancia media reportada fue 0.63% del portafolio y la perdida
  media -1.40%; la perdida media fue 2.22 veces mayor.
- Con refuerzo, la ganancia media fue 0.67% y la perdida media -2.08%; la perdida
  media fue 3.10 veces mayor.
- El tiempo y la proximidad al vencimiento destruyen rapidamente el valor de los
  contratos que no llegan al objetivo.
- Bid/ask y comisiones importan mucho en primas pequenas. Las comisiones
  consumieron USD 1,343.60 en base y USD 2,762.10 con refuerzo.
- El refuerzo aumenta exposicion precisamente en los casos cuyo movimiento
  inicial fracaso. Consiguio tres objetivos adicionales, pero empeoro el PnL en
  USD 4,520 y elevo el drawdown.

Los peores aportes base fueron LI, USO y XPEV. Excluirlos ahora mejoraria el
resultado retrospectivo, pero seria sobreajuste y no constituye evidencia de una
regla operable futura.

## Veredicto

**NO_GO.** Las opciones semanales OTM, el objetivo del 35% y el refuerzo descrito
en el curso no convierten esta senal en una estrategia rentable o robusta.

Esto no demuestra que ninguna estrategia de opciones pueda funcionar. Demuestra
algo mas acotado y util: bajo reglas ejecutables, costes reales y cuatro anos de
datos, estos principios concretos no sostienen la promesa economica. El refuerzo
es especialmente perjudicial.

La afirmacion de que 156 operaciones al 35% convierten USD 500 en USD 1 millon
trata cada operacion como si alcanzara el objetivo y omite perdidas, expiraciones,
spreads, comisiones, liquidez y secuencia de retornos. El backtest directo muestra
que esa aritmetica no describe el proceso real.

## Limites de la conclusion

- Se pruebo la senal post-shock congelada para aislar acciones frente a opciones;
  no se afirmo que represente toda interpretacion subjetiva posible del curso.
- El universo tiene activos preferidos del material con opciones historicas
  disponibles y liquidez razonable.
- Hubo 65 senales y 63 entradas, por debajo del minimo preregistrado de 100
  operaciones; aun asi, retorno, CAGR, Sharpe, profit factor y estabilidad anual
  fallaron independientemente.
- Probar otras reglas exige un nuevo preregistro y una nueva muestra. No se deben
  optimizar strikes, DTE o simbolos sobre estos resultados y presentar luego esa
  seleccion como validacion independiente.

