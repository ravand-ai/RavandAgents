"""Resolve harness.toml + user config into a policy. Fail closed."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ravand_policy.errors import FailClosed, PolicyDenied, UnknownAgent
from ravand_policy.store import FilePolicyStore, default_policy_store
from ravand_policy.vault import secret_present

PolicyStore = FilePolicyStore  # structural: load_toml / user_config / require_reachable


def ravand_home() -> Path:
    override = os.environ.get("RAVAND_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".ravand"


_SANDBOX_VALUES = frozenset({"none", "repo-only", "container"})
_LOOP_VALUES = frozenset({"acp", "native"})
_WRITE_SHELL_PERMISSIONS = frozenset({"repo-only", "ask", "plan"})


@dataclass
class ResolvedPolicy:
    profile: str
    home: str
    default_agent: str
    overflow_agent: str | None
    deny: list[str]
    permissions: str
    classification: str
    sandbox: str
    command: list[str]
    mcp: list[dict] = field(default_factory=list)
    skills_allow: list[str] = field(default_factory=list)
    functions_allow: list[str] = field(default_factory=list)
    agents_md: bool = False
    agent: str = ""
    account: str = ""
    account_kind: str = ""
    loop: str = "acp"


def _is_personal_account(account_id: str, record: dict) -> bool:
    if "personal" in account_id:
        return True
    if str(record.get("profile", "")) == "personal":
        return True
    if str(record.get("seat", "")) == "personal":
        return True
    return False


def _resolve_account(
    account_id: str,
    *,
    user: dict,
    harness: dict,
    agent: str,
    classification: str,
) -> tuple[str, str]:
    accounts_cfg = user.get("accounts") or {}
    if not isinstance(accounts_cfg, dict):
        raise PolicyDenied("user accounts table is invalid")

    record = accounts_cfg.get(account_id)
    if not isinstance(record, dict):
        raise PolicyDenied(f"unknown account {account_id!r}")

    if classification == "customer" and _is_personal_account(account_id, record):
        raise PolicyDenied("customer classification cannot use personal account")

    kind = str(record.get("kind", ""))
    if kind == "api":
        secret_ref = str(record.get("secret_ref") or "").strip()
        if not secret_ref:
            raise PolicyDenied(f"account {account_id!r} secret_ref is missing")
        secret_present(secret_ref, home=ravand_home())
    elif kind == "cli":
        account_agent = str(record.get("agent", ""))
        if account_agent != agent:
            raise PolicyDenied(
                f"account {account_id!r} agent {account_agent!r} "
                f"does not match {agent!r}"
            )
    else:
        raise PolicyDenied(f"account {account_id!r} has invalid kind")

    harness_accounts = harness.get("accounts") or {}
    if isinstance(harness_accounts, dict):
        deny = [str(x) for x in harness_accounts.get("deny", [])]
        if account_id in deny:
            raise PolicyDenied(f"account {account_id!r} is denied")
        if "allow" in harness_accounts:
            allow = [str(x) for x in harness_accounts.get("allow", [])]
            if account_id not in allow:
                raise PolicyDenied(f"account {account_id!r} is not allowed")

    return account_id, kind


def _parse_mcp(harness: dict) -> list[dict]:
    if "mcp" not in harness:
        return []
    mcp = harness.get("mcp")
    if not isinstance(mcp, dict):
        raise PolicyDenied("harness mcp table is invalid")
    if "servers" not in mcp:
        return []
    servers = mcp.get("servers")
    if not isinstance(servers, list):
        raise PolicyDenied("harness mcp servers must be a list")
    parsed: list[dict] = []
    for item in servers:
        if not isinstance(item, dict):
            raise PolicyDenied("mcp server must be a table")
        name = item.get("name")
        command = item.get("command")
        if not isinstance(name, str) or not name.strip():
            raise PolicyDenied("mcp server name is invalid")
        if not isinstance(command, list) or not command:
            raise PolicyDenied("mcp server command is invalid")
        parsed.append({"name": name, "command": [str(x) for x in command]})
    return parsed


def _parse_skills_allow(harness: dict) -> list[str]:
    if "skills" not in harness:
        return []
    skills = harness.get("skills")
    if not isinstance(skills, dict):
        raise PolicyDenied("harness skills table is invalid")
    if "allow" not in skills:
        return []
    allow = skills.get("allow")
    if not isinstance(allow, list):
        raise PolicyDenied("harness skills.allow must be a list")
    parsed: list[str] = []
    for item in allow:
        if not isinstance(item, str) or not item.strip():
            raise PolicyDenied("harness skills.allow entries must be strings")
        parsed.append(item)
    return parsed


def require_skill(policy: ResolvedPolicy, name: str) -> None:
    """Fail closed when allow is set and name is missing. SKILL.md names only."""
    if not policy.skills_allow:
        return
    if name not in policy.skills_allow:
        raise PolicyDenied(f"skill {name!r} is not allowed")


def _parse_functions_allow(harness: dict) -> list[str]:
    if "functions" not in harness:
        return []
    functions = harness.get("functions")
    if not isinstance(functions, dict):
        raise PolicyDenied("harness functions table is invalid")
    if "allow" not in functions:
        return []
    allow = functions.get("allow")
    if not isinstance(allow, list):
        raise PolicyDenied("harness functions.allow must be a list")
    parsed: list[str] = []
    for item in allow:
        if not isinstance(item, str) or not item.strip():
            raise PolicyDenied("harness functions.allow entries must be strings")
        parsed.append(item)
    return parsed


def require_function(policy: ResolvedPolicy, name: str) -> None:
    """Fail closed when allow is set and name is missing."""
    if not policy.functions_allow:
        return
    if name not in policy.functions_allow:
        raise PolicyDenied(f"function {name!r} is not allowed")


def _parse_sandbox(harness: dict) -> str:
    raw = harness.get("sandbox", "repo-only")
    if not isinstance(raw, str):
        raise PolicyDenied("harness sandbox must be a string")
    sandbox = raw.strip()
    if sandbox not in _SANDBOX_VALUES:
        raise PolicyDenied(f"harness sandbox {sandbox!r} is invalid")
    return sandbox


def _enforce_sandbox(
    *,
    sandbox: str,
    classification: str,
    permissions: str,
) -> None:
    if sandbox == "container":
        raise PolicyDenied("sandbox container is not implemented")
    if (
        classification == "customer"
        and sandbox == "none"
        and permissions in _WRITE_SHELL_PERMISSIONS
    ):
        raise PolicyDenied(
            "customer classification cannot use sandbox none when writes or shell are allowed"
        )


def _parse_loop(harness: dict) -> str:
    raw = harness.get("loop", "acp")
    if not isinstance(raw, str):
        raise PolicyDenied("harness loop must be a string")
    loop = raw.strip()
    if loop not in _LOOP_VALUES:
        raise PolicyDenied(f"harness loop {loop!r} is invalid")
    return loop


def _enforce_native_loop(*, loop: str, account: str, account_kind: str) -> None:
    if loop != "native":
        return
    if not account:
        raise PolicyDenied("loop native requires --account")
    if account_kind != "api":
        raise PolicyDenied(
            f"loop native requires kind api account, got {account_kind!r}"
        )


def _parse_agents_md(harness: dict) -> bool:
    if "agents_md" not in harness:
        return False
    value = harness.get("agents_md")
    if not isinstance(value, bool):
        raise PolicyDenied("harness agents_md must be a bool")
    return value


def resolve(
    cwd: Path,
    *,
    profile_override: str | None = None,
    agent_override: str | None = None,
    account_override: str | None = None,
    store: FilePolicyStore | None = None,
) -> ResolvedPolicy:
    cwd = cwd.resolve()
    harness_path = cwd / "harness.toml"
    home_root = ravand_home()
    policy_store = store if store is not None else default_policy_store()
    policy_store.require_reachable(home=home_root, cwd=cwd)
    user = policy_store.user_config(home_root)
    try:
        missing_harness = not harness_path.is_file()
    except OSError as exc:
        raise FailClosed("policy unreachable") from exc

    if not missing_harness:
        harness = policy_store.load_toml(harness_path)
    else:
        default_profile = user.get("default_profile", "personal")
        harness = {
            "profile": default_profile,
            "default": "",
            "overflow": "",
            "deny": [],
            "permissions": "repo-only",
            "classification": "internal",
            "sandbox": "repo-only",
            "agents": {},
        }

    repo_profile = str(harness.get("profile", "personal"))
    profile = profile_override or repo_profile
    classification = str(harness.get("classification", "internal"))
    deny = [str(x) for x in harness.get("deny", [])]
    permissions = str(harness.get("permissions", "repo-only"))
    sandbox = _parse_sandbox(harness)
    _enforce_sandbox(
        sandbox=sandbox,
        classification=classification,
        permissions=permissions,
    )
    default_agent = str(harness.get("default", ""))
    overflow_raw = str(harness.get("overflow") or "")
    overflow_agent = overflow_raw or None
    agents = harness.get("agents") or {}
    if not isinstance(agents, dict):
        raise PolicyDenied("harness agents table is invalid")

    if missing_harness:
        raise UnknownAgent("no harness.toml; run `ravand init`")
    if profile_override and profile_override != repo_profile:
        raise PolicyDenied(
            f"profile override {profile_override!r} does not match repo {repo_profile!r}"
        )
    if classification == "customer" and profile == "personal":
        raise PolicyDenied("customer classification cannot use personal profile")

    agent = agent_override or default_agent
    if not agent:
        raise UnknownAgent("no default agent")
    if agent in deny:
        raise PolicyDenied(f"agent {agent!r} is denied")
    if agent not in agents:
        raise UnknownAgent(f"unknown agent {agent!r}")

    profiles = user.get("profiles") or {}
    if isinstance(profiles, dict) and profile in profiles:
        allow = profiles[profile].get("allow")
        if isinstance(allow, list) and agent not in allow:
            raise PolicyDenied(f"agent {agent!r} is not allowed on profile {profile!r}")

    spec = agents[agent]
    if not isinstance(spec, dict) or "command" not in spec:
        raise UnknownAgent(f"agent {agent!r} has no command")
    command = [str(x) for x in spec["command"]]
    mcp = _parse_mcp(harness)
    skills_allow = _parse_skills_allow(harness)
    functions_allow = _parse_functions_allow(harness)
    agents_md = _parse_agents_md(harness)
    loop = _parse_loop(harness)

    account = ""
    account_kind = ""
    if account_override:
        account, account_kind = _resolve_account(
            account_override,
            user=user,
            harness=harness,
            agent=agent,
            classification=classification,
        )
    _enforce_native_loop(loop=loop, account=account, account_kind=account_kind)

    profile_home = home_root / "profiles" / profile
    return ResolvedPolicy(
        profile=profile,
        home=str(profile_home),
        default_agent=default_agent,
        overflow_agent=overflow_agent,
        deny=deny,
        permissions=permissions,
        classification=classification,
        sandbox=sandbox,
        command=command,
        mcp=mcp,
        skills_allow=skills_allow,
        functions_allow=functions_allow,
        agents_md=agents_md,
        agent=agent,
        account=account,
        account_kind=account_kind,
        loop=loop,
    )
