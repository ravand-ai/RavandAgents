"""Signed inbound webhook: HMAC, Policy, then dispatch. Fail closed."""

from __future__ import annotations

import hashlib
import hmac
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ravand_audit import AuditLog
from ravand_policy import PolicyDenied, UnknownAgent, ravand_home, resolve
from ravand_runtime.dispatch import dispatch
from ravand_sessions import FailClosed, SessionStore

_WEBHOOK_KEYS = frozenset(
    {"id", "path", "secret_ref", "prompt", "agent", "account", "classification"}
)
_TOKEN_MARKERS = ("sk-", "xai-", "Bearer")


@dataclass(frozen=True)
class WebhookTrigger:
    path: str
    secret_ref: str
    prompt: str
    id: str | None = None
    agent: str | None = None
    account: str | None = None
    classification: str | None = None


def _refuse_tokens(text: str) -> None:
    for marker in _TOKEN_MARKERS:
        if marker in text:
            raise PolicyDenied("webhook has a raw key")


def _require_secret_ref(secret_ref: str) -> None:
    if not secret_ref.startswith("vault:"):
        raise PolicyDenied("secret_ref must use vault:")
    rel = secret_ref.removeprefix("vault:")
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise PolicyDenied("secret_ref path is invalid")


def _norm_path(path: str) -> str:
    raw = path.split("?", 1)[0]
    if raw != "/" and raw.endswith("/"):
        return raw[:-1]
    return raw


def _parse_webhook(item: object) -> WebhookTrigger:
    if not isinstance(item, dict):
        raise PolicyDenied("webhook must be a table")
    extra = set(item) - _WEBHOOK_KEYS
    if extra:
        raise PolicyDenied("webhook has a raw key")
    path = item.get("path")
    secret_ref = item.get("secret_ref")
    prompt = item.get("prompt")
    if not isinstance(path, str) or not path.strip():
        raise PolicyDenied("webhook path is invalid")
    if not isinstance(secret_ref, str) or not secret_ref.strip():
        raise PolicyDenied("webhook secret_ref is invalid")
    if not isinstance(prompt, str) or not prompt.strip():
        raise PolicyDenied("webhook prompt is invalid")
    _refuse_tokens(path)
    _refuse_tokens(secret_ref)
    _refuse_tokens(prompt)
    _require_secret_ref(secret_ref)
    webhook_id = item.get("id")
    agent = item.get("agent")
    account = item.get("account")
    classification = item.get("classification")
    if webhook_id is not None:
        if not isinstance(webhook_id, str) or not webhook_id.strip():
            raise PolicyDenied("webhook id is invalid")
        _refuse_tokens(webhook_id)
    if agent is not None:
        if not isinstance(agent, str) or not agent.strip():
            raise PolicyDenied("webhook agent is invalid")
        _refuse_tokens(agent)
    if account is not None:
        if not isinstance(account, str) or not account.strip():
            raise PolicyDenied("webhook account is invalid")
        _refuse_tokens(account)
    if classification is not None:
        if not isinstance(classification, str) or not classification.strip():
            raise PolicyDenied("webhook classification is invalid")
        _refuse_tokens(classification)
    return WebhookTrigger(
        path=_norm_path(path),
        secret_ref=secret_ref,
        prompt=prompt,
        id=webhook_id if isinstance(webhook_id, str) else None,
        agent=agent if isinstance(agent, str) else None,
        account=account if isinstance(account, str) else None,
        classification=classification if isinstance(classification, str) else None,
    )


def load_webhook(cwd: Path) -> WebhookTrigger | None:
    path = cwd / "harness.toml"
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        harness = tomllib.load(handle)
    if "triggers" not in harness:
        return None
    triggers = harness.get("triggers")
    if not isinstance(triggers, dict):
        raise PolicyDenied("harness triggers table is invalid")
    if "webhook" not in triggers:
        return None
    return _parse_webhook(triggers.get("webhook"))


def verify_webhook_signature(
    body: bytes, signature: str | None, secret: bytes
) -> bool:
    if not signature or not secret:
        return False
    digest = hmac.new(secret, body, hashlib.sha256).hexdigest()
    expected = f"sha256={digest}"
    provided = signature.strip()
    if "=" not in provided:
        provided = f"sha256={provided}"
    return hmac.compare_digest(provided, expected)


def _load_secret(secret_ref: str, *, home: Path) -> bytes:
    _require_secret_ref(secret_ref)
    rel = secret_ref.removeprefix("vault:")
    root = (home / "secrets").resolve()
    path = (home / "secrets" / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PolicyDenied("secret_ref path escaped") from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise PolicyDenied("secret_ref is missing")
    return path.read_bytes()


def _deny(
    trigger: WebhookTrigger | None,
    *,
    cwd: Path,
    audit: AuditLog,
    detail: str,
    profile: str | None = None,
    agent: str | None = None,
) -> None:
    task_id = "webhook"
    if trigger is not None:
        task_id = trigger.id or trigger.path
    audit.emit(
        "trigger.denied",
        task_id=task_id,
        profile=profile,
        agent=agent,
        cwd=str(cwd),
        detail=detail,
    )


def handle_webhook(
    cwd: Path,
    *,
    path: str,
    body: bytes,
    signature: str | None,
    bus: object | None = None,
    store: SessionStore | None = None,
    audit: AuditLog | None = None,
) -> WebhookTrigger:
    cwd = cwd.resolve()
    log = audit if audit is not None else AuditLog(ravand_home())
    trigger = load_webhook(cwd)
    request_path = _norm_path(path)
    if trigger is None or trigger.path != request_path:
        _deny(trigger, cwd=cwd, audit=log, detail="unknown webhook")
        raise PolicyDenied("unknown webhook")
    try:
        secret = _load_secret(trigger.secret_ref, home=ravand_home())
    except PolicyDenied as exc:
        _deny(trigger, cwd=cwd, audit=log, detail="secret_ref is missing")
        raise PolicyDenied("secret_ref is missing") from exc
    if not verify_webhook_signature(body, signature, secret):
        _deny(trigger, cwd=cwd, audit=log, detail="unsigned webhook")
        raise PolicyDenied("unsigned webhook")
    try:
        policy = resolve(
            cwd,
            agent_override=trigger.agent,
            account_override=trigger.account,
        )
    except (PolicyDenied, UnknownAgent) as exc:
        _deny(trigger, cwd=cwd, audit=log, detail=str(exc))
        raise
    if trigger.classification and trigger.classification != policy.classification:
        _deny(
            trigger,
            cwd=cwd,
            audit=log,
            detail="classification no longer matches",
            profile=policy.profile,
            agent=policy.agent,
        )
        raise PolicyDenied("classification no longer matches")
    if trigger.account and trigger.account != policy.account:
        _deny(
            trigger,
            cwd=cwd,
            audit=log,
            detail="account no longer matches",
            profile=policy.profile,
            agent=policy.agent,
        )
        raise PolicyDenied("account no longer matches")
    if bus is not None:
        if store is None:
            raise PolicyDenied("webhook dispatch requires a session store")
        task_id = trigger.id or trigger.path
        try:
            dispatch(
                cwd,
                trigger.prompt,
                bus=bus,
                store=store,
                task_id=task_id,
                agent_override=trigger.agent,
                account_override=trigger.account,
            )
        except FailClosed:
            _deny(
                trigger,
                cwd=cwd,
                audit=log,
                detail="dispatch failed",
                profile=policy.profile,
                agent=policy.agent,
            )
            raise
    return trigger
