# claude-live-dashboard

Realtime observability dashboard cho Claude Code harness — ba nhìn con đang xử lý gì (tool calls, agents spawn, loops, flow) qua browser.

## Chạy

```bash
# Lần đầu (cài deps)
uv sync

# Khởi động
./start.bat          # Windows — mở sẵn trình duyệt
# hoặc
uv run python -X utf8 -m uvicorn src.main:app --host 127.0.0.1 --port 8765
```

Mở http://127.0.0.1:8765/dashboard

## Architecture

```
~/.claude/projects/<slug>/<session>.jsonl    (Claude Code transcript — append-only)
       ↓ watchfiles tail
   src/watcher.py                            (yield raw JSON per new line)
       ↓
   src/parser.py                             (classify → normalized schema)
       ↓
   src/state.py                              (in-memory rolling window + counters)
       ↓
   src/main.py (FastAPI)
       ├── /api/snapshot   (JSON state hiện tại)
       ├── /api/events     (SSE stream event mới)
       └── /dashboard      (static/dashboard.html)
                               ↓
                        Trình duyệt (SSE EventSource)
                               → timeline + agent tree + metrics
```

## Event schema (normalized)

```json
{
  "id": "toolu_01",
  "ts": 1793269414.627,
  "kind": "tool_use",        // tool_use | tool_result | user_msg | assistant_text | agent_spawn | agent_result | api_request | system
  "name": "Bash",
  "status": "running",       // running | success | error | null
  "duration": 2.3,           // giây (tool_result có, tính từ tool_use match qua tool_use_id)
  "payload": {...}
}
```

## Phase progress

- [x] Phase 1 — scaffold (dir + pyproject + uv sync)
- [x] Phase 2 — jsonl watcher (watchfiles tail + auto-switch session)
- [x] Phase 3 — event parser (8 kinds + extract `message.usage` tokens)
- [x] Phase 4 — FastAPI + SSE (port 8765, 4 endpoints + reconnect)
- [x] Phase 5 — HTML dashboard (GSAP + dark + 6 enhancements)
- [x] Phase 6 — start.bat launcher
- [x] Phase 7 — Enhancements v2:
    - Timeline fade-out old events
    - Flow tool-bus sustained glow
    - Real context tokens (actual API usage)
    - Agent tree collapse/expand
    - Loop lifecycle ring progress
    - Error red pulse
    - **Inventory panel** (MCP + Plugins + Skills từ ~/.claude/)
    - Session auto-switch
    - SSE auto-reconnect exponential backoff

## Endpoints

- `GET /` → redirect `/dashboard`
- `GET /dashboard` → static/dashboard.html
- `GET /api/snapshot` → full state JSON (counters + context tokens + events)
- `GET /api/events` → SSE stream events realtime
- `GET /api/inventory` → MCP servers + plugins + skills count/list
- `GET /api/health` → health check

## Verify

```bash
curl http://127.0.0.1:8765/api/health
# {"ok":true,"session":"<uuid>","events":<n>}

curl http://127.0.0.1:8765/api/snapshot | head -c 500
# JSON state
```

## Known issues

- Tabler webfont CDN chưa load trên 1 số môi trường — icons hiển thị trống. Fix sau bằng SVG inline.
- `api-request` events hiển thị "undefined chars" — payload parse không có `chars`. Cosmetic.
- Flow graph SVG tĩnh — chưa highlight node đang chạy. Phase sau.

## Decisions

- **Dark theme** mặc định (nền `#0f0f0e`). Lúc sau Astra 6 có thể chuyển light.
- **Font monospace** cho timeline, counter, session id — dễ đọc dạng techie.
- **Port 8765** — tránh trùng 8080/3000/5173 phổ biến.
- **No build step** — HTML + CSS + JS inline, ba sửa thẳng tay.
- **SSE one-way** — dashboard read-only, không cần WebSocket.

ScodeVN: github.com/scodevn2025
