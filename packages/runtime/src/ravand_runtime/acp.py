"""ACP JSON-RPC over stdio. Content-Length framing. Stdlib only."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any


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
    advertised method succeeds.
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
            client.request_with_handlers("authenticate", {"methodId": method_id})
            return
        except AcpError:
            continue
    raise AuthRequired(agent)


class AcpClient:
    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        self._proc = proc
        self._next_id = 1

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

    def _read(self) -> dict[str, Any] | None:
        assert self._proc.stdout is not None
        line = self._proc.stdout.readline()
        if not line:
            return None
        if line.lower().startswith(b"content-length"):
            n = int(line.split(b":")[1])
            while True:
                blank = self._proc.stdout.readline()
                if blank in (b"\r\n", b"\n", b""):
                    break
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
    ) -> dict[str, Any]:
        rid = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            msg = self._read()
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
