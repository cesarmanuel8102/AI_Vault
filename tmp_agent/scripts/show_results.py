import hashlib, time, requests, base64, json

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"

def get_headers():
    ts = str(int(time.time()))
    hashed = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{UID}:{hashed}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts}

# List all completed ParamLoop backtests
r = requests.post("https://www.quantconnect.com/api/v2/backtests/list",
    headers=get_headers(), json={"projectId": 29490680}, timeout=30)
backtests = r.json().get("backtests", [])

results = []
for bt in backtests:
    name = bt.get("name", "")
    status = bt.get("status", "")
    if "ParamLoop" in name and status in ("Completed.", "Completed"):
        bt_id = bt.get("backtestId", "")
        r2 = requests.post("https://www.quantconnect.com/api/v2/backtests/read",
            headers=get_headers(), json={"projectId": 29490680, "backtestId": bt_id}, timeout=30)
        full = r2.json().get("backtest", {})
        stats = full.get("statistics", {})
        ps = full.get("parameterSet", {})
        
        parts = name.split("ParamLoop ")
        label = parts[1].split(" PT=")[0].strip() if len(parts) > 1 else "?"
        
        def sf(k, d="0"):
            v = stats.get(k, d)
            try:
                return float(str(v).replace("%", "").replace(",", "").replace("$", ""))
            except:
                return 0.0
        
        results.append({
            "label": label,
            "pt": ps.get("profit_target_pct", "?"),
            "sl": ps.get("stop_loss_pct", "?"),
            "risk": ps.get("risk_per_trade", "?"),
            "ret": sf("Net Profit"),
            "cagr": sf("Compounding Annual Return"),
            "sharpe": sf("Sharpe Ratio"),
            "sortino": sf("Sortino Ratio"),
            "dd": sf("Drawdown"),
            "dd_rec": sf("Drawdown Recovery"),
            "trades": int(sf("Total Orders")),
            "wr": sf("Win Rate"),
            "pf": sf("Profit-Loss Ratio"),
            "vol": sf("Annual Standard Deviation"),
            "psr": sf("Probabilistic Sharpe Ratio"),
        })
        time.sleep(0.3)

# Add pass/fail
for r in results:
    r["gate"] = r["cagr"] >= 12.0 and r["sharpe"] >= 1.0

# Sort by sharpe desc
results.sort(key=lambda x: x["sharpe"], reverse=True)

hdr = "{:<10} {:>5} {:>6} {:>5} {:>9} {:>7} {:>7} {:>8} {:>6} {:>6} {:>6} {:>5} {:>5} {:>6} {:>6} {:>5}".format(
    "#", "PT", "SL", "Risk", "Return", "CAGR", "Sharpe", "Sortino", "DD", "DDRec", "Trades", "WR", "PF", "Vol", "PSR", "Gate")
print(hdr)
print("-" * len(hdr))

for r in results:
    g = "PASS" if r["gate"] else "FAIL"
    print("{:<10} {:>5} {:>6} {:>5} {:>+8.1f}% {:>6.1f}% {:>7.3f} {:>8.3f} {:>5.1f}% {:>6.0f} {:>6} {:>4.0f}% {:>5.2f} {:>5.1f}% {:>5.1f}% {:>5}".format(
        r["label"], r["pt"], r["sl"], r["risk"],
        r["ret"], r["cagr"], r["sharpe"], r["sortino"],
        r["dd"], r["dd_rec"], r["trades"], r["wr"], r["pf"],
        r["vol"], r["psr"], g))

passes = sum(1 for r in results if r["gate"])
print(f"\nTotal: {len(results)} completados | Gates PASS: {passes}/{len(results)}")
