# Precursores de perdida en la estrategia 0DTE TP5

Fecha: 2026-10-25  
Motor: QuantConnect LEAN Cloud  
Vehiculo: opciones ATM 0DTE  
TP: 5% sobre la prima  
Capital por entrada: 10% del patrimonio disponible

## Pregunta

Se puede conservar la alta tasa de acierto y reconocer las pocas operaciones
destructivas antes de que consuman casi toda la prima?

## Metodo

El control no se modifico. En cada entrada se registraron prima, cantidad,
friccion estimada, direccion, media tocada, volumen y contexto del subyacente.
Para posiciones abiertas se observaron checkpoints a 3, 5, 10, 15 y 30
minutos. El periodo 2023-2024 se uso para formular la regla y 2025-2026 para
confirmarla sin cambiarla.

La regla causal congelada fue:

1. no entrar si la friccion estimada de ida y vuelta supera el TP de 5%;
2. a los 15 minutos, salir solo si la opcion sigue perdiendo y el subyacente ha
   cruzado en contra la media tocada o el extremo invalidador de la vela.

No se uso un stop porcentual de la prima. Tampoco se buscaron combinaciones de
umbrales para maximizar retrospectivamente el PnL.

## Resultados anuales

| Ano | Control PnL | Control PF | Regla PnL | Regla PF | Ganadoras conservadas |
|---:|---:|---:|---:|---:|---:|
| 2023 | -$8,522.00 | 0.560 | +$2,021.28 | 1.454 | 66.7% |
| 2024 | -$43,669.28 | 0.199 | -$28,833.38 | 0.240 | 83.3% |
| 2025 | -$16,984.41 | 0.449 | -$13,100.02 | 0.382 | 73.7% |
| 2026 | -$24,525.36 | 0.335 | -$3,246.66 | 0.750 | 82.4% |

## Periodos agregados

| Periodo | Variante | Trades | Ganadoras | PnL | PF | Perdida media |
|---|---|---:|---:|---:|---:|---:|
| 2023-2024 | Control | 37 | 27 | -$52,191.28 | 0.293 | -$7,386.18 |
| 2023-2024 | Regla | 26 | 20 | -$26,812.10 | 0.368 | -$7,068.40 |
| 2025-2026 | Control | 46 | 36 | -$41,509.77 | 0.387 | -$6,766.73 |
| 2025-2026 | Regla | 33 | 28 | -$16,346.67 | 0.522 | -$6,834.14 |

El filtro reduce mucho el dano total, especialmente en 2026, pero no genera
expectancy positiva. En confirmacion solo tres posiciones activaron la salida
causal. Las perdidas restantes no habian invalidado limpiamente el subyacente a
los 15 minutos, aunque la opcion terminara deteriorandose por convexidad, theta,
spread y movimiento posterior.

## Interpretacion

La dificultad no es simplemente encontrar un stop mejor. Un TP bruto de 5%
necesita aproximadamente veinte ganancias para compensar una perdida total de
prima de igual tamano nocional, antes de costes. Con aciertos de 63%-83%, unas
pocas expiraciones cercanas a perdida total dominan inevitablemente muchas
ganancias pequenas.

Los checkpoints tampoco separan limpiamente ganadoras y perdedoras: varias
ganadoras mostraron retrocesos fuertes de la prima antes de alcanzar el TP. Un
stop mas sensible reduce perdidas, pero tambien liquida demasiadas futuras
ganadoras; uno basado solo en el subyacente llega demasiado tarde o no se activa.

## Veredicto

**NO-GO.** La regla de precursor reduce el dano, pero falla los criterios
pre-registrados de PnL positivo y PF mayor que 1 en formulacion y confirmacion.
No debe incorporarse como estrategia operable.

La siguiente hipotesis con sentido economico no es otro stop. Es cambiar la
distribucion de retornos: realizar una parte al +5% y conservar un runner con un
objetivo sustancialmente mayor o una salida ligada al subyacente. Eso intenta
mantener la frecuencia de aciertos y elevar la ganancia media, que es la variable
que actualmente impide la solvencia. Debe probarse como estudio nuevo y
pre-registrado, no como ajuste de esta muestra.

## Reproducibilidad

- Descubrimiento 2023: backtest `bf40799cd18aff94bf4f103cfcb7e345`.
- Descubrimiento 2024: backtest `21bf2f7e8c8d8a16587921a9a0d61d0f`.
- Confirmacion 2025: backtest `e7bfb4f75be064d97d3aa6a74c7170f9`.
- Confirmacion 2026: backtest `06d4350305528d6b832e2fef1000667e`.
- Resultados agregados: `zero_dte_loss_precursor_discovery.json` y
  `zero_dte_loss_precursor_confirmation.json`.
- Analizador: `analyze_loss_precursors.py`.
