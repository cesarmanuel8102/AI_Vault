param([string]$InstallRoot='C:\AI_VAULT_CODEX_BRIDGE',[switch]$Once,[switch]$DryRun,[switch]$Doctor)
if($Doctor -and ($Once -or $DryRun)){throw 'operator proxy execution mode is ambiguous'}
$env:OPERATOR_PROXY_ROOT=$InstallRoot
$reviewerRepo=Join-Path $InstallRoot 'repos\AI_Vault-governed'
if(-not (Test-Path -LiteralPath $reviewerRepo)){throw 'operator proxy reviewer repository missing'}
$reviewerTop=(& git -C $reviewerRepo rev-parse --show-toplevel)
if($LASTEXITCODE -ne 0 -or -not $reviewerTop){throw 'operator proxy reviewer repository invalid'}
$reviewerTop=$reviewerTop.Trim()
if(((& git -C $reviewerTop status --porcelain --untracked-files=all) -join "`n").Trim()){throw 'operator proxy reviewer repository dirty'}
$reviewerRemote=((& git -C $reviewerTop remote get-url origin) -join "`n").Trim()
if($LASTEXITCODE -ne 0 -or $reviewerRemote -notin @('https://github.com/cesarmanuel8102/AI_Vault','https://github.com/cesarmanuel8102/AI_Vault.git','git@github.com:cesarmanuel8102/AI_Vault.git')){throw 'operator proxy reviewer repository remote invalid'}
$env:OPERATOR_PROXY_REPO=$reviewerTop
$builderConfig=$env:OPERATOR_PROXY_BUILDER_CONFIG
if(-not $builderConfig){$builderConfig='C:\AI_VAULT_AGENT_WORKER\config\worker.json'}
if(Test-Path -LiteralPath $builderConfig){
  $builder=(Get-Content -LiteralPath $builderConfig -Raw|ConvertFrom-Json).opencode_model
  if($builder -notmatch '^ollama-cloud/[a-z0-9][a-z0-9.:-]{2,127}$'){throw 'Agent Loop builder model identity invalid'}
  if(-not $env:OPERATOR_PROXY_BUILDER_MODEL){$env:OPERATOR_PROXY_BUILDER_MODEL=$builder}
  if(-not $env:OPERATOR_PROXY_OLLAMA_BUILDER_MODEL){$env:OPERATOR_PROXY_OLLAMA_BUILDER_MODEL=$builder}
}
# The configured OpenCode/Ollama model builds first; bounded alternatives remain available.
if(-not $env:OPERATOR_PROXY_PREFERRED_BUILDER_BACKEND){$env:OPERATOR_PROXY_PREFERRED_BUILDER_BACKEND='opencode_ollama'}
$entry = Join-Path $InstallRoot 'operator_proxy.ts'
$args=@($entry);if($Once){$args+='--once'};if($DryRun){$args+='--dry-run'};if($Doctor){$args+='--doctor'};& (Join-Path $InstallRoot 'node_modules\.bin\tsx.cmd') @args;exit $LASTEXITCODE
