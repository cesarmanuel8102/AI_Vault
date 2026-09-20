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

$ProtectedPaths = @(
    "C:\AI_VAULT\Secrets",
    "C:\Jts",
    "C:\AI_VAULT\state\ibkr_paper_30d\reports\real_codex_invocations.sqlite3",
    "C:\AI_VAULT\state\ibkr_paper_30d\reports\real_codex_invocations.sqlite3-wal",
    "C:\AI_VAULT\state\ibkr_paper_30d\reports\real_codex_invocations.sqlite3-shm",
    "C:\AI_VAULT\state\ibkr_paper_30d\execution.lock",
    "C:\AI_VAULT\ibkr_paper_30d\broker.py",
    "C:\AI_VAULT\ibkr_paper_30d\trader_invocation.py"
)
$ManagedPaths = @($RuntimePath, $ExportPath, $ReportPath, $ProvisioningPath)
$ApprovedPaths = @($ManagedPaths + $ProtectedPaths)

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
    $AclChanges += New-AclChange -Path $Path -Rights "FullControl" -Type "Deny" -Directory (Test-Path -LiteralPath $Path -PathType Container)
}

$ScriptHash = Get-Sha256Hex -LiteralPath $PSCommandPath
$ApplyCommand = "PowerShell.exe -NoProfile -File .\AUDITOR_WINDOWS_PROVISIONING_V1.ps1 -Mode Apply"
$RollbackCommand = "PowerShell.exe -NoProfile -File .\AUDITOR_WINDOWS_PROVISIONING_V1.ps1 -Mode Rollback -ConfirmRollback"
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
        remote_addresses = @("127.0.0.1", "::1")
        account_sid_scope = "RESOLVE_ON_APPLY"
    }
    acl_changes = $AclChanges
    runtime_files = @()
    validation_commands = @(
        "Get-LocalUser -Name CodexAuditorV1",
        "Get-NetFirewallRule -Name CodexAuditorV1-Broker-Loopback-Block",
        "Get-Acl -LiteralPath C:\ProgramData\CodexAuditorV1\runtime",
        "Get-Acl -LiteralPath C:\ProgramData\CodexAuditorV1\exports",
        "Get-Acl -LiteralPath C:\ProgramData\CodexAuditorV1\reports"
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
    if (-not ($ApprovedPaths -contains [string]$Change.path)) {
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
    $Results = @()
    foreach ($Change in $AclChanges) {
        $Results += [ordered]@{ path = $Change.path; result = (Add-ManifestAce -Change $Change -Sid $User.SID) }
    }
    $Rule = Get-NetFirewallRule -Name $FirewallRuleName -ErrorAction SilentlyContinue
    if ($null -eq $Rule) {
        $Rule = New-NetFirewallRule -Name $FirewallRuleName -DisplayName $FirewallRuleName -Direction Outbound -Action Block -Protocol TCP -RemotePort 4001,4002 -RemoteAddress 127.0.0.1,::1 -Profile Any
    }
    $LocalUserSddl = "D:(A;;CC;;;$($User.SID.Value))"
    $Rule | Set-NetFirewallRule -LocalUser $LocalUserSddl -Enabled True
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

function Invoke-Rollback {
    if (-not $ConfirmRollback) { throw "ROLLBACK_CONFIRMATION_REQUIRED" }
    if (-not (Test-Path -LiteralPath $ChangeManifestPath -PathType Leaf)) {
        throw "PROVISIONING_MANIFEST_MISSING"
    }
    $AppliedManifest = [IO.File]::ReadAllText($ChangeManifestPath) | ConvertFrom-Json
    if (
        $AppliedManifest.schema -ne "AUDITOR_WINDOWS_PROVISIONING_MANIFEST_V1" -or
        $AppliedManifest.script_sha256 -ne $ScriptHash -or
        $AppliedManifest.account_name -ne $AccountName -or
        $AppliedManifest.firewall_rule.name -ne $FirewallRuleName
    ) {
        throw "PROVISIONING_MANIFEST_MISMATCH"
    }
    $User = Get-LocalUser -Name $AccountName -ErrorAction SilentlyContinue
    if ($null -ne $User) {
        foreach ($Change in $AppliedManifest.acl_changes) {
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
