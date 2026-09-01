"""Plan mode: parse human from harness; gate writes/shell until plan.allow."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from ravand_policy import ResolvedPolicy

_WRITE_KINDS = frozenset({"edit", "write", "create", "delete", "patch"})
_SHELL_KINDS = frozenset({"execute", "shell", "bash", "terminal", "command"})


def load_human(cwd: Path) -> str | None:
    """Return harness ``human`` when set."""
    path = cwd / "harness.toml"
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        harness = tomllib.load(handle)
    human = harness.get("human")
    if human is None:
        return None
    return str(human)


def plan_mode_active(cwd: Path, policy: ResolvedPolicy) -> bool:
    """True when policy or harness selects plan mode."""
    human = getattr(policy, "human", None)
    if human is None:
        human = load_human(cwd)
    if human == "plan":
        return True
    return policy.permissions == "plan"


def is_write_or_shell(tool_call: dict[str, Any]) -> bool:
    """Return True for write or shell tool requests."""
    kind = str(tool_call.get("kind") or "").lower()
    if kind in _WRITE_KINDS or kind in _SHELL_KINDS:
        return True
    title = str(tool_call.get("title") or "").lower()
    if any(word in title for word in ("shell", "execute", "write", "edit")):
        return True
    raw = tool_call.get("rawInput") or {}
    if isinstance(raw, dict) and (raw.get("path") or raw.get("file")):
        return True
    return False
