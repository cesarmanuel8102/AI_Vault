# brain_server_emergency.py - Versión corregida
from fastapi import FastAPI
import uvicorn
from financial_autonomy.api.financial_endpoints import router as financial_autonomy_router

app = FastAPI(title="Brain Server Emergency", version="1.0")

# Incluir routers
app.include_router(financial_autonomy_router)

@app.get("/")
async def root():
    return {"status": "emergency_mode", "message": "Brain Server en modo emergencia"}

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": "2026-03-11T03:20:00Z"}

@app.get("/financial-integration/status")
async def financial_integration_status():
    return {
        "status": "integrated", 
        "module": "financial_autonomy", 
        "emergency_mode": True
    }

if __name__ == "__main__":
    print("🚀 Iniciando Brain Server de emergencia en puerto 8010...")
    uvicorn.run(app, host="0.0.0.0", port=8010)
