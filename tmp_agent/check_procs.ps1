Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = $_
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
    Write-Host "PID=$($proc.Id) WS=$([math]::Round($proc.WorkingSet64/1MB,0))MB START=$($proc.StartTime) CMD=$cmd"
}
