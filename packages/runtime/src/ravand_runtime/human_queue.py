"""Human verification queue: named approver, timeout deny. Fail closed."""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ravand_audit import AuditLog
from ravand_policy import FailClosed

_KINDS = frozenset({"permission", "plan"})
_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(?:sk-|xai-|Bearer)")
_COOKIE_MARKERS = ("cookies", ".grok/", ".kimi/", ".cursor/", ".claude")


def _refuse_secrets(text: str) -> None:
    if _TOKEN_RE.search(text):
        raise FailClosed("human queue refuses tokens")
    lowered = text.lower()
    for marker in _COOKIE_MARKERS:
        if marker in lowered:
            raise FailClosed("human queue refuses cookie paths")


@dataclass
class HumanRequest:
    id: str
    task_id: str
    kind: str
    detail: str
    approver: str
    timeout_sec: float
    created_at: float
    status: str
    profile: str | None = None
    agent: str | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "taskId": self.task_id,
            "kind": self.kind,
            "detail": self.detail,
            "approver": self.approver,
            "timeoutSec": self.timeout_sec,
            "createdAt": self.created_at,
            "status": self.status,
        }
        if self.profile is not None:
            payload["profile"] = self.profile
        if self.agent is not None:
            payload["agent"] = self.agent
        return payload

    @classmethod
    def from_json(cls, data: dict[str, object]) -> HumanRequest:
        return cls(
            id=str(data["id"]),
            task_id=str(data["taskId"]),
            kind=str(data["kind"]),
            detail=str(data["detail"]),
            approver=str(data["approver"]),
            timeout_sec=float(str(data["timeoutSec"])),
            created_at=float(str(data["createdAt"])),
            status=str(data["status"]),
            profile=str(data["profile"]) if data.get("profile") is not None else None,
            agent=str(data["agent"]) if data.get("agent") is not None else None,
        )


class HumanQueue:
    """File queue under isolated HOME. Named approver must match. Timeout is deny."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], float] | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._root = root
        self._clock = clock or time.time
        self._audit = audit if audit is not None else AuditLog(root)

    def _dir(self) -> Path:
        path = self._root / "human-queue"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _path_for(self, item_id: str) -> Path:
        return self._dir() / f"{item_id}.json"

    def _write(self, item: HumanRequest) -> None:
        path = self._path_for(item.id)
        payload = json.dumps(item.to_json(), separators=(",", ":"))
        _refuse_secrets(payload)
        path.write_text(payload + "\n", encoding="utf-8")

    def _load(self, item_id: str) -> HumanRequest:
        path = self._path_for(item_id)
        if not path.is_file():
            raise FailClosed(f"unknown human request {item_id!r}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise FailClosed("human request is invalid")
        return HumanRequest.from_json(data)

    def _expired(self, item: HumanRequest) -> bool:
        now = self._clock()
        # Wall clock can jump backwards (NTP). Fail closed: cannot prove still in window.
        if now < item.created_at:
            return True
        return now >= item.created_at + item.timeout_sec

    def _audit_decision(self, item: HumanRequest, *, allowed: bool) -> None:
        event_type = f"{item.kind}.allow" if allowed else f"{item.kind}.deny"
        self._audit.emit(
            event_type,
            task_id=item.task_id,
            profile=item.profile,
            agent=item.agent,
            detail=item.detail,
        )

    def _timeout_deny(self, item: HumanRequest) -> bool:
        if item.status == "allow":
            return True
        if item.status == "deny":
            return False
        item.status = "deny"
        self._write(item)
        self._audit_decision(item, allowed=False)
        return False

    def enqueue(
        self,
        *,
        kind: str,
        task_id: str,
        detail: str,
        approver: str,
        timeout_sec: float,
        profile: str | None = None,
        agent: str | None = None,
    ) -> HumanRequest:
        if kind not in _KINDS:
            raise FailClosed(f"unknown human kind {kind!r}")
        if not isinstance(task_id, str) or not task_id.strip():
            raise FailClosed("human request task_id is invalid")
        if not isinstance(detail, str) or not detail.strip():
            raise FailClosed("human request detail is invalid")
        if not isinstance(approver, str) or not approver.strip():
            raise FailClosed("human request approver is invalid")
        if not isinstance(timeout_sec, (int, float)) or timeout_sec < 0:
            raise FailClosed("human request timeout is invalid")
        _refuse_secrets(task_id)
        _refuse_secrets(detail)
        _refuse_secrets(approver)
        if profile is not None:
            _refuse_secrets(profile)
        if agent is not None:
            _refuse_secrets(agent)
        item = HumanRequest(
            id=str(uuid.uuid4()),
            task_id=task_id,
            kind=kind,
            detail=detail,
            approver=approver,
            timeout_sec=float(timeout_sec),
            created_at=self._clock(),
            status="pending",
            profile=profile,
            agent=agent,
        )
        self._write(item)
        return item

    def decide(self, item_id: str, *, actor: str, allow: bool) -> bool:
        if not isinstance(actor, str) or not actor.strip():
            raise FailClosed("human request actor is invalid")
        _refuse_secrets(actor)
        item = self._load(item_id)
        if item.status == "allow":
            return True
        if item.status == "deny":
            return False
        if self._expired(item):
            return self._timeout_deny(item)
        if actor != item.approver:
            raise FailClosed(
                f"approver {actor!r} does not match {item.approver!r}"
            )
        item.status = "allow" if allow else "deny"
        self._write(item)
        self._audit_decision(item, allowed=allow)
        return allow

    def wait(self, item_id: str) -> bool:
        item = self._load(item_id)
        if item.status == "allow":
            return True
        if item.status == "deny":
            return False
        if self._expired(item):
            return self._timeout_deny(item)
        raise FailClosed("human verification is still pending")

    def ask_permission(
        self,
        detail: str,
        *,
        task_id: str,
        approver: str,
        timeout_sec: float = 0,
        profile: str | None = None,
        agent: str | None = None,
    ) -> bool:
        item = self.enqueue(
            kind="permission",
            task_id=task_id,
            detail=detail,
            approver=approver,
            timeout_sec=timeout_sec,
            profile=profile,
            agent=agent,
        )
        return self.wait(item.id)

    def ask_plan(
        self,
        detail: str,
        *,
        task_id: str,
        approver: str,
        timeout_sec: float = 0,
        profile: str | None = None,
        agent: str | None = None,
    ) -> bool:
        item = self.enqueue(
            kind="plan",
            task_id=task_id,
            detail=detail,
            approver=approver,
            timeout_sec=timeout_sec,
            profile=profile,
            agent=agent,
        )
        return self.wait(item.id)
