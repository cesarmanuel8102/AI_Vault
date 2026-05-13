$ErrorActionPreference = 'Continue'

$Root = 'C:\AI_VAULT\tmp_agent\strategies\mean_reversion_eq'
$PythonScript = Join-Path $Root 'run_local_campaign_gate_monitor.py'
$EmailScript = Join-Path $Root 'send_campaign_gate_email.py'
$JsonPath = Join-Path $Root 'campaign_gate_status_latest.json'
$AlertLog = Join-Path $Root 'campaign_gate_alert_status.txt'
$DesktopAlert = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ALERTA_TRADEIFY_CAMPAIGN_GATE.txt'

$timestamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
python $PythonScript | Out-Null

if (-not (Test-Path $JsonPath)) {
    "[$timestamp] ERROR: No existe $JsonPath" | Set-Content -Path $AlertLog -Encoding UTF8
    exit 1
}

try {
    $data = Get-Content $JsonPath -Raw | ConvertFrom-Json
    $state = [string]$data.state
    $action = [string]$data.action
    $age = [string]$data.campaign_age_days
    $start = [string]$data.campaign_start
    $last = [string]$data.last_signal
    $daysTo = [string]$data.days_to_activation_window

    $summary = @"
[$timestamp]
STATE: $state
ACTION: $action
CAMPAIGN_START: $start
LAST_SIGNAL: $last
CAMPAIGN_AGE_DAYS: $age
DAYS_TO_ACTIVATION_WINDOW: $daysTo

Archivos:
$JsonPath
$(Join-Path $Root 'campaign_gate_status_latest.txt')
"@

    $summary | Set-Content -Path $AlertLog -Encoding UTF8

    try {
        python $EmailScript | Out-Null
    }
    catch {
        "[$timestamp] EMAIL ERROR: $($_.Exception.Message)" | Add-Content -Path $AlertLog -Encoding UTF8
    }

    if ($state -eq 'ACTIVATION_WINDOW') {
        $msg = @"
ALERTA TRADEIFY / PROP FIRM

El monitor entro en ACTIVATION_WINDOW.
Accion: $action
Campana inicio: $start
Edad: $age dias
Ultima senal: $last

Revisar antes de comprar/activar cuenta.
"@
        $msg | Set-Content -Path $DesktopAlert -Encoding UTF8
        try { [console]::beep(1200, 600) } catch {}
        try { msg $env:USERNAME "TRADEIFY: ACTIVATION_WINDOW detectado. Revisar $DesktopAlert" } catch {}
    }
    elseif ($state -eq 'LATE_RISK_CONSISTENCY') {
        $msg = @"
ADVERTENCIA TRADEIFY / PROP FIRM

El monitor esta en LATE_RISK_CONSISTENCY.
No comprar tarde salvo override manual.
Campana inicio: $start
Edad: $age dias
Ultima senal: $last
"@
        $msg | Set-Content -Path $DesktopAlert -Encoding UTF8
        try { [console]::beep(800, 400) } catch {}
        try { msg $env:USERNAME "TRADEIFY: LATE_RISK_CONSISTENCY. No comprar tarde. Ver $DesktopAlert" } catch {}
    }
}
catch {
    "[$timestamp] ERROR: $($_.Exception.Message)" | Set-Content -Path $AlertLog -Encoding UTF8
    exit 1
}
