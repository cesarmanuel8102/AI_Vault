
import base64, hashlib, json, re, time, zlib
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
import requests

BASE="https://www.quantconnect.com/api/v2"; PROJECT_ID=29652652
ROOT=Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq")
SECRETS_PATH=Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH=ROOT/"main_phase50_trend_pullback_rebreak.py"
RESTORE_MAIN_PATH=ROOT/"main_phase11_pf200_entryfill_consistency.py"
BASE_PARAMS_PATH=ROOT/"params_p42_fastpass_hitrate_orb_r0135_2026-04-26.json"
OUT_JSON=ROOT/"phase51_gate_risk_campaign_2026-04-29.json"
OUT_TXT=ROOT/"phase51_gate_risk_campaign_2026-04-29.txt"

# Best Phase49 activation rule:
# iwm_dd50<=-0.0511294 AND qqq_rv20>=0.174213 AND iwm_rng10<=0.0152915
# Signals: 2023-09-17, 2025-01-19, 2025-01-26, 2025-02-02, 2025-02-16, 2025-02-23
ACTIVATION_STARTS = [
    date(2023, 9, 17),
    date(2025, 1, 19),
    date(2025, 1, 26),
    date(2025, 2, 2),
    date(2025, 2, 16),
    date(2025, 2, 23),
]


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
    if not r.get("success",False): raise RuntimeError(f"files/update failed: {r}")

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
    if not wr.get("success",False): raise RuntimeError(f"projects/update failed: {wr}")

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
        "consistency_pct":pf(rt(rts,"ConsistencyPct")),"consistency_ratio_pct":pf(rt(rts,"ConsistencyRatioPct")),
        "pf":pf(rt(rts,"ProfitFactor")),"cushion_pct":pf(rt(rts,"CushionPct")),
        "tr_orb":pi(rt(rts,"TrORB")),"tr_p50":pi(rt(rts,"TrP50")),"tr_volx":pi(rt(rts,"TrVOLX")),"tr_st":pi(rt(rts,"TrST")),
        "pnl_orb":pf(rt(rts,"PnlORB")),"pnl_p50":pf(rt(rts,"PnlP50")),"pnl_volx":pf(rt(rts,"PnlVOLX")),
    }

def base_params():
    b=json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8"))
    b.update({"trade_mnq":1,"trade_mes":1,"allow_shorts":1,"challenge_target_pct":0.06})
    return b

def candidates():
    base_orb={
        "alpha_mr_enabled":0,"alpha_orb_enabled":1,"alpha_stress_enabled":0,"alpha_daytype_enabled":0,
        "alpha_volx_enabled":0,"alpha_scalp_enabled":0,"alpha_p50_enabled":0,
        "or_minutes":15,"or_breakout_buffer_pct":0.0007,"or_target_atr_mult":1.55,"or_stop_atr_mult":0.75,
        "or_min_gap_pct":0.0015,"or_mom_entry_pct":0.001,"or_min_width_atr":0.22,"or_max_width_atr":1.10,
        "or_require_gap_alignment":1,"trailing_lock_mode":"EOD","guard_enabled":1,"max_open_positions":3,
        "max_trades_per_symbol_day":2,"daily_loss_limit_pct":0.018,"daily_profit_lock_pct":0.04,
    }
    def c(label, updates):
        d=dict(base_orb); d.update(updates); return (label,d)
    return [
        c("G1_ORB_R0135_BASE", {"or_risk":0.0135,"max_contracts_per_trade":8}),
        c("G1_ORB_R0150", {"or_risk":0.0150,"max_contracts_per_trade":10}),
        c("G1_ORB_R0175", {"or_risk":0.0175,"max_contracts_per_trade":10}),
        c("G1_ORB_R0200_CAP", {"or_risk":0.0200,"max_contracts_per_trade":10,"daily_profit_lock_pct":0.050}),
        c("G1_ORB_R0150_P50", {
            "or_risk":0.0150,"max_contracts_per_trade":10,"alpha_p50_enabled":1,
            "p50_risk":0.0030,"p50_max_contracts":1,"p50_min_mom_pct":0.0018,
            "p50_min_range_atr":0.30,"p50_max_range_atr":1.75,"p50_stop_atr_mult":0.46,
            "p50_target_atr_mult":1.15,"p50_pullback_vwap_band_pct":0.0022,"p50_rebreak_buffer_pct":0.00015,
        }),
        c("G1_ORB_R0150_VOLX", {
            "or_risk":0.0150,"max_contracts_per_trade":10,"alpha_volx_enabled":1,
            "p31_risk":0.0030,"p31_max_contracts":1,"p31_strong_max_contracts":1,
            "p31_min_mom_pct":0.0010,"p31_min_current_range_atr":0.32,"p31_compression_max_width_atr":0.35,
        }),
    ]

def windows():
    out=[]
    for st in ACTIVATION_STARTS:
        en=st+timedelta(days=44)
        out.append((f"G1_{st.isoformat()}_{en.isoformat()}", {"start_year":st.year,"start_month":st.month,"start_day":st.day,"end_year":en.year,"end_month":en.month,"end_day":en.day}))
    return out

def is_clean(r):
    return "Completed" in str(r.get("status")) and (r.get("dbr") or 0)==0 and (r.get("tbr") or 0)==0 and (r.get("dd_pct") is not None and r.get("dd_pct")<=3.5)

