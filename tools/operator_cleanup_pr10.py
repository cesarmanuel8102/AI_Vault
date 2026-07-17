from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
CONTRACT = ROOT / "scripts/agent_loop/local_worker/worker_contract.json"
HARDENING = ROOT / "tests/contract/test_agent_loop_worker_hardening_02.py"


def require_once(text: str, needle: str, label: str) -> None:
    count = text.count(needle)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")


worker = WORKER.read_text(encoding="utf-8")

# v1.5.6 deployment is implemented exclusively by the dynamic helper modules.
# Remove the obsolete embedded implementation to avoid two recovery authorities.
block_start = "\nHISTORICAL_PILOT_BASE_V156 = "
block_end = "\nclass SingleInstanceLock:"
require_once(worker, block_start, "embedded v1.5.6 block start")
require_once(worker, block_end, "SingleInstanceLock boundary")
start = worker.index(block_start)
end = worker.index(block_end, start)
worker = worker[:start] + "\n\n" + worker[end:]

parser_fragment = '; ap.add_argument("--trusted-v156-deploy-advance-recover-existing-pr", type=int)'
require_once(worker, parser_fragment, "obsolete v1.5.6 CLI argument")
worker = worker.replace(parser_fragment, "", 1)

route_start = "    if args.trusted_v156_deploy_advance_recover_existing_pr is not None:\n"
route_end = "    if args.trusted_v155_deploy_recover_existing_pr is not None:\n"
require_once(worker, route_start, "obsolete v1.5.6 CLI route")
require_once(worker, route_end, "v1.5.5 route boundary")
route_begin = worker.index(route_start)
route_finish = worker.index(route_end, route_begin)
worker = worker[:route_begin] + worker[route_finish:]

compile(worker, str(WORKER), "exec")
WORKER.write_text(worker, encoding="utf-8")

contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
hardening = contract.setdefault("hardening", {})
hardening.update(
    {
        "v156_dynamic_post_merge_recovery": True,
        "v156_runtime_post_merge_sha_authorization": True,
        "v156_approved_checkout_source_binding": True,
        "v156_force_with_lease_conflict_owner_escalation": True,
        "v156_transactional_event_log_rollback": True,
        "v156_single_recovery_authority": True,
    }
)
CONTRACT.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")

hardening_test = HARDENING.read_text(encoding="utf-8")
anchor = 'checks["contract_truthfulness"] = True\n'
require_once(hardening_test, anchor, "hardening assertion anchor")
insert = '''for key in (
    "v156_dynamic_post_merge_recovery",
    "v156_runtime_post_merge_sha_authorization",
    "v156_approved_checkout_source_binding",
    "v156_force_with_lease_conflict_owner_escalation",
    "v156_transactional_event_log_rollback",
    "v156_single_recovery_authority",
):
    assert contract["hardening"][key] is True, key
worker_source = MODULE_PATH.read_text(encoding="utf-8")
assert "--trusted-v156-deploy-advance-recover-existing-pr" not in worker_source
assert "HISTORICAL_PILOT_BASE_V156" not in worker_source
for rel in (
    "scripts/agent_loop/local_worker/v156_post_merge_recovery.py",
    "scripts/agent_loop/local_worker/v156_recovery_common.py",
    "scripts/agent_loop/local_worker/v156_recovery_transaction.py",
):
    assert (ROOT / rel).is_file(), rel
checks["v156_single_recovery_authority"] = True
'''
hardening_test = hardening_test.replace(anchor, insert + anchor, 1)
compile(hardening_test, str(HARDENING), "exec")
HARDENING.write_text(hardening_test, encoding="utf-8")

print(
    json.dumps(
        {
            "status": "PATCHED",
            "removed_embedded_v156": True,
            "removed_obsolete_cli_route": True,
            "dynamic_recovery_authority": True,
        },
        indent=2,
    )
)
