$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:8090"
$testFile = "C:/AI_VAULT/tmp_agent/brain_v9/agent/_c_test_target.py"

Write-Host "=== C-Sprint Mutation Test v2 ===" -ForegroundColor Yellow

# Verify test file exists and is valid Python
Write-Host "Checking test file..."
$content = Get-Content $testFile -Raw
Write-Host $content
python -c "import ast; ast.parse(open('$testFile', encoding='utf-8').read()); print('File is valid Python')"

# Apply mutation
$body = @{
    file_path = $testFile
    edit_type = "replace"
    target = "result = 1 + 1  # OLD: this will be mutated"
    content = "result = 42  # MUTATED"
    description = "test mutation"
    allow_critical = $false
    monitor = $false
} | ConvertTo-Json

Write-Host ""
Write-Host "Sending mutation..." -ForegroundColor Cyan
$resp = Invoke-RestMethod -Uri "$base/brain/mutations/test_apply" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 30
Write-Host ("success={0} mutation_id={1}" -f $resp.success, $resp.mutation_id) -ForegroundColor Magenta
if ($resp.error) { Write-Host ("error={0}" -f $resp.error) -ForegroundColor Red }

# Check file after
Write-Host ""
Write-Host "File after mutation:" -ForegroundColor Cyan
Get-Content $testFile -Raw

# Check mutations list
Write-Host ""
Write-Host "Mutations:" -ForegroundColor Cyan
(Invoke-RestMethod -Uri "$base/brain/mutations" -TimeoutSec 5).mutations | ForEach-Object {
    Write-Host ("  {0}: {1}" -f $_.id, $_.description)
}

# Counters
Write-Host ""
Write-Host "Counters:" -ForegroundColor Cyan
$c = (Invoke-RestMethod -Uri "$base/brain/validators" -TimeoutSec 5).live_module_counters
$c.PSObject.Properties | Where-Object { $_.Name -match "mutation" } | ForEach-Object {
    Write-Host ("  {0} = {1}" -f $_.Name, $_.Value)
}
