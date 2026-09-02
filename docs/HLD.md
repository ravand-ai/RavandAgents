# HLD: Ravand Agents services

Reading: [Docs map](README.md)

Previous: [Roadmap](ROADMAP.md)
Next: [Compared with DeepSeek Harness and Cordis](DSH-CORDIS.md), then [Modular runtime](MODULAR.md)

Status: v0.3  
Style: local-first, then workers on a bus (Postgres+PGMQ default) and cloud users  
Kernel: ours, Cordis-shaped. Not the Cordis package.  
I/O with agents: ACP v1 stdio and/or a native loop, both behind policy.

## Context

Ravand Agents is a modular control plane and runtime. A project picks providers, accounts, loops, tools, MCP, sandbox, workflows, and pipelines. People hold mixed seats and mixed API keys. Policy says which of those may touch this repo.

```
Human / IDE / CI / cloud user
        │
        ▼
     Gateway
        │
 Ravand kernel (plugins)
   Policy · Profile · Accounts · Registry
   Loop (ACP child and/or native)
   Tools · Functions · MCP · Subagents · Skills · Hooks
   Sandbox · Human verification · Plan · Steer
   Memory · Plugins · Cron · Stream
   Workflow · Pipeline
   Session · Audit · Eval · Metrics
        │
 Dispatcher (v2) ── bus (PGMQ default) ── Worker machines
 HTTP API · webhooks (later)
```

Seam list and project rules: [MODULAR.md](MODULAR.md).

## Design rules

1. Every run has a **profile** (seat HOME) and a **preset** (plugin tree). Policy beats flags except audited override.
2. Accounts are named. One vendor may have many CLI logins and many API keys. The project names which accounts may run.
3. Two model paths: subscription CLI over ACP, or native loop with a named API account. Do not wrap a vendor CLI's HTTP. Do not scrape TUI output.
4. Secrets never live in `harness.toml`, the bus, or work audit (unless `RAVAND_AUDIT_BODIES=1`). CLI cookies stay in the profile HOME and are not read. API keys live in the profile secret store or the cloud vault.
5. Workflows and pipelines may both bind tools, functions, and subagents. Missing bindings fail closed.
6. Human verification, when required, blocks the action until allow or timeout-deny. Plan mode blocks writes until the plan is allowed.
7. v0 = one process, ACP + seats + JSONL stream. Plugin host, skills, hooks, memory (file store), plan, steer, ACP server are v1. Native loop, cron, HTTP, webhooks, workflows, bus, cloud users, eval store come later.
8. The bus moves **tasks**, never credentials. Default bus is Postgres + PGMQ. Kafka and others are providers of the same seam. Do not import the bus driver from Policy or Runtime.
9. Kernel services use dependency injection by key. Packages depend on seams, not on Postgres.
10. Every task has `task_id` + a trace. Fail closed if policy, permission, or account cannot be evaluated.
11. Policy and Permission Broker cannot be unmounted.
12. Extra capability arrives as a plugin with a kind and grants. Memory isolation is policy. Memory store is a plugin.

## Services

### Gateway

Only public surface.

Logical API:

- `Which(cwd) → ResolvedPolicy + command`
- `Run(cwd, prompt, agent?) → stream SessionEvent` (JSONL)
- `Login(profile, account) → hint | status`
- `Cancel(sessionId)`
- `Steer(sessionId, text)`
- later: HTTP API (SSE of the same events)
- later: inbound webhook or cron → workflow, pipeline, or run
- later: `Approve(taskId)`, `ApprovePlan(taskId)`, `Eval(taskId)`

Modes:

- ACP **client** (CLI, CI)
- ACP **server** (v1: Zed/VS Code see one agent named `ravand`)
- HTTP **API** later (SSE)
- **Webhook** and **cron** later (signed or scheduled → policy → bus or local run)

### Policy

Reads, in order: repo `harness.toml` → org defaults (later) → `~/.ravand/config.toml`.

Outputs `ResolvedPolicy` (see SCHEMA.md).

### Profile

Maps `profile → { homeDir, env, allowedAgents }`.

```
~/.ravand/profiles/work/.claude
~/.ravand/profiles/work/.grok
~/.ravand/profiles/work/.cursor
~/.ravand/profiles/personal/.kimi
~/.ravand/profiles/personal/.grok
```

Creates dirs. Probes CLI login. Hands Runtime a scrubbed env. Does not read vendor cookie files.

Named **accounts** live on the profile: CLI adapters and API-key accounts. See [MODULAR.md](MODULAR.md).

### Registry

Adapter catalog. Data, not logic.

| id | command |
|---|---|
| grok | `grok agent stdio` |
| kimi | `kimi acp` |
| claude | `npx -y @agentclientprotocol/claude-agent-acp` |
| cursor | `cursor-agent acp` |
| opencode | `opencode acp` |
| dsh | `dsh --profile acp` |

### ACP Runtime

Spawn + handshake + stream + overflow trigger.

`initialize` → optional `authenticate` → `session/new|load` → `session/prompt` → `session/close`.

Steer is a further `session/prompt` (or vendor steer) on the live session. Stream every ACP session event as `SessionEvent` JSONL.

Native loop (later) is a different runtime plugin on the same Permission Broker, Session, Audit, Sandbox, Skill, Hook, and Memory seams. v0 does not ship it.

### Permission Broker

Answers `session/request_permission`.

