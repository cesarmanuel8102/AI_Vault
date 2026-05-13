param([string]$Py="python")
Set-Location -Path $PSScriptRoot
& $Py -c "import sys; sys.path.insert(0,'.'); import src.autonomy_planner as p; p.main()"
