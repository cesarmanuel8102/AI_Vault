from pathlib import Path
import re

logs = sorted(Path(r'C:/AI_VAULT/tmp_agent/logs').glob('brain_v9_stderr_*.log'), key=lambda x: x.stat().st_mtime, reverse=True)

# Look at recent logs (last few files) for real user interactions (not test_ sessions)
for logf in logs[:5]:
    content = logf.read_text(encoding='utf-8', errors='replace')
    lines = content.splitlines()
    print(f"\n=== {logf.name} ({len(lines)} lines) ===")
    
    for i, line in enumerate(lines):
        # Find chat messages from real sessions (not test_*)
        if "MSG='" in line and 'test_' not in line:
            safe = line[:300].encode('ascii', errors='replace').decode('ascii')
            print(f"  {safe}")
        # Also find session creation that's not test
        elif 'BrainSession' in line and 'v4-unified lista' in line and 'test_' not in line:
            safe = line[:200].encode('ascii', errors='replace').decode('ascii')
            print(f"  {safe}")
