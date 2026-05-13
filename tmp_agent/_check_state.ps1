$p = Get-Content C:/AI_VAULT/tmp_agent/state/proposed_patches/ce_prop_20260504_133441.json -Raw | ConvertFrom-Json
Write-Host "status        : $($p.status)"
Write-Host "applied_at    : $($p.applied_at)"
Write-Host "gate_result   : $($p.health_gate_result)"
Write-Host "backups count : $($p.backups.Count)"
Write-Host ""
Write-Host "--- Brain proc ---"
$bp = Get-Process python -ErrorAction SilentlyContinue
foreach ($x in $bp) {
  $age = (New-TimeSpan -Start $x.StartTime -End (Get-Date)).TotalSeconds
  Write-Host ("  PID={0} startedSecAgo={1:N0}" -f $x.Id, $age)
}
Write-Host ""
Write-Host "--- Health probe ---"
try {
  $r = Invoke-RestMethod -Uri http://127.0.0.1:8090/health -TimeoutSec 5
  Write-Host "  healthy=$($r.status) safe_mode=$($r.safe_mode)"
} catch {
  Write-Host "  DOWN: $($_.Exception.Message)"
}
