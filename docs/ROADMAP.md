# Roadmap

Reading: [Docs map](README.md)

Previous: [How Ravand can succeed](SUCCESS.md)
Next: [HLD](HLD.md)

[SUCCESS.md](SUCCESS.md) still wins on **what we ship first**. This file is version order. Do not start v1 because the TUI is ugly.

The wedge is mixed seats under policy: `ravand which` / `ravand run` / audit. Grok already has a coding TUI. Ravand is the control plane, not a worse Grok.

## Freeze: TUI

We over-built `ravand tui` (Textual, chat bubbles, copy, keys, timers). It is optional chrome on v0.

**Stop new TUI tickets** until:

1. [Issue #9](https://github.com/ravand-ai/RavandAgents/issues/9) dogfood lands through `ravand run` (a real commit + PR, not a talk-only `run.ended ok`)
2. The four SUCCESS checks hold on this repo

[Issue #51](https://github.com/ravand-ai/RavandAgents/issues/51) (strip TUI junk) waits. Scripts keep `ravand run --format jsonl`.

## v0: one machine (in progress)

**Shipped**

- Slices 0–4: uv workspace, policy, `which` / `login` / `run`, ACP NDJSON, sessions, audit, overflow
- `ravand status` login doctor
- kimi / cursor (and grok) as registry backends
- Auth handshake: missing login is exit 2 + `auth.missing`
- Human ask on a TTY (`--yes` for scripts)
- Optional `ravand tui` (do not grow it)
- Dogfood #9 via `ravand run -a grok` ([#9](https://github.com/ravand-ai/RavandAgents/issues/9) / PR [#60](https://github.com/ravand-ai/RavandAgents/pull/60))
- ACP turn survives the first tool: pick advertised permission `optionId` ([#54](https://github.com/ravand-ai/RavandAgents/issues/54) / PR [#58](https://github.com/ravand-ai/RavandAgents/pull/58))
- Slice 5: OTel spans if `OTEL_EXPORTER_OTLP_ENDPOINT` is set, else no-op ([#55](https://github.com/ravand-ai/RavandAgents/issues/55) / PR [#59](https://github.com/ravand-ai/RavandAgents/pull/59); wiring [#57](https://github.com/ravand-ai/RavandAgents/issues/57) / PR [#61](https://github.com/ravand-ai/RavandAgents/pull/61))

**Still v0. Do this. No native loop, no bus.**

| Order | Work | Why |
|-------|------|-----|
| 4 | Two other real repos on `ravand which` + `run` ([#56](https://github.com/ravand-ai/RavandAgents/issues/56)) | SUCCESS: `which` is right 100% of the time; a second human can login |

Exit: we refuse naked `grok` / `kimi` / `cursor-agent` on classified repos. Audit answers which profile touched the tree. Then v1.

## v1: modular local runtime

Same kernel. Still one machine. Policy grows; the CLI spawn path stays.

- Named accounts per profile (several CLI logins and API keys)
- `harness.toml` picks accounts, MCP, functions
- Native loop plugin (optional; ACP still works)
- Sandbox seam
- ACP **server** so Zed / VS Code attach to `ravand`
- Plugin host: `ravand plugin add|list`, kinds in [MODULAR.md](MODULAR.md). Load a disk package. Not a marketplace
- Skills allow list (`SKILL.md`, do not invent a second format)
- Hooks (`tool.pre` fail closed)
- Memory: isolation scopes + file store default
- Plan mode (`human = "plan"`)
- `ravand steer <sessionId>`
- Load the target repo `AGENTS.md` when policy allows
- Classification: customer repo never uses a personal profile or personal account

Exit: one project can say “this job is work-grok ACP, that job is company-claude API, both under the same deny list.”

## v2: workflows and a queue

Only after v1 is used daily on more than this repo.

- Workflows and pipelines (tools, functions, subagents)
- Human verification queue (named approver, timeout deny)
- HTTP API (SSE) and signed webhooks
- Cron (same Policy path)
- Bus seam: Postgres + PGMQ default (`q.tasks`, `q.events`, `q.results`). Kafka is an alternate provider, not the default
- Worker process + capability advertisement
- Cloud users, roles, per-project access
- Org vault for API keys. Still no vendor cookies in SaaS

Exit: a second machine can take a task you did not start in a TTY.

## v3: control plane and evals

- Fail closed if Policy or DB is down
- Inventory: adapters × profiles × workers × accounts
- `ravand pause --agent X --profile work`
- Signed evidence (task_id, actor, policy hash, decision)
- Judge plugin: tests must pass before `status=ok`
- Eval store: golden tasks, account vs account
- Cost proxy: utilization and provider usage
- Worker drain/cordon
- SLOs + page on queue age

Exit: a company can ask “who ran what, under which seat, did tests pass.”

## v4: channels and partners (not the product)

Do not pull these forward to look busy.

- Slack / OpenACP / other chat channels
- InsForge as one MCP row
- AgentField identity
- GRC export (NIST / EU), not a GRC product
- Infra AIOps (disks, kube)
- Plugin marketplace
- Desktop / companion apps
- Growing `ravand tui` into a coding IDE

## What we will not do

- Compete with Grok Build on fullscreen coding UX
- Add Kafka, a bus, or cloud users to fix a local ACP bug
- Add a PyPI package for convenience (TUI already has `textual`; that is enough)
- Soft-deny
- Rename profile / preset / harness again

## Positioning

Ravand is a **modular agent control plane**. Subscription CLIs, native loops, and later cloud users share one policy.

- Governance: runtime gates + evidence, not DPIAs
- AIOps: queue/worker health, not cluster healing
- AgentOps: traces, evals, cost in v3

Next: [HLD.md](HLD.md)
