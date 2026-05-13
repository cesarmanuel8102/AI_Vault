import json

src = r"C:\AI_VAULT\workspace\brainlab\brainlab\contracts\financial_motor_contract_v1.json"
dst = r"C:\AI_VAULT\workspace\brainlab\brainlab\contracts\financial_motor_contract_PASS.json"

with open(src, "r", encoding="utf-8") as f:
    j = json.load(f)

TARGET_KEYS = ("max_daily_loss","max_weekly_drawdown","max_total_exposure","kill_switch")

def find_limits(obj, path="$"):
    if isinstance(obj, dict):
        if all(k in obj for k in TARGET_KEYS):
            return obj, path
        for k,v in obj.items():
            r = find_limits(v, path + "." + k)
            if r: return r
    elif isinstance(obj, list):
        for i,v in enumerate(obj):
            r = find_limits(v, f"{path}[{i}]")
            if r: return r
    return None

found = find_limits(j)
if found:
    lim, p = found
else:
    lim = j.setdefault("limits", {})
    p = "$.limits (created)"

lim["max_daily_loss"] = 0.03
lim["max_weekly_drawdown"] = 0.12
lim["max_total_exposure"] = 1.0
lim["kill_switch"] = False

with open(dst, "w", encoding="utf-8") as f:
    json.dump(j, f, ensure_ascii=False, indent=2)

print("UPDATED_LIMITS_AT:", p)
print("TOP_KEYS:", list(j.keys()))
