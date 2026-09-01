"""Parse harness.toml hooks in the runtime (not policy)."""

from __future__ import annotations

import tomllib
from pathlib import Path


def load_tool_pre_command(cwd: Path) -> list[str] | None:
    """Return the argv list for the first ``tool.pre`` hook, or None if unset."""
    path = cwd / "harness.toml"
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        harness = tomllib.load(handle)
    hooks = harness.get("hooks")
    if not isinstance(hooks, list):
        return None
    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        if hook.get("on") != "tool.pre":
            continue
        command = hook.get("command")
        if isinstance(command, list) and all(isinstance(part, str) for part in command):
            return command
        return []
    return None
