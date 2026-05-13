# Especificacion Tecnica Inicial de Estrategias Forex para QuantConnect

Fecha: 2026-04-03

Este documento convierte el brief de investigacion en una especificacion ejecutable para backtesting y prototipado en `Python + QuantConnect`.

## 1. Supuestos comunes

- Broker objetivo inicial: `OANDA`.
- Motor de investigacion: `QuantConnect / LEAN`.
- Clase de activo: `Forex`.
- Universo base: pares G10 liquidos.
- Capital inicial de investigacion sugerido: `10,000 USD`.
- Cuenta: `margin`.
- Modo de prueba: `backtest -> paper -> micro live`.

## 2. Reglas de ingenieria obligatorias

- No hardcodear sesiones en UTC fijo; resolver horarios con conversion de zona porque Londres y Nueva York cambian por DST.
- Para intradia, consumir `QuoteBar` siempre que sea posible.
- No validar estrategias con spread fijo simplificado.
- Toda posicion abierta a `5 p.m. ET` debe registrar financing estimado o real.
- Toda estrategia debe exponer:
  - senal bruta;
  - score de confianza;
  - riesgo por trade;
  - motivo de entrada;
  - motivo de salida.

## 3. Estrategia 1: London-New York Volatility Breakout

## 3.1 Objetivo

Capturar expansiones de rango tras compresion previa durante la apertura europea o la superposicion Londres-Nueva York.

## 3.2 Universo inicial

- `EURUSD`
- `GBPUSD`
- `USDJPY`
- `AUDUSD`

## 3.3 Resoluciones

- suscripcion base: `Minute`
- consolidadores: `5m`, `15m`, `60m`

## 3.4 Features

- `asian_range_high`
- `asian_range_low`
- `asian_range_width`
- `atr_15m_14`
- `compression_ratio = asian_range_width / atr_15m_14`
- `compression_percentile_60d`
- `spread_now`
- `spread_to_recent_median`
- `session_label`
- `pre_breakout_slope`

## 3.5 Ventanas a probar

- bloque asiatico retrospectivo de `4h`, `6h`, `8h`
- bloque operativo:
  - apertura Londres;
  - overlap Londres-Nueva York;
  - ambos comparados por separado

## 3.6 Reglas de entrada iniciales

- `long` si:
  - precio supera `asian_range_high`;
  - `compression_percentile <= 30`;
  - `spread_to_recent_median <= 1.5`;
  - no hay veto de noticia;
  - la vela de ruptura no excede `2.5 * ATR_5m`.

- `short` simetrico sobre `asian_range_low`.

## 3.7 Reglas de salida iniciales

- `stop_loss = 1.0 * ATR_15m`
- `take_profit = 1.8R`
- `time_stop = fin de overlap` o `120` minutos, lo que ocurra primero
- trailing opcional al alcanzar `+1R`

## 3.8 Grid inicial de parametros

- `compression_percentile`: `20`, `30`, `40`
- `spread_to_recent_median_max`: `1.2`, `1.5`, `1.8`
- `stop_atr`: `0.8`, `1.0`, `1.2`
- `tp_r_multiple`: `1.5`, `1.8`, `2.2`
- `max_breakout_bar_atr`: `2.0`, `2.5`, `3.0`

## 3.9 Hipotesis prioritaria

La mejor version deberia aparecer en `EURUSD` y `GBPUSD`, con menos trades pero mejor payoff cuando se exige compresion real y spread contenido.

## 4. Estrategia 2: Intraday Mean Reversion After Exhaustion

## 4.1 Objetivo

Revertir sobreextensiones intradia medibles que no vengan acompanadas por verdadero cambio de regimen macro.

## 4.2 Universo inicial

- `EURUSD`
- `GBPUSD`
- `USDJPY`
- `USDCAD`

## 4.3 Resoluciones

- suscripcion base: `Minute`
- consolidadores: `1m`, `5m`, `15m`

## 4.4 Features

- `ret_5m_zscore`
- `ret_15m_zscore`
- `distance_to_vwap`
- `distance_to_ema_20_5m`
- `range_expansion_1h`
- `range_expansion_3h`
- `spread_now`
- `spread_to_recent_median`
- `impulse_decay_flag`
- `session_label`

## 4.5 Reglas de entrada iniciales

- `long` si:
  - `ret_5m_zscore <= -2.2` o `ret_15m_zscore <= -2.0`;
  - `distance_to_vwap <= -0.75 * ATR_5m`;
  - `spread_to_recent_median <= 1.3`;
  - fuera de ventana de noticia;
  - aparece primera senal de desaceleracion del impulso.

- `short` simetrico cuando la sobreextension es alcista.

## 4.6 Reglas de salida iniciales

- salida primaria en `VWAP` o `EMA_20_5m`
- `stop_loss = 0.8 * ATR_5m`
- `time_stop = 45` minutos
- salida anticipada si aparece nueva expansion contra la posicion

## 4.7 Grid inicial de parametros

- `zscore_entry`: `1.8`, `2.2`, `2.6`
- `distance_to_vwap_atr`: `0.5`, `0.75`, `1.0`
- `spread_to_recent_median_max`: `1.2`, `1.3`, `1.5`
- `stop_atr`: `0.6`, `0.8`, `1.0`
- `time_stop_minutes`: `30`, `45`, `60`

