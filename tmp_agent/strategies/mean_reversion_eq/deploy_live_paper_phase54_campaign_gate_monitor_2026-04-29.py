import base64, hashlib, json, re, time
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE='https://www.quantconnect.com/api/v2'
PROJECT_ID=30874635
SECRETS_PATH=Path(r'C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json')
MAIN_SOURCE=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main_phase54_campaign_gate_monitor.py')
OUT_JSON=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/live_deploy_phase54_campaign_gate_monitor_2026-04-29.json')

def load_creds():
    d=json.loads(SECRETS_PATH.read_text(encoding='utf-8'))
    return str(d.get('user_id') or d.get('userId')).strip(), str(d.get('api_token') or d.get('apiToken') or d.get('token')).strip()

def headers(uid,tok,ts=None):
    ts=int(ts or time.time()); sig=hashlib.sha256(f'{tok}:{ts}'.encode()).hexdigest(); auth=base64.b64encode(f'{uid}:{sig}'.encode()).decode()
    return {'Authorization':'Basic '+auth,'Timestamp':str(ts),'Content-Type':'application/json'}

def api_post(uid,tok,endpoint,payload,timeout=90,retries=8):
    last=None
    for i in range(retries):
        try:
            r=requests.post(f'{BASE}/{endpoint}',headers=headers(uid,tok),json=payload,timeout=timeout)
            try: data=r.json()
            except Exception: data={'success':False,'errors':[f'HTTP {r.status_code}',r.text[:500]]}
            if data.get('success'): return data
            msg=' '.join(data.get('errors') or [])
            m=re.search(r'Server Time:\s*(\d+)',msg)
            if m:
                r2=requests.post(f'{BASE}/{endpoint}',headers=headers(uid,tok,int(m.group(1))-1),json=payload,timeout=timeout)
                try: data2=r2.json()
                except Exception: data2={'success':False,'errors':[f'HTTP {r2.status_code}',r2.text[:500]]}
                if data2.get('success'): return data2
                data=data2
            last=data
        except Exception as e:
            last={'success':False,'errors':[str(e)]}
        time.sleep(min(3*(i+1),20))
    return last or {'success':False,'errors':['request failed']}

def compile_project(uid,tok):
    c=api_post(uid,tok,'compile/create',{'projectId':PROJECT_ID},timeout=120)
    cid=c.get('compileId')
    if not cid: raise RuntimeError(f'compile/create failed: {c}')
    for _ in range(180):
        r=api_post(uid,tok,'compile/read',{'projectId':PROJECT_ID,'compileId':cid},timeout=60)
        st=r.get('state','')
        if st in ('BuildSuccess','BuildWarning','BuildError','BuildAborted'):
            if st!='BuildSuccess': raise RuntimeError(f'compile failed: {st} | {r}')
            return cid
        time.sleep(2)
    raise RuntimeError('compile timeout')

def main():
    uid,tok=load_creds()
    out={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'project_id':PROJECT_ID,'profile':'PHASE54_CAMPAIGN_GATE_MONITOR','steps':[]}
    upd=api_post(uid,tok,'files/update',{'projectId':PROJECT_ID,'name':'main.py','content':MAIN_SOURCE.read_text(encoding='utf-8')},timeout=180)
    if not upd.get('success'): raise RuntimeError(f'files/update failed: {upd}')
    out['steps'].append({'step':'files_update_main','data':{'source':str(MAIN_SOURCE),'success':True}})

    params={'monitor_label':'PHASE54_CAMPAIGN_GATE_MONITOR','start_year':2024,'start_month':10,'start_day':1}
    p=api_post(uid,tok,'projects/update',{'projectId':PROJECT_ID,'parameters':[{'key':k,'value':str(v)} for k,v in params.items()]},timeout=90)
    if not p.get('success'): raise RuntimeError(f'projects/update failed: {p}')
    out['steps'].append({'step':'project_params_set','data':params})

    cid=compile_project(uid,tok); out['steps'].append({'step':'compile_done','data':{'compileId':cid}})

    live_before=api_post(uid,tok,'live/read',{'projectId':PROJECT_ID},timeout=60)
    before_status=str(live_before.get('status') or '')
    out['steps'].append({'step':'live_before','data':{'status':before_status,'deployId':live_before.get('deployId'),'brokerage':live_before.get('brokerage'),'nodeId':live_before.get('nodeId')}})
    if before_status.lower() in ('running','initializing','loggingin','runtimeerror'):
        stop=api_post(uid,tok,'live/update/stop',{'projectId':PROJECT_ID},timeout=60)
        out['steps'].append({'step':'live_stop','data':{'success':stop.get('success'),'errors':stop.get('errors')}})
        for i in range(40):
            time.sleep(3)
            chk=api_post(uid,tok,'live/read',{'projectId':PROJECT_ID},timeout=60)
            st=str(chk.get('status') or '')
            if st.lower() not in ('running','initializing','loggingin'):
                out['steps'].append({'step':'live_stopped_confirm','data':{'attempt':i+1,'status':st}})
                break

    node_id=live_before.get('nodeId') or 'LN-64d4787830461ee45574254f643f69b3'
    payload={'projectId':PROJECT_ID,'compileId':cid,'nodeId':node_id,'versionId':'-1','automaticRedeploy':True,'brokerage':{'id':'QuantConnectBrokerage'},'dataProviders':{'QuantConnectBrokerage':{'id':'QuantConnectBrokerage'}}}
    create=None; errs=[]
    for retry in range(12):
        r=api_post(uid,tok,'live/create',payload,timeout=120)
        if r.get('success'):
            create=r; out['steps'].append({'step':'live_create_ok','data':{'retry':retry+1,'deployId':r.get('deployId')}}); break
        msg=' '.join(r.get('errors') or [])
        if 'still being processing' in msg.lower():
            wait_s=20; m=re.search(r'try again in (\d+) seconds',msg,flags=re.I)
            if m: wait_s=max(5,int(m.group(1))+2)
            time.sleep(wait_s); continue
        errs.append({'retry':retry+1,'errors':r.get('errors'),'response':r}); break
    if create is None:
        out['steps'].append({'step':'live_create_failed','data':errs}); OUT_JSON.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({'ok':False,'out_json':str(OUT_JSON),'errors':errs},indent=2,ensure_ascii=False)); return
    deploy_id=create.get('deployId')
    confirm=None
    for i in range(60):
        time.sleep(3)
        chk=api_post(uid,tok,'live/read',{'projectId':PROJECT_ID},timeout=60)
        st=str(chk.get('status') or '').lower()
        if chk.get('deployId')==deploy_id and st in ('running','initializing','loggingin'):
            confirm=chk; out['steps'].append({'step':'live_confirm','data':{'attempt':i+1,'deployId':chk.get('deployId'),'status':chk.get('status'),'launched':chk.get('launched'),'brokerage':chk.get('brokerage'),'nodeId':chk.get('nodeId')}}); break
    OUT_JSON.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'ok':True,'project_id':PROJECT_ID,'out_json':str(OUT_JSON),'deployId':deploy_id,'status':(confirm or {}).get('status'),'launched':(confirm or {}).get('launched'),'brokerage':(confirm or {}).get('brokerage')},indent=2,ensure_ascii=False))

if __name__=='__main__': main()
