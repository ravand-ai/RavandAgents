# Docs map

Open this file first. Other files do not explain the reading order.

v0 CLI exists (`ravand which` / `run` / `login` / `status`). Four SUCCESS checks hold ([#56](https://github.com/ravand-ai/RavandAgents/issues/56) closed). Leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162). Current feature milestone is v2-s1-bus.

## Where to start

| You want to | Open first | Then |
|-------------|------------|------|
| Learn the product | [../README.md](../README.md) | This map, then the design path below |
| Walk the design in order | This file | Step 1 of the design path |
| Know v0 leftover vs v1–v4 | [ROADMAP.md](ROADMAP.md) | [HLD.md](HLD.md) |
| Know what to ship first | [SUCCESS.md](SUCCESS.md) | [ROADMAP.md](ROADMAP.md) |
| Implement a slice | [../AGENTS.md](../AGENTS.md) | The slice table in this file |
| Build this repo with Grok/Kimi/Cursor | [SECURITY.md](SECURITY.md) | [BOOTSTRAP.md](BOOTSTRAP.md) |
| See a real policy file | [../examples/harness.toml](../examples/harness.toml) | [SCHEMA.md](SCHEMA.md) |

## Design path (read these now)

Do this sequence. Each file names the previous file and the next file at the top.

1. [Product README](../README.md). What Ravand Agents is, what it is not, the v0 commands.
2. [How Ravand can succeed](SUCCESS.md). Wedge, freeze the map, what we ship first.
3. [Roadmap](ROADMAP.md). v0 leftover, freeze TUI, then v1 local modular, v2 queue, v3 control plane, v4 partners.
4. [HLD](HLD.md). Services, run path, trust, deployment.
5. [Compared with DeepSeek Harness and Cordis](DSH-CORDIS.md). Architecture we study. Our kernel. The few differences.
6. [Modular runtime](MODULAR.md). Accounts, loops, workflows, sandbox, cloud access, evals.
7. [Compared with OpenClaw, Hermes, Grok Build](COMPARE-PEERS.md). Gap list. Does not add services until HLD says so.
8. [Schema](SCHEMA.md). `harness.toml`, user config, session, audit, queue payloads.
9. [Governance](GOVERNANCE.md). Fail closed. Not GRC. Not AIOps. Classification rules.
10. [examples/harness.toml](../examples/harness.toml) and [examples/policy.user.toml](../examples/policy.user.toml). Canonical v0 samples. SCHEMA.md must match them.
11. [AGENTS.md](../AGENTS.md) from "Adopted product rules" down. How an implementer is allowed to build. Skip the stack/verify header unless you are running the task protocol.

After step 11 you know the product. The next design work is a new doc only if HLD, MODULAR, or SCHEMA cannot answer the question. Do not invent a service that HLD does not name.

To write code, read SECURITY.md and BOOTSTRAP.md, then take one GitHub issue.

## Build path (later, one slice)

Do not start this path until you have finished the design path.

| Slice | What you ship | Read before you code | Next slice |
|-------|---------------|----------------------|------------|
| 0 | shipped — `uv` workspace, `ravand` console script exists. SUCCESS [#56](https://github.com/ravand-ai/RavandAgents/issues/56) is closed. Leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162). Do not grow TUI. Do not implement issue 51. | Product README, HLD services list, AGENTS.md Slice 0 | 1 |
| 1 | `ravand which`, `ravand login`, profile dirs, policy tests | SCHEMA.md, both example tomls, HLD Policy / Profile / Registry | 2 |
| 2 | ACP runtime, `ravand run --format jsonl` | HLD ACP Runtime, SCHEMA SessionEvent | 3 |
| 3 | `~/.ravand/sessions/` and `audit.jsonl` | SCHEMA SessionRecord and Audit event, HLD Session and Audit | 4 |
| 4 | Overflow agent on rate_limit | HLD run path step 8, SCHEMA `overflowOf` and `agent.overflow` | 5 |
| 5 | OTel spans if `OTEL_EXPORTER_OTLP_ENDPOINT` is set | SCHEMA OTel | 6 |
| 6 | Bus worker, PGMQ default | HLD Bus, SCHEMA TaskMessage, MODULAR bus seam | stop. `ravand run` must already work |

Prompt text for each slice lives in [AGENTS.md](../AGENTS.md). Copy one slice. Slice 2 works on this repo. SUCCESS [#56](https://github.com/ravand-ai/RavandAgents/issues/56) is closed. Leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162). Current feature milestone is v2-s1-bus. Do not grow TUI. Do not implement issue 51.

To implement with Grok, Kimi, and Cursor, read [SECURITY.md](SECURITY.md) then [BOOTSTRAP.md](BOOTSTRAP.md). One GitHub issue per builder run.

## File index

| File | Answers | Next |
|------|---------|------|
| [docs/README.md](README.md) | Where to start | [../README.md](../README.md) |
| [../LICENSE](../LICENSE) | BSL 1.1 terms and Additional Use Grant | not on the design path |
| [../README.md](../README.md) | What the product is | [SUCCESS.md](SUCCESS.md) |
| [SUCCESS.md](SUCCESS.md) | Wedge and what we ship first | [SECURITY.md](SECURITY.md) |
| [SECURITY.md](SECURITY.md) | Fail closed, agent grants, secret rules | [BOOTSTRAP.md](BOOTSTRAP.md) |
| [BOOTSTRAP.md](BOOTSTRAP.md) | Ravand builds Ravand. Issue order. Grok/Kimi/Cursor | leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162). SUCCESS [#56](https://github.com/ravand-ai/RavandAgents/issues/56) is closed. Current feature milestone is v2-s1-bus. Do not grow TUI. |
| [ROADMAP.md](ROADMAP.md) | What ships in v0, v1, v2, v3 | [HLD.md](HLD.md) |
| [HLD.md](HLD.md) | Which services exist and how a run flows | [DSH-CORDIS.md](DSH-CORDIS.md) |
| [DSH-CORDIS.md](DSH-CORDIS.md) | Cordis architecture we study, kernel we write, differences we keep | [MODULAR.md](MODULAR.md) |
| [MODULAR.md](MODULAR.md) | Accounts, loops, workflows, sandbox, cloud, evals | [COMPARE-PEERS.md](COMPARE-PEERS.md) |
| [COMPARE-PEERS.md](COMPARE-PEERS.md) | Gaps vs OpenClaw, Hermes, Grok Build | [SCHEMA.md](SCHEMA.md) |
| [SCHEMA.md](SCHEMA.md) | Exact files, types, env vars, exit codes | [GOVERNANCE.md](GOVERNANCE.md) |
| [GOVERNANCE.md](GOVERNANCE.md) | What we refuse to become | examples, then AGENTS.md |
| [../examples/harness.toml](../examples/harness.toml) | Repo policy sample | [../examples/policy.user.toml](../examples/policy.user.toml) |
| [../examples/policy.user.toml](../examples/policy.user.toml) | User config sample | [../AGENTS.md](../AGENTS.md) |
| [../AGENTS.md](../AGENTS.md) | Hard constraints and slice order | leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162). SUCCESS [#56](https://github.com/ravand-ai/RavandAgents/issues/56) is closed. Current feature milestone is v2-s1-bus. Do not grow TUI. |

## If a file disagrees

`examples/harness.toml` and `examples/policy.user.toml` win for v0 sample values. SCHEMA.md must copy them. HLD.md wins for service names. MODULAR.md wins for seams (accounts, loops, workflows). SUCCESS.md wins for what we ship first. AGENTS.md wins for slice order and fail-closed rules. This map wins for reading order.
