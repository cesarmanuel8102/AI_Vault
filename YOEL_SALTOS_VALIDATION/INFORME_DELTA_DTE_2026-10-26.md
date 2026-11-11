# Informe delta/DTE - primer rebote de Yoel

## Configuracion congelada

- QuantConnect project 38449639.
- Periodo 2025-01-01 a 2026-10-25.
- Capital inicial USD 100,000; 10% maximo de capital disponible por entrada.
- Misma senal, universo y timing del estudio anterior.
- Sin stop loss; cierre forzoso 15:55 ET.
- Modelo de comisiones Interactive Brokers y slippage constante de USD 0.01.
- Matriz: delta 0.50/DTE0 y delta 0.70/DTE0/7/14, cada uno con TP 10% y 15%.

## Resultados cloud completados

| Delta / DTE | TP | Delta/DTE efectivos | Trades | Ganadoras | Objetivos | Retorno neto | Fees | DD | Sharpe | PF antes fees |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.50 / 0 | 10% | 0.5118 / 0.00 | 46 | 36 (78.3%) | 36 | -26.59% | $12,831 | 28.2% | -0.751 | 0.76 |
| 0.50 / 0 | 15% | 0.5118 / 0.00 | 46 | 33 (71.7%) | 33 | -37.38% | $12,113 | 39.0% | -0.888 | 0.67 |
| **0.70 / 0** | **10%** | **0.7241 / 0.00** | **46** | **35 (76.1%)** | **35** | **-14.75%** | **$5,514** | **20.3%** | **-0.551** | **0.82** |
| 0.70 / 0 | 15% | 0.7241 / 0.00 | 46 | 31 (67.4%) | 31 | -28.67% | $4,835 | 30.3% | -0.747 | 0.65 |
| 0.70 / 7 | 10% | 0.7057 / 7.28 | 93 | 43 (46.2%) | 39 | -50.31% | $4,431 | 50.8% | -2.402 | 0.38 |
| 0.70 / 7 | 15% | 0.7057 / 7.28 | 93 | 38 (40.9%) | 27 | -51.02% | $4,377 | 52.0% | -2.256 | 0.41 |
| 0.70 / 14 | 10% | 0.6996 / 13.89 | 93 | 35 (37.6%) | 28 | -54.01% | $2,795 | 54.5% | -2.781 | 0.27 |
| 0.70 / 14 | 15% | 0.6996 / 13.89 | 93 | 32 (34.4%) | 17 | -54.09% | $2,778 | 54.8% | -2.736 | 0.29 |

## Lectura

1. La tasa cercana al 80% se reproduce en delta 0.50/DTE0/TP10: 36 de 46 operaciones ganadoras. No se convierte en expectancy positiva.
2. Delta 0.70 ITM mejora mucho el 0DTE. Con TP10 reduce la perdida neta de -26.59% a -14.75%, las comisiones de $12,831 a $5,514 y el drawdown de 28.2% a 20.3%.
3. TP10 domina TP15 en las cuatro estructuras. Esperar 15% reduce aciertos y aumenta sustancialmente las perdidas.
4. DTE7 y DTE14 no funcionan con salida intradia. El movimiento diario del contrato es menor, los objetivos se alcanzan menos y la tasa de acierto cae. Ademas operan las 93 senales, mientras 0DTE solo puede operar las 46 con vencimiento ese mismo dia; esta diferencia de cobertura impide interpretar la comparacion como una muestra perfectamente emparejada.
5. El mejor caso sigue perdiendo antes de comisiones: sus operaciones suman -$9,236 antes de $5,514 en fees. Por tanto, reducir comisiones no basta para volverlo rentable.

## Veredicto

Ninguna variante es operable todavia. La mejor base para continuar es delta 0.70 ITM, DTE0 y TP10, porque conserva 76.1% de ganadoras y presenta la menor perdida, menor drawdown y mayor profit factor de la matriz. El siguiente estudio no deberia volver a variar TP/DTE: debe identificar causalmente la cola de 11 salidas perdedoras de esta variante o cambiar la distribucion de salida, con validacion fuera de muestra.

Los resultados crudos y los IDs inmutables estan registrados en `delta_dte_matrix_manifest.json`.
