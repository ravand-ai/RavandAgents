"""Slice 5 TDD: OTel no-op tracer and OTLP/HTTP JSON exporter."""

from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from ravand_policy import resolve
from ravand_runtime.otel import Tracer
from ravand_runtime.run import run_prompt

RESULTS = ("ok", "overflow", "rate_limit", "auth_missing", "crash", "denied")
FORBIDDEN = ("sk-", "xai-", "Bearer", "cookie")
SCHEMA_ATTRS = {
    "gen_ai.operation.name",
    "gen_ai.agent.name",
    "gen_ai.conversation.id",
    "ravand.task_id",
    "ravand.profile",
    "ravand.host",
    "ravand.overflow_of",
    "ravand.policy_hash",
}

ROOT_KW = {
    "agent": "grok",
    "task_id": "task_1",
    "profile": "work",
    "conversation_id": "acp-session-1",
    "policy_hash": "sha256:abc",
    "host": "devbox",
}

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"


def _write_fake_harness(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    fake = json.dumps([sys.executable, str(FAKE)])
    (repo / "harness.toml").write_text(
        "\n".join(
            [
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
        ),
        encoding="utf-8",
    )


def _run_fake(
    repo: Path,
    prompt: str,
    *,
    tracer: Tracer | None = None,
) -> tuple[int, list[dict]]:
    events: list[dict] = []
    policy = resolve(repo)
    kwargs: dict = {
        "cwd": repo,
        "sink": events.append,
    }
    if tracer is not None:
        kwargs["tracer"] = tracer
    code = run_prompt(policy, prompt, **kwargs)
    return code, events


class _CaptureHandler(BaseHTTPRequestHandler):
    posts: list[tuple[str, dict[str, str], bytes]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        type(self).posts.append(
            (self.path, {k.lower(): v for k, v in self.headers.items()}, body)
        )
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        pass


@pytest.fixture
def listener():
    _CaptureHandler.posts = []
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}", _CaptureHandler.posts
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _spans(body: bytes) -> list[dict]:
    payload = json.loads(body.decode("utf-8"))
    out: list[dict] = []
    for resource in payload["resourceSpans"]:
        for scope in resource["scopeSpans"]:
            out.extend(scope["spans"])
    return out


def _attrs(span: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for attr in span.get("attributes", []):
        value = attr["value"]
        result[attr["key"]] = next(iter(value.values()))
    return result


def test_noop_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not POST when endpoint is unset")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    tracer = Tracer.from_env()
    for result in RESULTS:
        with tracer.invoke_agent(**ROOT_KW):
            with tracer.execute_tool(name="WebFetch"):
                pass
            tracer.record_result(result)

    assert len(tracer.metrics.durations) == len(RESULTS)
    assert all(d >= 0 for d in tracer.metrics.durations)
    for result in RESULTS:
        assert tracer.metrics.results[result] == 1


def test_otlp_post_when_env_set(
    monkeypatch: pytest.MonkeyPatch, listener: tuple[str, list]
) -> None:
    endpoint, posts = listener
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)

    tracer = Tracer.from_env()
    with tracer.invoke_agent(**ROOT_KW, overflow_of="prev-run-id") as span:
        assert span is not None
        with tracer.execute_tool(name="WebFetch"):
            pass
        tracer.record_result("ok")

    assert len(posts) == 1
    path, headers, body = posts[0]
    assert path == "/v1/traces"
    assert headers["content-type"] == "application/json"

    spans = _spans(body)
    by_name = {s["name"]: s for s in spans}
    assert "invoke_agent" in by_name
    assert "execute_tool" in by_name

    root = by_name["invoke_agent"]
    tool = by_name["execute_tool"]
    assert tool["parentSpanId"] == root["spanId"]
    assert tool["traceId"] == root["traceId"]

    attrs = _attrs(root)
    assert set(attrs) <= SCHEMA_ATTRS
    assert attrs["gen_ai.operation.name"] == "invoke_agent"
    assert attrs["gen_ai.agent.name"] == "grok"
    assert attrs["gen_ai.conversation.id"] == "acp-session-1"
    assert attrs["ravand.task_id"] == "task_1"
    assert attrs["ravand.profile"] == "work"
    assert attrs["ravand.host"] == "devbox"
    assert attrs["ravand.policy_hash"] == "sha256:abc"
    assert attrs["ravand.overflow_of"] == "prev-run-id"

    assert tracer.metrics.results["ok"] == 1
    assert len(tracer.metrics.durations) == 1


def test_overflow_of_omitted_when_none(
    monkeypatch: pytest.MonkeyPatch, listener: tuple[str, list]
) -> None:
    endpoint, posts = listener
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)

    tracer = Tracer.from_env()
    with tracer.invoke_agent(**ROOT_KW, overflow_of=None):
        tracer.record_result("ok")

    (root,) = [s for s in _spans(posts[0][2]) if s["name"] == "invoke_agent"]
    assert "ravand.overflow_of" not in _attrs(root)


def test_export_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    # Grab a free port, then release it so the connection is refused.
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    host, port = server.server_address
    server.server_close()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://{host}:{port}")

    tracer = Tracer.from_env()
    with tracer.invoke_agent(**ROOT_KW):
        tracer.record_result("ok")

    assert tracer.export_errors == 1
    assert tracer.metrics.results["ok"] == 1


def test_no_secrets_in_export(
    monkeypatch: pytest.MonkeyPatch, listener: tuple[str, list]
) -> None:
    endpoint, posts = listener
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)

    tracer = Tracer.from_env()
    with tracer.invoke_agent(**ROOT_KW):
        with tracer.execute_tool(name="WebFetch"):
            pass
        tracer.record_result("ok")

    assert posts
    body = posts[0][2].decode("utf-8")
    for marker in FORBIDDEN:
        assert marker not in body


