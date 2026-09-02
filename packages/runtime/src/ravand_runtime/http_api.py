"""HTTP API: accept a run, resolve Policy, enqueue, stream SSE SessionEvent."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ravand_bus import Bus, FailClosed as BusFailClosed
from ravand_policy import FailClosed
from ravand_runtime.dispatch import dispatch
from ravand_sessions import FailClosed as SessionFailClosed, SessionStore

_FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _scrub(text: str) -> str:
    for marker in _FORBIDDEN:
        if marker in text:
            return "fail closed"
    return text


def _bound_cwd(raw: str, roots: tuple[Path, ...]) -> Path:
    if not roots:
        raise FailClosed("http api has no workspace root")
    cwd = Path(raw).expanduser().resolve()
    if not cwd.is_dir():
        raise FailClosed("cwd is not a workspace")
    for root in roots:
        base = root.resolve()
        if cwd == base or cwd.is_relative_to(base):
            return cwd
    raise FailClosed("cwd is outside workspace")


class HttpApiServer(HTTPServer):
    """HTTP server that holds the bus and session store."""

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        bus: Bus,
        store: SessionStore,
        workspace_roots: list[Path],
    ) -> None:
        if not workspace_roots:
            raise FailClosed("http api has no workspace root")
        self.bus = bus
        self.store = store
        self.workspace_roots = tuple(Path(root) for root in workspace_roots)
        super().__init__(server_address, HttpApiHandler)


class HttpApiHandler(BaseHTTPRequestHandler):
    """POST /run: Policy, dispatch, SSE SessionEvent."""

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        self._fail(403, "fail closed")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path != "/run":
            self._fail(403, "fail closed")
            return
        length_raw = self.headers.get("Content-Length")
        if not length_raw:
            self._fail(400, "fail closed")
            return
        try:
            length = int(length_raw)
        except ValueError:
            self._fail(400, "fail closed")
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._fail(400, "fail closed")
            return
        if not isinstance(payload, dict):
            self._fail(400, "fail closed")
            return
        cwd_raw = payload.get("cwd")
        prompt = payload.get("prompt")
        if not isinstance(cwd_raw, str) or not cwd_raw.strip():
            self._fail(400, "fail closed")
            return
        if not isinstance(prompt, str) or not prompt.strip():
            self._fail(400, "fail closed")
            return
        task_id = payload.get("taskId")
        if task_id is None or task_id == "":
            task_id = str(uuid.uuid4())
        elif not isinstance(task_id, str):
            self._fail(400, "fail closed")
            return
        agent = payload.get("agent")
        profile = payload.get("profile")
        account = payload.get("account")
        if agent is not None and not isinstance(agent, str):
            self._fail(400, "fail closed")
            return
        if profile is not None and not isinstance(profile, str):
            self._fail(400, "fail closed")
            return
        if account is not None and not isinstance(account, str):
            self._fail(400, "fail closed")
            return
        server = self.server
        if not isinstance(server, HttpApiServer):
            self._fail(403, "fail closed")
            return
        try:
            cwd = _bound_cwd(cwd_raw, server.workspace_roots)
            record = dispatch(
                cwd,
                prompt,
                bus=server.bus,
                store=server.store,
                task_id=task_id,
                profile_override=profile,
                agent_override=agent,
                account_override=account,
            )
        except (FailClosed, BusFailClosed, SessionFailClosed) as exc:
            self._fail(403, _scrub(str(exc)))
            return
        event = {
            "ts": _now_iso(),
            "taskId": record.task_id,
            "type": "run.started",
        }
        blob = json.dumps(event, separators=(",", ":"))
        data = f"data: {blob}\n\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _fail(self, code: int, message: str) -> None:
        payload = json.dumps(
            {"error": _scrub(message)}, separators=(",", ":")
        ).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
