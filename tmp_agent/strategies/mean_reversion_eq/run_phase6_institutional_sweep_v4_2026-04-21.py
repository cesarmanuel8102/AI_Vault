import base64, hashlib, json, re, time, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE='https://www.quantconnect.com/api/v2'
PROJECT_ID=29652652
SECRETS_PATH=Path(r'C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json')
MAIN_PATH=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py')
OUT_JSON=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase6_institutional_sweep_v4_2026-04-21.json')
OUT_TXT=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase6_institutional_sweep_v4_2026-04-21.txt')

def creds():
    d=json.loads(SECRETS_PATH.read_text(encoding='utf-8'))
    return str(d.get('user_id') or d.get('userId')).strip(), str(d.get('api_token') or d.get('apiToken') or d.get('token')).strip()

def headers(uid,tok,ts=None):
    ts=int(ts or time.time())
    sig=hashlib.sha256(f'{tok}:{ts}'.encode()).hexdigest()
    basic=base64.b64encode(f'{uid}:{sig}'.encode()).decode()
    return {'Authorization':f'Basic {basic}','Timestamp':str(ts),'Content-Type':'application/json'}

def post(uid,tok,ep,payload,timeout=120):
    ts=int(time.time())
    r=requests.post(f'{BASE}/{ep}',headers=headers(uid,tok,ts),json=payload,timeout=timeout)
    try:data=r.json()
    except Exception:data={'success':False,'errors':[f'HTTP {r.status_code}',r.text[:500]]}
    if r.status_code>=400:data.setdefault('success',False)
    if data.get('success',False):return data
    errs=' '.join(data.get('errors') or [])
    m=re.search(r'Server Time:\s*(\d+)',errs)
    if m:
        ts2=int(m.group(1))-1
        r2=requests.post(f'{BASE}/{ep}',headers=headers(uid,tok,ts2),json=payload,timeout=timeout)
        try:return r2.json()
        except Exception:return {'success':False,'errors':[f'HTTP {r2.status_code}',r2.text[:500]]}
    return data

def pf(x):
    try:return float(str(x).replace('%','').replace('$','').replace(',','').strip())
    except: return None

def pi(x):
    try:return int(float(str(x).replace(',','').strip()))
    except:return None

def rt_get(rt,key):
    if isinstance(rt,dict): return rt.get(key)
    if isinstance(rt,list):
        for i in rt:
            if isinstance(i,dict) and str(i.get('name') or i.get('Name'))==key:
                return i.get('value') or i.get('Value')
    return None

def mstats(bt):
    perf=bt.get('totalPerformance') or {}
    trades=perf.get('closedTrades') or []
    start=pf((perf.get('portfolioStatistics') or {}).get('startEquity')) or 50000.0
    bym=defaultdict(float)
    for t in trades:
        et=t.get('exitTime'); pnl=t.get('profitLoss')
        if et is None or pnl is None: continue
        try:d=datetime.fromisoformat(str(et).replace('Z','+00:00'))
        except: continue
        bym[f'{d.year:04d}-{d.month:02d}']+=float(pnl)
    if not bym:return {'monthly_mean_pct':None,'monthly_median_pct':None,'monthly_count':0}
    eq=float(start); arr=[]
    for m in sorted(bym):
        pnl=bym[m]; arr.append(0.0 if eq<=0 else (pnl/eq)*100.0); eq+=pnl
    return {'monthly_mean_pct':round(statistics.mean(arr),3),'monthly_median_pct':round(statistics.median(arr),3),'monthly_count':len(arr)}

def upload(uid,tok):
    d=post(uid,tok,'files/update',{'projectId':PROJECT_ID,'name':'main.py','content':MAIN_PATH.read_text(encoding='utf-8')},timeout=180)
    if not d.get('success',False): raise RuntimeError(d)

def clear(uid,tok):
    d=post(uid,tok,'projects/update',{'projectId':PROJECT_ID,'parameters':[]},timeout=60)
    if not d.get('success',False): raise RuntimeError(d)

def setp(uid,tok,params):
    d=post(uid,tok,'projects/update',{'projectId':PROJECT_ID,'parameters':[{'key':k,'value':str(v)} for k,v in params.items()]},timeout=60)
    if not d.get('success',False): raise RuntimeError(d)

def compile(uid,tok):
    c=post(uid,tok,'compile/create',{'projectId':PROJECT_ID},timeout=120)
    cid=c.get('compileId')
    if not cid: raise RuntimeError(c)
    for _ in range(180):
        r=post(uid,tok,'compile/read',{'projectId':PROJECT_ID,'compileId':cid},timeout=60)
        st=r.get('state','')
        if st in ('BuildSuccess','BuildWarning','BuildError','BuildAborted'):
            if st!='BuildSuccess': raise RuntimeError(r)
            return cid
        time.sleep(2)
    raise RuntimeError('compile timeout')

