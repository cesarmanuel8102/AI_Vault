import base64, hashlib, json, re, time, zlib
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29652652
SECRETS_PATH = Path(r"C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase31_fastpass_vol_expansion.py")
RESTORE_MAIN_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase11_pf200_entryfill_consistency.py")
BASE_PARAMS_PATH = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/params_p20_fastpass_qf3_ref_2026-04-22.json")
OUT_JSON = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase33_orb_accel_2026-04-26.json")
OUT_TXT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase33_orb_accel_2026-04-26.txt")

BASELINE = {"OOS_2025_2026Q1": 7.451, "STRESS_2020": 0.331, "RECENT_0401_0424": -0.595, "LIVE_WEEK_0420_0424": 0.0}

def creds():
    d=json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    return str(d.get("user_id") or d.get("userId")).strip(), str(d.get("api_token") or d.get("apiToken") or d.get("token")).strip()

def hdr(uid,tok,ts=None):
    ts=int(ts or time.time()); sig=hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest(); auth=base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {"Authorization":f"Basic {auth}","Timestamp":str(ts),"Content-Type":"application/json"}

def post(uid,tok,ep,payload,timeout=120):
    last=None
    for i in range(8):
        ts=int(time.time())
        try:
            r=requests.post(f"{BASE}/{ep}",headers=hdr(uid,tok,ts),json=payload,timeout=timeout)
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
            if isinstance(it,dict) and str(it.get("name") or it.get("Name"))==key: return it.get("value") or it.get("Value")
    return None

def upload_main(uid,tok,path):
    code=path.read_text(encoding="utf-8")
    if len(code)>63000:
        payload=base64.b64encode(zlib.compress(code.encode("utf-8"),9)).decode("ascii")
        code="import base64,zlib\nexec(zlib.decompress(base64.b64decode('"+payload+"')).decode('utf-8'))\n"
    r=post(uid,tok,"files/update",{"projectId":PROJECT_ID,"name":"main.py","content":code},timeout=180)
    if not r.get("success",False): raise RuntimeError(f"files/update failed: {r}")

def compile_project(uid,tok):
    c=post(uid,tok,"compile/create",{"projectId":PROJECT_ID},timeout=120); cid=c.get("compileId")
    if not cid: raise RuntimeError(f"compile/create failed: {c}")
    for _ in range(200):
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
    for _ in range(45):
        bc=post(uid,tok,"backtests/create",{"projectId":PROJECT_ID,"compileId":cid,"backtestName":name},timeout=120)
        bid=((bc.get("backtest") or {}).get("backtestId"))
        if bid: break
        if "no spare nodes available" in str(bc).lower(): time.sleep(45); continue
        return {"status":"CreateFailed","error":str(bc)}
    if not bid: return {"status":"CreateFailed","error":"missing backtest id"}
    bt={}
    for _ in range(540):
        rd=post(uid,tok,"backtests/read",{"projectId":PROJECT_ID,"backtestId":bid},timeout=120); bt=rd.get("backtest") or {}
        st=str(bt.get("status",""))
        if "Completed" in st: break
        if any(x in st for x in ("Error","Runtime","Aborted","Cancelled")): return {"status":st,"backtest_id":bid,"error":bt.get("error") or bt.get("message")}
        time.sleep(10)
    rd2=post(uid,tok,"backtests/read",{"projectId":PROJECT_ID,"backtestId":bid},timeout=120); bt=rd2.get("backtest") or bt
    s=bt.get("statistics") or {}; rts=bt.get("runtimeStatistics") or {}
    return {"status":str(bt.get("status","")),"backtest_id":bid,"np_pct":pf(s.get("Net Profit")),"dd_pct":pf(s.get("Drawdown")),"orders":pi(s.get("Total Orders")),"dbr":pi(rt(rts,"DailyLossBreaches")),"tbr":pi(rt(rts,"TrailingBreaches")),"days_to_6pct":pi(rt(rts,"DaysTo6Pct")),"tr_orb":pi(rt(rts,"TrORB")),"pnl_orb":pf(rt(rts,"PnlORB"))}

def base_params():
    b=json.loads(BASE_PARAMS_PATH.read_text(encoding="utf-8"))
    b.update({"trade_mnq":1,"trade_mes":1,"allow_shorts":1,"alpha_mr_enabled":0,"alpha_orb_enabled":1,"alpha_stress_enabled":1,"alpha_daytype_enabled":0,"alpha_volx_enabled":0,"challenge_target_pct":0.06})
    return b

def candidates():
    base={"trailing_lock_mode":"EOD","guard_enabled":1,"dynamic_risk_enabled":1,"max_open_positions":3,"max_trades_per_symbol_day":2}
    return [
        ("P33_ORB_R010", {**base, "or_risk":0.010, "max_contracts_per_trade":12, "daily_loss_limit_pct":0.018, "daily_profit_lock_pct":0.040}),
        ("P33_ORB_R012", {**base, "or_risk":0.012, "max_contracts_per_trade":12, "daily_loss_limit_pct":0.018, "daily_profit_lock_pct":0.040}),
        ("P33_ORB_R015", {**base, "or_risk":0.015, "max_contracts_per_trade":12, "daily_loss_limit_pct":0.018, "daily_profit_lock_pct":0.040}),
        ("P33_ORB_R018_DL12", {**base, "or_risk":0.018, "max_contracts_per_trade":12, "daily_loss_limit_pct":0.012, "daily_profit_lock_pct":0.030}),
        ("P33_ORB_R020_DL12", {**base, "or_risk":0.020, "max_contracts_per_trade":12, "daily_loss_limit_pct":0.012, "daily_profit_lock_pct":0.030}),
    ]

