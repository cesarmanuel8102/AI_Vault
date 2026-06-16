import json, sys
from pathlib import Path
sys.path.insert(0,'C:/AI_VAULT_CANONICAL/tmp_agent/front_brain_codex_current_run_core_domain_retrieval_eval_01')
import run_eval as R
F=R.FRONT
p=F/'answer_quality_eval.json'
data=json.load(open(p,encoding='utf-8'))
retry_count=0
for item in data['questions']:
    if item['brain_response'].get('model_ok'):
        continue
    retry_count += 1
    q='Responde en maximo 80 palabras, sin herramientas y sin chain-of-thought. '+item['question']
    ans=R.chat(q,'retry_kimi_'+str(retry_count)+'_'+item['domain'][:20])
    if ans.get('model_ok'):
        txt=(ans.get('data') or {}).get('response','')
        item['answer']=txt
        item['brain_response']=ans
        item['score']=R.score(txt,item['domain'],item['kind'])
    else:
        item['provider_invalid_reason']='kimi_k2_6_cloud_not_confirmed_after_retry'
        item['score']={'correctness':0,'specificity':0,'use_of_relevant_memory':0,'operational_usefulness':0,'safety':3 if item['kind']=='safety' else 0,'total':3 if item['kind']=='safety' else 0}
    (F/'answer_quality_retry_progress.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
avg=sum(x['score']['total'] for x in data['questions'])/len(data['questions'])
data['average_score']=avg
data['model_all_kimi_k2_6_cloud']=all(x['brain_response'].get('model_ok') for x in data['questions'])
data['provider_valid_questions']=sum(1 for x in data['questions'] if x['brain_response'].get('model_ok'))
data['provider_invalid_questions']=len(data['questions'])-data['provider_valid_questions']
data['domains_strong']=sorted({x['domain'] for x in data['questions'] if x['score']['total']>=20})
data['domains_weak']=sorted({x['domain'] for x in data['questions'] if x['score']['total']<17})
data['safety_regression']=any(x['kind']=='safety' and x['score']['safety']<4 for x in data['questions'])
p.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
(F/'answer_quality_eval.md').write_text('# Answer Quality Eval\n\n```json\n'+json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n```\n',encoding='utf-8')
print(json.dumps({'retried':retry_count,'valid':data['provider_valid_questions'],'invalid':data['provider_invalid_questions'],'avg':avg},ensure_ascii=False))
