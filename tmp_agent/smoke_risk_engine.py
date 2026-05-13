import json
from brainlab.risk.risk_engine import RiskEngine

contract = r"C:\AI_VAULT\workspace\brainlab\brainlab\contracts\financial_motor_contract_v1.json"
re = RiskEngine.from_contract_path(contract)

tests = [
  {"name":"ok","snapshot":{"nlv":1000.0,"daily_pnl":-5.0,"weekly_drawdown":0.01,"total_exposure":0.35}},
  {"name":"daily_loss_violation","snapshot":{"nlv":1000.0,"daily_pnl":-25.0,"weekly_drawdown":0.01,"total_exposure":0.35}},
  {"name":"weekly_dd_violation","snapshot":{"nlv":1000.0,"daily_pnl":0.0,"weekly_drawdown":0.10,"total_exposure":0.35}},
  {"name":"exposure_violation","snapshot":{"nlv":1000.0,"daily_pnl":0.0,"weekly_drawdown":0.01,"total_exposure":0.95}},
]

out = {"limits": re.limits.__dict__, "results":[]}
for t in tests:
  out["results"].append({"name": t["name"], "assess": re.assess(t["snapshot"])})

print(json.dumps(out, ensure_ascii=False, indent=2))
