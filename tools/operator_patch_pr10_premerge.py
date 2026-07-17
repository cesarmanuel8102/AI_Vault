from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
worker_path = root / 'scripts/agent_loop/local_worker/agent_worker.py'
s = worker_path.read_text(encoding='utf-8')

def one(old, new, label):
    global s
    if s.count(old) != 1:
        raise RuntimeError(f'{label}: expected one match, got {s.count(old)}')
    s = s.replace(old, new, 1)

one(
'''    source = Path(source_worker).resolve()
    if sha256_file(source).upper() != str(approved_worker_sha256).upper():
        raise ValueError("approved worker SHA mismatch")
    current_ref = gh_json(["api", f"repos/{cfg['repo']}/git/ref/heads/{cfg.get('base_branch','codex/own-capital-sustainable-return')}"])
''',
'''    source = Path(source_worker).resolve()
    if sha256_file(source).upper() != str(approved_worker_sha256).upper():
        raise ValueError("approved worker SHA mismatch")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", str(approved_control_plane_commit or "")):
        raise ValueError("approved control-plane commit must be a full SHA")
    try:
        control_repo = source.parents[3]
    except IndexError as exc:
        raise ValueError("source worker is not inside an approved checkout") from exc
    expected_source = (control_repo / "scripts/agent_loop/local_worker/agent_worker.py").resolve()
    if source != expected_source:
        raise ValueError("source worker path is outside the approved checkout")
    if Path(run(["git", "rev-parse", "--show-toplevel"], cwd=control_repo).strip()).resolve() != control_repo.resolve():
        raise ValueError("control-plane checkout root mismatch")
    control_head = run(["git", "rev-parse", "HEAD"], cwd=control_repo).strip()
    if control_head != approved_control_plane_commit:
        raise ValueError(f"control-plane checkout HEAD mismatch: {control_head}")
    if run(["git", "status", "--porcelain"], cwd=control_repo).strip():
        raise ValueError("control-plane checkout is dirty")
    current_ref = gh_json(["api", f"repos/{cfg['repo']}/git/ref/heads/{cfg.get('base_branch','codex/own-capital-sustainable-return')}"])
''',
'bind approved checkout')

one(
'''    cmp_pr9 = gh_json(["api", f"repos/{cfg['repo']}/compare/{APPROVED_PR9_HEAD_V156}...{approved_current_base_sha}"])
    if str(cmp_pr9.get("status")) not in {"ahead", "identical"}:
        raise ValueError("current base does not contain approved PR #9 head")
    cmp_hist = gh_json(["api", f"repos/{cfg['repo']}/compare/{historical_base_sha}...{approved_current_base_sha}"])
''',
'''    cmp_pr9 = gh_json(["api", f"repos/{cfg['repo']}/compare/{APPROVED_PR9_HEAD_V156}...{approved_current_base_sha}"])
    if str(cmp_pr9.get("status")) not in {"ahead", "identical"}:
        raise ValueError("current base does not contain approved PR #9 head")
    cmp_candidate = gh_json(["api", f"repos/{cfg['repo']}/compare/{approved_current_base_sha}...{approved_control_plane_commit}"])
    if str(cmp_candidate.get("status")) not in {"ahead", "identical"}:
        raise ValueError("approved control-plane commit is not descended from the live base")
    cmp_hist = gh_json(["api", f"repos/{cfg['repo']}/compare/{historical_base_sha}...{approved_current_base_sha}"])
''',
'validate candidate ancestry')

one(
'''    pushed = False
    new_head = None
    try:
''',
'''    pushed = False
    new_head = None
    owner_action_payload = None
    try:
''',
'initialize owner escalation')

one(
'''            except Exception as rb_exc: rollback["owner_action_required"] = True; rollback["remote_error"] = bounded_tail(str(rb_exc))
''',
'''            except Exception as rb_exc:
                actual_remote = "unknown"
                try:
                    remote_line = run(["git", "ls-remote", "origin", f"refs/heads/{expected_work_branch}"], cwd=repo_dir).strip()
                    if remote_line:
                        actual_remote = remote_line.split()[0]
                except Exception:
                    pass
                rollback["owner_action_required"] = True
                rollback["remote_error"] = bounded_tail(str(rb_exc))
                owner_action_payload = {
                    "status": "OWNER_ACTION_REQUIRED",
                    "reason": "force-with-lease refused rollback after unexpected remote movement",
                    "branch": expected_work_branch,
                    "expected_lease_sha": new_head,
                    "actual_remote_sha": actual_remote,
                    "rollback_target_sha": expected_old_pr_head,
                    "primary_failure": bounded_tail(str(exc)),
                }
''',
'force lease escalation')

one(
'''        event(cfg, "trusted_v156_post_merge_recovery_rollback", error=bounded_tail(str(exc)), rollback=rollback,
              historical_base=historical_base_sha, approved_current_base=approved_current_base_sha,
              old_pr_head=expected_old_pr_head, attempted_new_pr_head=new_head)
        raise
''',
'''        try:
            event(cfg, "trusted_v156_post_merge_recovery_rollback", error=bounded_tail(str(exc)), rollback=rollback,
                  historical_base=historical_base_sha, approved_current_base=approved_current_base_sha,
                  approved_control_plane_commit=approved_control_plane_commit,
                  old_pr_head=expected_old_pr_head, attempted_new_pr_head=new_head,
                  owner_action=owner_action_payload)
        except Exception:
            pass
        if owner_action_payload:
            raise RuntimeError("OWNER_ACTION_REQUIRED:" + json.dumps(owner_action_payload, sort_keys=True)) from exc
        raise
''',
'emit distinct owner escalation')

one(
'''        except RuntimeError as exc:
            evidence = worker_process_evidence(cfg["install_root"])
            raise SystemExit("worker.lock busy; trusted v1.5.6 post-merge recovery aborted before mutation; process_evidence=" + json.dumps(evidence, sort_keys=True)) from exc
''',
'''        except RuntimeError as exc:
            if str(exc).startswith("OWNER_ACTION_REQUIRED:"):
                raise SystemExit(str(exc)) from exc
            if "another worker instance" in str(exc) or "worker.lock busy" in str(exc):
                evidence = worker_process_evidence(cfg["install_root"])
                raise SystemExit("worker.lock busy; trusted v1.5.6 post-merge recovery aborted before mutation; process_evidence=" + json.dumps(evidence, sort_keys=True)) from exc
            raise
''',
'narrow lock error handling')

one(
'''        event(cfg, "trusted_v156_deploy_advance_recovery_existing_pr", historical_base=historical_base_sha,
              approved_current_base=approved_current_base_sha, old_pr_head=expected_old_pr_head, new_pr_head=new_head,
''',
'''        event(cfg, "trusted_v156_deploy_advance_recovery_existing_pr", historical_base=historical_base_sha,
              approved_current_base=approved_current_base_sha, approved_control_plane_commit=approved_control_plane_commit,
              old_pr_head=expected_old_pr_head, new_pr_head=new_head,
''',
'success evidence candidate')

compile(s, str(worker_path), 'exec')
worker_path.write_text(s, encoding='utf-8')
print('PATCHED_PR10_PREMERGE')
