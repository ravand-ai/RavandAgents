"""HTTP API + ravand serve http SSE gateway (GitHub issues #137, #206)."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from ravand_bus import Bus
from ravand_runtime.http_api import DEFAULT_HTTP_PORT, HttpApiServer, serve_http
from ravand_sessions import SessionStore

ROOT = Path(__file__).resolve().parents[1]
QUEUE_TASKS = "q.tasks"
FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")
SESSION_EVENT_TYPES = frozenset(
    {
        "run.started",
        "text.delta",
        "thinking.delta",
        "tool.call",
        "tool.result",
        "permission.ask",
        "plan.ready",
        "steer.accepted",
        "hook.deny",
        "run.ended",
    }
)


def _write_harness(
    repo: Path,
    *,
    profile: str = "work",
    default: str = "grok",
    overflow: str = "kimi",
    deny: str = "[]",
    classification: str = "internal",
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                f'default = "{default}"',
                f'overflow = "{overflow}"',
                f"deny = {deny}",
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
        ),
        encoding="utf-8",
    )


@contextmanager
def _api(
    home: Path, *, workspace: Path
) -> Iterator[tuple[str, Bus, SessionStore]]:
    bus = Bus()
    store = SessionStore(home)
    server = HttpApiServer(
        ("127.0.0.1", 0),
        bus=bus,
        store=store,
        workspace_root=workspace,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/run", bus, store
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _post(url: str, payload: dict) -> tuple[int, str, str]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
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


def _sse_events(body: str) -> list[dict]:
    events: list[dict] = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def test_http_run_enqueues_and_streams_sse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with _api(home, workspace=repo) as (url, bus, _store):
        status, body, ctype = _post(
            url,
            {
                "cwd": str(repo),
                "prompt": "ship the http api",
                "taskId": "job-1",
            },
        )
    assert status == 200, body
    assert "text/event-stream" in ctype
    events = _sse_events(body)
    assert events
    types = [event["type"] for event in events]
    assert "run.started" in types
    for event in events:
        assert event["type"] in SESSION_EVENT_TYPES
        assert event["taskId"] == "job-1"
        assert "ts" in event
    blob = body
    for marker in FORBIDDEN:
        assert marker not in blob
    got = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert got is not None
    assert got.task_id == "job-1"
    assert got.cwd_hint == str(repo.resolve())
    assert got.profile == "work"
    assert got.agent == "grok"
    assert got.prompt == "ship the http api"
    assert got.permissions == "repo-only"
    assert got.overflow == "kimi"
    sessions = list((home / "sessions").glob("*.json"))
    assert len(sessions) == 1


def test_denied_policy_does_not_enqueue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo, default="kimi", deny='["kimi"]')
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with _api(home, workspace=repo) as (url, bus, _store):
        status, body, _ctype = _post(
            url,
            {
                "cwd": str(repo),
                "prompt": "should not queue",
                "taskId": "task-deny",
            },
        )
    assert status != 200
    blob = body.lower()
    for marker in FORBIDDEN:
        assert marker not in blob
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []


def test_secret_prompt_does_not_enqueue_or_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with _api(home, workspace=repo) as (url, bus, _store):
        status, body, _ctype = _post(
            url,
            {
                "cwd": str(repo),
                "prompt": "token sk-secret-value must not queue",
                "taskId": "task-secret",
            },
        )
    assert status != 200
    for marker in FORBIDDEN:
        assert marker not in body
    assert "sk-secret-value" not in body
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []


def test_unknown_agent_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with _api(home, workspace=repo) as (url, bus, _store):
        status, body, _ctype = _post(
            url,
            {
                "cwd": str(repo),
                "prompt": "unknown agent",
                "agent": "no-such-agent",
                "taskId": "task-unknown",
            },
        )
    assert status != 200
    for marker in FORBIDDEN:
        assert marker not in body
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []


def test_payload_cwd_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    outside = tmp_path / "other"
    outside.mkdir()
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with _api(home, workspace=repo) as (url, bus, _store):
        status, body, _ctype = _post(
            url,
            {
                "cwd": str(outside),
                "prompt": "stay in workspace",
                "taskId": "task-bound",
            },
        )
    assert status == 200, body
    got = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert got is not None
    assert got.cwd_hint == str(repo.resolve())
    assert got.cwd_hint != str(outside.resolve())


def _ravand(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ravand", *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=15,
    )


def test_serve_http_help_exists() -> None:
    result = _ravand("serve", "http", "--help")
    assert result.returncode == 0, result.stderr
    combined = (result.stdout + result.stderr).lower()
    assert "usage" in combined
    assert "--port" in combined
    assert str(DEFAULT_HTTP_PORT) in combined


def test_serve_http_rejects_non_local_bind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(Exception) as excinfo:
        HttpApiServer(
            ("0.0.0.0", 0),
            bus=Bus(),
            store=SessionStore(home),
            workspace_root=repo,
        )
    blob = str(excinfo.value).lower()
    assert "local" in blob or "fail closed" in blob
    for marker in FORBIDDEN:
        assert marker not in blob


def test_serve_http_entry_binds_loopback_and_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    ready = threading.Event()
    holder: dict[str, HttpApiServer] = {}
    errors: list[BaseException] = []

    def on_listen(server: HttpApiServer) -> None:
        holder["server"] = server
        ready.set()

    def _run() -> None:
        try:
            code = serve_http(
                port=0,
                workspace_root=repo,
                bus=bus,
                store=store,
                on_listen=on_listen,
            )
            if code != 0:
                errors.append(RuntimeError(f"serve_http exited {code}"))
        except BaseException as exc:  # noqa: BLE001 — capture for assert
            errors.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    assert ready.wait(timeout=5), errors
    assert not errors, errors
    server = holder["server"]
    host, bound = server.server_address
    assert host == "127.0.0.1"
    assert isinstance(bound, int) and bound > 0
    try:
        status, body, ctype = _post(
            f"http://{host}:{bound}/run",
            {
                "cwd": str(repo),
                "prompt": "serve http gateway",
                "taskId": "serve-1",
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert status == 200, body
    assert "text/event-stream" in ctype
    events = _sse_events(body)
    assert any(event["type"] == "run.started" for event in events)
    for event in events:
        assert event["type"] in SESSION_EVENT_TYPES
        assert event["taskId"] == "serve-1"
    for marker in FORBIDDEN:
        assert marker not in body
    got = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert got is not None
    assert got.task_id == "serve-1"
    assert got.cwd_hint == str(repo.resolve())


def test_serve_http_fails_closed_when_policy_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("RAVAND_HOME", str(home))
    code = serve_http(port=0, workspace_root=empty)
    assert code != 0
    assert list((home / "sessions").glob("*.json")) == []


def test_cli_serve_http_fail_closed_without_harness(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    home = tmp_path / "home"
    env = dict(os.environ)
    env["RAVAND_HOME"] = str(home)
    result = _ravand("serve", "http", "--port", "0", cwd=empty, env=env)
    assert result.returncode != 0
    blob = (result.stdout + result.stderr).lower()
    for marker in FORBIDDEN:
        assert marker not in blob
