import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import store
from .config import settings
from .vision import ShelfMonitor

monitor = ShelfMonitor()
ROOT = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    monitor.start()
    yield


app = FastAPI(title="Shelf Monitor", version="1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/status")
def status():
    return {"status": monitor.status, "mode": settings.mode, "camera": "connected" if monitor.cap and monitor.cap.isOpened() else "demo" if settings.mode == "demo" else "disconnected", "model": bool(monitor.model), "uptime": int(__import__("time").time() - monitor.started_at) if monitor.started_at else 0}


@app.get("/api/shelves")
def get_shelves():
    return [{**s, "level": monitor.level(s["quantity"], s["capacity"]), "assigned_product": settings.products[s["id"]-1]} for s in store.shelves()]


@app.get("/api/events")
def get_events(limit: int = Query(default=40, ge=1, le=200)):
    return store.events(limit)


@app.get("/evidence/{filename}")
def evidence(filename: str):
    # Restrict paths to one plain filename beneath the evidence directory.
    if Path(filename).name != filename:
        return HTMLResponse("Not found", status_code=404)
    path = Path(settings.evidence_dir) / filename
    if not path.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(path, media_type="image/jpeg")


async def frames():
    while True:
        frame = monitor.jpeg()
        if frame:
            yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
        await asyncio.sleep(1 / max(settings.fps, 1))


@app.get("/api/camera")
def camera():
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")
