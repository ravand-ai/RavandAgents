"""ACP JSON-RPC over stdio. Content-Length framing. Stdlib only."""

from __future__ import annotations

import json
import os
import select
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

_DEFAULT_HANDSHAKE_TIMEOUT = 30.0
_HANDSHAKE_METHODS = frozenset({"initialize", "authenticate"})


class AcpError(Exception):
    pass


class AuthRequired(Exception):
    """Agent requires login; no cached credential satisfied the handshake."""

    def __init__(self, agent: str) -> None:
        super().__init__(f"agent {agent!r} requires authentication")
        self.agent = agent
        self.exit_code = 2


def is_auth_error(exc: AcpError) -> bool:
    """True when a JSON-RPC error is the ACP auth-required signal."""
    text = str(exc).lower()
    return "-32000" in text or "authentication required" in text


def _handshake_timeout_sec() -> float:
    raw = os.environ.get("RAVAND_ACP_HANDSHAKE_TIMEOUT")
    if raw is None or raw == "":
        return _DEFAULT_HANDSHAKE_TIMEOUT
    return float(raw)


def ensure_authenticated(
    client: AcpClient,
    init_result: dict[str, Any],
    *,
    agent: str,
) -> None:
    """ACP handshake step 3: authenticate when the agent advertises authMethods.

    Tries the advertised ``cached_token`` method (existing session) first,
    then any other advertised method id. Only method ids are sent; token
    material is never read, sent, or logged. Raises AuthRequired when no
    advertised method succeeds, or when authenticate times out.
    """
    methods = init_result.get("authMethods") or []
    ids: list[str] = []
    for method in methods:
        if isinstance(method, dict) and method.get("id"):
            ids.append(str(method["id"]))
    if not ids:
        return
    candidates = ["cached_token", *[mid for mid in ids if mid != "cached_token"]]
    for method_id in candidates:
        try:
            client.request_with_handlers(
                "authenticate",
                {"methodId": method_id},
                agent=agent,
            )
            return
        except AuthRequired:
            raise
        except AcpError:
            continue
    raise AuthRequired(agent)


_STDERR_DRAIN_CHUNK = 65536


def _start_stderr_drain(proc: subprocess.Popen[bytes]) -> None:
    if proc.stderr is None:
        return

    def _drain() -> None:
        assert proc.stderr is not None
        while True:
            chunk = proc.stderr.read(_STDERR_DRAIN_CHUNK)
            if not chunk:
                break

    threading.Thread(target=_drain, daemon=True).start()


class AcpClient:
    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        self._proc = proc
        self._next_id = 1
        _start_stderr_drain(proc)

    def close(self) -> None:
        if self._proc.stdin:
            self._proc.stdin.close()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()

    def _send(self, msg: dict[str, Any]) -> None:
        raw = json.dumps(msg, separators=(",", ":")) + "\n"
        assert self._proc.stdin is not None
        self._proc.stdin.write(raw.encode())
        self._proc.stdin.flush()

    def _wait_readable(self, deadline: float | None) -> None:
        if deadline is None:
            return
        assert self._proc.stdout is not None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("ACP handshake timed out")
        ready, _, _ = select.select([self._proc.stdout], [], [], remaining)
        if not ready:
            raise TimeoutError("ACP handshake timed out")

    def _read(self, *, deadline: float | None = None) -> dict[str, Any] | None:
        assert self._proc.stdout is not None
        self._wait_readable(deadline)
        line = self._proc.stdout.readline()
        if not line:
            return None
        if line.lower().startswith(b"content-length"):
            n = int(line.split(b":")[1])
            while True:
                self._wait_readable(deadline)
                blank = self._proc.stdout.readline()
                if blank in (b"\r\n", b"\n", b""):
                    break
            self._wait_readable(deadline)
            raw = self._proc.stdout.read(n)
            return json.loads(raw.decode())
        return json.loads(line.decode())

    def request_with_handlers(
        self,
        method: str,
        params: dict[str, Any],
        *,
        on_update: Callable[[dict[str, Any]], None] | None = None,
        on_permission: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        agent: str = "",
    ) -> dict[str, Any]:
        rid = self._next_id
        self._next_id += 1
        deadline: float | None = None
        if method in _HANDSHAKE_METHODS:
            deadline = time.monotonic() + _handshake_timeout_sec()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            try:
                msg = self._read(deadline=deadline)
            except TimeoutError as exc:
                raise AuthRequired(agent) from exc
            if msg is None:
                raise AcpError(f"EOF waiting for {method}")
            if msg.get("id") == rid and "result" in msg:
                return msg["result"]
            if msg.get("id") == rid and "error" in msg:
                raise AcpError(str(msg["error"]))
            if msg.get("method") == "session/request_permission":
                if on_permission is None:
                    raise AcpError("permission requested")
                reply = on_permission(msg)
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": reply})
                continue
            if msg.get("method") == "session/update" and on_update:
                on_update(msg)
                continue


def spawn(command: list[str], *, cwd: Path, home: str) -> AcpClient:
    env = os.environ.copy()
    env["HOME"] = home
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd),
        env=env,
    )
    return AcpClient(proc)
