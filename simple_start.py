# simple_start.py - Inicio simple y directo
import uvicorn
from brain_server_emergency import app

if __name__ == "__main__":
    print("🚀 Iniciando Brain Server Emergency en puerto 8010...")
    uvicorn.run(app, host="0.0.0.0", port=8010, log_level="info")
