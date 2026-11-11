# Diseno: precursores de perdida 0DTE

## Objetivo

Conservar la alta tasa de acierto del control ATM 0DTE con TP 5% y reducir las
pocas perdidas extremas usando exclusivamente informacion disponible antes de la
salida.

## Fase observacional

- Mantener sin cambios entradas, TP 5%, sizing 10% y cierre 15:55.
- Registrar al entrar: prima, cantidad, spread relativo, direccion, media tocada,
  volumen relativo, ubicacion direccional del cierre, precio del subyacente,
  media e invalidacion de la vela de senal.
- Para posiciones aun abiertas registrar a 3, 5, 10, 15 y 30 minutos: retorno al
  bid de la opcion, avance direccional del subyacente, distancia direccional a la
  media, distancia al extremo invalidador y spread relativo.
- Usar 2023-2024 para formular una unica regla. 2025-2026 se usan como confirmacion
  historica; ya no son fuera de muestra puro porque sus resultados agregados se
  observaron antes de este estudio.

## Regla candidata

La regla combinara como maximo:

1. un gate economico derivado de comision y slippage frente al TP, no de un
   barrido de primas;
2. invalidacion del subyacente respecto a la media o vela de senal;
3. un unico checkpoint failure-to-launch cuando opcion y subyacente confirmen
   ausencia de avance.

No se usara un stop fijo de prima: las ganadoras ya observadas soportaron una MAE
mediana cercana a 11.5%.

## Criterio

La regla debe conservar al menos 70% de las operaciones ganadoras del control,
reducir la perdida media, producir expectancy neta positiva y PF > 1 tanto en el
periodo de formulacion como en la confirmacion. Si no, NO-GO.
