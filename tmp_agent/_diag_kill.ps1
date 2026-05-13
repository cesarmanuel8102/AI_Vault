# Try to elevate or use WMI to terminate
$pid_target = 68628
$proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid_target" -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "Process $pid_target not found via CIM"
    exit 1
}
Write-Host "Owner: $($proc.GetOwner().User) Parent: $($proc.ParentProcessId) Cmd: $($proc.CommandLine.Substring(0,[Math]::Min(200,$proc.CommandLine.Length)))"

# Also check parent
$parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)" -ErrorAction SilentlyContinue
if ($parent) {
    Write-Host "Parent name: $($parent.Name) Cmd: $($parent.CommandLine.Substring(0,[Math]::Min(200,$parent.CommandLine.Length)))"
}

# Try CIM Terminate
$result = Invoke-CimMethod -InputObject $proc -MethodName Terminate
Write-Host "Terminate result: $($result.ReturnValue) (0=success)"
