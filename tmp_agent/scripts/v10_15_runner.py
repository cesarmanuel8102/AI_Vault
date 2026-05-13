import base64
import hashlib
import json
import time
from pathlib import Path

import requests

USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
BASE = "https://www.quantconnect.com/api/v2"
CODE_PATH = Path("C:/AI_VAULT/tmp_agent/strategies/brain_v10/v10_15_qqq.py")
OUT_DIR = Path("C:/AI_VAULT/tmp_agent/strategies/brain_v10")
SIGNATURE = "V10_15_QQQ_SIGNATURE_20260408"

STAT_KEYS = [
    "Total Orders",
    "Average Win",
    "Average Loss",
    "Compounding Annual Return",
    "Drawdown",
    "Expectancy",
    "Start Equity",
    "End Equity",
    "Net Profit",
    "Sharpe Ratio",
    "Sortino Ratio",
    "Probabilistic Sharpe Ratio",
    "Loss Rate",
    "Win Rate",
    "Profit-Loss Ratio",
    "Alpha",
    "Beta",
    "Annual Standard Deviation",
    "Annual Variance",
    "Information Ratio",
    "Tracking Error",
    "Treynor Ratio",
    "Total Fees",
    "Estimated Strategy Capacity",
    "Lowest Capacity Asset",
    "Portfolio Turnover",
    "Drawdown Recovery",
]

TESTS = [
    {"name": "v10.15 QQQ IS 2023-2024", "period": "IS", "start_year": "2023", "end_year": "2024"},
    {"name": "v10.15 QQQ OOS 2025-2026", "period": "OOS", "start_year": "2025", "end_year": "2026"},
    {"name": "v10.15 QQQ Full 2023-2026", "period": "FULL", "start_year": "2023", "end_year": "2026"},
]


def auth_headers():
    ts = str(int(time.time()))
    sha = hashlib.sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{USER_ID}:{sha}".encode()).decode()
    return {
        "Authorization": f"Basic {b64}",
        "Timestamp": ts,
        "Content-Type": "application/json",
    }


def api_post(endpoint, payload, retries=5, pause=4):
    url = f"{BASE}/{endpoint}"
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, headers=auth_headers(), json=payload, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"API_FAIL endpoint={endpoint} attempt={attempt}/{retries} err={e}")
            if attempt == retries:
                raise
            time.sleep(pause * attempt)


def load_baselines():
    is_oos = json.loads(Path("C:/AI_VAULT/tmp_agent/strategies/brain_v10/v10_13b_is_oos_results.json").read_text(encoding="utf-8"))
    full_raw = json.loads(Path("C:/AI_VAULT/tmp_agent/strategies/brain_v10/v10_13b_full_verified.json").read_text(encoding="utf-8"))
    return {
        "IS": is_oos.get("v10.13b IS 2023-2024", {}),
        "OOS": is_oos.get("v10.13b OOS 2025-2026", {}),
        "FULL": full_raw.get("backtest", full_raw).get("statistics", {}),
    }


