"""Run one ACP prompt and emit SessionEvent dicts."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ravand_permissions import decide_repo_only
from ravand_policy import ResolvedPolicy
from ravand_profile import ensure_profile_home
from ravand_runtime.acp import spawn

EventSink = Callable[[dict[str, Any]], None]


def _emit(sink: EventSink, event: dict[str, Any]) -> None:
    sink(event)


def run_prompt(
    policy: ResolvedPolicy,
    prompt: str,
    *,
    cwd: Path,
    sink: EventSink,
) -> int:
    cwd = cwd.resolve()
    ensure_profile_home(policy.home)
    _emit(sink, {"type": "run.started", "profile": policy.profile, "agent": policy.agent})
    client = spawn(policy.command, cwd=cwd, home=policy.home)
    try:
        client.request_with_handlers("initialize", {"protocolVersion": 1})
        session = client.request_with_handlers(
            "session/new",
            {"cwd": str(cwd), "mcpServers": []},
        )
        session_id = session.get("sessionId")

        def on_update(msg: dict[str, Any]) -> None:
            update = (msg.get("params") or {}).get("update") or {}
            content = update.get("content") or {}
            text = content.get("text")
            if text:
                _emit(sink, {"type": "text.delta", "text": text})

        def on_permission(msg: dict[str, Any]) -> dict[str, Any]:
            params = msg.get("params") or {}
            tool = params.get("toolCall") or {}
            decision = decide_repo_only(tool, str(cwd))
            _emit(
                sink,
                {
                    "type": "permission.ask",
                    "tool": tool.get("title") or tool.get("kind"),
                    "text": json.dumps(tool.get("rawInput") or {}),
                },
            )
            option = "deny" if decision == "deny" else "allow"
            return {
                "outcome": {
                    "outcome": "selected",
                    "optionId": option,
                }
            }

        client.request_with_handlers(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt}],
            },
            on_update=on_update,
            on_permission=on_permission,
        )
        try:
            client.request_with_handlers("session/close", {"sessionId": session_id})
        except Exception:
            pass
        _emit(sink, {"type": "run.ended", "status": "ok"})
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        _emit(sink, {"type": "run.ended", "status": "error"})
        return 5
    finally:
        client.close()
