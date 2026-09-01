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
2. [How Ravand can succeed](SUCCESS.md). Wedge, freeze the map, what we ship first.
3. [Roadmap](ROADMAP.md). v0 on one machine, then v1 humans, v2 queue, v3 control plane.
4. [HLD](HLD.md). Services, run path, trust, deployment.
5. [Compared with DeepSeek Harness and Cordis](DSH-CORDIS.md). Architecture we study. Our kernel. The few differences.
6. [Modular runtime](MODULAR.md). Accounts, loops, workflows, sandbox, cloud access, evals.
7. [Compared with OpenClaw, Hermes, Grok Build](COMPARE-PEERS.md). Gap list. Does not add services until HLD says so.
8. [Schema](SCHEMA.md). `harness.toml`, user config, session, audit, queue payloads.
9. [Governance](GOVERNANCE.md). Fail closed. Not GRC. Not AIOps. Classification rules.
10. [examples/harness.toml](../examples/harness.toml) and [examples/policy.user.toml](../examples/policy.user.toml). Canonical v0 samples. SCHEMA.md must match them.
11. [AGENTS.md](../AGENTS.md) from "Adopted product rules" down. How an implementer is allowed to build. Skip the stack/verify header unless you are running the task protocol.

After step 11 you know the product. The next design work is a new doc only if HLD, MODULAR, or SCHEMA cannot answer the question. Do not invent a service that HLD does not name.

## Build path (later, one slice)

Do not start this path until you have finished the design path.

| Slice | What you ship | Read before you code | Next slice |
|-------|---------------|----------------------|------------|
| 0 | `packages/cli` bin `ravand`, commands say not implemented | Product README, HLD services list, AGENTS.md Slice 0 | 1 |
| 1 | `ravand which`, `ravand login`, profile dirs, policy tests | SCHEMA.md, both example tomls, HLD Policy / Profile / Registry | 2 |
| 2 | ACP runtime, `ravand run --format jsonl` | HLD ACP Runtime, SCHEMA SessionEvent | 3 |
| 3 | `~/.ravand/sessions/` and `audit.jsonl` | SCHEMA SessionRecord and Audit event, HLD Session and Audit | 4 |
| 4 | Overflow agent on rate_limit | HLD run path step 8, SCHEMA `overflowOf` and `agent.overflow` | 5 |
| 5 | OTel spans if `OTEL_EXPORTER_OTLP_ENDPOINT` is set | SCHEMA OTel | 6 |
| 6 | Bus worker, PGMQ default | HLD Bus, SCHEMA TaskMessage, MODULAR bus seam | stop. `ravand run` must already work |

Prompt text for each slice lives in [AGENTS.md](../AGENTS.md). Copy one slice. Do not ask an agent for Slice 6 before Slice 2 works on one machine.

## File index

| File | Answers | Next |
|------|---------|------|
| [docs/README.md](README.md) | Where to start | [../README.md](../README.md) |
| [../LICENSE](../LICENSE) | BSL 1.1 terms and Additional Use Grant | not on the design path |
| [../README.md](../README.md) | What the product is | [SUCCESS.md](SUCCESS.md) |
| [SUCCESS.md](SUCCESS.md) | Wedge and what we ship first | [ROADMAP.md](ROADMAP.md) |
| [ROADMAP.md](ROADMAP.md) | What ships in v0, v1, v2, v3 | [HLD.md](HLD.md) |
| [HLD.md](HLD.md) | Which services exist and how a run flows | [DSH-CORDIS.md](DSH-CORDIS.md) |
| [DSH-CORDIS.md](DSH-CORDIS.md) | Cordis architecture we study, kernel we write, differences we keep | [MODULAR.md](MODULAR.md) |
| [MODULAR.md](MODULAR.md) | Accounts, loops, workflows, sandbox, cloud, evals | [COMPARE-PEERS.md](COMPARE-PEERS.md) |
| [COMPARE-PEERS.md](COMPARE-PEERS.md) | Gaps vs OpenClaw, Hermes, Grok Build | [SCHEMA.md](SCHEMA.md) |
| [SCHEMA.md](SCHEMA.md) | Exact files, types, env vars, exit codes | [GOVERNANCE.md](GOVERNANCE.md) |
| [GOVERNANCE.md](GOVERNANCE.md) | What we refuse to become | examples, then AGENTS.md |
| [../examples/harness.toml](../examples/harness.toml) | Repo policy sample | [../examples/policy.user.toml](../examples/policy.user.toml) |
| [../examples/policy.user.toml](../examples/policy.user.toml) | User config sample | [../AGENTS.md](../AGENTS.md) |
| [../AGENTS.md](../AGENTS.md) | Hard constraints and slice order | Slice 0 when you build |

## If a file disagrees

`examples/harness.toml` and `examples/policy.user.toml` win for v0 sample values. SCHEMA.md must copy them. HLD.md wins for service names. MODULAR.md wins for seams (accounts, loops, workflows). AGENTS.md wins for slice order and fail-closed rules. This map wins for reading order.
