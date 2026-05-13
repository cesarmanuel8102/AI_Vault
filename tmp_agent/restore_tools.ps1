param(
  [Parameter(Mandatory=$true)]
  [ValidateNotNullOrEmpty()]
  [string]$SnapshotDir,
  [switch]$NoSmoke
)

$root = "C:\AI_VAULT\tmp_agent"
if (-not (Test-Path -LiteralPath $SnapshotDir)) { throw "SNAPSHOT_NOT_FOUND: $SnapshotDir" }

$hashFile = Join-Path $SnapshotDir "_hashes.sha256.txt"
if (-not (Test-Path -LiteralPath $hashFile)) { throw "HASH_FILE_NOT_FOUND: $hashFile" }

# 1) Verifica hashes del snapshot (self-consistency)
$lines = Get-Content -Raw -LiteralPath $hashFile -Encoding UTF8 -ErrorAction Stop
$expected = @{}
($lines -split "`r?`n") | ForEach-Object {
  if ($_ -match '^\s*([0-9A-Fa-f]{64})\s\s+(.*)\s*$') {
    $expected[$matches[2]] = $matches[1].ToUpper()
  }
}

foreach ($p in $expected.Keys) {
  # $p is an absolute path under $root (captured when snapshot was created).
  # Validate the corresponding file INSIDE the snapshot, not the current root.
  if ($p -notlike "$root*") { throw "SNAPSHOT_PATH_OUTSIDE_ROOT: $p" }

  $rel = $p.Substring($root.Length).TrimStart("\","/")
  $src = Join-Path $SnapshotDir $rel

  if (-not (Test-Path -LiteralPath $src)) { throw "SNAPSHOT_FILE_MISSING_IN_SNAPSHOT: $src" }
  $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $src).Hash.ToUpper()
  if ($h -ne $expected[$p]) { throw "SNAPSHOT_HASH_MISMATCH_IN_SNAPSHOT: $src expected=$($expected[$p]) got=$h" }
}

# 2) Restore: copia solo los .py del snapshot al root
Get-ChildItem -LiteralPath $SnapshotDir -Filter *.py | ForEach-Object {
  $src = $_.FullName
  $dst = Join-Path $root $_.Name
  Copy-Item -Force -LiteralPath $src -Destination $dst
  Write-Host "RESTORED:" $_.Name
}

# 3) Smoke rápido (si existe contrato default)
$repo = "C:\AI_VAULT\workspace\brainlab"
$contract = Join-Path $repo "brainlab\contracts\financial_motor_contract_v1.json"
if (-not $NoSmoke) {
  if (Test-Path -LiteralPath $contract) {
    Write-Host "`nSMOKE:" -ForegroundColor Cyan
    python (Join-Path $root "dev_loop.py") --mode=smoke --contract="$contract" | Out-Host
  }
}
Write-Host "`nOK: restore complete from $SnapshotDir" -ForegroundColor Green


