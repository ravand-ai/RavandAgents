"""Native loop: optional path requiring kind=api named account. ACP unchanged."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"
FORBIDDEN = ("sk-", "xai-", "Bearer", "not-a-token")


def _write_user_config(
    home: Path,
    *,
    accounts: dict[str, dict[str, str]] | None = None,
) -> None:
    home.mkdir(parents=True, exist_ok=True)
    lines = [
        'default_profile = "work"',
        "",
        "[profiles.work]",
        'home = "~/.ravand/profiles/work"',
        'allow = ["fake", "grok"]',
        "",
    ]
    if accounts:
        for account_id, spec in accounts.items():
            lines.append(f"[accounts.{account_id}]")
            for key, value in spec.items():
                lines.append(f'{key} = "{value}"')
            lines.append("")
    (home / "config.toml").write_text("\n".join(lines), encoding="utf-8")


def _write_vault_secret(home: Path, ref: str, body: str = "not-a-token") -> None:
    assert ref.startswith("vault:")
    path = home / "secrets" / ref.removeprefix("vault:")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _write_harness(
    repo: Path,
    *,
    loop: str | None = None,
    accounts_allow: list[str] | None = None,
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
    ]
    if loop is not None:
        lines.append(f'loop = "{loop}"')
    lines.extend(
        [
            "",
            "[agents.fake]",
            f"command = {fake}",
            "",
        ]
    )
    if accounts_allow is not None:
        quoted = ", ".join(f'"{item}"' for item in accounts_allow)
        lines.extend(
            [
                "[accounts]",
                f"allow = [{quoted}]",
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
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    env.update(extra_env or {})
    return subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", *(extra_args or []), prompt],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _events(stdout: str) -> list[dict]:
    return [json.loads(ln) for ln in stdout.splitlines() if ln.strip()]


def test_native_loop_without_account_fail_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(home)
    repo = tmp_path / "repo"
    _write_harness(repo, loop="native")

    result = _run(repo, home, "hello")
    assert result.returncode == 3, result.stderr
    assert not list((home / "sessions").glob("*.json"))

    audit_path = home / "audit.jsonl"
    assert audit_path.is_file()
    audit_types = [
        json.loads(line)["type"]
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "agent.denied" in audit_types


def test_native_loop_with_cli_account_fail_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-work": {"kind": "cli", "agent": "fake"}},
    )
    repo = tmp_path / "repo"
    _write_harness(repo, loop="native", accounts_allow=["grok-work"])

    result = _run(repo, home, "hello", extra_args=["--account", "grok-work"])
    assert result.returncode == 3, result.stderr
    assert "api" in result.stderr.lower()


def test_native_loop_with_api_account_emits_events_without_acp_spawn(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    ref = "vault:work/claude-api"
    _write_user_config(
        home,
        accounts={
            "claude-api": {
                "kind": "api",
                "provider": "anthropic",
                "secret_ref": ref,
            }
        },
    )
    _write_vault_secret(home, ref)
    repo = tmp_path / "repo"
    _write_harness(repo, loop="native", accounts_allow=["claude-api"])
    spawn_marker = tmp_path / "acp-spawned"

    result = _run(
        repo,
        home,
        "hello native",
        extra_args=["--account", "claude-api"],
        extra_env={"FAKE_ACP_STATE": str(spawn_marker)},
    )
    assert result.returncode == 0, result.stderr
    assert not spawn_marker.exists()

    events = _events(result.stdout)
    types = [e["type"] for e in events]
    assert "run.started" in types
    assert "run.ended" in types
    assert events[-1].get("status") == "stub"

    sessions = list((home / "sessions").glob("*.json"))
    assert len(sessions) == 1
    session = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert session["status"] == "stub"
    assert session["account"] == "claude-api"

    audit_path = home / "audit.jsonl"
    audit_events = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    audit_types = [e["type"] for e in audit_events]
    assert "agent.selected" in audit_types
    assert "run.started" in audit_types
    assert "run.ended" in audit_types

    blob = result.stdout + result.stderr + sessions[0].read_text(encoding="utf-8")
    for marker in FORBIDDEN:
        assert marker not in blob


def test_acp_loop_default_unchanged(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(home)
    repo = tmp_path / "repo"
    _write_harness(repo)

    result = _run(repo, home, "say hi")
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert any(e.get("text") == "hello-from-fake" for e in events)
    assert events[-1].get("status") == "ok"


def test_api_account_with_acp_loop_still_denied(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ref = "vault:work/claude-api"
    _write_user_config(
        home,
        accounts={
            "claude-api": {
                "kind": "api",
                "secret_ref": ref,
            }
        },
    )
    _write_vault_secret(home, ref)
    repo = tmp_path / "repo"
    _write_harness(repo, loop="acp", accounts_allow=["claude-api"])

    result = _run(repo, home, "hi", extra_args=["--account", "claude-api"])
    assert result.returncode == 3, result.stderr
    assert not list((home / "sessions").glob("*.json"))
