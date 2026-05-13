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
OUT_JSON=ROOT/"phase53_maturity_consistency_cap_2026-04-29.json"
OUT_TXT=ROOT/"phase53_maturity_consistency_cap_2026-04-29.txt"
DECISION_TXT=ROOT/"phase53_decision_2026-04-29.txt"
STARTS=[date(2025,2,9), date(2025,2,16), date(2025,2,23)]

def creds():
    d=json.loads(SECRETS_PATH.read_text(encoding="utf-8")); return str(d.get("user_id") or d.get("userId")).strip(), str(d.get("api_token") or d.get("apiToken") or d.get("token")).strip()
def hdr(uid,tok,ts=None):
    ts=int(ts or time.time()); sig=hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest(); return {"Authorization":"Basic "+base64.b64encode(f"{uid}:{sig}".encode()).decode(),"Timestamp":str(ts),"Content-Type":"application/json"}
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
        except Exception as e: last={"success":False,"errors":[str(e)]}
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
            if isinstance(it,dict) and str(it.get("name") or it.get("Name"))==key: return it.get("value") or it.get("Value")
    return None
def upload(uid,tok,path):
    code=path.read_text(encoding="utf-8")
    if len(code)>63000:
        payload=base64.b64encode(zlib.compress(code.encode("utf-8"),9)).decode("ascii")
        code="import base64,zlib\nexec(zlib.decompress(base64.b64decode('"+payload+"')).decode('utf-8'))\n"
    r=post(uid,tok,"files/update",{"projectId":PROJECT_ID,"name":"main.py","content":code},timeout=180)
    if not r.get("success",False): raise RuntimeError(f"files/update failed: {r}")
def compile_project(uid,tok):
    c=post(uid,tok,"compile/create",{"projectId":PROJECT_ID},timeout=120); cid=c.get("compileId")
    if not cid: raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(220):
        rd=post(uid,tok,"compile/read",{"projectId":PROJECT_ID,"compileId":cid},timeout=60); st=rd.get("state","")
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
    for _ in range(60):
        bc=post(uid,tok,"backtests/create",{"projectId":PROJECT_ID,"compileId":cid,"backtestName":name},timeout=120); bid=((bc.get("backtest") or {}).get("backtestId"))
        if bid: break
        if "no spare nodes available" in str(bc).lower(): time.sleep(45); continue
        return {"status":"CreateFailed","error":str(bc)}
    if not bid: return {"status":"CreateFailed","error":"missing backtest id"}
    bt={}
    for _ in range(360):
        rd=post(uid,tok,"backtests/read",{"projectId":PROJECT_ID,"backtestId":bid},timeout=120); bt=rd.get("backtest") or {}; st=str(bt.get("status","")).strip()
        if "Completed" in st: break
        if any(x in st for x in ("Error","Runtime","Aborted","Cancelled")): return {"status":st,"backtest_id":bid,"error":bt.get("error") or bt.get("message")}
        time.sleep(10)
    rd2=post(uid,tok,"backtests/read",{"projectId":PROJECT_ID,"backtestId":bid},timeout=120); bt=rd2.get("backtest") or bt
    s=bt.get("statistics") or {}; rts=bt.get("runtimeStatistics") or {}
    return {"status":str(bt.get("status","")),"backtest_id":bid,"np_pct":pf(s.get("Net Profit")),"dd_pct":pf(s.get("Drawdown")),"orders":pi(s.get("Total Orders")),"dbr":pi(rt(rts,"DailyLossBreaches")),"tbr":pi(rt(rts,"TrailingBreaches")),"days_to_6pct":pi(rt(rts,"DaysTo6Pct")),"best_day_usd":pf(rt(rts,"BestDayUSD")),"consistency_pct":pf(rt(rts,"ConsistencyPct")),"consistency_ratio_pct":pf(rt(rts,"ConsistencyRatioPct")),"pf":pf(rt(rts,"ProfitFactor")),"tr_orb":pi(rt(rts,"TrORB")),"pnl_orb":pf(rt(rts,"PnlORB"))}
