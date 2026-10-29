"""FastAPI gateway — serve dashboard + SSE events từ Claude Code transcript."""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import orjson
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.requests import Request
from sse_starlette.sse import EventSourceResponse

from .inventory import inventory
from .parser import parse_event
from .state import SessionState
from .watcher import find_active_session, tail_file

STATIC_DIR = Path(__file__).parent.parent / "static"

state = SessionState(max_events=300)
subscribers: set[asyncio.Queue] = set()


async def _consume_session() -> None:
    """Background task: tail session hiện pinned (nếu có) hoặc active.

    - Nếu state.pinned_session_file set → tail file đó, catch-up từ đầu.
    - Nếu không → tail session active (newest mtime), auto-switch khi file mới xuất hiện.
    """
    while True:
        if state.pinned_session_file:
            sess = Path(state.pinned_session_file)
            if not sess.exists():
                await asyncio.sleep(2)
                continue
            # Pin mode: catch-up from offset 0 để load full history
            start_offset = 0
        else:
            sess = find_active_session()
            if not sess:
                await asyncio.sleep(2)
                continue
            # Auto mode: skip existing content, chỉ bắt event mới
            start_offset = sess.stat().st_size

        state.reset_session(str(sess), sess.stem)
        try:
            async for raw in tail_file(sess, start_offset=start_offset):
                # Nếu user pin session khác → restart loop
                if state.pinned_session_file and state.pinned_session_file != str(sess):
                    break
                # Nếu auto mode và có session newer → switch
                if not state.pinned_session_file:
                    current = find_active_session()
                    if current and current != sess and current.stat().st_mtime > sess.stat().st_mtime + 5:
                        break
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


@app.post("/api/pin-session")
async def pin_session(request: Request):
    """Pin dashboard theo dõi 1 session cụ thể qua session_id (basename).

    Body: {"id": "<session_uuid>"} → tìm file ~/.claude/projects/*/<id>.jsonl
    hoặc {"clear": true} để unpin, trở về auto-mode.
    """
    body = await request.json()
    if body.get("clear"):
        state.pinned_session_file = None
        return {"ok": True, "mode": "auto"}
    sid = body.get("id", "").strip()
    if not sid:
        return {"ok": False, "error": "missing id"}
    # Resolve id → full path
    projects_dir = Path.home() / ".claude" / "projects"
    matches = list(projects_dir.glob(f"*/{sid}.jsonl"))
    if not matches:
        return {"ok": False, "error": f"session {sid[:8]} not found"}
    state.pinned_session_file = str(matches[0])
    return {"ok": True, "mode": "pinned", "file": str(matches[0]), "id": sid}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="127.0.0.1", port=8765, reload=False, log_level="info")
