"""FastAPI gateway — serve dashboard + SSE events từ Claude Code transcript."""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import orjson
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse, Response
from sse_starlette.sse import EventSourceResponse

from .inventory import inventory
from .parser import parse_event
from .state import SessionState
from .watcher import find_active_session, tail_file

STATIC_DIR = Path(__file__).parent.parent / "static"

state = SessionState(max_events=300)
subscribers: set[asyncio.Queue] = set()


async def _consume_session() -> None:
    """Background task: tail active session + auto-switch khi session file đổi."""
    while True:
        sess = find_active_session()
        if not sess:
            await asyncio.sleep(2)
            continue
        state.reset_session(str(sess), sess.stem)
        size = sess.stat().st_size
        # Tail hiện tại cho đến khi phát hiện session file mới hơn
        try:
            async for raw in tail_file(sess, start_offset=size):
                # Check nếu có session file mới hơn (user mở session mới)
                current = find_active_session()
                if current and current != sess and current.stat().st_mtime > sess.stat().st_mtime + 5:
                    break  # restart loop với session mới
                for ev in parse_event(raw):
                    state.apply(ev)
                    payload = orjson.dumps(ev).decode()
                    for q in list(subscribers):
                        with contextlib.suppress(asyncio.QueueFull):
                            q.put_nowait(payload)
        except Exception as e:
            print(f"[watcher] error: {e}, restarting in 3s")
            await asyncio.sleep(3)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_consume_session())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(lifespan=lifespan, title="Claude Live Dashboard")


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard")
async def dashboard():
    html = STATIC_DIR / "dashboard.html"
    if not html.exists():
        return Response("dashboard.html not found", status_code=404)
    return FileResponse(html, media_type="text/html")


@app.get("/api/snapshot")
async def snapshot():
    return Response(
        orjson.dumps(state.snapshot()),
        media_type="application/json",
    )


@app.get("/api/events")
async def events():
    async def stream():
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        subscribers.add(q)
        try:
            # Initial burst: last 50 events
            for ev in state.recent(50):
                yield {"event": "snapshot", "data": orjson.dumps(ev).decode()}
            while True:
                data = await q.get()
                yield {"event": "event", "data": data}
        finally:
            subscribers.discard(q)
    return EventSourceResponse(stream())


@app.get("/api/health")
async def health():
    return {"ok": True, "session": state.session_id, "events": len(state.events)}


@app.get("/api/inventory")
async def api_inventory():
    """MCP servers + plugins + skills đã cài trong ~/.claude/."""
    return Response(orjson.dumps(inventory()), media_type="application/json")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="127.0.0.1", port=8765, reload=False, log_level="info")