def scenarios():
    return [
        ("IS_2022_2024",{"start_year":2022,"start_month":1,"start_day":1,"end_year":2024,"end_month":12,"end_day":31}),
        ("OOS_2025_2026Q1",{"start_year":2025,"start_month":1,"start_day":1,"end_year":2026,"end_month":3,"end_day":31}),
        ("STRESS_2020",{"start_year":2020,"start_month":1,"start_day":1,"end_year":2020,"end_month":12,"end_day":31}),
        ("RECENT_0401_0424",{"start_year":2026,"start_month":4,"start_day":1,"end_year":2026,"end_month":4,"end_day":24}),
        ("LIVE_WEEK_0420_0424",{"start_year":2026,"start_month":4,"start_day":20,"end_year":2026,"end_month":4,"end_day":24}),
    ]

def score(sc):
    oos=sc.get("OOS_2025_2026Q1",{}); stress=sc.get("STRESS_2020",{}); recent=sc.get("RECENT_0401_0424",{}); week=sc.get("LIVE_WEEK_0420_0424",{})
    dds=[r.get("dd_pct") for r in sc.values() if r.get("dd_pct") is not None]
    checks={"oos_ge_base":oos.get("np_pct") is not None and oos["np_pct"]>=BASELINE["OOS_2025_2026Q1"],"stress_ge_base":stress.get("np_pct") is not None and stress["np_pct"]>=BASELINE["STRESS_2020"],"dd_ok":bool(dds) and max(dds)<=3.5,"breaches_zero":all((r.get("dbr") or 0)==0 and (r.get("tbr") or 0)==0 for r in sc.values()),"recent_ge_base":recent.get("np_pct") is not None and recent["np_pct"]>=BASELINE["RECENT_0401_0424"],"week_nonneg":week.get("np_pct") is not None and week["np_pct"]>=0}
    dt=[r.get("days_to_6pct") for r in sc.values() if r.get("days_to_6pct") and r.get("days_to_6pct")>0]
    best=min(dt) if dt else -1
    speed=.55*(oos.get("np_pct") or 0)+.35*(stress.get("np_pct") or 0)+1.2*(recent.get("np_pct") or 0)+1.5*(week.get("np_pct") or 0)+(max(0,40-best)*.12 if best>0 else 0)
    return {"pass":all(checks.values()),"checks":checks,"best_days_to_6pct":best,"speed_proxy":round(speed,4)}

def main():
    uid,tok=creds(); restore=base_params(); rows=[]; by={}
    try:
        upload_main(uid,tok,MAIN_PATH); cid=compile_project(uid,tok)
        for label,ov in candidates():
            by[label]={"overrides":ov,"scenarios":{}}
            cfg=base_params(); cfg.update(ov)
            for sname,dates in scenarios():
                p=dict(cfg); p.update(dates); set_params(uid,tok,p)
                rr=run_bt(uid,tok,cid,f"{label}_{sname}_{int(time.time())}"); rr.update({"candidate":label,"scenario":sname,"overrides":ov})
                rows.append(rr); by[label]["scenarios"][sname]=rr
                OUT_JSON.write_text(json.dumps({"generated_at_utc":datetime.now(timezone.utc).isoformat(),"compile_id":cid,"rows":rows,"by":by},indent=2),encoding="utf-8")
        dec={k:{**score(v["scenarios"]),"overrides":v["overrides"]} for k,v in by.items()}
        final={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"rows":rows,"by":by,"decision":dec}
        OUT_JSON.write_text(json.dumps(final,indent=2),encoding="utf-8")
        ranked=sorted(dec.items(), key=lambda kv:(kv[1]["pass"],kv[1]["speed_proxy"]), reverse=True)
        lines=[f"generated_at_utc={final['generated_at_utc']}",""]
        for label,d in ranked:
            lines.append(f"{label} pass={d['pass']} speed={d['speed_proxy']} days6={d['best_days_to_6pct']} checks={d['checks']}")
            for s in ("IS_2022_2024","OOS_2025_2026Q1","STRESS_2020","RECENT_0401_0424","LIVE_WEEK_0420_0424"):
                r=by[label]["scenarios"].get(s,{})
                lines.append(f"  {s} np={r.get('np_pct')} dd={r.get('dd_pct')} orders={r.get('orders')} dbr/tbr={r.get('dbr')}/{r.get('tbr')} days6={r.get('days_to_6pct')}")
            lines.append(f"  overrides={d['overrides']}")
        OUT_TXT.write_text("\n".join(lines)+"\n",encoding="utf-8"); print(str(OUT_JSON))
    finally:
        try:
            upload_main(uid,tok,RESTORE_MAIN_PATH); set_params(uid,tok,restore)
        except Exception as exc:
            print(f"restore failed: {exc}")

if __name__=="__main__":
    main()
