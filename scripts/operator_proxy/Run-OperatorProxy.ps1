param([string]$InstallRoot='C:\AI_VAULT_CODEX_BRIDGE',[switch]$Once,[switch]$DryRun)
$entry = Join-Path $InstallRoot 'operator_proxy.ts'
$args=@($entry);if($Once){$args+='--once'};if($DryRun){$args+='--dry-run'};& (Join-Path $InstallRoot 'node_modules\.bin\tsx.cmd') @args;exit $LASTEXITCODE
