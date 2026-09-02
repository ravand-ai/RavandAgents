"""ravand init writes ./harness.toml. Issue #162."""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "examples" / "harness.toml"


def run_ravand(
    *args: str,
    cwd: Path,
    home: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ravand", *args],
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


def test_init_writes_eight_key_harness(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    result = run_ravand("init", cwd=repo, home=home)
    assert result.returncode == 0, combined_output(result)
    dest = repo / "harness.toml"
    assert dest.is_file()
    with dest.open("rb") as handle:
        data = tomllib.load(handle)
    with EXAMPLE.open("rb") as handle:
        example = tomllib.load(handle)
    assert data["profile"] == "work"
    assert data["default"] == "grok"
    assert data["overflow"] == "kimi"
    assert data["deny"] == []
    assert data["permissions"] == "repo-only"
    assert data["classification"] == "internal"
    assert "preset" not in data
    for agent_id in ("grok", "kimi", "claude", "cursor"):
        assert data["agents"][agent_id]["command"] == example["agents"][agent_id]["command"]
    text = dest.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "sk-" not in text
    assert "xai-" not in text
    assert "bearer" not in lowered
    assert "cookie" not in lowered
    assert "~/.ravand" not in text
    assert "/.ravand/" not in text


def test_init_does_not_overwrite_existing_harness(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    dest = repo / "harness.toml"
    original = 'profile = "personal"\n'
    dest.write_text(original, encoding="utf-8")
    result = run_ravand("init", cwd=repo, home=home)
    assert result.returncode == 3
    assert result.stderr.strip()
    assert dest.read_text(encoding="utf-8") == original


def test_which_after_init_is_work_grok(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    init = run_ravand("init", cwd=repo, home=home)
    assert init.returncode == 0, combined_output(init)
    result = run_ravand("which", cwd=repo, home=home)
    assert result.returncode == 0, combined_output(result)
    data = json.loads(result.stdout)
    assert data["profile"] == "work"
    assert data["agent"] == "grok"
    expected = home / ".ravand" / "profiles" / "work"
    assert Path(data["home"]) == expected


def test_which_without_harness_tells_human_to_run_init(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    result = run_ravand("which", cwd=repo, home=home)
    assert result.returncode != 0
    assert "ravand init" in combined_output(result)


def test_login_without_harness_tells_human_to_run_init(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    result = run_ravand("login", cwd=repo, home=home)
    assert result.returncode != 0
    assert "ravand init" in combined_output(result)


def test_login_work_without_harness_tells_human_to_run_init(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    result = run_ravand("login", "work", cwd=repo, home=home)
    assert result.returncode != 0
    text = combined_output(result)
    assert "ravand init" in text
    assert "does not match repo" not in text
