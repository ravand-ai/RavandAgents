"""Org vault for API keys. Files under ~/.ravand/secrets. Fail closed."""

from __future__ import annotations

from pathlib import Path

from ravand_policy.errors import PolicyDenied

_TOKEN_MARKERS = ("sk-", "xai-", "Bearer")
_COOKIE_MARKERS = ("cookie", ".grok/", ".kimi/", ".cursor/", ".claude")


def _root(home: Path | None) -> Path:
    if home is not None:
        return Path(home)
    from ravand_policy.resolve import ravand_home

    return ravand_home()


def _refuse_secrets(text: str) -> None:
    if any(marker in text for marker in _TOKEN_MARKERS):
        raise PolicyDenied("vault refuses tokens")
    lowered = text.lower()
    for marker in _COOKIE_MARKERS:
        if marker in lowered:
            raise PolicyDenied("vault refuses cookies")


def require_secret_ref(secret_ref: str) -> str:
    if not isinstance(secret_ref, str) or not secret_ref.startswith("vault:"):
        raise PolicyDenied("secret_ref must use vault:")
    rel = secret_ref.removeprefix("vault:")
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise PolicyDenied("secret_ref path is invalid")
    _refuse_secrets(secret_ref)
    return rel


def _secret_path(secret_ref: str, *, home: Path | None) -> Path:
    rel = require_secret_ref(secret_ref)
    base = _root(home)
    root = (base / "secrets").resolve()
    path = (base / "secrets" / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PolicyDenied("secret_ref path escaped") from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise PolicyDenied("secret_ref is missing")
    return path


def secret_present(secret_ref: str, *, home: Path | None = None) -> None:
    """Fail closed if the ref is missing or empty. Does not return bytes."""
    _secret_path(secret_ref, home=home)


def load_secret(secret_ref: str, *, home: Path | None = None) -> bytes:
    """Load secret bytes. Fail closed if missing. Never log the bytes."""
    path = _secret_path(secret_ref, home=home)
    data = path.read_bytes().strip()
    if not data:
        raise PolicyDenied("secret_ref is missing")
    return data
