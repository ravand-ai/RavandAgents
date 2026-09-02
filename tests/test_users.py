"""Cloud users, roles, per-project access (GitHub issue #142).

Source of law: docs/MODULAR.md Cloud access, docs/HLD.md Deployment.
Fail closed if the role cannot be resolved. No vendor CLI cookies in SaaS.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ravand_policy import PolicyDenied, resolve_access

FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")

DEFAULT_USERS = """
[users.alice]
role = "runner"
projects = ["acme"]

[users.bob]
role = "admin"
projects = ["acme", "internal"]

[roles.runner]
projects = ["acme"]
profiles = ["work"]
accounts = ["grok-work"]

[roles.approver]
projects = ["acme"]
profiles = ["work"]
accounts = ["grok-work"]

[roles.admin]
projects = ["acme", "internal"]
profiles = ["work"]
accounts = ["grok-work", "claude-company"]
"""


def _write_users(home: Path, text: str = DEFAULT_USERS) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "users.toml").write_text(text.strip() + "\n", encoding="utf-8")


def _write_config(home: Path, text: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(text.strip() + "\n", encoding="utf-8")


def test_runner_access_on_allowed_project(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(home)
    access = resolve_access("alice", "acme", home=home)
    assert access.user == "alice"
    assert access.role == "runner"
    assert access.project == "acme"
    assert access.profiles == ["work"]
    assert access.accounts == ["grok-work"]
    text = " ".join(access.accounts + access.profiles)
    for marker in FORBIDDEN:
        assert marker not in text


def test_admin_and_runner_differ_on_same_project(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(home)
    runner = resolve_access("alice", "acme", home=home)
    admin = resolve_access("bob", "acme", home=home)
    assert runner.accounts == ["grok-work"]
    assert admin.accounts == ["grok-work", "claude-company"]
    assert "claude-company" not in runner.accounts


def test_unknown_user_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(home)
    with pytest.raises(PolicyDenied):
        resolve_access("mallory", "acme", home=home)


def test_unknown_role_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(
        home,
        """
[users.alice]
role = "ghost"
projects = ["acme"]

[roles.runner]
projects = ["acme"]
profiles = ["work"]
accounts = ["grok-work"]
""",
    )
    with pytest.raises(PolicyDenied):
        resolve_access("alice", "acme", home=home)


def test_missing_role_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(
        home,
        """
[users.alice]
projects = ["acme"]

[roles.runner]
projects = ["acme"]
profiles = ["work"]
accounts = ["grok-work"]
""",
    )
    with pytest.raises(PolicyDenied):
        resolve_access("alice", "acme", home=home)


def test_project_not_in_role_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(home)
    with pytest.raises(PolicyDenied):
        resolve_access("alice", "internal", home=home)


def test_user_cannot_expand_role_projects(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(
        home,
        """
[users.alice]
role = "runner"
projects = ["acme", "internal"]

[roles.runner]
projects = ["acme"]
profiles = ["work"]
accounts = ["grok-work"]
""",
    )
    access = resolve_access("alice", "acme", home=home)
    assert access.project == "acme"
    with pytest.raises(PolicyDenied):
        resolve_access("alice", "internal", home=home)


def test_missing_users_config_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(PolicyDenied):
        resolve_access("alice", "acme", home=home)


def test_load_from_config_toml(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_config(home, DEFAULT_USERS)
    access = resolve_access("alice", "acme", home=home)
    assert access.role == "runner"
    assert access.accounts == ["grok-work"]


def test_users_toml_wins_over_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_config(
        home,
        """
[users.alice]
role = "admin"
projects = ["acme"]

[roles.admin]
projects = ["acme"]
profiles = ["work"]
accounts = ["claude-company"]
""",
    )
    _write_users(home)
    access = resolve_access("alice", "acme", home=home)
    assert access.role == "runner"
    assert access.accounts == ["grok-work"]


def test_isolated_home_does_not_read_real_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    _write_users(home)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    monkeypatch.delenv("HOME", raising=False)
    access = resolve_access("alice", "acme")
    assert access.user == "alice"
    assert access.role == "runner"


def test_cookie_key_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(
        home,
        """
[users.alice]
role = "runner"
projects = ["acme"]
cookie = "copied"

[roles.runner]
projects = ["acme"]
profiles = ["work"]
accounts = ["grok-work"]
""",
    )
    with pytest.raises(PolicyDenied):
        resolve_access("alice", "acme", home=home)


def test_cookie_path_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(
        home,
        """
[users.alice]
role = "runner"
projects = ["acme"]

[roles.runner]
projects = ["acme"]
profiles = ["work"]
accounts = ["grok-work"]
home = "~/.grok/cookies"
""",
    )
    with pytest.raises(PolicyDenied):
        resolve_access("alice", "acme", home=home)


def test_tokens_fail_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(
        home,
        """
[users.alice]
role = "runner"
projects = ["acme"]

[roles.runner]
projects = ["acme"]
profiles = ["work"]
accounts = ["sk-not-an-account"]
""",
    )
    with pytest.raises(PolicyDenied):
        resolve_access("alice", "acme", home=home)


def test_invalid_users_table_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_users(
        home,
        """
users = ["alice"]

[roles.runner]
projects = ["acme"]
profiles = ["work"]
accounts = ["grok-work"]
""",
    )
    with pytest.raises(PolicyDenied):
        resolve_access("alice", "acme", home=home)
