#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\AI_VAULT",
    [switch]$Scheduled
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskName = "CodexIBKRMarketDataGate"
$ReportRoot = Join-Path $RepoRoot "state\ibkr_paper_30d\reports"
$LedgerPath = Join-Path $ReportRoot "market_observations.jsonl"
$PolicyPath = Join-Path $ReportRoot "market_data_policy_v1.json"
$ValidationPath = Join-Path $ReportRoot "market_data_validation.json"
$StatePath = Join-Path $ReportRoot "market_gate_collection_state.json"

function Invoke-PythonJson {
    param([string[]]$Arguments)
    $Output = @(& python @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "PYTHON_COMMAND_FAILED:$($Arguments -join ' '):$($Output -join ' | ')"
    }
    $Candidates = @($Output | Where-Object { ([string]$_).TrimStart().StartsWith("{") })
    if ($Candidates.Count -eq 0) {
        throw "PYTHON_JSON_OUTPUT_MISSING:$($Output -join ' | ')"
    }
    return ([string]$Candidates[-1] | ConvertFrom-Json)
}

function Get-EasternNow {
    $Zone = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    return [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $Zone)
}

function Assert-RegularCollectionStart {
    $Now = Get-EasternNow
    if ($Now.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)) {
        throw "MARKET_DATA_COLLECTION_REQUIRES_WEEKDAY"
    }
    $Minutes = $Now.Hour * 60 + $Now.Minute
    if ($Minutes -lt (9 * 60 + 35) -or $Minutes -gt (14 * 60 + 45)) {
        throw "START_BETWEEN_09_35_AND_14_45_ET"
    }
}

function Initialize-CleanEvidence {
    if (Test-Path -LiteralPath $StatePath) { return }
    [void](New-Item -ItemType Directory -Path $ReportRoot -Force)
    $Existing = @(
        $LedgerPath,
        $PolicyPath,
        (Join-Path $ReportRoot "market_observation.json"),
        (Join-Path $ReportRoot "market_policy_freeze.json"),
        $ValidationPath
    ) | Where-Object { Test-Path -LiteralPath $_ }
    if ($Existing.Count -gt 0) {
        $Stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
        $Archive = Join-Path $ReportRoot ("archive\market-gate-" + $Stamp)
        [void](New-Item -ItemType Directory -Path $Archive -Force)
        foreach ($Path in $Existing) {
            Move-Item -LiteralPath $Path -Destination (Join-Path $Archive ([IO.Path]::GetFileName($Path))) -Force
        }
    }
    [ordered]@{
        schema = "MARKET_DATA_GATE_COLLECTION_STATE_V1"
        started_at_utc = [DateTime]::UtcNow.ToString("o").Replace("+00:00", "Z")
        protocol = "3x5min_windows_31min_start_separation"
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

function Wait-UntilUtc {
    param([DateTime]$Target)
    while ([DateTime]::UtcNow -lt $Target) {
        $Remaining = ($Target - [DateTime]::UtcNow).TotalSeconds
        $Slice = [Math]::Min([Math]::Max($Remaining, 1), 60)
        Start-Sleep -Seconds ([int][Math]::Ceiling($Slice))
    }
}

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "REPO_ROOT_NOT_FOUND:$RepoRoot"
}
Set-Location -LiteralPath $RepoRoot

if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port 4002 -InformationLevel Quiet)) {
    throw "IBKR_PAPER_GATEWAY_4002_NOT_LISTENING"
}

if (Test-Path -LiteralPath $ValidationPath) {
    try {
        $ExistingValidation = Get-Content -LiteralPath $ValidationPath -Raw | ConvertFrom-Json
        if ($ExistingValidation.market_data_gate -eq "PASS") {
            if ($Scheduled) {
                Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
            }
            Write-Output '{"status":"ALREADY_PASS","market_data_gate":"PASS"}'
            exit 0
        }
    }
    catch { }
}

Assert-RegularCollectionStart
Initialize-CleanEvidence

$ReadOnly = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.cli", "inspect-ibkr-readonly",
    "--host", "127.0.0.1", "--port", "4002"
)
if ($ReadOnly.status -ne "PASS") {
    throw "READONLY_IDENTITY_GATE_NOT_PASS:$($ReadOnly.reason_codes -join ',')"
}

$Starts = @()
for ($Index = 0; $Index -lt 3; $Index++) {
    if ($Index -gt 0) {
        $Target = $Starts[$Index - 1].AddMinutes(31)
        Wait-UntilUtc -Target $Target
    }
    $Starts += [DateTime]::UtcNow
    $Observation = Invoke-PythonJson -Arguments @(
        "-m", "ibkr_paper_30d.cli", "observe-market-data",
        "--host", "127.0.0.1", "--port", "4002",
        "--symbols", "SPY", "QQQ", "IEF",
        "--cadence-seconds", "5",
        "--window-seconds", "300"
    )
    if ($Observation.status -ne "PASS") {
        throw "MARKET_OBSERVATION_BLOCK:$($Observation.reason_codes -join ',')"
    }
}

$Freeze = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.cli", "freeze-market-policy",
    "--ledger", $LedgerPath,
    "--destination", $PolicyPath
)
if ($Freeze.status -notin @("PASS", "ALREADY_FROZEN")) {
    throw "MARKET_POLICY_FREEZE_BLOCK:$($Freeze.reason_codes -join ',')"
}

$Validation = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.cli", "validate-real-market-data",
    "--host", "127.0.0.1", "--port", "4002",
    "--policy", $PolicyPath
)
if ($Validation.market_data_gate -ne "PASS") {
    throw "MARKET_DATA_GATE_BLOCK:$($Validation.reason_codes -join ',')"
}

$Ready = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.prerequisite_tools", "readiness",
    "--report-root", $ReportRoot
)

if ($Scheduled) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
}

[ordered]@{
    status = "PASS"
    market_data_gate = $Validation.market_data_gate
    policy = $PolicyPath
    readiness = $Ready
    trading_armed = $false
} | ConvertTo-Json -Depth 8
