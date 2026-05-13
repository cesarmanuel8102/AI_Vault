import base64
import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/bt_last_week_live_profile_2026-04-22.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/bt_last_week_live_profile_2026-04-22.txt")


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
            m = re.search(r"Server Time:\s*(\d+)", " ".join(d.get("errors") or []))
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


def rt(runtime, key):
    if isinstance(runtime, dict):
        return runtime.get(key)
    if isinstance(runtime, list):
        for it in runtime:
            if isinstance(it, dict) and str(it.get("name") or it.get("Name")) == key:
                return it.get("value") or it.get("Value")
    return None


def compile_project(uid, tok):
    c = post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(180):
        r = post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = r.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(f"Compile failed: {st} | {r}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def run_backtest(uid, tok, cid, name):
    bid = None
    for _ in range(40):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": cid, "backtestName": name}, timeout=120)
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        if "no spare nodes available" in str(bc).lower():
            time.sleep(45)
            continue
        raise RuntimeError(f"backtests/create failed: {bc}")
    if not bid:
        raise RuntimeError("Backtest id missing")

    bt = {}
    for _ in range(480):
        rd = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        bt = rd.get("backtest") or {}
        st = str(bt.get("status", ""))
        if "Completed" in st:
            break
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            raise RuntimeError(f"Backtest ended in {st}: {bt.get('error') or bt.get('message')}")
        time.sleep(10)

    rd2 = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
    return rd2.get("backtest") or bt


def current_project_params(uid, tok):
    rd = post(uid, tok, "projects/read", {"projectId": PROJECT_ID}, timeout=60)
    projs = rd.get("projects") or []
    if not projs:
        raise RuntimeError(f"projects/read empty: {rd}")
    params = projs[0].get("parameters") or []
    out = {}
    for p in params:
        k = p.get("key")
        v = p.get("value")
        if k is not None:
            out[str(k)] = str(v) if v is not None else ""
    return out


def set_project_params(uid, tok, param_dict):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in param_dict.items()]}
    wr = post(uid, tok, "projects/update", payload, timeout=90)
    if not wr.get("success", False):
        raise RuntimeError(f"projects/update failed: {wr}")


def summarize(bt):
    s = bt.get("statistics") or {}
    rt_stats = bt.get("runtimeStatistics") or {}
    perf = bt.get("totalPerformance") or {}
    trades = perf.get("closedTrades") or []
    by_day = {}
    for t in trades:
        et = t.get("exitTime")
        pnl = t.get("profitLoss")
        if et is None or pnl is None:
            continue
        try:
            dt = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue
        dkey = f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
        by_day[dkey] = by_day.get(dkey, 0.0) + float(pnl)

    return {
        "status": bt.get("status"),
        "backtest_id": bt.get("backtestId"),
        "np_pct": pf(s.get("Net Profit")),
        "dd_pct": pf(s.get("Drawdown")),
        "sharpe": pf(s.get("Sharpe Ratio")),
        "sortino": pf(s.get("Sortino Ratio")),
        "win_rate_pct": pf(s.get("Win Rate")),
        "profit_factor": pf(s.get("Profit Factor")),
        "expectancy": pf(s.get("Expectancy")),
        "total_orders": pi(s.get("Total Orders")),
        "closed_trades": len(trades),
        "trade_days": len(by_day),
        "best_day_usd": max(by_day.values()) if by_day else 0.0,
        "worst_day_usd": min(by_day.values()) if by_day else 0.0,
        "daily_loss_breaches": pi(rt(rt_stats, "DailyLossBreaches")),
        "trailing_breaches": pi(rt(rt_stats, "TrailingBreaches")),
        "consistency_pct": pf(rt(rt_stats, "ConsistencyPct")),
        "external_stress_days": pi(rt(rt_stats, "ExternalStressDays")),
        "alpha_pnl_mr": pf(rt(rt_stats, "PnlMR")),
        "alpha_pnl_orb": pf(rt(rt_stats, "PnlORB")),
        "alpha_pnl_stress": pf(rt(rt_stats, "PnlST")),
        "alpha_tr_mr": pi(rt(rt_stats, "TrMR")),
        "alpha_tr_orb": pi(rt(rt_stats, "TrORB")),
        "alpha_tr_stress": pi(rt(rt_stats, "TrST")),
        "by_day": by_day,
    }


def main():
    uid, tok = creds()
    today = date(2026, 4, 22)
    end_date = today - timedelta(days=1)
    start_date = end_date - timedelta(days=6)

    original = current_project_params(uid, tok)
    work = dict(original)
    work.update(
        {
            "start_year": start_date.year,
            "start_month": start_date.month,
            "start_day": start_date.day,
            "end_year": end_date.year,
            "end_month": end_date.month,
            "end_day": end_date.day,
        }
    )

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "window": {"start": str(start_date), "end": str(end_date)},
        "profile_label": original.get("profile_label"),
        "steps": [],
    }

    try:
        set_project_params(uid, tok, work)
        out["steps"].append({"step": "params_set_for_week_bt", "count": len(work)})
        cid = compile_project(uid, tok)
        out["steps"].append({"step": "compile_ok", "compileId": cid})
        bt_name = f"LAST_WEEK_LIVE_PROFILE_{int(time.time())}"
        bt = run_backtest(uid, tok, cid, bt_name)
        summary = summarize(bt)
        out["backtest_name"] = bt_name
        out["summary"] = summary
    finally:
        # Restore full original parameter set used by live profile
        set_project_params(uid, tok, original)
        out["steps"].append({"step": "params_restored", "count": len(original)})

    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    s = out["summary"]
    lines = [
        f"generated_at_utc={out['generated_at_utc']}",
        f"profile_label={out.get('profile_label')}",
        f"window={out['window']['start']}..{out['window']['end']}",
        f"backtest_id={s.get('backtest_id')}",
        f"status={s.get('status')}",
        "",
        f"net_profit_pct={s.get('np_pct')}",
        f"drawdown_pct={s.get('dd_pct')}",
        f"sharpe={s.get('sharpe')}",
        f"sortino={s.get('sortino')}",
        f"win_rate_pct={s.get('win_rate_pct')}",
        f"profit_factor={s.get('profit_factor')}",
        f"expectancy={s.get('expectancy')}",
        f"total_orders={s.get('total_orders')}",
        f"closed_trades={s.get('closed_trades')}",
        f"trade_days={s.get('trade_days')}",
        f"best_day_usd={round(s.get('best_day_usd') or 0.0, 2)}",
        f"worst_day_usd={round(s.get('worst_day_usd') or 0.0, 2)}",
        f"daily_loss_breaches={s.get('daily_loss_breaches')}",
        f"trailing_breaches={s.get('trailing_breaches')}",
        f"consistency_pct={s.get('consistency_pct')}",
        f"external_stress_days={s.get('external_stress_days')}",
        "",
        f"alpha_pnl_mr={s.get('alpha_pnl_mr')}",
        f"alpha_pnl_orb={s.get('alpha_pnl_orb')}",
        f"alpha_pnl_stress={s.get('alpha_pnl_stress')}",
        f"alpha_tr_mr={s.get('alpha_tr_mr')}",
        f"alpha_tr_orb={s.get('alpha_tr_orb')}",
        f"alpha_tr_stress={s.get('alpha_tr_stress')}",
    ]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(OUT_JSON))


if __name__ == "__main__":
    main()
