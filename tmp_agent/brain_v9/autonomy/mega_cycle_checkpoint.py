from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class MegaCycleCheckpoint:
    front_name: str
    target_cycles: int
    completed_cycles: int = 0
    completed_batches: int = 0
    implemented: int = 0
    blocked: int = 0
    lessons_created: int = 0
    mistakes_created: int = 0
    promotion_candidates_created: int = 0
    last_cycle_id: str | None = None
    status: str = "running"
    updated_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["updated_utc"] = datetime.now(timezone.utc).isoformat()
        return data


def load_checkpoint(path: Path, front_name: str, target_cycles: int) -> MegaCycleCheckpoint:
    if not path.exists():
        return MegaCycleCheckpoint(front_name=front_name, target_cycles=target_cycles)
    data = json.loads(path.read_text(encoding="utf-8"))
    return MegaCycleCheckpoint(**data)


def save_checkpoint(path: Path, checkpoint: MegaCycleCheckpoint) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_resume_materials(evidence_dir: Path, checkpoint: MegaCycleCheckpoint, next_prompt_name: str) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "RESUME_STATE.json").write_text(
        json.dumps(checkpoint.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (evidence_dir / "RESUME_PROMPT.md").write_text(
        "# Resume Prompt\n\n"
        f"Continue `{checkpoint.front_name}` from cycle `{checkpoint.completed_cycles}` using `{next_prompt_name}`.\n"
        "Respect all hard gates: no memory/semantic writes, no FAISS writes, no trading, no B8, no secrets.\n",
        encoding="utf-8",
    )
    (evidence_dir / "HANDOFF_FOR_NEXT_CODEX.md").write_text(
        "# Handoff\n\n"
        f"- front: `{checkpoint.front_name}`\n"
        f"- completed_cycles: `{checkpoint.completed_cycles}`\n"
        f"- completed_batches: `{checkpoint.completed_batches}`\n"
        f"- status: `{checkpoint.status}`\n"
        "- continue with compact batches and commit safe artifacts only.\n",
        encoding="utf-8",
    )
