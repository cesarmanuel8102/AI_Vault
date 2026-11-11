# Optimizacion disciplinada de 0DTE con TP 5%

Fecha: 2026-10-25  
Plataforma: QuantConnect Cloud / LEAN  
Capital inicial por backtest: USD 100,000

## Metodo

Se conservaron la senal de primer rebote, opciones largas ATM con vencimiento el
mismo dia, asignacion maxima de 10%, take profit de 5%, modelo de comisiones IBKR,
slippage de USD 0.01 y cierre obligatorio a las 15:55 ET.

La seleccion se hizo exclusivamente con 2025. Despues de congelar una unica
variante, se comparo contra el control en 2026-01-01 a 2026-10-25 sin modificar
ningun parametro.

Variantes 2025 preregistradas:

1. control sin failure-to-launch;
2. cierre a 5 minutos si PnL al bid < 0%;
3. cierre a 8 minutos si PnL al bid < -2%;
4. mejor cierre temprano mas volumen relativo >= 1.2 y cierre de la vela dentro
   del 25% direccional extremo de su rango.

## Seleccion 2025

| Variante | Trades | Retorno | PF neto | Expectancy/trade | Drawdown | Fees |
|---|---:|---:|---:|---:|---:|---:|
| Control | 23 | -16.98% | 0.449 | -$738.45 | 24.5% | $4,893.60 |
| 5 min / 0% | 23 | -20.46% | 0.294 | -$889.40 | 20.5% | $5,047.10 |
| 8 min / -2% | 23 | -24.61% | 0.262 | -$1,069.93 | 24.6% | $4,864.90 |
| Calidad + 5 min / 0% | 17 | -4.32% | 0.632 | -$253.88 | 5.0% | $3,213.60 |

Los cierres temporales por si solos empeoraron el control. La variante de calidad
fue congelada para validacion porque obtuvo el mayor profit factor, la menor
perdida y el menor drawdown. Aun asi, tampoco fue rentable en 2025. Antes de
comisiones perdio aproximadamente USD 1,102.31.

## Validacion bloqueada 2026

| Variante | Trades | Retorno | PF neto | Expectancy/trade | Drawdown | TP | Fees |
|---|---:|---:|---:|---:|---:|---:|---:|
| Control | 23 | -24.53% | 0.335 | -$1,066.32 | 26.1% | 17 | $8,165.90 |
| Calidad + 5 min / 0% | 16 | -33.01% | 0.071 | -$2,063.08 | 33.6% | 4 | $6,795.20 |

La variante candidata termino plana, con 16 entradas y 16 cierres, cero rechazos
de entrada y cero rechazos de cierre. Doce operaciones salieron por failure-to-
launch y solo cuatro alcanzaron el TP. La perdida antes de comisiones tambien fue
material: aproximadamente USD 26,214.13.

## Enlaces reproducibles

### Seleccion 2025

- [Control](https://www.quantconnect.com/project/38449639/532b8565c1e5b3523ce7f6ae0fee9624)
- [5 minutos / 0%](https://www.quantconnect.com/project/38449639/75662efeec5b48563920b95440bafcc2)
- [8 minutos / -2%](https://www.quantconnect.com/project/38449639/0267a9227cda243cbca300d464ada687)
- [Calidad + 5 minutos / 0%](https://www.quantconnect.com/project/38449639/e6add4235ba48477a8ae2697744ab90a)

### Validacion 2026

- [Control](https://www.quantconnect.com/project/38449639/3f89ff89c956f888aa9ace36b681a0bf)
- [Calidad + 5 minutos / 0%](https://www.quantconnect.com/project/38449639/ba188e8b6a55680173ecd2a048c49118)

## Veredicto

**NO-GO.**

La salida a 5% no se vuelve rentable al agregar una salida temporal basada en el
comportamiento de las ganadoras ni con el filtro sencillo de volumen y cierre
direccional. La aparente mejora de 2025 no generalizo: en 2026 la variante perdio
mas que el control, tuvo menor tasa de objetivos y mayor drawdown.

El problema economico central permanece: el TP limita las ganancias, mientras
los spreads, slippage, comisiones por contrato y movimientos adversos de opciones
0DTE producen perdidas unitarias mucho mayores. No se recomienda seguir afinando
umbrales sobre este mismo periodo. Cualquier estudio posterior debe cambiar la
hipotesis economica, por ejemplo riesgo fijo por prima, limite estricto de
contratos o spreads definidos, y validarse en datos no usados aqui.
