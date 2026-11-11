# Variante concentrada: $500, una operacion diaria en apertura

Fecha: 26 de octubre de 2026  
Proyecto QuantConnect: `38449639`

## Configuracion

- Capital inicial: `$500`.
- Presupuesto por entrada: hasta `100%` del efectivo y equity disponibles.
- Maximo una entrada por sesion; no se fuerza una operacion si no hay senal.
- Ventana de seleccion: primera vela horaria, 09:30-10:30 ET; ejecucion en el
  primer dato posterior, normalmente 10:31 ET.
- Candidata diaria: mayor `volumen relativo x ubicacion direccional del cierre`
  entre las senales validas; desempate determinista.
- Delta objetivo `0.70`, `0DTE`, TP `10%`, filtro economico, salida causal a los
  15 minutos y cierre intradia sin cambios.
- No se abren nuevas entradas desde las 14:00 ET, aunque esta variante solo
  consume senales de la primera hora.

El 100% es un limite de presupuesto. La indivisibilidad de los contratos puede
dejar efectivo sin utilizar, y una opcion que cuesta mas que el equity disponible
se rechaza.

## Resultados

| Periodo | Final | Neto | Trades | Win rate | PF neto | Drawdown | Fees |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025 | $580.94 | +16.19% | 10 | 80% | 1.24 | 32.2% | $40.50 |
| 2026 a 25-oct | $726.86 | +45.37% | 14 | 71% | 1.32 | 59.5% | $71.10 |
| 2025 a 25-oct-2026, continuo | $798.64 | +59.73% | 24 | 75% | 1.27 | 43.4% | $118.00 |

Backtests:

- 2025: `17179d4ec23accd80230ff30ce16df89`
- 2026: `7d52e391c44220b7809edf849cbb282f`
- Combinado: `2a9aac7df62ad3361b4dc80988ff7a1a`

## Interpretacion

La concentracion aumenta mucho el retorno sobre el pequeno capital, pero no
mejora la calidad intrinseca de la estrategia. El PF neto combinado es solo
`1.27`, con 24 operaciones. Una operacion GLD de octubre de 2026 perdio cerca de
`$564` y explica gran parte del drawdown extremo. La secuencia combinada pudo
recuperarse y terminar en `$798.64`, pero una perdida similar mas temprano o dos
seguidas podrian dejar la cuenta sin capacidad para comprar otro contrato.

La conclusion correcta es: variante rentable en esta muestra y operable con
$500, pero economicamente fragil. Sirve como experimento agresivo, no como una
configuracion de riesgo sostenible demostrada.

## Optimizacion de entradas, simultaneidad y uso de capital

Se compararon cuatro formas de desplegar los mismos `$500`, manteniendo sin
cambios la senal de entrada, delta, DTE, TP y salida por fallo. Los resultados
combinados abarcan 2025 hasta el 25 de octubre de 2026.

| Variante | Capital final | Neto | Trades | Win rate | PF neto | Drawdown | Fees |
|---|---:|---:|---:|---:|---:|---:|---:|
| Una posicion, hasta 100% | $798.64 | +59.73% | 24 | 75% | 1.27 | 43.4% | $118.00 |
| Dos posiciones, 50% cada una | $776.92 | +55.38% | 20 | 90% | 1.91 | 23.1% | $58.40 |
| Hasta dos, asignacion adaptativa | $705.44 | +41.09% | 29 | 79% | 1.18 | 47.6% | $110.60 |
| Hasta tres, 33% cada una, solo 2025 | $587.19 | +17.44% | 3 | 100% | No significativo | 0.0% | N/D |

Backtests adicionales:

- Dos posiciones al 50%, combinado: `2a26154a609d0cafb994230c499b1a62`.
- Asignacion adaptativa, combinado: `1453014a8d9858bdea0f7c3df0f45707`.
- Tres posiciones al 33%, 2025: `b5b43bbe6cf6fb834d8fd64fcbc0db4d`.
- Fallo repetido desde minuto 5, 2025: `693309075ddd1774b31a9f8309c696a8`.

La asignacion adaptativa daba 50% a cada oportunidad cuando habia dos, pero
permitia usar hasta 100% cuando solo habia una. Produjo mas operaciones, pero
peor retorno y mas drawdown: concentro todo el riesgo precisamente en dias sin
diversificacion. Por tanto, queda rechazada.

La variante de tres posiciones tampoco es adecuada para una cuenta de `$500`:
unos `$166` por posicion no alcanzan para comprar la mayoria de los contratos
delta 0.70, por lo que el capital queda ocioso y la muestra cae a solo tres
operaciones.

Tambien se probo vigilar la salida de fallo cada cinco minutos desde el minuto
5. En 2025 termino en `$476.34` (`-4.73%`) y drawdown de `51.9%`, porque corto
recuperaciones validas. Se conserva la comprobacion unica y causal al minuto 15.

