import base64
import hashlib
import json
import re
import time
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")

FILES = [
    Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase14_challenge_cycle_activation_2026-04-22.json"),
    Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase14b_cycle_activation_dynrisk_2026-04-22.json"),
]


def creds():
    d = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    return str(d.get("user_id") or d.get("userId")).strip(), str(d.get("api_token") or d.get("apiToken") or d.get("token")).strip()


def hdr(uid, tok, ts=None):
    ts = int(ts or time.time())
    sig = hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": str(ts), "Content-Type": "application/json"}


def post(uid, tok, ep, payload, timeout=120):
    ts = int(time.time())
    r = requests.post(f"{BASE}/{ep}", headers=hdr(uid, tok, ts), json=payload, timeout=timeout)
    try:
        d = r.json()
    except Exception:
        d = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
    if r.status_code >= 400:
        d.setdefault("success", False)
    if d.get("success", False):
        return d
    m = re.search(r"Server Time:\s*(\d+)", " ".join(d.get("errors") or []))
    if m:
        ts2 = int(m.group(1)) - 1
        r2 = requests.post(f"{BASE}/{ep}", headers=hdr(uid, tok, ts2), json=payload, timeout=timeout)
        try:
            return r2.json()
        except Exception:
            return {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
    return d


def pf(x):
    try:
        return float(str(x).replace("%", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def pi(x):
    try:
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return None


def rt(runtime, key):
    if isinstance(runtime, dict):
        return runtime.get(key)
    if isinstance(runtime, list):
        for it in runtime:
            if isinstance(it, dict) and str(it.get("name") or it.get("Name")) == key:
                return it.get("value") or it.get("Value")
    return None


def main():
    uid, tok = creds()
    for f in FILES:
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        rows = d.get("rows") or []
        changed = 0
        for r in rows:
            if r.get("backtest_id") is None:
                continue
            if (
                r.get("np_pct") is not None
                and r.get("orders") is not None
                and not (int(r.get("closed_trades") or 0) == 0 and int(r.get("orders") or 0) > 0)
            ):
                continue

            rd = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": r["backtest_id"]}, timeout=120)
            bt = rd.get("backtest") or {}
            s = bt.get("statistics") or {}
            rts = bt.get("runtimeStatistics") or {}
            perf = bt.get("totalPerformance") or {}
            trades = perf.get("closedTrades") or []

            old_np = r.get("np_pct")
            r["np_pct"] = pf(s.get("Net Profit"))
            r["dd_pct"] = pf(s.get("Drawdown"))
            r["orders"] = pi(s.get("Total Orders"))
            r["dbr"] = pi(rt(rts, "DailyLossBreaches"))
            r["tbr"] = pi(rt(rts, "TrailingBreaches"))
            r["stress_days"] = pi(rt(rts, "ExternalStressDays"))
            if r.get("closed_trades") is None or (int(r.get("closed_trades") or 0) == 0 and int(r.get("orders") or 0) > 0):
                r["closed_trades"] = len(trades)
            if old_np != r.get("np_pct"):
                changed += 1

        d["rows"] = rows
        f.write_text(json.dumps(d, indent=2), encoding="utf-8")

        txt = f.with_suffix(".txt")
        lines = []
        for r in rows:
            lines.append(
                f"{r.get('candidate')} {r.get('scenario')} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} "
                f"closed={r.get('closed_trades')} hit6={r.get('challenge_hit')} days6={r.get('challenge_days')} best_day%={r.get('best_day_share_pct')} "
                f"orders={r.get('orders')} stress_days={r.get('stress_days')} id={r.get('backtest_id')}"
            )
        txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{f.name}: refreshed={changed}")


if __name__ == "__main__":
    main()
