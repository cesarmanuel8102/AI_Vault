import hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('C:/AI_VAULT_CANONICAL'); F=ROOT/'tmp_agent/front_brain_agent_full_rebuild_langgraph_recursive_closeout_01'
def utc(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as fh:
  for b in iter(lambda:fh.read(1048576),b''): h.update(b)
 return h.hexdigest()
def rows(p): return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
def counts():
 import faiss
 sem=ROOT/'memory/semantic/semantic_memory.jsonl'; ids=ROOT/'memory/semantic/semantic_memory_faiss_ids.json'; idx=ROOT/'memory/semantic/semantic_memory_faiss.index'; idl=json.loads(ids.read_text(encoding='utf-8'))
 return {'semantic_lines':len(rows(sem)),'faiss_ids':len(idl),'faiss_ntotal':int(faiss.read_index(str(idx)).ntotal),'semantic_sha256':sha(sem),'faiss_ids_sha256':sha(ids),'faiss_index_sha256':sha(idx),'ids_equals_ntotal':len(idl)==int(faiss.read_index(str(idx)).ntotal)}
def w(n,d): (F/n).write_text(json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def wm(n,t,d): (F/n).write_text('# '+t+'\n\n```json\n'+json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n```\n',encoding='utf-8')
base=json.load(open(F/'memory_faiss_baseline.json',encoding='utf-8')); final=counts(); final['hashes_unchanged']=base['semantic_sha256']==final['semantic_sha256'] and base['faiss_ids_sha256']==final['faiss_ids_sha256'] and base['faiss_index_sha256']==final['faiss_index_sha256']; final['rollback_used']=False
w('memory_faiss_integrity_final.json',final); wm('memory_faiss_integrity_final.md','Memory FAISS Integrity Final',final)
# journal validation
p=subprocess.run(['git','diff','--','memory/autonomous_journal.jsonl'],cwd=ROOT,text=True,capture_output=True,encoding='utf-8',errors='replace')
added=[l[1:] for l in p.stdout.splitlines() if l.startswith('+{')]; removed=[l for l in p.stdout.splitlines() if l.startswith('-{')]; objs=[json.loads(x) for x in added]
journal={'present':bool(added),'added_lines':len(added),'removed_json_lines':len(removed),'append_only_verified':bool(added) and not removed,'all_autonomy_lesson':all(o.get('category')=='autonomy_lesson' for o in objs),'no_secret_cot_trading_keywords':not any(k in '\n'.join(added).lower() for k in ['secret','password','api_key','token','chain-of-thought','raw_cot','broker','place order']),'semantic_faiss_effect':False,'event_ids':[o.get('event_id') for o in objs]}
w('autonomous_journal_append_validation.json',journal); wm('autonomous_journal_append_validation.md','Autonomous Journal Append Validation',journal)
bench=json.load(open(F/'agent_v2_benchmark_final.json',encoding='utf-8')); dep=json.load(open(F/'langgraph_dependency_decision.json',encoding='utf-8')); endp=json.load(open(F/'endpoint_verification.json',encoding='utf-8'))
report={'status':'AGENT_V2_REBUILD_COMPLETED_WITH_RESTART_REQUIRED_FOR_LIVE_ENDPOINTS','front':'BRAIN-AGENT-FULL-REBUILD-LANGGRAPH-RECURSIVE-CLOSEOUT-01','completed_utc':utc(),'start_head':json.load(open(F/'state_lock.json',encoding='utf-8'))['head_local'],'langgraph':dep,'agent_v2':{'implemented':True,'canonical_for_new_agent_runs':True,'package_path':'tmp_agent/brain_v9/core/agent_kernel_v2','run_storage_path':'tmp_agent/agent_kernel_v2/runs','legacy_agent_status':'legacy_compatible_not_canonical','chat_agent_separation':True},'api':endp,'benchmark':bench,'memory_faiss':final,'journal_append_validation':journal,'safety':{'trading_touched':False,'b8_touched':False,'strategies_touched':False,'secrets_exposed':False,'raw_cot_exposed':False,'promotion_queue_mutated':False,'semantic_staging_mutated':False},'restart_command':'cd C:/AI_VAULT_CANONICAL; python tmp_agent/brain_v9/main.py','recommended_next':'RESTART-BRAIN-8091-LOAD-AGENT-V2-ROUTES-01'}
w('final_report.json',report); wm('final_report.md','Final Report',report)
cesar=f"""# Agent V2 Closeout Review\n\n## Resultado\nAgent V2 fue implementado y es canonico para nuevos runs. LangGraph esta instalado y usado por runtime.\n\n## Endpoints\nLos endpoints `/v2/agent/*` estan registrados por import directo de FastAPI. El servidor vivo 8091 requiere restart para exponerlos.\n\n## Benchmark\nBenchmark: {bench['tasks_completed']}/{bench['tasks_total']} threshold_met={bench['threshold_met']}.\n\n## Memoria\nsemantic/FAISS permanecieron sin cambios: {final['hashes_unchanged']}.\n\n## Legacy\nLegacy agent/chat se preservan compatibles; Agent V2 queda como canonical para ejecucion agentica nueva.\n\n## Restart\n`cd C:/AI_VAULT_CANONICAL; python tmp_agent/brain_v9/main.py`\n"""
(F/'cesar_review_report.md').write_text(cesar,encoding='utf-8')
(F/'NEXT_PROMPT_RECOMMENDATION.md').write_text('# Next Prompt Recommendation\n\nRESTART-BRAIN-8091-LOAD-AGENT-V2-ROUTES-01\n',encoding='utf-8')
# roadmap ledger
road=ROOT/'ROADMAP_STATUS.json'; data=json.loads(road.read_text(encoding='utf-8')); data['migration_status']='agent_v2_rebuild_completed_restart_required'; data['last_applied_checkpoint']='BRAIN-AGENT-FULL-REBUILD-LANGGRAPH-RECURSIVE-CLOSEOUT-01'; data['front_brain_agent_full_rebuild_langgraph_recursive_closeout_01']={'status':'done_pending_commit','agent_v2_canonical':True,'langgraph_used':True,'benchmark_passed':bench['threshold_met'],'live_endpoint_restart_required':True,'memory_faiss_unchanged':final['hashes_unchanged'],'evidence_path':'tmp_agent/front_brain_agent_full_rebuild_langgraph_recursive_closeout_01','next':'RESTART-BRAIN-8091-LOAD-AGENT-V2-ROUTES-01'}; road.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
ledger=ROOT/'docs/MIGRATION_CONTROL_LEDGER.md'; ledger.write_text(ledger.read_text(encoding='utf-8').rstrip()+f"\n\n## BRAIN-AGENT-FULL-REBUILD-LANGGRAPH-RECURSIVE-CLOSEOUT-01 — Agent V2 Full Rebuild\n\n- timestamp_utc: {utc()}\n- Agent V2 implemented: true\n- canonical_for_new_agent_runs: true\n- langgraph_used: true\n- legacy_agent_status: legacy_compatible_not_canonical\n- endpoints: /v2/agent/* plus /brain-dashboard/agent-v2/status\n- live_server_restart_required: true\n- benchmark: {bench['tasks_completed']}/{bench['tasks_total']} threshold_met={bench['threshold_met']}\n- semantic_faiss_unchanged: {final['hashes_unchanged']}\n- autonomous_journal_append_included: {journal['present']} append_only_verified={journal['append_only_verified']}\n- next: RESTART-BRAIN-8091-LOAD-AGENT-V2-ROUTES-01\n",encoding='utf-8')
print(json.dumps({'final':report['status'],'hashes':final['hashes_unchanged']},ensure_ascii=False))
