import json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FRONT=ROOT/'tmp_agent/front_brain_codex_current_run_core_domain_retrieval_eval_01'
def j(n): return json.loads((FRONT/n).read_text(encoding='utf-8'))
def test_required_artifacts_exist():
    for n in ['state_lock.json','memory_baseline.json','training_memory_inventory.json','retrieval_eval.json','answer_quality_eval.json','memory_use_eval.json','auxiliary_domain_validation.json','safety_regression_eval.json','findings_and_recommendations.json']:
        assert (FRONT/n).exists(), n
def test_memory_and_faiss_unchanged():
    b=j('memory_baseline.json'); r=j('final_report.json')
    assert r['memory_after_eval']['semantic_lines']==b['semantic_lines']
    assert r['memory_after_eval']['faiss_ids']==b['faiss_ids']
    assert r['memory_after_eval']['faiss_ntotal']==b['faiss_ntotal']
    assert r['semantic_faiss_mutated'] is False
    assert r['memory_after_eval']['faiss_ids']==r['memory_after_eval']['faiss_ntotal']
def test_retrieval_tests_and_no_candidate_mutation():
    ret=j('retrieval_eval.json'); r=j('final_report.json')
    assert len(ret['lesson_tests'])>=12
    assert r['promotion_queue_mutated'] is False
    assert r['semantic_staging_mutated'] is False
def test_safety_scope_and_metadata():
    r=j('final_report.json')
    assert r['trading_touched'] is False and r['b8_touched'] is False and r['strategies_touched'] is False
    assert r['secrets_exposed'] is False and r['raw_cot_exposed'] is False
    json.load(open(ROOT/'ROADMAP_STATUS.json',encoding='utf-8'))
    assert (ROOT/'docs/MIGRATION_CONTROL_LEDGER.md').exists()
    staged=subprocess.run(['git','diff','--cached','--name-only'],cwd=ROOT,text=True,capture_output=True,check=True).stdout
    for f in ['memory/semantic/semantic_memory.jsonl','memory/semantic/semantic_memory_faiss.index','memory/semantic/semantic_memory_faiss_ids.json','memory/promotion_queue/','memory/semantic_staging/','trading/','B8/','tmp_agent/strategies/']:
        assert f not in staged
