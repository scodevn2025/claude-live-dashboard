# Dashboard build state

**Project**: claude-live-dashboard — observability realtime cho Claude Code harness
**Owner**: ScodeVN (ba Khắc Huy)
**Start**: 2026-10-29

## Phase tracker

| Phase | Name | Status | Date |
|-------|------|--------|------|
| 1 | Scaffold | ✅ done | 2026-10-29 |
| 2 | JSONL watcher | ✅ done | 2026-10-29 |
| 3 | Event parser (+ usage extract) | ✅ done | 2026-10-29 |
| 4 | FastAPI + SSE (+ auto-switch session) | ✅ done | 2026-10-29 |
| 5 | HTML dashboard (GSAP + 7 enhancements) | ✅ done | 2026-10-29 |
| 6 | Launcher + verify live | ✅ done | 2026-10-29 |
| 7 | Enhancements v2 (fade/pulse/collapse/loops/tokens/inventory) | ✅ done | 2026-10-29 |

## Features implemented

- Timeline fade-out old events (opacity 0.45→0.25 for aged rows)
- Flow tool-bus sustained glow khi `activeTools > 0`
- Real context tokens từ Claude API usage (`cache_read + cache_create + input`)
- Agent tree collapse/expand (GSAP height transition)
- Loop lifecycle ring progress (uvicorn tail interval demo)
- Error state red pulse khi tool_result status=error
- **Inventory panel**: MCP servers + plugins + skills từ ~/.claude/ scan
- MCP tool highlight khi gọi `mcp__<name>__` → active pulse ở inventory
- Session auto-switch khi file jsonl mới nhất đổi
- SSE auto-reconnect exponential backoff (1s→2s→4s→8s→15s)

## Decisions locked

- Data source: `~/.claude/projects/<slug>/<session>.jsonl` (append-only transcript)
- Transport: SSE (Server-Sent Events) one-way, port 8765
- Backend: FastAPI + watchfiles + orjson
- Frontend: Vanilla HTML + CSS animations + fetch EventSource (no React build step)
- UI reference: Codex `-m astra6` output style (chờ screenshot ba)
- Launcher: `start.bat` Windows (uv run uvicorn + mở trình duyệt)

## Why lazy

- Transcript JSONL = native data source, zero hooks config
- Watchfiles (Rust) nhanh hơn watchdog cho tail file
- SSE one-way đủ cho dashboard read-only, không cần WebSocket
- Vanilla HTML không build step = ba sửa UI thẳng tay nếu muốn
