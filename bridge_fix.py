import os
import re
import json

def fix_system():
    # 1. Reparar el Core (8010) para permitir que la Consola hable con el
    core_path = 'C:/AI_VAULT/00_identity/brain_server.py'
    if os.path.exists(core_path):
        with open(core_path, 'r', encoding='utf-8') as f: lines = f.readlines()
        # Asegurar 'from __future__' en linea 1
        lines = [l for l in lines if 'from __future__' not in l]
        lines.insert(0, 'from __future__ import annotations\n')
        # Inyectar CORS y Healthz
        content = ''.join(lines)
        if 'CORSMiddleware' not in content:
            content = content.replace('import uvicorn', 'import uvicorn\nfrom fastapi.middleware.cors import CORSMiddleware')
            cors_code = '\napp.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])\n@app.get("/healthz")\ndef hz(): return {"ok":True}\n'
            content = content.replace('app = FastAPI(', cors_code + 'app = FastAPI(')
        with open(core_path, 'w', encoding='utf-8') as f: f.write(content)

    # 2. Generar Reporte de Roadmap explicito para el Arquitecto
    roadmap_path = 'C:/AI_VAULT/tmp_agent/state/roadmap.json'
    status = {'fase': 'BL-02', 'detalles': 'Operativizacion de U'}
    if os.path.exists(roadmap_path):
        with open(roadmap_path, 'r', encoding='utf-8') as f: 
            rm = json.load(f)
            status['items_completados'] = [i['id'] for i in rm.get('work_items', []) if i.get('status') == 'done']
    
    with open('C:/AI_VAULT/ROADMAP_STATUS.json', 'w', encoding='utf-8') as f:
        json.dump(status, f, indent=2)

fix_system()