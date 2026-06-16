from __future__ import annotations
import json
from pathlib import Path
from .schemas import AgentCheckpoint, to_dict, utc_now


class CheckpointStore:
    def __init__(self, run_dir: Path):
        self.path = run_dir / "checkpoint.json"

    def save(self, run_id: str, status: str, step_index: int = 0, data=None) -> None:
        cp = AgentCheckpoint(run_id=run_id, status=status, updated_utc=utc_now(), step_index=step_index, data=data or {})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(to_dict(cp), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def load(self):
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))
