# Ravand Agents: Modular Agent Control Plane

Reading: [docs map](docs/README.md)

Previous: [docs map](docs/README.md)
Next: [Roadmap](docs/ROADMAP.md)

Ravand Agents is a modular control plane for coding agents. A project picks providers, accounts, loops, tools, MCP, sandbox, workflows, and pipelines.

v0 sits above subscription CLIs you already pay for (Claude Code, Grok Build, Kimi Code, Cursor Agent, DeepSeek Harness) over ACP. Later, a native loop may use named LLM accounts. Secrets never go in git. Policy fail-closes.

```
you / IDE / CI / cloud user
      │
      ▼
    ravand       kernel · policy · profile · accounts
      │          loop · tools · sandbox · workflow
      ▼
vendor CLI and/or native provider API
```

## Problem

People and small teams hold mixed seats: company Cursor, personal Kimi, work Claude, Grok on another laptop. Routers that want API keys do not fit. Sharing one login across repos is a ToS and employment problem.

The unit of value for Ravand Agents: **which account, under which profile, with which tools and sandbox, may touch this repo.**

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
LICENSE                   # Business Source License 1.1
AGENTS.md                 # project rules + implement slices
README.md                 # product pitch
docs/
  README.md               # start here: reading order
  ROADMAP.md
  HLD.md
  DSH-CORDIS.md          # Cordis-shaped kernel, not the Cordis package
  MODULAR.md             # accounts, loops, workflows, sandbox, cloud
  COMPARE-PEERS.md       # gaps vs OpenClaw, Hermes, Grok Build
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

- Wrapping a vendor CLI's HTTP or scraping TUI output
- Putting secrets in git, the bus, or work audit
- Sharing one company CLI cookie across humans
- Using the Cordis package as our kernel, or forking dsh
- Being a general AI-governance GRC suite or a general AIOps platform

## License

[LICENSE](LICENSE) is Business Source License 1.1 (SPDX: `BUSL-1.1`).

Production use is free if prior-year revenue is under USD 250,000 and you are not offering a competing product or hosted Ravand. Otherwise you need a commercial license from the Licensor. Each version becomes Apache License 2.0 four years after it is published, or on the Change Date, whichever comes first.

This is not an OSI open-source license today. Contributor perks and yearly commercial renewal are not in this file. They can be added later as a separate commercial contract.

## Next

Open [docs/README.md](docs/README.md). Follow the design path there. Do not start Slice 0 from this page.
