# HLD: Ravand Agents services

Reading: [Docs map](README.md)

Previous: [Roadmap](ROADMAP.md)
Next: [Compared with DeepSeek Harness and Cordis](DSH-CORDIS.md), then [Modular runtime](MODULAR.md)

Status: v0.3  
Style: local-first, then Postgres/PGMQ workers and cloud users  
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
   Tools · Functions · MCP · Subagents
   Sandbox · Human verification
   Workflow · Pipeline
   Session · Audit · Eval · Metrics
        │
 Dispatcher (v2) ── PGMQ ── Worker machines
```

Seam list and project rules: [MODULAR.md](MODULAR.md).

## Design rules

1. Every run has a **profile** (seat HOME) and a **preset** (plugin tree). Policy beats flags except audited override.
2. Accounts are named. One vendor may have many CLI logins and many API keys. The project names which accounts may run.
3. Two model paths: subscription CLI over ACP, or native loop with a named API account. Do not wrap a vendor CLI's HTTP. Do not scrape TUI output.
4. Secrets never live in `harness.toml`, PGMQ, or work audit (unless `RAVAND_AUDIT_BODIES=1`). CLI cookies stay in the profile HOME and are not read. API keys live in the profile secret store or the cloud vault.
5. Workflows and pipelines may both bind tools, functions, and subagents. Missing bindings fail closed.
6. Human verification, when required, blocks the action until allow or timeout-deny.
7. v0 = one process, ACP + seats. Native loop, sandbox plugins, workflows, cloud users, eval store come later. PGMQ is v2.
8. PGMQ moves **tasks**, never credentials.
9. Every task has `task_id` + a trace. Fail closed if policy, permission, or account cannot be evaluated.
10. Policy and Permission Broker cannot be unmounted.

## Services

### Gateway

Only public surface.

Logical API:

- `Which(cwd) → ResolvedPolicy + command`
- `Run(cwd, prompt, agent?) → stream SessionEvent`
- `Login(profile, account) → hint | status`
- `Cancel(sessionId)`
- later: `Approve(taskId)`, `Eval(taskId)`, workflow/pipeline start

Modes:

- ACP **client** (CLI, CI)
- ACP **server** later (Zed/VS Code see one agent named `ravand`)

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

Native loop (later) is a different runtime plugin on the same Permission Broker, Session, Audit, and Sandbox seams. v0 does not ship it.

### Permission Broker

Answers `session/request_permission`.

| Mode | In-repo read | In-repo write | Outside repo | Shell |
|---|---|---|---|---|
| repo-only | allow | allow | deny | ask (deny if `--yes`) |
| approve-reads | allow | ask | deny | ask |
| deny-writes | allow | deny | deny | deny |
| ask | ask | ask | deny | ask |

Human verification in the cloud is the same broker with a named approver and a timeout. Timeout is deny.

### Sandbox

Seam. Provider is none, repo-only OS, container, or remote. Customer classification cannot choose `none` if the project writes files or runs shell.

### Workflow and pipeline

Both are runners. Workflow is a graph. Pipeline is ordered stages. Either may attach tools, functions, and subagents. A step fails closed if a binding is denied or missing.

### Session Store

`~/.ravand/sessions/*.json`. Later SQLite / Postgres `tasks`.

### Audit Log

Append-only. Separate concern from Session. Work bodies off by default.

### Dispatcher (v2)

`pgmq.send` after Policy resolve. Routes by profile/agent. Archives completed messages.

### Worker (v2)

One process per machine that already has CLI logins.

1. `read('q.tasks', vt=600)`
2. `set_vt` heartbeat while ACP live
3. if `Profile.AuthOK` false → fast nack `capability_miss`
4. run Runtime on local worktree
5. `archive` on terminal state

Workspace must exist on the worker. Queue does not ship git.

### Observability

OpenTelemetry GenAI conventions + `ravand.*` attributes.
No-op exporter if OTLP unset.

### Eval and metrics

Metrics always: duration, result enum, tool calls, permission denials, human-wait. OTLP if set.

Eval store later: golden tasks, account vs account, judge plugin.

### Plugin Host

MCP servers, functions, and subagents are selective per project. Slack and other channels later. Not v0.

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

v2 inserts Dispatcher between 4 and 5 when `RAVAND_PGMQ_URL` is set.

## PGMQ

Infra: Postgres only.

| Queue | From | To |
|---|---|---|
| q.tasks | Dispatcher | Workers |
| q.events | Workers | Gateway / sink (optional if OTLP) |
| q.results | Workers | Gateway |

Optional split: `q.tasks.work`, `q.tasks.personal`.
FIFO group key = repo.

Primitives: `send`, `read(vt)`, `set_vt`, `archive` (success/fail), `delete` only for poison after inspect.

Idempotency: `task_id`. Session Store rejects second start if status is running|done.

## Trust

| Data | Where | Ravand Agents may read? |
|---|---|---|
| Policy | git + user config | yes |
| Vendor CLI cookies | profile HOME, vendor files | **no** |
| LLM API keys | profile secret store or cloud vault | **use, never log** |
| Prompts | memory + optional events | work: default no persist |
| Task metadata | sessions / Postgres | yes |

## Deployment

- v0: single binary on the laptop that has the CLIs
- v2: Gateway + Postgres; workers on machines that have the repo and the allowed accounts
- Cloud: users and roles. Org vault for API keys. Still never store company CLI cookies in SaaS.

Next: [Compared with DeepSeek Harness and Cordis](DSH-CORDIS.md), then [Modular runtime](MODULAR.md)
