import os
patterns = ['_sanitize_llm_chat_response', '_fmt_']
caller_files = {}
SEP = chr(92)
for root, _, files in os.walk('.'):
    norm = root.replace(SEP, '/')
    if any(skip in norm for skip in ['.git', '__pycache__', 'strategies', 'chat_area_upgrade', 'visual_trace_console_v1', 'b7_strangler_evidence', 'memory/semantic', 'node_modules', 'venv']):
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        p = os.path.join(root, f)
        try:
            txt = open(p, encoding='utf-8').read()
        except Exception:
            continue
        for pat in patterns:
            if pat in txt:
                caller_files.setdefault(pat, []).append(p.replace(SEP, '/'))
for pat, files in caller_files.items():
    print(pat, '->', len(files), 'files')
    for f in files[:50]:
        print('  ', f)
