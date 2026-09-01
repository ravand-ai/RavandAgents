# Modular runtime

Reading: [Docs map](README.md)

Previous: [Compared with DeepSeek Harness and Cordis](DSH-CORDIS.md)
Next: [Compared with OpenClaw, Hermes, Grok Build](COMPARE-PEERS.md)

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
| Human verification | off, local ask, named approver, plan | Plan mode approves the plan before writes |
| Skills | named `SKILL.md` packs | Allow list. Not a public store |
| Hooks | scripts on tool/file events | Not MCP. Deny from a hook fails closed |
| Memory | durable notes for later runs | Isolation scope + store plugin. Classified |
| Plugin | any of the rows below, plus more | One install path. Manifest names the kind |
| Cron | schedule → run or workflow | Same Policy path as webhook |
| Steer | extra instruction into a live run | ACP child or native loop |
| Stream | JSONL / SSE SessionEvent | `ravand run` and HTTP, not stdout text only |
| Workflow | graph of steps | May bind tools, functions, subagents |
| Pipeline | ordered stages | Same bindings as workflow |
| Eval | golden tasks, judges | Optional |
| Metrics | duration, tool calls, cost proxy, result enum | Always on in-process. OTLP if set |
| Trigger | CLI, HTTP API, webhook, cron | Policy still runs before any run starts |
| Bus | PGMQ (default), Kafka, other | Same task payload. Secrets never on the bus |

Workflows and pipelines are both runners. The difference is shape (graph vs ordered stages), not what they may attach. Either may accept tools, functions, and subagents. A step that cannot resolve its bindings fails closed.

## Triggers: CLI, API, webhook, cron

A run or a workflow may start from:

| Trigger | When |
|---------|------|
| CLI | `ravand run`, local v0 |
| HTTP API | Cloud and later local server. Authn required. Stream is SSE of SessionEvent. |
| Webhook | Signed inbound event. A rule maps the event to a workflow, pipeline, or single run. |
| Cron | Schedule in policy (`0 9 * * 1-5`). Fires the same Gateway path. |

The trigger does not skip Policy. Gateway receives the event, resolves policy and account, then enqueues or runs. An unsigned or unknown webhook fails closed. A cron job whose account or classification no longer matches is skipped and audited `trigger.denied`.

Webhook and cron secrets live in the profile store or org vault. They do not go in `harness.toml` as raw values. The file may name `secret_ref`.

## Skills

A skill is a named, versioned instruction pack (`SKILL.md` plus optional scripts). The loop may load it. A workflow is a graph of steps. They are not the same thing.

Project policy lists `skills.allow`. Unknown skills do not load. Skills inherit classification: a customer repo cannot load a skill that reads a personal memory store.

Ravand does not ship a public skill marketplace. ClawHub stays out.

The target repo's `AGENTS.md` (or `ravand.toml` skill index) may be loaded as context when policy allows `agents_md = true`.

## Hooks

A hook is a command that runs on an event: `tool.pre`, `tool.post`, `file.write`, `run.start`, `run.end`. It is not an MCP server.

The hook receives a JSON payload (no secrets). Exit 0 continues. Non-zero is deny for `tool.pre` and `file.write` (fail closed). `tool.post` and `run.end` may warn only; they cannot rewrite history.

Hooks are listed in `harness.toml`. A missing hook binary fails closed for pre-hooks.

## Memory

Memory is durable notes a later run may read. It is not the audit log and not the vendor transcript.

Isolation and storage are two seams. Policy names the **scope**. The preset names the **store**. Do not hard-code files.

### Isolation scopes

A memory space has one primary scope. Mixing scopes in one space is not allowed.

| Scope | Who can read/write | Typical use |
|-------|--------------------|-------------|
| `session` | this run only | scratch. Dropped when the run ends |
| `user` | one cloud user (or local OS user) | personal preferences |
| `profile` | one seat HOME | work vs personal notes |
| `project` | one repo / project id | decisions for this codebase |
| `org` | users the role allows | shared runbooks |
| `account` | one named LLM/CLI account | provider-specific hints |
| custom | a plugin-defined key | only if Policy lists it |

Customer classification never uses `user`/`profile` spaces that are personal. Project memory on a customer repo stays on work profiles. A query that would cross a denied scope fails closed. No silent merge of user memory into project memory.

### Stores

The store is a plugin. Same isolation API for all of them.

