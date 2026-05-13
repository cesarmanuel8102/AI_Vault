import base64
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_main.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_active_validation_2026-04-21.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/camino_b_active_validation_2026-04-21.txt")


def load_creds():
    d = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    uid = str(d.get("user_id") or d.get("userId") or "").strip()
    tok = str(d.get("api_token") or d.get("apiToken") or d.get("token") or "").strip()
    if not uid or not tok:
        raise RuntimeError("Credenciales QC invalidas")
    return uid, tok


def headers(uid, tok, ts=None):
    ts = int(ts or time.time())
    sig = hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    basic = base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {"Authorization": f"Basic {basic}", "Timestamp": str(ts), "Content-Type": "application/json"}


def api_post(uid, tok, endpoint, payload, timeout=120):
    ts = int(time.time())
    r = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts), json=payload, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
    if r.status_code >= 400:
        data.setdefault("success", False)
        data.setdefault("errors", [f"HTTP {r.status_code}"])
    if data.get("success", False):
        return data
    errs = " ".join(data.get("errors") or [])
    m = re.search(r"Server Time:\s*(\d+)", errs)
    if m:
        ts2 = int(m.group(1)) - 1
        r2 = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts2), json=payload, timeout=timeout)
        try:
            return r2.json()
        except Exception:
            return {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
    return data


def parse_float(x):
    try:
        return float(str(x).replace("%", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def parse_int(x):
    try:
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return None


def get_rt(rt, key):
    if isinstance(rt, dict):
        return rt.get(key)
    if isinstance(rt, list):
        for item in rt:
            if isinstance(item, dict) and str(item.get("name") or item.get("Name")) == key:
                return item.get("value") or item.get("Value")
    return None


def upload_main(uid, tok):
    payload = {"projectId": PROJECT_ID, "name": "main.py", "content": MAIN_PATH.read_text(encoding="utf-8")}
    resp = api_post(uid, tok, "files/update", payload, timeout=180)
    if not resp.get("success", False):
        raise RuntimeError(f"files/update main.py failed: {resp}")


def set_params(uid, tok, params):
    payload = {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]}
    resp = api_post(uid, tok, "projects/update", payload, timeout=60)
    if not resp.get("success", False):
        raise RuntimeError(f"projects/update failed: {resp}")


def compile_project(uid, tok):
    c = api_post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(180):
        r = api_post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = r.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(f"Compile no exitoso: {st} | {r}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def run_backtest(uid, tok, cid, name):
    bt = api_post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": cid, "backtestName": name}, timeout=120)
    bid = ((bt.get("backtest") or {}).get("backtestId"))
    if not bid:
        return {"status": "CreateFailed", "error": str(bt)}
    for _ in range(360):
        rd = api_post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        b = rd.get("backtest") or {}
        st = str(b.get("status", ""))
        if "Completed" in st:
            s = b.get("statistics") or {}
            rt = b.get("runtimeStatistics") or {}
            return {
                "status": st,
                "backtest_id": bid,
                "np_pct": parse_float(s.get("Net Profit")),
                "dd_pct": parse_float(s.get("Drawdown")),
                "sharpe": parse_float(s.get("Sharpe Ratio")),
                "orders": parse_int(s.get("Total Orders")),
                "dbr": parse_int(get_rt(rt, "DailyLossBreaches")),
                "tbr": parse_int(get_rt(rt, "TrailingBreaches")),
                "stress_trades": parse_int(get_rt(rt, "StressTrades")),
                "normal_trades": parse_int(get_rt(rt, "NormalTrades")),
                "stress_days": parse_int(get_rt(rt, "ExternalStressDays")),
                "error": b.get("error") or b.get("message"),
            }
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            return {"status": st, "backtest_id": bid, "error": (b.get("error") or b.get("message") or "backtest failed")}
        time.sleep(10)
    return {"status": "Timeout", "backtest_id": bid}


def main():
    uid, tok = load_creds()

    common = {
        "phase_mode": "T2_DUAL",
        "initial_cash": "50000",
        "allow_shorts": "1",
        "trade_nq": "1",
        "trade_m2k": "0",
        "trade_mym": "0",
        "entry_hour": "9",
        "entry_min": "40",
        "flatten_hour": "15",
        "flatten_min": "58",
        "ext_use_vixy": "1",
        "ext_vixy_sma_period": "5",
        "ext_use_vix": "0",
        "ext_min_signals": "1",
        "ext_rv_threshold": "1.0",
        "ext_gap_z_threshold": "99.0",
        "ext_gap_abs_threshold": "1.0",
        "daily_loss_limit_pct": "0.018",
        "daily_profit_lock_pct": "0.040",
        "trailing_dd_limit_pct": "0.035",
        "trailing_lock_mode": "EOD",
        "max_open_positions": "2",
        "max_trades_per_symbol_day": "2",
        "stress_risk_per_trade": "0.0040",
        "stress_stop_atr_mult": "0.80",
        "stress_target_atr_mult": "1.80",
        "stress_breakout_buffer_pct": "0.0007",
        "stress_max_contracts_per_trade": "2",
        "normal_stop_atr_mult": "0.60",
        "normal_gap_fill_fraction": "0.70",
        "normal_min_gap_pct": "0.0",
        "normal_use_trend_filter": "0",
        "normal_max_contracts_per_trade": "4",
    }

    candidates = [
        {
            "label": "CB_ACTIVE_E4",
            "overrides": {
                "ext_vixy_ratio_threshold": "1.03",
                "normal_risk_per_trade": "0.0090",
                "normal_gap_atr_mult": "0.22",
                "normal_max_gap_pct": "0.0090",
            },
        },
        {
            "label": "CB_ACTIVE_E5",
            "overrides": {
                "ext_vixy_ratio_threshold": "1.03",
                "normal_risk_per_trade": "0.0060",
                "normal_gap_atr_mult": "0.22",
                "normal_max_gap_pct": "0.0070",
            },
        },
        {
            "label": "CB_ACTIVE_E5_1025",
            "overrides": {
                "ext_vixy_ratio_threshold": "1.025",
                "normal_risk_per_trade": "0.0060",
                "normal_gap_atr_mult": "0.22",
                "normal_max_gap_pct": "0.0070",
            },
        },
        {
            "label": "CB_ACTIVE_E5_1035",
            "overrides": {
                "ext_vixy_ratio_threshold": "1.035",
                "normal_risk_per_trade": "0.0060",
                "normal_gap_atr_mult": "0.22",
                "normal_max_gap_pct": "0.0070",
            },
        },
        {
            "label": "CB_ACTIVE_E5_R65",
            "overrides": {
                "ext_vixy_ratio_threshold": "1.03",
                "normal_risk_per_trade": "0.0065",
                "normal_gap_atr_mult": "0.22",
                "normal_max_gap_pct": "0.0070",
            },
        },
    ]

    windows = [
        {
            "name": "LIVE_WEEK_2026_04_14_04_21",
            "dates": {
                "start_year": "2026",
                "start_month": "4",
                "start_day": "14",
                "end_year": "2026",
                "end_month": "4",
                "end_day": "21",
            },
        },
        {
            "name": "CH_2026_Q1",
            "dates": {
                "start_year": "2026",
                "start_month": "1",
                "start_day": "1",
                "end_year": "2026",
                "end_month": "3",
                "end_day": "31",
            },
        },
        {
            "name": "OOS_2025_2026Q1",
            "dates": {
                "start_year": "2025",
                "start_month": "1",
                "start_day": "1",
                "end_year": "2026",
                "end_month": "3",
                "end_day": "31",
            },
        },
        {
            "name": "STRESS_2020",
            "dates": {
                "start_year": "2020",
                "start_month": "1",
                "start_day": "1",
                "end_year": "2020",
                "end_month": "12",
                "end_day": "31",
            },
        },
    ]

    out = {
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "project_id": PROJECT_ID,
        "candidates": [c["label"] for c in candidates],
        "results": [],
        "verdict": [],
    }

    upload_main(uid, tok)
    set_params(uid, tok, common)
    cid = compile_project(uid, tok)
    out["compile_id"] = cid

    for c in candidates:
        for w in windows:
            p = dict(common)
            p.update(c["overrides"])
            p.update(w["dates"])
            p["label"] = c["label"]
            set_params(uid, tok, p)
            r = run_backtest(uid, tok, cid, f"CBACT_{c['label']}_{w['name']}_{int(time.time())}")
            r.update({"candidate": c["label"], "window": w["name"]})
            out["results"].append(r)
            OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    grouped = {}
    for row in out["results"]:
        grouped.setdefault(row["candidate"], {})[row["window"]] = row

    for label, m in grouped.items():
        live = m.get("LIVE_WEEK_2026_04_14_04_21", {})
        ch = m.get("CH_2026_Q1", {})
        oos = m.get("OOS_2025_2026Q1", {})
        stress = m.get("STRESS_2020", {})
        pass_live_active = (live.get("orders") or 0) >= 1
        pass_ch = (ch.get("np_pct") or -999) >= 6.0 and (ch.get("dbr") or 0) == 0 and (ch.get("tbr") or 0) == 0
        pass_oos = (oos.get("np_pct") or -999) > 0 and (oos.get("dbr") or 0) == 0 and (oos.get("tbr") or 0) == 0
        pass_stress = (stress.get("np_pct") or -999) >= 0 and (stress.get("dbr") or 0) == 0 and (stress.get("tbr") or 0) == 0
        score = 0.0
        score += (live.get("orders") or 0) * 0.5
        score += max(0.0, (ch.get("np_pct") or 0)) * 2.0
        score += max(0.0, (oos.get("np_pct") or 0))
        score += max(0.0, (stress.get("np_pct") or 0)) * 2.5
        score -= max(0.0, (oos.get("dd_pct") or 0))
        score -= max(0.0, (stress.get("dd_pct") or 0))
        if not pass_oos:
            score -= 100.0
        if not pass_stress:
            score -= 100.0
        out["verdict"].append(
            {
                "candidate": label,
                "score": round(score, 4),
                "overall_pass": bool(pass_live_active and pass_ch and pass_oos and pass_stress),
                "pass_live_active": pass_live_active,
                "pass_ch": pass_ch,
                "pass_oos": pass_oos,
                "pass_stress": pass_stress,
                "live_orders": live.get("orders"),
                "ch_np": ch.get("np_pct"),
                "oos_np": oos.get("np_pct"),
                "oos_tbr": oos.get("tbr"),
                "stress_np": stress.get("np_pct"),
                "stress_tbr": stress.get("tbr"),
            }
        )

    out["verdict"] = sorted(out["verdict"], key=lambda x: x["score"], reverse=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"generated_at_utc={out.get('generated_at_utc')}",
        f"project_id={PROJECT_ID}",
        f"compile_id={out.get('compile_id','')}",
        "",
        "=== RESULTS ===",
    ]
    for r in out["results"]:
        lines.append(
            f"{r.get('candidate')} {r.get('window')} np={r.get('np_pct')} dd={r.get('dd_pct')} "
            f"dbr={r.get('dbr')} tbr={r.get('tbr')} orders={r.get('orders')} "
            f"stress_trades={r.get('stress_trades')} normal_trades={r.get('normal_trades')} id={r.get('backtest_id')}"
        )
    lines.append("")
    lines.append("=== VERDICT ===")
    for v in out["verdict"]:
        lines.append(
            f"{v['candidate']} score={v['score']} overall_pass={v['overall_pass']} "
            f"live={v['pass_live_active']} ch={v['pass_ch']} oos={v['pass_oos']} stress={v['pass_stress']} "
            f"live_orders={v['live_orders']} ch_np={v['ch_np']} oos_np={v['oos_np']} stress_np={v['stress_np']}"
        )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "out_json": str(OUT_JSON), "out_txt": str(OUT_TXT)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
