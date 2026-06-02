"""B7-09 patch (re)generator.

Generates a patch consisting of:
  - git diff for tmp_agent/brain_v9/core/session.py (modified-tracked)
  - synthesized 'new file mode 100644' blocks for the 4 untracked B7-09 files

Does NOT use `git add -N` and does NOT touch the index.
Output: tmp_agent/b7_strangler_evidence/b7_09_tool_analysis_prefs_extraction.patch
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "tmp_agent" / "b7_strangler_evidence"
OUT = EVIDENCE_DIR / "b7_09_tool_analysis_prefs_extraction.patch"

MODIFIED = ["tmp_agent/brain_v9/core/session.py"]
NEW_FILES = [
    "tmp_agent/brain_v9/core/session_tool_analysis_prefs.py",
    "tests/unit/test_b7_tool_analysis_prefs_import_compat.py",
    "tests/unit/test_b7_tool_analysis_prefs_behavior_smoke.py",
    "tests/unit/test_b7_tool_analysis_prefs_no_session_dependency.py",
]


def git_diff(path: str) -> bytes:
    r = subprocess.run(["git", "diff", "--", path], cwd=ROOT, capture_output=True, check=True)
    return r.stdout


def synthesize_new_file_block(rel_path: str) -> bytes:
    abs_p = ROOT / rel_path
    raw = abs_p.read_bytes()
    has_trailing_newline = raw.endswith(b"\n")
    # split on \n preserving content; remove final empty if has trailing newline
    parts_b = raw.split(b"\n")
    if has_trailing_newline:
        parts_b = parts_b[:-1]
    n = len(parts_b)
    body = b"\n".join(b"+" + ln for ln in parts_b)
    if not has_trailing_newline and parts_b:
        body += b"\n\\ No newline at end of file"
    header = (
        f"diff --git a/{rel_path} b/{rel_path}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{rel_path}\n"
        f"@@ -0,0 +1,{n} @@\n"
    ).encode("utf-8")
    out = header + body
    if has_trailing_newline:
        out += b"\n"
    return out


def main() -> int:
    parts: list[bytes] = []
    for p in MODIFIED:
        d = git_diff(p)
        if not d.strip():
            print(f"WARN: no diff for {p}", file=sys.stderr)
        parts.append(d)
    for p in NEW_FILES:
        parts.append(synthesize_new_file_block(p))
    full = b"".join(parts)
    OUT.write_bytes(full)
    sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    size = OUT.stat().st_size
    print(f"PATCH: {OUT}")
    print(f"SIZE: {size}")
    print(f"SHA256: {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