def run(uid,tok,cid,name):
    b=post(uid,tok,'backtests/create',{'projectId':PROJECT_ID,'compileId':cid,'backtestName':name},timeout=120)
    bid=((b.get('backtest') or {}).get('backtestId'))
    if not bid:return {'status':'CreateFailed','error':str(b)}
    for _ in range(420):
        rd=post(uid,tok,'backtests/read',{'projectId':PROJECT_ID,'backtestId':bid},timeout=120)
        bt=rd.get('backtest') or {}
        st=str(bt.get('status',''))
        if 'Completed' in st:
            s=bt.get('statistics') or {}; rt=bt.get('runtimeStatistics') or {}
            row={'status':st,'backtest_id':bid,'np_pct':pf(s.get('Net Profit')),'dd_pct':pf(s.get('Drawdown')),'dbr':pi(rt_get(rt,'DailyLossBreaches')),'tbr':pi(rt_get(rt,'TrailingBreaches')),'stress_days':pi(rt_get(rt,'ExternalStressDays')),'trades':pi(rt_get(rt,'PF100TradesTotal'))}
            row.update(mstats(bt)); return row
        if any(x in st for x in ('Error','Runtime','Aborted','Cancelled')): return {'status':st,'backtest_id':bid,'error':bt.get('error') or bt.get('message')}
        time.sleep(10)
    return {'status':'Timeout','backtest_id':bid}

def ok_stress(r):
    return r.get('np_pct') is not None and r.get('np_pct')>=0 and int(r.get('dbr') or 0)==0 and int(r.get('tbr') or 0)==0

def main():
    uid,tok=creds()
    base={
      'regime_mode':'PF100','trade_nq':1,'trade_m2k':0,'trade_mym':0,'entry_hour':9,'entry_min':40,'trailing_lock_mode':'EOD',
      'risk_per_trade':0.024,'max_contracts_per_trade':10,'max_open_positions':3,'max_trades_per_symbol_day':3,
      'daily_loss_limit_pct':0.018,'daily_profit_lock_pct':0.04,'trailing_dd_limit_pct':0.035,
      'ext_use_vix':0,'ext_use_vixy':1,'ext_vixy_sma_period':5,'ext_vixy_ratio_threshold':0.98,'ext_min_signals':1,'ext_rv_threshold':1.0,'ext_gap_z_threshold':99.0,'ext_gap_abs_threshold':1.0,
      'gap_atr_mult':0.18,'max_gap_entry_pct':0.009,'second_entry_enabled':1,'second_entry_breakout_enabled':1,'second_mom_entry_pct':0.0015,'second_target_atr_mult':1.45,'second_risk_mult':1.1,
      'pf1_risk':0.004,'pf1_stop':0.45,'pf1_tgt':1.7,'pf1_rng':0.006,'pf1_buf':0.0005,'pf1_tpd':0,'pf1_mom':0.0006,'pf1_no_shorts':1,'pf1_maxc':1
    }
    cands=[
      ('P6V4_T0_V098',{}),
      ('P6V4_T1_V099',{'ext_vixy_ratio_threshold':0.99}),
      ('P6V4_T2_V100',{'ext_vixy_ratio_threshold':1.0}),
      ('P6V4_T3_V097',{'ext_vixy_ratio_threshold':0.97}),
      ('P6V4_T4_R30_V098',{'risk_per_trade':0.03,'max_contracts_per_trade':14,'second_risk_mult':1.2}),
      ('P6V4_T5_R24_M2K',{'trade_m2k':1,'max_open_positions':4}),
    ]
    scenarios=[('STRESS_2020',{'start_year':2020,'start_month':1,'start_day':1,'end_year':2020,'end_month':12,'end_day':31}),('OOS_2025_2026Q1',{'start_year':2025,'start_month':1,'start_day':1,'end_year':2026,'end_month':3,'end_day':31}),('FULL_2022_2026Q1',{'start_year':2022,'start_month':1,'start_day':1,'end_year':2026,'end_month':3,'end_day':31})]
    upload(uid,tok); clear(uid,tok); cid=compile(uid,tok)
    rows=[]
    for label,ov in cands:
      cfg=dict(base); cfg.update(ov)
      p=dict(cfg); p.update(scenarios[0][1]); setp(uid,tok,p); r0=run(uid,tok,cid,f'{label}_STRESS_{int(time.time())}'); r0.update({'candidate':label,'scenario':'STRESS_2020','overrides':ov}); rows.append(r0)
      if ok_stress(r0):
        for sname,sdates in scenarios[1:]:
          p2=dict(cfg); p2.update(sdates); setp(uid,tok,p2); r=run(uid,tok,cid,f'{label}_{sname}_{int(time.time())}'); r.update({'candidate':label,'scenario':sname,'overrides':ov}); rows.append(r)
      OUT_JSON.write_text(json.dumps({'generated_at_utc':datetime.now(timezone.utc).isoformat(),'compile_id':cid,'rows':rows},indent=2),encoding='utf-8')
    lines=[f'generated_at_utc={datetime.now(timezone.utc).isoformat()}',f'compile_id={cid}','']
    for r in rows:
      lines.append(f"{r['candidate']} {r['scenario']} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} m_mean={r.get('monthly_mean_pct')} m_med={r.get('monthly_median_pct')} stress_days={r.get('stress_days')} trades={r.get('trades')} id={r.get('backtest_id')}")
    OUT_TXT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(str(OUT_JSON))

if __name__=='__main__':
  main()
