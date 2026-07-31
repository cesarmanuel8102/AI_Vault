function Invoke-CheckedNative {
    param([Parameter(Mandatory=$true)][string]$FilePath,[Parameter(Mandatory=$true)][string[]]$Arguments,[Parameter(Mandatory=$true)][string]$Identity)
    & $FilePath @Arguments
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "$Identity failed with exit code $code" }
}

function Assert-NoReparsePoint {
    param([Parameter(Mandatory=$true)][string]$Path)
    $full=[IO.Path]::GetFullPath($Path)
    $root=[IO.Path]::GetPathRoot($full)
    $current=$root
    foreach($part in $full.Substring($root.Length).Split([IO.Path]::DirectorySeparatorChar,[StringSplitOptions]::RemoveEmptyEntries)){
        $current=Join-Path $current $part
        if(Test-Path -LiteralPath $current){
            $item=Get-Item -LiteralPath $current -Force
            if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw "reparse point denied: $current"}
        }
    }
}

function Resolve-TrustedOperatorProxyPath {
    param([Parameter(Mandatory=$true)][string]$Path,[switch]$MustExist)
    if(-not [IO.Path]::IsPathRooted($Path)){throw 'absolute local path required'}
    if($Path.StartsWith('\\')){throw 'UNC path denied'}
    if([Management.Automation.WildcardPattern]::ContainsWildcardCharacters($Path)){throw 'wildcard path denied'}
    if($Path -split '[\\/]' | Where-Object {$_ -eq '..'}){throw 'parent traversal denied'}
    $full=[IO.Path]::GetFullPath($Path)
    $root=[IO.Path]::GetPathRoot($full)
    if($full.Length -gt $root.Length){$full=$full.TrimEnd([IO.Path]::DirectorySeparatorChar,[IO.Path]::AltDirectorySeparatorChar)}
    if($MustExist -and -not (Test-Path -LiteralPath $full)){throw 'required path missing'}
    Assert-NoReparsePoint $full
    if(Test-Path -LiteralPath $full){
        $full=(Resolve-Path -LiteralPath $full).Path
        $root=[IO.Path]::GetPathRoot($full)
        if($full.Length -gt $root.Length){$full=$full.TrimEnd([IO.Path]::DirectorySeparatorChar,[IO.Path]::AltDirectorySeparatorChar)}
    }
    return $full
}

