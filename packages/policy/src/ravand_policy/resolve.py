"""Resolve harness.toml + user config into a policy. Fail closed."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ravand_policy.errors import PolicyDenied, UnknownAgent


def ravand_home() -> Path:
    override = os.environ.get("RAVAND_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".ravand"


@dataclass
class ResolvedPolicy:
    profile: str
    home: str
    default_agent: str
    overflow_agent: str | None
    deny: list[str]
    permissions: str
    classification: str
    command: list[str]
    mcp: list[dict] = field(default_factory=list)
    agent: str = ""
    account: str = ""
    account_kind: str = ""


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _user_config(home: Path) -> dict:
    path = home / "config.toml"
    if not path.is_file():
        return {}
    return _load_toml(path)


def _secret_present(secret_ref: str, *, home: Path) -> None:
    if not secret_ref.startswith("vault:"):
        raise PolicyDenied("secret_ref must use vault:")
    rel = secret_ref.removeprefix("vault:")
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise PolicyDenied("secret_ref path is invalid")
    root = (home / "secrets").resolve()
    path = (home / "secrets" / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PolicyDenied("secret_ref path escaped") from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise PolicyDenied("secret_ref is missing")


def _resolve_account(
    account_id: str,
    *,
    user: dict,
    harness: dict,
    agent: str,
) -> tuple[str, str]:
    accounts_cfg = user.get("accounts") or {}
    if not isinstance(accounts_cfg, dict):
        raise PolicyDenied("user accounts table is invalid")

    record = accounts_cfg.get(account_id)
    if not isinstance(record, dict):
        raise PolicyDenied(f"unknown account {account_id!r}")

    kind = str(record.get("kind", ""))
    if kind == "api":
        secret_ref = str(record.get("secret_ref") or "").strip()
        if not secret_ref:
            raise PolicyDenied(f"account {account_id!r} secret_ref is missing")
        _secret_present(secret_ref, home=ravand_home())
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


def resolve(
    cwd: Path,
    *,
    profile_override: str | None = None,
    agent_override: str | None = None,
    account_override: str | None = None,
) -> ResolvedPolicy:
    cwd = cwd.resolve()
    harness_path = cwd / "harness.toml"
    home_root = ravand_home()
    user = _user_config(home_root)

    if harness_path.is_file():
        harness = _load_toml(harness_path)
    else:
        default_profile = user.get("default_profile", "personal")
        harness = {
            "profile": default_profile,
            "default": "",
            "overflow": "",
            "deny": [],
            "permissions": "repo-only",
            "classification": "internal",
            "agents": {},
        }

    repo_profile = str(harness.get("profile", "personal"))
    profile = profile_override or repo_profile
    classification = str(harness.get("classification", "internal"))
    deny = [str(x) for x in harness.get("deny", [])]
    permissions = str(harness.get("permissions", "repo-only"))
    default_agent = str(harness.get("default", ""))
    overflow_raw = str(harness.get("overflow") or "")
    overflow_agent = overflow_raw or None
    agents = harness.get("agents") or {}
    if not isinstance(agents, dict):
        raise PolicyDenied("harness agents table is invalid")

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

    account = ""
    account_kind = ""
    if account_override:
        account, account_kind = _resolve_account(
            account_override,
            user=user,
            harness=harness,
            agent=agent,
        )

    profile_home = home_root / "profiles" / profile
    return ResolvedPolicy(
        profile=profile,
        home=str(profile_home),
        default_agent=default_agent,
        overflow_agent=overflow_agent,
        deny=deny,
        permissions=permissions,
        classification=classification,
        command=command,
        agent=agent,
        account=account,
        account_kind=account_kind,
    )
