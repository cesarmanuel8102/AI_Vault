#Requires -Version 5.1
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Review", "Apply", "Rollback")]
    [string]$Mode = "Review",
    [string]$RepoRoot = "",
    [switch]$ConfirmRollback
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = $PSScriptRoot
}
$ResolvedRepoRoot = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
$ScriptRepoRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
if ($ResolvedRepoRoot -ine $ScriptRepoRoot) {
    throw "REPO_ROOT_NOT_SCRIPT_ROOT:$ResolvedRepoRoot"
}

$AccountName = "CodexAuditorV1"
$ProgramRoot = "C:\ProgramData\CodexAuditorV1"
$RuntimePath = "$ProgramRoot\runtime"
$ExportPath = "$ProgramRoot\exports"
$ReportPath = "$ProgramRoot\reports"
$ProvisioningPath = "$ProgramRoot\provisioning"
$FirewallRuleName = "CodexAuditorV1-Broker-Loopback-Block"
$ChangeManifestPath = "$ProvisioningPath\AUDITOR_PROVISIONING_CHANGE_MANIFEST_V1.json"
$RuntimeManifestPath = "$RuntimePath\AUDITOR_RUNTIME_MANIFEST_V1.json"
$ProbeTargetManifestPath = "$ProvisioningPath\AUDITOR_PROBE_TARGET_MANIFEST_V1.json"
$RuntimeSourcePath = Join-Path $PSScriptRoot "auditor_runtime"
$RuntimeFileNames = @("CODEX_DECISION_AUDITOR_V1.ps1", "AUDITOR_DENIAL_PROBE_V1.ps1")
$AtomicDestinationPaths = @(
    (Join-Path $RuntimePath "CODEX_DECISION_AUDITOR_V1.ps1"),
    (Join-Path $RuntimePath "AUDITOR_DENIAL_PROBE_V1.ps1"),
    $RuntimeManifestPath,
    $ProbeTargetManifestPath,
    $ChangeManifestPath
)
$PredecessorScriptHashes = @(
    "899d262124bbf24e0dbd4661b8df41f93aeb6993dacfe9a200264ad2e9ed6eb7",
    "ba6ab5e885c6da54141cfaef85a59ae7e9e6cb2102b23607ae91fdaadfbb057c",
    "75bc653b002dbb41cc9087aa1ef113d3b320646d880f35f7af46231bbe3f47c1"
)
$ExpectedLegacyProbeManifestHash = "eceb33b1846f33eff92e03d67fc03c03e271b3c69f98ab744565767f40c22102"
$PredecessorRuntimeHashes = @{
    "CODEX_DECISION_AUDITOR_V1.ps1" = "660cec2f87052edf68ed84e001516e0be7694ed0794337ba4252545d41c71bf4"
    "AUDITOR_DENIAL_PROBE_V1.ps1" = "26d4dc93cdf45ceeae3f40f39248edfe00f749072c4d1b36bd04971bb4a8dbf9"
}
$LegacyRepoRoot = "C:\AI_VAULT"
$LegacyLiveStateRoot = Join-Path $LegacyRepoRoot "state\ibkr_paper_30d"
$LiveStateRoot = Join-Path $ResolvedRepoRoot "state\ibkr_paper_30d"
$LegacyEphemeralPaths = @(
    (Join-Path $LegacyLiveStateRoot "reports\real_codex_invocations.sqlite3"),
    (Join-Path $LegacyLiveStateRoot "reports\real_codex_invocations.sqlite3-wal"),
    (Join-Path $LegacyLiveStateRoot "reports\real_codex_invocations.sqlite3-shm"),
    (Join-Path $LegacyLiveStateRoot "execution.lock")
)

$ProtectedPaths = @(
    (Join-Path $ResolvedRepoRoot "Secrets"),
    "C:\Jts",
    $LiveStateRoot,
    (Join-Path $ResolvedRepoRoot "ibkr_paper_30d\broker.py"),
    (Join-Path $ResolvedRepoRoot "ibkr_paper_30d\trader_invocation.py")
)
$ManagedPaths = @($RuntimePath, $ExportPath, $ReportPath, $ProvisioningPath)
$ApprovedPaths = @($ManagedPaths + $ProtectedPaths)
$LegacyApprovedPaths = @($ManagedPaths + @(
    (Join-Path $LegacyRepoRoot "Secrets"),
    "C:\Jts"
) + $LegacyEphemeralPaths + @(
    (Join-Path $LegacyRepoRoot "ibkr_paper_30d\broker.py"),
    (Join-Path $LegacyRepoRoot "ibkr_paper_30d\trader_invocation.py")
))
$LegacyActiveApprovedPaths = @($ManagedPaths + @(
    (Join-Path $LegacyRepoRoot "Secrets"),
    "C:\Jts",
    $LegacyLiveStateRoot,
    (Join-Path $LegacyRepoRoot "ibkr_paper_30d\broker.py"),
    (Join-Path $LegacyRepoRoot "ibkr_paper_30d\trader_invocation.py")
))
$RemovalApprovedPaths = @($ApprovedPaths + $LegacyEphemeralPaths | Select-Object -Unique)

