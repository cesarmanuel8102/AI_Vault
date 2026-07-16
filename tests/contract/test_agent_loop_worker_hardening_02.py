#!/usr/bin/env python3
from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[2]
SRC=(ROOT/'scripts/agent_loop/local_worker/agent_worker.py').read_text(encoding='utf-8')
CONTRACT=json.loads((ROOT/'scripts/agent_loop/local_worker/worker_contract.json').read_text(encoding='utf-8'))
checks={
 'version': 'WORKER_VERSION = "1.5.0"' in SRC and CONTRACT.get('worker_version')=='1.5.0',
 'windows_cmd': 'command_for_subprocess' in SRC and '.cmd' in SRC and 'COMSPEC' in SRC,
 'dynamic_flags': 'opencode_run_supports("--auto"' in SRC,
 'generation_workspaces': 'workspace_created' in SRC and 'issue-{issue_no}-{stamp}' in SRC,
 'single_instance': 'class SingleInstanceLock' in SRC,
 'bounded_retries': 'max_local_retries' in SRC and 'terminalize_state_error' in SRC,
 'exclusive_labels': 'def set_phase' in SRC and 'PHASE_LABELS' in SRC,
 'preflight': 'def run_preflight' in SRC and 'worker-preflight.json' in SRC,
 'retention': 'def cleanup_stale_workspaces' in SRC and 'workspace_retention_days' in SRC,
 'final_report': 'same_head' in SRC and 'final_changed_files' in SRC,
 'no_auto_merge': 'merge_performed": False' in SRC,
 'no_canonical_sync': 'canonical_local_sync": False' in SRC,
}
failed=[k for k,v in checks.items() if not v]
print(json.dumps({'status':'PASS' if not failed else 'FAIL','checks':checks,'failed':failed},indent=2))
sys.exit(0 if not failed else 1)

