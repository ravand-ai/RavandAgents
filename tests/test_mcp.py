"""Parse harness MCP servers into ResolvedPolicy (GitHub issue #97)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ravand_policy import PolicyDenied, resolve


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


def test_which_mcp_empty_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    policy = resolve(repo)
    assert policy.mcp == []
    result = _which(repo, home)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["mcp"] == []


def test_which_includes_mcp_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(
        repo,
        extra=(
            "[mcp]\n"
            'servers = [{ name = "insforge", command = ["npx", "@insforge/mcp"] }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    policy = resolve(repo)
    assert policy.mcp == [{"name": "insforge", "command": ["npx", "@insforge/mcp"]}]
    result = _which(repo, home)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["mcp"] == [{"name": "insforge", "command": ["npx", "@insforge/mcp"]}]


def test_mcp_not_a_table_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, extra="mcp = []\n")
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        resolve(repo)
    result = _which(repo, home)
    assert result.returncode == 3


def test_mcp_servers_not_a_list_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, extra='[mcp]\nservers = "insforge"\n')
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        resolve(repo)
    result = _which(repo, home)
    assert result.returncode == 3


def test_mcp_item_missing_command_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, extra='[mcp]\nservers = [{ name = "insforge" }]\n')
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        resolve(repo)
    result = _which(repo, home)
    assert result.returncode == 3
