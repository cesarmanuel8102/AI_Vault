#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\AI_VAULT",
    [int]$WindowSeconds = 330,
    [int]$GapSeconds = 1500
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$StateReportRoot = Join-Path $RepoRoot "state\ibkr_paper_30d\reports"
$AuditorStatusPath = Join-Path $StateReportRoot "auditor_gate_v2_status.json"
$AuditorReceiptPath = Join-Path $StateReportRoot "auditor_gate_v2_receipt.json"
$MarketLedger = Join-Path $StateReportRoot "market_observations.jsonl"
$MarketObservationReport = Join-Path $StateReportRoot "market_observation.json"
$MarketPolicy = Join-Path $StateReportRoot "market_data_policy_v1.json"
$MarketPolicyReport = Join-Path $StateReportRoot "market_policy_freeze.json"
$MarketValidationReport = Join-Path $StateReportRoot "market_data_validation.json"
$ReadonlyReport = Join-Path $StateReportRoot "read_only_real_paper_reconciliation.json"
$FinalReadyReport = Join-Path $StateReportRoot "final_preflight_ready.json"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

function Get-Python {
    $venv = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venv -PathType Leaf) { return $venv }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { $cmd = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $cmd) { throw "PYTHON_NOT_FOUND" }
    return $cmd.Source
}

function Require-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "REQUIRED_FILE_MISSING:$Path"
    }
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $encoding = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Get-EasternNow {
    $tz = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    return [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz)
}

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "REPO_ROOT_NOT_FOUND:$RepoRoot"
}
Set-Location $RepoRoot
$Python = Get-Python

if ($env:IBKR_AUTONOMOUS_PAPER_ARMED -and $env:IBKR_AUTONOMOUS_PAPER_ARMED.ToLowerInvariant() -eq "true") {
    throw "PAPER_EXECUTOR_IS_ARMED_DURING_PREFLIGHT. Unset IBKR_AUTONOMOUS_PAPER_ARMED before continuing."
}

Require-File $AuditorStatusPath
Require-File $AuditorReceiptPath

$AuditorStatus = Get-Content -LiteralPath $AuditorStatusPath -Raw | ConvertFrom-Json
if ($AuditorStatus.gate -ne "PASS") {
    throw "AUDITOR_GATE_V2_NOT_PASS"
}
$AuditorReceipt = Get-Content -LiteralPath $AuditorReceiptPath -Raw | ConvertFrom-Json
$AuditorCompleted = [DateTime]::Parse([string]$AuditorReceipt.completed_at_utc).ToUniversalTime()
$AuditorAge = [DateTime]::UtcNow - $AuditorCompleted
if ($AuditorAge.TotalHours -ge 24) {
    throw "AUDITOR_GATE_V2_RECEIPT_STALE. Re-run FINALIZE_IBKR_AUDITOR_ADMIN.ps1 before market-data finalization."
}

Write-Step "Verify current time is suitable for 68-minute regular-session evidence run"
$EasternNow = Get-EasternNow
if ($EasternNow.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)) {
    throw "REGULAR_MARKET_SESSION_REQUIRED:today=$($EasternNow.DayOfWeek)"
}
$minStart = New-TimeSpan -Hours 9 -Minutes 35
$maxStart = New-TimeSpan -Hours 14 -Minutes 30
if ($EasternNow.TimeOfDay -lt $minStart -or $EasternNow.TimeOfDay -gt $maxStart) {
    throw ("START_TIME_OUTSIDE_SAFE_WINDOW_ET:{0:yyyy-MM-dd HH:mm:ss}" -f $EasternNow)
}

Write-Step "Verify local IBKR Paper Gateway"
$portOpen = Test-NetConnection -ComputerName 127.0.0.1 -Port 4002 -InformationLevel Quiet
if (-not $portOpen) {
    throw "IBKR_PAPER_GATEWAY_4002_NOT_REACHABLE"
}

Write-Step "Refresh real read-only IBKR reconciliation"
& $Python -m ibkr_paper_30d.cli inspect-ibkr-readonly --host 127.0.0.1 --port 4002
if ($LASTEXITCODE -ne 0) { throw "READONLY_RECONCILIATION_COMMAND_FAILED" }
Require-File $ReadonlyReport
$Readonly = Get-Content -LiteralPath $ReadonlyReport -Raw | ConvertFrom-Json
if (
    $Readonly.status -ne "PASS" -or
    $Readonly.paper_account_identity_gate -ne "PASS" -or
    $Readonly.broker_reconciliation_gate -ne "PASS"
) {
    throw ("READONLY_RECONCILIATION_NOT_PASS:" + (($Readonly.reason_codes | ForEach-Object { [string]$_ }) -join ","))
}

if (Test-Path -LiteralPath $MarketValidationReport) {
    try {
        $existingValidation = Get-Content -LiteralPath $MarketValidationReport -Raw | ConvertFrom-Json
        if ($existingValidation.status -eq "PASS" -and $existingValidation.market_data_gate -eq "PASS" -and (Test-Path -LiteralPath $MarketPolicy)) {
            Write-Host "MARKET DATA GATE already PASS; no new evidence run required." -ForegroundColor Green
            exit 0
        }
    } catch {}
}

