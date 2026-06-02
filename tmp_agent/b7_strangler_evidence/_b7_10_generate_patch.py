"""Binary-safe patch generator for B7-STRANGLER-10.

Generates a patch that includes both tracked modifications (via git diff)
and untracked new files (synthesized new-file diff blocks) WITHOUT using
git add -N.
"""
import subprocess, pathlib, hashlib, json, sys

ROOT = pathlib.Path(r"C:\AI_VAULT")
EV = ROOT / "tmp_agent" / "b7_strangler_evidence"

TRACKED = ["tmp_agent/brain_v9/core/session.py"]
UNTRACKED = [
    "tmp_agent/brain_v9/core/session_llm_chain_select.py",
    "tests/unit/test_b7_llm_chain_select_import_compat.py",
    "tests/unit/test_b7_llm_chain_select_behavior_smoke.py",
    "tests/unit/test_b7_llm_chain_select_no_session_dependency.py",
]

pieces = []

# 1. Tracked modifications via git diff
for f in TRACKED:
    result = subprocess.run(
        ["git", "diff", "--", f],
        cwd=ROOT,
        capture_output=True,
    )
    assert result.returncode == 0, f"git diff failed for {f}: {result.stderr.decode()!r}"
    pieces.append(result.stdout)

# 2. Untracked new files: synthesize patch blocks
for f in UNTRACKED:
    path = ROOT / f
    content = path.read_bytes()
    lines = content.splitlines(keepends=True)
    # Build synthetic diff block
    header = (
        f"diff --git a/{f} b/{f}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{f}\n"
    ).encode()
    # hunk header
    hunk = f"@@ -0,0 +1,{len(lines)} @@\n".encode()
    # prefix each line with +
    body = b"".join(b"+" + (line if line.endswith(b"\n") else line + b"\n") for line in lines)
    pieces.append(header + hunk + body)

patch_bytes = b"\n".join(pieces)

patch_path = EV / "b7_10_llm_chain_select_extraction.patch"
with open(patch_path, "wb") as fh:
    fh.write(patch_bytes)

# manifest
manifest = {
    "ticket": "B7-STRANGLER-10-IMPLEMENT-FIX",
    "files_in_patch": TRACKED + UNTRACKED,
    "tracked_files": TRACKED,
    "untracked_files": UNTRACKED,
    "patch_path": str(patch_path),
    "patch_bytes": len(patch_bytes),
    "patch_lines": patch_bytes.count(b"\n"),
    "patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
    "git_add_n_used": False,
}
with open(EV / "b7_10_llm_chain_select_patch_manifest.json", "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2)

print(f"PATCH written: {patch_path} ({len(patch_bytes)} bytes)")
print(f"  tracked: {len(TRACKED)}, untracked: {len(UNTRACKED)}")
