# Preregistro: validacion de la estrategia de saltos

Fecha: 2026-10-25

## Hipotesis principal

Tras un primer gap valido de al menos 1% en la direccion de una tendencia compatible, y sin otro gap de ese tamano en las cinco sesiones anteriores, la probabilidad de otro gap de al menos 1% en la misma direccion en la sesion siguiente es superior a la frecuencia base.

La afirmacion verbal del curso es aproximadamente 90%.

## Regla principal congelada

- Tendencia alcista: SMA20 > SMA40 y cierre previo > SMA40. Bajista: simetrica.
- Primer salto: gap de apertura de al menos 1% en la direccion de la tendencia y ningun gap absoluto de al menos 1% en las cinco sesiones anteriores.
- Segundo salto: gap de apertura de al menos 1% en la misma direccion en la siguiente sesion.
- Control: sesiones con el mismo contexto de tendencia que no son primer salto.
- Filtro de noticia aproximado: excluir volumen del dia de la senal superior a 2,5 veces el promedio previo de 20 sesiones.
- IS: antes de 2022. OOS: 2022 en adelante.
- Universo U1: lista citada en el curso. U2: U1 mas 25 acciones y ETF liquidos.

## Sensibilidad congelada

- Gap: 0,5%, 1%, 1,5% y 2%.
- Ausencia de gap previo: 5 y 10 sesiones.
- Tendencia normal y estricta (esta ultima exige tambien posicion respecto a SMA100).
- Con y sin exclusion por volumen extraordinario.

## Criterio GO

La tasa del segundo salto debe superar la base en al menos 10 puntos porcentuales, con el limite inferior Wilson 95% por encima de la base, signo consistente IS/OOS y lift positivo en al menos 70% de los tickers con muestra suficiente. Ninguna definicion se cambia tras observar OOS.

Si la Fase A falla, no se optimiza una estrategia de opciones: se conserva el resultado NO-GO y solo se usa evidencia previa de opciones como corroboracion secundaria.