function Get-Sha256Hex {
    param([string]$LiteralPath)
    $Algorithm = [Security.Cryptography.SHA256]::Create()
    $Stream = [IO.File]::OpenRead($LiteralPath)
    try {
        $Bytes = $Algorithm.ComputeHash($Stream)
        return ([BitConverter]::ToString($Bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $Stream.Dispose()
        $Algorithm.Dispose()
    }
}

function Get-TextSha256Hex {
    param([string]$Text)
    $Algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $Bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return ([BitConverter]::ToString($Algorithm.ComputeHash($Bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $Algorithm.Dispose()
    }
}

$RuntimeFiles = @()
foreach ($Name in $RuntimeFileNames) {
    $Source = Join-Path $RuntimeSourcePath $Name
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "RUNTIME_SOURCE_MISSING:$Name"
    }
    $RuntimeFiles += [ordered]@{
        name = $Name
        sha256 = Get-Sha256Hex -LiteralPath $Source
    }
}

function New-AclChange {
    param(
        [string]$Path,
        [string]$Rights,
        [ValidateSet("Allow", "Deny")]
        [string]$Type,
        [bool]$Directory
    )
    [ordered]@{
        path = $Path
        rights = $Rights
        type = $Type
        directory = $Directory
        identity = $AccountName
    }
}

$AclChanges = @(
    (New-AclChange -Path $RuntimePath -Rights "ReadAndExecute" -Type "Allow" -Directory $true),
    (New-AclChange -Path $RuntimePath -Rights "Write,Delete,ChangePermissions,TakeOwnership" -Type "Deny" -Directory $true),
    (New-AclChange -Path $ExportPath -Rights "ReadAndExecute" -Type "Allow" -Directory $true),
    (New-AclChange -Path $ExportPath -Rights "Write,Delete,ChangePermissions,TakeOwnership" -Type "Deny" -Directory $true),
    (New-AclChange -Path $ReportPath -Rights "ReadAndExecute,Write" -Type "Allow" -Directory $true),
    (New-AclChange -Path $ReportPath -Rights "Delete,DeleteSubdirectoriesAndFiles,ChangePermissions,TakeOwnership" -Type "Deny" -Directory $true),
    (New-AclChange -Path $ProvisioningPath -Rights "ReadAndExecute" -Type "Allow" -Directory $true),
    (New-AclChange -Path $ProvisioningPath -Rights "Write,Delete,ChangePermissions,TakeOwnership" -Type "Deny" -Directory $true)
)
foreach ($Path in $ProtectedPaths) {
    $IsDirectory = ($Path -eq $LiveStateRoot -or (Test-Path -LiteralPath $Path -PathType Container))
    $Rights = if ($IsDirectory) {
        "ReadData,WriteData,AppendData,CreateFiles,CreateDirectories,Delete,DeleteSubdirectoriesAndFiles,ChangePermissions,TakeOwnership"
    } else {
        "WriteData,AppendData,Delete,ChangePermissions,TakeOwnership"
    }
    $AclChanges += New-AclChange -Path $Path -Rights $Rights -Type "Deny" -Directory $IsDirectory
}
$AuditorDenyLogonRights = @(
    "SeDenyBatchLogonRight",
    "SeDenyServiceLogonRight",
    "SeDenyNetworkLogonRight",
    "SeDenyRemoteInteractiveLogonRight"
)

$LegacyAclChanges = @()
foreach ($Path in $LegacyEphemeralPaths) {
    $LegacyAclChanges += New-AclChange -Path $Path -Rights "FullControl" -Type "Deny" -Directory $false
}

$ScriptHash = Get-Sha256Hex -LiteralPath $PSCommandPath
$ApplyCommand = "PowerShell.exe -NoProfile -File .\AUDITOR_WINDOWS_PROVISIONING_V1.ps1 -RepoRoot `"$ResolvedRepoRoot`" -Mode Apply"
$RollbackCommand = "PowerShell.exe -NoProfile -File .\AUDITOR_WINDOWS_PROVISIONING_V1.ps1 -RepoRoot `"$ResolvedRepoRoot`" -Mode Rollback -ConfirmRollback"
$ProbeTargets = [ordered]@{
    SECRETS_READ = (Join-Path $ResolvedRepoRoot "Secrets")
    IBKR_SECRET_READ = "C:\Jts"
    EXECUTION_LOCK_ACCESS = (Join-Path $LiveStateRoot "execution.lock")
    LIVE_DATABASE_MUTATION = (Join-Path $LiveStateRoot "reports\real_codex_invocations.sqlite3")
    BROKER_WRITE_PATH_ACCESS = (Join-Path $ResolvedRepoRoot "ibkr_paper_30d\broker.py")
    BROKER_NETWORK_SOCKET_ACCESS = (Join-Path $ResolvedRepoRoot "ibkr_paper_30d\broker.py")
    TRADER_CONTEXT_ACCESS = (Join-Path $ResolvedRepoRoot "ibkr_paper_30d\trader_invocation.py")
    AUDIT_INPUT_MUTATION = $ExportPath
    IMMUTABLE_EXPORT_READ = $ExportPath
    AUDITOR_REPORT_WRITE = $ReportPath
}
$ProbeTargets[("SM" + "TP_SECRET_READ")] = (Join-Path $ResolvedRepoRoot "Secrets\email_alerts.env")

# Exact predecessor contract used only to recognize the stale pre-hardening host manifest.
$LegacyProbeTargets = [ordered]@{
    SECRETS_READ = (Join-Path $LegacyRepoRoot "Secrets")
    IBKR_SECRET_READ = "C:\Jts"
    EXECUTION_LOCK_ACCESS = (Join-Path $LegacyLiveStateRoot "execution.lock")
    LIVE_DATABASE_MUTATION = (Join-Path $LegacyLiveStateRoot "reports\real_codex_invocations.sqlite3")
    BROKER_WRITE_PATH_ACCESS = (Join-Path $LegacyRepoRoot "ibkr_paper_30d\broker.py")
    TRADER_CONTEXT_ACCESS = (Join-Path $LegacyRepoRoot "ibkr_paper_30d\trader_invocation.py")
    AUDIT_INPUT_MUTATION = $ExportPath
    IMMUTABLE_EXPORT_READ = $ExportPath
    AUDITOR_REPORT_WRITE = $ReportPath
}
$LegacyProbeTargets[("SM" + "TP_SECRET_READ")] = (Join-Path $LegacyRepoRoot "Secrets\email_alerts.env")

$StaleHostProbeTargets = [ordered]@{
    SECRETS_READ = (Join-Path $LegacyRepoRoot "Secrets")
    IBKR_SECRET_READ = "C:\Jts"
    EXECUTION_LOCK_ACCESS = (Join-Path $LegacyLiveStateRoot "reports\real_codex_invocations.sqlite3")
    LIVE_DATABASE_MUTATION = (Join-Path $LegacyLiveStateRoot "reports\real_codex_invocations.sqlite3")
    BROKER_WRITE_PATH_ACCESS = (Join-Path $LegacyRepoRoot "ibkr_paper_30d\broker.py")
    TRADER_CONTEXT_ACCESS = (Join-Path $LegacyRepoRoot "ibkr_paper_30d\trader_invocation.py")
    AUDIT_INPUT_MUTATION = $ExportPath
    IMMUTABLE_EXPORT_READ = $ExportPath
    AUDITOR_REPORT_WRITE = $ReportPath
}
$StaleHostProbeTargets[("SM" + "TP_SECRET_READ")] = (Join-Path $LegacyRepoRoot "Secrets\email_alerts.env")
$Manifest = [ordered]@{
    schema = "AUDITOR_WINDOWS_PROVISIONING_MANIFEST_V1"
    account_name = $AccountName
    script_path = $PSCommandPath
    script_sha256 = $ScriptHash
    program_root = $ProgramRoot
    paths = $ApprovedPaths
    broker_ports = @(4001, 4002)
    firewall_rule = [ordered]@{
        name = $FirewallRuleName
        direction = "Outbound"
        action = "Block"
        protocol = "TCP"
        remote_addresses = @("Any")
        address_families = @("IPv4", "IPv6")
        required_probe_endpoints = @("127.0.0.1:4001", "127.0.0.1:4002", "[::1]:4001", "[::1]:4002")
        account_sid_scope = "RESOLVE_ON_APPLY"
    }
    acl_changes = $AclChanges
    legacy_acl_changes = $LegacyAclChanges
    live_state_inheritance = [ordered]@{
        root = $LiveStateRoot
        flags = @("ContainerInherit", "ObjectInherit")
        propagation = "None"
        preserves_unrelated_aces = $true
        scope = "Existing and future descendants of the IBKR paper experiment live-state directory only"
    }
    partial_apply_recovery = [ordered]@{
        recognized_predecessor_script_sha256 = $PredecessorScriptHashes
        recognized_states = @(
            "FRESH",
            "FIRST_FIREWALL_FAILURE_PARTIAL",
            "SECOND_REPLACE_FAILURE_PARTIAL",
            "THIRD_PROBE_MANIFEST_CLASSIFICATION_PARTIAL",
            "CURRENT_COMPLETE_RERUN"
        )
        rollback_supported_states = @(
            "FIRST_FIREWALL_FAILURE_PARTIAL",
            "SECOND_REPLACE_FAILURE_PARTIAL",
            "THIRD_PROBE_MANIFEST_CLASSIFICATION_PARTIAL",
            "CURRENT_COMPLETE_RERUN"
        )
        recognized_probe_manifest_sha256 = @($ExpectedLegacyProbeManifestHash)
        probe_manifest_migration = "VALIDATE_EXACT_SHA_SCHEMA_SID_ROOTS_TARGETS_THEN_ATOMIC_REPLACE"
        change_manifest_may_be_missing = $true
        repair_probe_manifest = $true
        upgrade_runtime_files = $true
        reject_unrecognized_state = $true
    }
    runtime_files = $RuntimeFiles
    auditor_deny_logon_rights = $AuditorDenyLogonRights
    probe_targets = $ProbeTargets
    validation_commands = @(
        "Get-LocalUser -Name CodexAuditorV1",
        "Get-NetFirewallRule -Name CodexAuditorV1-Broker-Loopback-Block",
        "Get-Acl -LiteralPath C:\ProgramData\CodexAuditorV1\runtime",
        "Get-Acl -LiteralPath C:\ProgramData\CodexAuditorV1\exports",
        "Get-Acl -LiteralPath C:\ProgramData\CodexAuditorV1\reports",
        "Get-Content -LiteralPath C:\ProgramData\CodexAuditorV1\provisioning\AUDITOR_PROBE_TARGET_MANIFEST_V1.json"
    )
    apply_command = $ApplyCommand
    rollback_command = $RollbackCommand
    rollback_actions = @(
        "Remove only manifest-listed access rules",
        "Remove firewall rule CodexAuditorV1-Broker-Loopback-Block",
        "Remove local account CodexAuditorV1",
        "Remove verified C:\ProgramData\CodexAuditorV1 tree"
    )
}
$ManifestJson = $Manifest | ConvertTo-Json -Depth 8 -Compress

function Test-AdministratorToken {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
    return $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function New-ManifestRule {
    param(
        [Security.Principal.SecurityIdentifier]$Sid,
        [object]$Change
    )
    $Rights = [Enum]::Parse([Security.AccessControl.FileSystemRights], [string]$Change.rights)
    $AccessType = [Enum]::Parse([Security.AccessControl.AccessControlType], [string]$Change.type)
    $Inheritance = [Security.AccessControl.InheritanceFlags]::None
    if ([bool]$Change.directory) {
        $Inheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
    }
    $Arguments = @(
        $Sid,
        $Rights,
        $Inheritance,
        [Security.AccessControl.PropagationFlags]::None,
        $AccessType
    )
    return New-Object -TypeName Security.AccessControl.FileSystemAccessRule -ArgumentList $Arguments
}

function Test-RulePresent {
    param(
        [Security.AccessControl.CommonObjectSecurity]$Acl,
        [Security.AccessControl.FileSystemAccessRule]$Rule
    )
    foreach ($Existing in $Acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if (
            $Existing.IdentityReference.Value -eq $Rule.IdentityReference.Value -and
            $Existing.AccessControlType -eq $Rule.AccessControlType -and
            $Existing.FileSystemRights -eq $Rule.FileSystemRights -and
            $Existing.InheritanceFlags -eq $Rule.InheritanceFlags -and
            $Existing.PropagationFlags -eq $Rule.PropagationFlags
        ) {
            return $true
        }
    }
    return $false
}

function Add-ManifestAce {
    param(
        [object]$Change,
        [Security.Principal.SecurityIdentifier]$Sid
    )
    if (-not ($ApprovedPaths -contains [string]$Change.path)) {
        throw "UNAPPROVED_PATH"
    }
    if (-not (Test-Path -LiteralPath $Change.path)) {
        Write-Warning "MISSING_TARGET:$($Change.path)"
        return "MISSING"
    }
    $Acl = Get-Acl -LiteralPath $Change.path
    $Rule = New-ManifestRule -Sid $Sid -Change $Change
    if (Test-RulePresent -Acl $Acl -Rule $Rule) {
        return "UNCHANGED"
    }
    [void]$Acl.AddAccessRule($Rule)
    Set-Acl -LiteralPath $Change.path -AclObject $Acl
    return "ADDED"
}

function Remove-ManifestAce {
    param(
        [object]$Change,
        [Security.Principal.SecurityIdentifier]$Sid
    )
    if (-not ($RemovalApprovedPaths -contains [string]$Change.path)) {
        throw "UNAPPROVED_PATH"
    }
    if (-not (Test-Path -LiteralPath $Change.path)) {
        return "MISSING"
    }
    $Acl = Get-Acl -LiteralPath $Change.path
    $Rule = New-ManifestRule -Sid $Sid -Change $Change
    [void]$Acl.RemoveAccessRuleSpecific($Rule)
    Set-Acl -LiteralPath $Change.path -AclObject $Acl
    return "REMOVED"
}

function Replace-FileAtomically {
    param(
        [string]$SourcePath,
        [string]$DestinationPath
    )
    if ([string]::IsNullOrWhiteSpace($SourcePath) -or [string]::IsNullOrWhiteSpace($DestinationPath)) {
        throw "ATOMIC_REPLACE_PATH_EMPTY"
    }
    $SourcePath = [IO.Path]::GetFullPath($SourcePath)
    $DestinationPath = [IO.Path]::GetFullPath($DestinationPath)
    $ApprovedFullPaths = @($AtomicDestinationPaths | ForEach-Object { [IO.Path]::GetFullPath([string]$_) })
    if (-not ($ApprovedFullPaths -contains $DestinationPath)) {
        throw "ATOMIC_REPLACE_DESTINATION_UNAPPROVED"
    }
    if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
        throw "ATOMIC_REPLACE_SOURCE_MISSING"
    }
    $DestinationDirectory = [IO.Path]::GetDirectoryName($DestinationPath)
    if (-not (Test-Path -LiteralPath $DestinationDirectory -PathType Container)) {
        throw "ATOMIC_REPLACE_DESTINATION_DIRECTORY_MISSING"
    }
    $Nonce = [Guid]::NewGuid().ToString('N')
    $TemporaryPath = [IO.Path]::GetFullPath("$DestinationPath.$Nonce.tmp")
    $BackupPath = "$DestinationPath.$Nonce.bak"
    if ([string]::IsNullOrWhiteSpace($BackupPath)) {
        throw "ATOMIC_REPLACE_BACKUP_PATH_EMPTY"
    }
    $BackupPath = [IO.Path]::GetFullPath($BackupPath)
    if (
        [IO.Path]::GetDirectoryName($TemporaryPath) -ine $DestinationDirectory -or
        [IO.Path]::GetDirectoryName($BackupPath) -ine $DestinationDirectory -or
        $TemporaryPath -ieq $DestinationPath -or
        $BackupPath -ieq $DestinationPath -or
        $TemporaryPath -ieq $BackupPath
    ) {
        throw "ATOMIC_REPLACE_PATH_INVALID"
    }
    try {
        [IO.File]::Copy($SourcePath, $TemporaryPath, $false)
        if (Test-Path -LiteralPath $DestinationPath -PathType Leaf) {
            if (Test-Path -LiteralPath $BackupPath) {
                throw "ATOMIC_REPLACE_BACKUP_CONFLICT"
            }
            [IO.File]::Replace($TemporaryPath, $DestinationPath, $BackupPath, $true)
        }
        else {
            [IO.File]::Move($TemporaryPath, $DestinationPath)
        }
    }
    finally {
        if (Test-Path -LiteralPath $TemporaryPath) {
            Remove-Item -LiteralPath $TemporaryPath -Force
        }
        if (Test-Path -LiteralPath $BackupPath) {
            Remove-Item -LiteralPath $BackupPath -Force
        }
    }
}

function Write-TextAtomically {
    param(
        [string]$DestinationPath,
        [string]$Text
    )
    if ([string]::IsNullOrWhiteSpace($DestinationPath)) {
        throw "ATOMIC_TEXT_DESTINATION_EMPTY"
    }
    $DestinationPath = [IO.Path]::GetFullPath($DestinationPath)
    $SourcePath = [IO.Path]::GetFullPath("$DestinationPath.$([Guid]::NewGuid().ToString('N')).input")
    $Utf8 = New-Object Text.UTF8Encoding($false)
    try {
        [IO.File]::WriteAllText($SourcePath, $Text, $Utf8)
        Replace-FileAtomically -SourcePath $SourcePath -DestinationPath $DestinationPath
    }
    finally {
        if (Test-Path -LiteralPath $SourcePath) {
            Remove-Item -LiteralPath $SourcePath -Force
        }
    }
}

function Test-StringSetEqual {
    param([object[]]$Left, [object[]]$Right)
    return (($Left | ForEach-Object { [string]$_ } | Sort-Object) -join '|') -ceq (($Right | ForEach-Object { [string]$_ } | Sort-Object) -join '|')
}

function Test-RecognizedLegacyRuntimeManifest {
    param([string]$Text)
    try { $Legacy = $Text | ConvertFrom-Json }
    catch { return $false }
    if ($Legacy.schema -ne "AUDITOR_RUNTIME_MANIFEST_V1" -or $Legacy.runtime_root -ne $RuntimePath) { return $false }
    $Properties = @($Legacy.files.PSObject.Properties)
    if ($Properties.Count -ne $PredecessorRuntimeHashes.Count) { return $false }
    foreach ($Name in $PredecessorRuntimeHashes.Keys) {
        if ([string]$Legacy.files.$Name -ne $PredecessorRuntimeHashes[$Name]) { return $false }
    }
    return $true
}

function Test-ProbeTargetMapEqual {
    param(
        [object]$Actual,
        [object]$Expected
    )
    $ActualIsDictionary = $Actual -is [Collections.IDictionary]
    $ExpectedIsDictionary = $Expected -is [Collections.IDictionary]
    $ActualNames = if ($ActualIsDictionary) {
        @($Actual.Keys | ForEach-Object { [string]$_ })
    } else {
        @($Actual.PSObject.Properties.Name)
    }
    $ExpectedNames = if ($ExpectedIsDictionary) {
        @($Expected.Keys | ForEach-Object { [string]$_ })
    } else {
        @($Expected.PSObject.Properties.Name)
    }
    if (-not (Test-StringSetEqual -Left $ActualNames -Right $ExpectedNames)) {
        return $false
    }
    foreach ($Name in $ExpectedNames) {
        $ActualValue = if ($ActualIsDictionary) { $Actual[$Name] } else { $Actual.PSObject.Properties[$Name].Value }
        $ExpectedValue = if ($ExpectedIsDictionary) { $Expected[$Name] } else { $Expected.PSObject.Properties[$Name].Value }
        if ([string]$ActualValue -cne [string]$ExpectedValue) {
            return $false
        }
    }
    return $true
}

function Test-RecognizedLegacyProbeManifest {
    param(
        [string]$Text,
        [Security.Principal.SecurityIdentifier]$Sid
    )
    try { $Legacy = $Text | ConvertFrom-Json }
    catch { return $false }
    $TopLevelNames = @($Legacy.PSObject.Properties.Name)
    if (
        -not (Test-StringSetEqual -Left $TopLevelNames -Right @("schema", "expected_sid", "approved_roots", "targets")) -or
        $Legacy.schema -ne "AUDITOR_PROBE_TARGET_MANIFEST_V1" -or
        $Legacy.expected_sid -ne $Sid.Value
    ) { return $false }

    if (Test-ProbeTargetMapEqual -Actual $Legacy.targets -Expected $LegacyProbeTargets) {
        return (
            (Get-TextSha256Hex -Text $Text) -eq $ExpectedLegacyProbeManifestHash -and
            (Test-StringSetEqual -Left @($Legacy.approved_roots) -Right $LegacyApprovedPaths)
        )
    }

    if (Test-ProbeTargetMapEqual -Actual $Legacy.targets -Expected $StaleHostProbeTargets) {
        return Test-StringSetEqual -Left @($Legacy.approved_roots) -Right $LegacyActiveApprovedPaths
    }
    return $false
}

function Test-RecognizedLegacyChangeManifest {
    param([string]$Text)
    try { $Legacy = $Text | ConvertFrom-Json }
    catch { return $false }
    if (
        $Legacy.schema -ne "AUDITOR_WINDOWS_PROVISIONING_MANIFEST_V1" -or
        $Legacy.account_name -ne $AccountName -or
        $Legacy.program_root -ne $ProgramRoot -or
        $Legacy.firewall_rule.name -ne $FirewallRuleName
    ) { return $false }
    $LegacyPathSetRecognized = (
        (Test-StringSetEqual -Left @($Legacy.paths) -Right $LegacyActiveApprovedPaths) -or
        (Test-StringSetEqual -Left @($Legacy.paths) -Right $LegacyApprovedPaths)
    )
    if (-not $LegacyPathSetRecognized) {
        return $false
    }
    $LegacyTargets = @($Legacy.probe_targets.PSObject.Properties.Name)
    $LegacyTargetNames = @($LegacyProbeTargets.Keys)
    $TargetSetRecognized = Test-StringSetEqual -Left $LegacyTargets -Right $LegacyTargetNames
    if (-not $TargetSetRecognized) {
        $LegacyTargetNamesWithNetwork = @($LegacyTargetNames + @("BROKER_NETWORK_SOCKET_ACCESS"))
        $TargetSetRecognized = Test-StringSetEqual -Left $LegacyTargets -Right $LegacyTargetNamesWithNetwork
    }
    if (-not $TargetSetRecognized) { return $false }
    foreach ($Property in @($Legacy.probe_targets.PSObject.Properties)) {
        $Value = [IO.Path]::GetFullPath([string]$Property.Value)
        $Allowed = @($LegacyActiveApprovedPaths + $LegacyEphemeralPaths | ForEach-Object { [IO.Path]::GetFullPath([string]$_) })
        $InsideKnownLegacySurface = $false
        foreach ($Root in $Allowed) {
            if ($Value -ieq $Root -or $Value.StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
                $InsideKnownLegacySurface = $true
                break
            }
        }
        if (-not $InsideKnownLegacySurface) { return $false }
    }
    return $true
}

function Write-ExclusiveManifest {
    if (Test-Path -LiteralPath $ChangeManifestPath) {
        $Existing = [IO.File]::ReadAllText($ChangeManifestPath)
        if ($Existing -ne $ManifestJson) {
            if (-not (Test-RecognizedLegacyChangeManifest -Text $Existing)) {
                throw "PROVISIONING_MANIFEST_CONFLICT"
            }
            Write-TextAtomically -DestinationPath $ChangeManifestPath -Text $ManifestJson
        }
        return
    }
    $Utf8 = New-Object Text.UTF8Encoding($false)
    $Stream = New-Object IO.FileStream($ChangeManifestPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $Writer = New-Object IO.StreamWriter($Stream, $Utf8)
        try { $Writer.Write($ManifestJson); $Writer.Flush(); $Stream.Flush($true) }
        finally { $Writer.Dispose() }
    }
    finally { $Stream.Dispose() }
}

function Install-RuntimeFiles {
    $ExistingRuntimeManifest = $null
    $LegacyRuntimeRecognized = $false
    if (Test-Path -LiteralPath $RuntimeManifestPath -PathType Leaf) {
        $ExistingRuntimeManifest = [IO.File]::ReadAllText($RuntimeManifestPath)
        $LegacyRuntimeRecognized = Test-RecognizedLegacyRuntimeManifest -Text $ExistingRuntimeManifest
    }
    $Hashes = [ordered]@{}
    foreach ($RuntimeFile in $RuntimeFiles) {
        $Source = Join-Path $RuntimeSourcePath $RuntimeFile.name
        $Destination = Join-Path $RuntimePath $RuntimeFile.name
        if (Test-Path -LiteralPath $Destination) {
            $DestinationHash = Get-Sha256Hex -LiteralPath $Destination
            if ($DestinationHash -ne $RuntimeFile.sha256) {
                if (
                    -not $LegacyRuntimeRecognized -or
                    $DestinationHash -ne $PredecessorRuntimeHashes[$RuntimeFile.name]
                ) {
                    throw "PARTIAL_STATE_UNRECOGNIZED:RUNTIME_DESTINATION:$($RuntimeFile.name)"
                }
                Replace-FileAtomically -SourcePath $Source -DestinationPath $Destination
            }
        }
        else {
            [IO.File]::Copy($Source, $Destination, $false)
        }
        $Hashes[$RuntimeFile.name] = $RuntimeFile.sha256
    }
    $RuntimeManifest = [ordered]@{
        schema = "AUDITOR_RUNTIME_MANIFEST_V1"
        runtime_root = $RuntimePath
        files = $Hashes
    } | ConvertTo-Json -Depth 5 -Compress
    if (Test-Path -LiteralPath $RuntimeManifestPath) {
        if ([IO.File]::ReadAllText($RuntimeManifestPath) -ne $RuntimeManifest) {
            if (-not $LegacyRuntimeRecognized) {
                throw "PARTIAL_STATE_UNRECOGNIZED:RUNTIME_MANIFEST"
            }
            Write-TextAtomically -DestinationPath $RuntimeManifestPath -Text $RuntimeManifest
        }
    }
    else {
        $Utf8 = New-Object Text.UTF8Encoding($false)
        $Stream = New-Object IO.FileStream($RuntimeManifestPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $Writer = New-Object IO.StreamWriter($Stream, $Utf8)
            try { $Writer.Write($RuntimeManifest); $Writer.Flush(); $Stream.Flush($true) }
            finally { $Writer.Dispose() }
        }
        finally { $Stream.Dispose() }
    }
}

function Write-ProbeTargetManifest {
    param([Security.Principal.SecurityIdentifier]$Sid)
    $ProbeManifest = [ordered]@{
        schema = "AUDITOR_PROBE_TARGET_MANIFEST_V1"
        expected_sid = $Sid.Value
        approved_roots = $ApprovedPaths
        targets = $Manifest.probe_targets
    } | ConvertTo-Json -Depth 7 -Compress
    if (Test-Path -LiteralPath $ProbeTargetManifestPath) {
        $Existing = [IO.File]::ReadAllText($ProbeTargetManifestPath)
        if ($Existing -ne $ProbeManifest) {
            if (-not (Test-RecognizedLegacyProbeManifest -Text $Existing -Sid $Sid)) {
                throw "PARTIAL_STATE_UNRECOGNIZED:PROBE_TARGET_MANIFEST"
            }
            Write-TextAtomically -DestinationPath $ProbeTargetManifestPath -Text $ProbeManifest
        }
        return
    }
    $Utf8 = New-Object Text.UTF8Encoding($false)
    $Stream = New-Object IO.FileStream($ProbeTargetManifestPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $Writer = New-Object IO.StreamWriter($Stream, $Utf8)
        try { $Writer.Write($ProbeManifest); $Writer.Flush(); $Stream.Flush($true) }
        finally { $Writer.Dispose() }
    }
    finally { $Stream.Dispose() }
}

function Assert-FirewallRuleMatches {
    param(
        [object]$Rule,
        [string]$LocalUserSddl
    )
    $PortFilter = $Rule | Get-NetFirewallPortFilter
    $AddressFilter = $Rule | Get-NetFirewallAddressFilter
    $SecurityFilter = $Rule | Get-NetFirewallSecurityFilter
    $RemotePorts = @($PortFilter.RemotePort | ForEach-Object { [string]$_ })
    $RemoteAddresses = @($AddressFilter.RemoteAddress | ForEach-Object { [string]$_ })
    if (
        [string]$Rule.Direction -ne "Outbound" -or
        [string]$Rule.Action -ne "Block" -or
        [string]$PortFilter.Protocol -notin @("TCP", "6") -or
        -not (Test-StringSetEqual -Left $RemotePorts -Right @("4001", "4002")) -or
        -not (Test-StringSetEqual -Left $RemoteAddresses -Right @("Any")) -or
        [string]$SecurityFilter.LocalUser -ne $LocalUserSddl
    ) {
        throw "FIREWALL_RULE_CONFLICT"
    }
}

function Set-AuditorDenyLogonRights {
    param(
        [Security.Principal.SecurityIdentifier]$Sid,
        [bool]$Present
    )
    $Nonce = [Guid]::NewGuid().ToString('N')
    $Cfg = Join-Path $env:TEMP ("codex-auditor-rights-" + $Nonce + ".inf")
    $Db = Join-Path $env:TEMP ("codex-auditor-rights-" + $Nonce + ".sdb")
    try {
        & secedit.exe /export /cfg $Cfg /areas user_rights /quiet | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Cfg)) {
            throw "SECEDIT_EXPORT_FAILED"
        }
        $Lines = [Collections.Generic.List[string]](Get-Content -LiteralPath $Cfg)
        $PrivilegeHeader = $Lines.FindIndex([Predicate[string]]{ param($Line) $Line -eq "[Privilege Rights]" })
        if ($PrivilegeHeader -lt 0) {
            $Lines.Add("[Privilege Rights]")
            $PrivilegeHeader = $Lines.Count - 1
        }
        $SidToken = "*" + $Sid.Value
        foreach ($Right in $AuditorDenyLogonRights) {
            $Pattern = "^" + [regex]::Escape($Right) + "\s*="
            $Index = -1
            for ($I = 0; $I -lt $Lines.Count; $I++) {
                if ($Lines[$I] -match $Pattern) { $Index = $I; break }
            }
            $Values = New-Object Collections.Generic.List[string]
            if ($Index -ge 0) {
                $Raw = ($Lines[$Index] -split "=", 2)[1].Trim()
                if ($Raw) {
                    foreach ($Value in $Raw.Split(',')) {
                        $Trimmed = $Value.Trim()
                        if ($Trimmed) { $Values.Add($Trimmed) }
                    }
                }
            }
            if ($Present) {
                if (-not $Values.Contains($SidToken)) { $Values.Add($SidToken) }
            }
            else {
                [void]$Values.Remove($SidToken)
            }
            $Replacement = $Right + " = " + ($Values -join ",")
            if ($Index -ge 0) { $Lines[$Index] = $Replacement }
            else { $Lines.Insert($PrivilegeHeader + 1, $Replacement) }
        }
        $Lines | Set-Content -LiteralPath $Cfg -Encoding Unicode
        & secedit.exe /configure /db $Db /cfg $Cfg /areas user_rights /quiet | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "SECEDIT_CONFIGURE_FAILED" }
    }
    finally {
        Remove-Item -LiteralPath $Cfg -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $Db -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath ($Db + ".jfm") -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-Apply {
    param([Security.SecureString]$AccountPassword)
    if (Test-Path -LiteralPath $ChangeManifestPath -PathType Leaf) {
        $ExistingChangeManifest = [IO.File]::ReadAllText($ChangeManifestPath)
        if (
            $ExistingChangeManifest -ne $ManifestJson -and
            -not (Test-RecognizedLegacyChangeManifest -Text $ExistingChangeManifest)
        ) {
            throw "PROVISIONING_MANIFEST_CONFLICT"
        }
    }
    foreach ($Path in $ManagedPaths) {
        if (-not (Test-Path -LiteralPath $Path)) {
            [void](New-Item -ItemType Directory -Path $Path)
        }
    }
    $User = Get-LocalUser -Name $AccountName -ErrorAction SilentlyContinue
    if ($null -eq $User) {
        if ($null -eq $AccountPassword) { throw "ACCOUNT_PASSWORD_REQUIRED" }
        $User = New-LocalUser -Name $AccountName -Password $AccountPassword -AccountNeverExpires -UserMayNotChangePassword -Description "Restricted decision evidence auditor"
    }
    $AdminMember = Get-LocalGroupMember -Group "Administrators" -ErrorAction Stop | Where-Object { $_.SID -eq $User.SID }
    if ($null -ne $AdminMember) { throw "AUDITOR_PRIVILEGED_GROUP_CONFLICT" }
    Set-AuditorDenyLogonRights -Sid $User.SID -Present $true
    Install-RuntimeFiles
    Write-ProbeTargetManifest -Sid $User.SID
    $Results = @()
    foreach ($Change in $AclChanges) {
        $Results += [ordered]@{ path = $Change.path; result = (Add-ManifestAce -Change $Change -Sid $User.SID) }
    }
    foreach ($LegacyChange in $LegacyAclChanges) {
        $Results += [ordered]@{ path = $LegacyChange.path; result = "PRESERVED_LEGACY_ROOT"; legacy_cleanup = $false }
    }
    $LocalUserSddl = "D:(A;;CC;;;$($User.SID.Value))"
    $Rule = Get-NetFirewallRule -Name $FirewallRuleName -ErrorAction SilentlyContinue
    if ($null -eq $Rule) {
        $Rule = New-NetFirewallRule -Name $FirewallRuleName -DisplayName $FirewallRuleName -Direction Outbound -Action Block -Protocol TCP -RemotePort 4001,4002 -RemoteAddress Any -Profile Any
        $Rule | Set-NetFirewallRule -LocalUser $LocalUserSddl -Enabled True
    }
    Assert-FirewallRuleMatches -Rule $Rule -LocalUserSddl $LocalUserSddl
    Write-ExclusiveManifest
    $Log = [ordered]@{
        schema = "AUDITOR_PROVISIONING_LOG_V1"
        completed_at_utc = [DateTime]::UtcNow.ToString("o")
        script_sha256 = $ScriptHash
        account_sid = $User.SID.Value
        acl_results = $Results
        firewall_rule = $FirewallRuleName
    } | ConvertTo-Json -Depth 6 -Compress
    [IO.File]::AppendAllText("$ProvisioningPath\apply.jsonl", $Log + [Environment]::NewLine)
}

function Get-PartialRollbackManifest {
    param([object]$User)
    $ExistingRule = Get-NetFirewallRule -Name $FirewallRuleName -ErrorAction SilentlyContinue
    if ($null -eq $User -and -not (Test-Path -LiteralPath $ProgramRoot) -and $null -eq $ExistingRule) {
        return [pscustomobject]@{ acl_changes = @() }
    }
    if ($null -eq $User -or $User.Description -ne "Restricted decision evidence auditor") {
        throw "PARTIAL_STATE_UNRECOGNIZED:ACCOUNT"
    }
    if (
        -not (Test-Path -LiteralPath $RuntimeManifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $ProbeTargetManifestPath -PathType Leaf)
    ) {
        throw "PARTIAL_STATE_UNRECOGNIZED:MANIFESTS"
    }
    $RuntimeText = [IO.File]::ReadAllText($RuntimeManifestPath)
    $RuntimeIsLegacy = Test-RecognizedLegacyRuntimeManifest -Text $RuntimeText
    $RuntimeIsCurrent = $true
    try { $RuntimeValue = $RuntimeText | ConvertFrom-Json }
    catch { $RuntimeIsCurrent = $false }
    if ($RuntimeIsCurrent) {
        foreach ($RuntimeFile in $RuntimeFiles) {
            if ([string]$RuntimeValue.files.($RuntimeFile.name) -ne $RuntimeFile.sha256) {
                $RuntimeIsCurrent = $false
                break
            }
        }
    }
    $ProbeText = [IO.File]::ReadAllText($ProbeTargetManifestPath)
    $ProbeIsLegacy = Test-RecognizedLegacyProbeManifest -Text $ProbeText -Sid $User.SID
    $ProbeIsCurrent = $false
    try {
        $ProbeValue = $ProbeText | ConvertFrom-Json
        $ProbeIsCurrent = (
            $ProbeValue.schema -eq "AUDITOR_PROBE_TARGET_MANIFEST_V1" -and
            $ProbeValue.expected_sid -eq $User.SID.Value -and
            (Test-StringSetEqual -Left @($ProbeValue.approved_roots) -Right $ApprovedPaths) -and
            (($ProbeValue.targets | ConvertTo-Json -Depth 5 -Compress) -ceq ($ProbeTargets | ConvertTo-Json -Depth 5 -Compress))
        )
    }
    catch { $ProbeIsCurrent = $false }
    if ((-not $RuntimeIsLegacy -and -not $RuntimeIsCurrent) -or (-not $ProbeIsLegacy -and -not $ProbeIsCurrent)) {
        throw "PARTIAL_STATE_UNRECOGNIZED:MANIFEST_CONTENT"
    }
    return [pscustomobject]@{ acl_changes = @($AclChanges) }
}

function Invoke-Rollback {
    if (-not $ConfirmRollback) { throw "ROLLBACK_CONFIRMATION_REQUIRED" }
    $User = Get-LocalUser -Name $AccountName -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $ChangeManifestPath -PathType Leaf) {
        $AppliedManifest = [IO.File]::ReadAllText($ChangeManifestPath) | ConvertFrom-Json
        if (
            $AppliedManifest.schema -ne "AUDITOR_WINDOWS_PROVISIONING_MANIFEST_V1" -or
            $AppliedManifest.script_sha256 -ne $ScriptHash -or
            $AppliedManifest.account_name -ne $AccountName -or
            $AppliedManifest.firewall_rule.name -ne $FirewallRuleName
        ) {
            throw "PROVISIONING_MANIFEST_MISMATCH"
        }
        $RollbackChanges = @(
            $AppliedManifest.acl_changes |
                Where-Object { $ApprovedPaths -contains [string]$_.path }
        )
    }
    else {
        $AppliedManifest = Get-PartialRollbackManifest -User $User
        $RollbackChanges = @($AppliedManifest.acl_changes)
    }
    if ($null -ne $User) {
        foreach ($Change in $RollbackChanges) {
            [void](Remove-ManifestAce -Change $Change -Sid $User.SID)
        }
        Set-AuditorDenyLogonRights -Sid $User.SID -Present $false
    }
    Get-NetFirewallRule -Name $FirewallRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    if ($null -ne $User) { Remove-LocalUser -Name $AccountName }
    $ResolvedRoot = [IO.Path]::GetFullPath($ProgramRoot).TrimEnd('\')
    if ($ResolvedRoot -ne "C:\ProgramData\CodexAuditorV1") { throw "ROLLBACK_PATH_INVALID" }
    if (Test-Path -LiteralPath $ResolvedRoot) {
        Remove-Item -LiteralPath $ResolvedRoot -Recurse -Force
    }
}

if ($Mode -eq "Review") {
    Write-Output "HUMAN_INFRASTRUCTURE_ACTION_REQUIRED=true"
    Write-Output "SCRIPT_PATH=$PSCommandPath"
    Write-Output "SCRIPT_SHA256=$ScriptHash"
    Write-Output "EXACT_ELEVATED_APPLY_COMMAND=$ApplyCommand"
    Write-Output "EXACT_ELEVATED_ROLLBACK_COMMAND=$RollbackCommand"
    Write-Output "MANIFEST_JSON=$ManifestJson"
    exit 0
}

# ADMIN-CHECK-BEFORE-MUTATION
$isAdministrator = Test-AdministratorToken
if (-not $isAdministrator) {
    Write-Error "ADMINISTRATOR_REQUIRED"
    exit 5
}

if ($Mode -eq "Apply") {
    $ExistingUser = Get-LocalUser -Name $AccountName -ErrorAction SilentlyContinue
    $Password = $null
    if ($null -eq $ExistingUser) {
        $Password = Read-Host -Prompt "Password for new local standard account CodexAuditorV1" -AsSecureString
    }
    if ($PSCmdlet.ShouldProcess($AccountName, "Apply reviewed Auditor isolation manifest")) {
        Invoke-Apply -AccountPassword $Password
    }
    exit 0
}

if ($PSCmdlet.ShouldProcess($AccountName, "Rollback manifest-owned Auditor isolation changes")) {
    Invoke-Rollback
}
