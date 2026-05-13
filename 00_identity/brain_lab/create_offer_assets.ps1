$LAB="C:\AI_VAULT\00_identity\brain_lab"
$MEM="$LAB\memory"
New-Item -ItemType Directory -Force -Path $MEM | Out-Null

# Oferta IDEA_10
@"
OFFER v1  IDEA_10
Nombre: Paquete de Automatización PowerShell/Windows
Cliente: Oficinas pequeñas
Dolor: PC lenta / archivos caóticos / tareas repetitivas
Solución: scripts + mantenimiento + checklist

Entregables (4872h):
1) Diagnóstico: disco/RAM/procesos startup + reporte
2) Limpieza: archivos temporales + recomendaciones
3) Automatización: 3 scripts personalizados (ej: backup, limpieza, organización)
4) Checklist mensual: 10 minutos para mantener estable

Precio: $149 (v1)
Garantía: si no mejora performance percibida o no queda automatización útil, se devuelve 100%.

Requisitos:
- Acceso local o remoto (aprobado)
- No se instalan herramientas piratas
- No se toca data sensible sin permiso explícito
"@ | Set-Content -Encoding UTF8 "$MEM\offer_IDEA_10.txt"

# Oferta IDEA_06
@"
OFFER v1  IDEA_06
Nombre: Kit de SOPs + Checklists Operativos
Cliente: Equipos pequeños
Dolor: procesos inconsistentes / errores repetidos / falta de estándar
Solución: SOP pack + entrenamiento corto

Entregables (5 días):
1) 8 SOPs base (operación + control + comunicación)
2) 10 checklists (diario/semanal/mensual)
3) Plantillas: reporte, seguimiento, control
4) Sesión 45 min: implementación

Precio: $499 (v1)
Garantía: si en 14 días no reduce errores/tiempo (según KPI), ajuste sin costo.

Requisitos:
- 30 min entrevista + revisión de flujo actual
- No se diseña nada ilegal / no spam / no fraude
"@ | Set-Content -Encoding UTF8 "$MEM\offer_IDEA_06.txt"

Write-Host "OK: Ofertas creadas en $MEM (offer_IDEA_10.txt / offer_IDEA_06.txt)" -ForegroundColor Green
