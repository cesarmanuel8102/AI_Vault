$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
Import-Module (Join-Path $root 'scripts\operator_proxy\Repair-OperatorProxy.psm1') -Force
$head=(& git -C $root rev-parse HEAD).Trim()
$tmp=Join-Path $env:TEMP ('operator-proxy-'+[guid]::NewGuid())
$install=Join-Path $tmp 'install'
New-Item $install -ItemType Directory -Force|Out-Null
$old=[Text.Encoding]::UTF8.GetBytes('old-runtime')
[IO.File]::WriteAllBytes((Join-Path $install 'operator_proxy.ts'),$old)
$taskState=Join-Path $tmp 'task-state.txt';[IO.File]::WriteAllText($taskState,'Disabled')
$validateStage={param($stage) if(!(Test-Path (Join-Path $stage 'operator_proxy.ts'))){throw 'staging missing'};New-Item (Join-Path $stage 'node_modules\.bin') -ItemType Directory -Force|Out-Null;[IO.File]::WriteAllText((Join-Path $stage 'node_modules\.bin\tsx.cmd'),'@echo off')}
try {
    Invoke-OperatorProxyInstall -Repo $root -InstallRoot $install -ApprovedCommit $head -ValidateStaging $validateStage -ValidateInstalled {param($p)} | Out-Null
    if([Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes((Join-Path $install 'operator_proxy.ts'))) -eq 'old-runtime'){throw 'install did not replace runtime'}
    try { Invoke-OperatorProxyInstall -Repo $root -InstallRoot $install -ApprovedCommit ('0'*40) -ValidateStaging $validateStage | Out-Null; throw 'bad sha accepted' } catch { if($_.Exception.Message -eq 'bad sha accepted'){throw} }
    [IO.File]::WriteAllBytes((Join-Path $install 'operator_proxy.ts'),$old)
    try { Invoke-OperatorProxyInstall -Repo $root -InstallRoot $install -ApprovedCommit $head -ValidateStaging $validateStage -ValidateInstalled {param($p) throw 'post-install validation failure'} | Out-Null; throw 'post failure accepted' } catch { if($_.Exception.Message -eq 'post failure accepted'){throw} }
    if(-not [Linq.Enumerable]::SequenceEqual([byte[]]$old,[IO.File]::ReadAllBytes((Join-Path $install 'operator_proxy.ts')))){throw 'rollback bytes differ'}
    if([IO.File]::ReadAllText($taskState) -ne 'Disabled'){throw 'task state changed'}
    'OPERATOR_PROXY_TRANSACTION_PASS'
} finally { if(Test-Path $tmp){Remove-Item $tmp -Recurse -Force} }
