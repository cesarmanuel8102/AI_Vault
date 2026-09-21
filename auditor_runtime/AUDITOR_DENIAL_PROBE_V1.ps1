#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$ReportDirectory,
    [Parameter(Mandatory = $true)]
    [string]$RuntimeManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedSid,
    [switch]$ValidateTargetsOnly,
    [switch]$ClassifyEndpointsOnly,
    [ValidateRange(1, 65535)]
    [int[]]$BrokerPorts = @(4001, 4002)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RequiredTargets = @(
    "SECRETS_READ",
    "IBKR_SECRET_READ",
    "SMTP_SECRET_READ",
    "EXECUTION_LOCK_ACCESS",
    "LIVE_DATABASE_MUTATION",
    "BROKER_WRITE_PATH_ACCESS",
    "TRADER_CONTEXT_ACCESS",
    "AUDIT_INPUT_MUTATION",
    "IMMUTABLE_EXPORT_READ",
    "AUDITOR_REPORT_WRITE"
)

function Get-Sha256Hex {
    param([string]$LiteralPath)
    if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
        return (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $Algorithm = [Security.Cryptography.SHA256]::Create()
    $Stream = [IO.File]::OpenRead($LiteralPath)
    try {
        return ([BitConverter]::ToString($Algorithm.ComputeHash($Stream))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $Stream.Dispose()
        $Algorithm.Dispose()
    }
}

function Read-StrictJson {
    param([string]$LiteralPath)
    try { $Text = [IO.File]::ReadAllText($LiteralPath) }
    catch { return [ordered]@{ status = "MANIFEST_INVALID"; value = $null } }
    $Keys = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($Match in [regex]::Matches($Text, '"(?<key>(?:\\.|[^"\\])*)"\s*:')) {
        if (-not $Keys.Add($Match.Groups['key'].Value)) {
            return [ordered]@{ status = "MANIFEST_INVALID"; value = $null }
        }
    }
    try { $Value = $Text | ConvertFrom-Json }
    catch { return [ordered]@{ status = "MANIFEST_INVALID"; value = $null } }
    return [ordered]@{ status = "PASS"; value = $Value }
}

function Write-ResultLine {
    param([object]$Value)
    Write-Output ("RESULT_JSON=" + ($Value | ConvertTo-Json -Depth 8 -Compress))
}

function Test-ReparsePoint {
    param([string]$LiteralPath)
    $Item = Get-Item -LiteralPath $LiteralPath -Force
    return [bool]($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Test-PathChainReparse {
    param([string]$LiteralPath)
    $Cursor = [IO.Path]::GetFullPath($LiteralPath).TrimEnd('\')
    while (-not (Test-Path -LiteralPath $Cursor)) {
        $Parent = Split-Path -Parent $Cursor
        if ([string]::IsNullOrWhiteSpace($Parent) -or $Parent -eq $Cursor) { return $false }
        $Cursor = $Parent
    }
    while (-not [string]::IsNullOrWhiteSpace($Cursor)) {
        if (Test-ReparsePoint -LiteralPath $Cursor) { return $true }
        $Parent = Split-Path -Parent $Cursor
        if ([string]::IsNullOrWhiteSpace($Parent) -or $Parent -eq $Cursor) { break }
        $Cursor = $Parent
    }
    return $false
}

function Test-RuntimeManifest {
    $Read = Read-StrictJson -LiteralPath $RuntimeManifestPath
    if ($Read.status -ne "PASS") { return [ordered]@{ status = "RUNTIME_MANIFEST_INVALID" } }
    $Manifest = $Read.value
    if (
        $Manifest.schema -notin @("AUDITOR_RUNTIME_MANIFEST_V1", "AUDITOR_RUNTIME_MANIFEST_V2") -or
        $null -eq $Manifest.files
    ) {
        return [ordered]@{ status = "RUNTIME_MANIFEST_INVALID" }
    }
    $ActualRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSCommandPath)).TrimEnd('\')
    $ManifestRoot = [IO.Path]::GetFullPath((Split-Path -Parent $RuntimeManifestPath)).TrimEnd('\')
    if ($ManifestRoot -ine $ActualRoot) {
        return [ordered]@{ status = "RUNTIME_ROOT_MISMATCH" }
    }
    if ($Manifest.schema -eq "AUDITOR_RUNTIME_MANIFEST_V1") {
        $RuntimeRoot = [IO.Path]::GetFullPath([string]$Manifest.runtime_root).TrimEnd('\')
        if ($RuntimeRoot -ine $ActualRoot) { return [ordered]@{ status = "RUNTIME_ROOT_MISMATCH" } }
    }
    if (Test-PathChainReparse -LiteralPath $ActualRoot) {
        return [ordered]@{ status = "RUNTIME_PATH_REDIRECTED" }
    }
    $Properties = @($Manifest.files.PSObject.Properties)
    $Names = @($Properties | ForEach-Object { $_.Name })
    $Seen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    if ($Manifest.schema -eq "AUDITOR_RUNTIME_MANIFEST_V2") {
        $RequiredV2 = @(
            "AUDITOR_DENIAL_PROBE_V1.ps1",
            "AUDITOR_GATE_V2_PROBE.ps1",
            "CODEX_DECISION_AUDITOR_V1.ps1"
        ) | Sort-Object
        if (($RequiredV2 -join '|') -cne (@($Names | Sort-Object) -join '|')) {
            return [ordered]@{ status = "RUNTIME_FILE_SET_MISMATCH" }
        }
    }
    foreach ($Name in $Names) {
        if (
            -not $Seen.Add($Name) -or
            [IO.Path]::GetFileName($Name) -cne $Name -or
            $Name -in @("AUDITOR_RUNTIME_MANIFEST_V1.json", "AUDITOR_RUNTIME_MANIFEST_V2.json")
        ) {
            return [ordered]@{ status = "RUNTIME_UNSAFE_PATH" }
        }
    }
    $Expected = @($Names + [IO.Path]::GetFileName($RuntimeManifestPath)) | Sort-Object { $_.ToLowerInvariant() }
    $Actual = @(Get-ChildItem -LiteralPath $ActualRoot -File | ForEach-Object { $_.Name }) | Sort-Object { $_.ToLowerInvariant() }
    if (($Expected -join '|') -cne ($Actual -join '|')) {
        return [ordered]@{ status = "RUNTIME_FILE_SET_MISMATCH" }
    }
    foreach ($Property in $Properties) {
        $Target = Join-Path $ActualRoot $Property.Name
        if (
            (Test-ReparsePoint -LiteralPath $Target) -or
            (Get-Sha256Hex -LiteralPath $Target) -ne [string]$Property.Value
        ) {
            return [ordered]@{ status = "RUNTIME_HASH_MISMATCH" }
        }
    }
    return [ordered]@{
        status = "PASS"
        manifest_sha256 = Get-Sha256Hex -LiteralPath $RuntimeManifestPath
    }
}

function Get-PathValidation {
    param([string]$Target, [string[]]$ApprovedRoots)
    try { $Full = [IO.Path]::GetFullPath($Target).TrimEnd('\') }
    catch {
        return [ordered]@{
            normalized_path = $null
            approved_root = $null
            reparse_state = "NOT_EVALUATED"
            path_chain = @()
            valid = $false
            reason = "TARGET_PATH_INVALID"
        }
    }
    $MatchedRoot = $null
    foreach ($RootValue in $ApprovedRoots) {
        try { $Root = [IO.Path]::GetFullPath($RootValue).TrimEnd('\') }
        catch { continue }
        if ($Full -ieq $Root -or $Full.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) {
            $MatchedRoot = $Root
            break
        }
    }
    if ($null -eq $MatchedRoot) {
        return [ordered]@{
            normalized_path = $Full
            approved_root = $null
            reparse_state = "NOT_EVALUATED"
            path_chain = @()
            valid = $false
            reason = "TARGET_OUTSIDE_APPROVED_ROOT"
        }
    }

    $RootPath = [IO.Path]::GetPathRoot($Full).TrimEnd('\') + '\'
    $Relative = $Full.Substring($RootPath.Length)
    $Cursor = $RootPath
    $PathChain = @()
    foreach ($Part in @($Relative.Split('\') | Where-Object { $_ -ne '' })) {
        $Cursor = Join-Path $Cursor $Part
        try {
            $Item = Get-Item -LiteralPath $Cursor -Force -ErrorAction Stop
            $IsReparse = [bool]($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)
            $PathChain += [ordered]@{ path = $Cursor; state = $(if ($IsReparse) { "REPARSE" } else { "DIRECT" }) }
            if ($IsReparse) {
                return [ordered]@{
                    normalized_path = $Full
                    approved_root = $MatchedRoot
                    reparse_state = "REPARSE_DETECTED"
                    path_chain = $PathChain
                    valid = $false
                    reason = "TARGET_REPARSE_POINT"
                }
            }
        }
        catch [UnauthorizedAccessException] {
            $PathChain += [ordered]@{ path = $Cursor; state = "ACCESS_DENIED" }
            return [ordered]@{
                normalized_path = $Full
                approved_root = $MatchedRoot
                reparse_state = "OPAQUE_AFTER_OS_DENIAL"
                path_chain = $PathChain
                valid = $true
                reason = $(if ($Cursor -ieq $Full) { "ACCESS_DENIED_AT_TARGET" } else { "ACCESS_DENIED_AT_ANCESTOR" })
            }
        }
        catch [System.Management.Automation.ItemNotFoundException] {
            $PathChain += [ordered]@{ path = $Cursor; state = "NOT_FOUND" }
            break
        }
        catch {
            $PathChain += [ordered]@{ path = $Cursor; state = "UNINSPECTABLE" }
            return [ordered]@{
                normalized_path = $Full
                approved_root = $MatchedRoot
                reparse_state = "NOT_PROVEN"
                path_chain = $PathChain
                valid = $false
                reason = "TARGET_INSPECTION_FAILED"
            }
        }
    }
    return [ordered]@{
        normalized_path = $Full
        approved_root = $MatchedRoot
        reparse_state = "NO_REPARSE_DETECTED"
        path_chain = $PathChain
        valid = $true
        reason = "ACCEPTED"
    }
}

function Resolve-ApprovedTarget {
    param([string]$Target, [string[]]$ApprovedRoots)
    $Validation = Get-PathValidation -Target $Target -ApprovedRoots $ApprovedRoots
    if (-not $Validation.valid) { throw $Validation.reason }
    return $Validation.normalized_path
}

function Test-ReadCapability {
    param([string]$Target)
    try {
        $Exists = Test-Path -LiteralPath $Target -ErrorAction Stop
    }
    catch [UnauthorizedAccessException] { return "DENIED" }
    catch [Security.SecurityException] { return "DENIED" }
    catch { return "NOT_PROVEN" }
    if (-not $Exists) { return "NOT_PROVEN" }
    try {
        $Item = Get-Item -LiteralPath $Target -Force
        if ($Item.PSIsContainer) {
            [void](Get-ChildItem -LiteralPath $Target -Force -ErrorAction Stop | Select-Object -First 1)
        }
        else {
            $Stream = [IO.File]::Open($Target, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
            $Stream.Dispose()
        }
        return "ALLOWED"
    }
    catch [UnauthorizedAccessException] { return "DENIED" }
    catch [Security.SecurityException] { return "DENIED" }
    catch { return "NOT_PROVEN" }
}

function Test-MutationCapability {
    param([string]$Target)
    try {
        $Exists = Test-Path -LiteralPath $Target -ErrorAction Stop
    }
    catch [UnauthorizedAccessException] { return "DENIED" }
    catch [Security.SecurityException] { return "DENIED" }
    catch { return "NOT_PROVEN" }
    if (-not $Exists) { return "NOT_PROVEN" }
    try {
        $Item = Get-Item -LiteralPath $Target -Force
        if ($Item.PSIsContainer) {
            $Candidate = Join-Path $Target ("auditor-probe-" + [Guid]::NewGuid().ToString('N') + ".tmp")
            $Stream = New-Object IO.FileStream($Candidate, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            $Stream.Dispose()
            try { [IO.File]::Delete($Candidate) } catch { }
        }
        else {
            $Stream = [IO.File]::Open($Target, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::Read)
            $Stream.Dispose()
        }
        return "ALLOWED"
    }
    catch [UnauthorizedAccessException] { return "DENIED" }
    catch [Security.SecurityException] { return "DENIED" }
    catch { return "NOT_PROVEN" }
}

function Test-TcpEndpoint {
    param([string]$Address, [int]$Port)
    $IpAddress = [Net.IPAddress]::Parse($Address)
    $Client = New-Object Net.Sockets.TcpClient($IpAddress.AddressFamily)
    try {
        $Pending = $Client.BeginConnect($IpAddress, $Port, $null, $null)
        if (-not $Pending.AsyncWaitHandle.WaitOne(5000)) { return "OTHER" }
        $Client.EndConnect($Pending)
        return "CONNECTED"
    }
    catch [Net.Sockets.SocketException] {
        if ($_.Exception.SocketErrorCode -eq [Net.Sockets.SocketError]::AccessDenied) { return "DENIED" }
        if ($_.Exception.SocketErrorCode -eq [Net.Sockets.SocketError]::ConnectionRefused) { return "NO_LISTENER" }
        return "OTHER"
    }
    catch { return "OTHER" }
    finally { $Client.Dispose() }
}

function Test-BrokerNetworkCapability {
    $Outcomes = [ordered]@{}
    foreach ($Address in @("127.0.0.1", "::1")) {
        foreach ($Port in $BrokerPorts) {
            $Endpoint = $(if ($Address -eq "::1") { "[$Address]:$Port" } else { "$Address`:$Port" })
            $Outcomes[$Endpoint] = Test-TcpEndpoint -Address $Address -Port $Port
        }
    }
    $Values = @($Outcomes.Values)
    $Status = $(if ($Values -contains "CONNECTED") { "ALLOWED" } elseif (($Values | Where-Object { $_ -ne "DENIED" }).Count -eq 0) { "DENIED" } else { "NOT_PROVEN" })
    return [ordered]@{ status = $Status; network_endpoints = $Outcomes }
}

$Runtime = Test-RuntimeManifest
if ($Runtime.status -ne "PASS") {
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"; status = $Runtime.status })
    exit 20
}
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
$Elevated = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($Identity.User.Value -ne $ExpectedSid -or $Elevated) {
    Write-ResultLine -Value ([ordered]@{
        schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"
        status = $(if ($Elevated) { "TOKEN_ELEVATED" } else { "IDENTITY_INVALID" })
        effective_sid = $Identity.User.Value
        token_elevated = $Elevated
        results = [ordered]@{}
    })
    exit 21
}

if ($ClassifyEndpointsOnly) {
    $NetworkOnly = Test-BrokerNetworkCapability
    Write-ResultLine -Value ([ordered]@{
        schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"
        status = "ENDPOINT_CLASSIFICATION_COMPLETE"
        effective_sid = $Identity.User.Value
        token_elevated = $Elevated
        network_endpoints = $NetworkOnly.network_endpoints
    })
    exit 0
}

$Read = Read-StrictJson -LiteralPath $TargetManifestPath
if ($Read.status -ne "PASS") {
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"; status = "MANIFEST_INVALID" })
    exit 22
}
$Manifest = $Read.value
if (
    $Manifest.schema -ne "AUDITOR_PROBE_TARGET_MANIFEST_V1" -or
    $Manifest.expected_sid -ne $ExpectedSid -or
    $null -eq $Manifest.targets -or
    $null -eq $Manifest.approved_roots
) {
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"; status = "MANIFEST_INVALID" })
    exit 22
}
$TargetNames = @($Manifest.targets.PSObject.Properties | ForEach-Object { $_.Name })
$ActualTargetSet = (($TargetNames | Sort-Object) -join '|')
$RequiredTargetSet = (($RequiredTargets | Sort-Object) -join '|')
if ($ActualTargetSet -cne $RequiredTargetSet) {
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"; status = "TARGET_SET_MISMATCH" })
    exit 22
}

$Resolved = @{}
$TargetValidationMatrix = @()
foreach ($Property in $Manifest.targets.PSObject.Properties) {
    $Validation = Get-PathValidation -Target ([string]$Property.Value) -ApprovedRoots @($Manifest.approved_roots)
    $TargetValidationMatrix += [ordered]@{
        probe = $Property.Name
        path = [string]$Property.Value
        expected_root = $Validation.approved_root
        normalized_path = $Validation.normalized_path
        reparse_state = $Validation.reparse_state
        path_chain = $Validation.path_chain
        valid = $Validation.valid
        reason = $Validation.reason
    }
    if ($Validation.valid) { $Resolved[$Property.Name] = $Validation.normalized_path }
}
$InvalidTargets = @($TargetValidationMatrix | Where-Object { -not $_.valid })
if ($InvalidTargets.Count -ne 0) {
    Write-ResultLine -Value ([ordered]@{
        schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"
        status = "UNSAFE_TARGET_PATH"
        target_validation_matrix = $TargetValidationMatrix
    })
    exit 23
}
if ($ValidateTargetsOnly) {
    Write-ResultLine -Value ([ordered]@{
        schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"
        status = "TARGET_VALIDATION_COMPLETE"
        effective_sid = $Identity.User.Value
        token_elevated = $Elevated
        target_validation_matrix = $TargetValidationMatrix
    })
    exit 0
}

$Results = [ordered]@{}
$NetworkEndpoints = [ordered]@{}
foreach ($Name in $RequiredTargets) {
    if ($Name -in @("SECRETS_READ", "IBKR_SECRET_READ", "SMTP_SECRET_READ", "IMMUTABLE_EXPORT_READ")) {
        $Results[$Name] = Test-ReadCapability -Target $Resolved[$Name]
    }
    elseif ($Name -eq "BROKER_WRITE_PATH_ACCESS") {
        $FileResult = Test-MutationCapability -Target $Resolved[$Name]
        $NetworkResult = Test-BrokerNetworkCapability
        $NetworkEndpoints = $NetworkResult.network_endpoints
        if ($FileResult -eq "ALLOWED" -or $NetworkResult.status -eq "ALLOWED") { $Results[$Name] = "ALLOWED" }
        elseif ($FileResult -eq "DENIED" -and $NetworkResult.status -eq "DENIED") { $Results[$Name] = "DENIED" }
        else { $Results[$Name] = "NOT_PROVEN" }
    }
    elseif ($Name -ne "AUDITOR_REPORT_WRITE") {
        $Results[$Name] = Test-MutationCapability -Target $Resolved[$Name]
    }
}

$ResolvedReports = [IO.Path]::GetFullPath($ReportDirectory).TrimEnd('\')
if ($ResolvedReports -ine $Resolved["AUDITOR_REPORT_WRITE"]) {
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"; status = "REPORT_PATH_MISMATCH" })
    exit 24
}
if (Test-PathChainReparse -LiteralPath $ResolvedReports) {
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"; status = "UNSAFE_TARGET_PATH" })
    exit 24
}
[void][IO.Directory]::CreateDirectory($ResolvedReports)
$ReportPath = Join-Path $ResolvedReports ("denial-probe-" + [Guid]::NewGuid().ToString('N') + ".json")
$Utf8 = New-Object Text.UTF8Encoding($false)
try {
    $Stream = New-Object IO.FileStream($ReportPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
}
catch {
    $Results["AUDITOR_REPORT_WRITE"] = "DENIED"
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"; status = "REPORT_WRITE_DENIED"; results = $Results })
    exit 25
}
$Results["AUDITOR_REPORT_WRITE"] = "ALLOWED"
$Report = [ordered]@{
    schema = "AUDITOR_DENIAL_PROBE_REPORT_V1"
    status = "COMPLETE"
    effective_sid = $Identity.User.Value
    token_elevated = $Elevated
    runtime_manifest_sha256 = $Runtime.manifest_sha256
    input_manifest_sha256 = Get-Sha256Hex -LiteralPath $TargetManifestPath
    results = $Results
    network_endpoints = $NetworkEndpoints
    target_validation_matrix = $TargetValidationMatrix
    report_path = $ReportPath
}
try {
    $Writer = New-Object IO.StreamWriter($Stream, $Utf8)
    try {
        $Writer.Write(($Report | ConvertTo-Json -Depth 8 -Compress))
        $Writer.Flush()
        $Stream.Flush($true)
    }
    finally { $Writer.Dispose() }
}
finally { $Stream.Dispose() }
Write-ResultLine -Value $Report
exit 0