## Configuracion recomendada

La mejor configuracion por calidad economica y estabilidad es:

- Maximo dos posiciones simultaneas.
- Maximo dos entradas por dia, ambas derivadas de la primera hora.
- Hasta 50% del equity diario por posicion.
- Seleccionar las dos mejores senales por
  `volumen relativo x ubicacion direccional del cierre`.
- No reasignar automaticamente a una unica posicion la mitad reservada para la
  segunda oportunidad.
- Mantener delta `0.70`, `0DTE`, TP `10%`, filtro economico y salida causal unica
  al minuto 15.
- Cerrar cualquier posicion restante antes del cierre de la sesion.

Esta configuracion renuncia a unos `4.34` puntos porcentuales de retorno frente
a concentrar todo en una posicion, pero mejora el PF de `1.27` a `1.91` y reduce
el drawdown de `43.4%` a `23.1%`. Es el mejor intercambio observado.

"Usar todo el capital" debe interpretarse como mantenerlo disponible para las
dos mejores entradas, no como obligar a invertirlo en una sola. Con contratos
indivisibles y filtros de calidad siempre puede quedar efectivo residual. Forzar
su consumo empeoro los resultados en la prueba.

## Extension temporal bloqueada: 2020-2026

La configuracion recomendada `2 x 50%` se ejecuto sin recalibrar desde el 1 de
enero de 2020 hasta la ultima sesion completa disponible al 26 de octubre de
2026. El resultado contradice la aparente robustez observada en 2025-2026:

| Metrica | Resultado |
|---|---:|
| Capital inicial | $500.00 |
| Capital final | $266.35 |
| Retorno total | -46.73% |
| CAGR | -8.83% |
| Trades | 27 |
| Win rate | 81% |
| PF neto reconstruido | 0.55 |
| Drawdown maximo | 68.9% |
| Fees | $68.00 |

Backtest: `1c5ecca1ca2573d85b55c40f9d42cfa1`.

Contribucion neta de los trades cerrados dentro de la trayectoria compuesta:

| Ano | Trades | Win rate | PnL neto |
|---|---:|---:|---:|
| 2020 | 7 | 57% | -$296.77 |
| 2021 | 0 | N/D | $0.00 |
| 2022 | 6 | 83% | -$14.13 |
| 2023 | 6 | 100% | +$66.19 |
| 2024 | 4 | 75% | -$51.41 |
| 2025 | 1 | 100% | +$25.72 |
| 2026 | 3 | 100% | +$36.74 |

Las tres mayores perdidas fueron dos calls de NIO y una call de GLD en 2020:
`-$166.78`, `-$80.85` y `-$136.28`. Las ganancias pequenas y frecuentes no
compensaron esa cola: ganancia media `+4.89%` frente a perdida media `-28.23%`.

Despues de 2020 el capital reducido tampoco puede comprar muchos contratos
delta 0.70. Esto explica que 2025 y 2026 tengan menos operaciones dentro de la
trayectoria continua que en sus pruebas aisladas con `$500` reiniciados. No es
una inconsistencia: es dependencia de trayectoria y riesgo de ruina economica.

Conclusion revisada: `2 x 50%` es mejor que `1 x 100%` dentro de 2025-2026, pero
no es una estrategia rentable demostrada en distintos regimenes. No debe
promoverse para operacion real con todo el capital. El siguiente trabajo valido
seria disenar una contramedida de cola usando 2020-2024 como descubrimiento y
reservar 2025-2026 como validacion bloqueada; no ajustar retrospectivamente la
regla hasta que 2020 quede positiva.

## Escala de capital: $5,000 operativos y $1,000 de reserva

Se repitio exactamente la configuracion `2 x 50%` con `$5,000` disponibles para
el algoritmo. Los `$1,000` de reserva se mantuvieron conceptualmente fuera del
dimensionamiento y no se inyectaron durante el backtest.

| Metrica | Resultado operativo |
|---|---:|
| Capital inicial operado | $5,000.00 |
| Capital operativo final | $519.32 |
| Perdida operativa | -$4,480.68 |
| Retorno operativo | -89.61% |
| Drawdown | 95.4% |
| Trades | 50 |
| Win rate | 76% |
| PF neto reconstruido | 0.25 |
| Fees | $318.05 |

Incluyendo la reserva intacta, el patrimonio final seria `$1,519.32` sobre un
bankroll inicial total de `$6,000`, equivalente a `-74.68%`. Si la reserva se
hubiera inyectado para seguir operando, no existe evidencia de que mejoraria el
resultado; con expectativa negativa probablemente solo habria financiado mas
exposicion.

Backtest: `47369b378d792ee24eb96bb362536cf9`.

La mayor perdida fue una call AAPL 0DTE del 1 de mayo de 2020: cinco contratos,
prima inicial aproximada de `$2,549.50` y perdida neta de `$2,549.05`. Le
siguieron NIO con `-$1,042.37` y GLD con `-$953.92`. Una sola operacion supero
2.5 veces la reserva propuesta de `$1,000`.

