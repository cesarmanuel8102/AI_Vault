$ErrorActionPreference="Stop"
$ROOT="C:\AI_VAULT"
$CSV="$ROOT\60_METRICS\opportunity_scores.csv"

if(!(Test-Path $CSV)){
  Write-Host "Missing CSV: $CSV" -ForegroundColor Red
  exit 1
}

# Read existing IDs (avoid duplicates)
$existing = @{}
try {
  $rows = Import-Csv $CSV
  foreach($r in $rows){
    if($r.opportunity_id){ $existing[$r.opportunity_id.Trim()] = $true }
  }
} catch {}

function AddRow(
  [string]$id,[string]$name,[string]$cat,
  [int]$ttd,[int]$mrg,[int]$scal,[double]$capr,[int]$risk,[int]$comp,[int]$lgl,[int]$aut,
  [string]$evid
){
  if($existing.ContainsKey($id)){
    Write-Host "SKIP (exists): $id" -ForegroundColor DarkYellow
    return
  }

  # No commas allowed in free text fields for this simple CSV writer.
  $name = ($name -replace ",",";").Trim()
  $evid = ($evid -replace ",",";").Trim()

  $now = (Get-Date).ToString("s")
  $status="candidate"
  $score=""  # scoring fills it

  $line = @(
    $id,$name,$cat,$ttd,$mrg,$scal,$capr,$risk,$comp,$lgl,$aut,$evid,$score,$status,$now,$now
  ) -join ","

  Add-Content -Encoding UTF8 $CSV $line
  $existing[$id]=$true
  Write-Host "OK added: $id" -ForegroundColor Green
}

Write-Host "Populating 20 starter opportunities..." -ForegroundColor Cyan

# 20 oportunidades iniciales (MVP). Ajustaremos con reales después.
AddRow "OPP-001"  "Servicio: automatizar reportes Excel Docs para pequeños negocios" "services"   7  70 3  0 2 3 1 4 "demanda frecuente; entrega rapida"
AddRow "OPP-002"  "Servicio: crear dashboards KPI para negocios locales"            "services"  10  65 3  0 2 3 1 3 "valor claro; medible"
AddRow "OPP-003"  "Servicio: limpiar y estandarizar datos Excel para empresas"     "services"   7  75 3  0 2 3 1 4 "dolor comun; repetible"
AddRow "OPP-004"  "Servicio: automatizar emails y seguimiento de leads"            "services"  10  60 4  0 2 3 1 5 "automatizable; ROI evidente"
AddRow "OPP-005"  "Servicio: scripts para auditoria de PC y optimizacion"          "services"   5  60 3  0 2 3 1 3 "muchos usuarios con lentitud"

AddRow "OPP-006"  "Producto: pack de plantillas SOP para operaciones"              "product"   14  85 4 10 2 4 1 5 "escalable; bajo costo"
AddRow "OPP-007"  "Producto: plantilla de control financiero personal"             "product"   14  80 4 10 2 4 1 4 "mercado grande; simple"
AddRow "OPP-008"  "Producto: guia paso a paso IA local con scripts"                "product"   10  75 4  0 2 4 2 4 "alta demanda; soporte posible"
AddRow "OPP-009"  "Producto: toolkit de automatizacion para QA reportes"           "product"   14  85 4 20 2 4 1 5 "reutilizable; vendible"
AddRow "OPP-010"  "Producto: micro curso mantenimiento PC rendimiento"             "product"   21  70 4 10 2 4 1 3 "competitivo; aun viable"

AddRow "OPP-011"  "B2B: automatizar cotizaciones y seguimiento para pymes"          "b2b"       10  65 4  0 2 3 1 4 "pymes lo necesitan"
AddRow "OPP-012"  "B2B: automatizar facturas recibos y conciliacion basica"        "b2b"       14  60 4  0 2 3 1 4 "ahorro de tiempo"
AddRow "OPP-013"  "B2B: sistema simple de recordatorios pagos citas"               "b2b"        7  55 4  0 2 3 1 4 "facil; valor inmediato"
AddRow "OPP-014"  "B2B: generar reportes estandar semanales automatizados"         "b2b"       10  65 4  0 2 3 1 5 "muy automatizable"
AddRow "OPP-015"  "B2B: limpieza de datos + dashboard mensual"                     "b2b"       10  70 4  0 2 3 1 4 "servicio recurrente"

AddRow "OPP-016"  "Automation: capturar oportunidades y auto score diario"         "automation" 5   0 5  0 1 1 1 5 "acelera el sistema"
AddRow "OPP-017"  "Automation: RAG local para notas y procedimientos internos"     "automation" 7   0 5  0 1 2 1 5 "reduce friccion"
AddRow "OPP-018"  "Automation: pipeline logging decisiones y metricas"             "automation" 5   0 5  0 1 1 1 5 "gobernanza"
AddRow "OPP-019"  "Trading: sistema exploratorio paper a micro con control riesgo" "trading"   21  30 3 50 4 5 1 4 "solo exploratorio"
AddRow "OPP-020"  "Trading: arbitraje simple de volatilidad; validacion lenta"     "trading"   30  25 3 75 5 5 1 3 "probabilidad baja en 30 dias"

Write-Host "OK: Population done." -ForegroundColor Green