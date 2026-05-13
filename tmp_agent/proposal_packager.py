# proposal_packager.py (v0.2)
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from diff_engine import diff_files
from policies import SandboxPolicy


SANDBOX_ROOT = Path(r"C:\AI_VAULT\tmp_agent").resolve()
WORK_DIR = (SANDBOX_ROOT / "workspace").resolve()
PROPOSALS_DIR = (SANDBOX_ROOT / "proposals").resolve()

REPO_ROOT = Path(r"C:\AI_VAULT\workspace\brainlab").resolve()


def utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_dirs():
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str, policy: SandboxPolicy) -> None:
    policy.assert_can_write(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj: Any, policy: SandboxPolicy) -> None:
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2), policy)


def package_workspace_to_repo_proposal(
    title: str,
    rationale: str,
    match_mode: str = "by_filename",
    include_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Empaqueta cambios detectados en tmp_agent/workspace vs C:\AI_VAULT\workspace\brainlab (read-only).

    v0.2 fix:
      - Si no hay diffs (count=0) => devuelve skipped y NO crea bundle/diff.
    """
    ensure_dirs()
    policy = SandboxPolicy.default()

    policy.assert_can_read(REPO_ROOT)
    policy.assert_can_read(WORK_DIR)

    include_patterns = include_patterns or ["*.py", "*.json"]

    # Collect workspace files
    ws_files: List[Path] = []
    for pat in include_patterns:
        ws_files.extend(list(WORK_DIR.rglob(pat)))
    ws_files = sorted({p.resolve() for p in ws_files})

    # Index repo by filename (MVP) - includes patterns (e.g. *.py, *.json)
    repo_index: Dict[str, Path] = {}
    for pat in include_patterns:
        for p in REPO_ROOT.rglob(pat):
            # prefer first occurrence; MVP
            k = p.name.lower()
            if k not in repo_index:
                repo_index[k] = p.resolve()

    items: List[Dict[str, Any]] = []
    diffs_to_write: List[Dict[str, str]] = []

    proposal_id = f"prop_{int(time.time())}"

    for ws in ws_files:
        policy.assert_can_read(ws)
        repo_match: Optional[Path] = None
        if match_mode == "by_filename":
            repo_match = repo_index.get(ws.name.lower(), None)

        if repo_match is not None:
            policy.assert_can_read(repo_match)
            d = diff_files(repo_match, ws)
            if not d.ok or not d.data.get("changed", False):
                continue

            diff_text = d.data.get("diff_text", "")
            diff_path = (PROPOSALS_DIR / f"{proposal_id}_{ws.stem}.diff").resolve()

            diffs_to_write.append({"path": str(diff_path), "text": diff_text})

            items.append({
                "kind": "modify",
                "workspace_path": str(ws),
                "repo_path": str(repo_match),
                "old_sha256": d.data.get("old_sha256"),
                "new_sha256": d.data.get("new_sha256"),
                "diff_path": str(diff_path),
            })
        else:
            # New file
            d = diff_files(Path("NUL"), ws)
            diff_text = d.data.get("diff_text", "")
            diff_path = (PROPOSALS_DIR / f"{proposal_id}_{ws.stem}_NEW.diff").resolve()

            diffs_to_write.append({"path": str(diff_path), "text": diff_text})

            items.append({
                "kind": "new_file",
                "workspace_path": str(ws),
                "suggested_repo_path": f"(NEEDS_DECISION) {ws.name}",
                "new_sha256": d.data.get("new_sha256"),
                "diff_path": str(diff_path),
            })

    if len(items) == 0:
        return {
            "ok": True,
            "skipped": True,
            "reason": "NO_DIFFS",
            "proposal_id": None,
            "bundle_path": None,
            "items": [],
            "count": 0,
        }

    # Write diffs (only if items exist)
    for d in diffs_to_write:
        write_text(Path(d["path"]), d["text"], policy)

    bundle = {
        "proposal_id": proposal_id,
        "created_at": utc_iso(),
        "title": title,
        "rationale": rationale,
        "mode": "sandbox_proposal_bundle",
        "touches_runtime": False,
        "requires_human_approval_to_apply": True,
        "items": items,
    }

    bundle_path = (PROPOSALS_DIR / f"{proposal_id}_bundle.json").resolve()
    write_json(bundle_path, bundle, policy)

    return {
        "ok": True,
        "proposal_id": proposal_id,
        "bundle_path": str(bundle_path),
        "items": items,
        "count": len(items),
    }


if __name__ == "__main__":
    out = package_workspace_to_repo_proposal(
        title="Sandbox proposal bundle (auto)",
        rationale="Empaquetar diffs desde tmp_agent/workspace contra workspace/brainlab (read-only)."
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