| Mode | In-repo read | In-repo write | Outside repo | Shell |
|---|---|---|---|---|
| repo-only | allow | allow | deny | ask (deny if `--yes`) |
| approve-reads | allow | ask | deny | ask |
| deny-writes | allow | deny | deny | deny |
| ask | ask | ask | deny | ask |
| plan | allow after plan allow | deny until plan allow | deny | deny until plan allow |

Human verification in the cloud is the same broker with a named approver and a timeout. Timeout is deny. Plan mode is `ApprovePlan` before any write.

### Sandbox

Seam. Provider is none, repo-only OS, container, or remote. Customer classification cannot choose `none` if the project writes files or runs shell.

### Skills

Named `SKILL.md` packs. Policy allow list. Loaded into the loop, not executed as a workflow.

### Hooks

Commands on `tool.pre`, `tool.post`, `file.write`, `run.start`, `run.end`. Pre-hooks may deny (fail closed).

### Memory

Durable notes. Isolation scope (`session`, `user`, `profile`, `project`, `org`, `account`, or custom) is policy. Store (`file`, `sqlite`, `postgres`, `graph`, other) is a plugin. Injected only through Policy. Not the audit log. Cross-scope merge fails closed. See [MODULAR.md](MODULAR.md).

### Cron

Scheduler trigger. Same Gateway path as webhook. Skips and audits if policy no longer allows the job.

### Stream

`SessionEvent` JSONL on CLI. SSE on HTTP. See SCHEMA.md.

### Workflow and pipeline

Both are runners. Workflow is a graph. Pipeline is ordered stages. Either may attach tools, functions, and subagents. A step fails closed if a binding is denied or missing.

### Session Store

`~/.ravand/sessions/*.json`. Later SQLite / Postgres `tasks`.

### Audit Log

Append-only. Separate concern from Session. Work bodies off by default.

### Dispatcher (v2)

After Policy resolve, `Bus.send` to `q.tasks`. Routes by profile/agent/account. Archives or acks completed messages. The bus provider is injected. Default implementation is PGMQ.

### Worker (v2)

One process per machine that already has the allowed accounts.

1. `Bus.read('q.tasks')` with visibility timeout (PGMQ `vt=600` or Kafka equivalent)
2. Heartbeat while the run is live
3. if `Profile.AuthOK` false → fast nack `capability_miss`
4. if cordoned → fast nack `worker.cordoned` (no run)
5. run Runtime on local worktree
6. archive or ack on terminal state
7. drain: finish in-flight, then stop (no new reads)

Workspace must exist on the worker. Queue does not ship git.

### Observability

OpenTelemetry GenAI conventions + `ravand.*` attributes.
No-op exporter if OTLP unset.

### Eval and metrics

Metrics always: duration, result enum, tool calls, permission denials, human-wait. OTLP if set.

Eval store later: golden tasks, account vs account, judge plugin.

### Plugin Host

The kernel is the host. One install path for functions, services, tools, loops, sandboxes, buses, memory stores, skills, hooks, MCP, triggers, workflows, pipelines, integrations, and evals.

Manifest: `id`, `version`, `kind`, `inject`, `grants`. Unknown kind or missing grant fails closed. Plugins cannot unmount Policy or Permission Broker. Unload reverses effects.

`ravand plugin add|list`. Project `plugins.allow` / `plugins.deny`. Details in [MODULAR.md](MODULAR.md).

## Run path

```
1. Gateway.Run(cwd, prompt)
2. Policy.Resolve
3. Profile.Env + AuthOK
4. Registry.Lookup
5. Runtime.Spawn + ACP
6. Permission Broker
7. Session + Audit
8. rate_limit + overflow? → repeat 4–7
9. stream to caller
```

v2 inserts Dispatcher between 4 and 5 when a bus is configured.

HTTP API and webhooks enter at step 1. They do not skip Policy.

## Bus

Seam, not a Postgres import. Logical queues:

| Queue | From | To |
|---|---|---|
| q.tasks | Dispatcher | Workers |
| q.events | Workers | Gateway / sink (optional if OTLP) |
| q.results | Workers | Gateway |

Optional split: `q.tasks.work`, `q.tasks.personal`.
FIFO group key = repo.

Primitives the provider must implement: `send`, `read` with visibility timeout or equivalent, heartbeat, archive/ack (success/fail), poison after inspect.

Default provider: Postgres + PGMQ. Alternate: Kafka. Others if they meet the primitives.

Idempotency: `task_id`. Session Store rejects second start if status is running|done. That store may be files, SQLite, or Postgres. It is not the bus.

## Trust

| Data | Where | Ravand Agents may read? |
|---|---|---|
| Policy | git + user config | yes |
| Vendor CLI cookies | profile HOME, vendor files | **no** |
| LLM API keys | profile secret store or cloud vault | **use, never log** |
| Prompts | memory + optional events | work: default no persist |
| Task metadata | sessions / DB | yes |

## Deployment

- v0: single binary on the laptop that has the CLIs
- v2: Gateway + bus (PGMQ default) + workers on machines that have the repo and the allowed accounts. HTTP API and webhooks on the Gateway.
- Cloud: users and roles. Org vault for API keys. Still never store company CLI cookies in SaaS.

Next: [Compared with DeepSeek Harness and Cordis](DSH-CORDIS.md), then [Modular runtime](MODULAR.md)
