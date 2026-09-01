"""Adapter catalog. Data, not logic (HLD Registry).

Canonical vendor ACP commands per agent id, plus login hints.
No secrets live here. Unknown ids return None so the caller fails
closed before any spawn.
"""

AGENT_COMMANDS = {
    "grok": ["grok", "agent", "stdio"],
    "kimi": ["kimi", "acp"],
    "claude": ["npx", "-y", "@agentclientprotocol/claude-agent-acp"],
    "cursor": ["cursor-agent", "acp"],
    "opencode": ["opencode", "acp"],
    "dsh": ["dsh", "--profile", "acp"],
}


def agent_command(agent_id: str) -> list[str] | None:
    """Return the vendor ACP command for a known id, else None."""
    command = AGENT_COMMANDS.get(agent_id)
    return list(command) if command is not None else None


LOGIN_HINTS = {
    "grok": "grok login",
    "kimi": "kimi login",
    "claude": "claude  # vendor CLI login",
    "cursor": "cursor-agent  # use an already logged-in Cursor seat",
    "opencode": "opencode  # vendor login",
    "dsh": "dsh  # vendor login",
}


def login_hint(agent_id: str) -> str:
    return LOGIN_HINTS.get(agent_id, f"{agent_id}  # vendor login")
