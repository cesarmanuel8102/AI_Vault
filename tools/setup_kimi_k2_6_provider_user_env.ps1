[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [ValidateSet("Status", "Process", "User", "RemoveUser")]
    [string]$Mode = "Status",
    [ValidatePattern('^[A-Za-z0-9_.:-]+$')]
    [string]$ModelTag = "kimi-k2.6:cloud"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-EnvInfo {
    param([string]$Name)
    $processValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    $userValue = [Environment]::GetEnvironmentVariable($Name, "User")
    $machineValue = [Environment]::GetEnvironmentVariable($Name, "Machine")
    $value = $processValue
    $scope = "Process"
    if ([string]::IsNullOrWhiteSpace($value)) { $value = $userValue; $scope = "User" }
    if ([string]::IsNullOrWhiteSpace($value)) { $value = $machineValue; $scope = "Machine" }
    if ([string]::IsNullOrWhiteSpace($value)) { $scope = "Unknown" }
    [ordered]@{
        name = $Name
        present = -not [string]::IsNullOrWhiteSpace($value)
        length = if ($value) { $value.Length } else { 0 }
        source_scope = $scope
        value_redacted = $true
    }
}

function Write-Status {
    $vars = @("KIMI_OLLAMA_MODEL", "KIMI_API_KEY", "MOONSHOT_API_KEY", "KIMI_BASE_URL", "MOONSHOT_BASE_URL")
    $report = [ordered]@{
        status = "OK"
        mode = "Status"
        variables = @($vars | ForEach-Object { Get-EnvInfo $_ })
        secrets_exposed = $false
        env_file_written = $false
    }
    $report | ConvertTo-Json -Depth 5
}

switch ($Mode) {
    "Status" {
        Write-Status
    }
    "Process" {
        $env:KIMI_OLLAMA_MODEL = $ModelTag
        [ordered]@{
            status = "PROCESS_ENV_SET"
            variable = "KIMI_OLLAMA_MODEL"
            model_tag = $ModelTag
            scope = "Process"
            secrets_exposed = $false
            env_file_written = $false
        } | ConvertTo-Json -Depth 4
    }
    "User" {
        $confirm = Read-Host "Set KIMI_OLLAMA_MODEL in Windows User environment to '$ModelTag'? Type YES to continue"
        if ($confirm -ne "YES") { throw "User environment update cancelled" }
        [Environment]::SetEnvironmentVariable("KIMI_OLLAMA_MODEL", $ModelTag, "User")
        [ordered]@{
            status = "USER_ENV_SET"
            variable = "KIMI_OLLAMA_MODEL"
            model_tag = $ModelTag
            scope = "User"
            restart_required = "Open a new terminal and restart Brain 8091"
            secrets_exposed = $false
            env_file_written = $false
        } | ConvertTo-Json -Depth 4
    }
    "RemoveUser" {
        $confirm = Read-Host "Remove KIMI_OLLAMA_MODEL from Windows User environment? Type YES to continue"
        if ($confirm -ne "YES") { throw "User environment removal cancelled" }
        [Environment]::SetEnvironmentVariable("KIMI_OLLAMA_MODEL", $null, "User")
        [ordered]@{
            status = "USER_ENV_REMOVED"
            variable = "KIMI_OLLAMA_MODEL"
            scope = "User"
            restart_required = "Open a new terminal and restart Brain 8091"
            secrets_exposed = $false
            env_file_written = $false
        } | ConvertTo-Json -Depth 4
    }
}
