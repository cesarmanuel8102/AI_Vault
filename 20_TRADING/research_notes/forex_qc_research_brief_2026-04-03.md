# Investigacion Formal Forex para Python + QuantConnect

Fecha: 2026-04-03

## 1. Objetivo realista del proyecto

El objetivo original planteado como "generar altos ingresos semanales sostenidos con la menor cantidad de capital posible" no es cientificamente defendible como promesa de resultado. La formulacion correcta para una investigacion seria es:

- identificar estrategias de forex con expectativa positiva neta de costos;
- priorizar eficiencia de margen y escalabilidad desde cuentas pequenas;
- minimizar riesgo de ruina, sobreajuste y dependencia de un solo regimen;
- seleccionar solo estrategias que puedan validarse de forma reproducible en Python y QuantConnect.

La investigacion, por tanto, se orienta a construir un portafolio de estrategias testables y no a vender una promesa de rentabilidad fija semanal.

## 2. Alcance de la investigacion

La decantacion se apoya en cuatro capas de evidencia:

1. Documentacion oficial de infraestructura y ejecucion:
- QuantConnect LEAN y datos forex.
- OANDA: spreads, margin, financing, API v20.
- Restricciones regulatorias retail en EE. UU.

2. Literatura cuantitativa y macro:
- momentum en FX;
- carry y riesgo de crash;
- estructura intradia y efecto de sesiones;
- impacto de costos y flujo de orden.

3. Evidencia de comunidad tecnica:
- foros de QuantConnect;
- discusiones de algotrading sobre spread, rollover y divergencia entre backtest y live;
- consenso recurrente sobre los fallos mas comunes en FX retail automatizado.

4. Restricciones operativas reales:
- cuenta pequena;
- broker compatible con QC;
- latencia y calidad de datos retail;
- necesidad de backtests con costos realistas.

## 3. Hallazgos estructurales de la investigacion

### 3.1 Lo que casi siempre falla

Las familias de estrategias siguientes no pasan un filtro serio para este proyecto:

- martingale;
- grid averaging sin invalidacion estructural;
- "recovery systems" que duplican riesgo;
- arbitraje de latencia retail;
- estrategias basadas solo en velas o narrativa discrecional sin reglas cuantificables;
- scalping ultracorto muy dependiente de spread fijo idealizado.

Razon principal: estas familias suelen sobrevivir solo en backtests simplificados o en periodos cortos, pero colapsan al introducir spread variable, slippage, rollover, news shocks y limites regulatorios de margen.

### 3.2 Lo que si tiene base mas robusta

La evidencia investigada favorece tres familias defendibles:

- breakout de expansion intradia en ventanas de liquidez alta;
- mean reversion intradia despues de sobreextension medible;
- momentum cross-sectional con carry y filtro de crash.

Estas tres no son equivalentes: responden a regimens distintos y permiten construir una cartera menos fragil.

### 3.3 Restricciones clave para cuenta pequena

- En forex retail EE. UU. el apalancamiento y la marginacion vienen limitados por marco regulatorio, por lo que no se puede compensar falta de edge con apalancamiento arbitrario.
- OANDA advierte que los spreads se amplian alrededor de aperturas, cierres, noticias y episodios de incertidumbre; por tanto, cualquier estrategia intradia debe filtrar condiciones de spread.
- OANDA carga financing para posiciones abiertas al cierre diario de las 5 p.m. ET; toda estrategia overnight debe modelar ese costo.
- En QuantConnect, para forex hay que trabajar con `QuoteBar` y no asumir que un backtest con precio medio representa de forma suficiente el costo real de transaccion.

## 4. Decantacion final: las 3 estrategias recomendadas

## Estrategia 1. London-New York Volatility Breakout

### Tesis

Los pares G10 liquidos presentan expansiones de rango cuando salen de compresion y entran en la ventana de mayor liquidez del dia, especialmente durante la superposicion Londres-Nueva York. La idea no es perseguir cualquier ruptura, sino solo las rupturas que salen de un estado de compresion cuantificable.

### Universo

- `EURUSD`
- `GBPUSD`
- `USDJPY`
- `AUDUSD`

### Horizonte

- intradia;
- entradas en `5m` o `15m`;
- cierre el mismo dia.

### Variables principales

- rango de sesion asiatica;
- `ATR` intradia;
- percentil de compresion del rango previo;
- spread actual frente a su distribucion reciente;
- filtro horario de sesion.

### Regla base

1. Definir el rango asiatico desde un bloque horario fijo.
2. Medir compresion previa: rango asiatico / ATR de referencia.
3. Exigir que la compresion este en percentil bajo del historial reciente.
4. Esperar ruptura del maximo o minimo asiatico durante ventana Londres o solape Londres-Nueva York.
5. Confirmar que el spread esta por debajo de un umbral maximo por par.
6. Invalidar si hay noticia macro de alto impacto en la ventana inmediata de entrada.

