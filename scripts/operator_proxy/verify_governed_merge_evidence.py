import argparse
import json
from pathlib import Path


REQUIRED_ROLLUP_CHECKS = {
    "Phase 1 baseline (Windows)",
    "Security Smoke Tests",
    "Dashboard / Trace Tests",
    "Memory / Retrieval Regression",
    "Roadmap / Policy Regression",
    "Agent V2 Boundary Contracts",
    "Financial Autonomy Dry-Run Contract",
    "Hygiene Guard",
}
HYGIENE_CHECK = "Brain Agent V2 Hygiene Baseline"
ALLOWED_SKIPS = {"deterministic", "codex", "publish"}


def load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def verify(pr: dict, hygiene_runs: list[dict], expected_base: str, expected_head: str) -> None:
    if (
        pr.get("baseRefOid") != expected_base
        or pr.get("headRefOid") != expected_head
        or pr.get("state") != "OPEN"
        or pr.get("isDraft") is not True
        or pr.get("mergeable") != "MERGEABLE"
    ):
        raise ValueError("PR identity mismatch")

    checks = pr.get("statusCheckRollup") or []
    by_name = {check.get("name"): check for check in checks}
    if any(by_name.get(name, {}).get("conclusion") != "SUCCESS" for name in REQUIRED_ROLLUP_CHECKS):
        raise ValueError("required PR checks not successful")

    hygiene = by_name.get(HYGIENE_CHECK)
    if not hygiene or hygiene.get("conclusion") != "SUCCESS":
        exact_runs = [run for run in hygiene_runs if run.get("headSha") == expected_head]
        if not exact_runs:
            raise ValueError("exact-head hygiene evidence missing")
        latest = exact_runs[0]
        if (
            latest.get("workflowName") != "Brain Agent V2 Hygiene"
            or latest.get("event") != "workflow_dispatch"
            or latest.get("status") != "completed"
            or latest.get("conclusion") != "success"
        ):
            raise ValueError("latest exact-head hygiene run not successful")

    allowed_skips = set() if str(pr.get("headRefName", "")).startswith("agent/pilot-") else ALLOWED_SKIPS
    for check in checks:
        if check.get("status") != "COMPLETED":
            raise ValueError("check not terminal")
        if check.get("conclusion") == "SUCCESS":
            continue
        if check.get("name") in allowed_skips and check.get("conclusion") == "SKIPPED":
            continue
        raise ValueError(f"non-success check: {check.get('name')}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr-json", required=True)
    parser.add_argument("--hygiene-runs-json", required=True)
    parser.add_argument("--expected-base", required=True)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    try:
        verify(load_json(args.pr_json), load_json(args.hygiene_runs_json), args.expected_base, args.expected_head)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
