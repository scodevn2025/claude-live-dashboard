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
        # Nếu set → watcher chỉ tail file này (user pin via dashboard click)
        self.pinned_session_file: str | None = None
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
        # Agent tree + background tasks + skill tally
        self.subagents: list[dict] = []       # [{id, name, type, status, started_at}]
        self.bg_tasks: list[dict] = []        # [{id, name, status, started_at, summary}]
        self.skill_tally: dict[str, int] = {} # skill_name → invocation count
        self.tool_tally: dict[str, int] = {}  # tool_name → count (for hot path)

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

        # Prune stale pending_tools (bug #7: memory leak) — keep 500 newest
        if len(self.pending_tools) > 500:
            # Drop oldest by started_at
            sorted_ids = sorted(self.pending_tools.items(), key=lambda x: x[1].get("ts", 0))
            for tid, _ in sorted_ids[:len(self.pending_tools) - 500]:
                self.pending_tools.pop(tid, None)

        if kind == "tool_use":
            self.counters["tool_calls"] += 1
            tid = event["payload"].get("tool_use_id")
            if tid:
                self.pending_tools[tid] = event
            name = event.get("name", "")
            self.tool_tally[name] = self.tool_tally.get(name, 0) + 1
            p = event.get("payload") or {}
            # Agent spawn → subagent + counter (bug #5)
            if name == "Agent":
                self.counters["agents_spawned"] += 1
                self.subagents.append({
                    "id": tid or event.get("id"),
                    "name": p.get("agent_name") or p.get("summary", "")[:30],
                    "type": p.get("subagent_type", "general"),
                    "status": "running",
                    "started_at": event["ts"],
                    "summary": p.get("summary", "")[:60],
                })
                if len(self.subagents) > 20:
                    self.subagents.pop(0)
            # Background Bash → bg task
            elif name == "Bash" and p.get("in_background"):
                self.bg_tasks.append({
                    "id": tid or event.get("id"),
                    "name": (p.get("summary", "") or "")[:40],
                    "status": "running",
                    "started_at": event["ts"],
                    "summary": p.get("summary", "")[:80],
                })
                if len(self.bg_tasks) > 20:
                    self.bg_tasks.pop(0)
            # Skill invocation
            elif name == "Skill":
                skill = p.get("skill", "unknown")
                self.skill_tally[skill] = self.skill_tally.get(skill, 0) + 1
        elif kind == "tool_result":
            tid = event["payload"].get("tool_use_id")
            if tid and tid in self.pending_tools:
                started = self.pending_tools.pop(tid)
                event["duration"] = round(event["ts"] - started["ts"], 2)
                event["name"] = started["name"]
                # Update subagent/bg task status khi done
                for sa in self.subagents:
                    if sa.get("id") == tid:
                        sa["status"] = "error" if event.get("status") == "error" else "done"
                        sa["duration"] = event["duration"]
                for bg in self.bg_tasks:
                    if bg.get("id") == tid:
                        bg["status"] = "error" if event.get("status") == "error" else "done"
                        bg["duration"] = event["duration"]
            if event.get("status") == "error":
                self.counters["errors"] += 1
        elif kind == "assistant_text":
            self.counters["assistant_turns"] += 1

        # Bug #3: capture context tokens từ MỌI event có usage (tool_use + assistant_text)
        # Vì assistant turn chứa tool_use không trigger assistant_text kind
        usage = (event.get("payload") or {}).get("usage") or {}
        if usage and usage.get("context", 0) > 0:
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
            "pinned": self.pinned_session_file is not None,
            "started_at": self.started_at,
            "uptime_s": round(time.time() - self.started_at),
            "counters": dict(self.counters),
            "context": dict(self.context),
            "subagents": list(self.subagents),
            "bg_tasks": list(self.bg_tasks),
            "skill_tally": dict(self.skill_tally),
            "tool_tally": dict(self.tool_tally),
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
        self.subagents.clear()
        self.bg_tasks.clear()
        self.skill_tally.clear()
        self.tool_tally.clear()
        for k in self.counters:
            self.counters[k] = 0
        for k in ("tokens", "input", "output_total", "cache_read", "cache_create", "thinking_total", "thinking_last"):
            self.context[k] = 0

    def recent(self, n: int = 50) -> list[dict]:
        return list(self.events)[-n:]
