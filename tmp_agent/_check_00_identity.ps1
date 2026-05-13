$base = "C:/AI_VAULT/00_identity"
Write-Host "Exists: $(Test-Path $base)"
$pyfiles = Get-ChildItem $base -Recurse -Filter *.py -ErrorAction SilentlyContinue
Write-Host "TOTAL .py files: $($pyfiles.Count)"
$pyfiles | Select-Object -First 15 | ForEach-Object { Write-Host "  $($_.FullName)" }

Write-Host ""
Write-Host "===== ALL files first 20 (any extension) ====="
Get-ChildItem $base -Recurse -ErrorAction SilentlyContinue | Select-Object -First 20 | ForEach-Object { Write-Host "  $($_.FullName)" }
