import base64
import hashlib
import json
import re
import time
from datetime import datetime, timezone, date
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 31204537  # research-only
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase89_utility_first_pullback_instrument.py")
BASE_PARAMS_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/params_p20_fastpass_qf3_ref_2026-04-22.json")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase89_utility_first_pullback_instrument_2026-05-12.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase89_utility_first_pullback_instrument_2026-05-12.txt")


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
    for i in range(8):
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


def build_research_upload_source(raw_code):
    raw_code = re.sub(
        r"def _orb_diag_inc\(self, slot_label, key, n=1\):.*?\n\s*def _orb_slot_params\(self, slot_label\):",
        "def _orb_diag_inc(self, slot_label, key, n=1):\n        return\n\n    def _orb_slot_params(self, slot_label):",
        raw_code,
        flags=re.S,
    )
    out_lines = []
    for line in raw_code.splitlines():
        stripped = line.lstrip()
        if "_orb_diag_inc(" in line and not stripped.startswith("def _orb_diag_inc"):
            indent = line[: len(line) - len(line.lstrip())]
            out_lines.append(f"{indent}pass")
        else:
            out_lines.append(line)
    code = "\n".join(out_lines)
    code = re.sub(
        r"def _publish_runtime\(self, equity, dd\):.*?\n\s*def OnEndOfAlgorithm\(self\):",
        'def _publish_runtime(self, equity, dd):\n'
        '        self.SetRuntimeStatistic("Mode", "UF89")\n'
        '        self.SetRuntimeStatistic("Equity", f"{equity:.2f}")\n'
        '        self.SetRuntimeStatistic("DrawdownPct", f"{dd*100.0:.2f}")\n'
        '        self.SetRuntimeStatistic("TrORB", str(self.alpha_closed_trades["ORB"]))\n'
        '        self.SetRuntimeStatistic("Orb1Fills", str(self.orb_slot_fills["ORB1"]))\n'
        '        self.SetRuntimeStatistic("Orb2Fills", str(self.orb_slot_fills["ORB2"]))\n'
        '        self.SetRuntimeStatistic("Orb3Fills", str(self.orb_slot_fills["ORB3"]))\n'
        '        self.SetRuntimeStatistic("PbFills", str(getattr(self, "pb_fills", 0)))\n'
        '\n'
        '    def OnEndOfAlgorithm(self):',
        code,
        flags=re.S,
    )
    return code


def upload_main(uid, tok):
    code = build_research_upload_source(MAIN_PATH.read_text(encoding="utf-8"))
    r = post(uid, tok, "files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=180)
    if not r.get("success", False):
        raise RuntimeError(f"files/update failed: {r}")


def compile_project(uid, tok):
    c = post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(200):
        rd = post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = rd.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            if st != "BuildSuccess":
                raise RuntimeError(f"compile failed: {st} | {rd}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")


def run_backtest(uid, tok, compile_id, name):
    bid = None
    err = None
    for _ in range(45):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=120)
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        err = str(bc)
        if "no spare nodes available" in err.lower():
            time.sleep(45)
            continue
        return {"status": "CreateFailed", "error": err}
    if not bid:
        return {"status": "CreateFailed", "error": err or "missing backtest id"}

    bt = {}
    for _ in range(540):
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

    return {
        "status": str(bt.get("status", "")),
        "backtest_id": bid,
        "np_pct": pf(s.get("Net Profit")),
        "dd_pct": pf(s.get("Drawdown")),
        "orders": pi(s.get("Total Orders")),
        "dbr": pi(rt(rts, "DailyLossBreaches")),
        "tbr": pi(rt(rts, "TrailingBreaches")),
        "tr_orb": pi(rt(rts, "TrORB")),
        "orb1_fills": pi(rt(rts, "Orb1Fills")),
        "orb2_fills": pi(rt(rts, "Orb2Fills")),
        "orb3_fills": pi(rt(rts, "Orb3Fills")),
        "pb_fills": pi(rt(rts, "PbFills")),
    }


def set_params(uid, tok, params):
    wr = post(
        uid,
        tok,
        "projects/update",
        {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]},
        timeout=90,
    )
    if not wr.get("success", False):
        raise RuntimeError(f"projects/update failed: {wr}")


def weeks_between(d0, d1):
    return max(1.0, (d1 - d0).days / 7.0)