### Entrada

- `long` si el precio rompe maximo asiatico y la pendiente corta favorece expansion;
- `short` si rompe minimo asiatico bajo las mismas condiciones;
- se evita entrar en la primera ruptura si la vela de disparo excede un umbral de rango anormal y sugiere noticia o gap intradia.

### Salida

- stop inicial: `0.8 - 1.2 ATR` de la resolucion operativa;
- objetivo: `1.5R - 2.2R` o trailing estructural;
- `time stop`: salida al final de la ventana de overlap o antes del rollover.

### Ventajas

- no requiere dejar posiciones overnight;
- suele operar en momentos de mejor liquidez relativa;
- es compatible con cuentas pequenas porque concentra pocas operaciones y evita exposicion innecesaria de financiamiento.

### Riesgos y fallos tipicos

- falsas rupturas en dias sin catalizador;
- sesgo por DST y mala definicion de sesiones;
- degradacion severa si se ignora spread variable;
- exceso de operaciones si se opera toda ruptura sin medir compresion.

### Hipotesis cuantitativa a validar

La subfamilia mas prometedora es:

- breakout del rango asiatico;
- filtro de compresion;
- filtro de spread;
- exclusion de ventanas de noticias.

Esta combinacion deberia producir menos operaciones, pero una distribucion de payoff superior al breakout bruto.

## Estrategia 2. Intraday Mean Reversion After Exhaustion

### Tesis

En pares liquidos, parte de las extensiones intradia no representan un cambio real de regimen, sino una desalineacion temporal producida por microshock, limpieza de liquidez o barrido de stops. Cuando esa extension se aleja demasiado del equilibrio local y no coincide con un evento macro fuerte, tiende a revertir parcialmente.

### Universo

- `EURUSD`
- `GBPUSD`
- `USDJPY`
- `USDCAD`

### Horizonte

- intradia;
- resoluciones `1m`, `5m` y consolidacion de features a `15m`.

### Variables principales

- `z-score` de retorno corto;
- distancia a `VWAP` intradia o EMA de equilibrio;
- expansion de rango de 1 a 3 horas;
- spread actual;
- volumen proxy via actividad del `QuoteBar`;
- filtro de news y sesion.

### Regla base

1. Medir una sobreextension estadistica del movimiento reciente.
2. Exigir distancia minima respecto de un ancla de equilibrio intradia.
3. Exigir ausencia de evento macro de alto impacto en una ventana de seguridad.
4. Exigir spread bajo o normal para evitar capturar reversiones ficticias por widening de cotizacion.
5. Entrar solo cuando aparece desaceleracion del impulso y no en plena vela de expansion.

### Entrada

- `long` tras shock bajista sobreextendido y primer signo cuantificable de agotamiento;
- `short` tras shock alcista sobreextendido con la misma logica.

### Salida

- objetivo principal en retorno a `VWAP` o EMA corta;
- stop por estructura local o `ATR`;
- `time stop` corto, porque si no revierte rapido la tesis suele ser errada.

### Ventajas

- complementariedad natural frente a breakout;
- frecuencia operativa mayor que carry/momentum;
- buena adaptacion a cuentas pequenas si el spread esta controlado.

### Riesgos y fallos tipicos

- comprar una caida que en realidad es inicio de tendencia macro;
- sobreoptimizar umbrales de `z-score`;
- modelar `VWAP` con datos que no representan bien forex spot;
- operar en horarios de baja liquidez donde el spread destruye la esperanza.

### Hipotesis cuantitativa a validar

La mejor variante probable no es "contra toda sobreextension", sino:

- contraextremo solo en pares liquidos;
- fuera de eventos macro;
- con filtro de spread;
- con salida rapida al equilibrio.

## Estrategia 3. Cross-Sectional FX Momentum + Carry con Crash Filter

### Tesis

En forex, dos de las anomalias mas persistentes en la literatura son `momentum` y `carry`. El problema es que el carry sufre episodios de crash cuando cambian violentamente las condiciones de riesgo global. La forma seria de usar esta familia es combinar momentum y carry y apagar o reducir exposicion cuando sube el riesgo de reversal brusco.

### Universo

Cesta G10 frente a USD, con prioridad para:

- `EURUSD`
- `GBPUSD`
- `AUDUSD`
- `NZDUSD`
- `USDJPY`
- `USDCAD`
- `USDCHF`
- `NOKUSD` o cruces equivalentes si el dataset y broker lo permiten

### Horizonte

- semanal a mensual;
- rebalanceo semanal o quincenal.

### Variables principales

- retorno de `1M` y `3M`;
- diferencial de tasas o proxy de carry;
- volatilidad realizada;
- filtro de riesgo global;
- dispersion cross-sectional.

