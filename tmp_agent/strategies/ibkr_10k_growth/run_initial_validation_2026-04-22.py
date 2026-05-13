import base64
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/results/initial_validation_2026-04-22.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/ibkr_10k_growth/results/initial_validation_2026-04-22.txt")


def creds():
    d = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    uid = str(d.get("user_id") or d.get("userId") or "").strip()
    tok = str(d.get("api_token") or d.get("apiToken") or d.get("token") or "").strip()
    if not uid or not tok:
        raise RuntimeError("Missing QC credentials")
    return uid, tok


def hdr(uid, tok, ts=None):
    ts = int(ts or time.time())
    sig = hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": str(ts), "Content-Type": "application/json"}


def post(uid, tok, ep, payload, timeout=120):
    last = None
    for i in range(6):
        ts = int(time.time())
        try:
            r = requests.post(f"{BASE}/{ep}", headers=hdr(uid, tok, ts), json=payload, timeout=timeout)
            try:
                d = r.json()
            except Exception:
                d = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
            if r.status_code >= 400:
                d.setdefault("success", False)
            if d.get("success", False):
                return d
            m = re.search(r"Server Time:\\s*(\\d+)", " ".join(d.get("errors") or []))
            if m:
                ts2 = int(m.group(1)) - 1
                r2 = requests.post(f"{BASE}/{ep}", headers=hdr(uid, tok, ts2), json=payload, timeout=timeout)
                try:
                    d2 = r2.json()
                except Exception:
                    d2 = {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
                if d2.get("success", False):
                    return d2
                d = d2
            last = d
        except Exception as e:
            last = {"success": False, "errors": [str(e)]}
        time.sleep(min(3 * (i + 1), 20))
    return last or {"success": False, "errors": ["request failed"]}


def pf(x):
    try:
        return float(str(x).replace("%", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def create_project(uid, tok, name):
    r = post(uid, tok, "projects/create", {"name": name, "language": "Py"}, timeout=120)
    projects = r.get("projects") or []
    if not (r.get("success") and projects):
        raise RuntimeError(f"projects/create failed: {r}")
    return int(projects[0]["projectId"])


def upload_main(uid, tok, project_id):
    code = MAIN_PATH.read_text(encoding="utf-8")
    r = post(uid, tok, "files/create", {"projectId": project_id, "name": "main.py", "content": code}, timeout=180)
    if r.get("success", False):
        return
    msg = " ".join(r.get("errors") or [])
    if "already exist" in msg.lower():
        u = post(uid, tok, "files/update", {"projectId": project_id, "name": "main.py", "content": code}, timeout=180)
        if not u.get("success", False):
            raise RuntimeError(f"files/update failed: {u}")
        return
    raise RuntimeError(f"files/create failed: {r}")


def set_params(uid, tok, project_id, params):
    payload = {"projectId": project_id, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    r = post(uid, tok, "projects/update", payload, timeout=90)
    if not r.get("success", False):
        raise RuntimeError(f"projects/update failed: {r}")


def compile_project(uid, tok, project_id):
    c = post(uid, tok, "compile/create", {"projectId": project_id}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(240):
        rd = post(uid, tok, "compile/read", {"projectId": project_id, "compileId": cid}, timeout=60)
        st = rd.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(f"Compile failed: {st} | {rd}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def run_backtest(uid, tok, project_id, compile_id, name):
    bid = None
    for _ in range(40):
        bc = post(
            uid,
            tok,
            "backtests/create",
            {"projectId": project_id, "compileId": compile_id, "backtestName": name},
            timeout=120,
        )
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        if "no spare nodes available" in str(bc).lower():
            time.sleep(45)
            continue
        raise RuntimeError(f"backtests/create failed: {bc}")
    if not bid:
        raise RuntimeError("backtest id missing")

    bt = {}
    for _ in range(600):
        rd = post(uid, tok, "backtests/read", {"projectId": project_id, "backtestId": bid}, timeout=120)
        bt = rd.get("backtest") or {}
        st = str(bt.get("status", ""))
        if "Completed" in st:
            break
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            raise RuntimeError(f"Backtest ended in {st}: {bt.get('error') or bt.get('message')}")
        time.sleep(10)

    rd2 = post(uid, tok, "backtests/read", {"projectId": project_id, "backtestId": bid}, timeout=120)
    return rd2.get("backtest") or bt


def summarize(bt):
    s = bt.get("statistics") or {}
    return {
        "status": bt.get("status"),
        "backtest_id": bt.get("backtestId"),
        "np_pct": pf(s.get("Net Profit")),
        "cagr_pct": pf(s.get("Compounding Annual Return")),
        "dd_pct": pf(s.get("Drawdown")),
        "sharpe": pf(s.get("Sharpe Ratio")),
        "sortino": pf(s.get("Sortino Ratio")),
        "win_rate_pct": pf(s.get("Win Rate")),
        "profit_factor": pf(s.get("Profit Factor")),
        "trades": pf(s.get("Total Trades")),
    }


def main():
    uid, tok = creds()

    project_name = f"IBKR10K_GROWTH_MOMENTUM_{int(time.time())}"
    project_id = create_project(uid, tok, project_name)
    upload_main(uid, tok, project_id)

    base = {
        "initial_cash": 10000,
        "top_n": 2,
        "lookback_fast": 63,
        "lookback_slow": 126,
        "atr_period": 20,
        "sma_filter_period": 200,
        "score_min": 0.02,
        "w_fast": 0.65,
        "w_slow": 0.35,
        "vol_penalty": 2.4,
        "target_atr_pct": 0.04,
        "rebalance_buffer": 0.03,
        "circuit_dd_pct": 0.20,
        "cooldown_days": 20,
    }

    candidates = [
        ("IB10K_BALANCED", {"base_gross": 1.40, "max_gross": 1.60, "max_single_weight": 0.80}),
        ("IB10K_AGGRESSIVE", {"base_gross": 1.55, "max_gross": 1.85, "max_single_weight": 0.95, "circuit_dd_pct": 0.24}),
    ]

    scenarios = [
        ("FULL_2018_2026Q1", {"start_year": 2018, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("OOS_2023_2026Q1", {"start_year": 2023, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
    ]

    rows = []
    for label, ov in candidates:
        cfg = dict(base)
        cfg.update(ov)
        set_params(uid, tok, project_id, cfg)
        cid = compile_project(uid, tok, project_id)
        for sname, dts in scenarios:
            params = dict(cfg)
            params.update(dts)
            set_params(uid, tok, project_id, params)
            bt = run_backtest(uid, tok, project_id, cid, f"{label}_{sname}_{int(time.time())}")
            sm = summarize(bt)
            sm.update({"candidate": label, "scenario": sname})
            rows.append(sm)

            OUT_JSON.write_text(
                json.dumps(
                    {
                        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                        "project_id": project_id,
                        "project_name": project_name,
                        "rows": rows,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    lines = [
        f"generated_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"project_id={project_id}",
        f"project_name={project_name}",
        "",
    ]
    for r in rows:
        lines.append(
            f"{r['candidate']} {r['scenario']} np={r.get('np_pct')} cagr={r.get('cagr_pct')} dd={r.get('dd_pct')} "
            f"sharpe={r.get('sharpe')} sortino={r.get('sortino')} wr={r.get('win_rate_pct')} "
            f"pf={r.get('profit_factor')} trades={r.get('trades')} id={r.get('backtest_id')}"
        )

    OUT_TXT.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    print(json.dumps({"project_id": project_id, "project_name": project_name, "out_json": str(OUT_JSON), "out_txt": str(OUT_TXT)}, indent=2))


if __name__ == "__main__":
    main()
