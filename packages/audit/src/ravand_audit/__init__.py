"""Append-only audit log: ~/.ravand/audit.jsonl per SCHEMA.md."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUDIT_TYPES = frozenset(
    {
        "run.started",
        "run.ended",
        "agent.selected",
        "agent.denied",
        "agent.overflow",
        "permission.allow",
        "permission.deny",
        "auth.missing",
        "profile.mismatch",
        "worker.capability_miss",
        "worker.cordoned",
        "trigger.denied",
        "plan.allow",
        "plan.deny",
        "steer.accepted",
        "hook.deny",
    }
)

_COOKIE_MARKERS = ("cookies", ".grok/", ".kimi/", ".cursor/")
def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _audit_bodies_enabled() -> bool:
    return os.environ.get("RAVAND_AUDIT_BODIES", "").strip() in {"1", "true", "yes"}


def _scrub_detail(detail: str | None, *, profile: str | None) -> str | None:
    if detail is None:
        return None
    lowered = detail.lower()
    for marker in _COOKIE_MARKERS:
        if marker in lowered:
            return "[redacted]"
    if profile == "work" and not _audit_bodies_enabled():
        return "[redacted]"
    return detail


class AuditLog:
    """Append audit events as JSONL. Never writes cookie contents."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def path(self) -> Path:
        return self._root / "audit.jsonl"

    def emit(
        self,
        event_type: str,
        *,
        task_id: str,
        profile: str | None = None,
        agent: str | None = None,
        cwd: str | None = None,
        policy_hash: str | None = None,
        detail: str | None = None,
    ) -> None:
        if event_type not in AUDIT_TYPES:
            raise ValueError(f"unknown audit event type: {event_type!r}")
        event: dict[str, Any] = {
            "ts": _now_iso(),
            "type": event_type,
            "taskId": task_id,
        }
        if profile is not None:
            event["profile"] = profile
        if agent is not None:
            event["agent"] = agent
        if cwd is not None:
            event["cwd"] = cwd
        if policy_hash is not None:
            event["policyHash"] = policy_hash
        scrubbed = _scrub_detail(detail, profile=profile)
        if scrubbed is not None:
            event["detail"] = scrubbed
        self._root.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
