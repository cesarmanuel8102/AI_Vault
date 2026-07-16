#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ALLOWED = {
    'docs/agent_loop/pilot/PILOT_MARKER.md',
    'docs/agent_loop/pilot/EXECUTOR_REPORT.json',
}
EXPECTED = '# Agent Loop Pilot\nSTATUS=PASS\nEXECUTOR=KIMI_OPENCODE_OLLAMA\nSUPERVISOR=CODEX_GITHUB_ACTION\n'

def run(args):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if p.returncode: raise RuntimeError(f"{args}: {p.stdout}")
    return p.stdout.strip()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-sha'); ap.add_argument('--head-sha'); ap.add_argument('--report-path'); ap.add_argument('--local',action='store_true')
    a=ap.parse_args(); root=Path(__file__).resolve().parents[2]
    marker=root/'docs/agent_loop/pilot/PILOT_MARKER.md'; executor=root/'docs/agent_loop/pilot/EXECUTOR_REPORT.json'
    errors=[]
    if not marker.exists(): errors.append('marker missing')
    elif marker.read_text(encoding='utf-8-sig').replace('\r\n','\n') != EXPECTED: errors.append('marker content mismatch')
    if not executor.exists():
        if not a.local: errors.append('executor report missing')
    else:
        try:
            d=json.loads(executor.read_text(encoding='utf-8-sig'))
            if d.get('executor')!='Kimi via OpenCode/Ollama': errors.append('executor identity mismatch')
            if d.get('local_test_passed') is not True: errors.append('local test not passed')
            if d.get('merge_performed') is not False: errors.append('merge_performed must be false')
            if d.get('canonical_local_sync') is not False: errors.append('canonical_local_sync must be false')
        except Exception as e: errors.append(f'executor report invalid: {e}')
    changed=[]
    if a.base_sha:
        changed=[x for x in run(['git','diff','--name-only',a.base_sha,a.head_sha or 'HEAD']).splitlines() if x]
        extra=sorted(set(changed)-ALLOWED)
        missing=sorted(ALLOWED-set(changed))
        if extra: errors.append(f'out-of-scope changes: {extra}')
        if missing: errors.append(f'expected changed files missing: {missing}')
    report={'schema_version':1,'status':'PASS' if not errors else 'FAIL','errors':errors,'changed_files':changed,
            'base_sha':a.base_sha,'head_sha':a.head_sha,'generated_utc':datetime.now(timezone.utc).isoformat()}
    if a.report_path:
        Path(a.report_path).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if not errors else 1
if __name__=='__main__': sys.exit(main())

