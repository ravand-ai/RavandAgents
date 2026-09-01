"""Operator TTY: status header + streamed run. Not a coding TUI."""

from __future__ import annotations

import sys
from pathlib import Path

from ravand_cli.ask import confirm_permission, should_ask
from ravand_cli.status import run_status
from ravand_policy import PolicyDenied, UnknownAgent, resolve
from ravand_runtime import audit_agent_denied, run_prompt


def run_tui(cwd: Path) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "ravand tui needs a TTY. Use: ravand run --format jsonl",
            file=sys.stderr,
        )
        return 2

    cwd = cwd.resolve()
    run_status(cwd)
    print("q to quit. Permissions: y/N.", file=sys.stderr)

    yes = False
    ask = None
    if should_ask(yes=yes, is_tty=True):
        ask = confirm_permission

    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        prompt = line.strip()
        if not prompt:
            continue
        if prompt in {"q", "quit", "exit"}:
            return 0
        try:
            policy = resolve(cwd)
        except PolicyDenied as exc:
            audit_agent_denied(str(exc), cwd=cwd)
            print(str(exc), file=sys.stderr)
            continue
        except UnknownAgent as exc:
            print(str(exc), file=sys.stderr)
            continue

        def sink(event: dict) -> None:
            kind = event.get("type")
            if kind == "text.delta":
                print(event.get("text") or "", end="", flush=True)
            elif kind == "run.ended":
                print()
                status = event.get("status") or ""
                if status:
                    print(f"[{status}]", file=sys.stderr)

        run_prompt(policy, prompt, cwd=cwd, sink=sink, ask=ask, yes=yes)
