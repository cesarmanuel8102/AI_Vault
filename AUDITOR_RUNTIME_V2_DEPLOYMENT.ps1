#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("Review", "Install", "Remove")]
    [string]$Mode = "Review",
    [switch]$ConfirmRuntimeMutation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ExpectedSid = "S-1-5-21-214160970-1890373857-4055601883-1012"
$ProgramRoot = "C:\ProgramData\CodexAuditorV1"
$InstalledRuntime = Join-Path $ProgramRoot "runtime"
$ProvisioningRoot = Join-Path $ProgramRoot "provisioning"
$DeploymentManifestPath = Join-Path $ProvisioningRoot "AUDITOR_RUNTIME_V2_DEPLOYMENT_MANIFEST.json"
$RuntimeManifestName = "AUDITOR_RUNTIME_MANIFEST_V2.json"
$PayloadNames = @(
    "AUDITOR_DENIAL_PROBE_V1.ps1",
    "AUDITOR_GATE_V2_PROBE.ps1",
    "CODEX_DECISION_AUDITOR_V1.ps1"
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

function Get-FilesJson {
    param([hashtable]$Hashes)
    $Pairs = @()
    foreach ($Name in @($Hashes.Keys | Sort-Object)) {
        $Pairs += ((ConvertTo-Json $Name -Compress) + ":" + (ConvertTo-Json $Hashes[$Name] -Compress))
    }
    return "{" + ($Pairs -join ',') + "}"
}

function Get-ManifestText {
    param([string]$Schema, [hashtable]$Hashes)
    $FilesJson = Get-FilesJson -Hashes $Hashes
    $Body = "{`"files`":$FilesJson,`"schema`":`"$Schema`"}"
    $ManifestHash = Get-TextSha256 -Text $Body
    return "{`"files`":$FilesJson,`"manifest_sha256`":`"$ManifestHash`",`"schema`":`"$Schema`"}"
}

function Get-SourcePayloadHashes {
    $Hashes = @{}
    foreach ($Name in $PayloadNames) {
        $Path = Join-Path (Join-Path $PSScriptRoot "auditor_runtime") $Name
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "SOURCE_RUNTIME_FILE_MISSING:$Name" }
        $Hashes[$Name] = Get-Sha256Hex -LiteralPath $Path
    }
    return $Hashes
}

function Get-ExpectedDocuments {
    $PayloadHashes = Get-SourcePayloadHashes
    $RuntimeText = Get-ManifestText -Schema "AUDITOR_RUNTIME_MANIFEST_V2" -Hashes $PayloadHashes
    $DeploymentHashes = @{}
    foreach ($Name in $PayloadNames) { $DeploymentHashes[$Name] = $PayloadHashes[$Name] }
    $DeploymentHashes[$RuntimeManifestName] = Get-TextSha256 -Text $RuntimeText
    $DeploymentText = Get-ManifestText -Schema "AUDITOR_RUNTIME_DEPLOYMENT_MANIFEST_V2" -Hashes $DeploymentHashes
    return [ordered]@{
        payload_hashes = $PayloadHashes
        runtime_text = $RuntimeText
        runtime_sha256 = Get-TextSha256 -Text $RuntimeText
        deployment_text = $DeploymentText
        deployment_sha256 = Get-TextSha256 -Text $DeploymentText
    }
}

function Test-InstalledExact {
    param([object]$Expected)
    if (-not (Test-Path -LiteralPath $InstalledRuntime -PathType Container)) { return $false }
    $Names = @(Get-ChildItem -LiteralPath $InstalledRuntime -File | ForEach-Object { $_.Name } | Sort-Object)
    $ExpectedNames = @($PayloadNames + $RuntimeManifestName | Sort-Object)
    if (($Names -join '|') -cne ($ExpectedNames -join '|')) { return $false }
    foreach ($Name in $PayloadNames) {
        if ((Get-Sha256Hex (Join-Path $InstalledRuntime $Name)) -ne $Expected.payload_hashes[$Name]) { return $false }
    }
    if ([IO.File]::ReadAllText((Join-Path $InstalledRuntime $RuntimeManifestName)) -cne $Expected.runtime_text) { return $false }
    if (-not (Test-Path -LiteralPath $DeploymentManifestPath -PathType Leaf)) { return $false }
    return [IO.File]::ReadAllText($DeploymentManifestPath) -ceq $Expected.deployment_text
}

function Assert-Administrator {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
    if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "ADMINISTRATOR_REQUIRED"
    }
}

function Write-Utf8CreateNew {
    param([string]$LiteralPath, [string]$Text)
    $Utf8 = New-Object Text.UTF8Encoding($false)
    $Stream = New-Object IO.FileStream($LiteralPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $Writer = New-Object IO.StreamWriter($Stream, $Utf8)
        try { $Writer.Write($Text); $Writer.Flush(); $Stream.Flush($true) }
        finally { $Writer.Dispose() }
    }
    finally { $Stream.Dispose() }
}

