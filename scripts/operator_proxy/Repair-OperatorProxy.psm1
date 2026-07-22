function Invoke-CheckedNative {
    param([Parameter(Mandatory=$true)][string]$FilePath,[Parameter(Mandatory=$true)][string[]]$Arguments,[Parameter(Mandatory=$true)][string]$Identity)
    & $FilePath @Arguments
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "$Identity failed with exit code $code" }
}

function Invoke-OperatorProxyInstall {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Repo,
        [Parameter(Mandatory=$true)][string]$InstallRoot,
        [Parameter(Mandatory=$true)][string]$ApprovedCommit,
        [scriptblock]$ValidateStaging,
        [scriptblock]$ValidateInstalled
    )
    $ErrorActionPreference = 'Stop'
    $head = (& git -C $Repo rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -ne $ApprovedCommit) { throw 'control-plane commit mismatch' }
    if ($Repo -like 'C:\AI_VAULT_CANONICAL*' -or $InstallRoot -like 'C:\AI_VAULT_CANONICAL*') { throw 'canonical path denied' }

    $source = Join-Path $Repo 'scripts\operator_proxy'
    $parent = Split-Path $InstallRoot -Parent
    if (-not $parent) { $parent = $env:TEMP }
    New-Item $parent -ItemType Directory -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMddTHHmmssfffZ'
    $stage = Join-Path $parent ".operator-proxy-stage-$stamp"
    $backup = Join-Path $parent ".operator-proxy-backup-$stamp"
    $managed = @('schemas','action_executor.ts','codex_builder.ts','codex_reviewer.ts','decision_ledger.ts','evidence_collector.ts','github_bus.ts','operator_proxy.ts','policy_engine.ts','risk_classifier.ts','single_instance_lock.ts','state_machine.ts','types.ts','package.json','package-lock.json','tsconfig.json','Run-OperatorProxy.ps1')
    $installed = $false
    try {
        New-Item $stage -ItemType Directory | Out-Null
        foreach ($name in $managed) { Copy-Item (Join-Path $source $name) (Join-Path $stage $name) -Recurse -Force }
        if ($ValidateStaging) { & $ValidateStaging $stage }
        else {
            Push-Location $stage
            try {
                Invoke-CheckedNative 'npm.cmd' @('ci','--ignore-scripts') 'npm ci'
                Invoke-CheckedNative (Join-Path $stage 'node_modules\.bin\tsc.cmd') @('--noEmit','-p',(Join-Path $stage 'tsconfig.json')) 'typecheck'
            } finally { Pop-Location }
        }
        if(-not (Test-Path (Join-Path $stage 'node_modules\.bin\tsx.cmd'))){throw 'validated staging dependencies missing'}
        $managed += 'node_modules'

        New-Item $backup -ItemType Directory | Out-Null
        if (Test-Path $InstallRoot) {
            foreach ($name in $managed) { $p=Join-Path $InstallRoot $name; if(Test-Path $p){Copy-Item $p (Join-Path $backup $name) -Recurse -Force} }
        } else { New-Item $InstallRoot -ItemType Directory | Out-Null }
        foreach ($name in $managed) {
            $target=Join-Path $InstallRoot $name
            if(Test-Path $target){Remove-Item $target -Recurse -Force}
            Copy-Item (Join-Path $stage $name) $target -Recurse -Force
        }
        $installed = $true
        if ($ValidateInstalled) { & $ValidateInstalled $InstallRoot }
        Write-Output 'OPERATOR_PROXY_INSTALL_PASS'
    } catch {
        if ($installed) {
            foreach ($name in $managed) {
                $target=Join-Path $InstallRoot $name
                if(Test-Path $target){Remove-Item $target -Recurse -Force}
                $saved=Join-Path $backup $name
                if(Test-Path $saved){Copy-Item $saved $target -Recurse -Force}
            }
            Write-Output 'OPERATOR_PROXY_ROLLBACK_PASS'
        }
        throw
    } finally {
        if(Test-Path $stage){Remove-Item $stage -Recurse -Force}
    }
}
Export-ModuleMember -Function Invoke-OperatorProxyInstall,Invoke-CheckedNative
