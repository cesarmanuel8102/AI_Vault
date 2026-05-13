param([string]$Py="python")
Set-Location -Path $PSScriptRoot
& $Py -c "import sys; sys.path.insert(0,'.'); import json; from src.experiment_engine import plan; ideas=json.load(open('memory\\ideas_input.json',encoding='utf-8-sig')); import json as j; print(j.dumps(plan(ideas),indent=2,ensure_ascii=False))"
