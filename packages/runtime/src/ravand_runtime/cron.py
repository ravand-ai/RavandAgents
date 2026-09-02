"""Cron trigger: parse harness jobs, Policy, then dispatch if a bus is set."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ravand_audit import AuditLog
from ravand_policy import PolicyDenied, UnknownAgent, ravand_home, resolve
from ravand_runtime.dispatch import dispatch
from ravand_sessions import FailClosed, SessionStore

_JOB_KEYS = frozenset(
    {"id", "spec", "prompt", "agent", "account", "classification", "secret_ref"}
)
_TOKEN_MARKERS = ("sk-", "xai-", "Bearer")


@dataclass(frozen=True)
class CronJob:
    id: str
    spec: str
    prompt: str
    agent: str | None = None
    account: str | None = None
    classification: str | None = None
    secret_ref: str | None = None


def _refuse_tokens(text: str) -> None:
    for marker in _TOKEN_MARKERS:
        if marker in text:
            raise PolicyDenied("cron job has a raw key")


def _require_secret_ref(secret_ref: str) -> None:
    if not secret_ref.startswith("vault:"):
        raise PolicyDenied("secret_ref must use vault:")
    rel = secret_ref.removeprefix("vault:")
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise PolicyDenied("secret_ref path is invalid")


def _parse_job(item: object) -> CronJob:
    if not isinstance(item, dict):
        raise PolicyDenied("cron job must be a table")
    extra = set(item) - _JOB_KEYS
    if extra:
        raise PolicyDenied("cron job has a raw key")
    job_id = item.get("id")
    spec = item.get("spec")
    prompt = item.get("prompt")
    if not isinstance(job_id, str) or not job_id.strip():
        raise PolicyDenied("cron job id is invalid")
    if not isinstance(spec, str) or not spec.strip():
        raise PolicyDenied("cron job spec is invalid")
    if not isinstance(prompt, str) or not prompt.strip():
        raise PolicyDenied("cron job prompt is invalid")
    _refuse_tokens(job_id)
    _refuse_tokens(spec)
    _refuse_tokens(prompt)
    agent = item.get("agent")
    account = item.get("account")
    classification = item.get("classification")
    secret_ref = item.get("secret_ref")
    if agent is not None:
        if not isinstance(agent, str) or not agent.strip():
            raise PolicyDenied("cron job agent is invalid")
        _refuse_tokens(agent)
    if account is not None:
        if not isinstance(account, str) or not account.strip():
            raise PolicyDenied("cron job account is invalid")
        _refuse_tokens(account)
    if classification is not None:
        if not isinstance(classification, str) or not classification.strip():
            raise PolicyDenied("cron job classification is invalid")
        _refuse_tokens(classification)
    if secret_ref is not None:
        if not isinstance(secret_ref, str) or not secret_ref.strip():
            raise PolicyDenied("cron job secret_ref is invalid")
        _require_secret_ref(secret_ref)
        _refuse_tokens(secret_ref)
    _spec_fields(spec)
    return CronJob(
        id=job_id,
        spec=spec,
        prompt=prompt,
        agent=agent if isinstance(agent, str) else None,
        account=account if isinstance(account, str) else None,
        classification=classification if isinstance(classification, str) else None,
        secret_ref=secret_ref if isinstance(secret_ref, str) else None,
    )


def load_cron_jobs(cwd: Path) -> list[CronJob]:
    path = cwd / "harness.toml"
    if not path.is_file():
        return []
    with path.open("rb") as handle:
        harness = tomllib.load(handle)
    if "cron" not in harness:
        return []
    cron = harness.get("cron")
    if not isinstance(cron, dict):
        raise PolicyDenied("harness cron table is invalid")
    if "jobs" not in cron:
        return []
    jobs = cron.get("jobs")
    if not isinstance(jobs, list):
        raise PolicyDenied("harness cron.jobs must be a list")
    return [_parse_job(item) for item in jobs]


def _spec_fields(spec: str) -> list[str]:
    fields = spec.split()
    if len(fields) != 5:
        raise PolicyDenied("cron job spec is invalid")
    return fields


def _field_match(field: str, value: int, *, lo: int, hi: int) -> bool:
    for part in field.split(","):
        if not part:
            raise PolicyDenied("cron job spec is invalid")
        if "/" in part:
            range_part, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError as exc:
                raise PolicyDenied("cron job spec is invalid") from exc
            if step <= 0:
                raise PolicyDenied("cron job spec is invalid")
            if range_part == "*":
                start, end = lo, hi
            elif "-" in range_part:
                start_s, end_s = range_part.split("-", 1)
                try:
                    start, end = int(start_s), int(end_s)
                except ValueError as exc:
                    raise PolicyDenied("cron job spec is invalid") from exc
            else:
                try:
                    start = end = int(range_part)
                except ValueError as exc:
                    raise PolicyDenied("cron job spec is invalid") from exc
            if start <= value <= end and (value - start) % step == 0:
                return True
            continue
        if part == "*":
            return True
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            try:
                start, end = int(start_s), int(end_s)
            except ValueError as exc:
                raise PolicyDenied("cron job spec is invalid") from exc
            if start <= value <= end:
                return True
            continue
        try:
            if int(part) == value:
                return True
        except ValueError as exc:
            raise PolicyDenied("cron job spec is invalid") from exc
    return False


def _dow_match(field: str, weekday: int) -> bool:
    cron_dow = (weekday + 1) % 7
    if _field_match(field, cron_dow, lo=0, hi=7):
        return True
    if cron_dow == 0:
        return _field_match(field, 7, lo=0, hi=7)
    return False


def job_is_due(job: CronJob, now: datetime) -> bool:
    minute, hour, day, month, dow = _spec_fields(job.spec)
    instant = now.astimezone(UTC)
    if not _field_match(minute, instant.minute, lo=0, hi=59):
        return False
    if not _field_match(hour, instant.hour, lo=0, hi=23):
        return False
    if not _field_match(day, instant.day, lo=1, hi=31):
        return False
    if not _field_match(month, instant.month, lo=1, hi=12):
        return False
    return _dow_match(dow, instant.weekday())


def _deny(
    job: CronJob,
    *,
    cwd: Path,
    audit: AuditLog,
    detail: str,
    profile: str | None = None,
    agent: str | None = None,
) -> None:
    audit.emit(
        "trigger.denied",
        task_id=job.id,
        profile=profile,
        agent=agent,
        cwd=str(cwd),
        detail=detail,
    )


def fire_cron(
    cwd: Path,
    *,
    now: datetime | None = None,
    bus: object | None = None,
    store: SessionStore | None = None,
    audit: AuditLog | None = None,
) -> list[CronJob]:
    cwd = cwd.resolve()
    instant = now if now is not None else datetime.now(UTC)
    log = audit if audit is not None else AuditLog(ravand_home())
    fired: list[CronJob] = []
    for job in load_cron_jobs(cwd):
        if not job_is_due(job, instant):
            continue
        try:
            policy = resolve(
                cwd,
                agent_override=job.agent,
                account_override=job.account,
            )
        except (PolicyDenied, UnknownAgent) as exc:
            _deny(job, cwd=cwd, audit=log, detail=str(exc))
            continue
        if job.classification and job.classification != policy.classification:
            _deny(
                job,
                cwd=cwd,
                audit=log,
                detail="classification no longer matches",
                profile=policy.profile,
                agent=policy.agent,
            )
            continue
        if job.account and job.account != policy.account:
            _deny(
                job,
                cwd=cwd,
                audit=log,
                detail="account no longer matches",
                profile=policy.profile,
                agent=policy.agent,
            )
            continue
        if bus is not None:
            if store is None:
                raise PolicyDenied("cron dispatch requires a session store")
            occurrence = instant.strftime("%Y%m%dT%H%M")
            try:
                dispatch(
                    cwd,
                    job.prompt,
                    bus=bus,
                    store=store,
                    task_id=f"{job.id}:{occurrence}",
                    agent_override=job.agent,
                    account_override=job.account,
                )
            except FailClosed:
                continue
        fired.append(job)
    return fired
