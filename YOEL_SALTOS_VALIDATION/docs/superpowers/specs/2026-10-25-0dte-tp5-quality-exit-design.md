# Diseno: optimizacion disciplinada 0DTE TP 5%

## Intencion

Evaluar si la idea de primer rebote puede transformarse en una estrategia 0DTE
operable, conservando el take profit de 5% pero evitando que las operaciones que
no arrancan consuman gran parte de la prima. La meta es encontrar evidencia de
expectancy neta positiva fuera de muestra, no maximizar el resultado historico.

## Base congelada

- Universo, tendencia diaria y horaria, primer toque, medias y Bollinger iguales
  al estudio anterior.
- Opciones largas 0DTE ATM; no se continua optimizando OTM por su peor economia.
- Asignacion maxima de 10% del capital disponible por entrada.
- Take profit fijo de 5%, medido contra bid.
- Cierre obligatorio a las 15:55 ET y sin posiciones nocturnas.
- Modelo IBKR de comisiones y slippage constante de USD 0.01.

## Separacion temporal

- Desarrollo y seleccion: 2025-01-01 a 2025-12-31.
- Validacion bloqueada: 2026-01-01 a 2026-10-25.
- Ninguna regla se ajustara despues de observar 2026.

## Variantes preregistradas

1. **Control**: TP 5%, sin salida temprana adicional.
2. **Failure-to-launch**: a los 5 minutos, cerrar si la rentabilidad marcada al
   bid sigue por debajo de 0%.
3. **Failure-to-launch tolerante**: a los 8 minutos, cerrar si la rentabilidad
   marcada al bid sigue por debajo de -2%.
4. **Calidad + mejor failure-to-launch de 2025**: exigir volumen relativo >= 1.2
   y que el cierre de la vela de senal quede en el 25% direccional extremo de su
   rango. No se probaran umbrales adicionales.

La seleccion en 2025 priorizara profit factor neto, expectancy neta por trade,
drawdown y estabilidad por semestre. El retorno total solo desempata.

## Validacion 2026

Solo el control y una unica variante seleccionada con 2025 se ejecutaran en 2026.
La variante sera considerada prometedora si, despues de costes:

- expectancy por operacion > 0;
- profit factor > 1.0;
- retorno neto > 0;
- drawdown menor que el control;
- al menos 12 operaciones, o se declarara muestra insuficiente.

## Instrumentacion

Cada operacion registrara hora, simbolo, media tocada, volumen relativo, posicion
del cierre dentro de la vela, prima de entrada, PnL a 5 y 8 minutos, motivo y hora
de salida. Los resultados se reportaran separados por periodo, simbolo y semestre.

## Enfoques descartados

- Barrido amplio de tiempos, stops e indicadores: produciria sobreajuste con solo
  46 operaciones en la muestra completa.
- Usar la duracion media de ganadoras: ya empeoro los resultados y condiciona la
  regla a informacion futura.
- Continuar con OTM: tuvo peor retorno y aproximadamente el doble de comisiones.

## Entregables

- Codigo y pruebas de las reglas nuevas.
- Backtests QuantConnect reproducibles de 2025 y validacion 2026.
- Tabla comparativa neta de comisiones y veredicto GO / NO-GO / INSUFICIENTE.

