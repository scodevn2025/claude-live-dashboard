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


dropped_events: int = 0


async def _tail_dispatch(sess: Path, start_offset: int) -> None:
    """Tail file + dispatch events qua SSE queues. Raise khi session cần switch."""
    global dropped_events
    async for raw in tail_file(sess, start_offset=start_offset):
        # Bug #4: check pin thường xuyên để react nhanh
        if state.pinned_session_file and state.pinned_session_file != str(sess):
            return
        if not state.pinned_session_file:
            current = find_active_session()
            if current and current != sess and current.stat().st_mtime > sess.stat().st_mtime + 5:
                return
        for ev in parse_event(raw):
            state.apply(ev)
            payload = orjson.dumps(ev).decode()
            for q in list(subscribers):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    # Bug #5: log drop thay vì silent suppress
                    dropped_events += 1
                    print(f"[sse] dropped event (queue full), total dropped: {dropped_events}")


async def _consume_session() -> None:
    """Background task: tail session + reactively switch khi pin đổi (bug #4)."""
    while True:
        if state.pinned_session_file:
            sess = Path(state.pinned_session_file)
            if not sess.exists():
                await asyncio.sleep(1)
                continue
            start_offset = 0  # Pin mode: load full history
        else:
            sess = find_active_session()
            if not sess:
                await asyncio.sleep(2)
                continue
            # Catch-up 500KB cuối để seed recent_thinkings + counters + edit history
            # (thay vì skip toàn bộ existing content)
            start_offset = max(0, sess.stat().st_size - 500_000)

        state.reset_session(str(sess), sess.stem)
        try:
            # Wrap trong task để cancel được khi pin đổi (bug #4 race fix)
            dispatch_task = asyncio.create_task(_tail_dispatch(sess, start_offset))
            while not dispatch_task.done():
                await asyncio.sleep(1)
                # Pin đổi → cancel dispatch + loop lại
                if state.pinned_session_file != (str(sess) if state.pinned_session_file else None):
                    if state.pinned_session_file != str(sess):
                        dispatch_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await dispatch_task
                        break
            else:
                await dispatch_task  # retrieve result or exception
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
