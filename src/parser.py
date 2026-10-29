"""Event parser — raw JSONL object → normalized schema cho dashboard.

Normalized event:
    {
        "id":        str,            # uuid4 nếu không có
        "ts":        float,           # unix epoch
        "kind":      str,             # one of KIND_*
        "name":      str,             # tool name hoặc event sub-type
        "status":    str | None,      # pending/running/success/error
        "duration":  float | None,    # giây (nếu computable)
        "payload":   dict,            # raw event (debugging)
    }

Supported event kinds:
    user_msg          — user prompt tới Claude
    assistant_text    — assistant response text (không tool call)
    tool_use          — assistant invoke tool
    tool_result       — tool trả result (match với tool_use qua tool_use_id)
    agent_spawn       — SubAgent được spawn
    agent_result      — SubAgent xong
    api_request       — API call ra Claude backend (metrics)
    system            — system reminder, mode, chapter, etc.
    unknown           — fallback
"""
from __future__ import annotations

import time
import uuid
from typing import Any


KIND_USER = "user_msg"
KIND_ASSISTANT_TEXT = "assistant_text"
KIND_TOOL_USE = "tool_use"
KIND_TOOL_RESULT = "tool_result"
KIND_AGENT_SPAWN = "agent_spawn"
KIND_AGENT_RESULT = "agent_result"
KIND_API_REQUEST = "api_request"
KIND_SYSTEM = "system"
KIND_UNKNOWN = "unknown"


def _parse_ts(obj: dict) -> float:
    """Extract timestamp — fallback now()."""
    ts = obj.get("timestamp") or obj.get("ts")
    if isinstance(ts, (int, float)):
        return float(ts) / 1000 if ts > 1e12 else float(ts)
    if isinstance(ts, str):
        try:
            import datetime
            return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            pass
    return time.time()


def _norm(kind: str, name: str = "", status: str | None = None,
          duration: float | None = None, payload: dict | None = None,
          ts: float | None = None, event_id: str | None = None) -> dict:
    return {
        "id": event_id or str(uuid.uuid4())[:8],
        "ts": ts or time.time(),
        "kind": kind,
        "name": name,
        "status": status,
        "duration": duration,
        "payload": payload or {},
    }


def parse_event(obj: dict) -> list[dict]:
    """Convert raw JSONL object → 0..N normalized events.

    1 raw assistant turn có thể chứa nhiều tool_use trong content[] → emit nhiều events.
    """
    etype = obj.get("type", "")
    ts = _parse_ts(obj)
    eid = obj.get("uuid") or obj.get("id")

    if etype == "user":
        return _parse_user(obj, ts, eid)
    if etype == "assistant":
        return _parse_assistant(obj, ts, eid)
    if etype in ("agent-spawn", "subagent_spawn"):
        name = obj.get("agent_type") or obj.get("name") or "agent"
        return [_norm(KIND_AGENT_SPAWN, name, status="running",
                      payload={"description": obj.get("description")}, ts=ts, event_id=eid)]
    if etype in ("agent-result", "subagent_stop"):
        name = obj.get("agent_type") or obj.get("name") or "agent"
        return [_norm(KIND_AGENT_RESULT, name, status=obj.get("status", "success"),
                      duration=obj.get("duration_ms", 0) / 1000 if obj.get("duration_ms") else None,
                      payload={}, ts=ts, event_id=eid)]
    if etype in ("api-request", "api-request-blob"):
        return [_norm(KIND_API_REQUEST, etype, payload={}, ts=ts, event_id=eid)]
    if etype in ("system", "mode", "chapter", "agent-name", "atis-latch", "attachment", "task-notification"):
        return [_norm(KIND_SYSTEM, etype, payload={}, ts=ts, event_id=eid)]

    return [_norm(KIND_UNKNOWN, etype or "unknown", payload=obj, ts=ts, event_id=eid)]


