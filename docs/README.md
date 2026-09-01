# Docs map

Open this file first. Other files do not explain the reading order.

Ravand Agents is still design-only. There is no CLI to run. Read to learn what we will build, then stop. Do not start Slice 0 until the product README, this map, the roadmap, and the HLD agree with what you want.

## Where to start

| You want to | Open first | Then |
|-------------|------------|------|
| Learn the product | [../README.md](../README.md) | This map, then the design path below |
| Walk the design in order | This file | Step 1 of the design path |
| Know v0 vs later | [ROADMAP.md](ROADMAP.md) | [HLD.md](HLD.md) |
| Implement a slice | [../AGENTS.md](../AGENTS.md) | The slice table in this file |
| See a real policy file | [../examples/harness.toml](../examples/harness.toml) | [SCHEMA.md](SCHEMA.md) |

## Design path (read these now)

Do this sequence. Each file names the previous file and the next file at the top.

1. [Product README](../README.md). What Ravand Agents is, what it is not, the v0 commands.
2. [Roadmap](ROADMAP.md). v0 on one machine, then v1 humans, v2 queue, v3 control plane.
3. [HLD](HLD.md). Services, run path, trust, deployment.
4. [Schema](SCHEMA.md). `harness.toml`, user config, session, audit, queue payloads.
5. [Governance](GOVERNANCE.md). Fail closed. Not GRC. Not AIOps. Classification rules.
6. [examples/harness.toml](../examples/harness.toml) and [examples/policy.user.toml](../examples/policy.user.toml). Canonical samples. SCHEMA.md must match them.
7. [AGENTS.md](../AGENTS.md) from "Adopted product rules" down. How an implementer is allowed to build. Skip the stack/verify header unless you are running the task protocol.

After step 7 you know the product. The next design work is a new doc only if HLD or SCHEMA cannot answer the question. Do not invent a service that HLD does not name.

## Build path (later, one slice)

Do not start this path until you have finished the design path.

| Slice | What you ship | Read before you code | Next slice |
|-------|---------------|----------------------|------------|
| 0 | `packages/cli` bin `ravand`, commands say not implemented | Product README, HLD services list, AGENTS.md Slice 0 | 1 |
| 1 | `ravand which`, `ravand login`, profile dirs, policy tests | SCHEMA.md, both example tomls, HLD Policy / Profile / Registry | 2 |
| 2 | ACP runtime for one agent, `ravand run` | HLD ACP Runtime and Permission Broker, SCHEMA exit codes | 3 |
| 3 | `~/.ravand/sessions/` and `audit.jsonl` | SCHEMA SessionRecord and Audit event, HLD Session and Audit | 4 |
| 4 | Overflow agent on rate_limit | HLD run path step 8, SCHEMA `overflowOf` and `agent.overflow` | 5 |
| 5 | OTel spans if `OTEL_EXPORTER_OTLP_ENDPOINT` is set | SCHEMA OTel | 6 |
| 6 | PGMQ worker, only if `RAVAND_PGMQ_URL` is set | HLD Dispatcher, Worker, PGMQ. SCHEMA TaskMessage, WorkerInfo | stop. `ravand run` must already work |

Prompt text for each slice lives in [AGENTS.md](../AGENTS.md). Copy one slice. Do not ask an agent for Slice 6 before Slice 2 works on one machine.

## File index

| File | Answers | Next |
|------|---------|------|
| [docs/README.md](README.md) | Where to start | [../README.md](../README.md) |
| [../README.md](../README.md) | What the product is | [ROADMAP.md](ROADMAP.md) |
| [ROADMAP.md](ROADMAP.md) | What ships in v0, v1, v2, v3 | [HLD.md](HLD.md) |
| [HLD.md](HLD.md) | Which services exist and how a run flows | [SCHEMA.md](SCHEMA.md) |
| [SCHEMA.md](SCHEMA.md) | Exact files, types, env vars, exit codes | [GOVERNANCE.md](GOVERNANCE.md) |
| [GOVERNANCE.md](GOVERNANCE.md) | What we refuse to become | examples, then AGENTS.md |
| [../examples/harness.toml](../examples/harness.toml) | Repo policy sample | [../examples/policy.user.toml](../examples/policy.user.toml) |
| [../examples/policy.user.toml](../examples/policy.user.toml) | User config sample | [../AGENTS.md](../AGENTS.md) |
| [../AGENTS.md](../AGENTS.md) | Hard constraints and slice order | Slice 0 when you build |

## If a file disagrees

`examples/harness.toml` and `examples/policy.user.toml` win for sample values. SCHEMA.md must copy them. HLD.md wins for service names. AGENTS.md wins for slice order and fail-closed rules. This map wins for reading order.
