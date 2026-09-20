#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BundlePath,
    [Parameter(Mandatory = $true)]
    [string]$ReportDirectory,
    [Parameter(Mandatory = $true)]
    [string]$RuntimeManifestPath,
    [string]$ReportFileName
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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
    try { $Text = [IO.File]::ReadAllText($LiteralPath) }
    catch { return [ordered]@{ status = "MANIFEST_INVALID"; value = $null; text = "" } }
    $Keys = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $CaseKeys = @{}
    foreach ($Match in [regex]::Matches($Text, '"(?<key>(?:\\.|[^"\\])*)"\s*:')) {
        $Key = $Match.Groups['key'].Value
        if (-not $Keys.Add($Key)) {
            return [ordered]@{ status = "MANIFEST_INVALID"; value = $null; text = $Text }
        }
        $Folded = $Key.ToLowerInvariant()
        if ($CaseKeys.ContainsKey($Folded) -and $CaseKeys[$Folded] -cne $Key) {
            return [ordered]@{ status = "CASE_COLLISION"; value = $null; text = $Text }
        }
        $CaseKeys[$Folded] = $Key
    }
    try { $Value = $Text | ConvertFrom-Json }
    catch { return [ordered]@{ status = "MANIFEST_INVALID"; value = $null; text = $Text } }
    return [ordered]@{ status = "PASS"; value = $Value; text = $Text }
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

function Compare-ExactNames {
    param([string[]]$Expected, [string[]]$Actual)
    $ExpectedSorted = @($Expected | Sort-Object { $_.ToLowerInvariant() })
    $ActualSorted = @($Actual | Sort-Object { $_.ToLowerInvariant() })
    if ($ExpectedSorted.Count -ne $ActualSorted.Count) { return $false }
    for ($Index = 0; $Index -lt $ExpectedSorted.Count; $Index++) {
        if ($ExpectedSorted[$Index] -cne $ActualSorted[$Index]) { return $false }
    }
    return $true
}