| Store | When |
|-------|------|
| `file` | default local. Trees under the profile or project dir |
| `sqlite` | single-file DB |
| `postgres` | default when cloud/org memory is on |
| `graph` | entities and relations (decisions, people, modules) |
| other | allowed if it implements read/write/search/delete with scope in every key |

A project may use more than one space: e.g. `project` on `graph` plus `user` on `file`. The loop only sees spaces Policy injects. Agents cannot dump a store. Work bodies still off audit by default.

## Plugin system

Everything extra is a **plugin**. Functions, kernel services, pipelines, webhooks, third-party integrations, memory stores, buses, sandboxes, loops, skills, hooks, and MCP adapters all install the same way. The kernel is the plugin host. There is not a second plugin runtime.

```
ravand plugin add <source>     # path, git, or registry later
ravand plugin list
# preset / harness.toml names which plugins this project mounts
```

### Manifest

Each plugin ships `plugin.toml` (name may stay `plugin.toml`):

```toml
id = "acme.jira"
version = "1.2.0"
kind = "integration"          # see kinds below
inject = ["policy", "bus"]    # kernel services it needs

[grants]
# what it is allowed to register. Empty grants mount nothing.
```

Unknown `kind` fails closed. A plugin cannot unmount Policy or Permission Broker. A plugin cannot read secret stores except through the account/vault seam it was granted.

### Kinds

| kind | Registers |
|------|-----------|
| `function` | one or more callable functions for the loop |
| `tool` | model-facing tools |
| `service` | a kernel service on a new or existing key |
| `loop` | native agent loop |
| `sandbox` | sandbox provider |
| `bus` | bus provider |
| `memory` | memory store |
| `account` | provider/account adapter |
| `skill` | skill pack |
| `hook` | hook scripts or listeners |
| `mcp` | MCP server adapter |
| `trigger` | webhook, cron helper, or other inbound |
| `workflow` | workflow definition or step type |
| `pipeline` | pipeline definition or stage type |
| `integration` | third party (issue tracker, chat, CI) |
| `eval` | judge or golden-task source |

One package may declare several kinds. Each kind is a separate grant. An integration that also wants a webhook must list both `integration` and `trigger`.

### Trust

- Project `plugins.allow` / `plugins.deny` in `harness.toml`.
- Org may pin hashes later. v1 may load from disk path only.
- Plugin code runs in-process unless the plugin asks for a sandbox grant.
- Third-party integrations never get CLI cookies. API keys only via `secret_ref`.
- Disable is unload. Effects reverse. That is kernel law.

Skills and hooks remain first-class seams. They can also ship as plugins of those kinds. A loose `SKILL.md` in the repo is still a skill; it does not need a full package if policy allows repo skills.

## Plan mode

When `human = "plan"` (or permissions mode `plan`):

1. The runtime asks the agent for a plan (ACP prompt or native).
2. Permission Broker shows the plan. Writes and shell stay denied until allow.
3. Allow → execute. Deny or timeout → no writes.

This is coarser than per-tool `ask` and stricter than `repo-only`. `--yes` does not auto-approve a plan unless policy says `plan_ci = true`.

## Steer

`Gateway.Steer(sessionId, text)` pushes extra instruction into a live run.

- ACP child: `session/prompt` on the same session (or vendor steer if advertised).
- Native loop: inject into the next model request.
- If the session is not running: error, do not start a new run.

Cancel remains `Gateway.Cancel`. Steer is not cancel.

## Stream

`ravand run` and the HTTP API emit `SessionEvent` objects, one JSON object per line (CLI) or SSE (HTTP). Stdout text-only is not enough for bots.

Minimum event types: `run.started`, `text.delta`, `tool.call`, `permission.ask`, `plan.ready`, `steer.accepted`, `run.ended`. Schema in SCHEMA.md. No secret fields.

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
- Extra capability is a plugin. Plugins cannot unmount Policy or Permission Broker.
- BSL 1.1.

## v0 vs later

v0 still ships the ACP + seat path: `ravand which`, `ravand run --format jsonl`, isolated HOMEs, permission ask, session, audit.

Skills, hooks, plugin host, memory (file store + scopes), plan mode, steer, ACP server: v1. Graph/Postgres memory stores, cron, HTTP SSE, webhooks, native loop, sandbox plugins, workflows, bus, cloud users, eval store: later.

Next: [Compared with OpenClaw, Hermes, Grok Build](COMPARE-PEERS.md)
