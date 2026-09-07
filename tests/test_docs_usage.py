"""Operator guide and README usage (issue #216)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_usage_guide_exists() -> None:
    assert (ROOT / "docs" / "USAGE.md").is_file()


def test_readme_links_usage() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/USAGE.md" in text


def test_usage_names_init_and_serve() -> None:
    text = (ROOT / "docs" / "USAGE.md").read_text(encoding="utf-8")
    assert "ravand init" in text
    assert "ravand serve" in text


def test_readme_layout_matches_packages() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "empty until generated" not in text
    assert "acp-client/" not in text
