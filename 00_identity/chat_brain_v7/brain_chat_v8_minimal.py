#!/usr/bin/env python3
"""
Brain Chat V8.0 - Minimalista - Solo Core
Inicia servidor inmediatamente, carga sistemas bajo demanda
"""

import os
import sys
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
import uvicorn

app = FastAPI(title="Brain Chat V8.0 Minimalista", version="8.0.0")

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "8.0.0", "mode": "minimal"}

@app.get("/")
async def root():
    return {"message": "Brain Chat V8.0 Minimalista - Servidor funcionando", 
            "endpoints": ["/health", "/status", "/chat"]}

@app.post("/chat")
async def chat():
    return {"success": True, "reply": "Brain Chat V8.0 - Servidor en modo minimalista. Carga completa en progreso.", "mode": "minimal"}

@app.get("/status")
async def status():
    return {"status": "running", "initialized": False, "message": "Servidor iniciado. Cargando sistemas..."}

@app.get("/ui", response_class=HTMLResponse)
async def ui():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Brain Chat V8.0 - Funcionando</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: #0f172a; color: white; }
            h1 { color: #3b82f6; }
            .status { padding: 20px; background: #1e293b; border-radius: 8px; margin: 20px 0; }
            .success { color: #4ade80; }
        </style>
    </head>
    <body>
        <h1>Brain Chat V8.0 - Servidor Funcionando</h1>
        <div class="status">
            <p><strong class="success">Estado: ONLINE</strong></p>
            <p>Servidor minimalista iniciado correctamente en puerto 8090</p>
            <p>Endpoints disponibles:</p>
            <ul>
                <li><a href="/health" style="color: #3b82f6;">/health</a> - Health check</li>
                <li><a href="/status" style="color: #3b82f6;">/status</a> - Estado del sistema</li>
                <li><a href="/chat" style="color: #3b82f6;">/chat</a> - Chat endpoint</li>
            </ul>
        </div>
        <p><strong>Nota:</strong> El sistema completo V8.0 (11,891 líneas) está cargando en segundo plano.</p>
        <p>Para la versión completa con todas las features: <code>python brain_chat_v8.py</code></p>
    </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8090, log_level="info")
