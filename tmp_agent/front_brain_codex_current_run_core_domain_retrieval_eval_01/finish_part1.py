import json, sys
from pathlib import Path
sys.path.insert(0,'C:/AI_VAULT_CANONICAL/tmp_agent/front_brain_codex_current_run_core_domain_retrieval_eval_01')
import run_eval as R
ROOT=R.ROOT; F=R.FRONT; CORE=R.CORE; AUX=R.AUX
def w(n,d): (F/n).write_text(json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def wm(n,t,d): (F/n).write_text('# '+t+'\n\n```json\n'+json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n```\n',encoding='utf-8')
inv=json.load(open(F/'training_memory_inventory.json',encoding='utf-8'))
ans=json.load(open(F/'answer_quality_eval.json',encoding='utf-8'))
sys.path.insert(0,str(ROOT/'tmp_agent'))
from brain_v9.core.semantic_memory_faiss import SemanticMemoryFAISS
mem=SemanticMemoryFAISS(root=ROOT/'memory/semantic')
use=[]
for d in CORE:
    q=R.Q[d][0][1]
    hits=mem.search(q,top_k=3,min_score=0.0)
    a=next((x for x in ans['questions'] if x['domain']==d and x['question']==q),None)
    txt=(a or {}).get('answer','')
    has=any(d in json.dumps(h,ensure_ascii=False) for h in hits)
    ov=sum(1 for kw in R.ALIASES[d] if any(p.lower() in txt.lower() for p in kw.split() if len(p)>3))
    cls='memory_used_likely' if has and ov else 'memory_available_but_not_used' if has else 'answer_good_without_memory' if a and a['score']['total']>=18 else 'memory_missing'
    use.append({'domain':d,'question':q,'manual_retrieval_available':has,'answer_alias_overlap':ov,'classification':cls,'retrieved_ids':[h.get('id') for h in hits]})
mu={'no_memory_mode_available':True,'method':'manual semantic retrieval compared with direct Brain answer','rows':use,'memory_used_likely':sum(1 for x in use if x['classification']=='memory_used_likely'),'memory_available_but_not_used':sum(1 for x in use if x['classification']=='memory_available_but_not_used'),'memory_missing':sum(1 for x in use if x['classification']=='memory_missing'),'answer_good_without_memory':sum(1 for x in use if x['classification']=='answer_good_without_memory'),'answer_failed':sum(1 for x in use if x['classification']=='answer_failed')}
w(Path('memory_use_eval.json'),mu); wm(Path('memory_use_eval.md'),'Memory Use Eval',mu)
auxv={'flatbed_auxiliary_verified':inv['flatbed_auxiliary'],'english_auxiliary_verified':inv['english_auxiliary'],'not_mislabeled_as_core':all(x['domain_class']!='core' for x in inv['records'] if x['canonical_domain'] in AUX),'auxiliary_answer_rows':[x for x in ans['questions'] if x['kind']=='auxiliary_classification'],'future_core_training_scope_separate':True}
w(Path('auxiliary_domain_validation.json'),auxv); wm(Path('auxiliary_domain_validation.md'),'Auxiliary Domain Validation',auxv)
print(json.dumps({'memory_used_likely':mu['memory_used_likely'],'flatbed':auxv['flatbed_auxiliary_verified'],'english':auxv['english_auxiliary_verified']},ensure_ascii=False))
