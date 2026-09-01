# Project rules

Reading: [docs map](docs/README.md)

Previous: [Governance](docs/GOVERNANCE.md) and the example tomls
Next: Slice 0 in this file, only after you finish the design path in the docs map

This file has two parts. Stack, verify, and branches are for the task protocol. "Adopted product rules" is the implement contract. Skip to that heading if you are reading the design.

The task protocol lives in the installed task-protocol skill.

## Stack

- Language: TypeScript preferred, or Go
- Framework: none yet
- Test runner: unknown

## Verify commands

Run these commands in the Verify step. Report the result of each one. Show the output.

Search README.md, this file, docs, and examples for leftover old product names, the old env prefix, and the old home path. The search must print no lines.

Search the same paths for the old CLI word in lowercase. The search must print no lines.

Confirm the nested design-pack directory is absent.

Confirm these files exist:

```
test -f docs/README.md && test -f docs/HLD.md && test -f AGENTS.md && test -f examples/harness.toml && echo 'core files present'
```

Pass: leftover-name searches empty, nested design-pack directory absent, core files present.

## Integration branches

Do not push directly to a branch in this table.

| Branch | Note |
|--------|------|
| main | Integration branch |

## Ticket and branch

- Ticket key format: none
- Branch name format: `short-description`
- Commit message format: `type: description` (no ticket prefix)

## Task protocol

Follow the `task-protocol` skill for a feature, a bug fix, and a ticket.

Use the plan mode of the current harness. Wait for the user to accept the plan. Do not write product code before that.

Use the `coder` agent for Build and Verify when the harness has that agent.

Use the `reviewer` agent for Review and the pull request draft when the harness has that agent.

## Adopted product rules

You are implementing Ravand Agents, a modular agent control plane. v0 is local ACP over subscription CLIs. Later slices add named LLM accounts, a native loop, sandboxes, workflows, and cloud users.

Read this file before writing code. Follow it over conversational memory.

### Goal

Ship a CLI `ravand` that:

1. Reads `harness.toml` in the current repo (else `~/.ravand/config.toml`)
2. Picks `profile` + `agent`
3. Sets `HOME` (or vendor-specific config dir) to `~/.ravand/profiles/<profile>`
4. Spawns the vendor ACP command
5. Speaks ACP v1 over stdio (initialize → session/new → session/prompt)
6. Answers `session/request_permission` from policy
7. Writes session + audit records
8. Streams text to stdout

v0 is **one process**. Do not stand up a bus or Postgres until v2 flags exist.

### Hard constraints

- Do not put secrets in `harness.toml`, the bus, or work audit (unless `RAVAND_AUDIT_BODIES=1`).
- Never copy or log vendor CLI cookie files from profile HOMEs. API keys live in the profile secret store or cloud vault. Use them. Do not log them.
- If a subscription CLI needs a login, refuse and print the vendor login command.
- Work profile MUST NOT run on a repo whose policy says `profile = "personal"` and the reverse. Customer classification never uses a personal account.
- If Policy, Permission Broker, or account resolution cannot decide: **fail closed**. Do not spawn.
- Do not invent an ACP dialect. Use `@agentclientprotocol/sdk` (TypeScript) or the official Python/Rust SDK.
- Do not wrap vendor CLI HTTP APIs. Native loop (later) talks to the provider only through the named account plugin.
- Do not scrape TUI output. Structured ACP or the native loop plugin only.
- Do not add the Cordis package as the kernel. Do not fork dsh.
- Do not add a second plugin runtime. The kernel is the plugin host.
- Do not read memory across a denied isolation scope.

### Implementation order (do not skip)

Read [docs/README.md](docs/README.md) build path before Slice 0. One slice per change.

#### Slice 0: skeleton

Read first: [README.md](README.md), HLD services list.

- TypeScript (preferred) or Go. Node 22+.
- Package manager: pnpm if TS.
- `packages/cli` bin: `ravand`
- Commands that print “not implemented” except `ravand which` after slice 1.

Next: Slice 1.

#### Slice 1: Policy + Profile + Registry (no ACP yet)

Read first: [docs/SCHEMA.md](docs/SCHEMA.md), [examples/harness.toml](examples/harness.toml), [examples/policy.user.toml](examples/policy.user.toml), HLD Policy / Profile / Registry.

