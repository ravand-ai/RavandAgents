# Governance and ops mapping

Reading: [Docs map](README.md)

Previous: [Schema](SCHEMA.md)
Next: [examples/harness.toml](../examples/harness.toml), then [AGENTS.md](../AGENTS.md)

Ravand Agents is not a GRC product and not an AIOps suite.
This file is the gap list so features are added on purpose.

## One-question tests

- **Governance:** if the checker fails, does the action still run? If yes, that path is only observability. Ravand Agents must fail closed.
- **AIOps:** can we see fleet health and stop a bad worker without SSH folklore?
- **AgentOps:** can we replay a task as a tool timeline and say whether tests passed?

## What Ravand Agents already designs

| Control | Service |
|--------|---------|
| Who (which seat) | Profile HOME |
| What agent | Policy + Registry |
| Where (which tree) | cwd + classification |
| May it write | Permission Broker |
| Tape | Audit + Session + PGMQ archive |
| Spread across machines | Dispatcher + Worker |
| See the run | Observability |

## Missing for “governance-ready”

- Estate inventory
- Signed evidence
- Named human approver + timeout
- Kill switch across workers
- Detect `claude` run outside Ravand Agents on a managed host (optional)

## Missing for “AgentOps-ready”

- Full session replay UI
- Independent judge
- Eval regressions when a CLI updates
- Dollar cost (may never exist on subscriptions; use utilization)

## Missing for “AIOps-ready”

- SLO + paging
- Drain/cordon
- Poison queue workflow
- Workspace-mount health (“git is not on this worker”)

## Data classification rule

| classification | allowed profiles |
|---|---|
| public | any |
| internal | work, or personal if policy says so |
| customer | work only |

Never put customer prompts on a personal profile HOME.

Next: [examples/harness.toml](../examples/harness.toml), then [AGENTS.md](../AGENTS.md) from "Adopted product rules".
