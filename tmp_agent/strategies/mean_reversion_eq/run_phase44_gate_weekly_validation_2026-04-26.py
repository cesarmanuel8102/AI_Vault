import base64, hashlib, json, re, time, zlib
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
import requests

BASE="https://www.quantconnect.com/api/v2"; PROJECT_ID=29652652
ROOT=Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq")
SECRETS_PATH=Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH=ROOT/"main_phase44_regime_gate_v1.py"
RESTORE_MAIN_PATH=ROOT/"main_phase11_pf200_entryfill_consistency.py"
BASE_PARAMS_PATH=ROOT/"params_p20_fastpass_qf3_ref_2026-04-22.json"
OUT_JSON=ROOT/"phase44_gate_weekly_validation_2026-04-26.json"
OUT_TXT=ROOT/"phase44_gate_weekly_validation_2026-04-26.txt"


def creds():
    d=json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    return str(d.get("user_id") or d.get("userId")).strip(), str(d.get("api_token") or d.get("apiToken") or d.get("token")).strip()

def hdr(uid,tok,ts=None):
    ts=int(ts or time.time())
    sig=hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    auth=base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {"Authorization":f"Basic {auth}","Timestamp":str(ts),"Content-Type":"application/json"}

def post(uid,tok,ep,payload,timeout=120,retries=8):
    last=None
    for i in range(retries):
        try:
            r=requests.post(f"{BASE}/{ep}",headers=hdr(uid,tok),json=payload,timeout=timeout)
            try: d=r.json()
            except Exception: d={"success":False,"errors":[f"HTTP {r.status_code}",r.text[:500]]}
            if d.get("success",False): return d
            m=re.search(r"Server Time:\s*(\d+)"," ".join(d.get("errors") or []))
            if m:
                r2=requests.post(f"{BASE}/{ep}",headers=hdr(uid,tok,int(m.group(1))-1),json=payload,timeout=timeout)
                try: d2=r2.json()
                except Exception: d2={"success":False,"errors":[f"HTTP {r2.status_code}",r2.text[:500]]}
                if d2.get("success",False): return d2
                d=d2
            last=d
        except Exception as e:
            last={"success":False,"errors":[str(e)]}
        time.sleep(min(3*(i+1),20))
    return last or {"success":False,"errors":["request failed"]}

def pf(x):
    try: return float(str(x).replace("%","").replace("$","").replace(",","").strip())
    except Exception: return None

def pi(x):
    try: return int(float(str(x).replace(",","").strip()))
    except Exception: return None

def rt(runtime,key):
    if isinstance(runtime,dict): return runtime.get(key)
    if isinstance(runtime,list):
        for it in runtime:
            if isinstance(it,dict) and str(it.get("name") or it.get("Name"))==key:
                return it.get("value") or it.get("Value")
    return None

def upload(uid,tok,path):
    code=path.read_text(encoding="utf-8")
    if len(code)>63000:
        payload=base64.b64encode(zlib.compress(code.encode("utf-8"),9)).decode("ascii")
        code="import base64,zlib\nexec(zlib.decompress(base64.b64decode('"+payload+"')).decode('utf-8'))\n"
    r=post(uid,tok,"files/update",{"projectId":PROJECT_ID,"name":"main.py","content":code},timeout=180)
    if not r.get("success",False):
        raise RuntimeError(f"files/update failed: {r}")

def compile_project(uid,tok):
    c=post(uid,tok,"compile/create",{"projectId":PROJECT_ID},timeout=120)
    cid=c.get("compileId")
    if not cid: raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(220):
        rd=post(uid,tok,"compile/read",{"projectId":PROJECT_ID,"compileId":cid},timeout=60)
        st=rd.get("state","")
        if st in ("BuildSuccess","BuildWarning","BuildError","BuildAborted"):
            if st!="BuildSuccess": raise RuntimeError(f"compile failed: {st} | {rd}")
            return cid
        time.sleep(2)
    raise RuntimeError("compile timeout")

def set_params(uid,tok,params):
    wr=post(uid,tok,"projects/update",{"projectId":PROJECT_ID,"parameters":[{"key":k,"value":str(v)} for k,v in params.items()]},timeout=90)
    if not wr.get("success",False):
        raise RuntimeError(f"projects/update failed: {wr}")

