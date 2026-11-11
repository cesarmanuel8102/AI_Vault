# Supuestos y limites

- La transcripcion es automatica y contiene segmentos corruptos.
- El curso no define matematicamente "inicio", "final de tendencia", "punto medio" ni "edge line".
- La regla principal usa apilado SMA20/SMA40 porque es la operacionalizacion preregistrada en la especificacion recibida.
- Los precios de la comprobacion independiente son OHLCV diarios ajustados de Yahoo Finance. Esta fuente sirve como control independiente, no sustituye la replica en QuantConnect/LEAN.
- La exclusion de earnings usa volumen extraordinario como proxy y no un calendario corporativo real.
- El control no esta emparejado aun por tercil de ATR; si la senal ya queda por debajo de la base no emparejada, esta limitacion no rescata la afirmacion de 90%, pero debe corregirse si se busca estimar un efecto pequeno con precision.
- META hereda la serie historica del simbolo actual; las acciones con historia corta solo participan desde su disponibilidad.
- La Fase A estudia la afirmacion predictiva del subyacente. No modela spreads, theta, IV ni fills de opciones.
