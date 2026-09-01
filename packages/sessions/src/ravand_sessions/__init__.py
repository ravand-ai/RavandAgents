"""Session store: ~/.ravand/sessions/<id>.json per SCHEMA.md."""

from __future__ import annotations

import json
import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SessionStatus = str


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class SessionRecord:
    id: str
    task_id: str
    cwd: str
    profile: str
    agent: str
    command: list[str]
    status: SessionStatus
    created_at: str
    acp_session_id: str | None = None
    repo: str | None = None
    overflow_of: str | None = None
    ended_at: str | None = None
    host: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "taskId": self.task_id,
            "cwd": self.cwd,
            "profile": self.profile,
            "agent": self.agent,
            "command": self.command,
            "status": self.status,
            "createdAt": self.created_at,
        }
        if self.acp_session_id is not None:
            payload["acpSessionId"] = self.acp_session_id
        if self.repo is not None:
            payload["repo"] = self.repo
        if self.overflow_of is not None:
            payload["overflowOf"] = self.overflow_of
        if self.ended_at is not None:
            payload["endedAt"] = self.ended_at
        if self.host is not None:
            payload["host"] = self.host
        return payload

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SessionRecord:
        return cls(
            id=str(data["id"]),
            task_id=str(data["taskId"]),
            cwd=str(data["cwd"]),
            profile=str(data["profile"]),
            agent=str(data["agent"]),
            command=[str(part) for part in data.get("command", [])],
            status=str(data["status"]),
            created_at=str(data["createdAt"]),
            acp_session_id=data.get("acpSessionId"),
            repo=data.get("repo"),
            overflow_of=data.get("overflowOf"),
            ended_at=data.get("endedAt"),
            host=data.get("host"),
        )


class SessionStore:
    """Write SessionRecord JSON files under <root>/sessions/."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _sessions_dir(self) -> Path:
        path = self._root / "sessions"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _path_for(self, session_id: str) -> Path:
        return self._sessions_dir() / f"{session_id}.json"

    def write(self, record: SessionRecord) -> Path:
        path = self._path_for(record.id)
        path.write_text(
            json.dumps(record.to_json(), indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def load(self, session_id: str) -> SessionRecord:
        data = json.loads(self._path_for(session_id).read_text(encoding="utf-8"))
        return SessionRecord.from_json(data)

    def start(
        self,
        *,
        task_id: str,
        cwd: str,
        profile: str,
        agent: str,
        command: list[str],
        repo: str | None = None,
        overflow_of: str | None = None,
    ) -> SessionRecord:
        record = SessionRecord(
            id=str(uuid.uuid4()),
            task_id=task_id,
            cwd=cwd,
            profile=profile,
            agent=agent,
            command=command,
            status="running",
            created_at=_now_iso(),
            repo=repo,
            overflow_of=overflow_of,
            host=socket.gethostname(),
        )
        self.write(record)
        return record

    def finish(
        self,
        session_id: str,
        *,
        status: SessionStatus,
        acp_session_id: str | None = None,
    ) -> SessionRecord:
        record = self.load(session_id)
        record.status = status
        record.ended_at = _now_iso()
        if acp_session_id is not None:
            record.acp_session_id = acp_session_id
        self.write(record)
        return record
