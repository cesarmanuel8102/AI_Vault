
import base64
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 31204537
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase70_pf200_orb_ml_probe_filtercal.py")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase70_pf200_orb_ml_probe_filtercal_2026-05-05.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase70_pf200_orb_ml_probe_filtercal_2026-05-05.txt")

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
    for _ in range(8):
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
                d2 = r2.json()
            except Exception:
                d2 = {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
            if d2.get("success", False):
                return d2
            d = d2
        last = d
        time.sleep(5)
    return last or {"success": False, "errors": ["request failed"]}

def upload_main(uid, tok):
    code = MAIN_PATH.read_text(encoding="utf-8")
    r = post(uid, tok, "files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=180)
    if not r.get("success", False):
        raise RuntimeError(f"files/update failed: {r}")

def compile_project(uid, tok):
    c = post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=120)
    cid = c.get("compileId")
    if not cid:
        raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(240):
        rd = post(uid, tok, "compile/read", {"projectId": PROJECT_ID, "compileId": cid}, timeout=60)
        st = rd.get("state", "")
        if st in ("BuildSuccess", "BuildWarning", "BuildError", "BuildAborted"):
            return cid, rd
        time.sleep(2)
    raise RuntimeError("compile timeout")

def run_backtest(uid, tok, compile_id, name):
    bid = None
    for _ in range(45):
        bc = post(uid, tok, "backtests/create", {"projectId": PROJECT_ID, "compileId": compile_id, "backtestName": name}, timeout=120)
        bid = ((bc.get("backtest") or {}).get("backtestId"))
        if bid:
            break
        err = str(bc)
        if "no spare nodes available" in err.lower():
            time.sleep(45)
            continue
        raise RuntimeError(f"backtests/create failed: {bc}")
    if not bid:
        raise RuntimeError("no backtest id")
    bt = {}
    for _ in range(900):
        rd = post(uid, tok, "backtests/read", {"projectId": PROJECT_ID, "backtestId": bid}, timeout=120)
        bt = rd.get("backtest") or {}
        st = str(bt.get("status", ""))
        if "Completed" in st:
            return bid, bt
        if any(x in st for x in ("Error", "Runtime", "Aborted", "Cancelled")):
            raise RuntimeError(f"backtest failed: {st} | {bt.get('error') or bt.get('message')}")
        time.sleep(10)
    raise RuntimeError("backtest timeout")

def read_logs(uid, tok, backtest_id, query=' '):
    start = 0
    lines = []
    while True:
        r = post(uid, tok, "backtests/read/log", {"projectId": PROJECT_ID, "backtestId": backtest_id, "start": start, "end": start + 200, "query": query}, timeout=120)
        logs = r.get("logs") or []
        lines.extend(logs)
        total = int(r.get("length") or len(lines))
        start += len(logs)
        if len(lines) >= total or not logs:
            break
    return lines

def main():
    uid, tok = creds()
    upload_main(uid, tok)
    compile_id, compile_read = compile_project(uid, tok)
    if compile_read.get("state") != "BuildSuccess":
        raise RuntimeError(f"compile failed: {compile_read}")
    name = f"PHASE67_ORB_ML_PROBE_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    backtest_id, bt = run_backtest(uid, tok, compile_id, name)
    logs = read_logs(uid, tok, backtest_id, query=' ')
    summary = None
    for line in logs:
        if "PHASE67_SUMMARY " in line:
            summary = json.loads(line.split("PHASE67_SUMMARY ", 1)[1].strip())
            break
    out = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "compile_id": compile_id,
        "backtest_id": backtest_id,
        "status": bt.get("status"),
        "statistics": bt.get("statistics") or {},
        "runtimeStatistics": bt.get("runtimeStatistics") or {},
        "logs": logs,
        "summary": summary,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding='utf-8')
    lines = [
        'phase=67_ml_probe',
        f'project_id={PROJECT_ID}',
        f'backtest_id={backtest_id}',
        f'status={bt.get("status")}',
        f'ml_rows={(bt.get("runtimeStatistics") or {}).get("MLRows")}',
        f'ml_models={(bt.get("runtimeStatistics") or {}).get("MLModels")}',
    ]
    if summary is None:
        lines.append('summary=missing')
    else:
        lines.append(f"dataset_rows={summary.get('dataset_rows')}")
        lines.append(f"slot_counts={summary.get('slot_counts')}")
        lines.append(f"symbol_counts={summary.get('symbol_counts')}")
        lines.append(f"failures={summary.get('failures')}")
        for item in summary.get('results', []):
            if item.get('status') != 'ok':
                lines.append(f"{item.get('slot')}_{item.get('side')} status={item.get('status')} train_n={item.get('train_n')}")
            else:
                m=item['metrics']
                lines.append(
                    f"{item['slot']}_{item['side']} thr={item['picked']['threshold']} "
                    f"IS(auc={m['IS']['auc']},prec={m['IS']['precision']},sig={m['IS']['signal_rate']},base={m['IS']['base_rate']},n={m['IS']['n']}) "
                    f"OOS(auc={m['OOS']['auc']},prec={m['OOS']['precision']},sig={m['OOS']['signal_rate']},base={m['OOS']['base_rate']},n={m['OOS']['n']}) "
                    f"STRESS(auc={m['STRESS']['auc']},prec={m['STRESS']['precision']},sig={m['STRESS']['signal_rate']},base={m['STRESS']['base_rate']},n={m['STRESS']['n']})"
                )
    OUT_TXT.write_text('\n'.join(lines), encoding='utf-8')
    print(OUT_TXT)

if __name__ == '__main__':
    main()