def utility_score(row, weeks):
    np_pct = row.get("np_pct") or 0.0
    orders = row.get("orders") or 0
    weekly_pct = np_pct / weeks
    trades_per_week = (row.get("tr_orb") or 0) / weeks
    negativity_penalty = 0.0 if np_pct > 0 else abs(np_pct) * 1.5
    return weekly_pct * 10.0 + trades_per_week * 0.15 - negativity_penalty


def scenario_summary(row, weeks, target_low=5.0, target_high=10.0):
    weekly_pct = (row.get("np_pct") or 0.0) / weeks
    return {
        "weekly_pct": round(weekly_pct, 4),
        "trades_per_week": round((row.get("tr_orb") or 0) / weeks, 4),
        "target_band_hit": target_low <= weekly_pct <= target_high,
    }


def evaluate_candidate(payload, scenarios):
    weighted = 0.0
    hits = 0
    for sname, meta in scenarios:
        row = payload["scenarios"][sname]
        weeks = meta["weeks"]
        ss = scenario_summary(row, weeks)
        row["utility"] = ss
        weighted += utility_score(row, weeks) * meta["weight"]
        hits += 1 if ss["target_band_hit"] else 0
    payload["utility_score"] = round(weighted, 6)
    payload["target_band_hits"] = hits
    payload["positive_scenarios"] = sum(1 for sname, _ in scenarios if (payload["scenarios"][sname].get("np_pct") or 0.0) > 0)
    return payload


