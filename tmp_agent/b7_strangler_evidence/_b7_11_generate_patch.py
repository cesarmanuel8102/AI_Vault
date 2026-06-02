"""Binary-safe patch generator for B7-STRANGLER-11."""
import subprocess, pathlib, hashlib, json

ROOT = pathlib.Path(r"C:\AI_VAULT")
EV = ROOT / "tmp_agent" / "b7_strangler_evidence"

TRACKED = ["tmp_agent/brain_v9/core/session.py"]
UNTRACKED = [
    "tmp_agent/brain_v9/core/session_agent_render.py",
    "tests/unit/test_b7_agent_render_import_compat.py",
    "tests/unit/test_b7_agent_render_behavior_smoke.py",
    "tests/unit/test_b7_agent_render_no_session_dependency.py",
]

pieces = []

for f in TRACKED:
    result = subprocess.run(
        ["git", "diff", "--", f],
        cwd=ROOT,
        capture_output=True,
    )
    assert result.returncode == 0, f"git diff failed for {f}: {result.stderr.decode()!r}"
    pieces.append(result.stdout)

for f in UNTRACKED:
    path = ROOT / f
    content = path.read_bytes()
    lines = content.splitlines(keepends=True)
    header = (
        f"diff --git a/{f} b/{f}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{f}\n"
    ).encode()
    hunk = f"@@ -0,0 +1,{len(lines)} @@\n".encode()
    body = b"".join(b"+" + (line if line.endswith(b"\n") else line + b"\n") for line in lines)
    pieces.append(header + hunk + body)

patch_bytes = b"\n".join(pieces)

patch_path = EV / "b7_11_agent_render_extraction.patch"
with open(patch_path, "wb") as fh:
    fh.write(patch_bytes)

manifest = {
    "ticket": "B7-STRANGLER-11-IMPLEMENT",
    "files_in_patch": TRACKED + UNTRACKED,
    "tracked_files": TRACKED,
    "untracked_files": UNTRACKED,
    "patch_path": str(patch_path),
    "patch_bytes": len(patch_bytes),
    "patch_lines": patch_bytes.count(b"\n"),
    "patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
    "git_add_n_used": False,
}
with open(EV / "b7_11_agent_render_patch_manifest.json", "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2)

print(f"PATCH written: {patch_path} ({len(patch_bytes)} bytes)")
