"""Steer: ravand steer <sessionId> text continues a session via session/prompt."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"
FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


def _harness(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    fake = json.dumps([sys.executable, str(FAKE)])
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                'profile = "work"',
                'default = "fake"',
                'overflow = ""',
                "deny = []",
                'permissions = "repo-only"',
                'classification = "internal"',
                "",
                "[agents.fake]",
                f"command = {fake}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _run(repo: Path, home: Path, prompt: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    env.update(extra_env or {})
    return subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", prompt],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _steer(
    repo: Path,
    home: Path,
    session_id: str,
    text: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    env.update(extra_env or {})
    return subprocess.run(
        ["uv", "run", "ravand", "steer", session_id, text],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _events(stdout: str) -> list[dict]:
    return [json.loads(ln) for ln in stdout.splitlines() if ln.strip()]


def _prompt_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_steer_sends_second_session_prompt_and_audits(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    prompt_log = tmp_path / "prompts.jsonl"
    _harness(repo)
    env = {"FAKE_ACP_PROMPT_LOG": str(prompt_log)}

    first = _run(repo, home, "say hi", env)
    assert first.returncode == 0, first.stderr

    sessions = list((home / "sessions").glob("*.json"))
    assert len(sessions) == 1
    session = json.loads(sessions[0].read_text(encoding="utf-8"))
    session_id = session["id"]
    assert session.get("acpSessionId") == "sess-test"

    prompts = _prompt_log(prompt_log)
    assert len(prompts) == 1

    second = _steer(repo, home, session_id, "please continue", env)
    assert second.returncode == 0, second.stderr

    prompts = _prompt_log(prompt_log)
    assert len(prompts) == 2, prompts
    steer_prompt = prompts[1]
    assert "please continue" in json.dumps(steer_prompt)

    steer_events = _events(second.stdout)
    assert any(e.get("type") == "steer.accepted" for e in steer_events)
    assert any(e.get("type") == "text.delta" for e in steer_events)
    assert any(e.get("text") == "steer-ok" for e in steer_events)

    audit_path = home / "audit.jsonl"
    audit_events = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(e["type"] == "steer.accepted" for e in audit_events)

    blob = second.stdout + second.stderr + audit_path.read_text(encoding="utf-8")
    for marker in FORBIDDEN:
        assert marker not in blob


def test_steer_unknown_session_fails_closed_no_spawn(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    marker = tmp_path / "spawned-on-unknown-steer"
    result = _steer(
        repo,
        home,
        "00000000-0000-0000-0000-000000000000",
        "nope",
        {"FAKE_ACP_STATE": str(marker)},
    )
    assert result.returncode != 0, result.stderr
    assert not marker.exists()
    assert not list((home / "sessions").glob("*.json"))