Conclusion: aumentar el capital elimino parte del bloqueo por contratos
indivisibles, pero revelo mas claramente la expectativa negativa. `$1,000` de
reserva no protege `$5,000` operados al 50% por posicion. No existe una reserva
razonable que convierta esta version en rentable; primero debe limitarse la cola
de perdida por operacion y demostrarse una expectativa positiva fuera de muestra.

## Forense de la proteccion al minuto 15

La proteccion no estaba ausente, pero tampoco era un stop continuo. Con
`failure_repeat=false` se evaluaba una sola vez al alcanzar 15 minutos y solo
cerraba si coincidian estas tres condiciones:

1. al menos 15 minutos transcurridos;
2. retorno de la opcion igual o inferior a `-40%`;
3. movimiento direccional adverso del subyacente.

Las trazas de 2020 mostraron:

| Operacion | Opcion al min. 15 | Subyacente direccional | Resultado |
|---|---:|---:|---|
| AAPL call 01-may | -27.44% | -0.46% | No activa; termina casi sin valor |
| GLD call 02-jul | -4.86% | +0.02% | No activa; perdida al cierre |
| NIO call 21-ago | -9.41% | -0.31% | No activa; perdida al cierre |
| NIO call 02-oct | -55.99% | -1.45% | Activa correctamente |

Por tanto, el codigo ejecuto la regla definida. El problema fue que una
observacion unica y un umbral de `-40%` no protegen deterioros posteriores.
Ademas, con `$500` la call AAPL costaba unos `$510` por contrato y no cabia en
el cupo de `$250`; su ausencia previa fue un filtro accidental de asequibilidad,
no una victoria de la proteccion.

Se probaron dos contramedidas sin cambiar la senal:

| Variante 2020-2026, $5,000 | Final | Retorno | Drawdown |
|---|---:|---:|---:|
| 50% por posicion, control unico | $519.32 | -89.61% | 95.4% |
| 10% por posicion, control unico | $2,943.18 | -41.14% | 49.3% |
| 10% por posicion, vigilancia continua desde min. 15 | $3,226.15 | -35.48% | 38.0% |

Backtests de control de riesgo:

- 10%, control unico: `927f46cf9f3fdf91823c09b119f13ba3`.
- 10%, vigilancia continua: `bfa20d6014c0127ed1228773433b04a3`.
- Traza forense 2020: `30778e95aad5bb0af6e47e8e43df2583`.

La vigilancia continua reduce la cola, pero no restaura expectativa positiva.
No debe promocionarse como arreglo definitivo. La regla necesita una relacion
ganancia/perdida compatible con TP `10%` y validacion fuera de muestra; el
capital o la reserva no resuelven ese defecto.

## Rediseño post-COVID de la proteccion

Por decision del estudio se excluyeron 2020 y 2021. Se uso `2022-2024` para
descubrimiento y `2025-2026` como validacion bloqueada, con `$5,000` operativos,
10% maximo por posicion, dos posiciones, TP `10%` y vigilancia repetida desde
el minuto 15.

En descubrimiento se compararon limites de perdida de prima de `-15%`, `-20%`,
`-25%`, `-30%` y `-40%`. Todos fueron negativos:

| Limite | Retorno 2022-2024 | Drawdown | Win rate |
|---|---:|---:|---:|
| -15% | -23.69% | 27.2% | 59% |
| -20% | -22.06% | 25.6% | 60% |
| -25% | -20.38% | 24.0% | 62% |
| -30% | -24.10% | 27.5% | 62% |
| -40% | -21.98% | 27.7% | 68% |

El mejor resultado relativo fue `-25%`, pero no cumplio el requisito minimo de
expectativa positiva. Se congelo de todos modos para una unica comprobacion
fuera de muestra. En `2025-2026` produjo `-10.27%`, drawdown `14.7%`, 29 trades
y 62% de aciertos. Por tanto fallo tanto descubrimiento como validacion.

La trayectoria combinada post-COVID `2022-2026` termino en `$3,492.85` desde
`$5,000`: `-30.14%`, drawdown `34.3%`, 64 trades, 62% de aciertos y comisiones
de `$265.40`.

Backtests:

- Descubrimiento -25%: `c92741de269d21653547e8586478c49b`.
- Validacion bloqueada: `25f11d1f8cf19d93716b18306c378b8b`.
- Combinado 2022-2026: `217e34d2e8ed2c6c8bf5c06aeea89afa`.

Veredicto: **NO-GO**. Excluir COVID y endurecer la proteccion reduce el riesgo,
pero no convierte esta senal 0DTE en rentable. El siguiente estudio no debe ser
otro barrido de stops; debe modificar o filtrar la entrada para elevar la
calidad economica antes de arriesgar prima.
