import base64, hashlib, json, re, time, zlib
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
import requests

BASE="https://www.quantconnect.com/api/v2"; PROJECT_ID=29652652
ROOT=Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq")
SECRETS_PATH=Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH=ROOT/"main_phase37_fastpass_daytype_multislot.py"
RESTORE_MAIN_PATH=ROOT/"main_phase11_pf200_entryfill_consistency.py"
BASE_PARAMS_PATH=ROOT/"params_p20_fastpass_qf3_ref_2026-04-22.json"
OUT_JSON=ROOT/"phase42_orb_risk_hitrate_2026-04-26.json"
OUT_TXT=ROOT/"phase42_orb_risk_hitrate_2026-04-26.txt"


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
        "tr_orb":pi(rt(rts,"TrORB")),"tr_volx":pi(rt(rts,"TrVOLX")),"tr_st":pi(rt(rts,"TrST"))
    }

def base_params():
    b=json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8"))
    b.update({"trade_mnq":1,"trade_mes":1,"allow_shorts":1,"challenge_target_pct":0.06})
    return b

def daytype(hour,minute,risk,maxc,sidecar):
    ov={
        "alpha_daytype_enabled":1,"p25_require_or_breakout":0,"p25_require_cross_alignment":0,
        "p25_require_trend_alignment":1,"p25_entry_hour":hour,"p25_entry_min":minute,
        "p25_min_intraday_mom_pct":0.0008,"p25_min_day_range_atr":0.08,"p25_max_day_range_atr":99.0,
        "p25_stop_atr_mult":0.55,"p25_target_atr_mult":1.80,"p25_risk":risk,"p25_max_contracts":maxc,
        "max_contracts_per_trade":max(8,maxc) if sidecar else maxc,"max_open_positions":3,"max_trades_per_symbol_day":2,
        "daily_loss_limit_pct":0.018,"daily_profit_lock_pct":0.040
    }
    if not sidecar:
        ov.update({"alpha_orb_enabled":0,"alpha_stress_enabled":0})
    return ov

def candidates():
    return [
        ("P33_ORB_R010", {"or_risk":0.010,"daily_loss_limit_pct":0.018,"daily_profit_lock_pct":0.040,"max_contracts_per_trade":8,"max_open_positions":3,"max_trades_per_symbol_day":2}),
        ("P33_ORB_R0115", {"or_risk":0.0115,"daily_loss_limit_pct":0.018,"daily_profit_lock_pct":0.040,"max_contracts_per_trade":8,"max_open_positions":3,"max_trades_per_symbol_day":2}),
        ("P33_ORB_R0125", {"or_risk":0.0125,"daily_loss_limit_pct":0.018,"daily_profit_lock_pct":0.040,"max_contracts_per_trade":8,"max_open_positions":3,"max_trades_per_symbol_day":2}),
        ("P33_ORB_R0135", {"or_risk":0.0135,"daily_loss_limit_pct":0.018,"daily_profit_lock_pct":0.040,"max_contracts_per_trade":8,"max_open_positions":3,"max_trades_per_symbol_day":2}),
        ("P33_ORB_R015", {"or_risk":0.015,"daily_loss_limit_pct":0.018,"daily_profit_lock_pct":0.040,"max_contracts_per_trade":8,"max_open_positions":3,"max_trades_per_symbol_day":2}),
        ("P37_CLEAN_MS2_R003", {"alpha_daytype_enabled":1,"p25_require_or_breakout":0,"p25_require_cross_alignment":0,"p25_require_trend_alignment":1,"p25_entry_hour":10,"p25_entry_min":30,"p25_second_entry_enabled":1,"p25_second_entry_hour":11,"p25_second_entry_min":30,"p25_min_intraday_mom_pct":0.0008,"p25_min_day_range_atr":0.08,"p25_max_day_range_atr":99.0,"p25_stop_atr_mult":0.55,"p25_target_atr_mult":1.8,"p25_risk":0.003,"p25_max_contracts":1,"max_contracts_per_trade":8,"max_open_positions":3,"max_trades_per_symbol_day":3,"daily_loss_limit_pct":0.018,"daily_profit_lock_pct":0.040}),
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
        hits=[r for r in good if (r.get("days_to_6pct") or -1)>0]
        clean=[r for r in good if (r.get("dbr") or 0)==0 and (r.get("tbr") or 0)==0 and (r.get("dd_pct") is not None and r.get("dd_pct")<=3.5)]
        clean_hits=[r for r in clean if (r.get("days_to_6pct") or -1)>0]
        dts=sorted([r["days_to_6pct"] for r in clean_hits])
        nps=[r.get("np_pct") for r in good if r.get("np_pct") is not None]
        dds=[r.get("dd_pct") for r in good if r.get("dd_pct") is not None]
        summary[cand]={
            "windows":len(rs),"completed":len(good),"hit_count":len(hits),"clean_hit_count":len(clean_hits),
            "clean_hit_rate":round(len(clean_hits)/max(1,len(good)),3),
            "min_days_to_6":min(dts) if dts else -1,"median_days_to_6":dts[len(dts)//2] if dts else -1,
            "avg_np_pct":round(sum(nps)/len(nps),3) if nps else None,
            "min_np_pct":round(min(nps),3) if nps else None,"max_dd_pct":max(dds) if dds else None,
            "breach_windows":sum(1 for r in good if (r.get("dbr") or 0)>0 or (r.get("tbr") or 0)>0),
            "fast_10d_hits":sum(1 for r in clean_hits if r["days_to_6pct"]<=10),
            "fast_15d_hits":sum(1 for r in clean_hits if r["days_to_6pct"]<=15),
        }
    return summary

def write_outputs(cid, rows, done=False):
    summ=summarize(rows)
    payload={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"compile_id":cid,"done":done,"summary":summ,"rows":rows}
    OUT_JSON.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    lines=[f"generated_at_utc={payload['generated_at_utc']}",f"compile_id={cid}",""]
    for cand, s in sorted(summ.items(), key=lambda kv:(kv[1].get("clean_hit_count",0), -max(999, kv[1].get("median_days_to_6",999))), reverse=True):
        lines.append(f"{cand}: clean_hits={s['clean_hit_count']}/{s['completed']} rate={s['clean_hit_rate']} min_days={s['min_days_to_6']} median_days={s['median_days_to_6']} fast<=10={s['fast_10d_hits']} fast<=15={s['fast_15d_hits']} avg_np={s['avg_np_pct']} min_np={s['min_np_pct']} maxdd={s['max_dd_pct']} breach_windows={s['breach_windows']}")
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
                rr=run_bt(uid,tok,cid,f"P36_{cand}_{wname}_{int(time.time())}")
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