function Test-PathWithin {
    param([string]$Child,[string]$Parent)
    $c=[IO.Path]::GetFullPath($Child).TrimEnd('\')
    $p=[IO.Path]::GetFullPath($Parent).TrimEnd('\')
    return $c.Equals($p,[StringComparison]::OrdinalIgnoreCase) -or $c.StartsWith($p+'\',[StringComparison]::OrdinalIgnoreCase)
}

function Get-TrustedGitValue {
    param([string]$Repo,[string[]]$Arguments,[string]$Identity)
    $value=& git -C $Repo @Arguments
    if($LASTEXITCODE -ne 0){throw "$Identity failed"}
    return ($value -join "`n").Trim()
}

function Assert-TrustedOperatorProxyRepository {
    param([Parameter(Mandatory=$true)][string]$Repo,[Parameter(Mandatory=$true)][string]$ApprovedCommit)
    $resolved=Resolve-TrustedOperatorProxyPath $Repo -MustExist
    $top=Get-TrustedGitValue $resolved @('rev-parse','--show-toplevel') 'git top-level verification'
    $top=Resolve-TrustedOperatorProxyPath $top -MustExist
    if(-not $top.Equals($resolved,[StringComparison]::OrdinalIgnoreCase)){throw 'repository top-level identity mismatch'}
    if((Get-TrustedGitValue $resolved @('rev-parse','--is-inside-work-tree') 'git worktree verification') -ne 'true'){throw 'repository is not a worktree'}
    if((Get-TrustedGitValue $resolved @('rev-parse','HEAD') 'git HEAD verification') -ne $ApprovedCommit){throw 'control-plane commit mismatch'}
    $remote=Get-TrustedGitValue $resolved @('remote','get-url','origin') 'git remote verification'
    $allowed=@('https://github.com/cesarmanuel8102/AI_Vault','https://github.com/cesarmanuel8102/AI_Vault.git','git@github.com:cesarmanuel8102/AI_Vault.git')
    if($remote -notin $allowed){throw 'repository remote identity mismatch'}
    $source=Resolve-TrustedOperatorProxyPath (Join-Path $resolved 'scripts\operator_proxy') -MustExist
    if(-not (Test-PathWithin $source $resolved)){throw 'operator proxy source escaped repository'}
    if(Get-TrustedGitValue $resolved @('status','--porcelain','--untracked-files=all','--','scripts/operator_proxy') 'git source cleanliness verification'){throw 'operator proxy source is not clean'}
    return [pscustomobject]@{Repo=$resolved;Source=$source;Head=$ApprovedCommit;Remote=$remote}
}

function Assert-SafeInstallRoot {
    param([Parameter(Mandatory=$true)][string]$InstallRoot,[Parameter(Mandatory=$true)][string]$Repo)
    $resolved=Resolve-TrustedOperatorProxyPath $InstallRoot
    $canonical=Resolve-TrustedOperatorProxyPath 'C:\AI_VAULT_CANONICAL'
    if(Test-PathWithin $resolved $canonical){throw 'canonical path denied'}
    if((Test-PathWithin $resolved $Repo) -or (Test-PathWithin $Repo $resolved)){throw 'repository and install root overlap'}
    return $resolved
}

function Get-OperatorProxyTransactionParent {
    param([Parameter(Mandatory=$true)][string]$InstallRoot)
    $parent=[IO.Path]::GetDirectoryName($InstallRoot)
    $root=[IO.Path]::GetPathRoot($InstallRoot)
    if($parent -and $root -and $parent -eq $root.TrimEnd([IO.Path]::DirectorySeparatorChar,[IO.Path]::AltDirectorySeparatorChar)){$parent=$root}
    if(-not $parent -or -not [IO.Path]::IsPathRooted($parent)){throw 'install transaction parent invalid'}
    return $parent
}

function Assert-TransactionIdentity {
    param($Identity,[string]$InstallRoot,[string]$Stage,[string]$Backup)
    $current=Assert-TrustedOperatorProxyRepository $Identity.Repo $Identity.Head
    if($current.Source -ne $Identity.Source){throw 'source identity changed during transaction'}
    $resolvedInstall=Assert-SafeInstallRoot $InstallRoot $Identity.Repo
    foreach($path in @($resolvedInstall,$Stage,$Backup)){
        Assert-NoReparsePoint $path
        if($path -ne $resolvedInstall -and -not (Test-PathWithin $path (Split-Path $resolvedInstall -Parent))){throw 'transaction path escaped validated parent'}
    }
}

function Assert-SafeManagedTarget {
    param([string]$Target,[string]$Root)
    $resolved=[IO.Path]::GetFullPath($Target)
    if(-not (Test-PathWithin $resolved $Root)){throw 'managed target escaped authorized root'}
    Assert-NoReparsePoint $resolved
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
    $ErrorActionPreference='Stop'
    $identity=Assert-TrustedOperatorProxyRepository $Repo $ApprovedCommit
    $install=Assert-SafeInstallRoot $InstallRoot $identity.Repo
    $parent=Get-OperatorProxyTransactionParent $install
    if(-not (Test-Path -LiteralPath $parent)){New-Item -Path $parent -ItemType Directory -Force|Out-Null}
    $parent=Resolve-TrustedOperatorProxyPath $parent -MustExist
    $backupParent=Join-Path $parent 'AI_VAULT_OPERATOR_PROXY_BACKUPS'
    if(-not (Test-Path -LiteralPath $backupParent)){New-Item -Path $backupParent -ItemType Directory -Force|Out-Null}
    $backupParent=Resolve-TrustedOperatorProxyPath $backupParent -MustExist
    $stamp=Get-Date -Format 'yyyyMMddTHHmmssfffZ'
    $stage=Join-Path $parent ".operator-proxy-stage-$stamp"
    $backup=Join-Path $backupParent "operator-proxy-backup-$stamp"
    if((Test-PathWithin $stage $identity.Repo) -or (Test-PathWithin $backup $identity.Repo)){throw 'transaction artifacts overlap repository'}
    if((Test-Path -LiteralPath $stage) -or (Test-Path -LiteralPath $backup)){throw 'transaction path collision'}
    if($install -eq $stage -or $install -eq $backup){throw 'transaction root collision'}
    $managed=@('schemas','action_executor.ts','agent_loop_builder_adapter.ts','autonomous_flow.ts','autonomous_runtime.ts','codex_builder.ts','codex_reviewer.ts','decision_ledger.ts','evidence_collector.ts','external_effect_guard.ts','github_bus.ts','governed_builder.ts','lifecycle_store.ts','opencode_reviewer.ts','operator_proxy.ts','policy_engine.ts','production_effects.ts','redaction.ts','request_coordinator.ts','review_contract.ts','reviewer_backend.ts','reviewer_config.ts','reviewer_router.ts','risk_classifier.ts','roadmap_sequencer.ts','single_instance_lock.ts','spec_contract.ts','state_machine.ts','types.ts','package.json','package-lock.json','tsconfig.json','Run-OperatorProxy.ps1')
    $installed=$false
    try {
        Assert-TransactionIdentity $identity $install $stage $backup
        New-Item -Path $stage -ItemType Directory|Out-Null
        foreach($name in $managed){Assert-TransactionIdentity $identity $install $stage $backup;$src=Join-Path $identity.Source $name;$dst=Join-Path $stage $name;Assert-SafeManagedTarget $dst $stage;Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force}
        if($ValidateStaging){& $ValidateStaging $stage}else{Push-Location $stage;try{Invoke-CheckedNative 'npm.cmd' @('ci','--ignore-scripts') 'npm ci';Invoke-CheckedNative (Join-Path $stage 'node_modules\.bin\tsc.cmd') @('--noEmit','-p',(Join-Path $stage 'tsconfig.json')) 'typecheck'}finally{Pop-Location}}
        if(-not (Test-Path -LiteralPath (Join-Path $stage 'node_modules\.bin\tsx.cmd'))){throw 'validated staging dependencies missing'}
        $managed+='node_modules'
        Assert-TransactionIdentity $identity $install $stage $backup
        New-Item -Path $backup -ItemType Directory|Out-Null
        if(Test-Path -LiteralPath $install){foreach($name in $managed){$p=Join-Path $install $name;$saved=Join-Path $backup $name;Assert-SafeManagedTarget $p $install;Assert-SafeManagedTarget $saved $backup;if(Test-Path -LiteralPath $p){Copy-Item -LiteralPath $p -Destination $saved -Recurse -Force}}}else{New-Item -Path $install -ItemType Directory|Out-Null}
        $installed=$true
        foreach($name in $managed){Assert-TransactionIdentity $identity $install $stage $backup;$target=Join-Path $install $name;Assert-SafeManagedTarget $target $install;if(Test-Path -LiteralPath $target){Remove-Item -LiteralPath $target -Recurse -Force};Copy-Item -LiteralPath (Join-Path $stage $name) -Destination $target -Recurse -Force}
        if($ValidateInstalled){& $ValidateInstalled $install}
        Assert-TransactionIdentity $identity $install $stage $backup
        if(Get-TrustedGitValue $identity.Repo @('status','--porcelain','--untracked-files=all') 'git repository cleanliness verification'){throw 'repository changed during installation'}
        Write-Output 'OPERATOR_PROXY_INSTALL_PASS'
    } catch {
        if($installed){
            foreach($name in $managed){$target=Join-Path $install $name;Assert-SafeManagedTarget $target $install;if(Test-Path -LiteralPath $target){Remove-Item -LiteralPath $target -Recurse -Force};$saved=Join-Path $backup $name;Assert-SafeManagedTarget $saved $backup;if(Test-Path -LiteralPath $saved){Copy-Item -LiteralPath $saved -Destination $target -Recurse -Force}}
            Write-Output 'OPERATOR_PROXY_ROLLBACK_PASS'
        }
        throw
    } finally {
        if(Test-Path -LiteralPath $stage){Assert-SafeManagedTarget $stage $parent;Remove-Item -LiteralPath $stage -Recurse -Force}
    }
}
Export-ModuleMember -Function Invoke-OperatorProxyInstall,Invoke-CheckedNative,Resolve-TrustedOperatorProxyPath,Assert-NoReparsePoint,Assert-TrustedOperatorProxyRepository,Assert-SafeInstallRoot,Get-OperatorProxyTransactionParent
