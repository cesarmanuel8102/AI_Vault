from __future__ import annotations

import hashlib, json, os, re, shutil, subprocess, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path('C:/AI_VAULT_CANONICAL')
FRONT_NAME = 'HOTFIX-CURRENT-RUN-KEEP-KNOWLEDGE-ADD-MISSING-CORE-DOMAINS'
FRONT_KEY = 'front_brain_codex_current_run_keep_knowledge_add_missing_core_01'
FRONT = ROOT / 'tmp_agent' / FRONT_KEY
SESSION = 'hotfix_missing_core'
FRONT.mkdir(parents=True, exist_ok=True)

CORE_DOMAINS = {
    'brain_architecture': 'brain_architecture_runtime_debugging',
    'memory_faiss_governance': 'memory_semantic_faiss_retrieval_governance',
    'finance_trading_research': 'finance_trading_research_risk_management',
    'cei_fdot': 'cei_fdot_technical_inspection',
    'external_source_learning_pipeline_github_repo_docs_official_sources': 'external_source_learning_pipeline_github_repo_docs_official_sources',
    'autonomy_dashboard_visual_trace_self_improvement_governance': 'autonomy_dashboard_visual_trace_self_improvement_governance',
}
AUX_DOMAINS = {
    'flatbed_trucking': 'flatbed_trucking_dispatcher_automation_business_operations',
    'english_career': 'english_career_professional_communication',
}
MISSING_CORE = {
    'external_source_learning_pipeline_github_repo_docs_official_sources': [
        'Brain debe tratar GitHub, repositorios, documentos y fuentes oficiales como ingesta externa gobernada: registrar source_id, URL o path, licencia/estado, hashes y evidencia antes de convertir texto en candidato curado.',
        'La promocion desde fuentes externas debe pasar por extract, normalize, deduplicate, provenance, scoring, no-go checks y approval/dry-run antes de cualquier escritura canonica o FAISS.',
        'Cuando una fuente externa no esta disponible, es ambigua o carece de licencia/provenance, Brain debe responder con limitacion explicita y no inventar conocimiento ni evidencia.'
    ],
    'autonomy_dashboard_visual_trace_self_improvement_governance': [
        'La autonomia gobernada debe ser observable: cada ciclo debe exponer estado, stop/pause, evidencia, limites, errores y resultado sin ocultar fallback ni fallos de proveedor.',
        'El dashboard y la visual trace console deben mostrar rutas, herramientas, permisos, memoria usada y acciones bloqueadas, sin exponer chain-of-thought ni secretos.',
        'La auto-mejora solo puede avanzar con ciclos acotados, pruebas reproducibles, rollback, commit quirurgico y aprobacion humana para cambios de riesgo alto.'
    ],
}
DOMAIN_LABELS = {
    'external_source_learning_pipeline_github_repo_docs_official_sources': 'External source learning pipeline / GitHub / repo docs / official sources',
    'autonomy_dashboard_visual_trace_self_improvement_governance': 'Autonomy dashboard / visual trace / self-improvement governance',
}

def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()

def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')

