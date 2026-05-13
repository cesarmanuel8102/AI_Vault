$ErrorActionPreference = "Stop"

$base = "C:\AI_VAULT\repos"

$repos = @(
    @{
        Name = "openclaw"
        Url  = "https://github.com/openclaw/openclaw.git"
    },
    @{
        Name = "awesome-openclaw"
        Url  = "https://github.com/rylena/awesome-openclaw.git"
    },
    @{
        Name = "openfang"
        Url  = "https://github.com/RightNow-AI/openfang.git"
    }
)

function Ensure-Dir {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

function Sync-GitRepo {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoName,

        [Parameter(Mandatory = $true)]
        [string]$RepoUrl,

        [Parameter(Mandatory = $true)]
        [string]$BasePath
    )

    $target = Join-Path $BasePath $RepoName

    Write-Host ""
    Write-Host "=== $RepoName ===" -ForegroundColor Cyan
    Write-Host "Destino: $target"

    if (Test-Path $target) {
        if (Test-Path (Join-Path $target ".git")) {
            Write-Host "Repositorio ya existe. Actualizando..." -ForegroundColor Yellow
            Push-Location $target
            try {
                git remote -v
                git fetch --all --tags --prune
                git pull --ff-only
                git status --short --branch
            }
            finally {
                Pop-Location
            }
        }
        else {
            throw "La ruta existe pero no parece un repo git válido: $target"
        }
    }
    else {
        Write-Host "Clonando..." -ForegroundColor Green
        Push-Location $BasePath
        try {
            git -c credential.helper= clone $RepoUrl $RepoName
        }
        finally {
            Pop-Location
        }
    }
}

Ensure-Dir -Path $base

foreach ($repo in $repos) {
    Sync-GitRepo -RepoName $repo.Name -RepoUrl $repo.Url -BasePath $base
}

Write-Host ""
Write-Host "=== ESTRUCTURA FINAL ===" -ForegroundColor Magenta
Get-ChildItem $base -Directory | Select-Object Name, FullName

Write-Host ""
Write-Host "=== REMOTES ===" -ForegroundColor Magenta
foreach ($repo in $repos) {
    $target = Join-Path $base $repo.Name
    if (Test-Path (Join-Path $target ".git")) {
        Push-Location $target
        try {
            Write-Host ""
            Write-Host "[$($repo.Name)]" -ForegroundColor Cyan
            git remote -v
            git branch --show-current
        }
        finally {
            Pop-Location
        }
    }
}