def build_candidates():
    return [
        ("UF_PB_I_BASE", {
            "or_risk": 0.030,
            "or_target_atr_mult": 2.00,
            "max_contracts_per_trade": 50,
            "max_open_positions": 8,
            "max_trades_per_symbol_day": 6,
            "or_slot2_enabled": 1,
            "or_slot2_risk_mult": 1.75,
            "or_slot3_enabled": 1,
            "guard_enabled": 0,
            "daily_loss_limit_pct": 0.12,
            "trailing_dd_limit_pct": 0.20,
            "alpha_pb_enabled": 1,
            "pb_hour": 10,
            "pb_min": 45,
            "pb_break_extension_atr": 0.30,
            "pb_retest_band_atr": 0.25,
            "pb_stop_atr_mult": 0.55,
            "pb_target_atr_mult": 1.80,
            "pb_risk_mult": 0.80,
            "pb_min_session_mom_pct": 0.0004,
            "pb_mes_risk_mult": 1.00,
            "pb_mnq_risk_mult": 1.00,
            "pb_mes_extension_mult": 1.00,
            "pb_mnq_extension_mult": 1.00,
            "pb_mes_target_mult": 1.00,
            "pb_mnq_target_mult": 1.00,
        }),
        ("UF_PB_I_A", {
            "or_risk": 0.030,
            "or_target_atr_mult": 2.00,
            "max_contracts_per_trade": 50,
            "max_open_positions": 8,
            "max_trades_per_symbol_day": 6,
            "or_slot2_enabled": 1,
            "or_slot2_risk_mult": 1.75,
            "or_slot3_enabled": 1,
            "guard_enabled": 0,
            "daily_loss_limit_pct": 0.12,
            "trailing_dd_limit_pct": 0.20,
            "alpha_pb_enabled": 1,
            "pb_hour": 10,
            "pb_min": 45,
            "pb_break_extension_atr": 0.30,
            "pb_retest_band_atr": 0.25,
            "pb_stop_atr_mult": 0.55,
            "pb_target_atr_mult": 1.80,
            "pb_risk_mult": 0.80,
            "pb_min_session_mom_pct": 0.0004,
            "pb_mes_risk_mult": 0.85,
            "pb_mnq_risk_mult": 1.15,
            "pb_mes_extension_mult": 1.05,
            "pb_mnq_extension_mult": 0.95,
            "pb_mes_target_mult": 0.95,
            "pb_mnq_target_mult": 1.10,
        }),
        ("UF_PB_I_B", {
            "or_risk": 0.030,
            "or_target_atr_mult": 2.00,
            "max_contracts_per_trade": 50,
            "max_open_positions": 8,
            "max_trades_per_symbol_day": 6,
            "or_slot2_enabled": 1,
            "or_slot2_risk_mult": 1.75,
            "or_slot3_enabled": 1,
            "guard_enabled": 0,
            "daily_loss_limit_pct": 0.12,
            "trailing_dd_limit_pct": 0.20,
            "alpha_pb_enabled": 1,
            "pb_hour": 10,
            "pb_min": 45,
            "pb_break_extension_atr": 0.30,
            "pb_retest_band_atr": 0.25,
            "pb_stop_atr_mult": 0.55,
            "pb_target_atr_mult": 1.80,
            "pb_risk_mult": 0.80,
            "pb_min_session_mom_pct": 0.0004,
            "pb_mes_risk_mult": 1.15,
            "pb_mnq_risk_mult": 0.85,
            "pb_mes_extension_mult": 0.95,
            "pb_mnq_extension_mult": 1.05,
            "pb_mes_target_mult": 1.10,
            "pb_mnq_target_mult": 0.95,
        }),
        ("UF_PB_I_C", {
            "or_risk": 0.035,
            "or_target_atr_mult": 2.00,
            "max_contracts_per_trade": 60,
            "max_open_positions": 8,
            "max_trades_per_symbol_day": 6,
            "or_slot2_enabled": 1,
            "or_slot2_risk_mult": 1.75,
            "or_slot3_enabled": 1,
            "guard_enabled": 0,
            "daily_loss_limit_pct": 0.14,
            "trailing_dd_limit_pct": 0.22,
            "alpha_pb_enabled": 1,
            "pb_hour": 10,
            "pb_min": 45,
            "pb_break_extension_atr": 0.30,
            "pb_retest_band_atr": 0.20,
            "pb_stop_atr_mult": 0.55,
            "pb_target_atr_mult": 1.90,
            "pb_risk_mult": 0.90,
            "pb_min_session_mom_pct": 0.0004,
            "pb_mes_risk_mult": 0.80,
            "pb_mnq_risk_mult": 1.20,
            "pb_mes_extension_mult": 1.10,
            "pb_mnq_extension_mult": 0.90,
            "pb_mes_target_mult": 0.95,
            "pb_mnq_target_mult": 1.15,
        }),
        ("UF_PB_I_D", {
            "or_risk": 0.030,
            "or_target_atr_mult": 2.00,
            "max_contracts_per_trade": 50,
            "max_open_positions": 8,
            "max_trades_per_symbol_day": 6,
            "or_slot2_enabled": 1,
            "or_slot2_risk_mult": 1.75,
            "or_slot3_enabled": 1,
            "guard_enabled": 0,
            "daily_loss_limit_pct": 0.12,
            "trailing_dd_limit_pct": 0.20,
            "alpha_pb_enabled": 1,
            "pb_hour": 11,
            "pb_min": 0,
            "pb_break_extension_atr": 0.32,
            "pb_retest_band_atr": 0.18,
            "pb_stop_atr_mult": 0.50,
            "pb_target_atr_mult": 1.90,
            "pb_risk_mult": 0.75,
            "pb_min_session_mom_pct": 0.0005,
            "pb_mes_risk_mult": 0.90,
            "pb_mnq_risk_mult": 1.10,
            "pb_mes_extension_mult": 1.00,
            "pb_mnq_extension_mult": 0.95,
            "pb_mes_target_mult": 1.00,
            "pb_mnq_target_mult": 1.10,
        }),
        ("UF_PB_I_E", {
            "or_risk": 0.030,
            "or_target_atr_mult": 2.00,
            "max_contracts_per_trade": 50,
            "max_open_positions": 8,
            "max_trades_per_symbol_day": 6,
            "or_slot2_enabled": 1,
            "or_slot2_risk_mult": 1.75,
            "or_slot3_enabled": 1,
            "guard_enabled": 0,
            "daily_loss_limit_pct": 0.12,
            "trailing_dd_limit_pct": 0.20,
            "alpha_pb_enabled": 1,
            "pb_hour": 10,
            "pb_min": 50,
            "pb_break_extension_atr": 0.34,
            "pb_retest_band_atr": 0.28,
            "pb_stop_atr_mult": 0.60,
            "pb_target_atr_mult": 1.75,
            "pb_risk_mult": 0.80,
            "pb_min_session_mom_pct": 0.0006,
            "pb_mes_risk_mult": 1.00,
            "pb_mnq_risk_mult": 1.05,
            "pb_mes_extension_mult": 1.05,
            "pb_mnq_extension_mult": 0.95,
            "pb_mes_target_mult": 1.00,
            "pb_mnq_target_mult": 1.05,
        }),
    ]

