#Requires -RunAsAdministrator
param(
    [string]$Root = "C:\AI_VAULT_CANONICAL"
)

$ErrorActionPreference = "Continue"
$logDir = "$Root\tmp_agent\runtime"
$null = New-Item -ItemType Directory -Force -Path $logDir

function Write-Log {
    param([string]$msg)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $msg"
    Write-Host $line
    Add-Content -Path "$logDir\brain_stack_startup.log" -Value $line
}

Write-Log "=== Brain Stack Startup (Agent V2 Mode) ==="

# Step 1: Start 8091
Write-Log "Step 1: Starting Brain 8091..."
$brainProc = Start-Process -FilePath "powershell" `
    -ArgumentList "-ExecutionPolicy", "Bypass", "-File", "$Root\scripts\brain\restart_brain_8091_agent_v2.ps1", "-Root", $Root `
    -WorkingDirectory $Root `
    -PassThru
Write-Log "Brain 8091 start initiated (PID $($brainProc.Id))"

Start-Sleep -Seconds 10

# Step 2: Start 8092
Write-Log "Step 2: Starting Dashboard 8092..."
$dashProc = Start-Process -FilePath "powershell" `
    -ArgumentList "-ExecutionPolicy", "Bypass", "-File", "$Root\scripts\brain\restart_dashboard_8092_agent_v2.ps1", "-Root", $Root, "-SkipZombieWarning" `
    -WorkingDirectory $Root `
    -PassThru
Write-Log "Dashboard 8092 start initiated (PID $($dashProc.Id))"

Start-Sleep -Seconds 5

# Step 3: Verify
Write-Log "Step 3: Verification..."
& "$Root\scripts\brain\probe_agent_v2_live.ps1" -Root $Root
& "$Root\scripts\brain\probe_dashboard_8092_agent_v2.ps1" -Root $Root

Write-Log "=== Stack Startup Complete ==="
