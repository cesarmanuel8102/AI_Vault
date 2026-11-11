# Primer rebote con opciones 0DTE: ATM frente a OTM

Fecha del estudio: 2026-10-25  
Periodo: 2025-01-01 a 2026-10-25  
Capital inicial: USD 100,000  
Plataforma: QuantConnect Cloud / LEAN

## Configuracion congelada

Se mantuvo exactamente la senal de primer rebote previamente definida: tendencia
horaria SMA20/40/100/200, confirmacion diaria SMA20/40, primer toque por regimen,
distancia previa 0.25 ATR, rechazo de la media, Bollinger, vela y volumen relativo.

Se modifico exclusivamente la expresion de la operacion:

- opcion larga con vencimiento el mismo dia;
- ATM mas cercano o primer strike OTM;
- hasta 10% del menor entre efectivo disponible y equity;
- sin stop loss ni salida por invalidacion del subyacente;
- take profit de 35% medido contra el bid;
- cierre obligatorio a las 15:55 ET;
- sin posiciones nocturnas, ejercicio, promediado ni refuerzo.

## Resultados

| Variante | Retorno | CAGR | Drawdown | Sharpe | Trades | TP | Comisiones | Equity final |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ATM | -47.00% | -29.58% | 47.60% | -0.78 | 46 | 26 (56.5%) | $10,830.85 | $53,003.72 |
| OTM | -61.48% | -40.97% | 61.50% | -1.03 | 46 | 24 (52.2%) | $20,218.15 | $38,519.71 |

## Variacion adicional: take profit 5%

Se repitieron ATM y OTM cambiando exclusivamente el take profit de 35% a 5%.

| Variante | Retorno | CAGR | Drawdown | Sharpe | Trades | TP | Comisiones | Equity final |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ATM TP 5% | -37.10% | -22.60% | 37.30% | -1.06 | 46 | 36 (78.3%) | $11,688.00 | $62,903.54 |
| OTM TP 5% | -53.46% | -34.46% | 53.60% | -1.44 | 46 | 34 (73.9%) | $23,831.40 | $46,541.60 |

Bajar el objetivo mejora ambos retornos absolutos, pero no cambia el veredicto.
La tasa de objetivos aumenta mucho, mientras las pocas operaciones sin TP siguen
absorbiendo una fraccion grande de la prima. El profit/loss ratio reportado cae a
0.13 en ATM y 0.09 en OTM: muchas ganancias pequenas frente a pocas perdidas grandes.

## Salida segun duracion media de las ganadoras

En los backtests TP 5%, las operaciones ganadoras ATM tardaron en promedio 23.6
minutos y tuvieron mediana de 5.5 minutos. Las OTM tardaron en promedio 20.3
minutos y tuvieron mediana de 5 minutos. La diferencia entre media y mediana muestra
una cola de ganadoras tardias de hasta 176 minutos.

Se probaron limites redondeados cercanos a la media: 25 minutos para ATM y 20
minutos para OTM, manteniendo TP 5% y el resto sin cambios.

| Variante | Sin limite medio | Con limite | Cambio | TP con limite | Drawdown |
|---|---:|---:|---:|---:|---:|
| ATM | -37.10% | -48.49% (25 min) | -11.39 pp | 25/46 | 48.70% |
| OTM | -53.46% | -60.96% (20 min) | -7.50 pp | 24/46 | 61.10% |

El limite temporal empeora ambos resultados. Corta parte de las perdidas, pero
tambien elimina las ganadoras que necesitan mas que la media para alcanzar 5%.
Usar el promedio de las ganadoras no crea una frontera predictiva: es una estadistica
condicionada a conocer de antemano cuales operaciones terminaron ganando.

Ambas pruebas fueron tecnicamente validas: 46 entradas, 46 cierres, cero holdings
finales, cero rechazos de entrada y cero rechazos de cierre. De 93 senales, 47 se
omitieron porque el subyacente no tenia un contrato con vencimiento ese mismo dia.

## Por que pierde aunque el TP acierta mas de la mitad

ATM alcanzo el objetivo en 56.5% de las operaciones y OTM en 52.2%. Sin embargo,
el +35% de las ganadoras no compensa las opciones que permanecen abiertas sin stop
hasta las 15:55 y pierden gran parte de su prima. Antes de comisiones, ATM ya perdio
$36,165.42 y OTM $41,262.13.

El 10% de capital aplicado a opciones baratas produce cantidades muy grandes de
contratos. La comision media por round trip fue aproximadamente $235.45 en ATM y
$439.53 en OTM. OTM resulta especialmente penalizado porque una prima menor compra
mas contratos con el mismo presupuesto.

PnL neto anual:

| Variante | 2025 | 2026 hasta 25 octubre |
|---|---:|---:|
| ATM | -$24,924.86 | -$22,071.41 |
| OTM | -$42,668.11 | -$18,812.17 |

## Conclusion

Las dos variaciones quedan invalidadas. El problema no es solamente de comisiones:
ambas pierden decenas de miles de dolares antes de costes. Eliminar el stop transforma
el payoff en muchas ganancias limitadas al 35% y menos perdidas, pero mucho mayores.
El 10% por entrada amplifica esa asimetria.

No debe operarse esta configuracion. Una investigacion posterior tendria que ser una
hipotesis nueva y preregistrada, no un ajuste sobre estos mismos resultados. Las
variables que economicamente merecerian estudiarse fuera de muestra son exposicion
por delta o riesgo fijo, limite de contratos, entrada mas temprana y una salida
temporal o de prima que corte las perdidas; restaurar esas protecciones cambia la
estrategia solicitada y requiere otro test independiente.