def run_bt(uid,tok,cid,name):
    bid=None
    for _ in range(50):
        bc=post(uid,tok,"backtests/create",{"projectId":PROJECT_ID,"compileId":cid,"backtestName":name},timeout=120)
        bid=((bc.get("backtest") or {}).get("backtestId"))
        if bid: break
        if "no spare nodes available" in str(bc).lower():
            time.sleep(45); continue
        return {"status":"CreateFailed","error":str(bc)}
    if not bid: return {"status":"CreateFailed","error":"missing backtest id"}
    bt={}
    for _ in range(360):
        rd=post(uid,tok,"backtests/read",{"projectId":PROJECT_ID,"backtestId":bid},timeout=120)
        bt=rd.get("backtest") or {}; st=str(bt.get("status",""))
        if "Completed" in st: break
        if any(x in st for x in ("Error","Runtime","Aborted","Cancelled")):
            return {"status":st,"backtest_id":bid,"error":bt.get("error") or bt.get("message")}
        time.sleep(10)
    rd2=post(uid,tok,"backtests/read",{"projectId":PROJECT_ID,"backtestId":bid},timeout=120)
    bt=rd2.get("backtest") or bt
    s=bt.get("statistics") or {}; rts=bt.get("runtimeStatistics") or {}
    return {
        "status":str(bt.get("status","")),"backtest_id":bid,
        "np_pct":pf(s.get("Net Profit")),"dd_pct":pf(s.get("Drawdown")),"orders":pi(s.get("Total Orders")),
        "dbr":pi(rt(rts,"DailyLossBreaches")),"tbr":pi(rt(rts,"TrailingBreaches")),
        "days_to_6pct":pi(rt(rts,"DaysTo6Pct")),"best_day_usd":pf(rt(rts,"BestDayUSD")),
        "consistency_pct":pf(rt(rts,"ConsistencyPct")),"pf":pf(rt(rts,"ProfitFactor")),
        "tr_orb":pi(rt(rts,"TrORB")),"tr_volx":pi(rt(rts,"TrVOLX")),"tr_st":pi(rt(rts,"TrST")),
        "campaign_gate":rt(rts,"CampaignGate"),"gate_fast":rt(rts,"GateFast"),"gate_pass":rt(rts,"GatePass"),
        "gate_vixy":pf(rt(rts,"GateVIXY")),"gate_spyrv10":pf(rt(rts,"GateSPYRV10")),"gate_qqqrng10":pf(rt(rts,"GateQQQRNG10")),
    }

def base_params():
    b=json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8"))
    b.update({"trade_mnq":1,"trade_mes":1,"allow_shorts":1,"challenge_target_pct":0.06})
    return b

def candidates():
    fast=json.loads((ROOT/"params_p44_gate_fast15_r0135_2026-04-26.json").read_text(encoding="utf-8"))
    passany=json.loads((ROOT/"params_p44_gate_passany_r0135_2026-04-26.json").read_text(encoding="utf-8"))
    return [
        ("P44_GATE_FAST15_R0135", fast),
        ("P44_GATE_PASSANY_R0135", passany),
    ]

def windows():
    starts=[]
    d=date(2025,1,1)
    while d<=date(2025,4,15):
        starts.append(d); d+=timedelta(days=7)
    d=date(2026,1,1)
    while d<=date(2026,4,8):
        starts.append(d); d+=timedelta(days=7)
    out=[]
    max_end=date(2026,4,24)
    for st in starts:
        en=min(st+timedelta(days=44), max_end)
        if en<=st: continue
        out.append((f"W_{st.isoformat()}_{en.isoformat()}",{"start_year":st.year,"start_month":st.month,"start_day":st.day,"end_year":en.year,"end_month":en.month,"end_day":en.day}))
    return out

