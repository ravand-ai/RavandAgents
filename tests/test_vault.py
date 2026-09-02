"""Org vault for API keys (GitHub issue #143).

Source of law: docs/HLD.md Trust, docs/MODULAR.md Cloud access,
docs/SECURITY.md. Fail closed if secret_ref is missing. Never log keys.
Never store vendor CLI cookies. Isolated HOME only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ravand_audit import AuditLog
from ravand_bus import FailClosed, TaskMessage
from ravand_policy import PolicyDenied, load_secret, secret_present

FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")
REF = "vault:work/claude-api"
SECRET = "sk-not-a-real-key"


def _write_vault_secret(home: Path, ref: str, body: str) -> None:
    assert ref.startswith("vault:")
    path = home / "secrets" / ref.removeprefix("vault:")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_load_secret_from_isolated_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_vault_secret(home, REF, SECRET)
    got = load_secret(REF, home=home)
    assert got == SECRET.encode()


def test_secret_present_when_file_exists(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_vault_secret(home, REF, SECRET)
    assert secret_present(REF, home=home) is None


def test_missing_secret_ref_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(PolicyDenied, match="secret_ref is missing"):
        load_secret(REF, home=home)
    with pytest.raises(PolicyDenied, match="secret_ref is missing"):
        secret_present(REF, home=home)


def test_empty_secret_file_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_vault_secret(home, REF, "")
    with pytest.raises(PolicyDenied, match="secret_ref is missing"):
        load_secret(REF, home=home)


def test_whitespace_only_secret_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_vault_secret(home, REF, "\n")
    with pytest.raises(PolicyDenied, match="secret_ref is missing"):
        load_secret(REF, home=home)


def test_secret_ref_must_use_vault(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(PolicyDenied, match="secret_ref must use vault:"):
        load_secret("file:work/claude-api", home=home)


def test_absolute_secret_ref_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(PolicyDenied, match="secret_ref path is invalid"):
        load_secret("vault:/etc/passwd", home=home)


def test_secret_ref_path_escape_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(PolicyDenied):
        load_secret("vault:work/../../etc/passwd", home=home)


def test_symlink_escape_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    outside = tmp_path / "outside"
    outside.write_text(SECRET, encoding="utf-8")
    link = home / "secrets" / "work" / "claude-api"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)
    with pytest.raises(PolicyDenied):
        load_secret(REF, home=home)


def test_isolated_home_does_not_read_real_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    _write_vault_secret(home, REF, SECRET)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    monkeypatch.delenv("HOME", raising=False)
    got = load_secret(REF)
    assert got == SECRET.encode()


def test_does_not_read_vendor_cookies_from_profile_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cookie = home / "profiles" / "work" / ".grok" / "auth.json"
    cookie.parent.mkdir(parents=True, exist_ok=True)
    cookie.write_text("sk-leaked-from-fixture-cookie", encoding="utf-8")
    with pytest.raises(PolicyDenied):
        load_secret(REF, home=home)
    with pytest.raises(PolicyDenied):
        load_secret("vault:../profiles/work/.grok/auth.json", home=home)


def test_cookie_ref_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(PolicyDenied):
        load_secret("vault:work/.grok/cookies", home=home)


def test_token_in_ref_fails_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(PolicyDenied):
        load_secret("vault:work/sk-not-a-token", home=home)


def test_does_not_log_secret_bytes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    _write_vault_secret(home, REF, SECRET)
    got = load_secret(REF, home=home)
    assert got == SECRET.encode()
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert SECRET not in blob
    for marker in FORBIDDEN:
        assert marker not in blob
    try:
        load_secret("vault:work/missing", home=home)
    except PolicyDenied as exc:
        assert SECRET not in str(exc)
        for marker in FORBIDDEN:
            assert marker not in str(exc)


def test_secret_bytes_not_on_bus(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_vault_secret(home, REF, SECRET)
    got = load_secret(REF, home=home)
    with pytest.raises(FailClosed):
        TaskMessage(
            task_id="task-1",
            cwd_hint="/repo",
            profile="work",
            agent="grok",
            prompt=got.decode(),
            permissions="repo-only",
        )


def test_secret_bytes_not_in_audit(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_vault_secret(home, REF, SECRET)
    load_secret(REF, home=home)
    secret_present(REF, home=home)
    audit_path = home / "audit.jsonl"
    assert not audit_path.is_file()
    log = AuditLog(home)
    log.emit("agent.selected", task_id="vault", profile="work", agent="grok")
    blob = audit_path.read_text(encoding="utf-8")
    assert SECRET not in blob
    for marker in FORBIDDEN:
        assert marker not in blob
