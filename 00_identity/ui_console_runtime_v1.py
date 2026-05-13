from pathlib import Path
from fastapi.responses import HTMLResponse
import ui_proxy_server as legacy

app = legacy.app

# quitar la ruta /ui vieja del proxy legado
try:
    app.router.routes = [
        r for r in app.router.routes
        if getattr(r, "path", None) != "/ui"
    ]
except Exception:
    pass

HTML_FILE = Path(r"C:\AI_VAULT\00_identity\ui_console_conversational_v1.html")

@app.get("/ui", response_class=HTMLResponse)
async def ui_page_override() -> HTMLResponse:
    if HTML_FILE.exists():
        txt = HTML_FILE.read_text(encoding="utf-8").replace("%DEFAULT_MODEL%", getattr(legacy, "DEFAULT_MODEL", "qwen2.5:14b"))
        resp = HTMLResponse(txt)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    resp = HTMLResponse("<html><head><title>Brain Lab — Console Conversacional</title></head><body><h1>Falta ui_console_conversational_v1.html</h1></body></html>")
    resp.headers["Cache-Control"] = "no-store"
    return resp
