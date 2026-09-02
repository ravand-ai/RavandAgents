"""Pipeline: parse harness ordered stages, Policy, then dispatch. Fail closed."""

from __future__ import annotations

import tomllib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ravand_audit import AuditLog
from ravand_policy import (
    PolicyDenied,
    UnknownAgent,
    ravand_home,
    require_function,
    resolve,
)
from ravand_runtime.dispatch import dispatch
from ravand_sessions import FailClosed, SessionStore

_PIPELINE_KEYS = frozenset({"id", "stages"})
_STAGE_KEYS = frozenset(
    {
        "id",
        "prompt",
        "agent",
        "account",
        "functions",
        "tools",
        "subagents",
    }
)
_TOKEN_MARKERS = ("sk-", "xai-", "Bearer")


@dataclass(frozen=True)
class PipelineStage:
    id: str
    prompt: str
    agent: str | None = None
    account: str | None = None
    functions: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    subagents: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pipeline:
    stages: tuple[PipelineStage, ...]
    id: str | None = None


def _refuse_tokens(text: str) -> None:
    for marker in _TOKEN_MARKERS:
        if marker in text:
            raise PolicyDenied("pipeline has a raw key")


def _string_list(raw: object, *, field: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise PolicyDenied(f"pipeline stage {field} must be a list")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise PolicyDenied(f"pipeline stage {field} is invalid")
        _refuse_tokens(item)
        values.append(item)
    return tuple(values)


def _parse_stage(item: object) -> PipelineStage:
    if not isinstance(item, dict):
        raise PolicyDenied("pipeline stage must be a table")
    extra = set(item) - _STAGE_KEYS
    if extra:
        raise PolicyDenied("pipeline has a raw key")
    stage_id = item.get("id")
    prompt = item.get("prompt")
    if not isinstance(stage_id, str) or not stage_id.strip():
        raise PolicyDenied("pipeline stage id is invalid")
    if not isinstance(prompt, str) or not prompt.strip():
        raise PolicyDenied("pipeline stage prompt is invalid")
    _refuse_tokens(stage_id)
    _refuse_tokens(prompt)
    agent = item.get("agent")
    account = item.get("account")
    if agent is not None:
        if not isinstance(agent, str) or not agent.strip():
            raise PolicyDenied("pipeline stage agent is invalid")
        _refuse_tokens(agent)
    if account is not None:
        if not isinstance(account, str) or not account.strip():
            raise PolicyDenied("pipeline stage account is invalid")
        _refuse_tokens(account)
    return PipelineStage(
        id=stage_id,
        prompt=prompt,
        agent=agent if isinstance(agent, str) else None,
        account=account if isinstance(account, str) else None,
        functions=_string_list(item.get("functions"), field="functions"),
        tools=_string_list(item.get("tools"), field="tools"),
        subagents=_string_list(item.get("subagents"), field="subagents"),
    )


def _unique_ids(stages: tuple[PipelineStage, ...]) -> None:
    seen: set[str] = set()
    for stage in stages:
        if stage.id in seen:
            raise PolicyDenied("pipeline stage id is duplicate")
        seen.add(stage.id)


def load_pipeline(cwd: Path) -> Pipeline | None:
    path = cwd / "harness.toml"
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        harness = tomllib.load(handle)
    if "pipeline" not in harness:
        return None
    table = harness.get("pipeline")
    if not isinstance(table, dict):
        raise PolicyDenied("harness pipeline table is invalid")
    extra = set(table) - _PIPELINE_KEYS
    if extra:
        raise PolicyDenied("pipeline has a raw key")
    pipeline_id = table.get("id")
    if pipeline_id is not None:
        if not isinstance(pipeline_id, str) or not pipeline_id.strip():
            raise PolicyDenied("pipeline id is invalid")
        _refuse_tokens(pipeline_id)
    if "stages" not in table:
        return Pipeline(
            stages=(),
            id=pipeline_id if isinstance(pipeline_id, str) else None,
        )
    raw_stages = table.get("stages")
    if not isinstance(raw_stages, list):
        raise PolicyDenied("harness pipeline.stages must be a list")
    stages = tuple(_parse_stage(item) for item in raw_stages)
    _unique_ids(stages)
    return Pipeline(
        stages=stages,
        id=pipeline_id if isinstance(pipeline_id, str) else None,
    )


def _deny(
    pipeline: Pipeline,
    stage: PipelineStage | None,
    *,
    cwd: Path,
    audit: AuditLog,
    detail: str,
    profile: str | None = None,
    agent: str | None = None,
) -> None:
    task_id = pipeline.id or "pipeline"
    if stage is not None:
        task_id = f"{task_id}:{stage.id}"
    audit.emit(
        "agent.denied",
        task_id=task_id,
        profile=profile,
        agent=agent,
        cwd=str(cwd),
        detail=detail,
    )


def run_pipeline(
    cwd: Path,
    *,
    bus: object | None = None,
    store: SessionStore | None = None,
    audit: AuditLog | None = None,
    run: Callable[[PipelineStage], object] | None = None,
) -> list[PipelineStage]:
    cwd = cwd.resolve()
    log = audit if audit is not None else AuditLog(ravand_home())
    pipeline = load_pipeline(cwd)
    if pipeline is None:
        return []
    planned: list[tuple[PipelineStage, object]] = []
    for stage in pipeline.stages:
        try:
            policy = resolve(
                cwd,
                agent_override=stage.agent,
                account_override=stage.account,
            )
        except (PolicyDenied, UnknownAgent) as exc:
            _deny(
                pipeline,
                stage,
                cwd=cwd,
                audit=log,
                detail=str(exc),
            )
            raise
        try:
            for name in stage.functions:
                require_function(policy, name)
            for name in stage.subagents:
                resolve(
                    cwd,
                    agent_override=name,
                    account_override=stage.account,
                )
        except (PolicyDenied, UnknownAgent) as exc:
            _deny(
                pipeline,
                stage,
                cwd=cwd,
                audit=log,
                detail=str(exc),
                profile=policy.profile,
                agent=policy.agent,
            )
            raise
        planned.append((stage, policy))
    executed: list[PipelineStage] = []
    for stage, _policy in planned:
        if run is not None:
            run(stage)
        elif bus is not None:
            if store is None:
                raise PolicyDenied("pipeline dispatch requires a session store")
            pipe_id = pipeline.id or "pipeline"
            try:
                dispatch(
                    cwd,
                    stage.prompt,
                    bus=bus,
                    store=store,
                    task_id=f"{pipe_id}:{stage.id}:{uuid.uuid4()}",
                    agent_override=stage.agent,
                    account_override=stage.account,
                )
            except FailClosed:
                _deny(
                    pipeline,
                    stage,
                    cwd=cwd,
                    audit=log,
                    detail="dispatch failed",
                )
                raise
        executed.append(stage)
    return executed
