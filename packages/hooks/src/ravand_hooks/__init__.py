"""Hook runners: tool.pre executes a hook command and fails closed."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path

HookDecision = str  # "allow" | "deny"

_SECRET_NAME_MARKERS = ("TOKEN", "SECRET", "KEY")
_SECRET_VALUE_MARKERS = ("sk-", "xai-", "Bearer")


def _looks_secret(name: str, value: str) -> bool:
    upper = name.upper()
    if any(marker in upper for marker in _SECRET_NAME_MARKERS):
        return True
    return any(marker in value for marker in _SECRET_VALUE_MARKERS)


def _clean_env(env: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in env.items() if not _looks_secret(k, v)}


def run_tool_pre(
    command: list[str],
    cwd: Path | str,
    env: Mapping[str, str],
) -> HookDecision:
    """Run a tool.pre hook command.

    Returns "allow" when the hook exits 0, "deny" otherwise.
    Fails closed: a missing executable or any spawn error denies.
    The hook env is a copy of ``env`` with secret-looking keys dropped.
    """
    if not command:
        return "deny"
    try:
        result = subprocess.run(  # argv list, never a shell string
            command,
            cwd=cwd,
            env=_clean_env(env),
            capture_output=True,
        )
    except (OSError, ValueError):
        return "deny"
    return "allow" if result.returncode == 0 else "deny"
