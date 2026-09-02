"""Workflow graph: parse harness steps, Policy, then dispatch. Fail closed."""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ravand_audit import AuditLog
from ravand_policy import PolicyDenied, ravand_home
from ravand_runtime.step_runner import run_policy_steps
from ravand_sessions import SessionStore

_WORKFLOW_KEYS = frozenset({"id", "steps"})
_STEP_KEYS = frozenset(
    {
        "id",
        "prompt",
        "agent",
        "account",
        "needs",
        "depends",
        "functions",
        "tools",
        "subagents",
    }
)
_TOKEN_MARKERS = ("sk-", "xai-", "Bearer")


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    prompt: str
    agent: str | None = None
    account: str | None = None
    needs: tuple[str, ...] = ()
    functions: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    subagents: tuple[str, ...] = ()


@dataclass(frozen=True)
class Workflow:
    steps: tuple[WorkflowStep, ...]
    id: str | None = None


def _refuse_tokens(text: str) -> None:
    for marker in _TOKEN_MARKERS:
        if marker in text:
            raise PolicyDenied("workflow has a raw key")


def _string_list(raw: object, *, field: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise PolicyDenied(f"workflow step {field} must be a list")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise PolicyDenied(f"workflow step {field} is invalid")
        _refuse_tokens(item)
        values.append(item)
    return tuple(values)


def _parse_step(item: object) -> WorkflowStep:
    if not isinstance(item, dict):
        raise PolicyDenied("workflow step must be a table")
    extra = set(item) - _STEP_KEYS
    if extra:
        raise PolicyDenied("workflow has a raw key")
    step_id = item.get("id")
    prompt = item.get("prompt")
    if not isinstance(step_id, str) or not step_id.strip():
        raise PolicyDenied("workflow step id is invalid")
    if not isinstance(prompt, str) or not prompt.strip():
        raise PolicyDenied("workflow step prompt is invalid")
    _refuse_tokens(step_id)
    _refuse_tokens(prompt)
    agent = item.get("agent")
    account = item.get("account")
    if agent is not None:
        if not isinstance(agent, str) or not agent.strip():
            raise PolicyDenied("workflow step agent is invalid")
        _refuse_tokens(agent)
    if account is not None:
        if not isinstance(account, str) or not account.strip():
            raise PolicyDenied("workflow step account is invalid")
        _refuse_tokens(account)
    needs = _string_list(item.get("needs"), field="needs")
    depends = _string_list(item.get("depends"), field="depends")
    return WorkflowStep(
        id=step_id,
        prompt=prompt,
        agent=agent if isinstance(agent, str) else None,
        account=account if isinstance(account, str) else None,
        needs=needs + depends,
        functions=_string_list(item.get("functions"), field="functions"),
        tools=_string_list(item.get("tools"), field="tools"),
        subagents=_string_list(item.get("subagents"), field="subagents"),
    )


def _topo(steps: tuple[WorkflowStep, ...]) -> tuple[WorkflowStep, ...]:
    by_id: dict[str, WorkflowStep] = {}
    for step in steps:
        if step.id in by_id:
            raise PolicyDenied("workflow step id is duplicate")
        by_id[step.id] = step
    incoming = {step.id: 0 for step in steps}
    edges: dict[str, list[str]] = {step.id: [] for step in steps}
    for step in steps:
        for dep in step.needs:
            if dep not in by_id:
                raise PolicyDenied(f"unknown step {dep!r}")
            edges[dep].append(step.id)
            incoming[step.id] += 1
    ready = [step.id for step in steps if incoming[step.id] == 0]
    ordered: list[WorkflowStep] = []
    while ready:
        nid = ready.pop(0)
        ordered.append(by_id[nid])
        for nxt in edges[nid]:
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                ready.append(nxt)
    if len(ordered) != len(steps):
        raise PolicyDenied("workflow has a cycle")
    return tuple(ordered)


def load_workflow(cwd: Path) -> Workflow | None:
    path = cwd / "harness.toml"
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        harness = tomllib.load(handle)
    if "workflow" not in harness:
        return None
    table = harness.get("workflow")
    if not isinstance(table, dict):
        raise PolicyDenied("harness workflow table is invalid")
    extra = set(table) - _WORKFLOW_KEYS
    if extra:
        raise PolicyDenied("workflow has a raw key")
    workflow_id = table.get("id")
    if workflow_id is not None:
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            raise PolicyDenied("workflow id is invalid")
        _refuse_tokens(workflow_id)
    if "steps" not in table:
        return Workflow(steps=(), id=workflow_id if isinstance(workflow_id, str) else None)
    raw_steps = table.get("steps")
    if not isinstance(raw_steps, list):
        raise PolicyDenied("harness workflow.steps must be a list")
    steps = tuple(_parse_step(item) for item in raw_steps)
    _topo(steps)
    return Workflow(
        steps=steps,
        id=workflow_id if isinstance(workflow_id, str) else None,
    )


def run_workflow(
    cwd: Path,
    *,
    bus: object | None = None,
    store: SessionStore | None = None,
    audit: AuditLog | None = None,
    run: Callable[[WorkflowStep], object] | None = None,
) -> list[WorkflowStep]:
    cwd = cwd.resolve()
    log = audit if audit is not None else AuditLog(ravand_home())
    workflow = load_workflow(cwd)
    if workflow is None:
        return []
    ordered = _topo(workflow.steps)
    return run_policy_steps(
        ordered,
        cwd=cwd,
        root_id=workflow.id or "workflow",
        kind="workflow",
        bus=bus,
        store=store,
        audit=log,
        run=run,
    )
