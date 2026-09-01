"""Slice 0: ravand exists and unimplemented commands fail closed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ravand(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ravand", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_ravand_help_exits_zero() -> None:
    result = _ravand("--help")
    assert result.returncode == 0, result.stderr
    combined = (result.stdout + result.stderr).lower()
    assert "usage" in combined or "ravand" in combined


def test_ravand_which_is_not_implemented_yet() -> None:
    result = _ravand("which")
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "not implemented" in combined


def test_unknown_command_is_not_implemented() -> None:
    result = _ravand("run")
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "not implemented" in combined


def test_python_is_312_or_newer() -> None:
    assert sys.version_info >= (3, 12)
