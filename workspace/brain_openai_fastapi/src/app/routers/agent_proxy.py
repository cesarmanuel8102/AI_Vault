from fastapi import APIRouter

router = APIRouter()

@router.get("/agent/status")
def agent_status():
    return {"ok": True, "impl": "agent_proxy_placeholder_v1"}