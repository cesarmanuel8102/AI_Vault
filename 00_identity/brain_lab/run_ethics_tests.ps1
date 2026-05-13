param(
  [string]$Py = "python"
)

# Siempre ejecuta desde la carpeta donde está este .ps1 (brain_lab)
Set-Location -Path $PSScriptRoot

# Asegura que Python vea el root como sys.path[0]
& $Py -c "import sys; sys.path.insert(0,'.'); from src.ethics_kernel import run_tests; import json; print(json.dumps(run_tests(), indent=2))"
