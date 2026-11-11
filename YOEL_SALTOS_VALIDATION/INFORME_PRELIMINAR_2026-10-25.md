# Validacion de la estrategia de saltos de Yoel Sardinas

Fecha: 2026-10-25

## Veredicto

La afirmacion central del curso no supera la Fase A. La replica oficial en QuantConnect/LEAN midio una probabilidad fuera de muestra de 10,06% para un segundo gap de al menos 1% en la misma direccion, no 90%, frente a una frecuencia base comparable de 14,10%.

La conclusion es NO-GO para construir u optimizar la variante de opciones semanales OTM. Una fuente independiente produjo el mismo signo y orden de magnitud.

## Replica QuantConnect/LEAN

- Proyecto: `38446987`
- Backtest: `29f20d461fc2e5a847aaa9e8aeb1d719`
- LEAN: `2.5.0.0.18203`
- Periodo del algoritmo: 2008-2025; OOS definido desde 2022.
- Senales principales OOS U2: 616.
- Segundo salto: 10,06%.
- Frecuencia base: 14,10%.
- Lift: -4,03 puntos porcentuales.
- Intervalo Wilson 95%: 7,93%-12,69%.
- Tickers con lift positivo: 48,57%.
- Retorno intradia direccional medio de la sesion siguiente: +0,106%.
- Veredicto emitido por el algoritmo: `NO_GO`.
- Ordenes transmitidas: 0.

## Evidencia principal independiente

Datos: Yahoo Finance, OHLCV diario ajustado, 40 activos, 2008-02-29 a 2026-10-22.

Regla: gap >= 1%, SMA20/SMA40 compatible, sin gap >= 1% en las cinco sesiones anteriores, exclusion de volumen > 2,5 veces promedio 20 sesiones. OOS: 2022 en adelante.

| Universo / periodo | Exitos | Senales | Tasa segundo gap | Base | Lift | Retorno intradia direccional siguiente |
|---|---:|---:|---:|---:|---:|---:|
| U1 IS | 63 | 554 | 11,37% | 11,01% | +0,37 pp | +0,076% |
| U1 OOS | 26 | 209 | 12,44% | 18,99% | -6,55 pp | -0,090% |
| U2 IS | 182 | 1.916 | 9,50% | 9,85% | -0,35 pp | +0,051% |
| U2 OOS | 83 | 732 | 11,34% | 14,35% | -3,01 pp | +0,050% |

Intervalo Wilson 95% de la tasa principal U2 OOS: 9,24%-13,84%. El 90% alegado queda completamente fuera del intervalo.

Solo 47,2% de los 36 tickers con muestra suficiente tuvieron lift positivo, lejos del requisito preregistrado de 70%.

## Sensibilidad

Se probaron 64 combinaciones OOS: gaps de 0,5%, 1%, 1,5% y 2%; ventanas de 5/10 sesiones; tendencia normal/estricta; con/sin exclusion de volumen. Ninguna paso el criterio principal.

La mayor tasa OOS observada fue 21,62%, pero su base era 31,08%, por lo que no representa ventaja. El mejor lift fue +2,71 puntos porcentuales con gap de 2%, muy por debajo de los +10 puntos exigidos y con tasa absoluta de solo 8,09%.

## Evidencia previa en QuantConnect

Los backtests de opciones realizados en abril no constituyen una prueba preregistrada y sus reglas se alejaron de la version literal del curso, pero son evidencia secundaria consistente con sobreajuste:

| Variante | IS 2023-2024 | OOS 2025-2026 | Sharpe OOS |
|---|---:|---:|---:|
| G15 | +243,83% | -10,20% | -0,177 |
| G16 | +89,66% | -17,99% | -0,413 |
| G17 | +624,47% | -31,10% | -0,725 |
| V5a | +130,85% | -4,07% | -0,264 |

El patron es consistente: resultados espectaculares en la muestra usada para iterar y perdidas al congelar la regla fuera de muestra.

## Interpretacion economica

1. La frecuencia empirica no respalda que un primer salto anuncie otro con probabilidad cercana a 90%.
2. En OOS, la condicion principal selecciona dias con menor probabilidad de segundo gap que la base.
3. El retorno intradia medio posterior de +0,05% en U2 es demasiado pequeno para justificar opciones OTM semanales tras spread, theta y comisiones.
4. Limitar ganancias a +35% y aceptar perdidas cercanas a -100% requiere una tasa de acierto aproximada de 74% antes de costos; el curso no demuestra esa tasa.
5. Promediar a la baja un contrato que expira aumenta la cola de perdida y no repara la ausencia de senal en el subyacente.

## Limitaciones pendientes

- Replicar exactamente en QC/LEAN con la fuente institucional de QuantConnect.
- Sustituir el proxy de volumen por calendario real de earnings.
- Emparejar controles por terciles de ATR. Esto puede afinar un efecto pequeno, pero no es plausible que transforme 11% en 90%.
- Las expresiones subjetivas del curso admiten reinterpretaciones retrospectivas. Cualquier nueva definicion debe registrarse como una hipotesis nueva, no como correccion del OOS ya observado.

## Decision

La replica QC confirma estos ordenes de magnitud. La estrategia queda invalidada en su afirmacion central y no debe pasar a una nueva optimizacion de opciones. Una investigacion futura distinta podria estudiar gaps de 2% sobre el subyacente, pero ya no seria la promesa del curso ni justificaria por si sola opciones semanales OTM.
