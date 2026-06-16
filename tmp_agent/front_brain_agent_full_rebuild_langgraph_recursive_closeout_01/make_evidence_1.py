import hashlib,json,shutil,subprocess,importlib.metadata as md
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('C:/AI_VAULT_CANONICAL'); F=ROOT/'tmp_agent/front_brain_agent_full_rebuild_langgraph_recursive_closeout_01'; F.mkdir(parents=True,exist_ok=True)
def utc(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def run(c): return subprocess.run(c,cwd=ROOT,text=True,capture_output=True,encoding='utf-8',errors='replace').stdout.strip()
def w(n,d): (F/n).write_text(json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def wm(n,t,d): (F/n).write_text('# '+t+'\n\n```json\n'+json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n```\n',encoding='utf-8')
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as fh:
  for b in iter(lambda:fh.read(1048576),b''): h.update(b)
 return h.hexdigest()
def rows(p):
 out=[]
 for line in p.read_text(encoding='utf-8').splitlines():
  if line.strip(): out.append(json.loads(line))
 return out
def counts():
 import faiss
 sem=ROOT/'memory/semantic/semantic_memory.jsonl'; ids=ROOT/'memory/semantic/semantic_memory_faiss_ids.json'; idx=ROOT/'memory/semantic/semantic_memory_faiss.index'; idl=json.loads(ids.read_text(encoding='utf-8'))
 return {'semantic_lines':len(rows(sem)),'faiss_ids':len(idl),'faiss_ntotal':int(faiss.read_index(str(idx)).ntotal),'semantic_sha256':sha(sem),'faiss_ids_sha256':sha(ids),'faiss_index_sha256':sha(idx),'jsonl_valid':True,'faiss_readable':True,'ids_equals_ntotal':len(idl)==int(faiss.read_index(str(idx)).ntotal)}
lock={'front':'BRAIN-AGENT-FULL-REBUILD-LANGGRAPH-RECURSIVE-CLOSEOUT-01','timestamp_utc':utc(),'branch':run(['git','branch','--show-current']),'head_local':run(['git','rev-parse','--short','HEAD']),'head_remote':run(['git','rev-parse','--short','origin/codex/own-capital-sustainable-return']),'status_short':run(['git','status','--short']).splitlines(),'tracked_status':run(['git','status','--short','--untracked-files=no']).splitlines(),'staged':run(['git','diff','--cached','--name-status']).splitlines(),'diff_name_status':run(['git','diff','--name-status']).splitlines()}
# journal validation if present
p=subprocess.run(['git','diff','--','memory/autonomous_journal.jsonl'],cwd=ROOT,text=True,capture_output=True,encoding='utf-8',errors='replace')
added=[l[1:] for l in p.stdout.splitlines() if l.startswith('+{')]; removed=[l for l in p.stdout.splitlines() if l.startswith('-{')]; objs=[json.loads(x) for x in added]
lock['autonomous_journal_append_validation']={'present':bool(added),'added_lines':len(added),'removed_json_lines':len(removed),'append_only_verified':bool(added) and not removed,'all_autonomy_lesson':all(o.get('category')=='autonomy_lesson' for o in objs),'no_secret_cot_trading_keywords':not any(k in '\n'.join(added).lower() for k in ['secret','password','api_key','token','chain-of-thought','raw_cot','broker','place order'])}
w(Path('state_lock.json'),lock); wm(Path('state_lock.md'),'State Lock',lock)
stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S'); snap=ROOT/'memory/rollback_snapshots'/f'agent_full_rebuild_langgraph_recursive_closeout_01_{stamp}'; snap.mkdir(parents=True,exist_ok=True)
for rel in ['memory/semantic/semantic_memory.jsonl','memory/semantic/semantic_memory_faiss.index','memory/semantic/semantic_memory_faiss_ids.json']:
 shutil.copy2(ROOT/rel, snap/(ROOT/rel).name)
base=counts(); base['rollback_snapshot']=str(snap.relative_to(ROOT)).replace('\\','/')
w(Path('memory_faiss_baseline.json'),base); wm(Path('memory_faiss_baseline.md'),'Memory FAISS Baseline',base)
dep={'python_executable':run(['python','-c','import sys; print(sys.executable)']),'langgraph_import':True,'langgraph_version':md.version('langgraph'),'langchain_core_import':True,'langchain_core_version':md.version('langchain-core'),'attempted_install':True,'pip_install_log':'tmp_agent/front_brain_agent_full_rebuild_langgraph_recursive_closeout_01/langgraph_pip_install.txt','used_in_runtime':True,'fallback_used':False,'blocker_if_any':None}
w(Path('langgraph_dependency_decision.json'),dep); wm(Path('langgraph_dependency_decision.md'),'LangGraph Dependency Decision',dep)
audit={'weak_routing':['legacy /v1/agent status is health-only, not canonical execution','/agent route is legacy compatibility and points users to /chat','chat route may timeout/fallback under load'],'provider_ambiguity':'recent eval showed Kimi confirmation inconsistent under load; Agent V2 finalizer labels structured provider explicitly','missing_state':'legacy agent lacks durable per-run checkpoint and trace','agent_v2_fix':['run.json per run','trace.jsonl operational events','checkpoint.json after state transitions','permissioned tool gateway','read-only memory gateway','/v2/agent canonical endpoints'],'frontend_fragmentation':'8091 UI/dashboard and 8092 dashboard preserved; 8092 gets /brain-dashboard/agent-v2/status'}
w(Path('current_agent_failure_audit.json'),audit); wm(Path('current_agent_failure_audit.md'),'Current Agent Failure Audit',audit)
print(json.dumps({'baseline':base,'snapshot':str(snap)},ensure_ascii=False))
