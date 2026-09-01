"""OTel spans: no-op by default, OTLP/HTTP JSON when the env endpoint is set.

Stdlib only. No opentelemetry import. If OTEL_EXPORTER_OTLP_ENDPOINT is
unset, nothing is POSTed; in-process metrics still record duration and the
result enum. Export failures never raise to the caller.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.request
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit

_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"

_VALID_RESULTS = frozenset(
    {"ok", "overflow", "rate_limit", "auth_missing", "crash", "denied"}
)


class Metrics:
    """In-process counters, kept even when no OTLP endpoint is set."""

    def __init__(self) -> None:
        self.durations: list[float] = []
        self.results: Counter[str] = Counter()

    def record(self, *, duration_s: float, result: str) -> None:
        self.durations.append(duration_s)
        self.results[result] += 1


def _span_id() -> str:
    return f"{random.getrandbits(64):016x}"


def _trace_id() -> str:
    return f"{random.getrandbits(128):032x}"


def _attr(key: str, value: str) -> dict[str, Any]:
    return {"key": key, "value": {"stringValue": value}}


class _Span:
    def __init__(
        self,
        name: str,
        attributes: dict[str, str],
        *,
        trace_id: str,
        parent_id: str | None,
    ) -> None:
        self.name = name
        self.attributes = attributes
        self.trace_id = trace_id
        self.span_id = _span_id()
        self.parent_id = parent_id
        self.start_ns = time.time_ns()
        self.end_ns = self.start_ns

    def finish(self) -> None:
        self.end_ns = time.time_ns()

    def to_otlp(self) -> dict[str, Any]:
        span: dict[str, Any] = {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "name": self.name,
            "startTimeUnixNano": str(self.start_ns),
            "endTimeUnixNano": str(self.end_ns),
            "attributes": [_attr(k, v) for k, v in self.attributes.items()],
        }
        if self.parent_id:
            span["parentSpanId"] = self.parent_id
        return span


class _NoopExporter:
    def export(self, _spans: list[_Span]) -> None:
        return


class _OtlpHttpExporter:
    """POST OTLP/HTTP JSON to {endpoint}/v1/traces via stdlib urllib."""

    def __init__(self, endpoint: str) -> None:
        endpoint = endpoint.rstrip("/")
        if urlsplit(endpoint).path in ("", "/"):
            endpoint = endpoint + "/v1/traces"
        self.url = endpoint

    def export(self, spans: list[_Span]) -> None:
        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [_attr("service.name", "ravand")]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "ravand-runtime"},
                            "spans": [s.to_otlp() for s in spans],
                        }
                    ],
                }
            ]
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5):
            pass


class _InvokeAgentSpan:
    def __init__(self, tracer: Tracer, span: _Span) -> None:
        self._tracer = tracer
        self._span = span
        self._start = time.monotonic()

    def __enter__(self) -> _Span:
        self._tracer._stack.append(self._span)
        return self._span

    def __exit__(self, exc_type: object, *_exc: object) -> bool:
        self._tracer._stack.pop()
        result = self._tracer._pending_result
        if result is None:
            result = "crash" if exc_type is not None else "ok"
        self._tracer._pending_result = None
        duration_s = time.monotonic() - self._start
        self._tracer.metrics.record(duration_s=duration_s, result=result)
        # Root span ends last so it encloses every tool span.
        self._span.finish()
        self._tracer._export([self._span, *self._tracer._children])
        self._tracer._children = []
        return False


class Tracer:
    """Root span invoke_agent, child execute_tool. Not thread-safe."""

    def __init__(self, exporter: _NoopExporter | _OtlpHttpExporter) -> None:
        self._exporter = exporter
        self._stack: list[_Span] = []
        self._children: list[_Span] = []
        self._pending_result: str | None = None
        self.metrics = Metrics()
        self.export_errors = 0

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Tracer:
        env = os.environ if environ is None else environ
        endpoint = env.get(_ENV, "").strip()
        if endpoint:
            return cls(_OtlpHttpExporter(endpoint))
        return cls(_NoopExporter())

    def _export(self, spans: list[_Span]) -> None:
        try:
            self._exporter.export(spans)
        except Exception:
            self.export_errors += 1

    def invoke_agent(
        self,
        *,
        agent: str,
        task_id: str,
        profile: str,
        conversation_id: str,
        policy_hash: str,
        host: str,
        overflow_of: str | None = None,
    ) -> _InvokeAgentSpan:
        attributes = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": agent,
            "gen_ai.conversation.id": conversation_id,
            "ravand.task_id": task_id,
            "ravand.profile": profile,
            "ravand.host": host,
            "ravand.policy_hash": policy_hash,
        }
        if overflow_of is not None:
            attributes["ravand.overflow_of"] = overflow_of
        span = _Span("invoke_agent", attributes, trace_id=_trace_id(), parent_id=None)
        return _InvokeAgentSpan(self, span)

    @contextmanager
    def execute_tool(self, *, name: str) -> Iterator[_Span]:
        parent = self._stack[-1] if self._stack else None
        span = _Span(
            "execute_tool",
            {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": name,
            },
            trace_id=parent.trace_id if parent else _trace_id(),
            parent_id=parent.span_id if parent else None,
        )
        try:
            yield span
        finally:
            span.finish()
            self._children.append(span)

    def record_result(self, result: str) -> None:
        if result not in _VALID_RESULTS:
            raise ValueError(f"unknown result enum: {result}")
        self._pending_result = result
