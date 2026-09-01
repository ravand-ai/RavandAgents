"""Attach cwd/AGENTS.md to the prompt when policy.agents_md is true."""

from __future__ import annotations

from pathlib import Path

from ravand_policy import ResolvedPolicy


def attach_agents_md(policy: ResolvedPolicy, prompt: str, cwd: Path) -> str:
    if not policy.agents_md:
        return prompt
    path = cwd / "AGENTS.md"
    if not path.is_file():
        return prompt
    text = path.read_text(encoding="utf-8")
    return "[agents.md]\n" + text + "\n\n" + prompt