$Expected = Get-ExpectedDocuments
$InstalledExact = Test-InstalledExact -Expected $Expected
$InstallCommand = "PowerShell.exe -NoProfile -File .\AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1 -Mode Install -ConfirmRuntimeMutation"
$RemoveCommand = "PowerShell.exe -NoProfile -File .\AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1 -Mode Remove -ConfirmRuntimeMutation"

if ($Mode -eq "Review") {
    [ordered]@{
        schema = "AUDITOR_RUNTIME_V2_DEPLOYMENT_REVIEW_V1"
        MODE = "Review"
        EXPECTED_AUDITOR_SID = $ExpectedSid
        RUNTIME_ROOT = $InstalledRuntime
        PAYLOAD_SHA256 = $Expected.payload_hashes
        DEPLOYMENT_SCRIPT_SHA256 = Get-Sha256Hex -LiteralPath $PSCommandPath
        RUNTIME_MANIFEST_SHA256 = $Expected.runtime_sha256
        DEPLOYMENT_MANIFEST_SHA256 = $Expected.deployment_sha256
        INSTALLED_RUNTIME_EXACT = $InstalledExact
        NEW_ADMIN_ACTION_REQUIRED = -not $InstalledExact
        INSTALLATION_PERFORMED = $false
        INSTALL_COMMAND = $InstallCommand
        REMOVE_COMMAND = $RemoveCommand
    } | ConvertTo-Json -Depth 6
    exit 0
}

Assert-Administrator
if (-not $ConfirmRuntimeMutation) { throw "EXPLICIT_RUNTIME_MUTATION_CONFIRMATION_REQUIRED" }
if (-not (Test-Path -LiteralPath $ProgramRoot -PathType Container)) { throw "AUDITOR_PROGRAM_ROOT_NOT_RECOGNIZED" }

if ($Mode -eq "Install") {
    if (Test-Path -LiteralPath $InstalledRuntime -PathType Container) {
        $ExistingNames = @(Get-ChildItem -LiteralPath $InstalledRuntime -File | ForEach-Object { $_.Name })
        $KnownNames = @($PayloadNames + $RuntimeManifestName + "AUDITOR_RUNTIME_MANIFEST_V1.json")
        if (@($ExistingNames | Where-Object { $_ -notin $KnownNames }).Count -ne 0) { throw "UNRECOGNIZED_PRIOR_RUNTIME_STATE" }
    }
    $Acl = if (Test-Path -LiteralPath $InstalledRuntime) { Get-Acl -LiteralPath $InstalledRuntime } else { $null }
    $Stage = Join-Path $ProgramRoot ("runtime-v2-stage-" + [Guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $Stage)
    foreach ($Name in $PayloadNames) {
        Copy-Item -LiteralPath (Join-Path (Join-Path $PSScriptRoot "auditor_runtime") $Name) -Destination (Join-Path $Stage $Name)
    }
    Write-Utf8CreateNew -LiteralPath (Join-Path $Stage $RuntimeManifestName) -Text $Expected.runtime_text
    $Backup = $InstalledRuntime + ".v2-backup"
    if (Test-Path -LiteralPath $Backup) { throw "UNRECOGNIZED_PRIOR_RUNTIME_STATE" }
    if (Test-Path -LiteralPath $InstalledRuntime) { Move-Item -LiteralPath $InstalledRuntime -Destination $Backup }
    try {
        Move-Item -LiteralPath $Stage -Destination $InstalledRuntime
        if ($null -ne $Acl) { Set-Acl -LiteralPath $InstalledRuntime -AclObject $Acl }
        if (-not (Test-Path -LiteralPath $ProvisioningRoot)) { [void](New-Item -ItemType Directory -Path $ProvisioningRoot) }
        if (Test-Path -LiteralPath $DeploymentManifestPath) { [IO.File]::WriteAllText($DeploymentManifestPath, $Expected.deployment_text, (New-Object Text.UTF8Encoding($false))) }
        else { Write-Utf8CreateNew -LiteralPath $DeploymentManifestPath -Text $Expected.deployment_text }
        if (-not (Test-InstalledExact -Expected $Expected)) { throw "POST_INSTALL_VERIFICATION_FAILED" }
        if (Test-Path -LiteralPath $Backup) { Remove-Item -LiteralPath $Backup -Recurse -Force }
    }
    catch {
        if (Test-Path -LiteralPath $InstalledRuntime) { Remove-Item -LiteralPath $InstalledRuntime -Recurse -Force }
        if (Test-Path -LiteralPath $Backup) { Move-Item -LiteralPath $Backup -Destination $InstalledRuntime }
        throw
    }
    [ordered]@{ MODE = "Install"; INSTALLATION_PERFORMED = $true; VERIFIED = $true } | ConvertTo-Json
    exit 0
}

if (-not $InstalledExact) { throw "REMOVE_REFUSES_UNRECOGNIZED_RUNTIME_STATE" }
foreach ($Name in @($PayloadNames + $RuntimeManifestName)) { Remove-Item -LiteralPath (Join-Path $InstalledRuntime $Name) -Force }
Remove-Item -LiteralPath $DeploymentManifestPath -Force
[ordered]@{ MODE = "Remove"; INSTALLATION_PERFORMED = $false; REMOVAL_PERFORMED = $true } | ConvertTo-Json