### Regla base

1. Construir un score combinado de momentum y carry.
2. Rankear los pares disponibles.
3. Tomar `long` en los de score alto y `short` en los de score bajo.
4. Ponderar por volatilidad para evitar concentracion.
5. Aplicar `crash filter`: reducir o apagar si la volatilidad y la aversion al riesgo se disparan.

### Salida

- rebalanceo calendarizado;
- stop de volatilidad o corte de riesgo de portafolio;
- recorte tactico cuando el filtro de crash se activa.

### Ventajas

- es la familia con mejor respaldo academico de las tres;
- aporta diversificacion temporal frente a las dos intradia;
- menor sensibilidad microestructural que el scalping.

### Riesgos y fallos tipicos

- ignorar el costo de financiamiento overnight;
- usar proxies pobres de carry;
- pretender frecuencia semanal alta donde la estrategia es naturalmente mas lenta;
- no incorporar filtro de crash.

### Hipotesis cuantitativa a validar

La senal combinada `momentum + carry`, con volatilidad objetivo y filtro de crash, deberia dominar a un carry puro o momentum puro en robustez fuera de muestra.

## 5. Ranking de prioridad para desarrollo

Si el objetivo es empezar con la mejor relacion entre cuenta pequena, frecuencia y viabilidad live:

1. `London-New York Volatility Breakout`
2. `Intraday Mean Reversion After Exhaustion`
3. `Cross-Sectional FX Momentum + Carry con Crash Filter`

Si el objetivo es construir un portafolio serio a 12 meses:

1. desarrollar las tres;
2. asignar mas capital al sleeve con mejor estabilidad neta de costos;
3. limitar correlacion entre estrategias en shocks macro.

## 6. Protocolo de validacion cientifica

### 6.1 Reglas de backtest

- usar datos forex de QuantConnect compatibles con `QuoteBar`;
- no asumir spread fijo;
- incorporar comisiones y modelo de broker coherente con OANDA si aplica;
- modelar financing overnight en toda estrategia que cruce las 5 p.m. ET;
- segmentar por sesiones y por anios;
- usar `walk-forward optimization`, no una calibracion unica;
- reservar muestra fuera de optimizacion;
- realizar test por par y test agregado.

### 6.2 Pruebas minimas obligatorias

- backtest 2018-2026 o maximo periodo disponible consistente;
- `walk-forward` con ventanas rodantes;
- stress de spread + slippage;
- sensibilidad de parametros;
- degradacion deliberada de ejecucion;
- validacion por subperiodos: pre-2020, 2020-2022, 2023-2026;
- validacion por dias de noticia vs dias normales.

### 6.3 Criterios propuestos de aceptacion

No son objetivos comerciales; son umbrales de investigacion para decidir si una estrategia merece papel o live micro.

- expectativa neta positiva despues de costos;
- `Sharpe > 0.8` in-sample y `> 0.5` out-of-sample;
- `Profit Factor > 1.10` en intradia y `> 1.05` en carry/momentum;
- drawdown maximo tolerable por sleeve: `<= 12%` intradia y `<= 15%` swing;
- estabilidad de resultados en al menos tres subperiodos;
- ningun par explica mas del `35%` del PnL total;
- mejora moderada, no explosiva, al optimizar parametros; si mejora demasiado, sospecha de sobreajuste.

## 7. Arquitectura de implementacion recomendada en Python + QC

### 7.1 Estructura de investigacion

- `research/feature_engineering.py`
- `research/session_filters.py`
- `research/cost_models.py`
- `research/news_filters.py`
- `strategies/vol_breakout.py`
- `strategies/intraday_mean_reversion.py`
- `strategies/carry_momentum.py`
- `portfolio/risk_overlay.py`
- `portfolio/allocation.py`

### 7.2 Estructura en QuantConnect

Cada estrategia debe implementarse como modulo separado y luego combinarse en un algoritmo maestro de portafolio. El patron correcto es:

1. inicializar universo y resoluciones;
2. consolidar `QuoteBars`;
3. calcular features por estrategia;
4. emitir senales normalizadas;
5. aplicar overlay de riesgo;
6. ejecutar con limites por par, por sleeve y por portafolio.

### 7.3 Pseudocodigo minimo

```python
class ForexResearchPortfolio(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_cash(10000)
        self.settings.free_portfolio_value_percentage = 0.10

        self.pairs = [
            self.add_forex("EURUSD", Resolution.MINUTE, Market.OANDA).symbol,
            self.add_forex("GBPUSD", Resolution.MINUTE, Market.OANDA).symbol,
            self.add_forex("USDJPY", Resolution.MINUTE, Market.OANDA).symbol,
            self.add_forex("AUDUSD", Resolution.MINUTE, Market.OANDA).symbol,
        ]

        self.breakout = LondonNyBreakoutModel(self, self.pairs)
        self.mean_rev = IntradayMeanReversionModel(self, self.pairs)
        self.carry = CarryMomentumModel(self, self.pairs)
        self.risk = PortfolioRiskOverlay(self)

    def on_data(self, slice):
        signals = []
        signals.extend(self.breakout.update(slice))
        signals.extend(self.mean_rev.update(slice))
        signals.extend(self.carry.update(slice))
        orders = self.risk.transform(signals)
        self.execute_orders(orders)
```

