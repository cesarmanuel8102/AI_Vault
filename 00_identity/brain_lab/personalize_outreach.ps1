param([string]$Py="python",[string]$sender="Cesar")
Set-Location -Path $PSScriptRoot
& $Py -c "import sys; sys.path.insert(0,'.'); import src.outreach_assets as oa; import json; print(json.dumps(oa.personalize_from_leads(sender=r'''$sender'''), ensure_ascii=False, indent=2))"
