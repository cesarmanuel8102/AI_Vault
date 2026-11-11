# Informe de operabilidad de la teoria de saltos

Fecha: 2026-10-25

## Veredicto

**NO-GO para operar con capital real y NO-GO para trasladar la senal a
opciones.**

Se encontro una pequena expectativa positiva en la continuacion posterior a
un shock, pero no una ventaja robusta capaz de justificar riesgo real. El
resultado correcto no es que la teoria completa sea cierta: una version
cuantificada y bastante distinta de la narrativa del curso produjo beneficios
modestos, inestables y con coste de oportunidad elevado.

## Protocolo

- Universo de 40 acciones y ETF liquidos.
- Seleccion de configuracion con 2008-2021; OOS final 2022-2025.
- Capital inicial USD 100,000.
- Riesgo de 0.50% por entrada, maximo 10% de notional por posicion y 10
  posiciones simultaneas.
- Comisiones IBKR y slippage constante de 5 puntos basicos por lado.
- Stop 1 ATR, objetivo 2 ATR; sin refuerzos ni promedios a la baja.
- Entradas posteriores a toda la informacion usada por la senal.

El primer prototipo que entraba al cierre de confirmacion fue descartado por
look-ahead. La version valida entra en la apertura siguiente. El drawdown del
motor independiente tambien se corrigio para incluir mark-to-market.

## Resultados QuantConnect OOS

| Familia | Retorno neto | CAGR | Drawdown | Trades | Win rate | Profit factor neto | Sharpe oficial |
|---|---:|---:|---:|---:|---:|---:|---:|
| Continuacion al cierre, 3 sesiones | 8.52% | 2.06% | 3.80% | 157 | 55.4% | 1.43 | -1.253 |
| Continuacion confirmada a 30 min | 3.93% | 0.97% | 1.60% | 116 | 50.0% | 1.57 | -2.956 |
| Rechazo/fade confirmado a 30 min | 3.18% | 0.79% | 2.00% | 123 | 44.7% | 1.40 | -2.480 |

Todos los resultados incluyen fees y slippage. La estrategia permanece plana
fuera de las operaciones y no recibe intereses sobre efectivo en este modelo.

### Continuacion al cierre

- PnL neto: USD 8,516.48; fees: USD 405.14.
- PnL anual: 2022 USD 1,322; 2023 USD 489; 2024 USD 4,609; 2025 USD 2,096.
- 65% de los simbolos fueron rentables.
- UNH y NFLX aportaron juntos aproximadamente 53% del beneficio total.
- Bootstrap por bloques mensuales, PnL anualizado 95%: USD -378 a USD 4,899.
- La probabilidad bootstrap de media anual positiva fue 94.98%, justo por
  debajo de 95%, y el intervalo incluye cero.

El Sharpe sin descontar la tasa libre de riesgo, calculado sobre PnL realizado,
es aproximadamente 0.77. El Sharpe oficial de QuantConnect es negativo porque
el CAGR de 2.06% no compenso la tasa libre de riesgo del periodo. El criterio
preregistrado usa el Sharpe oficial/economico, no la version mas favorable.

### Confirmacion de apertura

La continuacion de 30 minutos fue positiva en tres de cuatro anos y en 70.3%
de los simbolos, pero su intervalo bootstrap anualizado tambien incluye cero:
USD -348 a USD 2,391. El CAGR de 0.97% no remunera el capital inmovilizado.

### Fade de apertura

El beneficio procede enteramente de 2022. Los anos 2023, 2024 y 2025 fueron
negativos. Es un efecto de regimen, no una estrategia estable.

## Comprobacion independiente

El motor diario independiente eligio sin consultar OOS la configuracion
`CLOSE_CONTINUATION|atr=1.25|hold=3`. En OOS produjo:

- retorno neto 3.64%;
- Sharpe 0.364;
- profit factor 1.147;
- drawdown 3.55%;
- 180 operaciones.

La direccion positiva coincide con QuantConnect, pero la magnitud no. Esa
discrepancia entre motores impide considerar demostrada la rentabilidad.

## Comparacion pasiva

SPY ajustado produjo aproximadamente 50.91% total, CAGR 10.86% y drawdown
24.50% durante 2022-2025. La continuacion tiene mucho menos drawdown y una
relacion CAGR/drawdown ligeramente competitiva, pero retorno absoluto, alpha e
information ratio inferiores. Aumentar apalancamiento no mejora la calidad
estadistica de la senal y violaria el limite de drawdown antes de resolver el
problema de Sharpe.

## Decision sobre opciones

No se ejecuta una nueva optimizacion de calls, puts o spreads. Las opciones
anadirian theta, volatilidad implicita y spreads a una senal del subyacente que
aun no supera el gate. Hacerlo ahora seria una busqueda posterior al resultado.

## Uso razonable del hallazgo

La continuacion al cierre puede conservarse como **senal de investigacion en
PAPER**, sin asignacion economica y sin modificar parametros. Solo una ventana
forward completamente nueva podria confirmar o rechazar el efecto. No existe
base para afirmar que la metodologia del curso, su 90%, su objetivo fijo de
35% o sus refuerzos sean rentables.

## Artefactos reproducibles

- Motor independiente: `independent_operability.py`
- Resultados: `operability_results.json`, `operability_trades.csv`
- Resumen QC: `operability_summary.json`
- Proyecto QC cierre: ID 38447559, backtest `50a2dfb2476ee3f5e89da9387be53a1b`
- Proyecto QC intradia: ID 38447691, backtests
  `6261ccb22a11f6f81fbffb08837f7e25` y
  `bdd1b886954c9d23bedf0885184fe63b`