function Test-CaseCollision {
    param([string[]]$Names)
    $Seen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($Name in $Names) {
        if (-not $Seen.Add($Name)) { return $true }
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
    if (Test-CaseCollision -Names $Names) { return [ordered]@{ status = "RUNTIME_CASE_COLLISION" } }
    if (
        $Manifest.schema -eq "AUDITOR_RUNTIME_MANIFEST_V2" -and
        -not (Compare-ExactNames -Expected @(
            "AUDITOR_DENIAL_PROBE_V1.ps1",
            "AUDITOR_GATE_V2_PROBE.ps1",
            "CODEX_DECISION_AUDITOR_V1.ps1"
        ) -Actual $Names)
    ) { return [ordered]@{ status = "RUNTIME_FILE_SET_MISMATCH" } }
    foreach ($Name in $Names) {
        if (
            [IO.Path]::GetFileName($Name) -cne $Name -or
            $Name -in @("AUDITOR_RUNTIME_MANIFEST_V1.json", "AUDITOR_RUNTIME_MANIFEST_V2.json")
        ) {
            return [ordered]@{ status = "RUNTIME_UNSAFE_PATH" }
        }
    }
    $ManifestName = [IO.Path]::GetFileName($RuntimeManifestPath)
    $ActualNames = @(Get-ChildItem -LiteralPath $ActualRoot -File | ForEach-Object { $_.Name })
    if (-not (Compare-ExactNames -Expected @($Names + $ManifestName) -Actual $ActualNames)) {
        return [ordered]@{ status = "RUNTIME_FILE_SET_MISMATCH" }
    }
    foreach ($Property in $Properties) {
        $Target = Join-Path $ActualRoot $Property.Name
        if (Test-ReparsePoint -LiteralPath $Target) {
            return [ordered]@{ status = "RUNTIME_PATH_REDIRECTED" }
        }
        if ((Get-Sha256Hex -LiteralPath $Target) -ne [string]$Property.Value) {
            return [ordered]@{ status = "RUNTIME_HASH_MISMATCH" }
        }
    }
    return [ordered]@{
        status = "PASS"
        manifest_sha256 = Get-Sha256Hex -LiteralPath $RuntimeManifestPath
    }
}

function Test-Bundle {
    $Root = [IO.Path]::GetFullPath($BundlePath).TrimEnd('\')
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        return [ordered]@{ status = "MANIFEST_INVALID" }
    }
    if (Test-PathChainReparse -LiteralPath $Root) {
        return [ordered]@{ status = "UNSAFE_MANIFEST_PATH" }
    }
    $ManifestPath = Join-Path $Root "manifest.json"
    $Read = Read-StrictJson -LiteralPath $ManifestPath
    if ($Read.status -ne "PASS") { return [ordered]@{ status = $Read.status } }
    $Manifest = $Read.value
    if (
        $Manifest.schema -ne "AUDIT_EXPORT_MANIFEST_V1" -or
        $null -eq $Manifest.files -or
        [string]::IsNullOrWhiteSpace([string]$Manifest.bundle_id)
    ) {
        return [ordered]@{ status = "MANIFEST_INVALID" }
    }
    $Properties = @($Manifest.files.PSObject.Properties)
    $Names = @($Properties | ForEach-Object { $_.Name })
    if (Test-CaseCollision -Names $Names) { return [ordered]@{ status = "CASE_COLLISION" } }
    foreach ($Name in $Names) {
        if (
            [IO.Path]::GetFileName($Name) -cne $Name -or
            $Name.Contains('/') -or
            $Name.Contains('\') -or
            $Name -eq "manifest.json"
        ) {
            return [ordered]@{ status = "UNSAFE_MANIFEST_PATH" }
        }
    }
    $ActualNames = @(Get-ChildItem -LiteralPath $Root -File | ForEach-Object { $_.Name })
    if (-not (Compare-ExactNames -Expected @($Names + "manifest.json") -Actual $ActualNames)) {
        return [ordered]@{ status = "FILE_SET_MISMATCH" }
    }
    foreach ($Property in $Properties) {
        $Target = Join-Path $Root $Property.Name
        if (Test-ReparsePoint -LiteralPath $Target) {
            return [ordered]@{ status = "UNSAFE_MANIFEST_PATH" }
        }
        if ((Get-Sha256Hex -LiteralPath $Target) -ne [string]$Property.Value) {
            return [ordered]@{ status = "HASH_MISMATCH" }
        }
    }
    $Pairs = @()
    foreach ($Property in ($Properties | Sort-Object Name)) {
        $Key = ConvertTo-Json -InputObject $Property.Name -Compress
        $Value = ConvertTo-Json -InputObject ([string]$Property.Value) -Compress
        $Pairs += "$Key`:$Value"
    }
    $FilesJson = "{" + ($Pairs -join ',') + "}"
    $BundleSha256 = Get-TextSha256 -Text $FilesJson
    if (
        [string]$Manifest.bundle_sha256 -ne $BundleSha256 -or
        [string]$Manifest.bundle_id -ne "audit-$($BundleSha256.Substring(0, 24))"
    ) {
        return [ordered]@{ status = "BUNDLE_ID_MISMATCH" }
    }
    return [ordered]@{
        status = "PASS"
        bundle_id = [string]$Manifest.bundle_id
        manifest_sha256 = Get-Sha256Hex -LiteralPath $ManifestPath
        verified_file_count = $Names.Count
    }
}

function Write-ResultLine {
    param([object]$Value)
    Write-Output ("RESULT_JSON=" + ($Value | ConvertTo-Json -Depth 8 -Compress))
}

$Runtime = Test-RuntimeManifest
if ($Runtime.status -ne "PASS") {
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_REPORT_V1"; status = $Runtime.status })
    exit 10
}

$Bundle = Test-Bundle
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
$Elevated = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($Bundle.status -ne "PASS") {
    Write-ResultLine -Value ([ordered]@{
        schema = "AUDITOR_REPORT_V1"
        status = $Bundle.status
        effective_sid = $Identity.User.Value
        token_elevated = $Elevated
        runtime_manifest_sha256 = $Runtime.manifest_sha256
    })
    exit 0
}

if (Test-PathChainReparse -LiteralPath $ReportDirectory) {
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_REPORT_V1"; status = "UNSAFE_REPORT_PATH" })
    exit 11
}
[void][IO.Directory]::CreateDirectory([IO.Path]::GetFullPath($ReportDirectory))
if ([string]::IsNullOrWhiteSpace($ReportFileName)) {
    $ReportFileName = "$($Bundle.bundle_id)-$([Guid]::NewGuid().ToString('N')).json"
}
if ([IO.Path]::GetFileName($ReportFileName) -cne $ReportFileName) {
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_REPORT_V1"; status = "UNSAFE_REPORT_PATH" })
    exit 11
}
$ReportPath = Join-Path ([IO.Path]::GetFullPath($ReportDirectory)) $ReportFileName
$Report = [ordered]@{
    schema = "AUDITOR_REPORT_V1"
    status = "PASS"
    isolation_gate = "BLOCK"
    isolation_reason = "OS_LEVEL_DENIALS_NOT_PROVEN"
    bundle_id = $Bundle.bundle_id
    manifest_sha256 = $Bundle.manifest_sha256
    verified_file_count = $Bundle.verified_file_count
    runtime_manifest_sha256 = $Runtime.manifest_sha256
    effective_sid = $Identity.User.Value
    token_elevated = $Elevated
    report_path = $ReportPath
}
$Encoded = $Report | ConvertTo-Json -Depth 8 -Compress
$Utf8 = New-Object Text.UTF8Encoding($false)
try {
    $Stream = New-Object IO.FileStream($ReportPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $Writer = New-Object IO.StreamWriter($Stream, $Utf8)
        try { $Writer.Write($Encoded); $Writer.Flush(); $Stream.Flush($true) }
        finally { $Writer.Dispose() }
    }
    finally { $Stream.Dispose() }
}
catch [IO.IOException] {
    Write-ResultLine -Value ([ordered]@{ schema = "AUDITOR_REPORT_V1"; status = "REPORT_EXISTS" })
    exit 12
}
Write-ResultLine -Value $Report
exit 0
