import json, sys, urllib.request
from pathlib import Path
ROOT=Path('C:/AI_VAULT_CANONICAL'); F=ROOT/'tmp_agent/front_brain_agent_full_rebuild_langgraph_recursive_closeout_01'
def probe(url, method='GET', data=None):
    try:
        body=json.dumps(data).encode() if data is not None else None
        req=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json'},method=method)
        with urllib.request.urlopen(req,timeout=5) as r:
            return {'ok':True,'status':r.status,'body':r.read(1000).decode('utf-8','replace')}
    except Exception as e:
        return {'ok':False,'error':repr(e)[:250]}
existing={u:probe(u) for u in ['http://127.0.0.1:8091/health','http://127.0.0.1:8091/status','http://127.0.0.1:8091/ui/','http://127.0.0.1:8091/dashboard','http://127.0.0.1:8092/','http://127.0.0.1:8092/health','http://127.0.0.1:8092/brain-dashboard/status']}
new_caps=probe('http://127.0.0.1:8091/v2/agent/capabilities')
new_status=probe('http://127.0.0.1:8091/v2/agent/status')
run_probe=probe('http://127.0.0.1:8091/v2/agent/runs','POST',{'goal':'endpoint verification','mode':'read_only'})
# direct route registration
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tmp_agent'))
direct={'import_ok':False,'routes':[],'new_routes_registered':False,'error':None}
try:
    from brain_v9.main import app
    routes=sorted(getattr(r,'path','') for r in app.routes)
    direct={'import_ok':True,'routes':[r for r in routes if '/v2/agent' in r or '/brain-dashboard/agent-v2/status' in r],'new_routes_registered':('/v2/agent/status' in routes and '/v2/agent/runs' in routes),'error':None}
except Exception as e:
    direct['error']=repr(e)
res={'existing_live':existing,'new_live':{'capabilities':new_caps,'status':new_status,'create_run':run_probe},'direct_app_route_registration':direct,'live_server_reload_required':not new_caps.get('ok'),'restart_command':'cd C:/AI_VAULT_CANONICAL; python tmp_agent/brain_v9/main.py'}
(F/'endpoint_verification.json').write_text(json.dumps(res,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
(F/'endpoint_verification.md').write_text('# Endpoint Verification\n\n```json\n'+json.dumps(res,ensure_ascii=False,indent=2,sort_keys=True)+'\n```\n',encoding='utf-8')
print(json.dumps({'live_new_ok':new_caps.get('ok'),'direct':direct['new_routes_registered']},ensure_ascii=False))

