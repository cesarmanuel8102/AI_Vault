$ErrorActionPreference = 'Stop'
$before = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/upgrade/settings' -Method GET
Write-Host "BEFORE self_dev_enabled=$($before.self_dev_enabled) require_approval=$($before.self_dev_require_approval) max_risk=$($before.self_dev_max_risk)"
$after = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/upgrade/settings/reload' -Method POST
Write-Host "AFTER  self_dev_enabled=$($after.self_dev_enabled) require_approval=$($after.self_dev_require_approval) max_risk=$($after.self_dev_max_risk)"