def _parse_user(obj: dict, ts: float, eid: str | None) -> list[dict]:
    msg = obj.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        # Nếu có tool_result → emit tool_result event
        events: list[dict] = []
        text_blocks = 0
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_result":
                tool_id = block.get("tool_use_id", "")
                is_error = block.get("is_error", False)
                events.append(_norm(
                    KIND_TOOL_RESULT, tool_id[:8],
                    status="error" if is_error else "success",
                    payload={"tool_use_id": tool_id, "is_error": is_error},
                    ts=ts, event_id=eid,
                ))
            elif btype == "text":
                text_blocks += 1
        if events:
            return events
        if text_blocks:
            return [_norm(KIND_USER, "", payload={}, ts=ts, event_id=eid)]
    return [_norm(KIND_USER, "", payload={}, ts=ts, event_id=eid)]


def _parse_assistant(obj: dict, ts: float, eid: str | None) -> list[dict]:
    msg = obj.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return [_norm(KIND_ASSISTANT_TEXT, "", payload={}, ts=ts, event_id=eid)]

    # Extract usage tokens từ Claude API response
    usage = msg.get("usage") or {}
    usage_summary = {}
    if usage:
        input_t = usage.get("input_tokens", 0)
        cache_create = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        output_t = usage.get("output_tokens", 0)
        usage_summary = {
            "input": input_t, "output": output_t,
            "cache_read": cache_read, "cache_create": cache_create,
            # Context size = tổng tất cả tokens của turn này
            "context": input_t + cache_create + cache_read,
        }

    events: list[dict] = []
    text_chars = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "tool_use":
            tool_name = block.get("name", "unknown")
            tool_id = block.get("id", "")
            tool_input = block.get("input", {}) or {}
            summary = _summarize_tool_input(tool_name, tool_input)
            events.append(_norm(
                KIND_TOOL_USE, tool_name,
                status="running",
                payload={"tool_use_id": tool_id, "summary": summary, "input_keys": list(tool_input.keys())[:5],
                         "usage": usage_summary} if usage_summary else {"tool_use_id": tool_id, "summary": summary, "input_keys": list(tool_input.keys())[:5]},
                ts=ts, event_id=tool_id[:8] if tool_id else eid,
            ))
        elif btype == "text":
            text_chars += len(block.get("text", ""))
    if text_chars > 0:
        events.append(_norm(KIND_ASSISTANT_TEXT, "", payload={"chars": text_chars, "usage": usage_summary}, ts=ts, event_id=eid))
    if not events:
        events.append(_norm(KIND_ASSISTANT_TEXT, "", payload={"usage": usage_summary}, ts=ts, event_id=eid))
    return events


def _summarize_tool_input(tool: str, inp: dict) -> str:
    """Short display label cho timeline."""
    if tool == "Bash":
        cmd = (inp.get("command") or "")[:80]
        return cmd
    if tool in ("Read", "Edit", "Write"):
        return inp.get("file_path", "")
    if tool in ("Grep", "Glob"):
        return inp.get("pattern") or inp.get("glob") or ""
    if tool == "Agent":
        return inp.get("description") or inp.get("subagent_type", "")
    if tool.startswith("mcp__"):
        return tool.split("__", 2)[-1] if "__" in tool else tool
    return str(inp.get("prompt", ""))[:60] if isinstance(inp.get("prompt"), str) else ""


if __name__ == "__main__":
    import asyncio
    from .watcher import find_active_session, _read_new_lines

    sess = find_active_session()
    size = sess.stat().st_size
    offset = max(0, size - 50000)
    raw, _ = _read_new_lines(sess, offset)
    print(f"[+] Parsing {len(raw)} raw events từ {sess.name}")
    counts: dict[str, int] = {}
    for obj in raw:
        for ev in parse_event(obj):
            counts[ev["kind"]] = counts.get(ev["kind"], 0) + 1
    print(f"[+] Normalized event kinds:")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {k:20} {v}")
