"""Customer classification must never use a personal seat or account."""

from __future__ import annotations

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
    classification: str = "customer",
    accounts_allow: list[str] | None = None,
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    lines = [
        f'profile = "{profile}"',
        f'default = "{default}"',
        'overflow = ""',
        "deny = []",
        'permissions = "repo-only"',
        f'classification = "{classification}"',
        "",
        "[agents.grok]",
        'command = ["grok", "agent", "stdio"]',
        "",
        "[agents.kimi]",
        'command = ["kimi", "acp"]',
        "",
    ]
    if accounts_allow is not None:
        lines.append("[accounts]")
        quoted = ", ".join(f'"{item}"' for item in accounts_allow)
        lines.append(f"allow = [{quoted}]")
        lines.append("")
    (repo / "harness.toml").write_text("\n".join(lines), encoding="utf-8")


def _write_user_config(
    home: Path,
    *,
    accounts: dict[str, dict[str, str]],
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


@pytest.mark.parametrize(
    ("account_id", "spec"),
    [
        ("grok-personal", {"kind": "cli", "agent": "grok"}),
        ("grok-work", {"kind": "cli", "agent": "grok", "profile": "personal"}),
        ("grok-work", {"kind": "cli", "agent": "grok", "seat": "personal"}),
    ],
    ids=["id-contains-personal", "record-profile-personal", "record-seat-personal"],
)
def test_customer_denies_personal_cli_account(
    tmp_path: Path,
    account_id: str,
    spec: dict[str, str],
) -> None:
    home = tmp_path / "home"
    _write_user_config(home, accounts={account_id: spec})
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=[account_id])

    result = _which(repo, home, extra=["--account", account_id])
    assert result.returncode == 3
    assert "personal" in result.stderr.lower()


def test_customer_denies_personal_api_account_by_id(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ref = "vault:work/claude-personal"
    secret = home / "secrets" / "work" / "claude-personal"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("fake-key", encoding="utf-8")
    _write_user_config(
        home,
        accounts={
            "claude-personal": {
                "kind": "api",
                "provider": "anthropic",
                "secret_ref": ref,
            }
        },
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["claude-personal"])

    result = _which(repo, home, extra=["--account", "claude-personal"])
    assert result.returncode == 3
    assert "personal" in result.stderr.lower()


def test_customer_denies_api_account_with_personal_seat(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ref = "vault:work/claude-api"
    secret = home / "secrets" / "work" / "claude-api"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("fake-key", encoding="utf-8")
    _write_user_config(
        home,
        accounts={
            "claude-api": {
                "kind": "api",
                "provider": "anthropic",
                "secret_ref": ref,
                "seat": "personal",
            }
        },
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["claude-api"])

    result = _which(repo, home, extra=["--account", "claude-api"])
    assert result.returncode == 3


def test_resolve_customer_personal_account_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-personal": {"kind": "cli", "agent": "grok"}},
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["grok-personal"])
    monkeypatch.setenv("RAVAND_HOME", str(home))

    with pytest.raises(PolicyDenied, match="personal"):
        resolve(repo, account_override="grok-personal")


def test_customer_allows_work_account(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-work": {"kind": "cli", "agent": "grok"}},
    )
    repo = tmp_path / "repo"
    _write_harness(repo, accounts_allow=["grok-work"])

    result = _which(repo, home, extra=["--account", "grok-work"])
    assert result.returncode == 0, result.stderr
