"""ravand serve (no subcommand) shares http, cron, and worker (GitHub issue #214).

One process, one Bus. Cron or webhook enqueue is visible to the in-process
worker. Existing ravand serve http|cron|worker stay. Fail closed if Policy
cannot resolve cwd. Injected bus. Stdlib threads. No Kafka. No TUI.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ravand_audit import AuditLog
from ravand_bus import Bus, TaskMessage
from ravand_runtime.http_api import DEFAULT_HTTP_PORT, HttpApiServer
from ravand_runtime.serve import serve_all
from ravand_sessions import SessionStore

ROOT = Path(__file__).resolve().parents[1]
QUEUE_TASKS = "q.tasks"
FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")
WEBHOOK_SECRET = b"test-webhook-secret"
WEBHOOK_SECRET_REF = "vault:work/webhook"
WEBHOOK_PATH = "/hooks/deploy"
DUE = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)


def _write_harness(repo: Path, *, extra: str = "") -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                'profile = "work"',
                'default = "grok"',
                'overflow = "kimi"',
                "deny = []",
                'permissions = "repo-only"',
                'classification = "internal"',
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


def _write_vault_secret(home: Path, ref: str, body: str) -> None:
    assert ref.startswith("vault:")
    path = home / "secrets" / ref.removeprefix("vault:")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.encode("utf-8"))


def _sig(body: bytes, secret: bytes = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _ravand(
    *args: str, cwd: Path | None = None, env: dict | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ravand", *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=15,
    )


def _post(
    url: str,
    payload: dict | bytes,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    if isinstance(payload, bytes):
        data = payload
    else:
        data = json.dumps(payload).encode()
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers=req_headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode()
            ctype = resp.headers.get("Content-Type") or ""
            return resp.status, body, ctype
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        ctype = exc.headers.get("Content-Type") or "" if exc.headers else ""
        return exc.code, body, ctype


def _start_serve_all(
    *,
    repo: Path,
    bus: Bus,
    store: SessionStore,
    audit: AuditLog,
    run: Callable[[TaskMessage], int],
    now: datetime | None = None,
    slept: list[float] | None = None,
) -> tuple[threading.Thread, HttpApiServer, list[BaseException]]:
    ready = threading.Event()
    holder: dict[str, HttpApiServer] = {}
    errors: list[BaseException] = []

    def on_listen(server: HttpApiServer) -> None:
        holder["server"] = server
        ready.set()

    def _run() -> None:
        try:
            code = serve_all(
                cwd=repo,
                port=0,
                bus=bus,
                store=store,
                audit=audit,
                now=now,
                cron_interval=0,
                worker_interval=0,
                sleep=(slept.append if slept is not None else None),
                run=run,
                on_listen=on_listen,
            )
            if code != 0:
                errors.append(RuntimeError(f"serve_all exited {code}"))
        except BaseException as exc:  # noqa: BLE001 — capture for assert
            errors.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    assert ready.wait(timeout=5), errors
    assert not errors, errors
    return thread, holder["server"], errors


def _stop_serve_all(thread: threading.Thread, server: HttpApiServer) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_serve_help_default_compose() -> None:
    result = _ravand("serve", "--help")
    assert result.returncode == 0, result.stderr
    combined = (result.stdout + result.stderr).lower()
    assert "usage" in combined
    assert "http" in combined
    assert "cron" in combined
    assert "worker" in combined
    assert "bus" in combined
    assert "--port" in combined
    assert str(DEFAULT_HTTP_PORT) in combined
    assert "not implemented" not in combined


def test_serve_http_cron_worker_help_still_exist() -> None:
    for name in ("http", "cron", "worker"):
        result = _ravand("serve", name, "--help")
        assert result.returncode == 0, result.stderr
        combined = (result.stdout + result.stderr).lower()
        assert "usage" in combined
        assert name in combined
        assert "not implemented" not in combined


def test_serve_all_fails_closed_when_policy_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("RAVAND_HOME", str(home))
    slept: list[float] = []
    code = serve_all(
        cwd=empty,
        port=0,
        cron_interval=0,
        worker_interval=0,
        max_ticks=1,
        sleep=slept.append,
    )
    assert code != 0
    assert slept == []
    assert list((home / "sessions").glob("*.json")) == []


def test_cli_serve_fail_closed_without_harness(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    home = tmp_path / "home"
    env = dict(os.environ)
    env["RAVAND_HOME"] = str(home)
    result = _ravand("serve", cwd=empty, env=env)
    assert result.returncode != 0
    blob = (result.stdout + result.stderr).lower()
    assert "not implemented" not in blob
    for marker in FORBIDDEN:
        assert marker not in blob


def test_serve_all_cron_enqueue_is_visible_to_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            'jobs = [{ id = "morning", spec = "0 9 * * 1-5", prompt = "status" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    seen = threading.Event()
    ran: list[TaskMessage] = []
    slept: list[float] = []

    def run(message: TaskMessage) -> int:
        ran.append(message)
        seen.set()
        return 0

    thread, server, errors = _start_serve_all(
        repo=repo,
        bus=bus,
        store=store,
        audit=AuditLog(home),
        run=run,
        now=DUE,
        slept=slept,
    )
    try:
        assert server.bus is bus
        host, bound = server.server_address
        assert host == "127.0.0.1"
        assert isinstance(bound, int) and bound > 0
        assert seen.wait(timeout=5), errors
        assert not errors, errors
        assert ran
        assert ran[0].task_id == "morning:20260907T0900"
        assert ran[0].prompt == "status"
        assert ran[0].agent == "grok"
        assert ran[0].cwd_hint == str(repo.resolve())
        assert all(seconds < 60 for seconds in slept)
        leftover = bus.read(QUEUE_TASKS, visibility_timeout=600)
        assert leftover is None
    finally:
        _stop_serve_all(thread, server)
    blob = (home / "audit.jsonl").read_text(encoding="utf-8") if (home / "audit.jsonl").is_file() else ""
    for marker in FORBIDDEN:
        assert marker not in blob


def test_serve_all_webhook_enqueue_is_visible_to_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra="\n".join(
            [
                "[triggers.webhook]",
                f'path = "{WEBHOOK_PATH}"',
                f'secret_ref = "{WEBHOOK_SECRET_REF}"',
                'prompt = "inbound webhook"',
                "",
            ]
        ),
    )
    _write_vault_secret(home, WEBHOOK_SECRET_REF, WEBHOOK_SECRET.decode())
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    seen = threading.Event()
    ran: list[TaskMessage] = []
    slept: list[float] = []

    def run(message: TaskMessage) -> int:
        ran.append(message)
        seen.set()
        return 0

    thread, server, errors = _start_serve_all(
        repo=repo,
        bus=bus,
        store=store,
        audit=AuditLog(home),
        run=run,
        slept=slept,
    )
    try:
        assert server.bus is bus
        host, bound = server.server_address
        body = b'{"ok":true}'
        status, resp, _ctype = _post(
            f"http://{host}:{bound}{WEBHOOK_PATH}",
            body,
            headers={"X-Ravand-Signature": _sig(body)},
        )
        assert status == 200, resp
        for marker in FORBIDDEN:
            assert marker not in resp
        assert WEBHOOK_SECRET.decode() not in resp
        assert seen.wait(timeout=5), errors
        assert not errors, errors
        assert ran
        assert ran[0].prompt == "inbound webhook"
        assert ran[0].agent == "grok"
        assert ran[0].cwd_hint == str(repo.resolve())
        assert all(seconds < 60 for seconds in slept)
        leftover = bus.read(QUEUE_TASKS, visibility_timeout=600)
        assert leftover is None
    finally:
        _stop_serve_all(thread, server)
