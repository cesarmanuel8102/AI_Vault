import base64, hashlib, json, re, time
from pathlib import Path
import requests
BASE='https://www.quantconnect.com/api/v2'
PROJECT_ID=30874635
ROOT=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq')
MAIN=ROOT/'main_phase54_campaign_gate_monitor.py'
OUT=ROOT/'phase54_campaign_monitor_bt_2026-04-29.json'
SEC=Path(r'C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json')
sec=json.loads(SEC.read_text()); uid=str(sec.get('user_id') or sec.get('userId')).strip(); tok=str(sec.get('api_token') or sec.get('apiToken') or sec.get('token')).strip()
def hdr(ts=None):
    ts=int(ts or time.time()); sig=hashlib.sha256(f'{tok}:{ts}'.encode()).hexdigest(); auth=base64.b64encode(f'{uid}:{sig}'.encode()).decode(); return {'Authorization':'Basic '+auth,'Timestamp':str(ts),'Content-Type':'application/json'}
def post(ep,pay,timeout=120,retries=8):
    last=None
    for i in range(retries):
        try:
            r=requests.post(f'{BASE}/{ep}',headers=hdr(),json=pay,timeout=timeout)
            try: d=r.json()
            except Exception: d={'success':False,'errors':[f'HTTP {r.status_code}',r.text[:500]]}
            if d.get('success'): return d
            m=re.search(r'Server Time:\s*(\d+)', ' '.join(d.get('errors') or []))
            if m:
                r2=requests.post(f'{BASE}/{ep}',headers=hdr(int(m.group(1))-1),json=pay,timeout=timeout)
                try: d2=r2.json()
                except Exception: d2={'success':False,'errors':[f'HTTP {r2.status_code}',r2.text[:500]]}
                if d2.get('success'): return d2
                d=d2
            last=d
        except Exception as e: last={'success':False,'errors':[str(e)]}
        time.sleep(min(3*(i+1),20))
    return last

def rt(runtime,key):
    if isinstance(runtime,dict): return runtime.get(key)
    if isinstance(runtime,list):
        for it in runtime:
            if isinstance(it,dict) and str(it.get('name') or it.get('Name'))==key: return it.get('value') or it.get('Value')
    return None
print('upload')
r=post('files/update',{'projectId':PROJECT_ID,'name':'main.py','content':MAIN.read_text(encoding='utf-8')},180)
if not r.get('success'): raise SystemExit(r)
print('params')
params={'start_year':2024,'start_month':10,'start_day':1,'end_year':2025,'end_month':2,'end_day':10}
r=post('projects/update',{'projectId':PROJECT_ID,'parameters':[{'key':k,'value':str(v)} for k,v in params.items()]},90)
if not r.get('success'): raise SystemExit(r)
print('compile')
c=post('compile/create',{'projectId':PROJECT_ID},120); cid=c.get('compileId'); print('cid',cid)
if not cid: raise SystemExit(c)
for _ in range(180):
    cr=post('compile/read',{'projectId':PROJECT_ID,'compileId':cid},60); st=cr.get('state');
    if st in ('BuildSuccess','BuildWarning','BuildError','BuildAborted'):
        print('compile state',st)
        if st!='BuildSuccess': raise SystemExit(json.dumps(cr)[:2000])
        break
    time.sleep(2)
print('backtest')
bc=post('backtests/create',{'projectId':PROJECT_ID,'compileId':cid,'backtestName':f'PHASE54_GATE_MONITOR_2025_{int(time.time())}'},120)
bid=(bc.get('backtest') or {}).get('backtestId'); print('bid',bid)
if not bid: raise SystemExit(bc)
bt={}
for i in range(240):
    br=post('backtests/read',{'projectId':PROJECT_ID,'backtestId':bid},120); bt=br.get('backtest') or {}; st=str(bt.get('status',''))
    if i%6==0: print('status',st)
    if 'Completed' in st: break
    if any(x in st for x in ('Error','Runtime','Aborted','Cancelled')): break
    time.sleep(10)
br=post('backtests/read',{'projectId':PROJECT_ID,'backtestId':bid},120); bt=br.get('backtest') or bt
rts=bt.get('runtimeStatistics') or {}
summary={k:rt(rts,k) for k in ['GateState','Action','CampaignStart','LastSignal','CampaignAgeDays','DaysToActivationWindow','BaseGateNow','SignalCount','FirstActivationWindow','ActivationWindowDaysSeen','LateWindowDaysSeen','MaxCampaignAgeSeen','IWM_DD50','QQQ_RV20','IWM_RNG10']}
out={'project_id':PROJECT_ID,'compile_id':cid,'backtest_id':bid,'status':bt.get('status'),'summary':summary,'statistics':bt.get('statistics'),'runtimeStatistics':rts}
OUT.write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'status':bt.get('status'),'summary':summary,'out':str(OUT)},indent=2))



