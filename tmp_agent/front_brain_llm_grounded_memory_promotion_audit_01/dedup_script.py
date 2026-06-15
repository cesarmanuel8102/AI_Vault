import json, glob, os
from collections import Counter
from datetime import datetime

candidates = []
cand_id = 0

def infer_domain(cat):
    cat = cat.lower()
    if any(x in cat for x in ['provider','reliability','chain','latency','route']): return 'provider_reliability'
    if any(x in cat for x in ['dashboard','status','endpoint']): return 'dashboard_reliability'
    if any(x in cat for x in ['governance','scheduler','autonomy','bounded','cycle']): return 'governance'
    if any(x in cat for x in ['semantic','memory','staging','promotion','faiss']): return 'memory_quality'
    if any(x in cat for x in ['cei','fdot','practical','concrete']): return 'CEI_FDOT'
    if any(x in cat for x in ['financial','trading','broker','order']): return 'financial_safety'
    if any(x in cat for x in ['operator','ux','chat','ui']): return 'operator_ux'
    if any(x in cat for x in ['rollback','safety','verify']): return 'rollback_safety'
    if any(x in cat for x in ['report','audit','evidence']): return 'report_quality'
    return 'coding_debugging'

# promotion_queue
for f in sorted(glob.glob('memory/promotion_queue/*.json')):
    with open(f) as fh:
        data = json.load(fh)
    cand_id += 1
    summary = data.get('summary') or data.get('text','')
    conf = data.get('confidence',0.5)
    domain = infer_domain(data.get('category',''))
    candidates.append({
        'candidate_id': f'audit_{cand_id:04d}',
        'original_id': data.get('candidate_id', os.path.basename(f)),
        'source_path': f.replace('\\','/'),
        'source_type': 'promotion_queue',
        'created_utc': data.get('created_utc',''),
        'summary': summary[:300],
        'domain': domain,
        'quality_score': conf,
        'evidence_strength': 'high' if conf > 0.85 else ('medium' if conf > 0.7 else 'low'),
        'usefulness': 'high' if conf > 0.85 else ('medium' if conf > 0.7 else 'low'),
        'novelty': 'unknown',
        'duplicate_of': None,
        'contains_raw_cot': False,
        'contains_secret': False,
        'contains_trading_execution': False,
        'canonical_promotion_allowed': False,
        'audit_decision': 'promote_later' if conf >= 0.7 else ('needs_human_review' if conf >= 0.4 else 'reject')
    })

# semantic_staging (exclude duplicates by original_id already seen in promotion_queue)
seen_ids = {c['original_id'] for c in candidates}
for f in sorted(glob.glob('memory/semantic_staging/*.json')):
    bid = os.path.basename(f)
    if bid in seen_ids: continue
    with open(f) as fh:
        data = json.load(fh)
    cand_id += 1
    summary = data.get('summary') or data.get('text','')
    conf = data.get('confidence',0.5)
    domain = infer_domain(data.get('category',''))
    candidates.append({
        'candidate_id': f'audit_{cand_id:04d}',
        'original_id': data.get('candidate_id', bid),
        'source_path': f.replace('\\','/'),
        'source_type': 'semantic_staging',
        'created_utc': data.get('created_utc',''),
        'summary': summary[:300],
        'domain': domain,
        'quality_score': conf,
        'evidence_strength': 'high' if conf > 0.85 else ('medium' if conf > 0.7 else 'low'),
        'usefulness': 'high' if conf > 0.85 else ('medium' if conf > 0.7 else 'low'),
        'novelty': 'unknown',
        'duplicate_of': None,
        'contains_raw_cot': False,
        'contains_secret': False,
        'contains_trading_execution': False,
        'canonical_promotion_allowed': False,
        'audit_decision': 'promote_later' if conf >= 0.7 else ('needs_human_review' if conf >= 0.4 else 'reject')
    })

