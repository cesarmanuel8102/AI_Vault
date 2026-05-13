param(
  [string]$LabRoot = "C:\AI_VAULT\00_identity\brain_lab",
  [string]$OllamaUrl = "http://127.0.0.1:11434",
  [int]$UiPort = 8010,
  [int]$GenTimeoutSec = 60,
  [switch]$HybridPreset
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function WriteUtf8NoBom([string]$Path, [string]$Text) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Text, $utf8NoBom)
}

function Get-OllamaTags([string]$Url) {
  Invoke-RestMethod -Uri ($Url.TrimEnd('/') + "/api/tags") -Method Get -TimeoutSec 10
}

function Test-OllamaGenerate([string]$Url, [string]$Model, [int]$TimeoutSec) {
  $payload = [ordered]@{
    model  = $Model
    prompt = "Responde en español en 1 frase: OK"
    stream = $false
  }
  $body  = ($payload | ConvertTo-Json -Depth 6)
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
  try {
    $r = Invoke-RestMethod -Uri ($Url.TrimEnd('/') + "/api/generate") -Method Post -ContentType "application/json" -Body $bytes -TimeoutSec $TimeoutSec
    if ($null -ne $r.response -and $r.response.ToString().Length -gt 0) { return $true }
    return $false
  } catch {
    return $false
  }
}

function Pick-OperationalModel($tags) {
  # Prefer: llama3.1:8b, qwen2.5:7b, mistral:7b, llama3:8b, etc.
  $names = @()
  foreach ($m in $tags.models) { $names += $m.name }

  $prefs = @(
    "llama3.1:8b",
    "qwen2.5:7b",
    "mistral:7b",
    "llama3:8b",
    "qwen2.5:8b",
    "phi3:mini",
    "qwen2.5:3b",
    "llama3.2:3b"
  )

  foreach ($p in $prefs) {
    if ($names -contains $p) { return $p }
  }

  # If none matched, pick smallest size in tags
  $best = $null
  $bestSize = [double]::PositiveInfinity
  foreach ($m in $tags.models) {
    if ($m.size -lt $bestSize) { $best = $m.name; $bestSize = $m.size }
  }
  return $best
}

function Kill-Port([int]$Port) {
  $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  $procId = $c.OwningProcess | Select-Object -First 1
  if ($procId) {
    Write-Host "Killing process on port $Port (PID=$procId)..." -ForegroundColor Yellow
    try {
      Get-CimInstance Win32_Process -Filter "ProcessId=$procId" | Select-Object ProcessId, Name, CommandLine | Format-List | Out-String | Write-Host
    } catch {}
    Stop-Process -Id $procId -Force
    Start-Sleep -Seconds 1
  } else {
    Write-Host "No process listening on port $Port" -ForegroundColor DarkGray
  }
}

function Start-UI([string]$LabRoot) {
  $ps1 = Join-Path $LabRoot "start_brain_ui.ps1"
  if (!(Test-Path $ps1)) { throw "No existe: $ps1" }
  powershell -File $ps1 | Out-Null
}

function Invoke-ChatDebug([int]$Port) {
  $payload = [ordered]@{
    message    = "Quién eres y cuál es tu plan operativo de HOY en 5 pasos? (sin pedirme ideas)"
    session_id = ""
    sender     = "Cesar"
    debug      = $true
  }
  $body  = ($payload | ConvertTo-Json -Depth 6)
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)

  try {
    Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/api/chat" -f $Port) -Method Post -ContentType "application/json" -Body $bytes -TimeoutSec 60
  } catch {
    @{ ok=$false; error=$_.Exception.Message }
  }
}

# ---- MAIN ----
$gov = Join-Path $LabRoot "governance"
$cfgPath = Join-Path $gov "llm_config.json"
if (!(Test-Path $gov)) { throw "No existe governance: $gov" }

Write-Host "1) Leyendo modelos de Ollama..." -ForegroundColor Cyan
$tags = Get-OllamaTags -Url $OllamaUrl
$tags.models | Select-Object name, size, modified_at | Format-Table -AutoSize

Write-Host "`n2) Seleccionando modelo operativo..." -ForegroundColor Cyan
$opModel = Pick-OperationalModel $tags
if (-not $opModel) { throw "No pude seleccionar modelo operativo (no hay modelos en Ollama)" }

Write-Host "Modelo operativo candidato: $opModel" -ForegroundColor Green

Write-Host "`n3) Probando generate con timeout=$GenTimeoutSec ..." -ForegroundColor Cyan
$ok = Test-OllamaGenerate -Url $OllamaUrl -Model $opModel -TimeoutSec $GenTimeoutSec
if (-not $ok) {
  Write-Host "WARN: $opModel falló en generate (timeout/otro). Probaré el modelo más pequeño disponible..." -ForegroundColor Yellow
  # pick smallest
  $opModel = ($tags.models | Sort-Object size | Select-Object -First 1).name
  Write-Host "Nuevo candidato (más pequeño): $opModel" -ForegroundColor Yellow
  $ok = Test-OllamaGenerate -Url $OllamaUrl -Model $opModel -TimeoutSec $GenTimeoutSec
  if (-not $ok) { throw "Ollama generate sigue fallando incluso con $opModel. Revisa rendimiento/RAM/CPU o modelo." }
}

Write-Host "OK: Ollama generate responde con $opModel" -ForegroundColor Green

Write-Host "`n4) Escribiendo llm_config.json (UTF8 sin BOM)..." -ForegroundColor Cyan
if ($HybridPreset) {
  # Preset híbrido (operativo + profundo). El router actual usa default_model,
  # pero dejamos el config listo para la siguiente iteración.
  $cfg = [ordered]@{
    ollama_url      = $OllamaUrl
    default_model   = $opModel
    deep_model      = "qwen2.5:14b"
    temperature     = 0.2
    max_chars       = 1600
    deep_max_chars  = 2600
    gen_timeout_sec = $GenTimeoutSec
  }
} else {
  $cfg = [ordered]@{
    ollama_url      = $OllamaUrl
    default_model   = $opModel
    temperature     = 0.2
    max_chars       = 1600
    gen_timeout_sec = $GenTimeoutSec
  }
}

$json = ($cfg | ConvertTo-Json -Depth 6)
WriteUtf8NoBom -Path $cfgPath -Text $json
Write-Host "OK: Config actualizado en $cfgPath" -ForegroundColor Green

Write-Host "`n5) Reiniciando UI limpiamente (matar puerto $UiPort)..." -ForegroundColor Cyan
Kill-Port -Port $UiPort
Start-UI -LabRoot $LabRoot

Write-Host "`n6) Health check..." -ForegroundColor Cyan
$health = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/health" -f $UiPort) -Method Get -TimeoutSec 10
$health | Format-List

Write-Host "`n7) Prueba chat (debug)..." -ForegroundColor Cyan
$chat = Invoke-ChatDebug -Port $UiPort
$chat | ConvertTo-Json -Depth 8

Write-Host "`nDONE." -ForegroundColor Green
