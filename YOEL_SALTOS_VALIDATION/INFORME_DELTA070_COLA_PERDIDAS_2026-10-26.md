# Diagnostico causal y contramedida: delta 0.70, 0DTE, TP 10%

Fecha: 26 de octubre de 2026  
Proyecto QuantConnect: `38449639`

## Veredicto

La estrategia original no perdia por falta de aciertos. Perdia porque una cola
pequena de continuaciones fallidas destruia varias ganancias, y porque algunos
contratos baratos tenian una friccion estimada superior al beneficio bruto que
se pretendia capturar.

La contramedida quedo respaldada por una prueba 2026 bloqueada, sin reajustar
sus parametros despues de observarla. El resultado combinado cambia de
`-14.75%` a `+7.65%` neto y reduce el drawdown de `20.3%` a `8.5%`.

Esto es evidencia favorable, no certificacion de rentabilidad futura: solo hay
43 operaciones combinadas y las metricas ajustadas por riesgo siguen debiles.

## Causa identificada

### 1. Cola de perdida 0DTE

En 2025, a los 15 minutos de la entrada, la combinacion siguiente separo cuatro
perdedoras grandes y ninguna ganadora:

- retorno de la opcion menor o igual a `-40%`; y
- retorno direccional del subyacente adverso a la posicion.

No basta que la opcion caiga: el subyacente tambien debe confirmar que la
continuacion inmediata fallo. En el replay congelado de 2026, la misma regla
identifico la perdida catastrofica de GLD y ninguna ganadora.

### 2. Economia de contratos baratos

El coste roundtrip conservador usado por el modelo es `$0.033` por accion de
opcion. La friccion relativa es `0.033 / ask`. Si supera el TP de `10%`, incluso
alcanzar el objetivo bruto no compensa el obstaculo de ejecucion estimado. El
control original aceptaba esos contratos y sufria especialmente en NIO.

## Contramedida congelada

La entrada, universo, delta objetivo, asignacion, TP y cierre de fin de dia se
mantuvieron sin cambios. Solo se agregaron dos controles:

1. Rechazar la entrada cuando `0.033 / ask > 0.10`.
2. Evaluar una sola vez, en el primer minuto disponible a partir de 15 minutos,
   si la opcion va `<= -40%` y el subyacente se mueve contra la posicion. Si
   ambas condiciones se cumplen, cerrar.

El TP se evalua antes de la salida causal. No se agrego stop ordinario, filtro
estadistico, cambio de universo ni busqueda adicional sobre 2026.

## Resultados QuantConnect

| Prueba | Trades | Win rate | Neto | Fees | PF neto | Drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Control 2025-2026 | 46 | 74% | -14.75% | $5,514.35 | 0.71 | 20.3% |
| Descubrimiento 2025 | 21 | 81% | -0.26% | $1,569.10 | 0.99 | 8.5% |
| Validacion bloqueada 2026 | 22 | 77% | +7.95% | $1,483.30 | 1.54 | 5.6% |
| Confirmacion 2025-2026 | 43 | 79% | +7.65% | $3,048.50 | 1.22 | 8.5% |

Backtests:

- Control combinado: `84390ce77f559f3209d5ca784ed796bd`
- Descubrimiento 2025: `30c65065228a91046bcbd92dad7d975b`
- Validacion 2026: `7cc2f40c7a6a166bc325ac0903f70a40`
- Confirmacion combinada: `e13f8e3e0e4a25643b0ebcf9f8cd1d29`

En la confirmacion combinada hubo 43 operaciones, 34 salidas por target, cinco
salidas por fallo de continuacion, cuatro salidas temporales y tres entradas
rechazadas por economia. El P&L antes de fees fue `$10,700.01`; despues de
`$3,048.50` de fees quedo en `$7,651.51`.

## Interpretacion

La hipotesis causal esta apoyada por tres hechos:

- actua sobre el mecanismo observado de perdida, no sobre el ticker o la fecha;
- mejora el periodo de descubrimiento sin exigir que este sea positivo;
- mejora de `-2.15%` a `+7.95%` en 2026, reservado como validacion.

Sin embargo, el Sharpe combinado es `-0.066` y el Probabilistic Sharpe Ratio es
solo `3.949%`. La curva es rentable en la muestra, pero todavia irregular y con
poca evidencia estadistica. La clasificacion correcta es:

**Hipotesis apoyada y contramedida rentable en este BT, pero no demostrada como
estrategia robusta para produccion.**

## Siguiente validacion recomendada

Congelar el codigo actual y probarlo en periodos anteriores no usados, por
regimen y mediante walk-forward. No optimizar de nuevo el umbral de 15 minutos,
el `-40%` ni el coste sobre el mismo 2025-2026. El criterio para avanzar debe
exigir PF neto mayor que 1, drawdown contenido y estabilidad entre periodos, no
solo conservar un win rate alto.

## Sensibilidad posterior: TP 30%

Se ejecuto una comparacion cambiando unicamente `take_profit` de `0.10` a
`0.30`. El resto de la configuracion causal permanecio igual. Backtest:
`8d65f1cda28bf76c3b07f7bd1742a89e`.

| Configuracion | Trades | Win rate | Neto | PF neto | Drawdown | Targets | Time exits |
|---|---:|---:|---:|---:|---:|---:|---:|
| TP 10% | 43 | 79% | +7.65% | 1.22 | 8.5% | 34 | 4 |
| TP 30% | 45 | 53% | -26.15% | 0.71 | 30.8% | 24 | 16 |

