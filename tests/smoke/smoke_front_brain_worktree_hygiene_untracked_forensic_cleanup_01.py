"""
Smoke test for FRONT-BRAIN-WORKTREE-HYGIENE-UNTRACKED-FORENSIC-CLEANUP-01
"""
import json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
EVIDENCE = os.path.join(ROOT, 'tmp_agent/front_brain_worktree_hygiene_untracked_forensic_cleanup_01')

def _read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_evidence_dir_exists():
    assert os.path.isdir(EVIDENCE)

def test_state_lock_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'state_lock.json'))

def test_memory_safety_check_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'memory_safety_check.json'))

def test_untracked_inventory_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'untracked_inventory.json'))

def test_quarantine_exists():
    assert os.path.exists(os.path.join(ROOT, 'tmp_agent/quarantine/worktree_hygiene_untracked_forensic_cleanup_01/dry_run'))
    assert os.path.exists(os.path.join(ROOT, 'tmp_agent/quarantine/worktree_hygiene_untracked_forensic_cleanup_01/stream'))

def test_root_junk_quarantined():
    assert not os.path.exists(os.path.join(ROOT, 'dry_run'))
    assert not os.path.exists(os.path.join(ROOT, 'stream'))
    assert not os.path.exists(os.path.join(ROOT, 'evaluation'))
    assert not os.path.exists(os.path.join(ROOT, 'read_only'))

def test_semantic_faiss_not_dirty():
    import subprocess
    out = subprocess.run(['git', 'status', '--short', '--untracked-files=no'], cwd=ROOT, capture_output=True, text=True).stdout
    dirty = [l for l in out.strip().split('\n') if l.strip()]
    semantic_dirty = any('semantic_memory' in l for l in dirty)
    faiss_dirty = any('faiss' in l for l in dirty)
    assert not semantic_dirty, "semantic_memory files are dirty"
    assert not faiss_dirty, "FAISS files are dirty"

def test_current_front_post_push_committed():
    assert os.path.exists(os.path.join(ROOT, 'tmp_agent/front_brain_agent_v2_mandatory_multitool_planner_hotfix_01/post_push_verification.json'))

def test_gitignore_exclude_policy_exists():
    with open(os.path.join(ROOT, '.git/info/exclude'), 'r') as f:
        content = f.read()
    assert 'tmp_agent/agent_kernel_v2/runs/' in content
    assert 'tmp_agent/evolution_runs/' in content

def test_roadmap_updated():
    data = _read_json(os.path.join(ROOT, 'ROADMAP_STATUS.json'))
    assert any('worktree' in k for k in data.keys())

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