## 4.8 Hipotesis prioritaria

Esta estrategia deberia aportar mas frecuencia que breakout, pero tambien mas sensibilidad a costos. Si no supera costos con filtros de spread estrictos, se descarta.

## 5. Estrategia 3: Cross-Sectional FX Momentum + Carry con Crash Filter

## 5.1 Objetivo

Explotar persistencia relativa entre monedas y el diferencial de tasas, reduciendo exposicion cuando sube el riesgo de reversal brusco.

## 5.2 Universo inicial

- `EURUSD`
- `GBPUSD`
- `AUDUSD`
- `NZDUSD`
- `USDJPY`
- `USDCAD`
- `USDCHF`

## 5.3 Resoluciones

- suscripcion base: `Daily`
- rebalanceo: semanal o quincenal

## 5.4 Features

- `mom_21d`
- `mom_63d`
- `realized_vol_21d`
- `carry_proxy`
- `cross_section_rank`
- `portfolio_dispersion`
- `crash_filter_state`

## 5.5 Senal compuesta inicial

```text
signal_score =
    0.45 * rank(mom_21d) +
    0.35 * rank(mom_63d) +
    0.20 * rank(carry_proxy)
```

La ponderacion es inicial. Luego se valida si conviene igual peso o peso por robustez fuera de muestra.

## 5.6 Construccion de cartera

- `long` en top `2` scores
- `short` en bottom `2` scores
- peso inverso a volatilidad
- limite de peso por par: `25%`
- beta monetaria agregada cercana a neutral cuando sea posible

## 5.7 Crash filter inicial

Se reduce exposicion al `50%` o se apaga totalmente si ocurre cualquiera:

- `realized_vol_21d` del portafolio supera percentil `85`;
- dispersion diaria del universo supera percentil `90`;
- drawdown rolling de `20d` excede umbral de seguridad.

## 5.8 Grid inicial de parametros

- formacion momentum: `21d`, `42d`, `63d`
- rebalanceo: `weekly`, `biweekly`
- seleccion:
  - top/bottom `1`
  - top/bottom `2`
  - terciles
- vol target anualizada: `8%`, `10%`, `12%`
- crash filter percentile: `80`, `85`, `90`

## 5.9 Hipotesis prioritaria

La combinacion `momentum + carry + vol targeting + crash filter` deberia producir una curva menos agresiva, pero mas robusta, que carry puro.

## 6. Risk overlay comun

Todas las estrategias deben pasar por un overlay comun:

- riesgo maximo por trade: `0.25%` a `0.50%` del equity
- riesgo maximo por estrategia: `2.0%`
- riesgo maximo portafolio agregado: `4.0%`
- maximo de pares correlacionados en la misma direccion:
  - `2` para intradia;
  - `3` para swing
- pausa automatica por drawdown:
  - `-4%` sleeve intradia: reducir mitad
  - `-6%` sleeve intradia: apagar
  - `-8%` portafolio total: apagar investigacion live

## 7. Matriz minima de experimentos

## 7.1 Fase 1: sanidad y datos

- verificar que cada par produce barras y horarios correctos;
- validar DST con semanas de transicion;
- validar disponibilidad de `QuoteBar`;
- validar conversion monetaria y PnL.

## 7.2 Fase 2: backtests individuales

Para cada estrategia y cada par:

- baseline sin optimizacion;
- grid pequena de parametros;
- reporte por anio;
- reporte por sesion;
- reporte por spread relativo.

## 7.3 Fase 3: walk-forward

- entrenar en ventana rolling;
- congelar parametros;
- evaluar siguiente bloque;
- repetir hasta cubrir todo el periodo.

## 7.4 Fase 4: cartera

- combinar las tres estrategias;
- limitar sleeve weights;
- medir correlacion rolling;
- medir estabilidad de portafolio.

## 8. Criterios de descarte

Descartar una estrategia si ocurre cualquiera:

- no mantiene expectativa positiva despues de costos;
- solo funciona en un par;
- su mejor version depende de un parametro muy estrecho;
- pierde robustez completa al subir spread y slippage;
- concentra mas del `50%` del PnL en un periodo corto aislado.

## 9. Orden recomendado de implementacion

1. `session_filters.py`
2. `cost_models.py`
3. `vol_breakout.py`
4. `intraday_mean_reversion.py`
5. `carry_momentum.py`
6. `risk_overlay.py`
7. algoritmo maestro de portafolio

## 10. Integracion recomendada con este repo

Primera etapa:

- desarrollar estrategia y evaluacion fuera del router;
- usar `trading/connectors.py` solo para chequeo de conectividad y futura operativa.

Segunda etapa:

- agregar endpoint de estado de backtests;
- agregar endpoint de configuracion activa;
- agregar endpoint de metricas de sleeve.

Tercera etapa:

- solo despues de paper trading satisfactorio, exponer capa de ejecucion live.

## 11. Siguiente paso exacto

El siguiente paso tecnico correcto es implementar el esqueleto de investigacion:

- clases base de estrategia;
- filtros de sesion;
- overlay de riesgo;
- algoritmo maestro QC;
- configuracion externa de parametros.