# semantic_memory_candidate.jsonl
jsonl_path = 'memory/semantic_staging/semantic_memory_candidate.jsonl'
if os.path.exists(jsonl_path):
    with open(jsonl_path) as jf:
        for line in jf:
            rec = json.loads(line.strip())
            cid = rec.get('candidate_id','')
            if cid in seen_ids: continue
            seen_ids.add(cid)
            cand_id += 1
            summary = rec.get('summary') or rec.get('text','')
            conf = rec.get('confidence',0.5)
            domain = infer_domain(rec.get('category',''))
            candidates.append({
                'candidate_id': f'audit_{cand_id:04d}',
                'original_id': cid,
                'source_path': jsonl_path,
                'source_type': 'semantic_memory_candidate_jsonl',
                'created_utc': rec.get('created_utc',''),
                'summary': summary[:300],
                'domain': domain,
                'quality_score': conf,
                'evidence_strength': 'high' if conf > 0.85 else ('medium' if conf > 0.7 else 'low'),
                'usefulness': 'high' if conf > 0.85 else ('medium' if conf > 0.7 else 'low'),
                'novelty': 'unknown',
                'duplicate_of': None,
                'contains_raw_cot': False,
                'contains_secret': False,
                'contains_trading_execution': False,
        'canonical_promotion_allowed': False,
        'audit_decision': 'promote_later' if conf >= 0.85 else ('needs_human_review' if conf >= 0.5 else 'reject')
    })

# Deduplicate by summary
summary_map = {}
for c in candidates:
    s = c['summary'].strip().lower()
    if s in summary_map:
        c['duplicate_of'] = summary_map[s]['candidate_id']
        c['audit_decision'] = 'duplicate'
    else:
        summary_map[s] = c

# Deduplicate by original_id
id_map = {}
for c in candidates:
    oid = c.get('original_id')
    if oid and oid in id_map:
        c['duplicate_of'] = id_map[oid]['candidate_id']
        c['audit_decision'] = 'duplicate'
    elif oid:
        id_map[oid] = c

# Safety screen — refined to avoid false positives
trading_phrases = ['place order','execute trade','broker api','trading execution','order execution','buy stock','sell stock']
secret_patterns = ['api_key =','password =','secret =','token =','apikey =']
for c in candidates:
    s = c['summary'].lower()
    if any(w in s for w in trading_phrases):
        c['contains_trading_execution'] = True
        c['audit_decision'] = 'unsafe_reject'
    if any(w in s for w in secret_patterns):
        c['contains_secret'] = True
        c['audit_decision'] = 'unsafe_reject'

domain_counts = Counter(c['domain'] for c in candidates)
decision_counts = Counter(c['audit_decision'] for c in candidates)

result = {
    'front': 'FRONT-BRAIN-LLM-GROUNDED-MEMORY-PROMOTION-AUDIT-01',
    'phase': 'PHASE_4_DEDUPLICATION_AND_SAFETY_SCREEN',
    'timestamp_utc': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S') + '+00:00',
    'total_candidates': len(candidates),
    'unique_candidates': len([c for c in candidates if c['audit_decision'] != 'duplicate']),
    'duplicates_marked': len([c for c in candidates if c['audit_decision'] == 'duplicate']),
    'unsafe_rejected': len([c for c in candidates if c['audit_decision'] == 'unsafe_reject']),
    'promote_later': len([c for c in candidates if c['audit_decision'] == 'promote_later']),
    'needs_human_review': len([c for c in candidates if c['audit_decision'] == 'needs_human_review']),
    'domain_distribution': dict(domain_counts),
    'decision_distribution': dict(decision_counts),
    'canonical_promotion_allowed_overall': False,
    'safety_verdict': 'SAFE_NO_CANONICAL_WRITE_THIS_FRONT',
    'candidates': candidates
}

with open('tmp_agent/front_brain_llm_grounded_memory_promotion_audit_01/deduplication_safety_screen.json','w') as out:
    json.dump(result, out, indent=2, default=str)

print(f'Total={len(candidates)} Unique={result["unique_candidates"]} Dup={result["duplicates_marked"]} Unsafe={result["unsafe_rejected"]} Later={result["promote_later"]} Review={result["needs_human_review"]}')
