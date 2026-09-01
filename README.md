# Ravand Agents: Subscription Agent Control Plane

Reading: [docs map](docs/README.md)

Previous: [docs map](docs/README.md)
Next: [Roadmap](docs/ROADMAP.md)

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
AGENTS.md                 # project rules + implement slices
README.md                 # product pitch
docs/
  README.md               # start here: reading order
  ROADMAP.md
  HLD.md
  SCHEMA.md
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

Open [docs/README.md](docs/README.md). Follow the design path there. Do not start Slice 0 from this page.
