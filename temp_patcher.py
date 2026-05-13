import os
import requests
import time

ruta_core = 'C:/AI_VAULT/00_identity/brain_server.py'

def aplicar_super_parche():
    with open(ruta_core, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Asegurar que tenga los imports necesarios
    if 'from fastapi.middleware.cors import CORSMiddleware' not in content:
        content = "from fastapi.middleware.cors import CORSMiddleware\n" + content

    # 2. Reemplazar/Inyectar el bloque de salud y CORS de forma limpia
    # Buscamos la creacion de la app
    if 'app = FastAPI(' in content and 'app.add_middleware' not in content:
        bloque_cors = """
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def healthz():
    return {"ok": True, "status": "healthy"}

@app.get("/v1/agent/healthz")
def healthz_v1():
    return {"ok": True, "status": "healthy"}
"""
        import re
        content = re.sub(r'(app = FastAPI\(.*?\))', r'\1' + bloque_cors, content, count=1)
        
    with open(ruta_core, 'w', encoding='utf-8') as f:
        f.write(content)
    print("[OK] Core parcheado con CORS y Healthz.")

aplicar_super_parche()
