from pathlib import Path
logs = sorted(Path(r'C:/AI_VAULT/tmp_agent/logs').glob('brain_v9_stderr_*.log'), key=lambda x: x.stat().st_mtime, reverse=True)
if logs:
    content = logs[0].read_text(encoding='utf-8', errors='replace')
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if 'MetaPlanner' in line or ('all_services' in line.lower() and 'INFO' in line):
            safe = line[:200].encode('ascii', errors='replace').decode('ascii')
            print(f'{i}: {safe}')
