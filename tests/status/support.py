"""Invoke `ravand status` under an isolated HOME. Never open vendor cookie files."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_ravand_status(
    *,
    cwd: Path,
    home: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ravand", "status"],
        cwd=cwd,
        env={
            "HOME": str(home),
            "PATH": os.environ.get("PATH", ""),
        },
        capture_output=True,
        text=True,
        check=False,
    )


def combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}\n{result.stderr}"
