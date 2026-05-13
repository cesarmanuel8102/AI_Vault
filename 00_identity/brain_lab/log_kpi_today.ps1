param(
  [string]$Py="python",
  [int]$outreach_sent = 0,
  [int]$responses = 0,
  [int]$calls_booked = 0,
  [int]$proposals_sent = 0,
  [int]$deals_closed = 0,
  [double]$revenue_usd = 0,
  [double]$cost_usd = 0
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$LAB = $PSScriptRoot
$KPI_DIR = Join-Path $LAB "kpi"
if(-not (Test-Path $KPI_DIR)){ New-Item -ItemType Directory -Force -Path $KPI_DIR | Out-Null }

# Pasamos valores por variables de entorno (simple y robusto)
$env:KPI_outreach_sent = "$outreach_sent"
$env:KPI_responses = "$responses"
$env:KPI_calls_booked = "$calls_booked"
$env:KPI_proposals_sent = "$proposals_sent"
$env:KPI_deals_closed = "$deals_closed"
$env:KPI_revenue_usd = "$revenue_usd"
$env:KPI_cost_usd = "$cost_usd"

$pyScriptPath = Join-Path $LAB "src\_kpi_logger_tmp.py"

@"
import json, os
from datetime import datetime

root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
kpi_path = os.path.join(root, "kpi", "kpi_daily.jsonl")

def env_int(k, d=0):
    try: return int(os.environ.get(k, d))
    except: return int(d)

def env_float(k, d=0.0):
    try: return float(os.environ.get(k, d))
    except: return float(d)

entry = {
  "ts": datetime.utcnow().isoformat() + "Z",
  "outreach_sent": env_int("KPI_outreach_sent", 0),
  "responses": env_int("KPI_responses", 0),
  "calls_booked": env_int("KPI_calls_booked", 0),
  "proposals_sent": env_int("KPI_proposals_sent", 0),
  "deals_closed": env_int("KPI_deals_closed", 0),
  "revenue_usd": env_float("KPI_revenue_usd", 0.0),
  "cost_usd": env_float("KPI_cost_usd", 0.0)
}

os.makedirs(os.path.dirname(kpi_path), exist_ok=True)
with open(kpi_path, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

print("OK KPI logged:", entry)
"@ | Set-Content -Encoding UTF8 $pyScriptPath

& $Py $pyScriptPath
