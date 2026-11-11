# Especificacion: operabilidad posterior a un shock

Fecha: 2026-10-25

## Objetivo

Determinar si la intuicion rescatable del curso, persistencia direccional o
reversion despues de un movimiento anormal, produce una estrategia operable y
rentable despues de costos.

## Hipotesis congeladas

1. `CONTINUATION_CLOSE`: tras un gap en direccion de la tendencia, entrar al
   cierre de la senal y mantener 1, 3 o 5 sesiones.
2. `OPENING_CONTINUATION`: tras el mismo gap, entrar cuando los primeros 30
   minutos confirman la direccion y mantener hasta el cierre.
3. `OPENING_FADE`: control contrario; operar el cierre parcial del gap cuando
   los primeros 30 minutos rechazan la direccion inicial.

El shock se normaliza por ATR y se prueba con umbrales predefinidos de 0.75,
1.00 y 1.25 ATR. El contexto usa SMA20/SMA40, volumen relativo y liquidez. No
se elige un parametro usando el resultado OOS.

## Universo y periodos

- Universo: U2 liquido del estudio anterior.
- IS: 2008-2017.
- Validacion: 2018-2021.
- OOS final: 2022-2025.
- Se reportan resultados agregados, por ano y por simbolo.

## Ejecucion y riesgo

- Primera fase con acciones; las opciones solo se estudian si el subyacente
  supera el criterio GO.
- Capital: USD 100,000; riesgo maximo teorico por entrada 0.50% del patrimonio.
- Maximo 10 posiciones simultaneas y una posicion por simbolo.
- Entrada en la siguiente barra disponible despues de confirmar la senal.
- Comision y slippage no nulos; no se permite look-ahead.
- Salida temporal al cumplir el horizonte, stop de 1 ATR y objetivo de 2 ATR.
- No hay promedios a la baja ni refuerzos.

## Criterio GO

Una familia pasa solo si, en OOS final y despues de costos:

- retorno total y CAGR positivos;
- Sharpe >= 0.75;
- profit factor >= 1.15;
- max drawdown <= 20%;
- al menos 100 operaciones;
- resultado positivo en al menos 60% de anos y 55% de simbolos con muestra;
- parametros vecinos conservan el signo de la expectativa;
- supera comprar y mantener en retorno ajustado por drawdown o demuestra baja
  correlacion con contribucion positiva de cartera.

Un fallo mantiene el veredicto `NO_GO`; no se optimizan opciones.
