import os
ruta = 'C:/AI_VAULT/00_identity/brain_server.py'
with open(ruta, 'r', encoding='utf-8') as f: lines = f.readlines()

# 1. Inyectar import de CORS
if 'from fastapi.middleware.cors import CORSMiddleware' not in ''.join(lines):
    lines.insert(1, 'from fastapi.middleware.cors import CORSMiddleware\n')

# 2. Inyectar configuracion de CORS y Health Check
cors_health_code = """
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def health_check():
    return {"status": "healthy", "ok": True}
"""

content = ''.join(lines)
if 'app.add_middleware' not in content:
    # Lo insertamos justo despues de la creacion de 'app = FastAPI(...)'
    if 'app = FastAPI' in content:
        import re
        content = re.sub(r'(app = FastAPI\(.*?\))', r'\1\n' + cors_health_code, content, flags=re.DOTALL)
    else:
        # Fallback si no encuentra la linea exacta
        content = content.replace('app = FastAPI()', 'app = FastAPI()\n' + cors_health_code)

with open(ruta, 'w', encoding='utf-8') as f: f.write(content)
print('CORS y Healthz inyectados correctamente.')