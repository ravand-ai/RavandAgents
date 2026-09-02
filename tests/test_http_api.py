"""HTTP API: Policy then dispatch, SSE SessionEvent (GitHub issue #137)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from ravand_bus import Bus
from ravand_runtime.http_api import HttpApiServer
from ravand_sessions import SessionStore

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
def _api(home: Path) -> Iterator[tuple[str, Bus, SessionStore]]:
    bus = Bus()
    store = SessionStore(home)
    server = HttpApiServer(("127.0.0.1", 0), bus=bus, store=store)
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
    with _api(home) as (url, bus, _store):
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
    with _api(home) as (url, bus, _store):
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
    with _api(home) as (url, bus, _store):
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
    with _api(home) as (url, bus, _store):
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
