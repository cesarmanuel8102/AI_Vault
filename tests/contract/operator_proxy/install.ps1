$ErrorActionPreference='Stop'
function Get-ContractPathIdentity {
    param([Parameter(Mandatory=$true)][string]$Path)
    $resolved=(Resolve-Path -LiteralPath $Path).Path
    $full=[IO.Path]::GetFullPath($resolved)
    $root=[IO.Path]::GetPathRoot($full)
    if($full.Length -gt $root.Length){$full=$full.TrimEnd([IO.Path]::DirectorySeparatorChar,[IO.Path]::AltDirectorySeparatorChar)}
    return $full
}
function Test-SameContractPath {
    param([Parameter(Mandatory=$true)][string]$Left,[Parameter(Mandatory=$true)][string]$Right)
    return (Get-ContractPathIdentity $Left).Equals((Get-ContractPathIdentity $Right),[StringComparison]::OrdinalIgnoreCase)
}
$root=(Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
Import-Module (Join-Path $root 'scripts\operator_proxy\Repair-OperatorProxy.psm1') -Force
$tmp=Join-Path $env:TEMP ('operator-proxy-'+[guid]::NewGuid())
$driveRoot=[IO.Path]::GetPathRoot($tmp)
$rootChild=Join-Path $driveRoot 'AI_VAULT_OPERATOR_PROXY_INSTALL_ROOT_TEST'
if((Get-OperatorProxyTransactionParent $rootChild) -ne $driveRoot){throw 'drive-root transaction parent was not normalized'}
$foreignCwd=Join-Path $env:TEMP ('operator-proxy-cwd-'+[guid]::NewGuid());New-Item $foreignCwd -ItemType Directory|Out-Null
Push-Location $foreignCwd
try {
    if((Resolve-TrustedOperatorProxyPath $driveRoot -MustExist) -ne $driveRoot){throw 'drive root became drive-relative during trusted resolution'}
} finally {
    Pop-Location
    Remove-Item -LiteralPath $foreignCwd -Recurse -Force
}
$synthetic=Join-Path $tmp 'synthetic-repo';New-Item $synthetic -ItemType Directory -Force|Out-Null
New-Item (Join-Path $synthetic 'scripts') -ItemType Directory|Out-Null
Copy-Item -LiteralPath (Join-Path $root 'scripts\operator_proxy') -Destination (Join-Path $synthetic 'scripts\operator_proxy') -Recurse
& git -C $synthetic init -q; & git -C $synthetic config user.email 'contract@example.invalid'; & git -C $synthetic config user.name 'Contract'; & git -C $synthetic remote add origin 'https://github.com/cesarmanuel8102/AI_Vault.git'; & git -C $synthetic add scripts/operator_proxy; & git -C $synthetic commit -qm 'fixture'
$syntheticHead=(& git -C $synthetic rev-parse HEAD).Trim()
$install=Join-Path $tmp 'install'
New-Item $install -ItemType Directory -Force|Out-Null
$old=[Text.Encoding]::UTF8.GetBytes('old-runtime')
[IO.File]::WriteAllBytes((Join-Path $install 'operator_proxy.ts'),$old)
$taskState=Join-Path $tmp 'task-state.txt';[IO.File]::WriteAllText($taskState,'Disabled')
$validateStage={param($stage) foreach($required in @('operator_proxy.ts','external_effect_guard.ts','redaction.ts','review_contract.ts')){if(!(Test-Path (Join-Path $stage $required))){throw "staging missing $required"}};New-Item (Join-Path $stage 'node_modules\.bin') -ItemType Directory -Force|Out-Null;[IO.File]::WriteAllText((Join-Path $stage 'node_modules\.bin\tsx.cmd'),'@echo off')}
try {
    Invoke-OperatorProxyInstall -Repo $synthetic -InstallRoot $install -ApprovedCommit $syntheticHead -ValidateStaging $validateStage -ValidateInstalled {param($p)} | Out-Null
    if([Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes((Join-Path $install 'operator_proxy.ts'))) -eq 'old-runtime'){throw 'install did not replace runtime'}
    if(& git -C $synthetic status --porcelain --untracked-files=all){throw 'install dirtied source repository'}
    if(Get-ChildItem $synthetic -Force -Filter '.operator-proxy-*'){throw 'transaction artifact created inside source repository'}
    $backupRoot=Join-Path $tmp 'AI_VAULT_OPERATOR_PROXY_BACKUPS'
    if(@(Get-ChildItem $backupRoot -Directory -Filter 'operator-proxy-backup-*').Count -ne 1){throw 'backup not isolated under transaction backup root'}
    $capturedArgs=Join-Path $tmp 'runner-args.txt'
    $shim="@echo off`r`n> `"$capturedArgs`" echo %~1`r`n>> `"$capturedArgs`" echo %~2`r`n>> `"$capturedArgs`" echo %~3`r`nexit /b 0`r`n"
    [IO.File]::WriteAllText((Join-Path $install 'node_modules\.bin\tsx.cmd'),$shim,[Text.Encoding]::ASCII)
    $foreignCwd=Join-Path $tmp 'foreign-cwd';New-Item $foreignCwd -ItemType Directory|Out-Null
    $runner=(Join-Path $install 'Run-OperatorProxy.ps1').Replace("'","''")
    $escapedInstall=$install.Replace("'","''")
    $escapedCwd=$foreignCwd.Replace("'","''")
    $childCommand="Set-Location '$escapedCwd'; & '$runner' -InstallRoot '$escapedInstall' -Once -DryRun"
    $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($childCommand))
    $shell=(Get-Process -Id $PID).Path
    & $shell -NoProfile -NonInteractive -EncodedCommand $encoded
    $runnerExit=$LASTEXITCODE
    if($runnerExit -ne 0){throw "runner failed from unrelated cwd: $runnerExit"}
    $actualArgs=[IO.File]::ReadAllLines($capturedArgs)|ForEach-Object{$_.Trim()}
    $expectedArgs=@((Join-Path $install 'operator_proxy.ts'),'--once','--dry-run')
    if((Compare-Object $expectedArgs $actualArgs -SyncWindow 0)){throw 'runner did not use absolute install entrypoint'}
    try { Invoke-OperatorProxyInstall -Repo $synthetic -InstallRoot $install -ApprovedCommit ('0'*40) -ValidateStaging $validateStage | Out-Null; throw 'bad sha accepted' } catch { if($_.Exception.Message -eq 'bad sha accepted'){throw} }
    [IO.File]::WriteAllBytes((Join-Path $install 'operator_proxy.ts'),$old)
    try { Invoke-OperatorProxyInstall -Repo $synthetic -InstallRoot $install -ApprovedCommit $syntheticHead -ValidateStaging $validateStage -ValidateInstalled {param($p) throw 'post-install validation failure'} | Out-Null; throw 'post failure accepted' } catch { if($_.Exception.Message -eq 'post failure accepted'){throw} }
    if(-not [Linq.Enumerable]::SequenceEqual([byte[]]$old,[IO.File]::ReadAllBytes((Join-Path $install 'operator_proxy.ts')))){throw 'rollback bytes differ'}
    if([IO.File]::ReadAllText($taskState) -ne 'Disabled'){throw 'task state changed'}

    # Synthetic repositories exercise physical/Git identity without touching the canonical checkout.
    $verified=Assert-TrustedOperatorProxyRepository $synthetic $syntheticHead
    if(-not (Test-SameContractPath $verified.Repo $synthetic)){throw 'legitimate repository rejected'}
    foreach($equivalent in @($synthetic.ToUpperInvariant(),$synthetic.Replace('\','/'),($synthetic+[IO.Path]::DirectorySeparatorChar))){if(-not (Test-SameContractPath $verified.Repo $equivalent)){throw "equivalent path identity rejected: $equivalent"}}
    $unexpected=Join-Path $synthetic 'scripts\operator_proxy\unexpected.txt';[IO.File]::WriteAllText($unexpected,'unexpected')
    try{Assert-TrustedOperatorProxyRepository $synthetic $syntheticHead|Out-Null;throw 'dirty source accepted'}catch{if($_.Exception.Message -eq 'dirty source accepted'){throw}}finally{Remove-Item -LiteralPath $unexpected}
    try{Assert-TrustedOperatorProxyRepository $synthetic ('0'*40)|Out-Null;throw 'wrong HEAD accepted'}catch{if($_.Exception.Message -eq 'wrong HEAD accepted'){throw}}
    & git -C $synthetic remote set-url origin 'https://github.com/other/AI_Vault.git'
    try{Assert-TrustedOperatorProxyRepository $synthetic $syntheticHead|Out-Null;throw 'wrong remote accepted'}catch{if($_.Exception.Message -eq 'wrong remote accepted'){throw}}
    & git -C $synthetic remote set-url origin 'https://github.com/cesarmanuel8102/AI_Vault.git'
    try{Assert-TrustedOperatorProxyRepository (Join-Path $synthetic 'scripts') $syntheticHead|Out-Null;throw 'nested path accepted'}catch{if($_.Exception.Message -eq 'nested path accepted'){throw}}
    foreach($bad in @('relative\path',(Join-Path $tmp 'x\..\y'),(Join-Path $tmp 'wild*'))){try{Resolve-TrustedOperatorProxyPath $bad|Out-Null;throw "unsafe path accepted: $bad"}catch{if($_.Exception.Message -like 'unsafe path accepted*'){throw}}}

    $aliasTarget=Join-Path $tmp 'alias-target';New-Item $aliasTarget -ItemType Directory|Out-Null
    $stageAlias=Join-Path $tmp 'stage-reparse';& cmd.exe /d /c "mklink /J `"$stageAlias`" `"$aliasTarget`"" | Out-Null;if($LASTEXITCODE -ne 0){throw 'stage junction fixture failed'}
    try{Assert-NoReparsePoint $stageAlias;throw 'stage reparse accepted'}catch{if($_.Exception.Message -eq 'stage reparse accepted'){throw}}
    & cmd.exe /d /c "rmdir `"$stageAlias`"" | Out-Null

    $canonicalAlias=Join-Path $tmp 'canonical-alias';& cmd.exe /d /c "mklink /J `"$canonicalAlias`" `"C:\AI_VAULT_CANONICAL`"" | Out-Null;if($LASTEXITCODE -ne 0){throw 'canonical junction fixture failed'}
    try{Assert-SafeInstallRoot $canonicalAlias $synthetic|Out-Null;throw 'canonical alias accepted'}catch{if($_.Exception.Message -eq 'canonical alias accepted'){throw}}
    & cmd.exe /d /c "rmdir `"$canonicalAlias`"" | Out-Null

    $source=Join-Path $synthetic 'scripts\operator_proxy';$realSource=Join-Path $synthetic 'scripts\operator_proxy-real';Move-Item -LiteralPath $source -Destination $realSource
    & cmd.exe /d /c "mklink /J `"$source`" `"$realSource`"" | Out-Null;if($LASTEXITCODE -ne 0){throw 'source junction fixture failed'}
    try{Assert-TrustedOperatorProxyRepository $synthetic $syntheticHead|Out-Null;throw 'source reparse accepted'}catch{if($_.Exception.Message -eq 'source reparse accepted'){throw}}
    & cmd.exe /d /c "rmdir `"$source`"" | Out-Null;Move-Item -LiteralPath $realSource -Destination $source

    $syntheticInstall=Join-Path $tmp 'synthetic-install';New-Item $syntheticInstall -ItemType Directory|Out-Null
    [IO.File]::WriteAllBytes((Join-Path $syntheticInstall 'operator_proxy.ts'),$old)
    $changeRemote={param($stagePath) New-Item (Join-Path $stagePath 'node_modules\.bin') -ItemType Directory -Force|Out-Null;[IO.File]::WriteAllText((Join-Path $stagePath 'node_modules\.bin\tsx.cmd'),'@echo off');& git -C $synthetic remote set-url origin 'https://github.com/other/AI_Vault.git'}
    try{Invoke-OperatorProxyInstall -Repo $synthetic -InstallRoot $syntheticInstall -ApprovedCommit $syntheticHead -ValidateStaging $changeRemote|Out-Null;throw 'TOCTOU remote change accepted'}catch{if($_.Exception.Message -eq 'TOCTOU remote change accepted'){throw}}finally{& git -C $synthetic remote set-url origin 'https://github.com/cesarmanuel8102/AI_Vault.git'}
    if(-not [Linq.Enumerable]::SequenceEqual([byte[]]$old,[IO.File]::ReadAllBytes((Join-Path $syntheticInstall 'operator_proxy.ts')))){throw 'pre-install TOCTOU changed install bytes'}
    $postIdentityChange={param($installedPath) & git -C $synthetic remote set-url origin 'https://github.com/other/AI_Vault.git'}
    try{Invoke-OperatorProxyInstall -Repo $synthetic -InstallRoot $syntheticInstall -ApprovedCommit $syntheticHead -ValidateStaging $validateStage -ValidateInstalled $postIdentityChange|Out-Null;throw 'post-install identity change accepted'}catch{if($_.Exception.Message -eq 'post-install identity change accepted'){throw}}finally{& git -C $synthetic remote set-url origin 'https://github.com/cesarmanuel8102/AI_Vault.git'}
    if(-not [Linq.Enumerable]::SequenceEqual([byte[]]$old,[IO.File]::ReadAllBytes((Join-Path $syntheticInstall 'operator_proxy.ts')))){throw 'TOCTOU rollback bytes differ'}
    'OPERATOR_PROXY_TRANSACTION_PASS'
} finally { if(Test-Path $tmp){Remove-Item $tmp -Recurse -Force} }
