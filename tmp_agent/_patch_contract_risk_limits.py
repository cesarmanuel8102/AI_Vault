import json

src = r"C:\AI_VAULT\workspace\brainlab\brainlab\contracts\financial_motor_contract_v1.json"
dst = r"C:\AI_VAULT\workspace\brainlab\brainlab\contracts\financial_motor_contract_PASS.json"

with open(src, "r", encoding="utf-8") as f:
    j = json.load(f)

risk = j.get("risk") or {}
limits = risk.get("limits") or {}

# Detect key names
def set_limit(key_candidates, value):
    for k in key_candidates:
        if k in limits:
            limits[k] = value
            return k
    # If none exist, create first candidate
    limits[key_candidates[0]] = value
    return key_candidates[0]

k1 = set_limit(("max_daily_loss_frac","max_daily_loss"), 0.03)
k2 = set_limit(("max_weekly_drawdown_frac","max_weekly_drawdown"), 0.12)
k3 = set_limit(("max_total_exposure_frac","max_total_exposure"), 1.0)
k4 = set_limit(("kill_switch",), False)

risk["limits"] = limits
j["risk"] = risk

# IMPORTANT: remove any accidental root-level 'limits' to avoid confusion
if "limits" in j and isinstance(j["limits"], dict):
    # only remove if it looks like the accidental block we added
    if any(k in j["limits"] for k in ("max_daily_loss","max_weekly_drawdown","max_total_exposure")):
        del j["limits"]

with open(dst, "w", encoding="utf-8") as f:
    json.dump(j, f, ensure_ascii=False, indent=2)

print("OK: wrote", dst)
print("risk.limits keys set:", k1, k2, k3, k4)
print("risk.limits =", limits)