def base_params():
    b=json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8")); b.update({"trade_mnq":1,"trade_mes":1,"allow_shorts":1,"challenge_target_pct":0.06}); return b
def core():
    return {"alpha_mr_enabled":0,"alpha_orb_enabled":1,"alpha_stress_enabled":0,"alpha_daytype_enabled":0,"alpha_volx_enabled":0,"alpha_scalp_enabled":0,"alpha_p50_enabled":0,"or_minutes":15,"or_breakout_buffer_pct":0.0007,"or_target_atr_mult":1.55,"or_stop_atr_mult":0.75,"or_min_gap_pct":0.0015,"or_mom_entry_pct":0.001,"or_min_width_atr":0.22,"or_max_width_atr":1.10,"or_require_gap_alignment":1,"or_risk":0.0150,"trailing_lock_mode":"EOD","guard_enabled":1,"max_open_positions":3,"max_trades_per_symbol_day":2,"daily_loss_limit_pct":0.018,"daily_profit_lock_pct":0.04,"max_contracts_per_trade":10}
def candidates():
    base=core()
    def c(label, upd):
        d=dict(base); d.update(upd); return label,d
    return [
        c("RAW_P52",{}),
        c("CAP030",{"daily_profit_lock_pct":0.030}),
        c("CAP025",{"daily_profit_lock_pct":0.025}),
        c("CAP022",{"daily_profit_lock_pct":0.022}),
        c("CAP020",{"daily_profit_lock_pct":0.020}),
        c("CAP025_CG40",{"daily_profit_lock_pct":0.025,"consistency_guard_enabled":1,"consistency_soft_cap_pct":35.0,"consistency_hard_cap_pct":40.0,"consistency_soft_risk_mult":0.50,"consistency_min_profit_pct":0.02,"cons_act_mult":1.10}),
        c("CAP022_CG40",{"daily_profit_lock_pct":0.022,"consistency_guard_enabled":1,"consistency_soft_cap_pct":35.0,"consistency_hard_cap_pct":40.0,"consistency_soft_risk_mult":0.50,"consistency_min_profit_pct":0.02,"cons_act_mult":1.10}),
    ]