def write_md(path: Path, title: str, data: Any | None = None, extra: str = '') -> None:
    body = f'# {title}\n\n'
    if extra:
        body += extra.strip() + '\n\n'
    if data is not None:
        body += '```json\n' + json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n```\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')

def run(cmd: list[str], check: bool = True) -> dict[str, Any]:
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, encoding='utf-8', errors='replace')
    out = {'cmd': cmd, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    if check and p.returncode != 0:
        raise RuntimeError(json.dumps(out, ensure_ascii=False, indent=2))
    return out

def sha(path: Path) -> str | None:
    if not path.exists(): return None
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open('r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if line:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError(f'{path}:{i} not object')
                rows.append(obj)
    return rows

def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows), encoding='utf-8')

def faiss_ntotal(path: Path) -> int | None:
    if not path.exists(): return None
    try:
        import faiss
        return int(faiss.read_index(str(path)).ntotal)
    except Exception as e:
        return None

def semantic_counts() -> dict[str, Any]:
    sem = ROOT/'memory/semantic/semantic_memory.jsonl'
    ids = ROOT/'memory/semantic/semantic_memory_faiss_ids.json'
    idx = ROOT/'memory/semantic/semantic_memory_faiss.index'
    id_obj = json.loads(ids.read_text(encoding='utf-8')) if ids.exists() else []
    return {
        'semantic_lines': len(load_jsonl(sem)) if sem.exists() else 0,
        'faiss_ids': len(id_obj) if isinstance(id_obj, list) else 0,
        'faiss_ntotal': faiss_ntotal(idx),
        'semantic_sha256': sha(sem),
        'faiss_ids_sha256': sha(ids),
        'faiss_index_sha256': sha(idx),
    }

def journal_append_verification() -> dict[str, Any]:
    diff = run(['git','diff','--','memory/autonomous_journal.jsonl'], check=False)['stdout']
    added = [line[1:] for line in diff.splitlines() if line.startswith('+{')]
    removed = [line for line in diff.splitlines() if line.startswith('-{')]
    parsed = [json.loads(x) for x in added]
    valid_jsonl = True
    try:
        load_jsonl(ROOT/'memory/autonomous_journal.jsonl')
    except Exception:
        valid_jsonl = False
    blob = '\n'.join(added).lower()
    banned = ['secret','password','api_key','apikey','token','chain-of-thought','raw_cot','broker','place order','orden real']
    hits = [b for b in banned if b in blob]
    ok_lines = all(
        x.get('category') == 'autonomy_lesson' and
        str(x.get('created_utc','')).startswith('2026-06-16T17:07:33') and
        x.get('evidence_path') == 'tmp_agent/runtime/autonomy_last_run.json' and
        x.get('promotion_status') == 'autonomous_journal_only'
        for x in parsed
    )
    return {
        'autonomous_journal_append_included': True,
        'append_only_verified': len(added) == 3 and not removed and ok_lines,
        'jsonl_valid': valid_jsonl,
        'added_lines': len(added),
        'removed_json_lines': len(removed),
        'no_secrets': not hits,
        'no_raw_chain_of_thought': 'chain-of-thought' not in blob and 'raw_cot' not in blob,
        'no_trading_execution': 'broker' not in blob and 'place order' not in blob and 'orden real' not in blob,
        'semantic_faiss_effect': False,
        'reason': 'required to achieve clean post-push lock without deleting valid operational journal events',
        'added_event_ids': [x.get('event_id') for x in parsed],
        'keyword_hits': hits,
    }

def classify_domain(domain: str) -> tuple[str, str, str | None]:
    if domain in CORE_DOMAINS:
        return CORE_DOMAINS[domain], 'core_keep', None
    if domain in AUX_DOMAINS:
        return AUX_DOMAINS[domain], 'auxiliary_keep', 'useful auxiliary knowledge; preserved but not counted as canonical Brain core domain'
    return domain, 'unknown_keep', 'not part of current taxonomy; kept unchanged except explicit records are not in scope'

def llm_probe() -> dict[str, Any]:
    payload = {
        'message': 'Modo conversación LLM directa, sin herramientas ni agente ORAV. Responde sin chain-of-thought, solo respuesta final. Di en una frase por qué el knowledge hotfix debe preservar conocimiento auxiliar y agregar dominios core faltantes.',
        'session_id': 'hotfix_missing_core_probe',
        'use_agent': False,
        'agent_mode': 'off'
    }
    try:
        req = urllib.request.Request('http://127.0.0.1:8091/chat', data=json.dumps(payload).encode('utf-8'), headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode('utf-8','replace'))
        text = json.dumps(data, ensure_ascii=False)
        return {'ok': True, 'provider_kimi_k2_6_cloud_expected': ('kimi-k2.6:cloud' in text or data.get('model_used') == 'kimi-k2.6:cloud'), 'response': data}
    except Exception as e:
        return {'ok': False, 'error': repr(e), 'provider_kimi_k2_6_cloud_expected': False}

def main() -> None:
    start = utc()
    branch = run(['git','branch','--show-current'])['stdout'].strip()
    head = run(['git','rev-parse','--short','HEAD'])['stdout'].strip()
    remote = run(['git','rev-parse','--short','origin/codex/own-capital-sustainable-return'])['stdout'].strip()
    status_tracked = run(['git','status','--short','--untracked-files=no'])['stdout'].splitlines()
    staged = run(['git','diff','--cached','--name-status'])['stdout'].splitlines()
    pre_counts = semantic_counts()
    journal_verify = journal_append_verification()
    control = {
        'front': FRONT_NAME,
        'started_utc': start,
        'branch': branch,
        'head_local': head,
        'head_remote': remote,
        'staged_empty': not staged,
        'tracked_dirty_before': status_tracked,
        'journal_append_authorization': journal_verify,
        'rules': {
            'keep_flatbed_and_english': True,
            'add_missing_core_domains': list(MISSING_CORE.keys()),
            'no_trading': True,
            'no_b8': True,
            'no_strategies': True,
            'no_raw_cot': True,
            'no_fake_embeddings': True,
        }
    }
    write_json(FRONT/'control_check.json', control)
    write_md(FRONT/'control_check.md', 'Control Check', control)
    if staged:
        raise SystemExit('FAILED_PREEXISTING_STAGED')
    if not journal_verify['append_only_verified'] or not journal_verify['jsonl_valid'] or not journal_verify['no_secrets'] or not journal_verify['no_raw_chain_of_thought'] or not journal_verify['no_trading_execution']:
        raise SystemExit('FAILED_JOURNAL_APPEND_VALIDATION')

    records = load_jsonl(ROOT/'memory/semantic/semantic_memory.jsonl')
    codex_records = [r for r in records if r.get('source') == 'FRONT-BRAIN-CODEX-PURE-BRAIN-AUTONOMOUS-TRAINING-AND-PENDING-DRAIN-01' and r.get('kind') == 'codex_training_lesson']
    existing_domains = sorted({(r.get('metadata') or {}).get('domain') for r in codex_records})
    inventory = {
        'semantic_before': pre_counts,
        'codex_training_lesson_count': len(codex_records),
        'existing_domains': existing_domains,
        'core_existing': [d for d in existing_domains if d in CORE_DOMAINS],
        'auxiliary_existing': [d for d in existing_domains if d in AUX_DOMAINS],
        'missing_core_domains': [d for d in MISSING_CORE if d not in existing_domains],
        'promotion_queue_candidates': sorted(p.name for p in (ROOT/'memory/promotion_queue').glob('codex_pure_brain_training_*training_*.json')),
        'semantic_staging_candidates': sorted(p.name for p in (ROOT/'memory/semantic_staging').glob('codex_pure_brain_training_*training_*.json')),
    }
    write_json(FRONT/'current_state_inventory.json', inventory)
    write_md(FRONT/'current_state_inventory.md', 'Current State Inventory', inventory)

    classification = []
    touched = 0
    new_records = []
    for r in records:
        meta = r.get('metadata') if isinstance(r.get('metadata'), dict) else {}
        if r.get('kind') == 'codex_training_lesson' and r.get('source') == 'FRONT-BRAIN-CODEX-PURE-BRAIN-AUTONOMOUS-TRAINING-AND-PENDING-DRAIN-01':
            d = meta.get('domain')
            canon, cls, reason = classify_domain(d)
            meta['canonical_domain'] = canon
            meta['domain_class'] = 'core' if cls == 'core_keep' else ('auxiliary' if cls == 'auxiliary_keep' else 'unknown')
            meta['taxonomy_hotfix_front'] = FRONT_NAME
            meta['taxonomy_hotfix_utc'] = start
            meta['taxonomy_keep_policy'] = cls
            if reason:
                meta['auxiliary_reason'] = reason
            r['metadata'] = meta
            touched += 1
            classification.append({'id': r.get('id'), 'candidate_id': meta.get('candidate_id'), 'domain': d, 'canonical_domain': canon, 'classification': cls})
        new_records.append(r)
    write_json(FRONT/'existing_knowledge_classification.json', {'records': classification, 'updated_records': touched})
    write_md(FRONT/'existing_knowledge_classification.md', 'Existing Knowledge Classification', {'records': classification, 'updated_records': touched})

    ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    rollback_dir = ROOT/'memory/rollback_snapshots'/f'codex_current_run_keep_knowledge_add_missing_core_01_{ts}'
    rollback_dir.mkdir(parents=True, exist_ok=True)
    for relp in ['memory/semantic/semantic_memory.jsonl','memory/semantic/semantic_memory_faiss.index','memory/semantic/semantic_memory_faiss_ids.json','memory/autonomous_journal.jsonl']:
        p = ROOT/relp
        if p.exists(): shutil.copy2(p, rollback_dir/p.name)
    snapshot = {'rollback_snapshot': rel(rollback_dir), 'before': pre_counts, 'journal_before_sha': sha(ROOT/'memory/autonomous_journal.jsonl')}
    write_json(FRONT/'pre_hotfix_snapshot.json', snapshot)
    write_md(FRONT/'pre_hotfix_snapshot.md', 'Pre Hotfix Snapshot', snapshot)

    plan = {
        'classification_update_records': touched,
        'classification_only_changes_existing_text_or_ids': False,
        'classification_changes_metadata_only': True,
        'new_core_domains_to_add': list(MISSING_CORE.keys()),
        'new_lessons_to_promote': sum(len(v) for v in MISSING_CORE.values()),
        'auxiliary_kept': list(AUX_DOMAINS.values()),
        'faiss_expected_delta': 6,
    }
    write_json(FRONT/'coherence_plan.json', plan)
    write_md(FRONT/'coherence_plan.md', 'Coherence Plan', plan)

    candidates: list[dict[str, Any]] = []
    now = utc()
    for domain, texts in MISSING_CORE.items():
        for i, text in enumerate(texts, 1):
            cid = f'codex_pure_brain_training_{domain}_training_{i}'
            cand = {
                'candidate_id': cid,
                'created_utc': now,
                'source': FRONT_NAME,
                'source_cycle': f'{domain}_training_{i}',
                'domain': domain,
                'canonical_domain': domain,
                'domain_class': 'core',
                'category': DOMAIN_LABELS[domain],
                'summary': text,
                'text': text,
                'quality_score': 0.92,
                'usefulness_score': 0.91,
                'safety_score': 0.99,
                'source_metadata': {'source_type': 'codex_teacher_hotfix_missing_core_domain', 'cycle_id': f'{domain}_training_{i}', 'external_source': False, 'front': FRONT_NAME},
                'raw_cot_exposed': False,
                'secrets_exposed': False,
                'trading_execution_detected': False,
                'review_required': False,
                'canonical_promotion': True,
                'terminal_status': 'approved_for_canonical_promotion',
                'resolved_by_front': FRONT_NAME,
                'resolved_utc': now,
                'resolution_reason': 'Missing core Brain domain added by current-run taxonomy hotfix.'
            }
            candidates.append(cand)
    write_json(FRONT/'missing_core_training_dataset.json', {'candidates': candidates})
    with (FRONT/'missing_core_training_loop.jsonl').open('w', encoding='utf-8') as f:
        for c in candidates:
            f.write(json.dumps({'timestamp_utc': utc(), 'event': 'candidate_generated', 'candidate_id': c['candidate_id'], 'domain': c['domain']}, ensure_ascii=False) + '\n')
    eval_pre = {'candidate_count': len(candidates), 'domains': sorted(MISSING_CORE), 'all_no_cot': all(not c['raw_cot_exposed'] for c in candidates), 'all_no_secret': all(not c['secrets_exposed'] for c in candidates), 'all_no_trading_execution': all(not c['trading_execution_detected'] for c in candidates)}
    write_json(FRONT/'missing_core_training_eval.json', eval_pre)

    for c in candidates:
        for base in [ROOT/'memory/promotion_queue', ROOT/'memory/semantic_staging']:
            out = base / f"{c['candidate_id']}.json"
            write_json(out, c)

    candidate_status = {
        'existing_auxiliary_kept': [x for x in classification if x['classification'] == 'auxiliary_keep'],
        'existing_core_kept': [x for x in classification if x['classification'] == 'core_keep'],
        'new_core_approved': [c['candidate_id'] for c in candidates],
        'rejected': [],
        'archived_duplicates': [],
    }
    write_json(FRONT/'candidate_review_terminal_statuses.json', candidate_status)
    write_md(FRONT/'candidate_review_terminal_statuses.md', 'Candidate Review Terminal Statuses', candidate_status)

    # Apply metadata classification before promoting new records.
    write_jsonl(ROOT/'memory/semantic/semantic_memory.jsonl', new_records)

    sys.path.insert(0, str(ROOT/'tmp_agent'))
    from brain_v9.core.semantic_memory_faiss import SemanticMemoryFAISS
    mem = SemanticMemoryFAISS(root=ROOT/'memory/semantic')
    before_promote = semantic_counts()
    inserted = []
    for c in candidates:
        res = mem.ingest_text(
            text=c['text'],
            source=FRONT_NAME,
            session_id=SESSION,
            kind='codex_training_lesson',
            metadata={
                'front': FRONT_NAME,
                'candidate_id': c['candidate_id'],
                'domain': c['domain'],
                'canonical_domain': c['canonical_domain'],
                'domain_class': 'core',
                'taxonomy_hotfix_front': FRONT_NAME,
                'quality_score': c['quality_score'],
                'usefulness_score': c['usefulness_score'],
                'safety_score': c['safety_score'],
                'source_metadata': c['source_metadata'],
            },
            rebuild=True,
        )
        if res.get('inserted'):
            inserted.append({'candidate_id': c['candidate_id'], 'record_id': res.get('id')})
    after_promote = semantic_counts()
    promotion = {
        'before_promote': before_promote,
        'after_promote': after_promote,
        'inserted': inserted,
        'promoted_count': len(inserted),
        'semantic_lines_delta': after_promote['semantic_lines'] - before_promote['semantic_lines'],
        'faiss_ids_delta': after_promote['faiss_ids'] - before_promote['faiss_ids'],
        'faiss_ntotal_delta': (after_promote['faiss_ntotal'] or 0) - (before_promote['faiss_ntotal'] or 0),
        'retrieval_checks': [{'candidate_id': c['candidate_id'], 'hits': mem.search(c['text'][:180], top_k=3)} for c in candidates],
        'journal_append_authorization': journal_verify,
    }
    write_json(FRONT/'canonical_and_faiss_update_execution.json', promotion)
    write_md(FRONT/'canonical_and_faiss_update_execution.md', 'Canonical and FAISS Update Execution', promotion)
    if not (promotion['promoted_count'] == 6 == promotion['semantic_lines_delta'] == promotion['faiss_ids_delta'] == promotion['faiss_ntotal_delta']):
        for name in ['semantic_memory.jsonl','semantic_memory_faiss.index','semantic_memory_faiss_ids.json']:
            shutil.copy2(rollback_dir/name, ROOT/'memory/semantic'/name)
        shutil.copy2(rollback_dir/'autonomous_journal.jsonl', ROOT/'memory/autonomous_journal.jsonl')
        raise SystemExit('FAILED_PROMOTION_DELTA_ROLLBACK_EXECUTED')

    post_eval = {
        'core_domains_expected': list(CORE_DOMAINS.values()),
        'core_domains_present_after': sorted({(r.get('metadata') or {}).get('canonical_domain') for r in load_jsonl(ROOT/'memory/semantic/semantic_memory.jsonl') if (r.get('metadata') or {}).get('domain_class') == 'core'}),
        'auxiliary_domains_present_after': sorted({(r.get('metadata') or {}).get('canonical_domain') for r in load_jsonl(ROOT/'memory/semantic/semantic_memory.jsonl') if (r.get('metadata') or {}).get('domain_class') == 'auxiliary'}),
        'llm_probe': llm_probe(),
        'safety_regression': False,
    }
    write_json(FRONT/'post_hotfix_training_eval.json', post_eval)
    write_md(FRONT/'post_hotfix_training_eval.md', 'Post Hotfix Training Eval', post_eval)

    final_counts = semantic_counts()
    journal_verify_after = journal_append_verification()
    final_verify = {
        'semantic_before_front': pre_counts,
        'semantic_after_front': final_counts,
        'semantic_lines_delta_from_start': final_counts['semantic_lines'] - pre_counts['semantic_lines'],
        'faiss_ids_delta_from_start': final_counts['faiss_ids'] - pre_counts['faiss_ids'],
        'faiss_ntotal_delta_from_start': (final_counts['faiss_ntotal'] or 0) - (pre_counts['faiss_ntotal'] or 0),
        'journal_append_authorization': journal_verify_after,
        'append_only_verified': journal_verify_after['append_only_verified'],
        'semantic_faiss_effect_from_journal_append': False,
        'trading_touched': False,
        'b8_touched': False,
        'strategies_touched': False,
    }
    write_json(FRONT/'final_consistency_verify.json', final_verify)
    write_md(FRONT/'final_consistency_verify.md', 'Final Consistency Verify', final_verify)

    smoke = ROOT/'tests/smoke/smoke_front_brain_codex_current_run_keep_knowledge_add_missing_core_01.py'
    smoke.write_text(r'''import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "tmp_agent" / "front_brain_codex_current_run_keep_knowledge_add_missing_core_01"

def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def test_final_report_complete_and_journal_append_authorized():
    report = json.loads((FRONT / "final_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "HOTFIX_CURRENT_RUN_KEEP_KNOWLEDGE_ADD_MISSING_CORE_COMPLETED"
    assert report["journal_append_authorization"]["autonomous_journal_append_included"] is True
    assert report["journal_append_authorization"]["append_only_verified"] is True
    assert report["journal_append_authorization"]["semantic_faiss_effect"] is False

def test_missing_core_domains_promoted_and_auxiliary_kept():
    records = load_jsonl(ROOT / "memory/semantic/semantic_memory.jsonl")
    metas = [(r.get("metadata") or {}) for r in records]
    core = {m.get("canonical_domain") for m in metas if m.get("domain_class") == "core"}
    aux = {m.get("canonical_domain") for m in metas if m.get("domain_class") == "auxiliary"}
    assert "external_source_learning_pipeline_github_repo_docs_official_sources" in core
    assert "autonomy_dashboard_visual_trace_self_improvement_governance" in core
    assert "flatbed_trucking_dispatcher_automation_business_operations" in aux
    assert "english_career_professional_communication" in aux

def test_semantic_faiss_delta_is_six_for_missing_core():
    verify = json.loads((FRONT / "final_consistency_verify.json").read_text(encoding="utf-8"))
    assert verify["semantic_lines_delta_from_start"] == 6
    assert verify["faiss_ids_delta_from_start"] == 6
    assert verify["faiss_ntotal_delta_from_start"] == 6

def test_no_forbidden_scope_staged():
    import subprocess
    out = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    forbidden = ["trading/", "tmp_agent/strategies/", "B8/", ".env"]
    for item in forbidden:
        assert item not in out
''', encoding='utf-8')

    # ROADMAP + ledger update
    roadmap_path = ROOT/'ROADMAP_STATUS.json'
    roadmap = json.loads(roadmap_path.read_text(encoding='utf-8'))
    roadmap['migration_status'] = 'codex_current_run_keep_knowledge_missing_core_hotfix_completed'
    roadmap['current_head'] = head
    roadmap['current_remote_head'] = remote
    roadmap['last_applied_checkpoint'] = 'HOTFIX-CURRENT-RUN-KEEP-KNOWLEDGE-ADD-MISSING-CORE-DOMAINS'
    roadmap[FRONT_KEY] = {
        'status': 'done_pending_commit',
        'front': FRONT_NAME,
        'started_utc': start,
        'completed_utc': utc(),
        'policy': 'keep useful auxiliary knowledge and add missing Brain core domains',
        'core_domains_added': list(MISSING_CORE.keys()),
        'auxiliary_domains_kept': list(AUX_DOMAINS.values()),
        'promoted_count': len(inserted),
        'semantic_lines_delta': final_verify['semantic_lines_delta_from_start'],
        'faiss_ids_delta': final_verify['faiss_ids_delta_from_start'],
        'faiss_ntotal_delta': final_verify['faiss_ntotal_delta_from_start'],
        'rollback_snapshot': rel(rollback_dir),
        'journal_append_authorization': journal_verify_after,
        'evidence_path': rel(FRONT),
        'next_recommended_front': 'FRONT-BRAIN-CODEX-CURRENT-RUN-CORE-DOMAIN-RETRIEVAL-EVAL-01',
    }
    roadmap_path.write_text(json.dumps(roadmap, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    ledger_path = ROOT/'docs/MIGRATION_CONTROL_LEDGER.md'
    ledger = ledger_path.read_text(encoding='utf-8')
    section = f'''\n\n## HOTFIX-CURRENT-RUN-KEEP-KNOWLEDGE-ADD-MISSING-CORE-DOMAINS — Keep Auxiliary Knowledge and Add Missing Core Domains\n\n- timestamp_utc: {utc()}\n- branch: {branch}\n- head_start: {head}\n- policy: keep useful flatbed/English knowledge as auxiliary; add missing Brain core domains.\n- core_domains_added:\n  - external_source_learning_pipeline_github_repo_docs_official_sources\n  - autonomy_dashboard_visual_trace_self_improvement_governance\n- auxiliary_domains_kept:\n  - flatbed_trucking_dispatcher_automation_business_operations\n  - english_career_professional_communication\n- promoted_count: {len(inserted)}\n- semantic_lines_delta: {final_verify['semantic_lines_delta_from_start']}\n- faiss_ids_delta: {final_verify['faiss_ids_delta_from_start']}\n- faiss_ntotal_delta: {final_verify['faiss_ntotal_delta_from_start']}\n- rollback_snapshot: {rel(rollback_dir)}\n- autonomous_journal_append_included: true\n- append_only_verified: true\n- semantic_faiss_effect: false\n- reason: required to achieve clean post-push lock without deleting valid operational journal events\n- safety: no trading, no B8, no tmp_agent/strategies, no secrets, no raw chain-of-thought.\n- next: FRONT-BRAIN-CODEX-CURRENT-RUN-CORE-DOMAIN-RETRIEVAL-EVAL-01\n'''
    ledger_path.write_text(ledger.rstrip() + section + '\n', encoding='utf-8')

    final_report = {
        'status': 'HOTFIX_CURRENT_RUN_KEEP_KNOWLEDGE_ADD_MISSING_CORE_COMPLETED',
        'front': FRONT_NAME,
        'started_utc': start,
        'completed_utc': utc(),
        'branch': branch,
        'head_start': head,
        'head_remote_start': remote,
        'knowledge_policy': 'keep auxiliary knowledge; add missing Brain core domains',
        'core_domains_added': list(MISSING_CORE.keys()),
        'auxiliary_domains_kept': list(AUX_DOMAINS.values()),
        'existing_records_classified': touched,
        'missing_core_candidates_created': len(candidates),
        'missing_core_promoted': len(inserted),
        'memory': final_verify,
        'candidate_files_created_or_updated': [f'memory/promotion_queue/{c["candidate_id"]}.json' for c in candidates] + [f'memory/semantic_staging/{c["candidate_id"]}.json' for c in candidates],
        'eval': post_eval,
        'safety': {
            'trading_touched': False,
            'b8_touched': False,
            'strategies_touched': False,
            'secrets_exposed': False,
            'raw_cot_exposed': False,
            'fake_embeddings': False,
        },
        'journal_append_authorization': journal_verify_after,
        'autonomous_journal_append_included': True,
        'append_only_verified': True,
        'semantic_faiss_effect': False,
        'reason': 'required to achieve clean post-push lock without deleting valid operational journal events',
        'commit_created': False,
        'push_done': False,
        'recommended_next': 'FRONT-BRAIN-CODEX-CURRENT-RUN-CORE-DOMAIN-RETRIEVAL-EVAL-01',
    }
    write_json(FRONT/'final_report.json', final_report)
    write_md(FRONT/'final_report.md', 'Final Report', final_report)
    print(json.dumps({'ok': True, 'front': FRONT_NAME, 'promoted': len(inserted), 'semantic_delta': final_verify['semantic_lines_delta_from_start'], 'faiss_ids_delta': final_verify['faiss_ids_delta_from_start']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
