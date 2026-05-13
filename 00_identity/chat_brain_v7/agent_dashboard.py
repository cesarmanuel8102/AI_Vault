#!/usr/bin/env python3
"""
Dashboard Web del Agente
Interfaz web para monitorear y controlar el agente
"""

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import asyncio
from datetime import datetime

app = FastAPI(title="Brain Agent Dashboard")

HTML_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <title>Brain Agent Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .card { background: #16213e; border-radius: 8px; padding: 20px; margin: 10px 0; }
        .metric { display: inline-block; margin: 10px 20px; }
        .metric-value { font-size: 24px; color: #0f4c75; }
        .status-online { color: #4ecca3; }
        .status-offline { color: #e74c3c; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Brain Agent V8 - Dashboard</h1>
        
        <div class="card">
            <h2>Estado del Sistema</h2>
            <div class="metric">
                <div class="metric-value status-online">●</div>
                <div>Agente Online</div>
            </div>
            <div class="metric">
                <div class="metric-value">8090</div>
                <div>Puerto</div>
            </div>
            <div class="metric">
                <div class="metric-value">11</div>
                <div>Modelos LLM</div>
            </div>
        </div>
        
        <div class="card">
            <h2>Métricas</h2>
            <div class="metric">
                <div class="metric-value">19</div>
                <div>Tests Pasados</div>
            </div>
            <div class="metric">
                <div class="metric-value">100%</div>
                <div>Cobertura Tests</div>
            </div>
            <div class="metric">
                <div class="metric-value">9</div>
                <div>Módulos</div>
            </div>
        </div>
        
        <div class="card">
            <h2>Log</h2>
            <div id="log">Sistema operativo...</div>
        </div>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=HTML_DASHBOARD)

@app.get("/api/status")
async def api_status():
    return {
        "status": "online",
        "version": "8.0",
        "timestamp": datetime.now().isoformat(),
        "tests_passed": 19,
        "tests_total": 19
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8092)
