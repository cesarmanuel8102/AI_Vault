# Selector causal independiente del capital

Fecha: 26 de octubre de 2026  
Proyecto QuantConnect: `38449639`

## Pregunta

Se puede sustituir el filtro accidental de asequibilidad de la cuenta de $500
por una medida explicita de calidad, de modo que las mismas buenas senales sean
operables con mas capital?

## Intervencion medida

Se midio una sola diferencia: un filtro causal antes del dimensionamiento. El
ranking original `rank_daily_candidates` se preservo en control y tratamiento.
El selector no recibe efectivo, equity, prima asequible ni cantidad; por tanto,
la calidad de la senal es independiente del capital disponible.

Se mantuvieron iguales delta `0.70`, DTE `0`, entrada a las `10:31 ET`, TP
`10%`, modelo de comisiones IBKR, slippage de `$0.01`, maximo dos entradas por
dia, 10% del patrimonio por posicion, cierre intradia y vigilancia repetida de
perdida de prima `-25%` desde el minuto 15.

Para limitar el sobreajuste se probo una unica familia causal: extension de la
vela inicial medida como `rango / ATR`. La rejilla preregistrada fue `1.25`,
`1.50`, `1.75`, `2.00` y `2.25`. Se selecciono el umbral mas amplio con PnL y
PF positivos tanto en entrenamiento `2022-2023` como en confirmacion `2024`,
con al menos 8 y 4 operaciones respectivamente.

El perfil congelado fue:

```text
aceptar solo si rango_09:30_10:30 / ATR14 <= 1.50
```

No se inspecciono el resultado 2025-2026 durante la seleccion automatica.

## Independencia de asequibilidad

La traza de descubrimiento `ba6ca854fe60f2aaa016fe740c9ea45e` se ejecuto
con `$100,000` y sin limite diario de entradas. Registro 138 senales: 92 no
tenian vencimiento 0DTE disponible y las 46 restantes llegaron a entrada. Hubo
cero omisiones por cotizacion, cero rechazos de entrada y cero omisiones por
economics. Por ello, la muestra tradable no quedo censurada por el tamano de la
cuenta.

Limitacion: las variables se registraron despues del fill. La ausencia total de
rechazos reduce el sesgo practico en esta traza, pero una version futura deberia
persistirlas antes de enviar la orden.

## Descubrimiento y confirmacion interna

| Periodo | Trades | Win rate | PF aproximado |
|---|---:|---:|---:|
| 2022-2023 | 9 | 88.9% | 2.05 |
| 2024 | 4 | 75.0% | 1.21 |

## Reproduccion exacta 2022-2024

| Metrica | Control | Filtro congelado |
|---|---:|---:|
| Retorno | -20.38% | **+5.93%** |
| Capital final | $3,980.78 | **$5,296.54** |
| Trades | 40 | 13 |
| Win rate | 62% | 85% |
| PF neto reconstruido | 0.64 | **2.07** |
| Drawdown | 24.0% | **3.6%** |
| Fees | $189.50 | $64.40 |

Backtests: control `cfda3142d0d5fe67c6f6a150a3f00e0e`; filtro
`a9d75f569208c5ff151a2e68732958d5`.

## Validacion congelada 2025-2026

| Metrica | Control | Filtro congelado |
|---|---:|---:|
| Retorno | -10.27% | **-9.94%** |
| Capital final | $4,486.48 | $4,503.04 |
| Trades | 29 | 11 |
| Win rate | **62%** | 55% |
| PF neto reconstruido | **0.70** | 0.45 |
| Drawdown | 14.7% | 14.7% |
| Fees | $104.50 | $49.60 |

Backtests: control `c7738ed8b4afc58b21362b77f751dbcf`; filtro
`e202115fec989c4df972911fa154e299`.

## Resultados anuales

PnL bruto de operaciones cerradas antes de comisiones:

| Ano | Control: trades / wins / PnL | Filtro: trades / wins / PnL |
|---|---:|---:|
| 2022 | 10 / 8 / +$179.67 | 1 / 1 / +$60.78 |
| 2023 | 16 / 11 / -$119.30 | 8 / 7 / +$221.96 |
| 2024 | 14 / 6 / -$890.07 | 4 / 3 / +$78.19 |
| 2025 | 15 / 11 / -$18.24 | 7 / 4 / -$244.92 |
| 2026 | 14 / 7 / -$390.78 | 4 / 2 / -$202.45 |

## Interpretacion

La hipotesis economica era razonable: evitar entrar despues de una primera hora
excesivamente extendida. Funciono con fuerza en 2022-2024, pero no se mantuvo en
2025-2026. El filtro redujo actividad y costos, pero en el holdout retiro
proporcionalmente mas ganancias que perdidas: empeoraron el win rate y el PF.

Esto demuestra dos cosas:

1. El capital ya no decide la calidad; esa dependencia fue eliminada del nuevo
   filtro y este se aplica antes del sizing.
2. `rango / ATR` por si solo no identifica una subpoblacion estable de senales
   rentables. La aparente ventaja de la cuenta pequena no puede convertirse
   honestamente en una regla general con esta evidencia.

No se probaron umbrales adicionales despues de observar la validacion. Hacerlo
convertiria 2025-2026 en otro periodo de ajuste y produciria una rentabilidad
retrospectiva dificil de distinguir de sobreajuste.

## Veredicto

**NO-GO para activar el filtro.** Permanece implementado, parametrizado y
apagado por defecto para reproducibilidad. La estrategia 0DTE no queda validada
para usar mas capital. El siguiente ensayo legitimo necesita informacion causal
nueva, por ejemplo regimen del mercado, catalizador o contexto de volatilidad,
o un periodo futuro no observado; no otro ajuste del mismo umbral.

## Artefactos

- `causal_signal_selector_manifest.json`
- `causal_selector_feature_trace_2022_2024_trace.json`
- `causal_selector_exact_control_2022_2024_raw.json`
- `causal_selector_exact_filter_2022_2024_raw.json`
- `causal_selector_exact_control_2025_2026_raw.json`
- `causal_selector_exact_filter_2025_2026_raw.json`
- `analyze_causal_signal_selector.py`
