"""Profile HOME dirs. Never copy vendor cookies."""

from __future__ import annotations

from pathlib import Path


def ensure_profile_home(home: str | Path) -> Path:
    path = Path(home)
    path.mkdir(parents=True, exist_ok=True)
    return path
