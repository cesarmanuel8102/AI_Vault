import base64
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_SOURCE = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase11_pf200_entryfill_consistency.py")
FAST_PARAMS_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/params_p20_fastpass_qf3_ref_2026-04-22.json")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/live_deploy_p20_fast_2026-04-22.json")


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


def api_post(uid, tok, endpoint, payload, timeout=90):
    last = None
    for i in range(6):
        ts = int(time.time())
        try:
            r = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts), json=payload, timeout=timeout)
            try:
                data = r.json()
            except Exception:
                data = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
            if r.status_code >= 400:
                data.setdefault("success", False)
            if data.get("success", False):
                return data
            errs = " ".join(data.get("errors") or [])
            m = re.search(r"Server Time:\s*(\d+)", errs)
            if m:
                ts2 = int(m.group(1)) - 1
                r2 = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts2), json=payload, timeout=timeout)
                try:
                    d2 = r2.json()
                except Exception:
                    d2 = {"success": False, "errors": [f"HTTP {r2.status_code}", r2.text[:500]]}
                if d2.get("success", False):
                    return d2
                data = d2
            last = data
        except Exception as e:
            last = {"success": False, "errors": [str(e)]}
        time.sleep(min(3 * (i + 1), 20))
    return last or {"success": False, "errors": ["request failed"]}


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


def main():
    uid, tok = load_creds()
    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "profile": "P20_QF3_REF_FAST",
        "steps": [],
    }

    code = MAIN_SOURCE.read_text(encoding="utf-8")
    upd = api_post(uid, tok, "files/update", {"projectId": PROJECT_ID, "name": "main.py", "content": code}, timeout=180)
    if not upd.get("success", False):
        raise RuntimeError(f"files/update failed: {upd}")
    out["steps"].append({"step": "files_update_main", "data": {"source": str(MAIN_SOURCE), "success": True}})

    fast = json.loads(FAST_PARAMS_PATH.read_text(encoding="utf-8"))
    params = {
        "profile_label": "P20_QF3_REF_FAST",
        "trade_mnq": 1,
        "trade_mes": 1,
        "allow_shorts": 1,
    }
    params.update(fast)

    p = api_post(
        uid,
        tok,
        "projects/update",
        {"projectId": PROJECT_ID, "parameters": [{"key": k, "value": str(v)} for k, v in params.items()]},
        timeout=90,
    )
    if not p.get("success", False):
        raise RuntimeError(f"projects/update failed: {p}")
    out["steps"].append({"step": "project_params_set", "data": {"count": len(params), "params_path": str(FAST_PARAMS_PATH)}})

    cid = compile_project(uid, tok)
    out["steps"].append({"step": "compile_done", "data": {"compileId": cid}})

    live_before = api_post(uid, tok, "live/read", {"projectId": PROJECT_ID}, timeout=60)
    before_status = str(live_before.get("status") or "")
    out["steps"].append(
        {
            "step": "live_before",
            "data": {
                "status": before_status,
                "deployId": live_before.get("deployId"),
                "brokerage": live_before.get("brokerage"),
                "nodeId": live_before.get("nodeId"),
            },
        }
    )

    if before_status.lower() in ("running", "initializing", "loggingin", "runtimeerror"):
        stop = api_post(uid, tok, "live/update/stop", {"projectId": PROJECT_ID}, timeout=60)
        out["steps"].append({"step": "live_stop", "data": {"success": stop.get("success"), "errors": stop.get("errors")}})
        for i in range(40):
            time.sleep(3)
            chk = api_post(uid, tok, "live/read", {"projectId": PROJECT_ID}, timeout=60)
            st = str(chk.get("status") or "")
            if st.lower() not in ("running", "initializing", "loggingin"):
                out["steps"].append({"step": "live_stopped_confirm", "data": {"attempt": i + 1, "status": st}})
                break

    node_id = live_before.get("nodeId") or "LN-64d4787830461ee45574254f643f69b3"
    payload = {
        "projectId": PROJECT_ID,
        "compileId": cid,
        "nodeId": node_id,
        "versionId": "-1",
        "automaticRedeploy": True,
        "brokerage": {"id": "QuantConnectBrokerage"},
        "dataProviders": {"QuantConnectBrokerage": {"id": "QuantConnectBrokerage"}},
    }

    create = None
    errs = []
    for retry in range(12):
        r = api_post(uid, tok, "live/create", payload, timeout=120)
        if r.get("success"):
            create = r
            out["steps"].append({"step": "live_create_ok", "data": {"retry": retry + 1, "deployId": r.get("deployId")}})
            break
        msg = " ".join(r.get("errors") or [])
        if "still being processing" in msg.lower():
            wait_s = 20
            m = re.search(r"try again in (\d+) seconds", msg, flags=re.IGNORECASE)
            if m:
                wait_s = max(5, int(m.group(1)) + 2)
            time.sleep(wait_s)
            continue
        errs.append({"retry": retry + 1, "errors": r.get("errors"), "response": r})
        break

    if create is None:
        out["steps"].append({"step": "live_create_failed", "data": errs})
        OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"ok": False, "out_json": str(OUT_JSON), "errors": errs}, indent=2, ensure_ascii=False))
        return

    deploy_id = create.get("deployId")
    confirm = None
    for i in range(60):
        time.sleep(3)
        chk = api_post(uid, tok, "live/read", {"projectId": PROJECT_ID}, timeout=60)
        st = str(chk.get("status") or "").lower()
        if chk.get("deployId") == deploy_id and st in ("running", "initializing", "loggingin"):
            confirm = chk
            out["steps"].append(
                {
                    "step": "live_confirm",
                    "data": {
                        "attempt": i + 1,
                        "deployId": chk.get("deployId"),
                        "status": chk.get("status"),
                        "launched": chk.get("launched"),
                        "brokerage": chk.get("brokerage"),
                        "nodeId": chk.get("nodeId"),
                    },
                }
            )
            break

    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "out_json": str(OUT_JSON),
                "deployId": deploy_id,
                "status": (confirm or {}).get("status"),
                "launched": (confirm or {}).get("launched"),
                "brokerage": (confirm or {}).get("brokerage"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
