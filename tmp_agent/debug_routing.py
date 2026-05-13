"""Direct test: call BrainSession.chat() to see intent/route."""
import sys, asyncio, os
sys.path.insert(0, "C:/AI_VAULT/tmp_agent")
os.chdir("C:/AI_VAULT/tmp_agent")

from brain_v9.core.session import BrainSession

async def test():
    s = BrainSession("test_debug")
    
    # Test 1: Sharpe question
    msg = "explicame brevemente que es el ratio de sharpe"
    history = s.memory.get_context()
    intent, confidence, meta = s.intent.detect(msg, history)
    use_agent = s._should_use_agent(msg, intent, confidence)
    print(f"[TEST1] msg='{msg}'")
    print(f"  intent={intent} conf={confidence:.2f} meta={meta}")
    print(f"  use_agent={use_agent}")
    
    # Test 2: read file
    msg2 = "lee las primeras 5 lineas de brain_v9/core/session.py"
    intent2, conf2, meta2 = s.intent.detect(msg2, history)
    use_agent2 = s._should_use_agent(msg2, intent2, conf2)
    print(f"\n[TEST2] msg='{msg2}'")
    print(f"  intent={intent2} conf={conf2:.2f} meta={meta2}")
    print(f"  use_agent={use_agent2}")
    
    # Test 3: Check _AGENT_PATTERNS
    from brain_v9.core.session import _AGENT_PATTERNS
    matches1 = [(i, p.pattern) for i, p in enumerate(_AGENT_PATTERNS) if p.search(msg)]
    matches2 = [(i, p.pattern) for i, p in enumerate(_AGENT_PATTERNS) if p.search(msg2)]
    print(f"\n  Sharpe pattern matches: {matches1}")
    print(f"  ReadFile pattern matches: {matches2}")
    
    await s.close()

asyncio.run(test())
