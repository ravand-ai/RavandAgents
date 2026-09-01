# Schemas

Reading: [Docs map](README.md)

Previous: [Compared with OpenClaw, Hermes, Grok Build](COMPARE-PEERS.md)
Next: [Governance](GOVERNANCE.md)

Canonical samples: [examples/harness.toml](../examples/harness.toml), [examples/policy.user.toml](../examples/policy.user.toml).

## harness.toml (repo)

```toml
# examples/harness.toml is canonical

profile = "work"                 # work | personal | <named>
default = "grok"                 # registry id
overflow = "kimi"                # or "" 
deny = []                        # never use these here
permissions = "repo-only"        # repo-only | approve-reads | deny-writes | ask | plan
classification = "internal"      # public | internal | customer

[agents.claude]
command = ["npx", "-y", "@agentclientprotocol/claude-agent-acp"]

[agents.grok]
command = ["grok", "agent", "stdio"]

[agents.kimi]
command = ["kimi", "acp"]

[agents.cursor]
command = ["cursor-agent", "acp"]

[mcp]
# v1+
# servers = [{ name = "insforge", command = ["npx", "@insforge/mcp"] }]
```

Later fields (not in the v0 example file). Names only. Secrets stay out of git:

```toml
loop = "acp"                    # acp | native
sandbox = "repo-only"           # none | repo-only | container | remote
human = "ask"                   # off | ask | approver | plan
agents_md = true                # load repo AGENTS.md as context

[skills]
allow = ["review-diff"]

[hooks]
# { on = "tool.pre", command = ["./hooks/pre.sh"] }

[memory]
# isolation = "project" | "user" | "profile" | "org" | "account" | "session"
# store = "file" | "sqlite" | "postgres" | "graph"
isolation = "project"
store = "file"

[plugins]
# allow = ["acme.jira"]
# deny = []

[cron]
# jobs = [{ id = "morning", spec = "0 9 * * 1-5", prompt = "status" }]

[accounts]
allow = ["grok-work", "claude-company"]
deny = ["claude-personal"]

[workflow]
# graph of steps; each step may bind tools, functions, subagents

[pipeline]
# ordered stages; same bindings as workflow

[bus]
# v2+. driver = "pgmq" | "kafka"
# url from env or secret_ref, never a password in this file

[triggers.webhook]
# v2+. path + secret_ref. Unsigned requests fail closed
```

## ~/.ravand/config.toml (user)

```toml
default_profile = "personal"
audit_bodies = false

[profiles.work]
home = "~/.ravand/profiles/work"
allow = ["claude", "grok", "cursor"]

[profiles.personal]
home = "~/.ravand/profiles/personal"
allow = ["kimi", "grok", "opencode", "dsh"]

# Named accounts later. Id is local to the profile. kind is cli | api.
# [accounts.grok-work]
# kind = "cli"
# agent = "grok"
# [accounts.claude-api]
# kind = "api"
# provider = "anthropic"
# secret_ref = "vault:work/claude-api"
```

## ResolvedPolicy (internal)

```ts
type ResolvedPolicy = {
  profile: string
  home: string
  defaultAgent: string
  overflowAgent: string | null
  deny: string[]
  permissions: "repo-only" | "approve-reads" | "deny-writes" | "ask" | "plan"
  classification: "public" | "internal" | "customer"
  command: string[]
  mcp: { name: string; command: string[] }[]
  accounts?: string[]
  loop?: "acp" | "native"
  sandbox?: "none" | "repo-only" | "container" | "remote"
  human?: "off" | "ask" | "approver" | "plan"
  skillsAllow?: string[]
  agentsMd?: boolean
  memoryIsolation?: "session" | "user" | "profile" | "project" | "org" | "account" | string
  memoryStore?: "file" | "sqlite" | "postgres" | "graph" | string
  pluginsAllow?: string[]
  pluginsDeny?: string[]
}
```

## SessionRecord

```ts
type SessionRecord = {
  id: string
  taskId: string
  acpSessionId?: string
  repo?: string
  cwd: string
  profile: string
  agent: string
  command: string[]
  overflowOf?: string
  status: "running" | "ok" | "error" | "denied" | "auth" | "cancelled"
  createdAt: string
  endedAt?: string
  host?: string
}
```

