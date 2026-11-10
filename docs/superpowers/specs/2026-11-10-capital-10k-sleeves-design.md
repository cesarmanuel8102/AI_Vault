# Capital de USD 10,000 por sleeve — diseño

## Intención

Elevar la autoridad económica de `REGULAR_SLEEVE` y `CONTINUOUS_SLEEVE` desde USD 500 hasta USD 10,000 cada uno, preservando el P&L acumulado, el reloj vigente y todo el historial append-only.

## Decisión aprobada

- Registrar un aporte de capital de USD 9,500 en cada sleeve.
- Mantener el P&L histórico; el aporte no es ganancia ni pérdida.
- Mantener el epoch y el reloj de 30 días actuales.
- Mantener ambos sleeves aislados: no hay transferencias, préstamos ni offsets cruzados.
- Mantener la política `AGGRESSIVE_CAPITAL_BOUNDARY_V1` y su límite de responsabilidad máxima igual al equity disponible de cada sleeve.
- Actualizar el benchmark aspiracional a duplicar USD 10,000 por sleeve y USD 20,000 agregados.

## Arquitectura

La ampliación se representa mediante eventos `CAPITAL_CONTRIBUTION` en el ledger. Cada evento aumenta simultáneamente la asignación autorizada y el efectivo USD, sin modificar realized P&L, unrealized P&L, fees ni reloj.

Las autoridades de sleeve y la autorización económica se enmiendan mediante eventos append-only que enlazan criptográficamente con la autoridad anterior. La raíz de la cadena debe seguir coincidiendo con el target de transición existente; la autoridad efectiva más reciente debe coincidir con la asignación del ledger.

La migración de producción será única, atómica e idempotente. Exigirá cuenta reconciliada, ambos sleeves sin posiciones, órdenes ni responsabilidad reservada, copia previa de SQLite y coincidencia exacta con la asignación anterior de USD 500.

## Requisitos

- Estado final esperado: asignación USD 10,000 en cada sleeve.
- Equity esperado: equity anterior + USD 9,500 por sleeve.
- P&L acumulado idéntico antes y después.
- Ningún cambio en start/end del reloj ni epoch.
- La autoridad original permanece verificable como raíz.
- Un segundo intento idéntico es idempotente; cualquier importe o identidad distinta falla cerrado.
- El runtime sólo habilita nueva responsabilidad si ledger, autoridad efectiva y linaje del target coinciden.
- No se envían órdenes durante la migración.

## Enfoques considerados

1. **Aporte append-only con enmienda de autoridad (seleccionado).** Conserva historia, P&L y reloj; deja evidencia auditable.
2. Resetear cada sleeve a USD 10,000. Rechazado porque borraría económicamente el resultado acumulado.
3. Añadir efectivo sin actualizar autoridad/asignación. Rechazado porque produciría una discrepancia peligrosa entre solvencia, reporting y ejecución.

## No objetivos

- No cambiar estrategia, cadencia, universo ni autonomía del agente.
- No modificar las posiciones o decisiones históricas.
- No conectar al puerto LIVE 4001.
- No reiniciar el reloj.