def test_fake_run_records_in_process_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_fake_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    tracer = Tracer.from_env()
    code, events = _run_fake(repo, "say hi", tracer=tracer)
    assert code == 0
    assert tracer.metrics.results["ok"] == 1
    assert len(tracer.metrics.durations) == 1
    assert tracer.metrics.durations[0] >= 0
    types = [e["type"] for e in events]
    assert "run.started" in types
    assert "tool.call" in types
    assert "run.ended" in types


def test_fake_run_exports_invoke_agent_and_execute_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listener: tuple[str, list]
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_fake_harness(repo)
    endpoint, posts = listener
    monkeypatch.setenv("RAVAND_HOME", str(home))
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)

    code, events = _run_fake(repo, "say hi")
    assert code == 0
    assert events[-1]["type"] == "run.ended"
    assert events[-1]["status"] == "ok"
    assert posts

    spans = _spans(posts[0][2])
    by_name = {s["name"]: s for s in spans}
    assert "invoke_agent" in by_name
    assert "execute_tool" in by_name

    root = by_name["invoke_agent"]
    tool = by_name["execute_tool"]
    assert tool["parentSpanId"] == root["spanId"]
    assert tool["traceId"] == root["traceId"]

    attrs = _attrs(root)
    assert set(attrs) <= SCHEMA_ATTRS
    assert attrs["gen_ai.operation.name"] == "invoke_agent"
    assert attrs["gen_ai.agent.name"] == "fake"
    assert attrs["gen_ai.conversation.id"] == "sess-test"
    assert attrs["ravand.task_id"]
    assert attrs["ravand.profile"] == "work"
    assert attrs["ravand.host"] == socket.gethostname()
    assert attrs["ravand.policy_hash"].startswith("sha256:")
    assert "ravand.overflow_of" not in attrs

    tool_attrs = _attrs(tool)
    assert tool_attrs["gen_ai.operation.name"] == "execute_tool"
    assert tool_attrs["gen_ai.tool.name"] == "Read AGENTS.md"


def test_fake_run_export_failure_does_not_crash_jsonl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_fake_harness(repo)
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    host, port = server.server_address
    server.server_close()
    monkeypatch.setenv("RAVAND_HOME", str(home))
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://{host}:{port}")

    code, events = _run_fake(repo, "say hi")
    assert code == 0
    types = [e["type"] for e in events]
    assert "run.started" in types
    assert "text.delta" in types
    assert events[-1]["type"] == "run.ended"
    assert events[-1]["status"] == "ok"
    blob = json.dumps(events)
    for marker in FORBIDDEN:
        assert marker not in blob


def test_fake_run_spans_have_no_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listener: tuple[str, list]
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_fake_harness(repo)
    endpoint, posts = listener
    monkeypatch.setenv("RAVAND_HOME", str(home))
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)

    code, _events = _run_fake(repo, "say hi")
    assert code == 0
    assert posts
    body = posts[0][2].decode("utf-8")
    for marker in FORBIDDEN:
        assert marker not in body
    for span in _spans(posts[0][2]):
        if span["name"] == "invoke_agent":
            assert set(_attrs(span)) <= SCHEMA_ATTRS
