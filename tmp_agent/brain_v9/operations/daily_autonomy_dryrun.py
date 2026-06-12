from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tmp_agent.brain_v9.autonomy.mega_cycle_runner import run_mega_cycles

DEFAULT_REPORT_DIR = Path("tmp_agent/brain_v9/operations/daily_autonomy_reports")


def run_daily_autonomy_dryrun(report_dir: Path = DEFAULT_REPORT_DIR, cycles: int = 3) -> dict[str, Any]:
    """Run a manual governed dry-run without semantic/FAISS/trading side effects."""
    report_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = report_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = run_mega_cycles(
        evidence_dir=evidence_dir,
        target_cycles=cycles,
        max_cycles_per_run=cycles,
        batch_size=cycles,
        score_before=0.888,
        calibration_mode="daily_dryrun_compact_micro_cycle",
    )
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "report_type": "brain_daily_autonomous_dryrun",
        "cycles_requested": cycles,
        "cycles_completed": summary.cycles_completed,
        "provider_success_rate": summary.provider_success_rate,
        "fallback_rate": summary.fallback_rate,
        "memory_semantic_write": False,
        "faiss_write": False,
        "trading": False,
        "b8_touched": False,
        "recommended_human_actions": [
            "Review provider fallback rate before increasing autonomy.",
            "Review generated lessons before any promotion to semantic memory.",
        ],
        "evidence_dir": str(evidence_dir),
    }
    (evidence_dir / "daily_dryrun_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run_daily_autonomy_dryrun(), separators=(",", ":")))
