"""Slice 4 TDD: overflow to second agent on rate_limit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RATE_LIMIT = ROOT / "tests" / "support" / "fake_acp_rate_limit_agent.py"
OVERFLOW = ROOT / "tests" / "support" / "fake_acp_overflow_agent.py"


def _harness(repo: Path, *, overflow: str = '"overflow"', deny: str = "[]") -> None:
    repo.mkdir(parents=True, exist_ok=True)
    primary = json.dumps([sys.executable, str(RATE_LIMIT)])
    overflow_cmd = json.dumps([sys.executable, str(OVERFLOW)])
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                'profile = "work"',
                'default = "primary"',
                f"overflow = {overflow}",
                f"deny = {deny}",
                'permissions = "repo-only"',
                'classification = "internal"',
                "",
                "[agents.primary]",
                f"command = {primary}",
                "",
                "[agents.overflow]",
                f"command = {overflow_cmd}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _run(repo: Path, home: Path, prompt: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    return subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", prompt],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _events(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def test_overflow_on_rate_limit_calls_second_agent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(repo, home, "say hi")
    assert result.returncode == 0, result.stderr

    sessions = sorted(
        (home / "sessions").glob("*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    assert len(sessions) == 2
    primary = json.loads(sessions[0].read_text(encoding="utf-8"))
    overflow = json.loads(sessions[1].read_text(encoding="utf-8"))
    assert overflow["overflowOf"] == primary["id"]
    assert overflow["agent"] == "overflow"
    assert overflow["status"] == "ok"
    assert primary["taskId"] == overflow["taskId"]

    audit_types = [
        json.loads(line)["type"]
        for line in (home / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "agent.overflow" in audit_types

    events = _events(result.stdout)
    assert any(event.get("text") == "hello-from-overflow" for event in events)


def _session_files(home: Path) -> list[Path]:
    sessions_dir = home / "sessions"
    if not sessions_dir.is_dir():
        return []
    return list(sessions_dir.glob("*.json"))


def _audit_types(home: Path) -> list[str]:
    audit = home / "audit.jsonl"
    if not audit.is_file():
        return []
    return [
        json.loads(line)["type"]
        for line in audit.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_overflow_in_deny_list_does_not_spawn_second_agent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, deny='["overflow"]')
    result = _run(repo, home, "say hi")
    assert result.returncode == 5, result.stderr
    assert len(_session_files(home)) == 1
    assert "agent.overflow" not in _audit_types(home)
    events = _events(result.stdout)
    assert not any(event.get("text") == "hello-from-overflow" for event in events)


def test_missing_overflow_does_not_spawn_second_agent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, overflow='""')
    result = _run(repo, home, "say hi")
    assert result.returncode == 5, result.stderr
    assert len(_session_files(home)) == 1
    assert "agent.overflow" not in _audit_types(home)