def to_float(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s or s == "?":
        return None
    try:
        if s.startswith("$"):
            s = s[1:]
        s = s.replace(",", "").replace("%", "")
        return float(s)
    except Exception:
        return None


def delta_text(curr, prev):
    a = to_float(curr)
    b = to_float(prev)
    if a is None or b is None:
        return "-"
    d = a - b
    if "%" in str(curr) or "%" in str(prev):
        return f"{d:+.3f} pp"
    return f"{d:+.3f}"


def print_table(period, stats, base):
    print("-" * 138)
    print(f"METRICS_TABLE period={period} rows=27")
    print(f"{'Metric':<34} {'v10.15_QQQ':>30} {'v10.13b_base':>30} {'Delta':>18}")
    print("-" * 138)
    for k in STAT_KEYS:
        c = str(stats.get(k, "?"))
        b = str(base.get(k, "?"))
        d = delta_text(c, b)
        print(f"{k:<34} {c:>30} {b:>30} {d:>18}")
    print("-" * 138)


def upload_and_verify(code):
    u = api_post("files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code})
    if not u.get("success"):
        raise RuntimeError(f"upload failed: {u}")
    rd = api_post("files/read", {"projectId": PROJECT_ID, "name": "main.py"})
    files = rd.get("files", [])
    if not files:
        raise RuntimeError(f"files/read empty: {rd}")
    remote = files[0].get("content", "")
    if SIGNATURE not in remote:
        raise RuntimeError("signature mismatch: remote main.py is not v10.15 code")


def compile_project():
    cr = api_post("compile/create", {"projectId": PROJECT_ID})
    compile_id = cr.get("compileId")
    state = cr.get("state")
    for _ in range(60):
        if state in ("BuildSuccess", "BuildError"):
            break
        time.sleep(3)
        rr = api_post("compile/read", {"projectId": PROJECT_ID, "compileId": compile_id})
        state = rr.get("state")
    if state != "BuildSuccess":
        raise RuntimeError(f"compile failed id={compile_id} state={state}")
    return compile_id


def run_backtest(name, compile_id):
    bt_create = api_post("backtests/create", {
        "projectId": PROJECT_ID,
        "compileId": compile_id,
        "backtestName": name,
    })
    bt = bt_create.get("backtest", bt_create)
    bt_id = bt.get("backtestId")
    if not bt_id:
        raise RuntimeError(f"backtest create failed: {bt_create}")

    for i in range(540):
        time.sleep(10)
        rr = api_post("backtests/read", {"projectId": PROJECT_ID, "backtestId": bt_id})
        backtest = rr.get("backtest", rr)
        progress = backtest.get("progress", 0)
        done = bool(backtest.get("completed", False))
        ptxt = f"{progress:.0%}" if isinstance(progress, float) else str(progress)
        if i % 6 == 0 or done:
            print(f"POLL idx={i+1} progress={ptxt} completed={done}")
        if done:
            return bt_id, backtest, rr
    raise RuntimeError(f"timeout bt_id={bt_id}")


def main():
    code = CODE_PATH.read_text(encoding="utf-8")
    baselines = load_baselines()
    results = {}

    for test in TESTS:
        print("\n" + "=" * 88)
        print(f"RUN {test['name']}")
        print("=" * 88)

        upload_and_verify(code)
        print("UPLOAD_VERIFY_OK")

        params = [
            {"key": "start_year", "value": test["start_year"]},
            {"key": "end_year", "value": test["end_year"]},
        ]
        pu = api_post("projects/update", {"projectId": PROJECT_ID, "parameters": params})
        if not pu.get("success"):
            raise RuntimeError(f"projects/update failed: {pu}")
        print(f"PARAMS_OK start_year={test['start_year']} end_year={test['end_year']}")

        compile_id = compile_project()
        print(f"COMPILE_OK id={compile_id}")

        bt_id, backtest, raw_resp = run_backtest(test["name"], compile_id)
        print(f"BACKTEST_DONE bt_id={bt_id} status={backtest.get('status')}")

        row = {
            "status": backtest.get("status"),
            "error": backtest.get("error"),
            "bt_id": bt_id,
            "start_year": test["start_year"],
            "end_year": test["end_year"],
        }

        stats = backtest.get("statistics", {})
        for k in STAT_KEYS:
            row[k] = stats.get(k, "?")
        results[test["name"]] = row

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"v10_15_{test['period'].lower()}_raw.json").write_text(
            json.dumps(raw_resp, indent=2, default=str), encoding="utf-8"
        )

        print_table(test["period"], row, baselines[test["period"]])

    out = OUT_DIR / "v10_15_qqq_is_oos_full_results.json"
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"RESULTS_SAVED {out}")


if __name__ == "__main__":
    main()
