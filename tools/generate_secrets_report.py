#!/usr/bin/env python3
import os
import re
import json
import csv
from pathlib import Path

ROOT = Path("c:/AI_VAULT")
OUT_DIR = ROOT / "audit_reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Exclude common large / vendor dirs
EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', 'site-packages'}
MAX_FILE_BYTES = 50 * 1024 * 1024  # skip files larger than 50MB

PATTERNS = {
    'openai_key': re.compile(r'sk-(?:proj-)?[A-Za-z0-9_\-]{16,}'),
    'generic_token_field': re.compile(r'\b(token|api_key|apikey|access_token|secret)\b\s*[:=]\s*["\']?([A-Za-z0-9_\-\.=:/@]+)["\']?', re.IGNORECASE),
    'aws_key': re.compile(r'AKIA[0-9A-Z]{16}'),
    'gcp_key': re.compile(r'AIza[0-9A-Za-z\-_]{35}'),
    'private_key_block': re.compile(r'-----BEGIN (?:RSA )?PRIVATE KEY-----'),
    'ssh_rsa': re.compile(r'ssh-rsa\s+[A-Za-z0-9+/=]{100,}'),
    'db_url': re.compile(r'\b(?:postgresql|postgres|mysql|mongodb|redis)://[^\s"\']+'),
    'env_var_style': re.compile(r'\b[A-Z_]+_?KEY\b'),
    'password_assignment': re.compile(r'password\b\s*[:=]\s*["\']?([^"\'\n]{4,})', re.IGNORECASE),
}

SEVERITY = {
    'openai_key': 'high',
    'generic_token_field': 'high',
    'aws_key': 'high',
    'gcp_key': 'high',
    'private_key_block': 'critical',
    'ssh_rsa': 'high',
    'db_url': 'high',
    'env_var_style': 'medium',
    'password_assignment': 'high',
}

results = []

for dirpath, dirnames, filenames in os.walk(ROOT):
    # normalize and filter excluded dirs
    parts = Path(dirpath).parts
    if any(p in EXCLUDE_DIRS for p in parts):
        # skip this subtree
        dirnames[:] = []
        continue

    for fname in filenames:
        fpath = Path(dirpath) / fname
        try:
            size = fpath.stat().st_size
        except Exception:
            continue
        if size > MAX_FILE_BYTES:
            continue

        # try open text
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except Exception:
            continue

        for i, line in enumerate(lines, start=1):
            for pname, preg in PATTERNS.items():
                for m in preg.finditer(line):
                    match_text = m.group(0)
                    # context: prev and next line (if present)
                    pre = lines[i-2].rstrip('\n') if i-2 >= 0 and len(lines) >= i-1 else ''
                    post = lines[i] .rstrip('\n') if i < len(lines) else ''
                    results.append({
                        'file': str(fpath.relative_to(ROOT)),
                        'abs_path': str(fpath),
                        'line': i,
                        'pattern': pname,
                        'severity': SEVERITY.get(pname, 'low'),
                        'match': match_text,
                        'pre_context': pre,
                        'line_text': line.rstrip('\n'),
                        'post_context': post,
                    })

# Write JSON and CSV
json_out = OUT_DIR / 'secrets_report.json'
csv_out = OUT_DIR / 'secrets_report.csv'
with open(json_out, 'w', encoding='utf-8') as jf:
    json.dump(results, jf, indent=2, ensure_ascii=False)

with open(csv_out, 'w', newline='', encoding='utf-8') as cf:
    writer = csv.DictWriter(cf, fieldnames=['file','line','pattern','severity','match','pre_context','line_text','post_context','abs_path'])
    writer.writeheader()
    for r in results:
        writer.writerow(r)

print(f"Found {len(results)} matches. Reports written to: {json_out} and {csv_out}")
