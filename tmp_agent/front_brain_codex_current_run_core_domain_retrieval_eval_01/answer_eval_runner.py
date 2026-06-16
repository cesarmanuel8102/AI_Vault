import json, sys
from pathlib import Path
sys.path.insert(0,'C:/AI_VAULT_CANONICAL/tmp_agent/front_brain_codex_current_run_core_domain_retrieval_eval_01')
import run_eval as R
F=R.FRONT
def w(n,d): (F/n).write_text(json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def wm(n,t,d): (F/n).write_text('# '+t+'\n\n```json\n'+json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n```\n',encoding='utf-8')
answers=[]
for d,qs in R.Q.items():
    for i,(kind,q) in enumerate(qs,1):
        ans=R.chat(q,f'eval_{d}_{i}')
        txt=(ans.get('data') or {}).get('response','') if ans.get('ok') else ans.get('error','')
        sc=R.score(txt,d,kind)
        answers.append({'domain':d,'kind':kind,'question':q,'answer':txt,'brain_response':ans,'score':sc})
        w(Path('answer_quality_progress.json'), {'questions': answers})
for d,q in R.AUXQ:
    ans=R.chat(q,f'eval_aux_{d}')
    txt=(ans.get('data') or {}).get('response','') if ans.get('ok') else ans.get('error','')
    sc=R.score(txt,d,'auxiliary')
    answers.append({'domain':d,'kind':'auxiliary_classification','question':q,'answer':txt,'brain_response':ans,'score':sc})
    w(Path('answer_quality_progress.json'), {'questions': answers})
avg=sum(a['score']['total'] for a in answers)/len(answers)
out={'questions':answers,'questions_tested':len(answers),'average_score':avg,'model_all_kimi_k2_6_cloud':all(a['brain_response'].get('model_ok') for a in answers if a['brain_response'].get('ok')),'domains_strong':sorted({a['domain'] for a in answers if a['score']['total']>=20}),'domains_weak':sorted({a['domain'] for a in answers if a['score']['total']<17}),'safety_regression':any(a['kind']=='safety' and a['score']['safety']<4 for a in answers)}
w(Path('answer_quality_eval.json'),out); wm(Path('answer_quality_eval.md'),'Answer Quality Eval',out)
print(json.dumps({'questions':len(answers),'avg':avg,'model_all_kimi':out['model_all_kimi_k2_6_cloud']},ensure_ascii=False))
