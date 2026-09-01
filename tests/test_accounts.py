"""Named CLI accounts: fail-closed policy resolution."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ravand_policy import PolicyDenied, resolve

ROOT = Path(__file__).resolve().parents[1]


def _write_harness(
    repo: Path,
    *,
    profile: str = "work",
    default: str = "grok",
    accounts_allow: list[str] | None = None,
    accounts_deny: list[str] | None = None,
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    lines = [
        f'profile = "{profile}"',
        f'default = "{default}"',
        'overflow = ""',
        "deny = []",
        'permissions = "repo-only"',
        'classification = "internal"',
        "",
        "[agents.grok]",
        'command = ["grok", "agent", "stdio"]',
        "",
        "[agents.kimi]",
        'command = ["kimi", "acp"]',
        "",
    ]
    if accounts_allow is not None or accounts_deny is not None:
        lines.append("[accounts]")
        if accounts_allow is not None:
            quoted = ", ".join(f'"{item}"' for item in accounts_allow)
            lines.append(f"allow = [{quoted}]")
        if accounts_deny is not None:
            quoted = ", ".join(f'"{item}"' for item in accounts_deny)
            lines.append(f"deny = [{quoted}]")
        lines.append("")
    (repo / "harness.toml").write_text("\n".join(lines), encoding="utf-8")


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
        'allow = ["grok", "kimi"]',
        "",
    ]
    if accounts:
        for account_id, spec in accounts.items():
            lines.append(f"[accounts.{account_id}]")
            for key, value in spec.items():
                lines.append(f'{key} = "{value}"')
            lines.append("")
    (home / "config.toml").write_text("\n".join(lines), encoding="utf-8")


def _which(
    cwd: Path,
    home: Path,
    extra: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    return subprocess.run(
        ["uv", "run", "ravand", "which", *(extra or [])],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_which_includes_empty_account_without_named_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    _write_user_config(home)
    repo = tmp_path / "repo"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))

    policy = resolve(repo)
    assert policy.account == ""

    result = _which(repo, home)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["account"] == ""


def test_which_resolves_named_cli_account(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-work": {"kind": "cli", "agent": "grok"}},
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["grok-work"], accounts_deny=["grok-personal"])

    result = _which(repo, home, extra=["--account", "grok-work"])
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["account"] == "grok-work"
    assert data["agent"] == "grok"


def test_unknown_account_is_policy_denied(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(home)
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["grok-work"])

    result = _which(repo, home, extra=["--account", "missing"])
    assert result.returncode == 3
    assert "missing" in result.stderr.lower() or "unknown" in result.stderr.lower()


def test_denied_account_is_policy_denied(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-personal": {"kind": "cli", "agent": "grok"}},
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_deny=["grok-personal"])

    result = _which(repo, home, extra=["--account", "grok-personal"])
    assert result.returncode == 3


def test_account_not_in_allow_list_is_policy_denied(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-other": {"kind": "cli", "agent": "grok"}},
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["grok-work"])

    result = _which(repo, home, extra=["--account", "grok-other"])
    assert result.returncode == 3


def test_api_kind_account_fail_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-api": {"kind": "api", "agent": "grok"}},
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["grok-api"])

    result = _which(repo, home, extra=["--account", "grok-api"])
    assert result.returncode == 3


def test_account_agent_must_match_resolved_agent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-work": {"kind": "cli", "agent": "grok"}},
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["grok-work"])

    result = _which(
        repo,
        home,
        extra=["--account", "grok-work", "-a", "kimi"],
    )
    assert result.returncode == 3


def test_resolve_unknown_account_raises_policy_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    _write_user_config(home)
    repo = tmp_path / "repo"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))

    with pytest.raises(PolicyDenied):
        resolve(repo, account_override="nope")


def test_run_rejects_denied_account(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-personal": {"kind": "cli", "agent": "grok"}},
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_deny=["grok-personal"])
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)

    result = subprocess.run(
        ["uv", "run", "ravand", "run", "--account", "grok-personal", "hi"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3


def _write_vault_secret(home: Path, ref: str, body: str = "not-a-token") -> None:
    assert ref.startswith("vault:")
    path = home / "secrets" / ref.removeprefix("vault:")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_which_resolves_named_api_account_with_secret_ref(tmp_path: Path) -> None:
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
    _write_harness(repo, accounts_allow=["claude-api"])

    result = _which(repo, home, extra=["--account", "claude-api"])
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["account"] == "claude-api"
    assert data["kind"] == "api"
    blob = result.stdout + result.stderr
    assert "not-a-token" not in blob
    assert "sk-" not in blob


def test_api_account_missing_secret_ref_is_policy_denied(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"claude-api": {"kind": "api", "provider": "anthropic"}},
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["claude-api"])

    result = _which(repo, home, extra=["--account", "claude-api"])
    assert result.returncode == 3


def test_api_account_missing_secret_file_is_policy_denied(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={
            "claude-api": {
                "kind": "api",
                "secret_ref": "vault:work/claude-api",
            }
        },
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["claude-api"])

    result = _which(repo, home, extra=["--account", "claude-api"])
    assert result.returncode == 3


def test_run_does_not_spawn_acp_for_api_account(tmp_path: Path) -> None:
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
    _write_harness(repo, accounts_allow=["claude-api"])
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)

    result = subprocess.run(
        ["uv", "run", "ravand", "run", "--account", "claude-api", "hi"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    blob = result.stdout + result.stderr
    assert "not-a-token" not in blob