def summarize(rows):
    by={}
    for r in rows:
        by.setdefault(r["candidate"],[]).append(r)
    summary={}
    for cand,rs in by.items():
        good=[r for r in rs if "Completed" in str(r.get("status"))]
        active=[r for r in good if (r.get("orders") or 0)>0 or abs(r.get("np_pct") or 0)>0.0001]
        hits=[r for r in good if (r.get("days_to_6pct") or -1)>0]
        clean=[r for r in good if (r.get("dbr") or 0)==0 and (r.get("tbr") or 0)==0 and (r.get("dd_pct") is not None and r.get("dd_pct")<=3.5)]
        clean_hits=[r for r in clean if (r.get("days_to_6pct") or -1)>0]
        active_clean=[r for r in active if (r.get("dbr") or 0)==0 and (r.get("tbr") or 0)==0 and (r.get("dd_pct") is not None and r.get("dd_pct")<=3.5)]
        active_clean_hits=[r for r in active_clean if (r.get("days_to_6pct") or -1)>0]
        dts=sorted([r["days_to_6pct"] for r in clean_hits])
        active_dts=sorted([r["days_to_6pct"] for r in active_clean_hits])
        nps=[r.get("np_pct") for r in good if r.get("np_pct") is not None]
        active_nps=[r.get("np_pct") for r in active if r.get("np_pct") is not None]
        dds=[r.get("dd_pct") for r in good if r.get("dd_pct") is not None]
        active_dds=[r.get("dd_pct") for r in active if r.get("dd_pct") is not None]
        summary[cand]={
            "windows":len(rs),"completed":len(good),"hit_count":len(hits),"clean_hit_count":len(clean_hits),
            "clean_hit_rate":round(len(clean_hits)/max(1,len(good)),3),
            "active_windows":len(active),"active_clean_hits":len(active_clean_hits),
            "active_clean_hit_rate":round(len(active_clean_hits)/max(1,len(active)),3),
            "min_days_to_6":min(dts) if dts else -1,"median_days_to_6":dts[len(dts)//2] if dts else -1,
            "active_min_days_to_6":min(active_dts) if active_dts else -1,
            "active_median_days_to_6":active_dts[len(active_dts)//2] if active_dts else -1,
            "avg_np_pct":round(sum(nps)/len(nps),3) if nps else None,
            "active_avg_np_pct":round(sum(active_nps)/len(active_nps),3) if active_nps else None,
            "min_np_pct":round(min(nps),3) if nps else None,"max_dd_pct":max(dds) if dds else None,
            "active_min_np_pct":round(min(active_nps),3) if active_nps else None,
            "active_max_dd_pct":max(active_dds) if active_dds else None,
            "breach_windows":sum(1 for r in good if (r.get("dbr") or 0)>0 or (r.get("tbr") or 0)>0),
            "fast_10d_hits":sum(1 for r in clean_hits if r["days_to_6pct"]<=10),
            "fast_15d_hits":sum(1 for r in clean_hits if r["days_to_6pct"]<=15),
            "active_fast_10d_hits":sum(1 for r in active_clean_hits if r["days_to_6pct"]<=10),
            "active_fast_15d_hits":sum(1 for r in active_clean_hits if r["days_to_6pct"]<=15),
        }
    return summary

def write_outputs(cid, rows, done=False):
    summ=summarize(rows)
    payload={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"compile_id":cid,"done":done,"summary":summ,"rows":rows}
    OUT_JSON.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    lines=[f"generated_at_utc={payload['generated_at_utc']}",f"compile_id={cid}",""]
    for cand, s in sorted(summ.items(), key=lambda kv:(kv[1].get("clean_hit_count",0), -max(999, kv[1].get("median_days_to_6",999))), reverse=True):
        lines.append(f"{cand}: clean_hits={s['clean_hit_count']}/{s['completed']} rate={s['clean_hit_rate']} active_hits={s['active_clean_hits']}/{s['active_windows']} active_rate={s['active_clean_hit_rate']} active_days[min/med]={s['active_min_days_to_6']}/{s['active_median_days_to_6']} active_fast<=10={s['active_fast_10d_hits']} active_fast<=15={s['active_fast_15d_hits']} avg_np={s['avg_np_pct']} active_avg_np={s['active_avg_np_pct']} min_np={s['min_np_pct']} active_min_np={s['active_min_np_pct']} maxdd={s['max_dd_pct']} active_maxdd={s['active_max_dd_pct']} breach_windows={s['breach_windows']}")
        top=sorted([r for r in rows if r['candidate']==cand and (r.get('days_to_6pct') or -1)>0], key=lambda r:r.get('days_to_6pct') or 999)[:5]
        for r in top:
            lines.append(f"  {r['window']} days6={r.get('days_to_6pct')} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr/tbr={r.get('dbr')}/{r.get('tbr')} orders={r.get('orders')}")
    OUT_TXT.write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    uid,tok=creds(); restore=base_params(); rows=[]; cid=None
    try:
        upload(uid,tok,MAIN_PATH); cid=compile_project(uid,tok)
        for cand, ov in candidates():
            cfg=base_params(); cfg.update(ov)
            for wname, dates in windows():
                p=dict(cfg); p.update(dates); set_params(uid,tok,p)
                rr=run_bt(uid,tok,cid,f"P44_{cand}_{wname}_{int(time.time())}")
                rr.update({"candidate":cand,"window":wname,"dates":dates,"overrides":ov})
                rows.append(rr); write_outputs(cid, rows, done=False)
        write_outputs(cid, rows, done=True)
        print(str(OUT_JSON))
    finally:
        try:
            upload(uid,tok,RESTORE_MAIN_PATH); set_params(uid,tok,restore)
        except Exception as exc:
            print(f"restore failed: {exc}")

if __name__=="__main__":
    main()

