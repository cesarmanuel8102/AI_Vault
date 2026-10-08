#Requires -Version 5.1
# Regression harness for RUN_IBKR_MARKET_DATA_GATE.ps1 evidence functions.
# Extracts the requested function via the PowerShell AST (the script's main
# body is NEVER executed) and runs it under StrictMode Latest against a
# caller-provided temporary report root.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ScriptPath,
    [Parameter(Mandatory = $true)][string]$ReportRoot,
    [Parameter(Mandatory = $true)][ValidateSet("Initialize-CleanEvidence", "Archive-CollectionEvidence", "Invoke-PythonJson", "Resolve-MarketGateMode")][string]$Function,
    [Parameter(Mandatory = $true)][ValidateSet("0", "1", "many", "friday-pass")][string]$ExistingCount,
    [Parameter()][ValidateSet("zero", "one", "many")][string]$PythonJsonMode = "one",
    [Parameter()][ValidateSet("scheduled", "scheduled-force", "inspect", "none", "both")][string]$GateMode = "scheduled"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Emit {
    param([hashtable]$Payload, [int]$Code)
    $Json = ConvertTo-Json -InputObject $Payload -Depth 8 -Compress
    [Console]::Out.WriteLine($Json)
    exit $Code
}

$Tokens = $null
$ParseErrors = $null
$Ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$Tokens, [ref]$ParseErrors)
if ($null -ne $ParseErrors -and @($ParseErrors).Count -gt 0) {
    Emit -Payload @{ status = "PARSE_ERROR"; messages = @($ParseErrors | ForEach-Object { $_.Message }) } -Code 4
}
$Definition = $null
foreach ($Node in $Ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    if ($Node.Name -eq $Function) {
        $Definition = $Node.Extent.Text
        break
    }
}
if ($null -eq $Definition) {
    Emit -Payload @{ status = "FUNCTION_NOT_FOUND"; function = $Function } -Code 4
}
Invoke-Expression -Command $Definition

