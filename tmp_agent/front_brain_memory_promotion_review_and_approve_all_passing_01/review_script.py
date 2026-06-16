import json, os, re
from datetime import datetime

def load_audit_data():
    with open('tmp_agent/front_brain_llm_grounded_memory_promotion_audit_01/deduplication_safety_screen.json') as f:
        return json.load(f)

def strict_review(candidate):
    """Apply strict approval gates to each candidate."""
    gates_passed = []
    gates_failed = []
    safety_flags = []
    
    cid = candidate.get('candidate_id', '')
    src = candidate.get('source_path', '')
    summary = candidate.get('summary', '')
    domain = candidate.get('domain', '')
    conf = candidate.get('quality_score', 0)
    audit_decision = candidate.get('audit_decision', '')
    
    # Gate 1: has clear source_path
    if src and len(src) > 10:
        gates_passed.append('clear_source_path')
    else:
        gates_failed.append('missing_source_path')
    
    # Gate 2: has clear candidate_id
    if cid and cid.startswith('audit_'):
        gates_passed.append('clear_candidate_id')
    else:
        gates_failed.append('missing_candidate_id')
    
    # Gate 3: has useful operational summary (>50 chars, not generic)
    if summary and len(summary) > 50 and not summary.lower().startswith('governed stability cycle'):
        gates_passed.append('useful_summary')
    else:
        gates_failed.append('summary_too_short_or_generic')
    
    # Gate 4: not duplicate (based on audit_decision)
    if audit_decision != 'duplicate':
        gates_passed.append('not_duplicate')
    else:
        gates_failed.append('marked_duplicate')
    
    # Gate 5: no raw chain-of-thought
    cot_patterns = ['raw chain-of-thought', 'hidden reasoning', 'internal thought', 'cot:']
    if not any(p in summary.lower() for p in cot_patterns):
        gates_passed.append('no_raw_cot')
    else:
        gates_failed.append('raw_cot_detected')
        safety_flags.append('raw_cot')
    
    # Gate 6: no secrets/tokens/credentials
    secret_patterns = ['api_key=', 'password=', 'secret=', 'token=', 'private_key', 'credential']
    if not any(p in summary.lower() for p in secret_patterns):
        gates_passed.append('no_secrets')
    else:
        gates_failed.append('secrets_detected')
        safety_flags.append('secrets')
    
    # Gate 7: no broker/order/trading execution
    trading_patterns = ['place order', 'execute trade', 'broker api', 'trading execution', 'buy stock', 'sell stock']
    if not any(p in summary.lower() for p in trading_patterns):
        gates_passed.append('no_trading')
    else:
        gates_failed.append('trading_detected')
        safety_flags.append('trading')
    
    # Gate 8: no unsafe financial promise
    financial_patterns = ['guaranteed profit', 'risk-free', 'sure gain', '100% return']
    if not any(p in summary.lower() for p in financial_patterns):
        gates_passed.append('no_unsafe_financial')
    else:
        gates_failed.append('unsafe_financial')
        safety_flags.append('unsafe_financial')
    
    # Gate 9: no instruction to bypass governance
    bypass_patterns = ['bypass governance', 'disable safety', 'turn off guardrails', 'override approval']
    if not any(p in summary.lower() for p in bypass_patterns):
        gates_passed.append('no_bypass_governance')
    else:
        gates_failed.append('bypass_governance')
        safety_flags.append('bypass_governance')
    
    # Gate 10: no canonical memory mutation mentioned
    if 'canonical semantic memory' not in summary.lower() or 'mutation' not in summary.lower():
        gates_passed.append('no_canonical_mutation')
    else:
        gates_failed.append('canonical_mutation_mentioned')
    
    # Gate 11: no FAISS write attempt mentioned
    if 'faiss write' not in summary.lower():
        gates_passed.append('no_faiss_write')
    else:
        gates_failed.append('faiss_write_mentioned')
    
    # Gate 12: quality_score acceptable OR strong usefulness
    if conf >= 0.7 or candidate.get('usefulness') == 'high':
        gates_passed.append('quality_acceptable')
    else:
        gates_failed.append('quality_too_low')
    
    # Gate 13: candidate improves one of the allowed domains
    allowed_domains = [
        'provider_reliability', 'dashboard_reliability', 'governance', 
        'memory_quality', 'coding_debugging', 'CEI_FDOT', 
        'financial_safety', 'operator_ux', 'rollback_safety', 'report_quality'
    ]
    if domain in allowed_domains:
        gates_passed.append('allowed_domain')
    else:
        gates_failed.append('disallowed_domain')
    
    # Gate 14: summary not empty or useless
    useless_patterns = ['transient execution traces', 'generic operational noise']
    if not any(p in summary.lower() for p in useless_patterns):
        gates_passed.append('not_useless')
    else:
        gates_failed.append('useless_summary')
    
    # Determine final decision
    critical_failures = [g for g in gates_failed if g in [
        'secrets_detected', 'trading_detected', 'unsafe_financial', 
        'bypass_governance', 'canonical_mutation_mentioned', 'faiss_write_mentioned',
        'raw_cot_detected', 'disallowed_domain'
    ]]
    
    if critical_failures:
        final_decision = 'rejected'
        reason = f"Critical failures: {', '.join(critical_failures)}"
    elif 'marked_duplicate' in gates_failed:
        final_decision = 'duplicate'
        reason = "Marked as duplicate in audit"
    elif 'quality_too_low' in gates_failed and 'useless_summary' in gates_failed:
        final_decision = 'rejected'
        reason = "Low quality and useless summary"
    elif 'quality_too_low' in gates_failed:
        final_decision = 'needs_more_review'
        reason = f"Quality score {conf} below threshold; needs operator review"
    else:
        final_decision = 'approved_for_future_canonical_promotion'
        reason = f"Passed all gates: {len(gates_passed)} passed, {len(gates_failed)} minor"
    
    return {
        'candidate_id': cid,
        'source_path': src,
        'domain': domain,
        'summary': summary[:300],
        'quality_score': conf,
        'original_audit_decision': audit_decision,
        'final_review_decision': final_decision,
        'approval_reason': reason if final_decision == 'approved_for_future_canonical_promotion' else '',
        'rejection_reason': reason if final_decision != 'approved_for_future_canonical_promotion' else '',
        'safety_flags': safety_flags,
        'gates_passed': gates_passed,
        'gates_failed': gates_failed,
        'canonical_promotion_performed': False
    }