def save_partial(meta):
    OUT_JSON.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main():
    uid, tok = creds()
    upload_main(uid, tok)
    cid = compile_project(uid, tok)

    base = {
        "alpha_mr_enabled": 0,
        "or_risk": 0.009,
        "max_contracts_per_trade": 12,
        "max_trades_per_symbol_day": 2,
        "or_minutes": 15,
        "or_breakout_buffer_pct": 0.0007,
        "or_target_atr_mult": 1.55,
        "or_stop_atr_mult": 0.75,
        "or_min_gap_pct": 0.0015,
        "or_mom_entry_pct": 0.001,
        "or_min_width_atr": 0.22,
        "or_max_width_atr": 1.1,
        "or_require_gap_alignment": 1,
        "trailing_lock_mode": "EOD",
        "guard_enabled": 1,
        "trade_mnq": 1,
        "trade_mes": 1,
        "allow_shorts": 1,
        "alpha_orb_enabled": 1,
        "alpha_stress_enabled": 1,
    }
    candidates = build_candidates()
    scenarios = [
        ("IS_2022_2024", {"dates": {"start_year": 2022, "start_month": 1, "start_day": 1, "end_year": 2024, "end_month": 12, "end_day": 31}, "weeks": weeks_between(date(2022, 1, 1), date(2024, 12, 31)), "weight": 0.30}),
        ("OOS_2025_2026Q1", {"dates": {"start_year": 2025, "start_month": 1, "start_day": 1, "end_year": 2026, "end_month": 3, "end_day": 31}, "weeks": weeks_between(date(2025, 1, 1), date(2026, 3, 31)), "weight": 0.50}),
        ("STRESS_2020", {"dates": {"start_year": 2020, "start_month": 1, "start_day": 1, "end_year": 2020, "end_month": 12, "end_day": 31}, "weeks": weeks_between(date(2020, 1, 1), date(2020, 12, 31)), "weight": 0.20}),
    ]

    rows = []
    results = {}
    for label, ov in candidates:
        cfg = dict(base)
        cfg.update(ov)
        results[label] = {"overrides": ov, "scenarios": {}, "target_band_hits": 0}
        for sname, meta in scenarios:
            params = dict(cfg)
            params.update(meta["dates"])
            set_params(uid, tok, params)
            rr = run_backtest(uid, tok, cid, f"{label}_{sname}_{int(time.time())}")
            rr.update({"candidate": label, "scenario": sname, "overrides": ov})
            rows.append(rr)
            results[label]["scenarios"][sname] = rr
            save_partial({
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "compile_id": cid,
                "results": results,
                "rows": rows,
            })
        evaluate_candidate(results[label], scenarios)

    ranked = sorted(
        [{"label": k, **v} for k, v in results.items()],
        key=lambda x: (x.get("target_band_hits", 0), x.get("utility_score", -999999)),
        reverse=True,
    )

    best = ranked[0]["label"] if ranked else None
    top = ranked[0] if ranked else {}

    final = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "compile_id": cid,
        "objective": "UTILITY_FIRST_EXPERIMENT",
        "target_weekly_pct_band": [5.0, 10.0],
        "scenarios": {name: meta for name, meta in scenarios},
        "results": results,
        "rows": rows,
        "ranked": ranked,
        "best_label": best,
        "best_summary": {
            "utility_score": top.get("utility_score"),
            "target_band_hits": top.get("target_band_hits"),
            "positive_scenarios": top.get("positive_scenarios"),
        } if top else {},
    }
    OUT_JSON.write_text(json.dumps(final, indent=2), encoding="utf-8")

    lines = []
    lines.append(f"generated_at_utc={final['generated_at_utc']}")
    lines.append(f"project_id={PROJECT_ID}")
    lines.append(f"compile_id={cid}")
    lines.append("objective=UTILITY_FIRST_EXPERIMENT")
    lines.append("target_weekly_pct_band=5.0..10.0")
    lines.append("")
    for item in ranked:
        lines.append(
            f"{item['label']} utility_score={item.get('utility_score')} target_hits={item.get('target_band_hits')} positive_scenarios={item.get('positive_scenarios')}"
        )
        for sname, meta in scenarios:
            row = item["scenarios"][sname]
            u = row.get("utility") or {}
            lines.append(
                f"  {sname}: np={row.get('np_pct')} weekly={u.get('weekly_pct')} trades_wk={u.get('trades_per_week')} "
                f"dd={row.get('dd_pct')} orders={row.get('orders')} tr_orb={row.get('tr_orb')} target_hit={u.get('target_band_hit')}"
            )
        lines.append(f"  overrides={item['overrides']}")
        lines.append("")
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "best_label": best, "out_json": str(OUT_JSON), "out_txt": str(OUT_TXT)}, indent=2))


if __name__ == "__main__":
    main()
