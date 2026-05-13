"""
PF100 FASTPASS Stage16B Targeted Regime Validation
"""

import json
import time
from base64 import b64encode
from datetime import datetime, date
from hashlib import sha256
from pathlib import Path
import requests

UID='384945'; TOKEN='4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3'; BASE='https://www.quantconnect.com/api/v2'; PROJECT_ID=29652652
SOURCE_FILE=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py')
OUT_JSON=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage16b_targeted.json')
OUT_TXT=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/pf100_fastpass_stage16b_targeted.txt')


def headers():
    ts=str(int(time.time())); sig=sha256(f"{TOKEN}:{ts}".encode()).hexdigest(); auth=b64encode(f"{UID}:{sig}".encode()).decode()
    return {'Authorization':f'Basic {auth}','Timestamp':ts,'Content-Type':'application/json'}

def api_post(endpoint,payload,timeout=90,retries=8,backoff=3):
    last=None
    for i in range(retries):
        try:
            r=requests.post(f"{BASE}/{endpoint}",headers=headers(),json=payload,timeout=timeout)
            r.raise_for_status(); return r.json()
        except Exception as e:
            last=e; time.sleep(min(backoff*(2**i),45))
    raise RuntimeError(f"api_post_failed endpoint={endpoint} err={last}")

def parse_pct(s):
    try: return float(str(s).replace('%','').replace(' ','').replace(',',''))
    except: return None

def parse_int(s):
    try: return int(float(str(s).replace(',','').strip()))
    except: return None

def parse_bool(s):
    return str(s).strip().lower() in ('1','true','yes')

def parse_date(s):
    try:
        p=str(s).split('-')
        return date(int(p[0]),int(p[1]),int(p[2])) if len(p)==3 else None
    except: return None

def upload_source(path):
    code=path.read_text(encoding='utf-8')
    return api_post('files/update',{'projectId':PROJECT_ID,'name':'main.py','content':code},timeout=90)

def compile_project():
    c=api_post('compile/create',{'projectId':PROJECT_ID},timeout=120); cid=c.get('compileId','')
    if not cid: return False,'',c
    for _ in range(120):
        r=api_post('compile/read',{'projectId':PROJECT_ID,'compileId':cid},timeout=60); st=r.get('state','')
        if st in ('BuildSuccess','BuildError','BuildWarning','BuildAborted'): return st=='BuildSuccess',cid,r
        time.sleep(2)
    return False,cid,{'error':'compile timeout'}

def set_parameters(params):
    return api_post('projects/update',{'projectId':PROJECT_ID,'parameters':[{'key':k,'value':str(v)} for k,v in params.items()]},timeout=90)

def create_backtest_retry(compile_id,name,wait_sec=20,max_retries=20):
    for _ in range(max_retries):
        d=api_post('backtests/create',{'projectId':PROJECT_ID,'compileId':compile_id,'backtestName':name},timeout=90)
        bid=(d.get('backtest') or {}).get('backtestId','')
        if d.get('success') and bid: return True,bid,d
        errs=' | '.join(d.get('errors',[]) or []).lower()
        if 'spare nodes' in errs or 'too many backtest requests' in errs or 'slow down' in errs:
            time.sleep(wait_sec); continue
        return False,'',d
    return False,'',{'errors':['create_backtest_retry_exhausted'],'success':False}

def poll_backtest(backtest_id,timeout_sec=2400):
    elapsed=0
    while elapsed < timeout_sec:
        d=api_post('backtests/read',{'projectId':PROJECT_ID,'backtestId':backtest_id},timeout=90)
        bt=d.get('backtest',{}); st=str(bt.get('status',''))
        if 'Completed' in st:
            time.sleep(2)
            d2=api_post('backtests/read',{'projectId':PROJECT_ID,'backtestId':backtest_id},timeout=90)
            return True,d2.get('backtest',bt)
        if 'Error' in st or 'Runtime' in st or 'Cancelled' in st:
            return False,bt
        time.sleep(10); elapsed += 10
    return False,{'status':'Timeout'}

