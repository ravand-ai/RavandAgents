# HLD: Ravand Agents services

Reading: [Docs map](README.md)

Previous: [Roadmap](ROADMAP.md)
Next: [Compared with DeepSeek Harness and Cordis](DSH-CORDIS.md)

Status: v0.2  
Style: local-first, then Postgres/PGMQ workers  
I/O with agents: ACP v1 JSON-RPC over stdio only

## Context

Users run vendor coding-agent CLIs on subscription logins. Ravand Agents is the control plane: policy, tenancy, distribution, observability.

```
Human / IDE / CI
        │
        ▼
     Gateway
        │
 Policy + Profile + Registry
        │
   ACP Runtime ──► vendor CLI
        │
 Permission · Session · Audit
        │
 Dispatcher (v2) ── PGMQ ── Worker machines
        │
 Observability (OTLP)
```

## Design rules

1. Vendor harness owns the model loop. Ravand Agents never wraps provider HTTP.
2. Every run has a **profile**. Profile = isolated HOME / credential dir.
3. Every repo has **policy** (`harness.toml`). Policy beats flags except audited override.
4. ACP is the only agent I/O. MCP is optional, attached at `session/new`.
5. v0 = one process (modules). v2 = Postgres + PGMQ + workers.
6. PGMQ moves **tasks**, never credentials.
7. Every task has `task_id` + a trace. Fail closed if policy cannot be evaluated.

## Services

### Gateway

Only public surface.

Logical API:

- `Which(cwd) → ResolvedPolicy + command`
- `Run(cwd, prompt, agent?) → stream SessionEvent`
- `Login(profile, agent) → hint | status`
- `Cancel(sessionId)`

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

Creates dirs. Probes login. Hands Runtime a scrubbed env. Does not read token files.

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

### Permission Broker

Answers `session/request_permission`.

| Mode | In-repo read | In-repo write | Outside repo | Shell |
|---|---|---|---|---|
| repo-only | allow | allow | deny | ask (deny if `--yes`) |
| approve-reads | allow | ask | deny | ask |
| deny-writes | allow | deny | deny | deny |
| ask | ask | ask | deny | ask |

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

### Plugin Host (later)

MCP (InsForge), channels (Slack), judges, flows. Not v0.

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
| Vendor tokens | profile HOME, vendor files | **no** |
| Prompts | memory + optional events | work: default no persist |
| Task metadata | sessions / Postgres | yes |

## Deployment

- v0: single binary on the laptop that has the CLIs
- v2: Gateway + Postgres; workers on machines that have both the repo and the logins
- Never SaaS that stores company Claude/Grok cookies

Next: [Compared with DeepSeek Harness and Cordis](DSH-CORDIS.md)
