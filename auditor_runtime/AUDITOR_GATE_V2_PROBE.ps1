#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BundlePath,
    [Parameter(Mandatory = $true)][string]$PaperIdentityReceiptPath,
    [Parameter(Mandatory = $true)][string]$TargetManifestPath,
    [Parameter(Mandatory = $true)][string]$DeploymentManifestPath,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedDeploymentManifestSha256,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedPaperAccountHash,
    [Parameter(Mandatory = $true)][string]$ExpectedSid,
    [Parameter(Mandatory = $true)][string]$ReportDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RuntimeRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSCommandPath)).TrimEnd('\')
$RuntimeManifestPath = Join-Path $RuntimeRoot "AUDITOR_RUNTIME_MANIFEST_V2.json"
$DenialProbePath = Join-Path $RuntimeRoot "AUDITOR_DENIAL_PROBE_V1.ps1"
$FunctionalAuditorPath = Join-Path $RuntimeRoot "CODEX_DECISION_AUDITOR_V1.ps1"
$ExpectedRuntimeNames = @(
    "AUDITOR_DENIAL_PROBE_V1.ps1",
    "AUDITOR_GATE_V2_PROBE.ps1",
    "AUDITOR_RUNTIME_MANIFEST_V2.json",
    "CODEX_DECISION_AUDITOR_V1.ps1"
)
$ExpectedTargets = @(
    "SECRETS_READ", "IBKR_SECRET_READ", "SMTP_SECRET_READ",
    "EXECUTION_LOCK_ACCESS", "LIVE_DATABASE_MUTATION",
    "BROKER_WRITE_PATH_ACCESS", "TRADER_CONTEXT_ACCESS",
    "AUDIT_INPUT_MUTATION", "IMMUTABLE_EXPORT_READ", "AUDITOR_REPORT_WRITE"
)

function Get-Sha256Hex {
    param([string]$LiteralPath)
    if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
        return (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $Algorithm = [Security.Cryptography.SHA256]::Create()
    $Stream = [IO.File]::OpenRead($LiteralPath)
    try { return ([BitConverter]::ToString($Algorithm.ComputeHash($Stream))).Replace("-", "").ToLowerInvariant() }
    finally { $Stream.Dispose(); $Algorithm.Dispose() }
}

function Get-TextSha256 {
    param([string]$Text)
    $Algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $Bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return ([BitConverter]::ToString($Algorithm.ComputeHash($Bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally { $Algorithm.Dispose() }
}

function Read-StrictJson {
    param([string]$LiteralPath)
    $Text = [IO.File]::ReadAllText($LiteralPath)
    $Seen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($Match in [regex]::Matches($Text, '"(?<key>(?:\\.|[^"\\])*)"\s*:')) {
        if (-not $Seen.Add($Match.Groups['key'].Value)) { throw "DUPLICATE_JSON_KEY" }
    }
    return ($Text | ConvertFrom-Json)
}

function Read-ResultLine {
    param([object[]]$Lines)
    $Matches = @($Lines | Where-Object { [string]$_ -like "RESULT_JSON=*" })
    if ($Matches.Count -ne 1) { throw "CHILD_RESULT_INVALID" }
    return ([string]$Matches[0]).Substring(12) | ConvertFrom-Json
}

function Assert-ExactSet {
    param([string[]]$Expected, [string[]]$Actual, [string]$Reason)
    $Left = @($Expected | Sort-Object)
    $Right = @($Actual | Sort-Object)
    if ($Left.Count -ne $Right.Count -or ($Left -join '|') -cne ($Right -join '|')) { throw $Reason }
}

$Started = [DateTime]::UtcNow
$RunId = [Guid]::NewGuid().ToString('N')
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
$Elevated = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($Identity.User.Value -ne $ExpectedSid -or $Elevated) { throw "AUDITOR_IDENTITY_INVALID" }

$ActualNames = @(Get-ChildItem -LiteralPath $RuntimeRoot -File | ForEach-Object { $_.Name })
Assert-ExactSet -Expected $ExpectedRuntimeNames -Actual $ActualNames -Reason "RUNTIME_FILESET_MISMATCH"
if ((Get-Sha256Hex -LiteralPath $DeploymentManifestPath) -ne $ExpectedDeploymentManifestSha256) {
    throw "DEPLOYMENT_MANIFEST_HASH_MISMATCH"
}
$RuntimeManifest = Read-StrictJson -LiteralPath $RuntimeManifestPath
$DeploymentManifest = Read-StrictJson -LiteralPath $DeploymentManifestPath
if ($RuntimeManifest.schema -ne "AUDITOR_RUNTIME_MANIFEST_V2" -or $DeploymentManifest.schema -ne "AUDITOR_RUNTIME_DEPLOYMENT_MANIFEST_V2") {
    throw "RUNTIME_MANIFEST_INVALID"
}
foreach ($Property in $DeploymentManifest.files.PSObject.Properties) {
    $Target = Join-Path $RuntimeRoot $Property.Name
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf) -or (Get-Sha256Hex $Target) -ne [string]$Property.Value) {
        throw "RUNTIME_HASH_MISMATCH"
    }
}

$DenialLines = & powershell.exe -NoProfile -File $DenialProbePath `
    -TargetManifestPath $TargetManifestPath -ReportDirectory $ReportDirectory `
    -RuntimeManifestPath $RuntimeManifestPath -ExpectedSid $ExpectedSid
if ($LASTEXITCODE -ne 0) { throw "DENIAL_PROBE_FAILED" }
$Denial = Read-ResultLine -Lines $DenialLines
if ($Denial.status -ne "COMPLETE") { throw "DENIAL_PROBE_INCOMPLETE" }

$FunctionalName = "functional-$RunId.json"
$FunctionalLines = & powershell.exe -NoProfile -File $FunctionalAuditorPath `
    -BundlePath $BundlePath -ReportDirectory $ReportDirectory `
    -RuntimeManifestPath $RuntimeManifestPath -ReportFileName $FunctionalName
if ($LASTEXITCODE -ne 0) { throw "FUNCTIONAL_AUDITOR_FAILED" }
$Functional = Read-ResultLine -Lines $FunctionalLines
if ($Functional.status -ne "PASS") { throw "FUNCTIONAL_AUDITOR_BLOCK" }

$PaperReceipt = Read-StrictJson -LiteralPath $PaperIdentityReceiptPath
if (
    $PaperReceipt.schema -ne "REAL_IBKR_READ_ONLY_RECONCILIATION_V1" -or
    $PaperReceipt.paper_account_identity_gate -ne "PASS" -or
    $PaperReceipt.real_ibkr_read_only_identity_gate -ne "PASS" -or
    $PaperReceipt.broker_reconciliation_gate -ne "PASS" -or
    $PaperReceipt.gateway_mode -ne "PAPER" -or
    [int]$PaperReceipt.port -ne 4002
) { throw "PAPER_IDENTITY_BLOCK" }
$PaperReceiptHash = Get-Sha256Hex -LiteralPath $PaperIdentityReceiptPath
$PaperEnvironment = "PAPER:" + (Get-TextSha256 "$($PaperReceipt.host)|$($PaperReceipt.port)|$($PaperReceipt.gateway_mode)|$ExpectedPaperAccountHash")
$SessionEnvironment = "PAPER-SESSION:" + (Get-TextSha256 "$($PaperReceipt.server_version)|$($PaperReceipt.connection_time)|$($PaperReceipt.server_timestamp_utc)")

$TargetRows = @($Denial.target_validation_matrix | ForEach-Object {
    [ordered]@{ run_id = $RunId; probe = $_.probe; valid = [bool]$_.valid }
})
Assert-ExactSet -Expected $ExpectedTargets -Actual @($TargetRows | ForEach-Object { $_.probe }) -Reason "TARGET_SET_MISMATCH"
$OutcomeNames = @($Denial.results.PSObject.Properties | ForEach-Object { $_.Name })
Assert-ExactSet -Expected $ExpectedTargets -Actual $OutcomeNames -Reason "CAPABILITY_SET_MISMATCH"
$EndpointValues = @($Denial.network_endpoints.PSObject.Properties | ForEach-Object { [string]$_.Value })
if ($EndpointValues -notcontains "CONNECTED") { throw "TECHNICAL_SOCKET_REACHABILITY_NOT_OBSERVED" }

$FunctionalPath = [string]$Functional.report_path
$Receipt = [ordered]@{
    schema = "AUDITOR_GATE_V2_RECEIPT_V1"; gate_version = "V2"; run_id = $RunId
    started_at_utc = $Started.ToString("o").Replace("+00:00", "Z")
    completed_at_utc = [DateTime]::UtcNow.ToString("o").Replace("+00:00", "Z")
    effective_sid = $Identity.User.Value; token_elevated = $Elevated; separate_process = $true
    runtime_integrity = [ordered]@{
        status = "PASS"; runtime_manifest_sha256 = Get-Sha256Hex $RuntimeManifestPath
        deployment_manifest_sha256 = Get-Sha256Hex $DeploymentManifestPath
        probe_sha256 = Get-Sha256Hex $PSCommandPath
        probe_manifest_sha256 = Get-Sha256Hex $TargetManifestPath
        exact_fileset = $true; verified_at_utc = $Started.ToString("o").Replace("+00:00", "Z")
        predicates = [ordered]@{
            BROKER_MODULE_AVAILABLE = $false; ORDER_WRITE_SYMBOL_AVAILABLE = $false
            EXECUTION_ADAPTER_AVAILABLE = $false; EXECUTION_LOCK_CLIENT_AVAILABLE = $false
            TRADER_IPC_CLIENT_AVAILABLE = $false; BROKER_CREDENTIAL_SOURCE_AVAILABLE = $false
            ORDER_WRITE_MODULE_AVAILABLE = $false
        }
    }
    target_validation_matrix = $TargetRows
    capability_outcomes = $Denial.results
    functional_auditor = [ordered]@{ run_id = $RunId; status = "PASS"; bundle_id = $Functional.bundle_id; manifest_sha256 = $Functional.manifest_sha256 }
    paper_identity = [ordered]@{
        run_id = $RunId; expected_account_identity_hash = $ExpectedPaperAccountHash
        identity_receipt_sha256 = $PaperReceiptHash; environment_reference = $PaperEnvironment
        broker_session_environment_reference = $SessionEnvironment; verified_at_utc = $PaperReceipt.server_timestamp_utc
        paper_identity_gate = "PASS"; readonly_identity_gate = "PASS"; broker_reconciliation_gate = "PASS"
        paper_only = $true; live_allowed = $false; real_money_allowed = $false
    }
    network_facts = [ordered]@{
        AUDITOR_TECHNICAL_SOCKET_REACHABILITY = $true; AUDITOR_NETWORK_ISOLATION_REQUIRED = $false
        AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE = $true; AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED = $true
        endpoints = $Denial.network_endpoints
    }
    output = [ordered]@{
        run_id = $RunId; report_path = $FunctionalPath; created = $true
        report_sha256 = Get-Sha256Hex $FunctionalPath; evidence_origin = "REAL_RESTRICTED_TOKEN"
    }
}

[void][IO.Directory]::CreateDirectory([IO.Path]::GetFullPath($ReportDirectory))
$ReceiptPath = Join-Path ([IO.Path]::GetFullPath($ReportDirectory)) "auditor-gate-v2-$RunId.json"
$Utf8 = New-Object Text.UTF8Encoding($false)
$Stream = New-Object IO.FileStream($ReceiptPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    $Writer = New-Object IO.StreamWriter($Stream, $Utf8)
    try { $Writer.Write(($Receipt | ConvertTo-Json -Depth 10 -Compress)); $Writer.Flush(); $Stream.Flush($true) }
    finally { $Writer.Dispose() }
}
finally { $Stream.Dispose() }
Write-Output ("RESULT_JSON=" + ($Receipt | ConvertTo-Json -Depth 10 -Compress))
