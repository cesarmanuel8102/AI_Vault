import base64, hashlib, json, re, time, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE='https://www.quantconnect.com/api/v2'
PROJECT_ID=29652652
SECRETS_PATH=Path(r'C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json')
MAIN_PATH=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase7_pf200.py')
OUT_JSON=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase7_pf200_eod_recheck_2026-04-22.json')
OUT_TXT=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/phase7_pf200_eod_recheck_2026-04-22.txt')

def creds():
 d=json.loads(SECRETS_PATH.read_text(encoding='utf-8'));return str(d.get('user_id') or d.get('userId')).strip(),str(d.get('api_token') or d.get('apiToken') or d.get('token')).strip()

def hdr(uid,tok,ts=None):
 ts=int(ts or time.time());sig=hashlib.sha256(f'{tok}:{ts}'.encode()).hexdigest();b=base64.b64encode(f'{uid}:{sig}'.encode()).decode();return {'Authorization':f'Basic {b}','Timestamp':str(ts),'Content-Type':'application/json'}

def post(uid,tok,ep,payload,timeout=120):
 ts=int(time.time());r=requests.post(f'{BASE}/{ep}',headers=hdr(uid,tok,ts),json=payload,timeout=timeout)
 try:data=r.json()
 except Exception:data={'success':False,'errors':[f'HTTP {r.status_code}',r.text[:500]]}
 if r.status_code>=400:data.setdefault('success',False)
 if data.get('success',False):return data
 m=re.search(r'Server Time:\s*(\d+)', ' '.join(data.get('errors') or []))
 if m:
  ts2=int(m.group(1))-1;r2=requests.post(f'{BASE}/{ep}',headers=hdr(uid,tok,ts2),json=payload,timeout=timeout)
  try:return r2.json()
  except Exception:return {'success':False,'errors':[f'HTTP {r2.status_code}',r2.text[:500]]}
 return data

def pf(x):
 try:return float(str(x).replace('%','').replace('$','').replace(',','').strip())
 except:return None

def pi(x):
 try:return int(float(str(x).replace(',','').strip()))
 except:return None

def rt(rt,key):
 if isinstance(rt,dict):return rt.get(key)
 if isinstance(rt,list):
  for it in rt:
   if isinstance(it,dict) and str(it.get('name') or it.get('Name'))==key:return it.get('value') or it.get('Value')
 return None

def mstats(bt):
 perf=bt.get('totalPerformance') or {};trades=perf.get('closedTrades') or [];start=pf((perf.get('portfolioStatistics') or {}).get('startEquity')) or 50000.0
 bym=defaultdict(float)
 for t in trades:
  et=t.get('exitTime');pnl=t.get('profitLoss')
  if et is None or pnl is None:continue
  try:d=datetime.fromisoformat(str(et).replace('Z','+00:00'))
  except:continue
  bym[f'{d.year:04d}-{d.month:02d}']+=float(pnl)
 if not bym:return {'monthly_mean_pct':None,'monthly_median_pct':None,'monthly_count':0}
 eq=float(start);arr=[]
 for m in sorted(bym):
  pnl=bym[m];arr.append(0.0 if eq<=0 else (pnl/eq)*100.0);eq+=pnl
 return {'monthly_mean_pct':round(statistics.mean(arr),3),'monthly_median_pct':round(statistics.median(arr),3),'monthly_count':len(arr)}

def upload(uid,tok):
 d=post(uid,tok,'files/update',{'projectId':PROJECT_ID,'name':'main.py','content':MAIN_PATH.read_text(encoding='utf-8')},timeout=180)
 if not d.get('success',False):raise RuntimeError(d)

def clear(uid,tok):
 d=post(uid,tok,'projects/update',{'projectId':PROJECT_ID,'parameters':[]},timeout=60)
 if not d.get('success',False):raise RuntimeError(d)

def setp(uid,tok,params):
 d=post(uid,tok,'projects/update',{'projectId':PROJECT_ID,'parameters':[{'key':k,'value':str(v)} for k,v in params.items()]},timeout=60)
 if not d.get('success',False):raise RuntimeError(d)

def compile(uid,tok):
 c=post(uid,tok,'compile/create',{'projectId':PROJECT_ID},timeout=120);cid=c.get('compileId')
 if not cid:raise RuntimeError(c)
 for _ in range(180):
  r=post(uid,tok,'compile/read',{'projectId':PROJECT_ID,'compileId':cid},timeout=60);st=r.get('state','')
  if st in ('BuildSuccess','BuildWarning','BuildError','BuildAborted'):
   if st!='BuildSuccess':raise RuntimeError(r)
   return cid
  time.sleep(2)
 raise RuntimeError('compile timeout')

