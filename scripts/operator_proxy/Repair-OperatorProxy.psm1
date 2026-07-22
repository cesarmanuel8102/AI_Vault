function Invoke-OperatorProxyInstall { [CmdletBinding()]param([string]$Repo,[string]$InstallRoot,[string]$ApprovedCommit)
 $head=(git -C $Repo rev-parse HEAD).Trim(); if($LASTEXITCODE -or $head -ne $ApprovedCommit){throw 'control-plane commit mismatch'}; if($Repo -like 'C:\AI_VAULT_CANONICAL*' -or $InstallRoot -like 'C:\AI_VAULT_CANONICAL*'){throw 'canonical path denied'}
 $src=Join-Path $Repo 'scripts\operator_proxy'; $backup=Join-Path $InstallRoot ('backups\'+(Get-Date -Format 'yyyyMMddTHHmmssZ')); New-Item $backup -ItemType Directory -Force|Out-Null; foreach($n in 'src','schemas','package.json','tsconfig.json'){if(Test-Path (Join-Path $InstallRoot $n)){Copy-Item (Join-Path $InstallRoot $n) $backup -Recurse -Force}}
 try {New-Item $InstallRoot -ItemType Directory -Force|Out-Null; Copy-Item (Join-Path $src '*.ts') $InstallRoot -Force; Copy-Item (Join-Path $src 'schemas') $InstallRoot -Recurse -Force; Copy-Item (Join-Path $src 'package.json') $InstallRoot -Force; Copy-Item (Join-Path $src 'tsconfig.json') $InstallRoot -Force; Write-Output 'OPERATOR_PROXY_INSTALL_PASS'} catch {throw}
}
Export-ModuleMember -Function Invoke-OperatorProxyInstall
