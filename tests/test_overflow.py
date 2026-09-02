"""Slice 4 TDD: overflow to second agent on rate_limit / AuthRequired (#200)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RATE_LIMIT = ROOT / "tests" / "support" / "fake_acp_rate_limit_agent.py"
OVERFLOW = ROOT / "tests" / "support" / "fake_acp_overflow_agent.py"


def _hang_auth_agent(path: Path) -> None:
    """Fake ACP child: answers initialize with authMethods, never answers authenticate."""
    path.write_text(
        textwrap.dedent(
            """\
            import json
            import sys
            import time

            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                msg = json.loads(line)
                method = msg.get("method")
                mid = msg.get("id")
                if method == "initialize":
                    sys.stdout.write(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": mid,
                                "result": {
                                    "protocolVersion": 1,
                                    "authMethods": [
                                        {"id": "cached_token", "name": "Cached token"}
                                    ],
                                },
                            }
                        )
                        + "\\n"
                    )
                    sys.stdout.flush()
                elif method == "authenticate":
                    time.sleep(3600)
            """
        ),
        encoding="utf-8",
    )


def _harness(
    repo: Path,
    *,
    overflow: str = '"overflow"',
    deny: str = "[]",
    primary_script: Path | None = None,
    overflow_script: Path | None = None,
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    primary = json.dumps([sys.executable, str(primary_script or RATE_LIMIT)])
    overflow_cmd = json.dumps(
        [sys.executable, str(overflow_script or OVERFLOW)]
    )
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


def _run(
    repo: Path,
    home: Path,
    prompt: str,
    *,
    handshake_timeout: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    if handshake_timeout is not None:
        env["RAVAND_ACP_HANDSHAKE_TIMEOUT"] = handshake_timeout
    return subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", prompt],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
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


def test_overflow_on_auth_missing_calls_second_agent(tmp_path: Path) -> None:
    """Primary AuthRequired at initialize/authenticate → overflow (#200)."""
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    hang = tmp_path / "hang_auth_agent.py"
    _hang_auth_agent(hang)
    _harness(repo, primary_script=hang)
    result = _run(repo, home, "say hi", handshake_timeout="1")
    assert result.returncode == 0, result.stderr
    assert "login" not in result.stderr.lower()

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

    audit_types = _audit_types(home)
    assert "agent.overflow" in audit_types
    assert "auth.missing" not in audit_types

    events = _events(result.stdout)
    assert any(event.get("text") == "hello-from-overflow" for event in events)


def test_overflow_auth_missing_when_overflow_also_auth_exits_2(tmp_path: Path) -> None:
    """Overflow AuthRequired after primary AuthRequired → exit 2 auth.missing."""
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    hang_primary = tmp_path / "hang_primary.py"
    hang_overflow = tmp_path / "hang_overflow.py"
    _hang_auth_agent(hang_primary)
    _hang_auth_agent(hang_overflow)
    _harness(repo, primary_script=hang_primary, overflow_script=hang_overflow)
    result = _run(repo, home, "say hi", handshake_timeout="1")
    assert result.returncode == 2, result.stderr
    assert "login" in result.stderr.lower()

    audit_types = _audit_types(home)
    assert "agent.overflow" in audit_types
    assert "auth.missing" in audit_types


def test_auth_missing_without_overflow_exits_2(tmp_path: Path) -> None:
    """AuthRequired with no overflow configured stays exit 2 (no overflow)."""
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    hang = tmp_path / "hang_auth_agent.py"
    _hang_auth_agent(hang)
    _harness(repo, overflow='""', primary_script=hang)
    result = _run(repo, home, "say hi", handshake_timeout="1")
    assert result.returncode == 2, result.stderr
    assert "login" in result.stderr.lower()
    assert "agent.overflow" not in _audit_types(home)
    assert "auth.missing" in _audit_types(home)
    assert len(_session_files(home)) == 0


def test_auth_missing_overflow_in_deny_does_not_spawn(tmp_path: Path) -> None:
    """AuthRequired + overflow in deny → exit 2, no second agent."""
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    hang = tmp_path / "hang_auth_agent.py"
    _hang_auth_agent(hang)
    _harness(repo, deny='["overflow"]', primary_script=hang)
    result = _run(repo, home, "say hi", handshake_timeout="1")
    assert result.returncode == 2, result.stderr
    assert "agent.overflow" not in _audit_types(home)
    assert "auth.missing" in _audit_types(home)
    assert not any(
        event.get("text") == "hello-from-overflow" for event in _events(result.stdout)
    )