# Script-scope variables mirroring RUN_IBKR_MARKET_DATA_GATE.ps1 lines 13-17.
$ReportRoot = [IO.Path]::GetFullPath($ReportRoot).TrimEnd('\')
$LedgerPath = Join-Path $ReportRoot "market_observations.jsonl"
$PolicyPath = Join-Path $ReportRoot "market_data_policy_v1.json"
$ValidationPath = Join-Path $ReportRoot "market_data_validation.json"
$StatePath = Join-Path $ReportRoot "market_gate_collection_state.json"
$ObservationReportPath = Join-Path $ReportRoot "market_observation.json"
$FreezeReportPath = Join-Path $ReportRoot "market_policy_freeze.json"

[void](New-Item -ItemType Directory -Path $ReportRoot -Force)

switch ($ExistingCount) {
    "1" {
        Set-Content -LiteralPath $LedgerPath -Value "{}" -Encoding UTF8
    }
    "many" {
        if ($Function -eq "Archive-CollectionEvidence") {
            foreach ($Path in @($LedgerPath, $ValidationPath, $StatePath)) {
                Set-Content -LiteralPath $Path -Value "{}" -Encoding UTF8
            }
        }
        else {
            foreach ($Path in @($LedgerPath, $PolicyPath, $ObservationReportPath, $FreezeReportPath, $ValidationPath)) {
                Set-Content -LiteralPath $Path -Value "{}" -Encoding UTF8
            }
        }
    }
    "friday-pass" {
        [ordered]@{
            market_data_gate = "PASS"
            validated_at_utc = "2026-09-25T19:00:00Z"
        } | ConvertTo-Json -Compress | Set-Content -LiteralPath $ValidationPath -Encoding UTF8
    }
    "0" { }
}

function Emit-FileOperationResult {
    $ArchiveRoot = Join-Path $ReportRoot "archive"
    $ArchiveDirNames = @()
    if (Test-Path -LiteralPath $ArchiveRoot) {
        $ArchiveDirNames = @(Get-ChildItem -LiteralPath $ArchiveRoot -Directory | ForEach-Object { $_.Name })
    }
    $ArchivedFiles = 0
    foreach ($DirName in $ArchiveDirNames) {
        $ArchivedFiles += @(Get-ChildItem -LiteralPath (Join-Path $ArchiveRoot $DirName) -File -ErrorAction SilentlyContinue).Count
    }
    $AllEvidencePaths = @($LedgerPath, $PolicyPath, $ObservationReportPath, $FreezeReportPath, $ValidationPath, $StatePath)
    $Remaining = @($AllEvidencePaths | Where-Object { Test-Path -LiteralPath $_ })
    Emit -Payload @{
        status          = "OK"
        function        = $Function
        state_created   = (Test-Path -LiteralPath $StatePath)
        archive_dirs    = $ArchiveDirNames
        archived_files  = $ArchivedFiles
        remaining       = $Remaining
    } -Code 0
}

try {
    if ($Function -eq "Initialize-CleanEvidence") {
        Initialize-CleanEvidence
        Emit-FileOperationResult
    }
    elseif ($Function -eq "Archive-CollectionEvidence") {
        Archive-CollectionEvidence -Reason "regression-test"
        Emit-FileOperationResult
    }
    elseif ($Function -eq "Resolve-MarketGateMode") {
        $Scheduled = $GateMode -in @("scheduled", "scheduled-force", "both")
        $InspectStatus = $GateMode -in @("inspect", "both")
        $ForceFresh = $GateMode -eq "scheduled-force"
        $Mode = Resolve-MarketGateMode -IsScheduled $Scheduled -IsInspectStatus $InspectStatus -IsForceFresh $ForceFresh
        $Existing = Get-Content -LiteralPath $ValidationPath -Raw | ConvertFrom-Json
        Emit -Payload @{
            status                            = "OK"
            function                          = $Function
            mode                              = $Mode
            existing_market_data_gate         = $Existing.market_data_gate
            existing_validated_at_utc         = $Existing.validated_at_utc
            existing_pass_reusable_for_launch = ($Mode -eq "REUSE_EXISTING")
        } -Code 0
    }
    else {
        $PythonExe = "powershell.exe"
        $PayloadOnePath = Join-Path $ReportRoot ("harness-one-" + [guid]::NewGuid().ToString("N") + ".json")
        $PayloadTwoPath = Join-Path $ReportRoot ("harness-two-" + [guid]::NewGuid().ToString("N") + ".json")
        Set-Content -LiteralPath $PayloadOnePath -Value '{"a":1}' -Encoding UTF8
        Set-Content -LiteralPath $PayloadTwoPath -Value '{"a":2}' -Encoding UTF8
        switch ($PythonJsonMode) {
            "zero" { $PyArgs = @("-NoProfile", "-Command", "Write-Output plain") }
            "one" { $PyArgs = @("-NoProfile", "-Command", "Get-Content -LiteralPath '$PayloadOnePath'") }
            "many" { $PyArgs = @("-NoProfile", "-Command", "Get-Content -LiteralPath '$PayloadOnePath'; Get-Content -LiteralPath '$PayloadTwoPath'") }
        }
        $Parsed = Invoke-PythonJson -Arguments $PyArgs
        Emit -Payload @{ status = "OK"; function = $Function; parsed = $Parsed } -Code 0
    }
}
catch {
    Emit -Payload @{
        status                  = "ERROR"
        function                = $Function
        error_type              = $_.Exception.GetType().FullName
        fully_qualified_error_id = $_.FullyQualifiedErrorId
        exception_message_head  = ($_.Exception.Message -split "`n")[0]
        position                = $(if ($null -ne $_.InvocationInfo) { $_.InvocationInfo.PositionMessage } else { "" })
        script_stack_trace      = $(if ($null -ne $_.ScriptStackTrace) { $_.ScriptStackTrace } else { "" })
    } -Code 5
}