Path: `~/.ravand/sessions/<id>.json`

## Audit event

```ts
type AuditEvent = {
  ts: string
  type:
    | "run.started"
    | "run.ended"
    | "agent.selected"
    | "agent.denied"
    | "agent.overflow"
    | "permission.allow"
    | "permission.deny"
    | "auth.missing"
    | "profile.mismatch"
    | "worker.capability_miss"
    | "trigger.denied"
    | "plan.allow"
    | "plan.deny"
    | "steer.accepted"
    | "hook.deny"
  taskId: string
  profile?: string
  agent?: string
  cwd?: string
  policyHash?: string
  detail?: string
}
```

Path: `~/.ravand/audit.jsonl`  
Do not put prompt bodies when profile is `work` unless `RAVAND_AUDIT_BODIES=1`.

## Bus task payload

Same JSON on PGMQ, Kafka, or another bus provider. No tokens, no HOME contents, no cookies.

```ts
type TaskMessage = {
  task_id: string
  traceparent?: string
  repo?: string
  ref?: string
  cwd_hint: string
  profile: string
  agent: string
  overflow?: string
  prompt: string
  permissions: string
  created_by?: string
}
```

No tokens, no HOME contents, no cookies.

## Worker advertisement

```ts
type WorkerInfo = {
  host: string
  profiles: string[]
  agents: string[]
  workspaceRoots: string[]
  seenAt: string
}
```

## OTel

Root span name: `invoke_agent`  
Tool span name: `execute_tool`  
Queue span name: `messaging` (`messaging.system=pgmq` or `kafka` or the driver name)

Attributes:

```
gen_ai.operation.name
gen_ai.agent.name          # registry id
gen_ai.conversation.id     # acp session id
ravand.task_id
ravand.profile
ravand.host
ravand.overflow_of            # optional
ravand.policy_hash
```

Metrics:

```
ravand.queue.depth
ravand.queue.oldest_age_s
ravand.task.duration_s
ravand.task.result            # ok|overflow|rate_limit|auth_missing|crash|denied
ravand.worker.up
ravand.permission.denied
```

## SessionEvent (stream)

CLI: one JSON object per line on stdout (`ravand run --format jsonl`).  
HTTP: `text/event-stream` with the same objects.

```ts
type SessionEvent = {
  ts: string
  taskId: string
  type:
    | "run.started"
    | "text.delta"
    | "thinking.delta"
    | "tool.call"
    | "tool.result"
    | "permission.ask"
    | "plan.ready"
    | "steer.accepted"
    | "hook.deny"
    | "run.ended"
  text?: string
  tool?: string
  status?: SessionRecord["status"]
}
```

No secret fields. No cookie paths. `text.delta` is assistant text only. `thinking.delta` is the agent's thought stream. `tool.call` / `tool.result` carry a short title, never raw cookie or token fields.

## Plugin manifest

```toml
id = "acme.jira"
version = "1.2.0"
kind = "integration"
inject = ["policy", "bus"]
```

`kind` is one of: `function`, `tool`, `service`, `loop`, `sandbox`, `bus`, `memory`, `account`, `skill`, `hook`, `mcp`, `trigger`, `workflow`, `pipeline`, `integration`, `eval`. Several kinds require several grants.

## Memory space

```ts
type MemorySpace = {
  id: string
  isolation: "session" | "user" | "profile" | "project" | "org" | "account" | string
  store: "file" | "sqlite" | "postgres" | "graph" | string
  classification: "public" | "internal" | "customer"
}
```

Every read/write carries `isolation` + owner id. The store plugin must key by that. Cross-scope access is `FailClosed`.

## CLI exit codes

| Code | Meaning |
|---|---|
| 0 | ok |
| 2 | auth required |
| 3 | policy deny |
| 4 | spawn fail |
| 5 | agent error |
| 6 | capability miss (worker) |

## `ravand which` JSON

```json
{
  "profile": "work",
  "agent": "grok",
  "overflow": "kimi",
  "permissions": "repo-only",
  "home": "/home/ada/.ravand/profiles/work",
  "command": ["grok", "agent", "stdio"],
  "auth": "unknown"
}
```

Next: [Governance](GOVERNANCE.md)
