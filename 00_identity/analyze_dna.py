import json

with open(r'C:\AI_VAULT\FULL_DNA.JSON', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=== ANALISIS DEL FULL_DNA.JSON ===")
print(f"Total de archivos/codigo: {len(data)}")
print()

# Archivos clave
key_files = [
    '00_identity\\advisor_server.py',
    '00_identity\\brain_server.py', 
    '00_identity\\agent_loop.py',
    '00_identity\\brain_router.py',
    '00_identity\\constitution.md',
    '00_identity\\decision_engine_protocol.md',
    '00_identity\\memory_system.md'
]

print("=== ARCHIVOS CLAVE DEL SISTEMA ===")
for kf in key_files:
    if kf in data:
        content = data[kf]
        lines = content.count('\n')
        print(f"[OK] {kf}: {lines} lineas")
    else:
        print(f"[MISSING] {kf}: NO ENCONTRADO")

print()
print("=== BACKUPS Y VERSIONES ===")
backups = [k for k in data.keys() if '.bak' in k or 'LKG' in k]
print(f"Total de backups/versiones: {len(backups)}")

# Agrupar por tipo de archivo
py_files = [k for k in data.keys() if k.endswith('.py') and 'venv' not in k]
json_files = [k for k in data.keys() if k.endswith('.json') and 'venv' not in k]
md_files = [k for k in data.keys() if k.endswith('.md') and 'venv' not in k]

print(f"\nArchivos Python (proyecto): {len(py_files)}")
print(f"Archivos JSON (proyecto): {len(json_files)}")
print(f"Archivos Markdown (proyecto): {len(md_files)}")

# Verificar estructura de carpetas
folders = set()
for key in data.keys():
    if '\\' in key:
        parts = key.split('\\')
        for i in range(1, len(parts)):
            folders.add('\\'.join(parts[:i]))

print(f"\nCarpetas principales: {len(folders)}")
for folder in sorted(folders)[:15]:
    files_in_folder = len([k for k in data.keys() if k.startswith(folder + '\\')])
    print(f"  {folder}: {files_in_folder} archivos")

# Analizar contenido de archivos principales
print("\n=== CONTENIDO DE ARCHIVOS PRINCIPALES ===")

# Advisor Server
adv = data.get('00_identity\\advisor_server.py', '')
print(f"\nadvisor_server.py:")
print(f"  Lineas: {adv.count(chr(10))}")
print(f"  Tiene FastAPI: {'FastAPI' in adv}")
print(f"  Tiene OpenAI: {'openai' in adv.lower()}")
print(f"  Endpoints: {len([l for l in adv.split(chr(10)) if '@app.' in l])}")

# Brain Server  
brain = data.get('00_identity\\brain_server.py', '')
print(f"\nbrain_server.py:")
print(f"  Lineas: {brain.count(chr(10))}")
print(f"  Tiene FastAPI: {'FastAPI' in brain}")
print(f"  Modelos Pydantic: {len([l for l in brain.split(chr(10)) if '(BaseModel)' in l])}")
print(f"  Referencias HARDENING: {brain.count('HARDENING')}")

# Agent Loop
agent = data.get('00_identity\\agent_loop.py', '')
print(f"\nagent_loop.py:")
print(f"  Lineas: {agent.count(chr(10))}")
print(f"  Clases: {len([l for l in agent.split(chr(10)) if l.strip().startswith('class ')])}")
print(f"  Tiene mission: {'mission' in agent.lower()}")
print(f"  Tiene plan: {'plan' in agent.lower()}")

# Documentacion
const = data.get('00_identity\\constitution.md', '')
dec = data.get('00_identity\\decision_engine_protocol.md', '')
mem = data.get('00_identity\\memory_system.md', '')

print(f"\nDocumentacion:")
print(f"  constitution.md: {const.count(chr(10))} lineas")
print(f"  decision_engine_protocol.md: {dec.count(chr(10))} lineas")
print(f"  memory_system.md: {mem.count(chr(10))} lineas")

print("\n=== ANALISIS COMPLETADO ===")
