import ast, sys
src = open("C:/AI_VAULT/tmp_agent/brain_v9/agent/failure_learner.py", encoding="utf-8").read()
try:
    ast.parse(src)
    print("OK syntax")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
