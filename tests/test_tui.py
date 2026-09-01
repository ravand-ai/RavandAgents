"""ravand tui: operator screen. Non-TTY must refuse."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ravand(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TERM"] = "dumb"
    return subprocess.run(
        ["uv", "run", "ravand", *args],
        cwd=ROOT,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_tui_non_tty_exits_nonzero() -> None:
    result = _ravand("tui")
    assert result.returncode != 0
    blob = (result.stdout + result.stderr).lower()
    assert "tty" in blob
    assert "jsonl" in blob


def test_help_lists_tui() -> None:
    result = _ravand("--help")
    assert result.returncode == 0
    assert "tui" in (result.stdout + result.stderr).lower()
