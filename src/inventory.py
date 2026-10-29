"""Inventory scanner — liệt kê MCP servers, plugins, skills đã cài trong Claude Code."""
from __future__ import annotations

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
    """Scan ~/.claude/plugins/installed_plugins.json."""
    installed = CLAUDE_HOME / "plugins" / "installed_plugins.json"
    if not installed.exists():
        return []
    try:
        data = orjson.loads(installed.read_bytes())
        if isinstance(data, dict):
            # Format: {"plugin-name": {...meta...}}
            out = []
            for name, meta in data.items():
                out.append({
                    "name": name,
                    "version": (meta or {}).get("version", ""),
                    "marketplace": (meta or {}).get("marketplace", ""),
                })
            return out
        if isinstance(data, list):
            return [{"name": p.get("name", "?"), "version": p.get("version", "")} for p in data]
    except Exception:
        pass
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


def inventory() -> dict:
    """Full inventory snapshot."""
    skills = list_skills()
    plugins = list_plugins()
    mcps = list_mcp_servers()
    return {
        "skills": {"count": len(skills), "items": skills},
        "plugins": {"count": len(plugins), "items": plugins},
        "mcps": {"count": len(mcps), "items": mcps},
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