El TP 30% queda rechazado. En 0DTE, esperar el objetivo mas amplio transforma
muchas ganancias pequenas alcanzables en posiciones mantenidas hasta las
15:55, donde la perdida de valor temporal y las reversiones producen una nueva
cola de perdidas. Ademas, como el filtro economico se expresa respecto al TP,
la configuracion de 30% admite contratos mas baratos: solo rechazo una entrada,
frente a tres con TP 10%.

## Sensibilidad posterior: trailing desde +15%

Se implemento un trailing opcional que se activa cuando la opcion alcanza
`+15%` y cierra tras devolver cinco puntos porcentuales desde su mayor retorno
observado. Su beneficio inicialmente protegible es `+10%`, por lo que el filtro
economico conservo el mismo umbral que la variante TP10. El trailing reemplazo
el target fijo, sin alterar senales, contratos, sizing, failure exit o cierre.

| Prueba | Trades | Win rate | Neto | Drawdown | Trailing exits |
|---|---:|---:|---:|---:|---:|
| Descubrimiento 2025 | 21 | 57% | -21.78% | 24.1% | 14 |
| Validacion 2026 | 22 | 68% | -6.88% | 11.8% | 16 |
| Combinado | 43 | 63% | -27.42% | 27.8% | 30 |

Backtests: `209ceeb512f49549c3f4e1658ed67ca5`,
`ed3e8307f904ece4ed174cf106b30d0c` y
`ec4de81b18f8758d0791c61a9ed9cdfd`.

El trailing queda rechazado. En opciones 0DTE el suelo teorico no es un precio
garantizado: entre observaciones de un minuto el bid puede atravesarlo, y la
orden de mercado se ejecuta despues de que la prima haya retrocedido mucho mas.
Ademas, exigir primero +15% reduce sustancialmente la proporcion de operaciones
que monetizan el movimiento alcanzable. La implementacion permanece disponible
pero desactivada por defecto (`trailing_activation=0`, `trailing_distance=0`).

## Busqueda de salidas que preserven upside

Se examino una escalera de beneficios para conservar el TP10 como primer cobro
y dejar solo una fraccion como runner. Todos los contratos del control tenian
cantidad suficiente para una salida parcial. Las alternativas fueron
preregistradas y evaluadas primero en 2025:

| Criterio 2025 | Neto | Win rate | Drawdown | Resultado |
|---|---:|---:|---:|---|
| Cerrar 100% a +10% | -0.26% | 81% | 8.5% | Control aceptado |
| 50% a +10%, resto a +15% | -6.53% | 82% | 12.9% | Rechazado |
| 75% a +10%, resto a +15% | -3.36% | 82% | 9.8% | Rechazado |
| 75% a +10%, resto a +20% | -3.26% | 79% | 10.0% | Rechazado |
| Solo si ya cotiza >=15%: 75%, resto a 20% | -1.25% | 79% | 9.2% | Rechazado |

Backtests: `a3f5a9236a60bc8f963fce71da57b33a`,
`954a5bf517b5c040fe0c7703ed0e7dfc`,
`cde3e803a2d8e91c838d9ee4c270cbd4` y
`9a44092df781a2d42b9e0087fc07bd32`.

La variante selectiva genero solo tres scale-outs: dos runners alcanzaron +20%
y uno termino por tiempo. Aun asi, el resultado empeoro casi un punto frente al
control. Ninguna candidata supero el periodo de descubrimiento, por lo que no
se uso 2026 para seleccionar ni se promovio una escalera. El criterio de salida
que permanece respaldado es cerrar el 100% al alcanzar +10%.

## Contramedida de entrada: no abrir 0DTE desde las 14:00 ET

Tras rechazar las alternativas de salida, se examinaron rasgos observables al
entrar. El filtro previo de volumen relativo y localizacion del cierre no se
reutilizo porque habia empeorado fuera de muestra. La hipotesis elegida fue
temporal y causal: una entrada 0DTE durante las ultimas dos horas tiene menos
tiempo para recuperarse, mayor sensibilidad gamma y una perdida temporal mas
severa. Se congelo una sola regla, sin barrer varios horarios:

**No abrir nuevas posiciones 0DTE a partir de las 14:00 ET.**

Las posiciones ya abiertas conservan TP10, el control causal de 15 minutos y
el cierre de fin de dia. No cambiaron universo, delta, asignacion ni costes.

| Periodo | Baseline TP10 | Corte 14:00 | PF neto corte | DD corte | Trades corte |
|---|---:|---:|---:|---:|---:|
| 2025, descubrimiento | -0.26% | +6.84% | 1.54 | 7.9% | 19 |
| 2026, validacion bloqueada | +7.95% | +6.65% | 1.46 | 5.8% | 21 |
| 2025-octubre 2026 | +7.65% | +13.89% | 1.49 | 7.9% | 40 |

Backtests: `d3f29f145338628fa032739212322793`,
`66372693f017d5acbf84431c4b7485e7` y
`fdf04d4761adbe46c8a97918dff12ccb`.

La regla mejora claramente la muestra combinada y convierte ambos subperiodos
en rentables. No supera al baseline durante 2026: reduce el retorno de +7.95%
a +6.65% y aumenta levemente su drawdown de 5.6% a 5.8%. Por tanto, la evidencia
correcta no es que el corte domine siempre, sino que elimina una cola tardia
grave en 2025 sin destruir la rentabilidad fuera de muestra. Con solo 40
operaciones y PSR combinado de 8.711%, sigue siendo una hipotesis prometedora,
no una garantia de rentabilidad futura.
