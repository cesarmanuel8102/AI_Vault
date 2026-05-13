param(
  [Parameter(Mandatory=$true)]
  [ValidateNotNullOrEmpty()]
  [string]$Name
)

$root = "C:\AI_VAULT\tmp_agent"
$state = Join-Path $root "state"
if (-not (Test-Path -LiteralPath $state)) { New-Item -ItemType Directory -Force -Path $state | Out-Null }

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$snap = Join-Path $state ("tools_snapshot_{0}_{1}" -f $Name, $ts)
New-Item -ItemType Directory -Force -Path $snap | Out-Null

# copy .py tools
Get-ChildItem -LiteralPath $root -Filter *.py | ForEach-Object {
  Copy-Item -Force -LiteralPath $_.FullName -Destination (Join-Path $snap $_.Name)
}

# write hashes file: "<sha256>  <absolute_path_under_root>"
$hashFile = Join-Path $snap "_hashes.sha256.txt"
$lines = @()
Get-ChildItem -LiteralPath $snap -Filter *.py | ForEach-Object {
  $src = $_.FullName
  $dstAbs = Join-Path $root $_.Name
  $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $src).Hash.ToUpper()
  $lines += "$h  $dstAbs"
}
$lines -join "`r`n" | Set-Content -Encoding UTF8 -LiteralPath $hashFile

Write-Host "OK: snapshot created $snap" -ForegroundColor Green
