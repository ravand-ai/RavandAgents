"""AGENTS.md auto-run: do not wait for plan or commit approval (#217)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agents_does_not_wait_for_approval() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Do not wait for plan, branch, commit, or pull-request approval." in text
    assert "Wait for the user to accept the plan." not in text
    assert "Human still merges to `main`." in text
