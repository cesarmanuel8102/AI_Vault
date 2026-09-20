#Requires -Version 5.1
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Review", "Apply", "Rollback")]
    [string]$Mode = "Review",
    [switch]$ConfirmRollback
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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
    $ProbeTargetManifestPath
)
$PredecessorScriptHashes = @(
    "899d262124bbf24e0dbd4661b8df41f93aeb6993dacfe9a200264ad2e9ed6eb7",
    "ba6ab5e885c6da54141cfaef85a59ae7e9e6cb2102b23607ae91fdaadfbb057c"
)
$PredecessorRuntimeHashes = @{
    "CODEX_DECISION_AUDITOR_V1.ps1" = "660cec2f87052edf68ed84e001516e0be7694ed0794337ba4252545d41c71bf4"
    "AUDITOR_DENIAL_PROBE_V1.ps1" = "26d4dc93cdf45ceeae3f40f39248edfe00f749072c4d1b36bd04971bb4a8dbf9"
}
$LiveStateRoot = "C:\AI_VAULT\state\ibkr_paper_30d"
$LegacyEphemeralPaths = @(
    "$LiveStateRoot\reports\real_codex_invocations.sqlite3",
    "$LiveStateRoot\reports\real_codex_invocations.sqlite3-wal",
    "$LiveStateRoot\reports\real_codex_invocations.sqlite3-shm",
    "$LiveStateRoot\execution.lock"
)

$ProtectedPaths = @(
    "C:\AI_VAULT\Secrets",
    "C:\Jts",
    $LiveStateRoot,
    "C:\AI_VAULT\ibkr_paper_30d\broker.py",
    "C:\AI_VAULT\ibkr_paper_30d\trader_invocation.py"
)
$ManagedPaths = @($RuntimePath, $ExportPath, $ReportPath, $ProvisioningPath)
$ApprovedPaths = @($ManagedPaths + $ProtectedPaths)
$LegacyApprovedPaths = @($ManagedPaths + @(
    "C:\AI_VAULT\Secrets",
    "C:\Jts",
    $LegacyEphemeralPaths,
    "C:\AI_VAULT\ibkr_paper_30d\broker.py",
    "C:\AI_VAULT\ibkr_paper_30d\trader_invocation.py"
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
    $AclChanges += New-AclChange -Path $Path -Rights "FullControl" -Type "Deny" -Directory ($Path -eq $LiveStateRoot -or (Test-Path -LiteralPath $Path -PathType Container))
}
$LegacyAclChanges = @()
foreach ($Path in $LegacyEphemeralPaths) {
    $LegacyAclChanges += New-AclChange -Path $Path -Rights "FullControl" -Type "Deny" -Directory $false
}

$ScriptHash = Get-Sha256Hex -LiteralPath $PSCommandPath
$ApplyCommand = "PowerShell.exe -NoProfile -File .\AUDITOR_WINDOWS_PROVISIONING_V1.ps1 -Mode Apply"
$RollbackCommand = "PowerShell.exe -NoProfile -File .\AUDITOR_WINDOWS_PROVISIONING_V1.ps1 -Mode Rollback -ConfirmRollback"
$ProbeTargets = [ordered]@{
    SECRETS_READ = "C:\AI_VAULT\Secrets"
    IBKR_SECRET_READ = "C:\Jts"
    EXECUTION_LOCK_ACCESS = "C:\AI_VAULT\state\ibkr_paper_30d\execution.lock"
    LIVE_DATABASE_MUTATION = "C:\AI_VAULT\state\ibkr_paper_30d\reports\real_codex_invocations.sqlite3"
    BROKER_WRITE_PATH_ACCESS = "C:\AI_VAULT\ibkr_paper_30d\broker.py"
    TRADER_CONTEXT_ACCESS = "C:\AI_VAULT\ibkr_paper_30d\trader_invocation.py"
    AUDIT_INPUT_MUTATION = $ExportPath
    IMMUTABLE_EXPORT_READ = $ExportPath
    AUDITOR_REPORT_WRITE = $ReportPath
}
$ProbeTargets[("SM" + "TP_SECRET_READ")] = "C:\AI_VAULT\Secrets\email_alerts.env"
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
            "CURRENT_COMPLETE_RERUN"
        )
        rollback_supported_states = @(
            "FIRST_FIREWALL_FAILURE_PARTIAL",
            "SECOND_REPLACE_FAILURE_PARTIAL",
            "CURRENT_COMPLETE_RERUN"
        )
        change_manifest_may_be_missing = $true
        repair_probe_manifest = $true
        upgrade_runtime_files = $true
        reject_unrecognized_state = $true
    }
    runtime_files = $RuntimeFiles
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

function Test-RecognizedLegacyProbeManifest {
    param(
        [string]$Text,
        [Security.Principal.SecurityIdentifier]$Sid
    )
    try { $Legacy = $Text | ConvertFrom-Json }
    catch { return $false }
    if (
        $Legacy.schema -ne "AUDITOR_PROBE_TARGET_MANIFEST_V1" -or
        $Legacy.expected_sid -ne $Sid.Value -or
        -not (Test-StringSetEqual -Left @($Legacy.approved_roots) -Right $LegacyApprovedPaths)
    ) { return $false }
    $ExpectedTargets = $ProbeTargets | ConvertTo-Json -Depth 5 -Compress
    $ActualTargets = $Legacy.targets | ConvertTo-Json -Depth 5 -Compress
    return $ActualTargets -ceq $ExpectedTargets
}

function Write-ExclusiveManifest {
    if (Test-Path -LiteralPath $ChangeManifestPath) {
        $Existing = [IO.File]::ReadAllText($ChangeManifestPath)
        if ($Existing -ne $ManifestJson) {
            throw "PROVISIONING_MANIFEST_CONFLICT"
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

function Invoke-Apply {
    param([Security.SecureString]$AccountPassword)
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
    Install-RuntimeFiles
    Write-ProbeTargetManifest -Sid $User.SID
    $Results = @()
    foreach ($Change in $AclChanges) {
        $Results += [ordered]@{ path = $Change.path; result = (Add-ManifestAce -Change $Change -Sid $User.SID) }
    }
    foreach ($LegacyChange in $LegacyAclChanges) {
        $Results += [ordered]@{ path = $LegacyChange.path; result = (Remove-ManifestAce -Change $LegacyChange -Sid $User.SID); legacy_cleanup = $true }
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
    return [pscustomobject]@{ acl_changes = @($AclChanges + $LegacyAclChanges) }
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
        $RollbackChanges = @($AppliedManifest.acl_changes) + @($LegacyAclChanges)
    }
    else {
        $AppliedManifest = Get-PartialRollbackManifest -User $User
        $RollbackChanges = @($AppliedManifest.acl_changes)
    }
    if ($null -ne $User) {
        foreach ($Change in $RollbackChanges) {
            [void](Remove-ManifestAce -Change $Change -Sid $User.SID)
        }
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
