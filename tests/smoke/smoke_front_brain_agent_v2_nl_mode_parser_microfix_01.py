"""Smoke test: NL mode parser must NOT match 'auto' inside compound words."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from tmp_agent.brain_v9.core.agent_kernel_v2.governance import parse_mode_from_message

CASES = [
    ("Review promotion queue before autonomous promotion.", None, "autonomous must not trigger auto"),
    ("Heartbeat is stale — verify autonomy process.", None, "autonomy must not trigger auto"),
    ("auto_promote_strategies status", None, "auto_underscore compound must not match"),
    ("auto-promote queue", None, "auto-hyphen compound must not match"),
    ("modo auto. verifica últimos cambios", "auto", "explicit NL auto command"),
    ("modo build. revisa estado del repo", "build", "explicit NL build command"),
    ("hazlo en build y corrige el bug", "build", "explicit NL build command"),
    ("apruebo build", "build", "approval phrase with build keyword"),
    ("modo read. revisa estado", "read_only", "explicit NL read command"),
    ("modo lectura. revisa estado", "read_only", "explicit NL read command Spanish"),
    ("auto-promote or build pipeline", None, "build inside sentence must NOT match without explicit phrase"),
    ("This is a read_only mode test", "read_only", "standalone read_only keyword is safe to match (rare in normal text)"),
    ("Just a normal question", None, "no mode keyword"),
]

def test_all():
    failures = []
    for msg, expected, note in CASES:
        got = parse_mode_from_message(msg)
        if got != expected:
            failures.append({"note": note, "msg": msg, "expected": expected, "got": got})
    if failures:
        for f in failures:
            print(f"FAIL: {f['note']}\n  msg={f['msg']!r}\n  expected={f['expected']!r} got={f['got']!r}")
        assert False, f"{len(failures)} NL parser tests failed"
    else:
        print(f"PASS: all {len(CASES)} NL parser microfix tests passed")