def clean(r): return "Completed" in str(r.get("status")) and (r.get("dbr") or 0)==0 and (r.get("tbr") or 0)==0 and (r.get("dd_pct") is not None and r.get("dd_pct")<=3.5)
def hit(r): return (r.get("days_to_6pct") or -1)>0
def tf(r): return clean(r) and hit(r) and (r.get("consistency_pct") is None or r.get("consistency_pct")<=40.0)
def summarize(rows):
    out={}
    for label,_ in candidates():
        rs=[r for r in rows if r["candidate"]==label]; comp=[r for r in rs if "Completed" in str(r.get("status"))]
        hits=[r for r in comp if clean(r) and hit(r)]; tfs=[r for r in comp if tf(r)]
        dts=sorted([r["days_to_6pct"] for r in hits]); nps=[r["np_pct"] for r in comp if r.get("np_pct") is not None]; dds=[r["dd_pct"] for r in comp if r.get("dd_pct") is not None]; cons=[r["consistency_pct"] for r in comp if r.get("consistency_pct") is not None]
        out[label]={"completed":len(comp),"hits":len(hits),"hit_rate":round(len(hits)/max(1,len(comp)),3),"tf_hits":len(tfs),"tf_rate":round(len(tfs)/max(1,len(comp)),3),"fast15":sum(1 for r in hits if r["days_to_6pct"]<=15),"fast15_rate":round(sum(1 for r in hits if r["days_to_6pct"]<=15)/max(1,len(comp)),3),"min_days":min(dts) if dts else -1,"median_days":dts[len(dts)//2] if dts else -1,"avg_np":round(sum(nps)/len(nps),3) if nps else None,"min_np":round(min(nps),3) if nps else None,"maxdd":max(dds) if dds else None,"max_cons":round(max(cons),2) if cons else None,"breaches":sum(1 for r in comp if (r.get("dbr") or 0)>0 or (r.get("tbr") or 0)>0)}
    return out
def write_outputs(cid, rows, done=False):
    summ=summarize(rows); payload={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"compile_id":cid,"done":done,"summary":summ,"rows":rows}
    OUT_JSON.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    lines=[f"generated_at_utc={payload['generated_at_utc']}",f"compile_id={cid}","starts="+", ".join(d.isoformat() for d in STARTS),""]
    for label,s in sorted(summ.items(), key=lambda kv:(kv[1]['tf_rate'],kv[1]['fast15_rate'],kv[1]['hit_rate'], -(kv[1]['median_days'] if kv[1]['median_days']>0 else 99)), reverse=True):
        lines.append(f"{label}: tf={s['tf_hits']}/{s['completed']} rate={s['tf_rate']} hits={s['hits']}/{s['completed']} fast15={s['fast15']}/{s['completed']} min_days={s['min_days']} median_days={s['median_days']} avg_np={s['avg_np']} min_np={s['min_np']} maxdd={s['maxdd']} max_cons={s['max_cons']} breaches={s['breaches']}")
        for r in sorted([x for x in rows if x['candidate']==label], key=lambda x:x['start']):
            lines.append(f"  {r['start']} days6={r.get('days_to_6pct')} np={r.get('np_pct')} dd={r.get('dd_pct')} cons={r.get('consistency_pct')} dbr/tbr={r.get('dbr')}/{r.get('tbr')} orders={r.get('orders')} orb={r.get('tr_orb')}")
    OUT_TXT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    best=None
    for label,s in summ.items():
        if s.get('completed')==3 and s.get('tf_rate')>=0.75 and s.get('fast15_rate')>=0.75 and s.get('breaches')==0 and (s.get('maxdd') or 99)<=2.0:
            if best is None or (s['tf_rate'],s['fast15_rate'],-s['median_days'])>(best[1]['tf_rate'],best[1]['fast15_rate'],-best[1]['median_days']): best=(label,s)
    dec=["PHASE53 DECISION — MATURITY CONSISTENCY CAP",f"generated_at_utc={payload['generated_at_utc']}",""]
    if best: dec.append(f"VERDICT: PROMOTE {best[0]} provisionally. tf={best[1]['tf_hits']}/{best[1]['completed']} fast15={best[1]['fast15']}/{best[1]['completed']} median_days={best[1]['median_days']} maxdd={best[1]['maxdd']} max_cons={best[1]['max_cons']}")
    else: dec.append("VERDICT: DO NOT PROMOTE. No variant reached >=75% Tradeify-clean and fast15 without risk degradation.")
    DECISION_TXT.write_text("\n".join(dec)+"\n",encoding="utf-8")
def main():
    uid,tok=creds(); restore=base_params(); rows=[]; cid=None
    try:
        upload(uid,tok,MAIN_PATH); cid=compile_project(uid,tok)
        for label,ov in candidates():
            cfg=base_params(); cfg.update(ov)
            for st in STARTS:
                en=st+timedelta(days=44); p=dict(cfg); p.update({"start_year":st.year,"start_month":st.month,"start_day":st.day,"end_year":en.year,"end_month":en.month,"end_day":en.day})
                set_params(uid,tok,p); rr=run_bt(uid,tok,cid,f"P53_{label}_{st.isoformat()}_{int(time.time())}")
                rr.update({"candidate":label,"start":st.isoformat(),"end":en.isoformat(),"overrides":ov}); rows.append(rr); write_outputs(cid,rows,done=False)
                print(f"{label} {st.isoformat()} status={rr.get('status')} days={rr.get('days_to_6pct')} np={rr.get('np_pct')} dd={rr.get('dd_pct')} cons={rr.get('consistency_pct')} dbr/tbr={rr.get('dbr')}/{rr.get('tbr')}", flush=True)
        write_outputs(cid,rows,done=True); print(str(OUT_TXT)); print(str(DECISION_TXT))
    finally:
        try: upload(uid,tok,RESTORE_MAIN_PATH); set_params(uid,tok,restore)
        except Exception as exc: print(f"restore failed: {exc}")
if __name__=="__main__": main()
