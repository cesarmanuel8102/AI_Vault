import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List


HARD_REJECT_REASONS = {
    "daily_loss_limit_reached",
    "trailing_drawdown_limit_reached",
    "outside_allowed_session",
    "qty_over_order_limit",
    "qty_over_total_limit",
    "automation_blocked",
}


def load_reports(artifacts_dir: Path) -> List[dict]:
    rows = []
    for p in sorted(artifacts_dir.glob("paper_day_report_*.json")):
        payload = json.loads(p.read_text(encoding="utf-8"))
        payload["_path"] = str(p)
        rows.append(payload)
    return rows


def evaluate(reports: List[dict], window_days: int) -> dict:
    if not reports:
        return {"window": 0, "pass": False, "reason": "no_reports"}

    use = reports[-window_days:]
    violations = 0
    totals = {"accepted": 0, "rejected": 0, "signals": 0}
    reason_counts = {}

    for r in use:
        s = r.get("summary", {})
        totals["accepted"] += int(s.get("accepted", 0))
        totals["rejected"] += int(s.get("rejected", 0))
        totals["signals"] += int(s.get("total", 0))
        reasons = s.get("reasons", {}) or {}
        for k, v in reasons.items():
            reason_counts[k] = reason_counts.get(k, 0) + int(v)
            if k in HARD_REJECT_REASONS:
                violations += int(v)

    return {
        "window": len(use),
        "hard_violations": violations,
        "totals": totals,
        "reason_counts": reason_counts,
        "pass": len(use) >= window_days and violations == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 0 paper review")
    parser.add_argument("--artifacts", default="artifacts", help="Artifacts directory")
    parser.add_argument("--window", type=int, default=5, help="Window of paper reports")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    art = (base / args.artifacts).resolve()
    reports = load_reports(art)
    out = evaluate(reports, args.window)
    out["generated_at_utc"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    out["reports_used"] = [r.get("_path") for r in reports[-args.window:]]

    out_file = art / f"paper_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"report={out_file}")


if __name__ == "__main__":
    main()
