"""In-memory session state — snapshot cho dashboard."""
from __future__ import annotations

import time
from collections import deque
from typing import Any


class SessionState:
    """Rolling window state cho 1 Claude Code session."""

    def __init__(self, max_events: int = 200):
        self.session_file: str | None = None
        self.session_id: str | None = None
        self.started_at: float = time.time()
        self.events: deque[dict] = deque(maxlen=max_events)
        # Pending tool_use_id → tool_use event (match với tool_result sau)
        self.pending_tools: dict[str, dict] = {}
        self.counters: dict[str, int] = {
            "tool_calls": 0,
            "agents_spawned": 0,
            "assistant_turns": 0,
            "user_msgs": 0,
            "errors": 0,
        }
        # Context window usage từ assistant message.usage
        self.context: dict[str, int] = {
            "tokens": 0,          # tổng context lúc assistant trả lời gần nhất
            "input": 0,
            "output_total": 0,     # cumulative output
            "cache_read": 0,       # tổng cache read lúc gần nhất
            "cache_create": 0,
            "thinking_total": 0,   # cumulative thinking tokens (extended thinking)
            "thinking_last": 0,    # thinking tokens turn gần nhất
            "max_tokens": 200000,  # Claude context limit
        }

    def apply(self, event: dict) -> None:
        """Ingest 1 normalized event."""
        kind = event["kind"]
        self.events.append(event)

        if kind == "tool_use":
            self.counters["tool_calls"] += 1
            tid = event["payload"].get("tool_use_id")
            if tid:
                self.pending_tools[tid] = event
        elif kind == "tool_result":
            tid = event["payload"].get("tool_use_id")
            if tid and tid in self.pending_tools:
                started = self.pending_tools.pop(tid)
                event["duration"] = round(event["ts"] - started["ts"], 2)
                event["name"] = started["name"]
            if event.get("status") == "error":
                self.counters["errors"] += 1
        elif kind == "assistant_text":
            self.counters["assistant_turns"] += 1
            # Capture context tokens từ usage của assistant turn mới nhất
            usage = event.get("payload", {}).get("usage") or {}
            if usage:
                self.context["tokens"] = usage.get("context", 0)
                self.context["input"] = usage.get("input", 0)
                self.context["cache_read"] = usage.get("cache_read", 0)
                self.context["cache_create"] = usage.get("cache_create", 0)
                self.context["output_total"] += usage.get("output", 0)
                th = usage.get("thinking", 0)
                self.context["thinking_last"] = th
                self.context["thinking_total"] += th
        elif kind == "user_msg":
            self.counters["user_msgs"] += 1
        elif kind == "agent_spawn":
            self.counters["agents_spawned"] += 1

    def snapshot(self) -> dict[str, Any]:
        """Full state cho /api/snapshot."""
        return {
            "session_file": self.session_file,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "uptime_s": round(time.time() - self.started_at),
            "counters": dict(self.counters),
            "context": dict(self.context),
            "events": list(self.events),
            "pending_tools": {
                tid: {"name": t["name"], "ts": t["ts"]}
                for tid, t in self.pending_tools.items()
            },
        }

    def reset_session(self, session_file: str, session_id: str) -> None:
        """Reset state khi session file đổi (user mở session mới)."""
        self.session_file = session_file
        self.session_id = session_id
        self.started_at = time.time()
        self.events.clear()
        self.pending_tools.clear()
        for k in self.counters:
            self.counters[k] = 0
        for k in ("tokens", "input", "output_total", "cache_read", "cache_create", "thinking_total", "thinking_last"):
            self.context[k] = 0

    def recent(self, n: int = 50) -> list[dict]:
        return list(self.events)[-n:]
