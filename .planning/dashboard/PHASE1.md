# Phase 1 — Scaffold

**Goal**: Dir structure + Python env + deps đủ để Phase 2 bắt đầu code.

## Success criteria

- [x] Dir tree tạo xong (`src/`, `static/`, `.planning/dashboard/`)
- [x] `pyproject.toml` khai báo 5 deps
- [x] `.gitignore` loại .venv/__pycache__/*.log
- [x] `STATE.md` khai báo phase tracker + decisions
- [ ] `uv sync` cài deps thành công
- [ ] Import check: 5 lib đều import được

## Task list

1. mkdir dir tree ✅
2. Write pyproject.toml ✅
3. Write .gitignore ✅
4. Write STATE.md ✅
5. Write PHASE1.md (file này) ✅
6. uv sync — cài fastapi/uvicorn/watchfiles/sse-starlette/orjson
7. Verify imports: `uv run python -c "import fastapi, watchfiles, sse_starlette, orjson, uvicorn"`

## Verify command

```bash
cd "D:/Projects/Claude Cowork/CLAUDE OUTPUTS/code/claude-live-dashboard"
uv sync
uv run python -c "import fastapi, watchfiles, sse_starlette, orjson, uvicorn; print('phase 1 OK')"
```

Expected: `phase 1 OK`

## Verify artifact

- `.venv/` folder tồn tại
- `uv.lock` được tạo (gitignored)
- Import check print "phase 1 OK"
