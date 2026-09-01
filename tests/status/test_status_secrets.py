"""Status output must never leak secrets or cookie file contents."""

from __future__ import annotations

from pathlib import Path

from .support import REPO_ROOT, combined_output, run_ravand_status

FORBIDDEN_SECRET_MARKERS = ("sk-", "xai-", "Bearer")

# Sentinels written into a fake vendor cookie. Tests never read real cookies.
COOKIE_SENTINEL_SK = "sk-leaked-from-fixture-cookie"
COOKIE_SENTINEL_XAI = "xai-leaked-from-fixture-cookie"
COOKIE_SENTINEL_BEARER = "Bearer leaked-from-fixture-cookie"


def _write_fixture_cookie(home: Path) -> Path:
    """Create a dummy cookie path. Do not open any file under a real profile HOME."""
    cookie = home / ".ravand" / "profiles" / "work" / ".grok" / "cookies"
    cookie.parent.mkdir(parents=True, exist_ok=True)
    cookie.write_text(
        "\n".join(
            [
                COOKIE_SENTINEL_SK,
                COOKIE_SENTINEL_XAI,
                COOKIE_SENTINEL_BEARER,
            ]
        ),
        encoding="utf-8",
    )
    return cookie


def test_status_output_contains_no_secret_markers(isolated_home: Path) -> None:
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result)
    assert result.returncode == 0, text
    for marker in FORBIDDEN_SECRET_MARKERS:
        assert marker not in text


def test_status_does_not_print_cookie_file_contents(isolated_home: Path) -> None:
    _write_fixture_cookie(isolated_home)
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result)
    assert COOKIE_SENTINEL_SK not in text
    assert COOKIE_SENTINEL_XAI not in text
    assert COOKIE_SENTINEL_BEARER not in text
    assert result.returncode == 0, text
    lowered = text.lower()
    assert "profile" in lowered
    assert any(state in lowered for state in ("logged-in", "missing", "unknown"))
