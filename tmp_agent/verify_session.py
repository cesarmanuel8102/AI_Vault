import sys
sys.path.insert(0, r'C:\AI_VAULT\tmp_agent')

# Forzar recarga del módulo
if 'brain_v9.core.session' in sys.modules:
    del sys.modules['brain_v9.core.session']
    print("Módulo session.py eliminado de cache")

from brain_v9.core.session import BrainSession
import inspect

# Verificar el código fuente
source = inspect.getsource(BrainSession._route_to_agent)
if 'synthesis_prompt' in source:
    print("✅ CÓDIGO NUEVO: Síntesis está activada")
else:
    print("❌ CÓDIGO ANTIGUO: Síntesis NO está activada")
    print("\nPrimeras líneas del método:")
    lines = source.split('\n')
    for i, line in enumerate(lines[:15]):
        print(f"  {i}: {line}")
