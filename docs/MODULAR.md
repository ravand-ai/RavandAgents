# Modular runtime

Reading: [Docs map](README.md)

Previous: [Compared with DeepSeek Harness and Cordis](DSH-CORDIS.md)
Next: [Schema](SCHEMA.md)

This file is product law for how a project picks providers, loops, tools, sandboxes, and people. [HLD.md](HLD.md) names services. This file names the seams those services plug.

Ravand is fully modular. A project chooses its providers, accounts, agent loop, tools, functions, MCP servers, sandbox, workflows, pipelines, and (later) which message bus it uses. Nothing is hard-wired except kernel law: fail closed, secrets stay out of git and out of the queue, profile is the seat.

The kernel uses **dependency injection**. Plugins declare the services they need by key. The context waits until those services exist, then mounts. Do not import a concrete Postgres, Kafka, or sandbox class from business code. Swap the provider in the preset.

Other patterns we keep: seams (definition, provider, consumer), waterfall for permission, strategy for loop/sandbox/bus, append-only log. We do not invent a second container beside the kernel.

## Two ways to talk to a model

A project may use either, or both, under policy.

| Path | How it runs | Secrets | Loop |
|------|-------------|---------|------|
| Subscription CLI | Spawn vendor ACP (`grok agent stdio`, `dsh --profile acp`, …) | Vendor login files in the profile HOME. Ravand does not read them. | Vendor owns the loop |
| Native LLM | Named account + API key in the profile secret store | Key never in `harness.toml`, never in PGMQ, never in audit by default | Ravand loop plugin, if the project selected one |

Do not wrap a subscription CLI's HTTP. Do not scrape TUI output. Native path calls the provider API only through the selected account plugin.

## Accounts

A person or org may hold several Claude accounts, several Grok accounts, and other providers. Each account is a named record on a profile.

```
profile work
  account claude-company     kind=cli     home=.claude
  account claude-api         kind=api     secret=...
  account grok-work          kind=cli     home=.grok
  account grok-api-2         kind=api     secret=...
```

Project policy names which accounts may run here, for which jobs, with which loop and sandbox. A flag must not pick an account the policy denies.

Cloud version: the same account records live in an org vault. Users get access by role. One company seat is still not shared as a copied cookie. API keys in the vault are issued per role, not pasted into chat.

## Seams a project may choose

Each row is a plugin. The project preset lists which provider implements it.

| Seam | What you pick | Notes |
|------|----------------|-------|
| Provider / account | CLI adapter and/or LLM account | Many accounts per vendor |
| Agent loop | none (ACP child) or a native loop plugin | Native loop is optional |
| Tools | file, shell, search, custom | Only what policy allows |
| Functions | named function-calling tools | Selective. Not all at once |
| MCP | named servers from `harness.toml` | Selective. Deny list wins |
| Subagents | ACP child or native child | Isolated HOME or sandbox |
| Sandbox | none, repo-only, container, remote | Required when policy says so |
| Human verification | off, local ask, named approver | If needed. Timeout fail closed |
| Workflow | graph of steps | May bind tools, functions, subagents |
| Pipeline | ordered stages | Same bindings as workflow |
| Eval | golden tasks, judges | Optional |
| Metrics | duration, tool calls, cost proxy, result enum | Always on in-process. OTLP if set |
| Trigger | CLI, HTTP API, webhook | Policy still runs before any run starts |
| Bus | PGMQ (default), Kafka, other | Same task payload. Secrets never on the bus |

Workflows and pipelines are both runners. The difference is shape (graph vs ordered stages), not what they may attach. Either may accept tools, functions, and subagents. A step that cannot resolve its bindings fails closed.

## Triggers: CLI, API, webhook

A run or a workflow may start from:

| Trigger | When |
|---------|------|
| CLI | `ravand run`, local v0 |
| HTTP API | Cloud and later local server. Authn required. |
| Webhook | Signed inbound event. A rule maps the event to a workflow, pipeline, or single run. |

The trigger does not skip Policy. Gateway receives the event, resolves policy and account, then enqueues or runs. An unsigned or unknown webhook fails closed.

Webhook secrets live in the profile store or org vault, same as API keys. They do not go in `harness.toml` as raw values. The file may name `secret_ref`.

## Bus: Postgres first, not Postgres-only

v2 ships a **bus seam**. Dispatcher and Worker talk to `q.tasks`, `q.events`, `q.results` as names. They do not import `pgmq` from policy or runtime code.

| Provider | Role |
|----------|------|
| Postgres + PGMQ | Default. This is what we build first and dogfood. |
| Kafka | Alternate bus. Same payload, different delivery. |
| Other | Allowed if it implements the seam: send, read with visibility timeout or equivalent, heartbeat, archive/ack, poison after N failures. |

Focus stays on Postgres: session/task tables, eval store, and the first bus provider are Postgres. A deployment that picks Kafka still may use Postgres for records, or another store later. Do not require Kafka. Do not scatter `RAVAND_PGMQ_URL` through packages. One bus config: driver + URL.

Idempotency stays `task_id` on the Session Store, independent of the bus.

## Human verification

When policy or a step says a human must confirm:

- Local: Permission Broker `ask` (already in HLD).
- Cloud: named approver, timeout, then deny if nobody answers.
- `--yes` in CI maps `ask` to deny unless the project explicitly allows auto-approve for that class of action.

Verification is not a log line. If the human is required and missing, the action does not run.

## Sandboxes

A sandbox is a seam, not a hardcoded Docker call. Projects pick a provider: none (repo-only permission table), OS user, container, or remote worker.

The kernel does not execute shell or writes itself except through the selected sandbox and permission waterfall. Unmounting the sandbox plugin is allowed only if policy names `sandbox = "none"` and classification is not `customer`.

## Cloud access

Local v0: one human, many profiles.

Cloud later: many users on one org.

| Subject | Access |
|---------|--------|
| User | which projects, which profiles, which accounts |
| Role | runner, approver, admin |
| Project | which accounts, loops, MCP, sandbox |
| Classification | customer work stays on work profiles and work accounts |

Different users on the same project may see different accounts and different tool sets. Policy still fail-closes if the role cannot be resolved.

## Evals and metrics

Metrics are not optional in the process: duration, result enum, tool-call count, permission deny count, rate_limit, human-wait time.

Evals are a plugin: golden tasks, compare two accounts (Claude vs Grok), judge (tests must pass). Cloud stores eval history. Local writes under `~/.ravand/evals/` when enabled.

Dollar cost: use provider usage when the native path exposes it. Subscription CLIs may only have utilization as a proxy.

## What stays kernel law

These are not project options:

- Fail closed if policy, permission, or account resolution cannot decide.
- Secrets not in git, not in queue payloads, not in work audit unless `RAVAND_AUDIT_BODIES=1`.
- Profile = seat HOME. Preset = plugin tree.
- Customer classification never uses a personal profile or a personal account.
- Own kernel. Not the Cordis package. Not a dsh fork.
- BSL 1.1.

## v0 vs later

v0 still ships the ACP + seat path: `ravand which`, `ravand run`, isolated HOMEs, permission ask, session, audit.

Native loop, named API accounts, sandbox plugins, workflows, pipelines, HTTP API, webhooks, bus (PGMQ first), cloud users, eval store: later slices. The seams exist in this doc so HLD and SCHEMA do not paint themselves into a CLI-only or Postgres-only corner.

Next: [Schema](SCHEMA.md)
