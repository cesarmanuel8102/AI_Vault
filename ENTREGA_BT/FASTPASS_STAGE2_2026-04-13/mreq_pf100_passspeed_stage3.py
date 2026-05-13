"""
PF100 pass-speed Stage 2:
- Align internal risk rails with MFFU Flex 50k evaluation shape
- Probe faster pass by controlled risk/capacity increases
"""

import json
import time
from base64 import b64encode
from collections import defaultdict
from datetime import datetime, date
from hashlib import sha256
from pathlib import Path

import requests

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SOURCE_FILE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_passspeed_stage3_results.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_passspeed_stage3_results.txt")


def headers():
    ts = str(int(time.time()))
    sig = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}


def api_post(endpoint, payload, timeout=90, retries=8, backoff=3):
    last = None
    for i in range(retries):
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(min(backoff * (2**i), 45))
    raise RuntimeError(f"api_post_failed endpoint={endpoint} err={last}")


def parse_pct(s):
    try:
        return float(str(s).replace("%", "").replace(" ", "").replace(",", ""))
    except Exception:
        return None


def parse_int(s):
    try:
        return int(float(str(s).replace(",", "").strip()))
    except Exception:
        return None


def upload_source(path):
    code = path.read_text(encoding="utf-8")
    return api_post("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=60)


def compile_project():
    c = api_post("compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId", "")
    if not cid:
        return False, "", c
    for _ in range(120):
        r = api_post("compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = r.get("state", "")
        if st in ("BuildSuccess", "BuildError", "BuildWarning", "BuildAborted"):
            return st == "BuildSuccess", cid, r
        time.sleep(2)
    return False, cid, {"error": "compile timeout"}


def set_parameters(params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    return api_post("projects/update", payload, timeout=60)


def create_backtest(compile_id, name):
    d = api_post("backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=90)
    bt = d.get("backtest", {})
    return bool(d.get("success")), bt.get("backtestId", ""), d


def poll_backtest(backtest_id, timeout_sec=2400):
    elapsed = 0
    while elapsed < timeout_sec:
        d = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
        bt = d.get("backtest", {})
        st = str(bt.get("status", ""))
        if "Completed" in st:
            time.sleep(2)
            d2 = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": backtest_id}, timeout=90)
            return True, d2.get("backtest", bt)
        if "Error" in st or "Runtime" in st:
            return False, bt
        time.sleep(10)
        elapsed += 10
    return False, {"status": "Timeout"}


def pass_metrics(bt, target_usd=3000.0, consistency_limit=0.50, min_days=2):
    perf = bt.get("totalPerformance", {}) or {}
    trades = perf.get("closedTrades", []) or []
    by_day = defaultdict(float)
    for tr in trades:
        et = tr.get("exitTime")
        pnl = tr.get("profitLoss")
        if et is None or pnl is None:
            continue
        try:
            dt = datetime.fromisoformat(str(et).replace("Z", "+00:00"))
        except Exception:
            continue
        by_day[date(dt.year, dt.month, dt.day)] += float(pnl)
    if not by_day:
        return {
            "pass_achieved": False,
            "pass_date": None,
            "calendar_days_to_pass": None,
            "trading_days_to_pass": 0,
            "consistency_pct_at_pass": None,
        }
    days = sorted(by_day.keys())
    first = days[0]
    cum = 0.0
    best = 0.0
    td = 0
    for d in days:
        pnl = by_day[d]
        if abs(pnl) > 1e-9:
            td += 1
        cum += pnl
        if pnl > best:
            best = pnl
        if cum >= target_usd and td >= min_days:
            c = best / cum if cum > 0 else None
            if c is not None and c <= consistency_limit:
                return {
                    "pass_achieved": True,
                    "pass_date": d.isoformat(),
                    "calendar_days_to_pass": (d - first).days + 1,
                    "trading_days_to_pass": td,
                    "consistency_pct_at_pass": round(c * 100.0, 2),
                }
    c = best / cum if cum > 0 else None
    return {
        "pass_achieved": False,
        "pass_date": None,
        "calendar_days_to_pass": None,
        "trading_days_to_pass": td,
        "consistency_pct_at_pass": round(c * 100.0, 2) if c is not None else None,
    }


def extract_metrics(bt):
    s = bt.get("statistics", {}) or {}
    rt = bt.get("runtimeStatistics", {}) or {}
    perf = bt.get("totalPerformance", {}) or {}
    trades = perf.get("closedTrades", []) or []
    q = [abs(float(t.get("quantity") or 0)) for t in trades if t.get("quantity") is not None]
    m = {
        "backtest_id": bt.get("backtestId"),
        "net_profit_pct": parse_pct(s.get("Net Profit")),
        "drawdown_pct": parse_pct(s.get("Drawdown")),
        "daily_loss_breaches": parse_int(rt.get("DailyLossBreaches")),
        "trailing_breaches": parse_int(rt.get("TrailingBreaches")),
        "closed_trades": len(trades),
        "avg_qty": round(sum(q) / len(q), 2) if q else None,
        "max_qty": max(q) if q else None,
    }
    m.update(pass_metrics(bt))
    return m


def base_cfg():
    return {
        "regime_mode": "PF100",
        "profile_mode": "PAYOUT_SAFE",
        "trade_nq": 1,
        "trade_m2k": 1,
        "entry_hour": 9,
        "entry_min": 40,
        "trailing_lock_mode": "EOD",
        "ext_use_vixy": 1,
        "ext_vixy_sma_period": 5,
        "ext_vixy_ratio_threshold": 1.03,
        "second_entry_enabled": 1,
        "second_entry_breakout_enabled": 1,
        "second_mom_entry_pct": 0.0025,
        "second_stop_atr_mult": 0.65,
        "second_target_atr_mult": 1.35,
        "second_max_hold_hours": 3,
        "max_trades_per_symbol_day": 2,
        # Align with MFFU 50k eval shape (no daily DLL; max loss approx 4%)
        "daily_loss_limit_pct": 0.040,
        "trailing_dd_limit_pct": 0.040,
    }


def candidates():
    b = base_cfg()
    rows = []

    def add(label, **kw):
        c = dict(b)
        c["label"] = label
        c.update(kw)
        rows.append(c)

    # Baseline control
    add("S3_A_CTRL_R125", risk_per_trade=0.0125, pf1_risk=0.0090, max_contracts_per_trade=5, pf1_maxc=2, second_risk_mult=0.70)
    # Hold-time compression + later second window
    add("S3_B_H4_LATE2ND", risk_per_trade=0.0125, pf1_risk=0.0090, max_contracts_per_trade=5, pf1_maxc=2, max_hold_hours=4, second_entry_hour=13, second_entry_min=10, second_mom_entry_pct=0.0018, second_risk_mult=0.80)
    add("S3_C_H3_LATE2ND", risk_per_trade=0.0125, pf1_risk=0.0090, max_contracts_per_trade=5, pf1_maxc=2, max_hold_hours=3, second_entry_hour=13, second_entry_min=10, second_mom_entry_pct=0.0015, second_risk_mult=0.85)
    add("S3_D_H3_TR3", risk_per_trade=0.0125, pf1_risk=0.0090, max_contracts_per_trade=5, pf1_maxc=2, max_hold_hours=3, max_trades_per_symbol_day=3, second_entry_hour=13, second_entry_min=20, second_mom_entry_pct=0.0015, second_risk_mult=0.85)
    # Risk escalation without changing core
    add("S3_E_R150_H4", risk_per_trade=0.0150, pf1_risk=0.0105, max_contracts_per_trade=6, pf1_maxc=3, max_hold_hours=4, second_entry_hour=13, second_entry_min=10, second_mom_entry_pct=0.0018, second_risk_mult=0.85)
    add("S3_F_R160_H4", risk_per_trade=0.0160, pf1_risk=0.0110, max_contracts_per_trade=6, pf1_maxc=3, max_hold_hours=4, second_entry_hour=13, second_entry_min=10, second_mom_entry_pct=0.0018, second_risk_mult=0.85)
    add("S3_G_R170_H4", risk_per_trade=0.0170, pf1_risk=0.0115, max_contracts_per_trade=6, pf1_maxc=3, max_hold_hours=4, second_entry_hour=13, second_entry_min=10, second_mom_entry_pct=0.0018, second_risk_mult=0.90)
    # Gate variants around baseline
    add("S3_H_R125_V1028", risk_per_trade=0.0125, pf1_risk=0.0090, max_contracts_per_trade=5, pf1_maxc=2, ext_vixy_ratio_threshold=1.028, max_hold_hours=4, second_entry_hour=13, second_entry_min=10, second_mom_entry_pct=0.0018, second_risk_mult=0.80)
    add("S3_I_R125_V1032", risk_per_trade=0.0125, pf1_risk=0.0090, max_contracts_per_trade=5, pf1_maxc=2, ext_vixy_ratio_threshold=1.032, max_hold_hours=4, second_entry_hour=13, second_entry_min=10, second_mom_entry_pct=0.0018, second_risk_mult=0.80)
    # Universe + gate toggles
    add("S3_J_MNQ_ONLY", trade_m2k=0, trade_nq=1, risk_per_trade=0.0125, pf1_risk=0.0090, max_contracts_per_trade=5, pf1_maxc=2, second_risk_mult=0.70)
    add("S3_K_MES_PLUS_MNQ", trade_m2k=0, trade_nq=1, trade_mym=0, risk_per_trade=0.0125, pf1_risk=0.0090, max_contracts_per_trade=5, pf1_maxc=2, second_risk_mult=0.70)
    add("S3_L_GATE_OFF", ext_use_vixy=0, trade_nq=1, trade_m2k=1, risk_per_trade=0.0125, pf1_risk=0.0090, max_contracts_per_trade=5, pf1_maxc=2, second_risk_mult=0.70)
    add("S3_M_GATE_OFF_MNQ", ext_use_vixy=0, trade_nq=1, trade_m2k=0, risk_per_trade=0.0125, pf1_risk=0.0090, max_contracts_per_trade=5, pf1_maxc=2, second_risk_mult=0.70)
    return rows


def run_challenge(compile_id, label, params):
    p = dict(params)
    p.update({"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2025, "end_month": 12, "end_day": 31})
    upd = set_parameters(p)
    if not upd.get("success"):
        return {"candidate": label, "error": f"set_parameters_failed: {upd}"}
    ok, bt_id, create = create_backtest(compile_id, f"{label}_CH2025_{int(time.time())}")
    if not ok or not bt_id:
        return {"candidate": label, "error": f"create_backtest_failed: {create}"}
    ok, bt = poll_backtest(bt_id)
    if not ok:
        return {"candidate": label, "backtest_id": bt_id, "error": f"poll_failed: {bt}"}
    m = extract_metrics(bt)
    m["candidate"] = label
    return m


def save(rows):
    payload = {"updated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z", "rows": rows}
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [f"updated_utc={payload['updated_utc']}", "", "=== PF100 PASSSPEED STAGE3 ==="]
    for r in rows:
        lines.append(
            f"{r.get('candidate')} np={r.get('net_profit_pct')} dd={r.get('drawdown_pct')} "
            f"dbr={r.get('daily_loss_breaches')} tbr={r.get('trailing_breaches')} "
            f"pass={r.get('pass_achieved')} pass_date={r.get('pass_date')} cal_days={r.get('calendar_days_to_pass')} "
            f"tr_days={r.get('trading_days_to_pass')} cons={r.get('consistency_pct_at_pass')} "
            f"trades={r.get('closed_trades')} avg_qty={r.get('avg_qty')} max_qty={r.get('max_qty')} "
            f"err={r.get('error')} id={r.get('backtest_id')}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main():
    up = upload_source(SOURCE_FILE)
    if not up.get("success"):
        raise RuntimeError(f"upload_failed: {up}")
    ok, compile_id, comp = compile_project()
    if not ok:
        raise RuntimeError(f"compile_failed: {comp}")
    rows = []
    for c in candidates():
        label = c["label"]
        cfg = {k: v for k, v in c.items() if k != "label"}
        m = run_challenge(compile_id, label, cfg)
        rows.append(m)
        save(rows)
        print(
            f"{label} pass={m.get('pass_achieved')} cal_days={m.get('calendar_days_to_pass')} "
            f"np={m.get('net_profit_pct')} dbr={m.get('daily_loss_breaches')} tbr={m.get('trailing_breaches')} "
            f"avg_qty={m.get('avg_qty')} max_qty={m.get('max_qty')}"
        )
        time.sleep(4)


if __name__ == "__main__":
    main()