- Parse `examples/harness.toml` schema in `docs/SCHEMA.md`
- `ravand which` prints JSON: `{ profile, agent, overflow, permissions, home, command }`
- `ravand login <profile>` prints login hints per agent in that profile
- Isolated dirs: create `~/.ravand/profiles/<name>` if missing
- Unit tests for deny list, profile mismatch, missing harness.toml fallback

Next: Slice 2.

#### Slice 2: ACP Runtime for ONE agent

Read first: HLD ACP Runtime, HLD Permission Broker, SCHEMA SessionEvent and CLI exit codes.

Start with Grok Build if `grok` is on PATH: `grok agent stdio`.
Fallback order: `kimi acp` → `npx -y @agentclientprotocol/claude-agent-acp` → `cursor-agent acp`.

Handshake:

1. spawn with `HOME` + `cwd` = repo root
2. `initialize` (protocolVersion 1)
3. if agent requires `authenticate`, try advertised method `cached_token` / existing session; else print vendor login and exit 2
4. `session/new` with absolute cwd
5. `session/prompt`
6. emit `SessionEvent` JSONL (`run.started`, `text.delta`, `run.ended`). Do not print secrets.
7. `session/close` on SIGINT / completion

Permission mode v0: `repo-only` (allow read/write under cwd, deny else; shell = ask or deny in `--yes` CI).
`--format jsonl` is the default for scripts. A human TTY may still show text. The machine stream must exist.

Next: Slice 3.

#### Slice 3: Session + Audit

Read first: SCHEMA SessionRecord, SCHEMA Audit event, HLD Session Store, HLD Audit Log.

- `~/.ravand/sessions/<id>.json` as in SCHEMA.md
- append-only `~/.ravand/audit.jsonl`
- events: `run.started`, `run.ended`, `agent.selected`, `agent.denied`, `permission.allow`, `permission.deny`, `auth.missing`

Next: Slice 4.

#### Slice 4: Overflow

Read first: HLD run path step 8, SCHEMA `overflowOf`, audit type `agent.overflow`.

If Runtime ends with rate_limit / quota / crash AND policy.overflow is set AND overflow not in deny: start a second run. Audit `agent.overflow`. Same task_id, field `overflowOf`.

Next: Slice 5.

#### Slice 5: Observability hooks (no vendor backend required)

Read first: SCHEMA OTel.

- Emit OTel spans if `OTEL_EXPORTER_OTLP_ENDPOINT` is set; else no-op.
- Root span: `invoke_agent` with attributes in SCHEMA.md
- Child: `execute_tool` per tool call
- Metrics counters in-process even without OTLP: duration, result enum

Next: Slice 6, only after `ravand run` works on one machine.

#### Slice 6: Bus (feature-flagged)

Read first: HLD Dispatcher, Worker, Bus. SCHEMA TaskMessage, WorkerInfo. MODULAR bus seam.

Only if a bus is configured. Default driver is PGMQ.

- Talk to the Bus seam, not to `pgmq` from Policy or Runtime
- Dispatcher `send` to `q.tasks`
- Worker loop `read` + heartbeat + archive/ack
- Payload exactly as SCHEMA.md (no secrets)
- Worker skips job if local profile cannot run that agent (`capability_miss`, nack fast)
- Do not add Kafka in this slice. Postgres + PGMQ is the first provider.

### Code style

- Small packages matching `docs/HLD.md` service names
- No catch-all `utils.ts` for policy
- Failures: typed errors `PolicyDenied`, `AuthRequired`, `CapabilityMiss`, `FailClosed`
- Exit codes: 0 ok, 2 auth, 3 policy deny, 4 spawn fail, 5 agent error

### Tests to write first

1. Policy: personal repo + work override flag → denied
2. Permission: write `/etc/passwd` → deny
3. Registry: unknown agent id → error
4. Runtime mock: fake ACP server that answers initialize/session/prompt
5. Overflow: mock rate_limit then second agent called

### Do not

- Implement Slack, InsForge, AgentField, or a desktop app in v0
- Add Kubernetes
- Store prompts in audit for `profile = work` unless `RAVAND_AUDIT_BODIES=1`
- Reformat this document’s product rules

### When stuck

Prefer wrapping `@agentclientprotocol/sdk` and copying acpx’s spawn/session shape over writing JSON-RPC by hand.
Reference: https://github.com/openclaw/acpx (MIT), https://agentclientprotocol.com

Reading order lives in [docs/README.md](docs/README.md).
