from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Brain Server Working")

@app.get("/")
async def root():
    return {"status": "ok", "service": "brain_working"}

@app.get("/v1/agent/status")
async def status():
    return {"ok": True, "status": "operational", "version": "2.0"}

@app.post("/v1/agent/run_once")
async def run_once(data: dict):
    return {"ok": True, "room_id": data.get("room_id", "unknown"), "executed": True}

if __name__ == "__main__":
    print("🧠 Brain Server Working iniciando en puerto 8010...")
    uvicorn.run(app, host="0.0.0.0", port=8010, log_level="info")
