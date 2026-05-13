param([string]$Py="python")
Set-Location -Path $PSScriptRoot
& $Py -c "import sys; sys.path.insert(0,'.'); import src.outreach_assets as oa; oa.generate_assets(); print('OK')"
