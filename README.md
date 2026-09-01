# Ravand Agents: Subscription Agent Control Plane

Ravand Agents sits above coding-agent CLIs you already pay for (Claude Code, Grok Build, Kimi Code, Cursor Agent, later OpenCode / DeepSeek Harness).

It does **not** call model APIs and does **not** hold provider keys.
It **selects**, **isolates**, **queues**, and **records** those CLIs over ACP (Agent Client Protocol).

```
you / IDE / CI
      │
      ▼
    ravand       policy · profile · queue · audit
      │  ACP stdio
      ▼
vendor CLI already logged in
```

## Problem

People and small teams hold mixed seats: company Cursor, personal Kimi, work Claude, Grok on another laptop. Routers that want API keys do not fit. Sharing one login across repos is a ToS and employment problem.

The unit of value for Ravand Agents: **which licensed agent may touch this repo, under which profile, on which machine.**

## What v0 is

A local CLI + policy file.

```bash
ravand which                 # resolve agent + profile for cwd
ravand run "add rate limits" # spawn that ACP agent
ravand run -a grok "review"  # override
ravand login work            # print how to auth CLIs into the work HOME
ravand status                # workers, queue (v2), login probes
```

## Repo layout

```
AGENTS.md                 # instructions for Grok Build / other agents
README.md
docs/
  HLD.md
  SCHEMA.md
  ROADMAP.md
  GOVERNANCE.md
examples/
  harness.toml
  policy.user.toml
packages/                 # implement here; empty until generated
  acp-client/
  policy/
  profile/
  registry/
  runtime/
  permissions/
  sessions/
  audit/
  dispatcher/
  worker/
  observability/
  cli/
```

## Non-goals

- New coding agent loop
- HTTP proxy to Anthropic / xAI / Moonshot
- Putting OAuth tokens in Postgres or PGMQ
- Sharing one company seat across humans
- Being a general AI-governance GRC suite or a general AIOps platform

## License intent

- ACP adapters and schemas: keep open if possible
- Policy engine, profile isolation, audit evidence: product core

## Next

Read `AGENTS.md`, then `docs/HLD.md` and `docs/SCHEMA.md`. Implement in the order in `AGENTS.md`.

Log the CLIs you actually have into isolated HOMEs later. For first slice, system login is fine.

```bash
grok login    # if you use Grok Build as first ACP backend
# kimi login
# claude
```

Start Grok Build in this directory so it reads `AGENTS.md`:

```bash
grok
```

Then prompt:

```
Read AGENTS.md, docs/HLD.md, and docs/SCHEMA.md.
Implement Slice 0 and Slice 1 only: repo skeleton + ravand which + harness.toml parser + profile dirs.
Do not spawn ACP yet. Add tests for profile mismatch and deny list.
```

Next prompts (one slice each):

```
Implement Slice 2: ACP runtime for grok agent stdio using @agentclientprotocol/sdk.
```

```
Implement Slice 3: session store and audit.jsonl as specified in docs/SCHEMA.md.
```

```
Implement Slice 4: overflow agent on rate_limit.
```

Do not ask it to implement PGMQ until `ravand run` works on one machine.

Point Grok at a real project later by copying `examples/harness.toml` into that project as `harness.toml`.
