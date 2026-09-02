"""ravand pause --agent X --profile work fail-closes new runs (GitHub issue #145)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"
FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


def _harness(repo: Path, *, profile: str = "work", agent: str = "fake") -> None:
    repo.mkdir(parents=True, exist_ok=True)
    fake = json.dumps([sys.executable, str(FAKE)])
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                f'default = "{agent}"',
                'overflow = ""',
                "deny = []",
                'permissions = "repo-only"',
                'classification = "internal"',
                "",
                f"[agents.{agent}]",
                f"command = {fake}",
                "",
                "[agents.other]",
                f"command = {fake}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    return env


def _pause(
    repo: Path,
    home: Path,
    *,
    agent: str,
    profile: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ravand", "pause", "--agent", agent, "--profile", profile],
        cwd=repo,
        env=_env(home),
        capture_output=True,
        text=True,
        check=False,
    )


def _run(
    repo: Path,
    home: Path,
    prompt: str,
    *,
    agent: str | None = None,
) -> subprocess.CompletedProcess[str]:
    args = ["uv", "run", "ravand", "run", "--format", "jsonl"]
    if agent is not None:
        args.extend(["--agent", agent])
    args.append(prompt)
    return subprocess.run(
        args,
        cwd=repo,
        env=_env(home),
        capture_output=True,
        text=True,
        check=False,
    )


def _audit_events(home: Path) -> list[dict[str, object]]:
    path = home / "audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_pause_writes_flag_and_audits(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)

    result = _pause(repo, home, agent="fake", profile="work")
    assert result.returncode == 0, result.stderr

    paused = home / "paused" / "work" / "fake"
    assert paused.is_file()

    events = _audit_events(home)
    assert any(e.get("type") == "agent.paused" for e in events)
    paused_event = next(e for e in events if e.get("type") == "agent.paused")
    assert paused_event.get("agent") == "fake"
    assert paused_event.get("profile") == "work"
    blob = (home / "audit.jsonl").read_text(encoding="utf-8")
    for marker in FORBIDDEN:
        assert marker not in blob


def test_paused_pair_fail_closes_new_run(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)

    ok = _run(repo, home, "before pause")
    assert ok.returncode == 0, ok.stderr

    paused = _pause(repo, home, agent="fake", profile="work")
    assert paused.returncode == 0, paused.stderr

    blocked = _run(repo, home, "after pause")
    assert blocked.returncode == 3, blocked.stderr
    combined = (blocked.stdout + blocked.stderr).lower()
    assert "pause" in combined

    events = _audit_events(home)
    assert any(e.get("type") == "agent.paused" for e in events)
    denied = [e for e in events if e.get("type") == "agent.denied"]
    assert denied
    assert any("pause" in str(e.get("detail", "")).lower() for e in denied)


def test_pause_is_scoped_to_agent_profile_pair(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)

    paused = _pause(repo, home, agent="fake", profile="work")
    assert paused.returncode == 0, paused.stderr

    other = _run(repo, home, "other agent ok", agent="other")
    assert other.returncode == 0, other.stderr

    same = _run(repo, home, "same pair blocked")
    assert same.returncode == 3, same.stderr


def test_pause_requires_agent_and_profile(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)

    missing_agent = subprocess.run(
        ["uv", "run", "ravand", "pause", "--profile", "work"],
        cwd=repo,
        env=_env(home),
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing_agent.returncode != 0

    missing_profile = subprocess.run(
        ["uv", "run", "ravand", "pause", "--agent", "fake"],
        cwd=repo,
        env=_env(home),
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing_profile.returncode != 0
