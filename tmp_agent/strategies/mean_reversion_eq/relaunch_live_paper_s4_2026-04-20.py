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
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/live_relaunch_s4_restore_2026-04-20.json")


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
    ts = int(time.time())
    r = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts), json=payload, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"success": False, "errors": [f"HTTP {r.status_code}", r.text[:500]]}
    if r.status_code >= 400:
        data.setdefault("success", False)
        if "errors" not in data:
            data["errors"] = [f"HTTP {r.status_code}"]
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


def compile_project(uid, tok):
    c = api_post(uid, tok, "compile/create", {"projectId": PROJECT_ID}, timeout=90)
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
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "project_id": PROJECT_ID,
        "steps": [],
    }

    pr = api_post(uid, tok, "projects/read", {"projectId": PROJECT_ID}, timeout=60)
    projects = pr.get("projects") or []
    if not projects:
        raise RuntimeError(f"projects/read failed: {pr}")
    out["steps"].append(
        {
            "step": "project_read",
            "data": {
                "name": projects[0].get("name"),
                "organizationId": projects[0].get("organizationId"),
                "leanVersionId": projects[0].get("leanVersionId"),
            },
        }
    )

    cid = compile_project(uid, tok)
    out["steps"].append({"step": "compile_done", "data": {"compileId": cid, "state": "BuildSuccess"}})

    live_before = api_post(uid, tok, "live/read", {"projectId": PROJECT_ID}, timeout=60)
    out["steps"].append(
        {
            "step": "live_before_stop",
            "data": {
                "status": live_before.get("status"),
                "deployId": live_before.get("deployId"),
            },
        }
    )

    if str(live_before.get("status") or "").lower() in ("running", "initializing", "loggingin", "runtimeerror"):
        stop = api_post(uid, tok, "live/update/stop", {"projectId": PROJECT_ID}, timeout=60)
        out["steps"].append({"step": "live_stop", "data": {"success": stop.get("success"), "errors": stop.get("errors")}})
        for i in range(20):
            time.sleep(3)
            chk = api_post(uid, tok, "live/read", {"projectId": PROJECT_ID}, timeout=60)
            st = str(chk.get("status") or "")
            if st.lower() not in ("running", "initializing", "loggingin"):
                out["steps"].append({"step": "live_stopped_confirm", "data": {"attempt": i + 1, "status": st}})
                break

    node_id = "LN-64d4787830461ee45574254f643f69b3"
    out["steps"].append({"step": "node_selected", "data": {"nodeId": node_id}})

    payloads = [
        {
            "projectId": PROJECT_ID,
            "compileId": cid,
            "nodeId": node_id,
            "versionId": "-1",
            "automaticRedeploy": True,
            "brokerage": {"id": "QuantConnectBrokerage"},
        },
        {
            "projectId": PROJECT_ID,
            "compileId": cid,
            "nodeId": node_id,
            "versionId": "-1",
            "automaticRedeploy": True,
            "brokerage": {"id": "PaperBrokerage"},
            "dataProviders": {"QuantConnectBrokerage": {"id": "QuantConnectBrokerage"}},
        },
        {
            "projectId": PROJECT_ID,
            "compileId": cid,
            "nodeId": node_id,
            "versionId": "-1",
            "automaticRedeploy": True,
            "brokerage": {"id": "PaperBrokerage"},
        },
    ]

    create_data = None
    create_errors = []
    for idx, p in enumerate(payloads, 1):
        resp = api_post(uid, tok, "live/create", p, timeout=120)
        if resp.get("success"):
            create_data = resp
            out["steps"].append({"step": "live_create_response", "data": {"attempt": idx, "response": resp}})
            break
        create_errors.append({"attempt": idx, "errors": resp.get("errors"), "response": resp})

    if create_data is None:
        out["steps"].append({"step": "live_create_failed", "data": create_errors})
        OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"ok": False, "out_json": str(OUT_JSON), "errors": create_errors}, indent=2, ensure_ascii=False))
        return

    deploy_id = create_data.get("deployId")
    live_confirm = None
    for i in range(20):
        time.sleep(3)
        chk = api_post(uid, tok, "live/read", {"projectId": PROJECT_ID}, timeout=60)
        if chk.get("deployId") == deploy_id and str(chk.get("status") or "").lower() in ("running", "initializing", "loggingin"):
            live_confirm = chk
            out["steps"].append(
                {
                    "step": "live_running_confirm",
                    "data": {
                        "attempt": i + 1,
                        "deployId": chk.get("deployId"),
                        "status": chk.get("status"),
                        "launched": chk.get("launched"),
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
                "status": (live_confirm or {}).get("status"),
                "launched": (live_confirm or {}).get("launched"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
