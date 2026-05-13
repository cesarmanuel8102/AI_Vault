from pathlib import Path
logs = sorted(Path(r'C:/AI_VAULT/tmp_agent/logs').glob('brain_v9_stderr_*.log'), key=lambda x: x.stat().st_mtime, reverse=True)
if logs:
    content = logs[0].read_text(encoding='utf-8', errors='replace')
    lines = content.splitlines()
    found = False
    for i, line in enumerate(lines):
        if 'test_single_port' in line or ('single_port' in line.lower() and 'INFO' in line):
            found = True
        if found and ('single_port' in line.lower() or 'AgentLoop' in line or 'LLMManager' in line or 'Budget' in line or 'GATE' in line or 'paso ' in line or 'wall-clock' in line or 'synthesis' in line or 'verify' in line or 'ORAV' in line):
            safe = line[:250].encode('ascii', errors='replace').decode('ascii')
            print(f'{i}: {safe}')
        if found and i > 300:
            break
