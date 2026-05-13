# Two-turn test: ask a question, then send a correction
$sid = "r4_correction_test_" + (Get-Random)

# Turn 1: ask something
Write-Host "=== TURN 1: ask ==="
$b1 = @{ message = "que es 2 + 2"; session_id = $sid } | ConvertTo-Json
$r1 = Invoke-RestMethod -Uri http://127.0.0.1:8090/chat -Method POST -Body $b1 -ContentType "application/json" -TimeoutSec 90
Write-Host "Reply: $($r1.response)"

Start-Sleep 2

# Turn 2: send a correction
Write-Host "`n=== TURN 2: correction ==="
$b2 = @{ message = "no, eso es incorrecto, el resultado real es 5"; session_id = $sid } | ConvertTo-Json
$r2 = Invoke-RestMethod -Uri http://127.0.0.1:8090/chat -Method POST -Body $b2 -ContentType "application/json" -TimeoutSec 90
Write-Host "Reply: $($r2.response)"

Start-Sleep 2

# Verify it landed in semantic memory
Write-Host "`n=== Semantic memory search for 'correction' ==="
$bs = @{ message = "/sem buscar correction"; session_id = $sid } | ConvertTo-Json
try {
    $rs = Invoke-RestMethod -Uri http://127.0.0.1:8090/chat -Method POST -Body $bs -ContentType "application/json" -TimeoutSec 60
    Write-Host $rs.response
} catch {
    Write-Host "search err: $($_.Exception.Message)"
}