Write-Step "Archive previous market-policy evidence without deleting it"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archive = Join-Path $StateReportRoot ("market_archive_" + $stamp)
[void](New-Item -ItemType Directory -Path $archive -Force)
foreach ($path in @($MarketLedger, $MarketObservationReport, $MarketPolicy, $MarketPolicyReport, $MarketValidationReport)) {
    if (Test-Path -LiteralPath $path) {
        Move-Item -LiteralPath $path -Destination (Join-Path $archive ([IO.Path]::GetFileName($path)))
    }
}

Write-Step "Collect 3 independent real-time regular-session evidence windows"
$windows = @()
for ($i = 1; $i -le 3; $i++) {
    $start = Get-EasternNow
    Write-Host ("Window {0}/3 start ET: {1:HH:mm:ss}" -f $i, $start) -ForegroundColor Yellow

    & $Python -m ibkr_paper_30d.cli observe-market-data --host 127.0.0.1 --port 4002 --symbols SPY QQQ IEF --cadence-seconds 5 --window-seconds $WindowSeconds
    if ($LASTEXITCODE -ne 0) { throw "MARKET_OBSERVATION_COMMAND_FAILED:window=$i" }

    Require-File $MarketObservationReport
    $obs = Get-Content -LiteralPath $MarketObservationReport -Raw | ConvertFrom-Json
    if ($obs.status -ne "PASS") {
        throw ("MARKET_OBSERVATION_NOT_PASS:window=${i}:" + (($obs.reason_codes | ForEach-Object { [string]$_ }) -join ","))
    }
    if ([int]$obs.rejected_observation_count -ne 0) {
        throw "MARKET_OBSERVATION_HAS_REJECTIONS:window=$i rejected=$($obs.rejected_observation_count)"
    }
    if ([int]$obs.accepted_observation_count -lt 180) {
        throw "MARKET_OBSERVATION_SAMPLE_TOO_SMALL:window=$i accepted=$($obs.accepted_observation_count)"
    }

    $windows += [ordered]@{
        window = $i
        window_id = [string]$obs.window_id
        accepted = [int]$obs.accepted_observation_count
        rejected = [int]$obs.rejected_observation_count
        start_et = $start.ToString("o")
    }

    if ($i -lt 3) {
        Write-Host "Waiting $GapSeconds seconds so next window starts >30 minutes after the prior one..." -ForegroundColor DarkYellow
        Start-Sleep -Seconds $GapSeconds
    }
}

Write-Step "Freeze MARKET_DATA_POLICY_V1 from collected evidence"
& $Python -m ibkr_paper_30d.cli freeze-market-policy --ledger $MarketLedger --destination $MarketPolicy
if ($LASTEXITCODE -ne 0) { throw "MARKET_POLICY_FREEZE_COMMAND_FAILED" }

Require-File $MarketPolicyReport
$freeze = Get-Content -LiteralPath $MarketPolicyReport -Raw | ConvertFrom-Json
if ($freeze.status -notin @("PASS","ALREADY_FROZEN") -or -not [bool]$freeze.market_data_policy_frozen) {
    throw ("MARKET_POLICY_FREEZE_NOT_PASS:" + (($freeze.reason_codes | ForEach-Object { [string]$_ }) -join ","))
}

Write-Step "Validate fresh real market data against frozen policy"
& $Python -m ibkr_paper_30d.cli validate-real-market-data --host 127.0.0.1 --port 4002 --policy $MarketPolicy
if ($LASTEXITCODE -ne 0) { throw "MARKET_DATA_VALIDATION_COMMAND_FAILED" }

Require-File $MarketValidationReport
$validation = Get-Content -LiteralPath $MarketValidationReport -Raw | ConvertFrom-Json
if ($validation.status -ne "PASS" -or $validation.market_data_gate -ne "PASS") {
    throw ("MARKET_DATA_GATE_NOT_PASS:" + (($validation.reason_codes | ForEach-Object { [string]$_ }) -join ","))
}

Write-Step "Write final experiment readiness receipt"
$final = [ordered]@{
    schema = "CODEX_IBKR_FINAL_PREFLIGHT_READY_V1"
    ready_for_paper_experiment = $true
    created_at_utc = [DateTime]::UtcNow.ToString("o").Replace("+00:00","Z")
    auditor_gate_v2 = "PASS"
    auditor_receipt_completed_at_utc = [string]$AuditorReceipt.completed_at_utc
    market_data_policy_frozen = $true
    market_data_gate = "PASS"
    market_policy_sha256 = [string]$freeze.policy_sha256
    market_policy_version = [string]$freeze.policy_version
    evidence_windows = $windows
    paper_gateway = "127.0.0.1:4002"
    paper_account_identity_gate = [string]$Readonly.paper_account_identity_gate
    broker_reconciliation_gate = [string]$Readonly.broker_reconciliation_gate
    paper_executor_armed = $false
    note = "All prerequisites are PASS. Paper execution remains intentionally unarmed until explicit experiment start."
}
Write-Utf8NoBom -Path $FinalReadyReport -Text ($final | ConvertTo-Json -Depth 8 -Compress)

Write-Host ""
Write-Host "AUDITOR GATE V2       = PASS" -ForegroundColor Green
Write-Host "MARKET DATA POLICY    = FROZEN" -ForegroundColor Green
Write-Host "MARKET DATA GATE      = PASS" -ForegroundColor Green
Write-Host "FINAL PREFLIGHT READY = TRUE" -ForegroundColor Green
Write-Host "PAPER EXECUTOR ARMED  = FALSE" -ForegroundColor Yellow
Write-Host ""
Write-Host "Final receipt: $FinalReadyReport"
