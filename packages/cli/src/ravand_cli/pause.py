"""Pause flag under ~/.ravand: fail-close new runs for an agent+profile pair."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from ravand_audit import AuditLog
from ravand_policy import PolicyDenied, ravand_home

_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def _require_id(value: str, *, kind: str) -> str:
    name = value.strip()
    if not name or not _SAFE.fullmatch(name):
        raise PolicyDenied(f"{kind} is invalid")
    return name


def pause_path(agent: str, profile: str, *, root: Path | None = None) -> Path:
    """Marker path: ~/.ravand/paused/<profile>/<agent>."""
    home = root if root is not None else ravand_home()
    return home / "paused" / profile / agent


def is_paused(agent: str, profile: str, *, root: Path | None = None) -> bool:
    """True when the agent+profile pair has a pause marker."""
    try:
        agent_id = _require_id(agent, kind="agent")
        profile_id = _require_id(profile, kind="profile")
    except PolicyDenied:
        return False
    return pause_path(agent_id, profile_id, root=root).is_file()


def require_not_paused(agent: str, profile: str, *, root: Path | None = None) -> None:
    """Fail closed if the pair is paused."""
    if is_paused(agent, profile, root=root):
        raise PolicyDenied(
            f"agent {agent!r} profile {profile!r} is paused"
        )


def set_pause(agent: str, profile: str, *, root: Path | None = None) -> Path:
    """Write the pause marker and audit agent.paused. Resume is a later issue."""
    agent_id = _require_id(agent, kind="agent")
    profile_id = _require_id(profile, kind="profile")
    home = root if root is not None else ravand_home()
    marker = pause_path(agent_id, profile_id, root=home)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")
    AuditLog(home).emit(
        "agent.paused",
        task_id=str(uuid.uuid4()),
        profile=profile_id,
        agent=agent_id,
        detail="pause",
    )
    return marker
