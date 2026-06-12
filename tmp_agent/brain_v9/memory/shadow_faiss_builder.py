from __future__ import annotations

import json
from pathlib import Path

STAGING_DIR = Path("memory/semantic_staging")


def build_shadow_index(staging_jsonl: Path = STAGING_DIR / "semantic_memory_candidate.jsonl", output_dir: Path = STAGING_DIR / "shadow_faiss") -> dict[str, object]:
    """Build a shadow text index manifest without overwriting canonical FAISS."""
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    if staging_jsonl.exists():
        records = [json.loads(line) for line in staging_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [record.get("candidate_id") for record in records]
    (output_dir / "shadow_ids.json").write_text(json.dumps(ids, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "shadow_manifest.json").write_text(json.dumps({"record_count": len(records), "canonical_overwritten": False}, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "record_count": len(records), "canonical_overwritten": False, "output_dir": str(output_dir)}
