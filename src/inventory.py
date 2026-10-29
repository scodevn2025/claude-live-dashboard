"""Inventory scanner — liệt kê MCP servers, plugins, skills + active sessions."""
from __future__ import annotations

import time
from pathlib import Path
import orjson

CLAUDE_HOME = Path.home() / ".claude"
CLAUDE_JSON = Path.home() / ".claude.json"


def list_skills() -> list[dict]:
    """Scan ~/.claude/skills/ — mỗi thư mục con là 1 skill."""
    skills_dir = CLAUDE_HOME / "skills"
    if not skills_dir.exists():
        return []
    out = []
    for item in sorted(skills_dir.iterdir()):
        if item.is_dir():
            # Try read description from SKILL.md frontmatter
            desc = ""
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                try:
                    text = skill_md.read_text(encoding="utf-8", errors="ignore")[:1000]
                    for line in text.splitlines():
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip('"').strip("'")[:100]
                            break
                except Exception:
                    pass
            out.append({"name": item.name, "description": desc, "source": "user"})
        elif item.suffix == ".md":
            out.append({"name": item.stem, "description": "", "source": "inline"})
    return out


def list_plugins() -> list[dict]:
    """Scan ~/.claude/plugins/installed_plugins.json.

    Schema v2 Claude Code (bug #3):
      {"version": 2, "plugins": {"<name>@<marketplace>": [{"scope","installPath","version","installedAt","gitCommitSha"}]}}
    """
    installed = CLAUDE_HOME / "plugins" / "installed_plugins.json"
    if not installed.exists():
        return []
    try:
        data = orjson.loads(installed.read_bytes())
        if not isinstance(data, dict):
            return []
        plugins = data.get("plugins", {})
        if not isinstance(plugins, dict):
            return []
        out = []
        for key, entries in plugins.items():
            # Split "name@marketplace"
            if "@" in key:
                name, marketplace = key.split("@", 1)
            else:
                name, marketplace = key, ""
            # Entries là list, lấy first (latest install)
            entry = {}
            if isinstance(entries, list) and entries:
                entry = entries[0] if isinstance(entries[0], dict) else {}
            elif isinstance(entries, dict):
                entry = entries
            out.append({
                "name": name,
                "version": entry.get("version", ""),
                "marketplace": marketplace,
                "scope": entry.get("scope", "user"),
            })
        return out
    except Exception:
        return []


def list_mcp_servers() -> list[dict]:
    """Scan ~/.claude.json cho mcpServers."""
    if not CLAUDE_JSON.exists():
        return []
    try:
        data = orjson.loads(CLAUDE_JSON.read_bytes())
        servers = data.get("mcpServers") or {}
        out = []
        for name, cfg in servers.items():
            cfg = cfg or {}
            kind = "stdio"
            if cfg.get("url") or cfg.get("type") == "http":
                kind = "http"
            elif cfg.get("type") == "sse":
                kind = "sse"
            out.append({
                "name": name,
                "kind": kind,
                "cmd": (cfg.get("command") or cfg.get("url", ""))[:60],
            })
        return out
    except Exception:
        return []


def _extract_session_name(jsonl: Path) -> str | None:
    """Scan first ~50 lines tìm custom-title event để lấy tên session."""
    try:
        with open(jsonl, "rb") as f:
            for i, line in enumerate(f):
                if i > 60:
                    break
                try:
                    obj = orjson.loads(line)
                    if obj.get("type") == "custom-title":
                        title = obj.get("customTitle")
                        if title:
                            return str(title)[:60]
                except Exception:
                    continue
    except Exception:
        pass
    return None


def list_active_sessions(limit: int = 30, window_s: int = 604800) -> list[dict]:
    """List Claude Code sessions có activity trong window (default 7 ngày).

    Returns sorted by mtime desc, each with name từ custom-title event.
    """
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return []
    now = time.time()
    out = []
    for jsonl in projects_dir.glob("*/*.jsonl"):
        try:
            stat = jsonl.stat()
            age = now - stat.st_mtime
            if age > window_s:
                continue
            name = _extract_session_name(jsonl) or jsonl.stem[:8]
            out.append({
                "id": jsonl.stem,
                "name": name,
                "project": jsonl.parent.name,
                "size_mb": round(stat.st_size / 1024 / 1024, 1),
                "mtime": stat.st_mtime,
                "age_s": int(age),
                "live": age < 60,       # updated < 1 min = live
                "recent": age < 300,    # < 5 min = recent
            })
        except Exception:
            continue
    out.sort(key=lambda s: s["mtime"], reverse=True)
    return out[:limit]


def check_tg_gateway() -> dict:
    """Check Telegram gateway status (plugin claudeScode_bot)."""
    tg_dir = Path.home().parent / "Scode" / ".claude" / "plugins" / "claude-tg-gateway"
    alt_dir = Path("D:/Projects/Claude Cowork/CLAUDE OUTPUTS/code/claude-tg-gateway")
    folder = tg_dir if tg_dir.exists() else (alt_dir if alt_dir.exists() else None)
    return {
        "installed": folder is not None,
        "folder": str(folder) if folder else None,
        "bot": "@claudeScode_bot",
        "note": "Plugin chạy embedded trong Claude Code, không expose HTTP endpoint riêng",
    }


def inventory() -> dict:
    """Full inventory snapshot + active sessions + telegram status."""
    skills = list_skills()
    plugins = list_plugins()
    mcps = list_mcp_servers()
    sessions = list_active_sessions()
    tg = check_tg_gateway()
    return {
        "skills": {"count": len(skills), "items": skills},
        "plugins": {"count": len(plugins), "items": plugins},
        "mcps": {"count": len(mcps), "items": mcps},
        "sessions": {"count": len(sessions), "items": sessions},
        "telegram": tg,
    }


if __name__ == "__main__":
    inv = inventory()
    print(f"Skills: {inv['skills']['count']}")
    for s in inv['skills'][:5]:
        print(f"  - {s}")
    print(f"\nPlugins: {inv['plugins']['count']}")
    print(f"\nMCP servers: {inv['mcps']['count']}")
    for m in inv['mcps']['items'][:10]:
        print(f"  - {m['name']} ({m['kind']})")
