import glob, os, sys

logs = sorted(glob.glob('C:/AI_VAULT/tmp_agent/logs/brain_v9_stderr_*.log'), key=os.path.getmtime)
with open(logs[-1], 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# Find QC query
start = 0
for i, l in enumerate(lines):
    if 'ultimo backtest' in l.lower():
        start = i
        break

keywords = ['GATE:', 'sub-task', 'MetaPlanner', 'write_file', 'run_python', 'grep_codebase', 
            'ynthesis', 'AgentLoop', 'tool_calls', 'search_files']

with open('C:/AI_VAULT/tmp_agent/scripts/_log_output.txt', 'w', encoding='utf-8') as out:
    for l in lines[start:start+100]:
        stripped = l.rstrip()
        if any(k in stripped for k in keywords):
            out.write(stripped[:400] + '\n')
    out.write('\n--- ALL LINES ---\n')
    for l in lines[start:start+80]:
        out.write(l.rstrip()[:400] + '\n')

print("Done - see _log_output.txt")