def is_hit(r):
    return (r.get("days_to_6pct") or -1)>0

def is_tradeify_clean(r):
    # Conservative proxy: target hit, no breaches, DD <= 3.5%, best day share <= 40% after target/final equity.
    cons = r.get("consistency_pct")
    return is_clean(r) and is_hit(r) and (cons is None or cons <= 40.0)

def summarize(rows):
    by={}
    for r in rows: by.setdefault(r["candidate"],[]).append(r)
    out={}
    for cand,rs in by.items():
        good=[r for r in rs if "Completed" in str(r.get("status"))]
        clean=[r for r in good if is_clean(r)]
        hits=[r for r in clean if is_hit(r)]
        tf=[r for r in good if is_tradeify_clean(r)]
        dts=sorted([r["days_to_6pct"] for r in hits])
        nps=[r.get("np_pct") for r in good if r.get("np_pct") is not None]
        dds=[r.get("dd_pct") for r in good if r.get("dd_pct") is not None]
        cons=[r.get("consistency_pct") for r in good if r.get("consistency_pct") is not None]
        out[cand]={
            "windows":len(rs),"completed":len(good),"clean_windows":len(clean),
            "clean_hits":len(hits),"clean_hit_rate":round(len(hits)/max(1,len(good)),3),
            "tradeify_clean_hits":len(tf),"tradeify_clean_rate":round(len(tf)/max(1,len(good)),3),
            "min_days_to_6":min(dts) if dts else -1,"median_days_to_6":dts[len(dts)//2] if dts else -1,
            "fast_8d_hits":sum(1 for r in hits if r["days_to_6pct"]<=8),
            "fast_10d_hits":sum(1 for r in hits if r["days_to_6pct"]<=10),
            "fast_15d_hits":sum(1 for r in hits if r["days_to_6pct"]<=15),
            "avg_np_pct":round(sum(nps)/len(nps),3) if nps else None,"min_np_pct":round(min(nps),3) if nps else None,
            "max_dd_pct":max(dds) if dds else None,"max_consistency_pct":round(max(cons),2) if cons else None,
            "breach_windows":sum(1 for r in good if (r.get("dbr") or 0)>0 or (r.get("tbr") or 0)>0),
        }
    return out

def write_outputs(cid, rows, done=False):
    summ=summarize(rows)
    payload={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"compile_id":cid,"gate_rule":"iwm_dd50<=-0.0511294 AND qqq_rv20>=0.174213 AND iwm_rng10<=0.0152915","done":done,"summary":summ,"rows":rows}
    OUT_JSON.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    lines=[f"generated_at_utc={payload['generated_at_utc']}",f"compile_id={cid}",f"gate_rule={payload['gate_rule']}",""]
    for cand,s in sorted(summ.items(), key=lambda kv:(kv[1].get("tradeify_clean_hits",0), kv[1].get("clean_hits",0), -max(999,kv[1].get("median_days_to_6",999))), reverse=True):
        lines.append(f"{cand}: tradeify_clean={s['tradeify_clean_hits']}/{s['completed']} rate={s['tradeify_clean_rate']} clean_hits={s['clean_hits']}/{s['completed']} rate={s['clean_hit_rate']} min_days={s['min_days_to_6']} median_days={s['median_days_to_6']} fast<=8={s['fast_8d_hits']} fast<=10={s['fast_10d_hits']} fast<=15={s['fast_15d_hits']} avg_np={s['avg_np_pct']} min_np={s['min_np_pct']} maxdd={s['max_dd_pct']} max_cons={s['max_consistency_pct']} breach_windows={s['breach_windows']}")
        for r in sorted([x for x in rows if x['candidate']==cand], key=lambda x:x['window']):
            lines.append(f"  {r['window']} days6={r.get('days_to_6pct')} np={r.get('np_pct')} dd={r.get('dd_pct')} cons={r.get('consistency_pct')} dbr/tbr={r.get('dbr')}/{r.get('tbr')} orders={r.get('orders')} orb={r.get('tr_orb')} p50={r.get('tr_p50')} volx={r.get('tr_volx')}")
    OUT_TXT.write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    uid,tok=creds(); restore=base_params(); rows=[]; cid=None
    try:
        upload(uid,tok,MAIN_PATH); cid=compile_project(uid,tok)
        for cand,ov in candidates():
            cfg=base_params(); cfg.update(ov)
            for wname,dates in windows():
                p=dict(cfg); p.update(dates); set_params(uid,tok,p)
                rr=run_bt(uid,tok,cid,f"P51_{cand}_{wname}_{int(time.time())}")
                rr.update({"candidate":cand,"window":wname,"dates":dates,"overrides":ov})
                rows.append(rr); write_outputs(cid,rows,done=False)
                print(f"{cand} {wname} status={rr.get('status')} days={rr.get('days_to_6pct')} np={rr.get('np_pct')} dd={rr.get('dd_pct')} cons={rr.get('consistency_pct')} dbr/tbr={rr.get('dbr')}/{rr.get('tbr')}", flush=True)
        write_outputs(cid,rows,done=True)
        print(str(OUT_TXT))
    finally:
        try:
            upload(uid,tok,RESTORE_MAIN_PATH); set_params(uid,tok,restore)
        except Exception as exc:
            print(f"restore failed: {exc}")

if __name__=="__main__": main()
