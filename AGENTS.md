# Project rules

This file is the project layer. The task protocol lives in the installed task-protocol skill.

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
test -f docs/HLD.md && test -f AGENTS.md && test -f examples/harness.toml && echo 'core files present'
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

You are implementing Ravand Agents, a local (then distributed) ACP control plane for subscription coding agents.

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

v0 is **one process**. Do not stand up Postgres or PGMQ until v2 flags exist.

### Hard constraints

- No provider API keys in Ravand Agents config. If a CLI needs a key, refuse and print the vendor login command.
- Never copy or log credential files from profile HOMEs.
- Work profile MUST NOT run on a repo whose policy says `profile = "personal"` and the reverse.
- If Policy or Permission Broker cannot decide: **fail closed**. Do not spawn.
- Do not invent an ACP dialect. Use `@agentclientprotocol/sdk` (TypeScript) or the official Python/Rust SDK.
- Do not wrap vendor HTTP APIs.
- Do not scrape TUI output. Structured ACP only.

### Implementation order (do not skip)

#### Slice 0: skeleton

- TypeScript (preferred) or Go. Node 22+.
- Package manager: pnpm if TS.
- `packages/cli` bin: `ravand`
- Commands that print “not implemented” except `ravand which` after slice 1.

#### Slice 1: Policy + Profile + Registry (no ACP yet)

- Parse `examples/harness.toml` schema in `docs/SCHEMA.md`
- `ravand which` prints JSON: `{ profile, agent, overflow, permissions, home, command }`
- `ravand login <profile>` prints login hints per agent in that profile
- Isolated dirs: create `~/.ravand/profiles/<name>` if missing
- Unit tests for deny list, profile mismatch, missing harness.toml fallback

#### Slice 2: ACP Runtime for ONE agent

Start with Grok Build if `grok` is on PATH: `grok agent stdio`.
Fallback order: `kimi acp` → `npx -y @agentclientprotocol/claude-agent-acp` → `cursor-agent acp`.

Handshake:

1. spawn with `HOME` + `cwd` = repo root
2. `initialize` (protocolVersion 1)
3. if agent requires `authenticate`, try advertised method `cached_token` / existing session; else print vendor login and exit 2
4. `session/new` with absolute cwd
5. `session/prompt`
6. print streamed assistant text
7. `session/close` on SIGINT / completion

Permission mode v0: `repo-only` (allow read/write under cwd, deny else; shell = ask or deny in `--yes` CI).

#### Slice 3: Session + Audit

- `~/.ravand/sessions/<id>.json` as in SCHEMA.md
- append-only `~/.ravand/audit.jsonl`
- events: `run.started`, `run.ended`, `agent.selected`, `agent.denied`, `permission.allow`, `permission.deny`, `auth.missing`

#### Slice 4: Overflow

If Runtime ends with rate_limit / quota / crash AND policy.overflow is set AND overflow not in deny: start a second run. Audit `agent.overflow`. Same task_id, field `overflowOf`.

#### Slice 5: Observability hooks (no vendor backend required)

- Emit OTel spans if `OTEL_EXPORTER_OTLP_ENDPOINT` is set; else no-op.
- Root span: `invoke_agent` with attributes in SCHEMA.md
- Child: `execute_tool` per tool call
- Metrics counters in-process even without OTLP: duration, result enum

#### Slice 6: PGMQ (feature-flagged)

Only if `RAVAND_PGMQ_URL` is set.

- Dispatcher `send` to `q.tasks`
- Worker loop `read(vt=600)` + `set_vt` heartbeat + `archive`
- Payload exactly as SCHEMA.md (no secrets)
- Worker skips job if local profile cannot run that agent (`capability_miss`, do not burn long VT; nack fast)

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
