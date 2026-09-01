"""Login hints. No secrets."""

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
