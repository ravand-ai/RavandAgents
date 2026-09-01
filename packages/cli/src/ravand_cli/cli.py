"""ravand CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ravand_policy import PolicyDenied, UnknownAgent, resolve
from ravand_profile import ensure_profile_home
from ravand_registry import login_hint
from ravand_runtime import run_prompt

NOT_IMPLEMENTED = "not implemented"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ravand")
    sub = parser.add_subparsers(dest="command")
    which = sub.add_parser("which", help="resolve agent and profile for cwd")
    which.add_argument("--profile", dest="profile_override")
    which.add_argument("-a", "--agent", dest="agent_override")
    run = sub.add_parser("run", help="spawn the selected ACP agent")
    run.add_argument("prompt", nargs="?")
    run.add_argument("-a", "--agent", dest="agent_override")
    run.add_argument("--format", choices=["jsonl", "text"], default="jsonl")
    login = sub.add_parser("login", help="print vendor login hints")
    login.add_argument("profile", nargs="?", default=None)
    sub.add_parser("status", help="login doctor")
    return parser


def _which(args: argparse.Namespace) -> int:
    try:
        policy = resolve(
            Path.cwd(),
            profile_override=getattr(args, "profile_override", None),
            agent_override=getattr(args, "agent_override", None),
        )
    except PolicyDenied as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except UnknownAgent as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    ensure_profile_home(policy.home)
    payload = {
        "profile": policy.profile,
        "agent": policy.agent,
        "overflow": policy.overflow_agent or "",
        "permissions": policy.permissions,
        "home": policy.home,
        "command": policy.command,
        "auth": "unknown",
    }
    print(json.dumps(payload))
    return 0


def _run(args: argparse.Namespace) -> int:
    prompt = args.prompt
    if not prompt:
        print("prompt required", file=sys.stderr)
        return 2
    try:
        policy = resolve(
            Path.cwd(),
            agent_override=getattr(args, "agent_override", None),
        )
    except PolicyDenied as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except UnknownAgent as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code

    def sink(event: dict) -> None:
        print(json.dumps(event), flush=True)

    return run_prompt(policy, prompt, cwd=Path.cwd(), sink=sink)


def _login(args: argparse.Namespace) -> int:
    profile = args.profile
    try:
        policy = resolve(
            Path.cwd(),
            profile_override=profile if profile else None,
        )
    except PolicyDenied as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except UnknownAgent as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    ensure_profile_home(policy.home)
    print(f"profile {policy.profile}")
    print(f"home {policy.home}")
    print(login_hint(policy.agent))
    if policy.overflow_agent:
        print(login_hint(policy.overflow_agent))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "which":
        return _which(args)
    if args.command == "login":
        return _login(args)
    if args.command == "run":
        return _run(args)
    print(NOT_IMPLEMENTED, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
