from pathlib import Path

logs = sorted(Path(r'C:/AI_VAULT/tmp_agent/logs').glob('brain_v9_stderr_*.log'), key=lambda x: x.stat().st_mtime, reverse=True)

# Focus on the two most recent logs with real user interactions
for logf in logs[:2]:
    content = logf.read_text(encoding='utf-8', errors='replace')
    lines = content.splitlines()
    print(f"\n{'='*80}")
    print(f"=== {logf.name} ===")
    print(f"{'='*80}")
    
    for i, line in enumerate(lines):
        # Show lines related to default session (real user) - skip test_ and warmup
        low = line.lower()
        if ('default' in line or 'MSG=' in line) and 'test_' not in line and 'warmup' not in line:
            safe = line[:400].encode('ascii', errors='replace').decode('ascii')
            print(f"{i:4d}: {safe}")