def extract(bt,sy,sm,sd):
    s=bt.get('statistics',{}) or {}; rt=bt.get('runtimeStatistics',{}) or {}
    hit=parse_bool(rt.get('ChallengeTargetHit')); hit_date=parse_date(rt.get('ChallengeHitDate')); start=date(int(sy),int(sm),int(sd))
    days_start=None
    if hit and hit_date is not None:
        days_start=(hit_date-start).days+1
    return {
        'backtest_id':bt.get('backtestId'),'np':parse_pct(s.get('Net Profit')),'dd':parse_pct(s.get('Drawdown')),
        'dbr':parse_int(rt.get('DailyLossBreaches')),'tbr':parse_int(rt.get('TrailingBreaches')),
        'hit':hit,'days_tr':parse_int(rt.get('ChallengeDaysToTarget')),'hit_date':rt.get('ChallengeHitDate'),'days_start':days_start
    }

def base_common():
    return {
        'regime_mode':'PF100','profile_mode':'FAST_PASS','trade_nq':1,'trade_m2k':0,'trade_mym':0,'allow_shorts':1,
        'entry_hour':9,'entry_min':40,'second_entry_enabled':1,'second_entry_breakout_enabled':1,'second_entry_hour':9,'second_entry_min':55,
        'second_max_hold_hours':2,'trailing_lock_mode':'EOD','challenge_mode_enabled':1,'challenge_lock_on_target':1,'challenge_target_pct':0.06,
        'challenge_min_trading_days':0,'ext_use_vix':0,'ext_use_vixy':1,'ext_vixy_sma_period':5,'ext_vixy_ratio_threshold':1.0,
        'max_open_positions':3,'max_trades_per_symbol_day':2,'pf1_w2win':0,'pf1_tpd':1,
        'gap_atr_mult':0.15,'second_mom_entry_pct':0.0008,'second_stop_atr_mult':0.55,'second_target_atr_mult':1.20,
        'pf1_stop':0.42,'pf1_tgt':1.35,'pf1_mom':0.0005,
        'risk_per_trade':0.03,'pf1_risk':0.02,'max_contracts_per_trade':15,'pf1_maxc':6,
    }

def configs():
    b=base_common(); out=[]
    seeds=[
      ('C120_L50',{'max_atr_pct':0.013,'max_gap_entry_pct':0.02,'daily_loss_limit_pct':0.05,'trailing_dd_limit_pct':0.05}),
      ('C120_L40',{'max_atr_pct':0.013,'max_gap_entry_pct':0.02,'daily_loss_limit_pct':0.04,'trailing_dd_limit_pct':0.05}),
      ('C120_L34',{'max_atr_pct':0.013,'max_gap_entry_pct':0.02,'daily_loss_limit_pct':0.03,'trailing_dd_limit_pct':0.04}),
      ('C136_L50',{'max_atr_pct':0.03,'max_gap_entry_pct':0.0065,'daily_loss_limit_pct':0.05,'trailing_dd_limit_pct':0.05}),
      ('C136_L40',{'max_atr_pct':0.03,'max_gap_entry_pct':0.0065,'daily_loss_limit_pct':0.04,'trailing_dd_limit_pct':0.05}),
      ('C136_L34',{'max_atr_pct':0.03,'max_gap_entry_pct':0.0065,'daily_loss_limit_pct':0.03,'trailing_dd_limit_pct':0.04}),
    ]
    for label,extra in seeds:
        c=dict(b); c.update(extra); c['label']=label; out.append(c)
    return out

WINDOWS=[
 ('CH_2025',2025,1,1,2025,12,31),
 ('CH_2024',2024,1,1,2024,12,31),
 ('CH_2026_Q1',2026,1,1,2026,3,31),
 ('CH_2026_YTD',2026,1,1,2026,4,14),
]