### 7.4 Integracion con este repo

El repositorio ya tiene una base de integracion con QuantConnect y trading:

- `trading/connectors.py`
- `trading/router.py`

Eso permite plantear dos capas:

- capa 1: investigacion y backtests en LEAN/QC;
- capa 2: exposicion de estado, salud y ejecucion a traves del router local.

La recomendacion es no mezclar desde el inicio el motor de investigacion con el bridge de ejecucion. Primero se valida en QC. Despues se conecta a operativa.

## 8. Mejoras que enriquecen la idea original

Estas mejoras elevan mucho la calidad del proyecto:

- convertir el objetivo de "mucho dinero semanal" en `retorno por unidad de margen` y `consistencia fuera de muestra`;
- agregar un `portfolio risk overlay` comun a las tres estrategias;
- usar `walk-forward` automatizado como criterio de paso obligado;
- incorporar filtros de spread y rollover como features de primer nivel, no como detalle final;
- anadir reporte semanal automatizado con:
  - PnL por estrategia;
  - PnL por par;
  - drawdown;
  - slippage estimado;
  - exposicion overnight;
- exigir `paper trading` antes de cualquier live;
- separar claramente:
  - investigacion;
  - simulacion;
  - ejecucion;
  - monitoreo.

## 9. Conclusiones ejecutivas

- No existe una via seria para prometer altos ingresos semanales sostenidos con muy poco capital sin asumir riesgo de ruina.
- Si el objetivo es construir algo real, las tres mejores familias para este proyecto son breakout intradia, mean reversion intradia y momentum+carry con filtro de crash.
- Para empezar con cuenta pequena y entorno QC, la prioridad correcta es desarrollar primero las dos intradia y usar la tercera como capa de diversificacion de horizonte mayor.
- El criterio de exito no debe ser "ganar mucho rapido", sino "sobrevivir costos reales, pasar validacion fuera de muestra y escalar sin romperse".

## 10. Fuentes utilizadas

### Documentacion oficial

- QuantConnect Forex data:
  - https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/forex-data
- QuantConnect handling data:
  - https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/forex/handling-data
- QuantConnect walk-forward optimization:
  - https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization
- QuantConnect OANDA brokerage model:
  - https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/brokerages/supported-models/oanda
- QuantConnect live trading brokerages:
  - https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/cfd-and-forex-brokerages
- OANDA spreads and margins:
  - https://www.oanda.com/us-en/trading/spreads-margin/
- OANDA core spreads + commission:
  - https://help.oanda.com/us/en/faqs/spreads-commission.htm
- OANDA financing fees:
  - https://www.oanda.com/us-en/trading/financing-fees/
- OANDA v20 API:
  - https://developer.oanda.com/rest-live-v20/introduction/
- Interactive Brokers FX order sizes:
  - https://www.interactivebrokers.com/en/trading/forexOrderSize.php
- CFTC retail forex rules:
  - https://www.cftc.gov/PressRoom/PressReleases/5883-10

### Literatura y evidencia cuantitativa

- AQR, Carry Trades and Currency Crashes:
  - https://www.aqr.com/Insights/Research/Working-Paper/Carry-Trades-and-Currency-Crashes
- BIS, Order flow and exchange rate dynamics:
  - https://www.bis.org/publ/bispap02j.pdf

### Evidencia comunitaria util

Estas fuentes no sustituyen validacion cientifica, pero son utiles para detectar fricciones reales que suelen matar bots de FX retail:

- QuantConnect forum, Forex spread:
  - https://www.quantconnect.com/forum/discussion/569/forex-spread/
- QuantConnect forum, DST and forex data timing:
  - https://www.quantconnect.com/forum/discussion/5365/daylight-savings-timezone-confusion/
- Reddit algotrading, data and spread for forex backtests:
  - https://www.reddit.com/r/algotrading/comments/gp2rcq
- Reddit algotrading, live divergence after strong backtests:
  - https://www.reddit.com/r/algotrading/comments/1s5tihu/i_spent_35_years_building_a_forex_algo_from/

## 11. Siguiente paso recomendado

El siguiente entregable correcto ya no es otro texto general. Es una especificacion tecnica ejecutable con:

- parametros iniciales por estrategia;
- features exactas;
- esquema de clases en Python;
- orden de implementacion en QuantConnect;
- matriz de experimentos para backtesting.

