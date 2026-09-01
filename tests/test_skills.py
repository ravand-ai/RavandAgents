"""Parse harness [skills] allow into ResolvedPolicy (GitHub issue #98)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ravand_policy import PolicyDenied, require_skill, resolve


def _write_harness(repo: Path, extra: str = "") -> None:
    repo.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        [
            'profile = "work"',
            'default = "grok"',
            'overflow = ""',
            "deny = []",
            'permissions = "repo-only"',
            'classification = "internal"',
            extra,
            "",
            "[agents.grok]",
            'command = ["grok", "agent", "stdio"]',
            "",
        ]
    )
    (repo / "harness.toml").write_text(text, encoding="utf-8")


def _which(cwd: Path, home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    return subprocess.run(
        ["uv", "run", "ravand", "which"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_which_skills_allow_empty_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    policy = resolve(repo)
    assert policy.skills_allow == []
    result = _which(repo, home)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["skillsAllow"] == []


def test_which_includes_skills_allow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, extra='[skills]\nallow = ["review-diff"]\n')
    monkeypatch.setenv("RAVAND_HOME", str(home))
    policy = resolve(repo)
    assert policy.skills_allow == ["review-diff"]
    result = _which(repo, home)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["skillsAllow"] == ["review-diff"]


def test_skills_empty_allow_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, extra="[skills]\nallow = []\n")
    monkeypatch.setenv("RAVAND_HOME", str(home))
    policy = resolve(repo)
    assert policy.skills_allow == []
    result = _which(repo, home)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["skillsAllow"] == []


def test_skills_not_a_table_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, extra="skills = []\n")
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        resolve(repo)
    result = _which(repo, home)
    assert result.returncode == 3


def test_skills_allow_not_a_list_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, extra='[skills]\nallow = "review-diff"\n')
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        resolve(repo)
    result = _which(repo, home)
    assert result.returncode == 3


def test_unknown_skill_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, extra='[skills]\nallow = ["review-diff"]\n')
    monkeypatch.setenv("RAVAND_HOME", str(home))
    policy = resolve(repo)
    require_skill(policy, "review-diff")
    with pytest.raises(PolicyDenied):
        require_skill(policy, "unknown-skill")
