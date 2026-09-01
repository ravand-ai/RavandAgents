"""ravand status login doctor. Probes vendor login without reading cookie contents."""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from ravand_policy import PolicyDenied, resolve
from ravand_profile import ensure_profile_home

# Relative to profile HOME. Stat only; never open for read.
_COOKIE_MARKERS: dict[str, tuple[str, ...]] = {
    "grok": (".grok", "cookies"),
    "kimi": (".kimi", "credentials"),
}


def _load_harness(cwd: Path) -> dict:
    path = cwd / "harness.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _classification_denied(harness: dict) -> str | None:
    profile = str(harness.get("profile", "personal"))
    classification = str(harness.get("classification", "internal"))
    if classification == "customer" and profile == "personal":
        return "customer classification cannot use personal profile"
    return None


def _cookie_login(profile_home: Path, parts: tuple[str, ...]) -> str | None:
    cookie = profile_home.joinpath(*parts)
    try:
        size = cookie.stat().st_size
    except OSError:
        return "missing"
    if size > 0:
        return "logged-in"
    return "missing"


def _cli_on_path(command: list[str]) -> bool:
    return bool(command) and shutil.which(command[0]) is not None


def _cli_version_ok(command: list[str], *, home: Path) -> bool:
    if not _cli_on_path(command):
        return False
    env = os.environ.copy()
    env["HOME"] = str(home)
    try:
        proc = subprocess.run(
            [command[0], "--version"],
            capture_output=True,
            timeout=5,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _probe_login(agent_id: str, command: list[str], profile_home: Path) -> str:
    marker = _COOKIE_MARKERS.get(agent_id)
    if marker is not None:
        state = _cookie_login(profile_home, marker)
        if state == "logged-in":
            return state
        if not _cli_on_path(command):
            return "unknown"
        return state
    if not _cli_on_path(command):
        return "unknown"
    if _cli_version_ok(command, home=profile_home):
        return "logged-in"
    return "unknown"


def _agent_roles(
    agent_id: str,
    *,
    default_agent: str,
    overflow_agent: str,
) -> list[str]:
    roles: list[str] = []
    if agent_id == default_agent:
        roles.append("default")
    if overflow_agent and agent_id == overflow_agent:
        roles.append("overflow")
    if agent_id != default_agent and agent_id != overflow_agent:
        roles.append("registered")
    return roles


def run_status(cwd: Path) -> int:
    cwd = cwd.resolve()
    harness = _load_harness(cwd)
    deny_reason = _classification_denied(harness)
    if deny_reason is not None:
        profile = str(harness.get("profile", "personal"))
        print(f"profile {profile}")
        print(f"denied: {deny_reason}")
        return 0

    try:
        policy = resolve(cwd)
    except PolicyDenied as exc:
        print("denied")
        print(str(exc))
        return 0

    ensure_profile_home(policy.home)
    profile_home = Path(policy.home)
    agents = harness.get("agents") or {}
    if not isinstance(agents, dict):
        agents = {}

    default_agent = policy.default_agent
    overflow_agent = policy.overflow_agent or ""

    print(f"profile {policy.profile}")
    print(f"home {policy.home}")
    print(f"default {default_agent}")
    if overflow_agent:
        print(f"overflow {overflow_agent}")

    for agent_id in sorted(agents):
        spec = agents[agent_id]
        if not isinstance(spec, dict):
            continue
        command = [str(part) for part in spec.get("command", [])]
        login = _probe_login(agent_id, command, profile_home)
        roles = _agent_roles(
            agent_id,
            default_agent=default_agent,
            overflow_agent=overflow_agent,
        )
        suffix = f" ({', '.join(roles)})" if roles else ""
        print(f"{agent_id}{suffix}: {login}")

    return 0