def save(payload):
    payload['updated_utc']=datetime.utcnow().isoformat(timespec='seconds')+'Z'
    OUT_JSON.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    lines=[f"updated_utc={payload['updated_utc']}",'','=== PF100 FASTPASS STAGE16B TARGETED ===','']
    for r in payload.get('results',[]):
        lines.append(f"{r.get('label')} {r.get('window')} hit={r.get('hit')} start_d={r.get('days_start')} tr_d={r.get('days_tr')} np={r.get('np')} dd={r.get('dd')} dbr={r.get('dbr')} tbr={r.get('tbr')} err={r.get('error')} id={r.get('backtest_id')}")
    lines.append(''); lines.append('Score')
    for s in payload.get('score',[]):
        lines.append(f"{s['label']} score={s['score']} 2025_d={s['d2025']} 2024_d={s['d2024']} q1_d={s['d2026q1']} ytd_d={s['d2026ytd']} q1_np={s['np2026q1']} ytd_np={s['np2026ytd']}")
    OUT_TXT.write_text('\n'.join(lines),encoding='utf-8')

def main():
    up=upload_source(SOURCE_FILE)
    if not up.get('success'): raise RuntimeError(f"upload_failed: {up}")
    ok,cid,comp=compile_project()
    if not ok: raise RuntimeError(f"compile_failed: {comp}")

    payload={'results':[],'score':[]}; save(payload)

    for c in configs():
        cfg={k:v for k,v in c.items() if k!='label'}
        for w,sy,sm,sd,ey,em,ed in WINDOWS:
            p=dict(cfg); p.update({'start_year':sy,'start_month':sm,'start_day':sd,'end_year':ey,'end_month':em,'end_day':ed})
            upd=set_parameters(p)
            if not upd.get('success'):
                r={'label':c['label'],'window':w,'error':f"set_parameters_failed:{upd}"}
                payload['results'].append(r); save(payload); print('E',c['label'],w,'set_params_fail'); continue
            ok,bid,cd=create_backtest_retry(cid,f"{c['label']}_{w}_{int(time.time())}")
            if not ok:
                r={'label':c['label'],'window':w,'error':f"create_backtest_failed:{cd}"}
                payload['results'].append(r); save(payload); print('E',c['label'],w,'create_fail'); continue
            ok,bt=poll_backtest(bid)
            if not ok:
                r={'label':c['label'],'window':w,'backtest_id':bid,'error':f"poll_failed:{bt}"}
                payload['results'].append(r); save(payload); print('E',c['label'],w,'poll_fail'); continue
            m=extract(bt,sy,sm,sd); m.update({'label':c['label'],'window':w})
            payload['results'].append(m); save(payload)
            print(c['label'],w,'hit',m.get('hit'),'d',m.get('days_start'),'np',m.get('np'),'dbr',m.get('dbr'),'tbr',m.get('tbr'))
            time.sleep(2)

    by={}
    for r in payload['results']:
        by.setdefault(r['label'],{})[r['window']]=r
    score=[]
    for label,d in by.items():
        r25=d.get('CH_2025',{}); r24=d.get('CH_2024',{}); rQ=d.get('CH_2026_Q1',{}); rY=d.get('CH_2026_YTD',{})
        s=0.0
        for rr,wt in ((r25,1.0),(r24,0.7),(rQ,1.2),(rY,1.2)):
            if not rr or rr.get('error'):
                s += 2_000_000 * wt
                continue
            if not rr.get('hit'):
                s += 500_000 * wt
            s += (rr.get('days_start') or 250) * 1000 * wt
            s += ((rr.get('dbr') or 0) + (rr.get('tbr') or 0)) * 200_000 * wt
        score.append({
            'label':label,'score':round(s,3),
            'd2025':r25.get('days_start'),'d2024':r24.get('days_start'),'d2026q1':rQ.get('days_start'),'d2026ytd':rY.get('days_start'),
            'np2026q1':rQ.get('np'),'np2026ytd':rY.get('np')
        })
    score.sort(key=lambda x:x['score'])
    payload['score']=score
    save(payload)

if __name__=='__main__':
    main()
