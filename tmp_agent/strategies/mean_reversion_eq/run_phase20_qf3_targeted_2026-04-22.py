import base64
import hashlib
import json
import re
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase11_pf200_entryfill_consistency.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase20_qf3_targeted_2026-04-22.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase20_qf3_targeted_2026-04-22.txt")

CHALLENGE_TARGET_PCT = 0.06


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


def perf_metrics(bt):
    perf = bt.get("totalPerformance") or {}
    trades = perf.get("closedTrades") or []
    start = pf((perf.get("portfolioStatistics") or {}).get("startEquity")) or 50000.0

    by_month = defaultdict(float)
    by_day = defaultdict(float)
    gp, gl = 0.0, 0.0
    wins, losses = 0, 0
    max_l, cur_l = 0, 0

    for t in trades:
        et, pnl = t.get("exitTime"), t.get("profitLoss")
        if et is None or pnl is None:
            continue
        p = float(pnl)
        try:
            dt = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue
        by_month[f"{dt.year:04d}-{dt.month:02d}"] += p
        by_day[f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"] += p
        if p >= 0:
            gp += p
            wins += 1
            cur_l = 0
        else:
            gl += abs(p)
            losses += 1
            cur_l += 1
            max_l = max(max_l, cur_l)

    target_usd = start * CHALLENGE_TARGET_PCT
    challenge_hit = False
    challenge_days = None
    if by_day:
        cum = 0.0
        for i, d in enumerate(sorted(by_day.keys())):
            cum += by_day[d]
            if (not challenge_hit) and cum >= target_usd:
                challenge_hit = True
                challenge_days = i + 1
                break

    arr = []
    eq = float(start)
    for m in sorted(by_month.keys()):
        pnl = by_month[m]
        arr.append(0.0 if eq <= 0 else (pnl / eq) * 100.0)
        eq += pnl

    total = sum(by_day.values())
    best = max(by_day.values()) if by_day else 0.0
    wr = 100.0 * wins / max(1, wins + losses)
    return {
        "closed_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(wr, 2),
        "profit_factor_calc": round(gp / gl, 3) if gl > 0 else None,
        "max_consec_losses": int(max_l),
        "best_day_share_pct": round(999.0 if total <= 0 else (best / total) * 100.0, 2),
        "monthly_mean_pct": round(statistics.mean(arr), 3) if arr else None,
        "monthly_median_pct": round(statistics.median(arr), 3) if arr else None,
        "monthly_count": len(arr),
        "challenge_hit": challenge_hit,
        "challenge_days": challenge_days,
    }


def run_bt(uid, tok, cid, name):
    bid = None
    err = None
    for _ in range(40):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": cid, "backtestName": name}, timeout=120)
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        err = str(bc)
        if "no spare nodes available" in err.lower():
            time.sleep(45)
            continue
        return {"status": "CreateFailed", "error": err}
    if not bid:
        return {"status": "CreateFailed", "error": err or "no id"}

    bt = {}
    for _ in range(480):
        rd = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        bt = rd.get("backtest") or {}
        st = str(bt.get("status", ""))
        if "Completed" in st:
            break
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": bt.get("error") or bt.get("message")}
        time.sleep(10)

    rd2 = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
    bt = rd2.get("backtest") or bt
    s = bt.get("statistics") or {}
    rts = bt.get("runtimeStatistics") or {}
    row = {
        "status": str(bt.get("status", "")),
        "backtest_id": bid,
        "np_pct": pf(s.get("Net Profit")),
        "dd_pct": pf(s.get("Drawdown")),
        "dbr": pi(rt(rts, "DailyLossBreaches")),
        "tbr": pi(rt(rts, "TrailingBreaches")),
        "orders": pi(s.get("Total Orders")),
        "stress_days": pi(rt(rts, "ExternalStressDays")),
        "pnl_mr": pf(rt(rts, "PnlMR")),
        "pnl_orb": pf(rt(rts, "PnlORB")),
        "pnl_stress": pf(rt(rts, "PnlST")),
        "tr_mr": pi(rt(rts, "TrMR")),
        "tr_orb": pi(rt(rts, "TrORB")),
        "tr_stress": pi(rt(rts, "TrST")),
    }
    row.update(perf_metrics(bt))
    return row


def main():
    uid, tok = creds()
    code = MAIN_PATH.read_text(encoding="utf-8")
    u = post(uid, tok, "files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=180)
    if not u.get("success", False):
        raise RuntimeError(u)
    clr = post(uid, tok, "projects/update", {"projectId": PROJECT_ID, "parameters": []}, timeout=60)
    if not clr.get("success", False):
        raise RuntimeError(clr)
    c = post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(c)
    for _ in range(180):
        cr = post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = cr.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(cr)
            break
        time.sleep(2)

    base = {
        "alpha_mr_enabled": 0,
        "n_risk": 0.013,
        "or_risk": 0.0090,
        "max_contracts_per_trade": 12,
        "max_trades_per_symbol_day": 2,
        "or_minutes": 15,
        "or_breakout_buffer_pct": 0.0007,
        "or_target_atr_mult": 1.55,
        "or_stop_atr_mult": 0.75,
        "or_min_gap_pct": 0.0015,
        "or_mom_entry_pct": 0.0010,
        "or_min_width_atr": 0.22,
        "or_max_width_atr": 1.10,
        "or_require_gap_alignment": 1,
        "trailing_lock_mode": "EOD",
        "guard_enabled": 1,
    }

    candidates = [
        ("P20_QF3_REF", {}),
        ("P20_QF3_VIX1025", {"ext_vixy_ratio_threshold": 1.025}),
        ("P20_QF3_VIX1020", {"ext_vixy_ratio_threshold": 1.020}),
        ("P20_QF3_VIX1015", {"ext_vixy_ratio_threshold": 1.015}),
        (
            "P20_QF3_STRESS_RELAX",
            {"s_min_gap_pct": 0.0055, "s_intraday_mom_pct": 0.0007, "s_target_atr_mult": 1.65, "s_risk": 0.0038},
        ),
        (
            "P20_QF3_VIX1020_STRESS_RELAX",
            {
                "ext_vixy_ratio_threshold": 1.020,
                "s_min_gap_pct": 0.0050,
                "s_intraday_mom_pct": 0.0006,
                "s_target_atr_mult": 1.65,
                "s_risk": 0.0038,
            },
        ),
        ("P20_QF3_ORRISK_UP", {"or_risk": 0.0105}),
        ("P20_QF3_ORRISK_LOW", {"or_risk": 0.0082}),
        ("P20_QF3_TP135_SL070", {"or_target_atr_mult": 1.35, "or_stop_atr_mult": 0.70}),
    ]

    scenarios = [
        ("CYCLE_2025_H1", {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2025, "end_month": 6, "end_day": 30}),
        ("CYCLE_2025_H2", {"start_year": 2025, "start_month": 7, "start_day": 1, "end_year": 2025, "end_month": 12, "end_day": 31}),
        ("CYCLE_2026_Q1", {"start_year": 2026, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}),
        ("STRESS_2020", {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}),
    ]

    rows = []
    for label, ov in candidates:
        cfg = dict(base)
        cfg.update(ov)
        for sname, dates in scenarios:
            p = dict(cfg)
            p.update(dates)
            su = post(
                uid,
                tok,
                "projects/update",
                {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in p.items()]},
                timeout=60,
            )
            if not su.get("success", False):
                raise RuntimeError(su)
            rr = run_bt(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
            rr.update({"candidate": label, "scenario": sname, "overrides": ov})
            rows.append(rr)
            OUT_JSON.write_text(
                json.dumps(
                    {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "compile_id": cid, "rows": rows},
                    indent=2,
                ),
                encoding="utf-8",
            )

    lines = [f"generated_at_utc={datetime.now(timezone.utc).isoformat()}", f"compile_id={cid}", ""]
    for r in rows:
        lines.append(
            f"{r.get('candidate')} {r.get('scenario')} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} "
            f"closed={r.get('closed_trades')} hit6={r.get('challenge_hit')} days6={r.get('challenge_days')} "
            f"best_day%={r.get('best_day_share_pct')} wr={r.get('win_rate_pct')} pf={r.get('profit_factor_calc')} "
            f"pnl_mr={r.get('pnl_mr')} pnl_orb={r.get('pnl_orb')} pnl_st={r.get('pnl_stress')} "
            f"tr_mr={r.get('tr_mr')} tr_orb={r.get('tr_orb')} tr_st={r.get('tr_stress')} "
            f"orders={r.get('orders')} stress_days={r.get('stress_days')} id={r.get('backtest_id')}"
        )
    lines += ["", "target_phase20: push H2 to non-negative without sacrificing H1 speed and low breaches"]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(OUT_JSON))


if __name__ == "__main__":
    main()
