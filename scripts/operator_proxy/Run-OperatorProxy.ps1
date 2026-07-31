param([string]$InstallRoot='C:\AI_VAULT_CODEX_BRIDGE',[switch]$Once,[switch]$DryRun)
$builderConfig=$env:OPERATOR_PROXY_BUILDER_CONFIG
if(-not $builderConfig){$builderConfig='C:\AI_VAULT_AGENT_WORKER\config\worker.json'}
if(-not $env:OPERATOR_PROXY_BUILDER_MODEL -and (Test-Path -LiteralPath $builderConfig)){
  $builder=(Get-Content -LiteralPath $builderConfig -Raw|ConvertFrom-Json).opencode_model
  if($builder -notmatch '^ollama-cloud/[a-z0-9][a-z0-9.:-]{2,127}$'){throw 'Agent Loop builder model identity invalid'}
  $env:OPERATOR_PROXY_BUILDER_MODEL=$builder
}
$entry = Join-Path $InstallRoot 'operator_proxy.ts'
$args=@($entry);if($Once){$args+='--once'};if($DryRun){$args+='--dry-run'};& (Join-Path $InstallRoot 'node_modules\.bin\tsx.cmd') @args;exit $LASTEXITCODE
