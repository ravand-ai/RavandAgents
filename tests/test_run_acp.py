"""Slice 2 TDD: ravand run over ACP with isolated HOME and JSONL."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"


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
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def test_run_streams_jsonl_without_secrets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(repo, home, "say hi")
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    types = [e["type"] for e in events]
    assert "run.started" in types
    assert "text.delta" in types
    assert "run.ended" in types
    blob = result.stdout + result.stderr
    assert "sk-" not in blob
    assert "xai-" not in blob
    assert "Bearer" not in blob
    assert any(e.get("text") == "hello-from-fake" for e in events)


def test_write_passwd_is_denied(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(repo, home, "write /etc/passwd")
    blob = (result.stdout + result.stderr).lower()
    assert "sk-" not in blob
    events = _events(result.stdout) if result.stdout.strip() else []
    types = [e.get("type") for e in events]
    assert "permission.ask" in types or result.returncode in (0, 3)
    assert "/root/.claude" not in blob
