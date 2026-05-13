$LAB="C:\AI_VAULT\00_identity\brain_lab"
$MEM="$LAB\memory"
New-Item -ItemType Directory -Force -Path $MEM | Out-Null

$path = Join-Path $MEM "leads_day1.json"

# Plantilla: llenar a mano (sin scraping)
$stub = @()
for($i=1; $i -le 20; $i++){
  $stub += [pscustomobject]@{
    id = ("LEAD_{0:D2}" -f $i)
    business_name = ""
    contact_name  = ""
    email         = ""
    phone         = ""
    source        = "manual"
    niche         = "office_small"
    notes         = ""
    status        = "new"
  }
}

$stub | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $path
Write-Host "OK: Plantilla de 20 leads creada en $path" -ForegroundColor Green
Write-Host "Rellénala y mañana empezamos outreach 1:1 (Día 4 del plan), o antes si ya hay leads." -ForegroundColor Yellow
