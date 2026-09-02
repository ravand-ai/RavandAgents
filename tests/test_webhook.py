"""Signed inbound webhooks fail closed if unsigned (GitHub issue #138).

Source of law: docs/HLD.md Gateway, docs/MODULAR.md Triggers,
docs/SCHEMA.md [triggers.webhook].
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from ravand_audit import AuditLog
from ravand_bus import Bus
from ravand_policy import PolicyDenied
from ravand_runtime.webhook import (
    handle_webhook,
    load_webhook,
    verify_webhook_signature,
)
from ravand_sessions import SessionStore

QUEUE_TASKS = "q.tasks"
SECRET = b"test-webhook-secret"
SECRET_REF = "vault:work/webhook"
FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


def _write_harness(
    repo: Path,
    *,
    profile: str = "work",
    default: str = "grok",
    deny: str = "[]",
    classification: str = "internal",
    extra: str = "",
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                f'default = "{default}"',
                'overflow = "kimi"',
                f"deny = {deny}",
                'permissions = "repo-only"',
                f'classification = "{classification}"',
                extra,
                "",
                "[agents.grok]",
                'command = ["grok", "agent", "stdio"]',
                "",
                "[agents.kimi]",
                'command = ["kimi", "acp"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


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


def _write_vault_secret(home: Path, ref: str, body: str) -> None:
    assert ref.startswith("vault:")
    path = home / "secrets" / ref.removeprefix("vault:")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.encode("utf-8"))


def _webhook_extra(
    *,
    path: str = "/hooks/deploy",
    secret_ref: str = SECRET_REF,
    prompt: str = "inbound webhook",
    extra_fields: str = "",
) -> str:
    lines = [
        "[triggers.webhook]",
        f'path = "{path}"',
        f'secret_ref = "{secret_ref}"',
        f'prompt = "{prompt}"',
    ]
    if extra_fields:
        lines.append(extra_fields)
    return "\n".join(lines) + "\n"


def _sig(body: bytes, secret: bytes = SECRET) -> str:
    digest = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _audit_events(root: Path) -> list[dict[str, object]]:
    path = root / "audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_verify_hmac_accepts_injected_secret_bytes() -> None:
    body = b'{"ok":true}'
    secret = b"injected-secret-bytes"
    assert verify_webhook_signature(body, _sig(body, secret), secret)
    assert not verify_webhook_signature(body, _sig(body, b"other"), secret)
    assert not verify_webhook_signature(body, None, secret)


def test_load_webhook_from_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo, extra=_webhook_extra())
    monkeypatch.setenv("RAVAND_HOME", str(home))
    trigger = load_webhook(repo)
    assert trigger is not None
    assert trigger.path == "/hooks/deploy"
    assert trigger.secret_ref == SECRET_REF
    assert trigger.prompt == "inbound webhook"


def test_missing_webhook_section_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    assert load_webhook(repo) is None


def test_secret_ref_must_use_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_webhook_extra(secret_ref="file:work/webhook"),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        load_webhook(repo)


def test_password_in_harness_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_webhook_extra(extra_fields='password = "hunter2"'),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        load_webhook(repo)


def test_unsigned_webhook_fails_closed_and_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo, extra=_webhook_extra())
    _write_vault_secret(home, SECRET_REF, SECRET.decode())
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    body = b'{"ok":true}'
    with pytest.raises(PolicyDenied):
        handle_webhook(
            repo,
            path="/hooks/deploy",
            body=body,
            signature=None,
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []
    events = _audit_events(home)
    assert [event["type"] for event in events] == ["trigger.denied"]
    blob = (home / "audit.jsonl").read_text(encoding="utf-8")
    for marker in FORBIDDEN:
        assert marker not in blob
    assert SECRET.decode() not in blob


def test_bad_signature_fails_closed_and_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo, extra=_webhook_extra())
    _write_vault_secret(home, SECRET_REF, SECRET.decode())
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    body = b'{"ok":true}'
    with pytest.raises(PolicyDenied):
        handle_webhook(
            repo,
            path="/hooks/deploy",
            body=body,
            signature=_sig(body, b"wrong-secret"),
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    events = _audit_events(home)
    assert [event["type"] for event in events] == ["trigger.denied"]
    blob = (home / "audit.jsonl").read_text(encoding="utf-8")
    for marker in FORBIDDEN:
        assert marker not in blob


def test_unknown_webhook_fails_closed_and_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo, extra=_webhook_extra())
    _write_vault_secret(home, SECRET_REF, SECRET.decode())
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    body = b'{"ok":true}'
    with pytest.raises(PolicyDenied):
        handle_webhook(
            repo,
            path="/hooks/unknown",
            body=body,
            signature=_sig(body),
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    events = _audit_events(home)
    assert [event["type"] for event in events] == ["trigger.denied"]


def test_good_signature_dispatches_after_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo, extra=_webhook_extra())
    _write_vault_secret(home, SECRET_REF, SECRET.decode())
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    body = b'{"ok":true}'
    trigger = handle_webhook(
        repo,
        path="/hooks/deploy",
        body=body,
        signature=_sig(body),
        bus=bus,
        store=store,
        audit=AuditLog(home),
    )
    assert trigger is not None
    assert trigger.path == "/hooks/deploy"
    got = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert got is not None
    assert got.prompt == "inbound webhook"
    assert got.agent == "grok"
    assert got.profile == "work"
    assert got.cwd_hint == str(repo.resolve())
    assert list((home / "sessions").glob("*.json"))
    events = _audit_events(home)
    assert "trigger.denied" not in [event["type"] for event in events]
    blob = (home / "audit.jsonl").read_text(encoding="utf-8") if events else ""
    for marker in FORBIDDEN:
        assert marker not in blob
    assert SECRET.decode() not in blob


def test_denied_policy_does_not_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        default="kimi",
        deny='["kimi"]',
        extra=_webhook_extra(),
    )
    _write_vault_secret(home, SECRET_REF, SECRET.decode())
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    body = b'{"ok":true}'
    with pytest.raises(PolicyDenied):
        handle_webhook(
            repo,
            path="/hooks/deploy",
            body=body,
            signature=_sig(body),
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []
    events = _audit_events(home)
    assert [event["type"] for event in events] == ["trigger.denied"]


def test_account_mismatch_skips_and_audits_trigger_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-personal": {"kind": "cli", "agent": "grok"}},
    )
    _write_harness(
        repo,
        classification="customer",
        extra=_webhook_extra(extra_fields='account = "grok-personal"'),
    )
    _write_vault_secret(home, SECRET_REF, SECRET.decode())
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    body = b'{"ok":true}'
    with pytest.raises(PolicyDenied):
        handle_webhook(
            repo,
            path="/hooks/deploy",
            body=body,
            signature=_sig(body),
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    events = _audit_events(home)
    assert [event["type"] for event in events] == ["trigger.denied"]
    blob = (home / "audit.jsonl").read_text(encoding="utf-8")
    assert "sk-" not in blob
    assert SECRET.decode() not in blob
