"""JSONL watcher — tail session transcript, yield new events.

Claude Code lưu session events vào ~/.claude/projects/<slug>/<uuid>.jsonl
mỗi tool_use, assistant turn, user message = 1 line JSON. Append-only.

Logic:
    find_active_session() picks jsonl có mtime mới nhất (= session đang chạy)
    tail_file() yield từng JSON object khi line mới xuất hiện

Standalone test:
    uv run python -m src.watcher
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncIterator

import orjson
from watchfiles import awatch

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def find_active_session() -> Path | None:
    """Pick most recently modified .jsonl across all project folders."""
    if not CLAUDE_PROJECTS_DIR.exists():
        return None
    candidates = list(CLAUDE_PROJECTS_DIR.glob("*/*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def list_sessions() -> list[Path]:
    """List all session jsonl, newest first."""
    if not CLAUDE_PROJECTS_DIR.exists():
        return []
    return sorted(
        CLAUDE_PROJECTS_DIR.glob("*/*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _read_new_lines(path: Path, offset: int) -> tuple[list[dict], int]:
    """Read COMPLETE lines từ offset, giữ partial tail cho lần đọc sau (bug #1).

    Chỉ advance offset tới newline cuối cùng — partial line không bị skip.
    """
    objs: list[dict] = []
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            buf = f.read()
            if not buf:
                return objs, offset
            last_nl = buf.rfind(b"\n")
            if last_nl < 0:
                # Chưa có line hoàn chỉnh nào — giữ offset nguyên
                return objs, offset
            complete = buf[:last_nl + 1]
            offset += len(complete)
            for line in complete.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    objs.append(orjson.loads(stripped))
                except ValueError:
                    continue
    except FileNotFoundError:
        pass
    return objs, offset


async def tail_file(path: Path, start_offset: int = 0) -> AsyncIterator[dict]:
    """Yield JSON events from path as new lines append."""
    offset = start_offset

    # Catch-up: read anything already past offset
    existing, offset = _read_new_lines(path, offset)
    for obj in existing:
        yield obj

    # Watch dir for file changes
    async for changes in awatch(path.parent, recursive=False):
        touched = any(os.path.normcase(str(path)) == os.path.normcase(c[1]) for c in changes)
        if not touched:
            continue
        new_objs, offset = _read_new_lines(path, offset)
        for obj in new_objs:
            yield obj


def _event_label(obj: dict) -> str:
    """Compact one-line description for CLI test output."""
    kind = obj.get("type", "?")
    msg = obj.get("message") or {}
    content = msg.get("content") or []
    if kind == "user":
        if isinstance(content, list):
            tool_results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
            if tool_results:
                return f"tool_result ({len(tool_results)})"
        return "user_msg"
    if kind == "assistant":
        tools = [b.get("name") for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
        if tools:
            return f"assistant tool_use={tools}"
        return "assistant text"
    return kind


async def _demo() -> None:
    sess = find_active_session()
    if not sess:
        print("[!] No active session file found")
        return
    size = sess.stat().st_size
    print(f"[+] Tailing {sess.name}")
    print(f"[+] Project: {sess.parent.name}")
    print(f"[+] Starting from offset {size:,} bytes (skipping existing)")
    print(f"[+] Waiting for new events... (Ctrl+C to stop)")
    print()
    try:
        async for obj in tail_file(sess, start_offset=size):
            print(f"  → {_event_label(obj)}")
    except KeyboardInterrupt:
        print("\n[+] Stopped")


if __name__ == "__main__":
    try:
        asyncio.run(_demo())
    except KeyboardInterrupt:
        sys.exit(0)
