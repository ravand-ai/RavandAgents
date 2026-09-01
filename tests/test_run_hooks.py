"""Wire tool.pre hooks into ravand run on session/request_permission."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"


def _script(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _harness(
    repo: Path,
    *,
    hook_command: list[str] | None = None,
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    fake = json.dumps([sys.executable, str(FAKE)])
    lines = [
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
    if hook_command is not None:
        cmd_json = json.dumps(hook_command)
        lines.extend(
            [
                "[[hooks]]",
                'on = "tool.pre"',
                f"command = {cmd_json}",
                "",
            ]
        )
    (repo / "harness.toml").write_text("\n".join(lines), encoding="utf-8")


def _run(
    repo: Path,
    home: Path,
    prompt: str,
    *,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    return subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", *(extra_args or []), prompt],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _audit_types(home: Path) -> list[str]:
    audit_path = home / "audit.jsonl"
    if not audit_path.is_file():
        return []
    return [
        json.loads(line)["type"]
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_no_hook_uses_permission_broker_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(repo, home, "write /etc/passwd")
    assert result.returncode == 0, result.stderr
    types = _audit_types(home)
    assert "hook.deny" not in types
    assert "permission.deny" in types or "permission.allow" in types


def test_hook_allow_continues_to_broker(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, hook_command=_script("pass"))
    result = _run(repo, home, "write /etc/passwd")
    assert result.returncode == 0, result.stderr
    types = _audit_types(home)
    assert "hook.deny" not in types
    assert "permission.deny" in types


def test_hook_deny_rejects_tool_and_audits(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, hook_command=_script("import sys; sys.exit(1)"))
    result = _run(repo, home, "write /etc/passwd")
    assert result.returncode == 0, result.stderr
    types = _audit_types(home)
    assert "hook.deny" in types
    assert "permission.deny" not in types


def test_hook_missing_binary_denies(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, hook_command=["definitely-not-an-executable-hooks-101"])
    result = _run(repo, home, "write /etc/passwd")
    assert result.returncode == 0, result.stderr
    assert "hook.deny" in _audit_types(home)


def test_hook_empty_command_denies(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, hook_command=[])
    result = _run(repo, home, "write /etc/passwd")
    assert result.returncode == 0, result.stderr
    assert "hook.deny" in _audit_types(home)


def test_hook_allow_then_yes_allows_fetch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, hook_command=_script("pass"))
    result = _run(
        repo,
        home,
        "fetch https://example.com",
        extra_args=["--yes"],
    )
    assert result.returncode == 0, result.stderr
    events = [
        json.loads(line)
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    assert any(e.get("text") == "fetched-ok" for e in events)
    types = _audit_types(home)
    assert "hook.deny" not in types
    assert "permission.allow" in types


def test_hook_deny_blocks_fetch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, hook_command=_script("import sys; sys.exit(2)"))
    result = _run(
        repo,
        home,
        "fetch https://example.com",
        extra_args=["--yes"],
    )
    assert result.returncode == 0, result.stderr
    events = [
        json.loads(line)
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    assert not any(e.get("text") == "fetched-ok" for e in events)
    assert "hook.deny" in _audit_types(home)
    assert "permission.allow" not in _audit_types(home)
