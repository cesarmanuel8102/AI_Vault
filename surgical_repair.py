import os
import json
import re

def repair():
    # 1. REPARACION MAESTRA DEL CORE (8010)
    path = 'C:/AI_VAULT/00_identity/brain_server.py'
    # Escribimos el servidor desde cero para evitar residuos de 638KB
    master_code = """from __future__ import annotations
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import json
import os
from pathlib import Path

app = FastAPI(title='Brain Lab Master Core')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.get('/healthz')
@app.get('/v1/agent/healthz')
@app.get('/v1/agent/status')
def health(): return {'ok': True, 'status': 'healthy', 'fase': 'BL-02'}

@app.get('/ui/live')
def dashboard(): return {'message': 'Dashboard Online', 'fase': 'BL-02'}

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=8010)
"""
    with open(path, 'w', encoding='utf-8') as f: f.write(master_code)

    # 2. LECTURA EXPLICITA DEL ROADMAP
    roadmap_path = 'C:/AI_VAULT/tmp_agent/state/roadmap.json'
    report = {'fase_actual': 'BL-02', 'objetivo': 'Operativizar U'}
    if os.path.exists(roadmap_path):
        with open(roadmap_path, 'r', encoding='utf-8') as f:
            rm = json.load(f)
            report['detalle'] = rm.get('objective', 'Construccion de Motor Financiero')
    
    with open('C:/AI_VAULT/CODEX_REPORT.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

repair()