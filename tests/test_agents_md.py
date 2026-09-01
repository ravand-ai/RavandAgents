"""Load repo AGENTS.md when agents_md is true (GitHub issue #99)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ravand_policy import PolicyDenied, resolve

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"
MARKER = "MARKER-AGENTS-MD-ATTACH"


def _write_harness(repo: Path, *, agents_md: str | None) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    fake = json.dumps([sys.executable, str(FAKE)])
    lines = [
        'profile = "work"',
        'default = "fake"',
        'overflow = ""',
        "deny = []",
        'permissions = "repo-only"',
        'classification = "internal"',
    ]
    if agents_md is not None:
        lines.append(f"agents_md = {agents_md}")
    lines.extend(
        [
            "",
            "[agents.fake]",
            f"command = {fake}",
            "",
        ]
    )
    (repo / "harness.toml").write_text("\n".join(lines), encoding="utf-8")
    (repo / "AGENTS.md").write_text(MARKER + "\n", encoding="utf-8")


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


def _run(cwd: Path, home: Path, prompt: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    return subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", prompt],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _events(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def test_which_agents_md_false_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, agents_md=None)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    policy = resolve(repo)
    assert policy.agents_md is False
    result = _which(repo, home)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["agentsMd"] is False


def test_which_agents_md_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, agents_md="true")
    monkeypatch.setenv("RAVAND_HOME", str(home))
    policy = resolve(repo)
    assert policy.agents_md is True
    result = _which(repo, home)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["agentsMd"] is True


def test_agents_md_invalid_shape_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    _write_harness(repo, agents_md='"yes"')
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        resolve(repo)
    result = _which(repo, home)
    assert result.returncode == 3


def test_run_does_not_read_agents_md_when_false(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _write_harness(repo, agents_md="false")
    result = _run(repo, home, "hello")
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert not any(e.get("text") == "agents-md-ok" for e in events)
    blob = result.stdout + result.stderr
    assert MARKER not in blob


def test_run_attaches_agents_md_when_true(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _write_harness(repo, agents_md="true")
    result = _run(repo, home, "hello")
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert any(e.get("text") == "agents-md-ok" for e in events)
    blob = result.stdout + result.stderr
    assert "sk-" not in blob
