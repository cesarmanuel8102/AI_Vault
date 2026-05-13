from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Brain Server Simple")

@app.get("/")
async def root():
    return {"status": "ok", "service": "brain_simple"}

@app.get("/v1/agent/status")
async def status():
    return {"ok": True, "status": "operational"}

@app.post("/v1/agent/run_once")
async def run_once(data: dict):
    return {"ok": True, "room_id": data.get("room_id", "unknown")}

if __name__ == "__main__":
    print("🧠 Brain Server Simple iniciando en puerto 8010...")
    uvicorn.run(app, host="0.0.0.0", port=8010)
