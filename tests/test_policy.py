"""Slice 1 TDD: fail-closed policy and ravand which."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _write_harness(
    repo: Path,
    *,
    profile: str = "work",
    default: str = "grok",
    overflow: str = "kimi",
    deny: str = "[]",
    classification: str = "internal",
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                f'default = "{default}"',
                f'overflow = "{overflow}"',
                f"deny = {deny}",
                'permissions = "repo-only"',
                f'classification = "{classification}"',
                "",
                "[agents.grok]",
                'command = ["grok", "agent", "stdio"]',
                "",
                "[agents.kimi]",
                'command = ["kimi", "acp"]',
                "",
                "[agents.cursor]",
                'command = ["cursor-agent", "acp"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _which(
    cwd: Path, home: Path, extra: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    return subprocess.run(
        ["uv", "run", "ravand", "which", *(extra or [])],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_which_this_repo_is_work_grok_kimi_overflow(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    result = _which(ROOT, home)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["profile"] == "work"
    assert data["agent"] == "grok"
    assert data["overflow"] == "kimi"
    assert data["permissions"] == "repo-only"
    assert data["command"] == ["grok", "agent", "stdio"]
    assert data["home"].endswith("profiles/work")
    assert (home / "profiles" / "work").is_dir()


def test_personal_repo_work_override_denied(tmp_path: Path) -> None:
    repo = tmp_path / "personal"
    _write_harness(repo, profile="personal", default="kimi", overflow="")
    result = _which(repo, tmp_path / "home", extra=["--profile", "work"])
    assert result.returncode == 3
    assert "not implemented" not in (result.stdout + result.stderr).lower()


def test_customer_on_personal_denied(tmp_path: Path) -> None:
    repo = tmp_path / "cust"
    _write_harness(
        repo, profile="personal", default="kimi", classification="customer"
    )
    result = _which(repo, tmp_path / "home")
    assert result.returncode == 3


def test_unknown_agent_errors(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_harness(repo, default="nope")
    result = _which(repo, tmp_path / "home")
    assert result.returncode != 0
    assert result.returncode != 0


def test_deny_list_blocks_agent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_harness(repo, default="kimi", deny='["kimi"]')
    result = _which(repo, tmp_path / "home")
    assert result.returncode == 3


def test_login_prints_hints_not_secrets(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    result = subprocess.run(
        ["uv", "run", "ravand", "login", "work"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    text = (result.stdout + result.stderr).lower()
    assert result.returncode == 0, result.stderr
    assert "grok login" in text or "grok" in text
    assert "sk-" not in text
    assert "xai-" not in text
    assert "bearer" not in text


def test_login_prints_home_prefixed_vendor_and_gh(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_harness(repo)
    home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("RAVAND_HOME", None)
    result = subprocess.run(
        ["uv", "run", "ravand", "login", "work"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    profile_home = home / ".ravand" / "profiles" / "work"
    out = result.stdout
    assert f"HOME={profile_home} grok login" in out
    assert f"HOME={profile_home} kimi login" in out
    assert f"HOME={profile_home} cursor-agent" in out
    assert f"HOME={profile_home} gh auth login" in out
    gh_line = next(line for line in out.splitlines() if line.endswith("gh auth login"))
    agent_lines = [
        line
        for line in out.splitlines()
        if line.startswith(f"HOME={profile_home} ") and not line.endswith("gh auth login")
    ]
    assert agent_lines
    assert out.index(agent_lines[-1]) < out.index(gh_line)
    lowered = (out + result.stderr).lower()
    assert "sk-" not in lowered
    assert "xai-" not in lowered
    assert "bearer" not in lowered