def run(uid,tok,cid,name):
 b=post(uid,tok,'backtests/create',{'projectId':PROJECT_ID,'compileId':cid,'backtestName':name},timeout=120);bid=((b.get('backtest') or {}).get('backtestId'))
 if not bid:return {'status':'CreateFailed','error':str(b)}
 for _ in range(420):
  rd=post(uid,tok,'backtests/read',{'projectId':PROJECT_ID,'backtestId':bid},timeout=120);bt=rd.get('backtest') or {};st=str(bt.get('status',''))
  if 'Completed' in st:
   s=bt.get('statistics') or {};rts=bt.get('runtimeStatistics') or {}
   row={'status':st,'backtest_id':bid,'np_pct':pf(s.get('Net Profit')),'dd_pct':pf(s.get('Drawdown')),'dbr':pi(rt(rts,'DailyLossBreaches')),'tbr':pi(rt(rts,'TrailingBreaches')),'orders':pi(s.get('Total Orders')),'stress_days':pi(rt(rts,'ExternalStressDays'))}
   row.update(mstats(bt));return row
  if any(x in st for x in ('Error','Runtime','Aborted','Cancelled')):return {'status':st,'backtest_id':bid,'error':bt.get('error') or bt.get('message')}
  time.sleep(10)
 return {'status':'Timeout','backtest_id':bid}

def stress_ok(r):
 return r.get('np_pct') is not None and r.get('np_pct')>=0 and int(r.get('dbr') or 0)==0 and int(r.get('tbr') or 0)==0

def main():
 uid,tok=creds()
 base={'trade_mnq':1,'trade_mes':1,'allow_shorts':1,'daily_loss_limit_pct':0.018,'daily_profit_lock_pct':0.04,'flatten_hour':15,'flatten_min':58,
       'ext_vixy_sma_period':5,'ext_vixy_ratio_threshold':1.03,'ext_rv_threshold':1.0,'ext_gap_abs_threshold':1.0,
       'n_risk':0.013,'or_risk':0.010,'s_risk':0.003,'risk_per_trade':0.018,'max_contracts_per_trade':12,'max_trades_per_symbol_day':3,
       'or_minutes':10,'or_breakout_buffer_pct':0.0003,'or_target_atr_mult':1.55,'or_stop_atr_mult':0.75,'trailing_lock_mode':'EOD'}
 cands=[
  ('P7E_A0_DD35',{'trailing_dd_limit_pct':0.035}),
  ('P7E_A1_DD40',{'trailing_dd_limit_pct':0.040}),
  ('P7E_A2_DD45',{'trailing_dd_limit_pct':0.045}),
  ('P7E_A3_DD40_R20',{'trailing_dd_limit_pct':0.040,'risk_per_trade':0.020,'n_risk':0.014,'or_risk':0.011}),
  ('P7E_A4_DD45_R20',{'trailing_dd_limit_pct':0.045,'risk_per_trade':0.020,'n_risk':0.014,'or_risk':0.011}),
 ]
 scenarios=[('STRESS_2020',{'start_year':2020,'start_month':1,'start_day':1,'end_year':2020,'end_month':12,'end_day':31}),('OOS_2025_2026Q1',{'start_year':2025,'start_month':1,'start_day':1,'end_year':2026,'end_month':3,'end_day':31}),('FULL_2022_2026Q1',{'start_year':2022,'start_month':1,'start_day':1,'end_year':2026,'end_month':3,'end_day':31})]
 upload(uid,tok);clear(uid,tok);cid=compile(uid,tok)
 rows=[]
 for label,ov in cands:
  cfg=dict(base);cfg.update(ov)
  p=dict(cfg);p.update(scenarios[0][1]);setp(uid,tok,p);r0=run(uid,tok,cid,f'{label}_STRESS_{int(time.time())}');r0.update({'candidate':label,'scenario':'STRESS_2020','overrides':ov});rows.append(r0)
  if stress_ok(r0):
   for sname,sdates in scenarios[1:]:
    p2=dict(cfg);p2.update(sdates);setp(uid,tok,p2);r=run(uid,tok,cid,f'{label}_{sname}_{int(time.time())}');r.update({'candidate':label,'scenario':sname,'overrides':ov});rows.append(r)
  OUT_JSON.write_text(json.dumps({'generated_at_utc':datetime.now(timezone.utc).isoformat(),'compile_id':cid,'rows':rows},indent=2),encoding='utf-8')
 lines=[f'generated_at_utc={datetime.now(timezone.utc).isoformat()}',f'compile_id={cid}','']
 for r in rows:
  lines.append(f"{r['candidate']} {r['scenario']} np={r.get('np_pct')} dd={r.get('dd_pct')} dbr={r.get('dbr')} tbr={r.get('tbr')} m_mean={r.get('monthly_mean_pct')} m_med={r.get('monthly_median_pct')} orders={r.get('orders')} stress_days={r.get('stress_days')} id={r.get('backtest_id')}")
 OUT_TXT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(str(OUT_JSON))

if __name__=='__main__':
 main()
