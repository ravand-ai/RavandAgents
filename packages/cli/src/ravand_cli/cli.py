"""ravand CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ravand_policy import PolicyDenied, UnknownAgent, resolve
from ravand_profile import ensure_profile_home
from ravand_registry import login_hint
from ravand_cli.ask import confirm_permission, confirm_plan, should_ask
from ravand_cli.status import run_status
from ravand_cli.tui import run_tui
from ravand_plugins import FailClosed as PluginFailClosed, PluginHost
from ravand_runtime import audit_agent_denied, run_native_prompt, run_prompt, serve_acp, steer_prompt
from ravand_runtime.plan import plan_mode_active

NOT_IMPLEMENTED = "not implemented"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ravand")
    sub = parser.add_subparsers(dest="command")
    which = sub.add_parser("which", help="resolve agent and profile for cwd")
    which.add_argument("--profile", dest="profile_override")
    which.add_argument("-a", "--agent", dest="agent_override")
    which.add_argument("--account", dest="account_override")
    run = sub.add_parser("run", help="spawn the selected ACP agent")
    run.add_argument("prompt", nargs="?")
    run.add_argument("-a", "--agent", dest="agent_override")
    run.add_argument("--account", dest="account_override")
    run.add_argument("--format", choices=["jsonl", "text"], default="jsonl")
    run.add_argument(
        "--yes",
        action="store_true",
        help="auto-decide permissions (repo-only); never prompt",
    )
    login = sub.add_parser("login", help="print vendor login hints")
    login.add_argument("profile", nargs="?", default=None)
    sub.add_parser("status", help="login doctor")
    sub.add_parser("tui", help="operator screen (TTY)")
    steer = sub.add_parser("steer", help="continue a live session")
    steer.add_argument("session_id")
    steer.add_argument("text")
    plugin = sub.add_parser("plugin", help="manage disk plugins")
    plugin_sub = plugin.add_subparsers(dest="plugin_command")
    plugin_add = plugin_sub.add_parser("add", help="install a plugin from a path")
    plugin_add.add_argument("source", type=Path)
    plugin_sub.add_parser("list", help="list installed plugins")
    serve = sub.add_parser("serve", help="long-running services")
    serve_sub = serve.add_subparsers(dest="serve_command")
    serve_sub.add_parser("acp", help="stdio ACP server (agent ravand)")
    return parser


def _which(args: argparse.Namespace) -> int:
    try:
        policy = resolve(
            Path.cwd(),
            profile_override=getattr(args, "profile_override", None),
            agent_override=getattr(args, "agent_override", None),
            account_override=getattr(args, "account_override", None),
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
        "account": policy.account,
        "kind": policy.account_kind,
        "overflow": policy.overflow_agent or "",
        "permissions": policy.permissions,
        "sandbox": policy.sandbox,
        "home": policy.home,
        "command": policy.command,
        "mcp": policy.mcp,
        "skillsAllow": policy.skills_allow,
        "functionsAllow": policy.functions_allow,
        "agentsMd": policy.agents_md,
        "loop": policy.loop,
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
            account_override=getattr(args, "account_override", None),
        )
    except PolicyDenied as exc:
        audit_agent_denied(str(exc), cwd=Path.cwd())
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except UnknownAgent as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    if policy.loop == "native":
        def sink(event: dict) -> None:
            print(json.dumps(event), flush=True)

        return run_native_prompt(
            policy,
            prompt,
            cwd=Path.cwd(),
            sink=sink,
        )
    if policy.account_kind == "api":
        denied = PolicyDenied(
            f"account {policy.account!r} kind api cannot spawn ACP"
        )
        audit_agent_denied(str(denied), cwd=Path.cwd())
        print(str(denied), file=sys.stderr)
        return denied.exit_code

    def sink(event: dict) -> None:
        print(json.dumps(event), flush=True)

    yes = bool(getattr(args, "yes", False))
    ask = None
    if should_ask(yes=yes, is_tty=sys.stdin.isatty()):
        ask = confirm_permission
    cwd = Path.cwd()
    ask_plan = confirm_plan if plan_mode_active(cwd, policy) else None
    return run_prompt(
        policy,
        prompt,
        cwd=cwd,
        sink=sink,
        ask=ask,
        ask_plan=ask_plan,
        yes=yes,
    )


def _steer(args: argparse.Namespace) -> int:
    def sink(event: dict) -> None:
        print(json.dumps(event), flush=True)

    return steer_prompt(args.session_id, args.text, sink=sink)


def _plugin_add(args: argparse.Namespace) -> int:
    host = PluginHost()
    try:
        manifest = host.add(args.source)
    except PluginFailClosed as exc:
        print(str(exc), file=sys.stderr)
        return 3
    print(json.dumps(manifest.to_dict()))
    return 0


def _plugin_list() -> int:
    host = PluginHost()
    rows = [manifest.to_dict() for manifest in host.list()]
    print(json.dumps(rows))
    return 0


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
    if args.command == "steer":
        return _steer(args)
    if args.command == "status":
        return run_status(Path.cwd())
    if args.command == "tui":
        return run_tui(Path.cwd())
    if args.command == "plugin":
        if args.plugin_command == "add":
            return _plugin_add(args)
        if args.plugin_command == "list":
            return _plugin_list()
        print(NOT_IMPLEMENTED, file=sys.stderr)
        return 2
    if args.command == "serve":
        if args.serve_command == "acp":
            return serve_acp()
        print(NOT_IMPLEMENTED, file=sys.stderr)
        return 2
    print(NOT_IMPLEMENTED, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
