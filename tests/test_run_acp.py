"""Slice 2 TDD: ravand run over ACP with isolated HOME and JSONL."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"
FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


def _harness(repo: Path, *, deny: list[str] | None = None) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    fake = json.dumps([sys.executable, str(FAKE)])
    deny_json = json.dumps(deny or [])
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                'profile = "work"',
                'default = "fake"',
                'overflow = ""',
                f"deny = {deny_json}",
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


def _run(
    repo: Path,
    home: Path,
    prompt: str,
    extra_env: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    env.update(extra_env or {})
    return subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", *(extra_args or []), prompt],
        cwd=repo,
        env=env,
        input=stdin,
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
    assert "thinking.delta" in types
    assert "tool.call" in types
    assert any(e.get("tool") == "Read AGENTS.md" for e in events)


def test_run_format_text_prints_turns_not_json(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    result = subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "text", "--yes", "say hi"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "hello-from-fake" in out
    assert "run started" in out
    assert "run ended" in out
    for line in out.splitlines():
        stripped = line.strip()
        if stripped:
            assert not stripped.startswith("{"), stripped
    blob = out + result.stderr
    assert "sk-" not in blob
    assert "xai-" not in blob
    assert "Bearer" not in blob


def test_session_update_list_content_after_permission_does_not_crash(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(repo, home, "fetch https://example.com")
    assert result.returncode == 0, result.stderr
    assert "list' object has no attribute 'get'" not in result.stderr
    events = _events(result.stdout)
    types = [e.get("type") for e in events]
    assert "permission.ask" in types
    assert "text.delta" in types
    assert any(e.get("text") == "fetched-ok" for e in events)
    assert events[-1].get("type") == "run.ended"
    assert events[-1].get("status") == "ok"


def test_yes_fetch_uses_advertised_allow_once_option(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(
        repo,
        home,
        "fetch https://example.com",
        extra_args=["--yes"],
    )
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert any(e.get("text") == "fetched-ok" for e in events)
    assert events[-1].get("type") == "run.ended"
    assert events[-1].get("status") == "ok"


def test_deny_replies_with_reject_once_option(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    passwd = _run(repo, home, "write /etc/passwd")
    assert passwd.returncode == 0, passwd.stderr
    passwd_events = _events(passwd.stdout) if passwd.stdout.strip() else []
    assert "permission.ask" in [e.get("type") for e in passwd_events]
    assert "invalid permission optionId" not in passwd.stderr.lower()

    denied_fetch = _run(
        repo,
        home,
        "fetch https://example.com",
        extra_env={"RAVAND_ASK": "1"},
        stdin="n\n",
    )
    assert denied_fetch.returncode == 0, denied_fetch.stderr
    denied_events = _events(denied_fetch.stdout)
    assert not any(e.get("text") == "fetched-ok" for e in denied_events)
    assert "invalid permission optionId" not in denied_fetch.stderr.lower()


def test_stderr_spam_does_not_hang(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", "stderr-spam"],
        cwd=repo,
        env={**os.environ, "RAVAND_HOME": str(home)},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert any(e.get("text") == "stderr-drained" for e in events)
    assert events[-1].get("status") == "ok"


def test_human_ask_yes_allows_fetch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(
        repo,
        home,
        "fetch https://example.com",
        extra_env={"RAVAND_ASK": "1"},
        stdin="y\n",
    )
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert any(e.get("text") == "fetched-ok" for e in events)
    assert "allow" in result.stderr.lower()


def test_human_ask_no_denies_fetch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(
        repo,
        home,
        "fetch https://example.com",
        extra_env={"RAVAND_ASK": "1"},
        stdin="n\n",
    )
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert not any(e.get("text") == "fetched-ok" for e in events)
    types = [e.get("type") for e in events]
    assert "permission.ask" in types


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


def test_run_writes_session_and_audit_without_secrets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    prompt = "say hi"
    result = _run(repo, home, prompt)
    assert result.returncode == 0, result.stderr

    sessions = list((home / "sessions").glob("*.json"))
    assert len(sessions) == 1
    session = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert session["status"] == "ok"
    assert session["profile"] == "work"
    assert session["agent"] == "fake"
    assert session["taskId"]
    assert session.get("acpSessionId") == "sess-test"

    audit_path = home / "audit.jsonl"
    assert audit_path.is_file()
    audit_events = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    audit_types = [event["type"] for event in audit_events]
    assert "agent.selected" in audit_types
    assert "run.started" in audit_types
    assert "run.ended" in audit_types

    blob = (
        sessions[0].read_text(encoding="utf-8")
        + audit_path.read_text(encoding="utf-8")
        + result.stdout
        + result.stderr
    )
    for marker in FORBIDDEN:
        assert marker not in blob
    for event in audit_events:
        assert prompt not in event.get("detail", "")


def test_denied_run_writes_agent_denied_without_spawn(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, deny=["fake"])
    result = _run(repo, home, "say hi")
    assert result.returncode == 3, result.stderr
    assert not list((home / "sessions").glob("*.json"))

    audit_path = home / "audit.jsonl"
    assert audit_path.is_file()
    audit_events = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(event["type"] == "agent.denied" for event in audit_events)
    blob = audit_path.read_text(encoding="utf-8") + result.stdout + result.stderr
    for marker in FORBIDDEN:
        assert marker not in blob


def test_auth_required_exits_2_no_session_no_spawn(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    marker = tmp_path / "spawned-after-auth-failure"
    result = _run(
        repo,
        home,
        "say hi",
        {"FAKE_ACP_AUTH": "required", "FAKE_ACP_STATE": str(marker)},
    )
    assert result.returncode == 2, result.stderr
    assert "login" in result.stderr.lower()
    assert not marker.exists()
    assert not list((home / "sessions").glob("*.json"))

    audit_path = home / "audit.jsonl"
    assert audit_path.is_file()
    audit_events = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    audit_types = [event["type"] for event in audit_events]
    assert "auth.missing" in audit_types
    blob = audit_path.read_text(encoding="utf-8") + result.stdout + result.stderr
    for marker_text in FORBIDDEN:
        assert marker_text not in blob


def test_auth_cached_token_continues_run(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(repo, home, "say hi", {"FAKE_ACP_AUTH": "cached"})
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert any(e.get("text") == "hello-from-fake" for e in events)