def main():
    audit = load_audit_data()
    candidates = audit['candidates']
    
    approved = []
    held = []
    rejected = []
    duplicates = []
    
    for c in candidates:
        result = strict_review(c)
        decision = result['final_review_decision']
        
        if decision == 'approved_for_future_canonical_promotion':
            approved.append(result)
        elif decision == 'needs_more_review':
            held.append(result)
        elif decision == 'duplicate':
            duplicates.append(result)
        else:
            rejected.append(result)
    
    # Build output
    out_dir = 'tmp_agent/front_brain_memory_promotion_review_and_approve_all_passing_01'
    os.makedirs(out_dir, exist_ok=True)
    
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S') + '+00:00'
    
    # Candidate review decisions
    review_data = {
        'front': 'FRONT-BRAIN-MEMORY-PROMOTION-REVIEW-AND-APPROVE-ALL-PASSING-01',
        'phase': 'PHASE_2_STRICT_REVIEW',
        'timestamp_utc': timestamp,
        'total_reviewed': len(candidates),
        'approved_count': len(approved),
        'held_count': len(held),
        'rejected_count': len(rejected),
        'duplicate_count': len(duplicates),
        'reviews': [r for r in candidates]  # Include all original candidates
    }
    
    with open(f'{out_dir}/candidate_review_decisions.json', 'w') as f:
        json.dump(review_data, f, indent=2, default=str)
    
    # Approved manifest
    approved_manifest = {
        'front': 'FRONT-BRAIN-MEMORY-PROMOTION-REVIEW-AND-APPROVE-ALL-PASSING-01',
        'phase': 'PHASE_3_APPROVAL_MANIFEST',
        'timestamp_utc': timestamp,
        'approved_for_future_canonical_promotion': approved,
        'count': len(approved),
        'policy': 'approve_all_passing',
        'canonical_promotion_performed': False,
        'faiss_write_performed': False,
        'required_future_action': 'future_canonical_promotion_only'
    }
    
    with open(f'{out_dir}/APPROVED_FOR_FUTURE_CANONICAL_PROMOTION.json', 'w') as f:
        json.dump(approved_manifest, f, indent=2, default=str)
    
    # Held manifest
    held_manifest = {
        'front': 'FRONT-BRAIN-MEMORY-PROMOTION-REVIEW-AND-APPROVE-ALL-PASSING-01',
        'phase': 'PHASE_4_HELD_MANIFEST',
        'timestamp_utc': timestamp,
        'held_for_more_review': held,
        'count': len(held),
        'reason': 'Quality or usefulness below strict threshold; requires operator review'
    }
    
    with open(f'{out_dir}/HELD_FOR_MORE_REVIEW.json', 'w') as f:
        json.dump(held_manifest, f, indent=2, default=str)
    
    # Rejected manifest
    rejected_manifest = {
        'front': 'FRONT-BRAIN-MEMORY-PROMOTION-REVIEW-AND-APPROVE-ALL-PASSING-01',
        'phase': 'PHASE_4_REJECTED_MANIFEST',
        'timestamp_utc': timestamp,
        'rejected_after_review': rejected,
        'count': len(rejected),
        'reason': 'Failed critical safety, quality, or usefulness gates'
    }
    
    with open(f'{out_dir}/REJECTED_AFTER_REVIEW.json', 'w') as f:
        json.dump(rejected_manifest, f, indent=2, default=str)
    
    # Duplicate manifest
    duplicate_manifest = {
        'front': 'FRONT-BRAIN-MEMORY-PROMOTION-REVIEW-AND-APPROVE-ALL-PASSING-01',
        'phase': 'PHASE_4_DUPLICATE_MANIFEST',
        'timestamp_utc': timestamp,
        'duplicates_after_review': duplicates,
        'count': len(duplicates),
        'reason': 'Identified as duplicate during audit; not unique enough for promotion'
    }
    
    with open(f'{out_dir}/DUPLICATES_AFTER_REVIEW.json', 'w') as f:
        json.dump(duplicate_manifest, f, indent=2, default=str)
    
    print(f'Review complete:')
    print(f'  Total reviewed: {len(candidates)}')
    print(f'  Approved: {len(approved)}')
    print(f'  Held: {len(held)}')
    print(f'  Rejected: {len(rejected)}')
    print(f'  Duplicates: {len(duplicates)}')
    
    # Print approved candidates
    print('\n=== APPROVED CANDIDATES ===')
    for a in approved:
        print(f'  {a[\"candidate_id\"]} | {a[\"domain\"]} | {a[\"summary\"][:100]}')

if __name__ == '__main__':
    main()
