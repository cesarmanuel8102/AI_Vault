param([string]$Msg, [string]$Sid="r4_test")
$body = @{ message = $Msg; session_id = $Sid } | ConvertTo-Json
try {
    $r = Invoke-RestMethod -Uri http://127.0.0.1:8090/chat -Method POST -Body $body -ContentType "application/json" -TimeoutSec 180
    Write-Host "model=$($r.model_used) route=$($r.route) success=$($r.success)"
    Write-Host "---"
    Write-Host $r.response
} catch {
    Write-Host "ERR: $($_.Exception.Message)"
}
