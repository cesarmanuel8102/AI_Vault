param(
  [Parameter(Mandatory=$true)][string]$LeadId,
  [Parameter(Mandatory=$true)][string]$Status,
  [Parameter(Mandatory=$false)][string]$Note = ""
)
$ErrorActionPreference="Stop"
$ROOT="C:\AI_VAULT"
$env:BRAINLAB_ROOT=$ROOT
python "$ROOT\70_SCORING_ENGINE\mark_lead.py" $LeadId $Status $Note