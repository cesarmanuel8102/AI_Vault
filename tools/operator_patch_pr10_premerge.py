from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'tests/contract/test_agent_loop_worker_v156_post_merge_recovery.py'
s = path.read_text(encoding='utf-8')

def one(old, new, label):
    global s
    if s.count(old) != 1:
        raise RuntimeError(f'{label}: expected one match, got {s.count(old)}')
    s = s.replace(old, new, 1)

one(
'''    def upd_issue(repo,num,body):
        if fail_at=="issue_body": raise RuntimeError("issue body fail")
        store["issue_body"]=body
''',
'''    def upd_issue(repo,num,body):
        if fail_at=="issue_body":
            if force_lease_conflict and not store.get("third_party_head"):
                third=Path(tempfile.mkdtemp(prefix="v156-third-party-"))
                git(["clone",str(store["remote_path"]),str(third)],third.parent)
                git(["checkout","-B",BRANCH,f"origin/{BRANCH}"],third)
                git(["config","user.name","third"],third); git(["config","user.email","third@example.invalid"],third)
                (third/"third-party.txt").write_text("third-party\\n",encoding="utf-8")
                git(["add","third-party.txt"],third); git(["commit","-m","third-party movement"],third)
                store["third_party_head"]=git(["rev-parse","HEAD"],third)
                git(["push","origin",f"HEAD:refs/heads/{BRANCH}"],third)
            raise RuntimeError("issue body fail")
        store["issue_body"]=body
''',
'add real remote conflict')

one(
'''        root=Path(td); repo,hist,current,pr9,old=make_repo(root,dirty=dirty,ahead=ahead,wrong_head=wrong_head,nongit=nongit)
        worker.HISTORICAL_PILOT_BASE_V156=hist; worker.APPROVED_CURRENT_BASE_V156=current; worker.APPROVED_PR9_HEAD_V156=pr9; worker.OLD_PILOT_HEAD_V156=old
''',
'''        root=Path(td); repo,hist,current,pr9,old=make_repo(root,dirty=dirty,ahead=ahead,wrong_head=wrong_head,nongit=nongit)
        worker.HISTORICAL_PILOT_BASE_V156=hist; worker.APPROVED_CURRENT_BASE_V156=current; worker.APPROVED_PR9_HEAD_V156=pr9; worker.OLD_PILOT_HEAD_V156=old
        remote_path=root/"remote.git"
        control=root/"control"
        git(["clone",str(remote_path),str(control)],root)
        git(["checkout","-B","control-candidate",current],control)
        git(["config","user.name","control"],control); git(["config","user.email","control@example.invalid"],control)
        source=control/"scripts/agent_loop/local_worker/agent_worker.py"; source.parent.mkdir(parents=True,exist_ok=True); source.write_bytes(MODULE.read_bytes())
        git(["add","scripts/agent_loop/local_worker/agent_worker.py"],control); git(["commit","-m","approved control candidate"],control)
        control_commit=git(["rev-parse","HEAD"],control)
''',
'create approved control checkout')

one(
'''        source=root/"source_worker.py"; source.write_bytes(MODULE.read_bytes()); sha=worker.sha256_file(source)
        store={"issue_body":issue_body(hist),"pr_body":f"EXPECTED_BASE_SHA: {hist}","issue_labels":{"loop:repairing"},"pr_labels":{"loop:token-exhausted"},"pr_head":old,"events":[]}
''',
'''        sha=worker.sha256_file(source)
        store={"issue_body":issue_body(hist),"pr_body":f"EXPECTED_BASE_SHA: {hist}","issue_labels":{"loop:repairing"},"pr_labels":{"loop:token-exhausted"},"pr_head":old,"events":[],"remote_path":remote_path,"control_commit":control_commit}
''',
'use checkout-bound source')

one(
'''                worker.trusted_v156_deploy_advance_recover_existing_pr({"install_root":str(root),"repo":REPO,"owner":OWNER,"base_branch":"codex/own-capital-sustainable-return"},5,str(source),sha,hist,current,current,old,FRONT,6,BRANCH)
''',
'''                worker.trusted_v156_deploy_advance_recover_existing_pr({"install_root":str(root),"repo":REPO,"owner":OWNER,"base_branch":"codex/own-capital-sustainable-return"},5,str(source),sha,hist,current,control_commit,old,FRONT,6,BRANCH)
''',
'pass approved candidate commit')

one(
'''            remote=git(["rev-parse",f"origin/{BRANCH}"],repo) if repo.exists() and (repo/".git").exists() else ""
''',
'''            remote=(git(["ls-remote","origin",f"refs/heads/{BRANCH}"],repo).split()[0] if repo.exists() and (repo/".git").exists() else "")
''',
'read authoritative remote')

insert = '''\n\ndef test_real_force_with_lease_conflict():
    outcome,bs,as_,bw,aw,st,store,remote,old,current=run_case(fail_at="issue_body",conflict=True)
    assert outcome.startswith("OWNER_ACTION_REQUIRED:"), outcome
    assert store.get("third_party_head") and remote==store["third_party_head"] and remote!=old
    payload=json.loads(outcome.split(":",1)[1])
    assert payload["expected_lease_sha"]!=payload["actual_remote_sha"]
    assert payload["actual_remote_sha"]==store["third_party_head"]
    assert payload["rollback_target_sha"]==old
    assert bs==as_ and bw==aw
'''
marker = '\nif __name__=="__main__":\n'
if s.count(marker) != 1:
    raise RuntimeError('main marker mismatch')
s = s.replace(marker, insert + marker, 1)

one(
'''    test_failures_before_mutation(); test_successful_combined_transition(); test_rollback_matrix()
    print(json.dumps({"status":"PASS","worker_version":worker.WORKER_VERSION,"combined_transition":"PASS","pre_mutation_failures":"PASS","rollback_matrix":"PASS","remote_push_rollback":"PASS","force_with_lease_conflict":"COVERED_BY_EXACT_LEASE_PATH"},indent=2))
''',
'''    test_failures_before_mutation(); test_successful_combined_transition(); test_rollback_matrix(); test_real_force_with_lease_conflict()
    print(json.dumps({"status":"PASS","worker_version":worker.WORKER_VERSION,"combined_transition":"PASS","pre_mutation_failures":"PASS","rollback_matrix":"PASS","remote_push_rollback":"PASS","approved_control_checkout_binding":"PASS","force_with_lease_conflict":"PASS_REAL_REMOTE_MOVEMENT","owner_action_required":"PASS"},indent=2))
''',
'run real conflict test')

compile(s, str(path), 'exec')
path.write_text(s, encoding='utf-8')
print('PATCHED_PR10_TESTS')
