#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import v156_recovery_common as common
import v156_recovery_transaction as transaction
from v156_recovery_common import *
from v156_recovery_transaction import execute_recovery, run_locked


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--source-worker", required=True)
    parser.add_argument("--approved-worker-sha256", required=True)
    parser.add_argument("--historical-base-sha", required=True)
    parser.add_argument("--pre-pr10-base-sha", required=True)
    parser.add_argument("--approved-feature-head", required=True)
    parser.add_argument("--approved-merged-base-sha", required=True)
    parser.add_argument("--approved-control-plane-commit", required=True)
    parser.add_argument("--expected-old-pr-head", required=True)
    parser.add_argument("--expected-front", required=True)
    parser.add_argument("--expected-pr-number", required=True, type=int)
    parser.add_argument("--expected-work-branch", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = worker.load_json(Path(args.config))
    auth = Authorization(
        historical_base=args.historical_base_sha,
        pre_pr10_base=args.pre_pr10_base_sha,
        approved_feature_head=args.approved_feature_head,
        approved_merged_base=args.approved_merged_base_sha,
        approved_control_plane_commit=args.approved_control_plane_commit,
        expected_old_pr_head=args.expected_old_pr_head,
        expected_front=args.expected_front,
        expected_pr_number=args.expected_pr_number,
        expected_work_branch=args.expected_work_branch,
        approved_worker_sha256=args.approved_worker_sha256,
    )
    try:
        result = run_locked(cfg, auth, source_worker=Path(args.source_worker))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except OwnerActionRequired as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "error": bounded(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
