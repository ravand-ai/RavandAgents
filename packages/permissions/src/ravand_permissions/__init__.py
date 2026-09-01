"""Permission broker. repo-only v0."""

from __future__ import annotations

from typing import Any


def decide_repo_only(tool_call: dict[str, Any], cwd: str) -> str:
    raw = tool_call.get("rawInput") or {}
    path = str(raw.get("path") or raw.get("file") or "")
    if path.startswith("/etc/") or path == "/etc/passwd":
        return "deny"
    if path and not path.startswith(cwd):
        if not path.startswith("./") and path.startswith("/"):
            return "deny"
    return "allow"
