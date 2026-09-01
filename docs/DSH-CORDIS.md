# Compared with DeepSeek Harness and Cordis

Reading: [Docs map](README.md)

Previous: [HLD](HLD.md)
Next: [Schema](SCHEMA.md)

Status: proposal. This file does not replace [HLD.md](HLD.md) until we accept the differences below.

DeepSeek Harness (`dsh`) is DeepSeek's agent runtime. Cordis is the plugin kernel under it. Ravand Agents should look like that stack, with a short list of differences. We copy the kernel and the composition style. We do not copy the model loop.

Sources:

- https://github.com/deepseek-ai/deepseek-harness
- https://github.com/cordiverse/cordis
- https://deepseek.com/harness/en/
- Paper: *A Programming Paradigm for Spatiotemporal Composability* (arXiv:2608.25512)

## What they are

**Cordis** is a meta-framework. It is not an agent. Plugins mount into a shared context. Each plugin registers services on `ctx.<key>`, typed events, and reversible effects. Unload undoes those effects. Load order comes from `inject` dependencies, not a hand-written boot list.

Five ideas, from the dsh Cordis primer:

1. A plugin implements `Service` (`apply(ctx)` or a `Service` subclass).
2. A context is a repository of services (`ctx.tools`, `ctx.llm`, `ctx.sessions`).
3. `inject` waits until required services exist.
4. Events are `emit`, `waterfall`, `parallel`, `serial`, or `bail`.
5. Registrations are reversible effects. Reload and teardown unwind them.

**DeepSeek Harness** is Cordis applied to a coding agent with no leftover core. Models, tools, skills, sessions, sandboxes, storage, the agent loop, scheduling, and the UI are plugins. A running `dsh` is a plugin tree composed at boot.

A **dsh profile** is a named plugin composition in the Harness home (`web`, `headless`, `sdk`, `acp`). A **bundle** is a stack of Cordis config rows. `dsh --profile acp` is the automation-only ACP stdio server. `dsh-subagent-acp` can spawn any ACP agent as a child, not only dsh.

Invariant in dsh: **model-visible means logged**. The append-only session log is the source of what the model saw. Resume, fork, and replay read that log.

dsh is MIT. It takes provider keys (`DEEPSEEK_API_KEY`). It owns tools and the turn/step loop.

## What Ravand is today

[HLD.md](HLD.md) says Ravand sits **above** vendor CLIs. It selects, isolates, queues, and records them over ACP. It does not call model APIs. It does not hold provider keys. The vendor harness owns the model loop.

Ravand **profile** means an isolated HOME / credential directory (`~/.ravand/profiles/work`). That is not a Cordis plugin tree.

The roadmap already lists "Cordis custom loop as one registry row" under later/partners. The registry already has `dsh` as `dsh --profile acp`. That treats dsh as one backend, not as the architecture of Ravand.

## Same

Copy these from dsh/Cordis into Ravand:

| Idea | In dsh | In Ravand |
|------|--------|-----------|
| Kernel | Cordis context, plugins, reversible effects | Same. Ravand services are Cordis plugins, not a private module graph. |
| Composition | Profile + bundles + ordered patches | Same style. `ravand` boots a plugin tree. |
| ACP stdio | `dsh --profile acp` | Gateway still speaks ACP as client (and later as server named `ravand`). |
| Seams | Service definition, provider, consumer | Policy, profile HOME, registry, runtime, permission, session, audit each have a seam. |
| Interception | `waterfall` on tool/permission events | Permission Broker is a waterfall listener. Fail closed means return without `next()`. |
| Session log | Append-only events | Session + audit stay append-only. Work bodies still off by default. |
| Isolate child HOME | `DSH_HOME` for nested dsh | Spawn vendor CLIs with `HOME=~/.ravand/profiles/<name>`. |
| One launcher | every app starts at `dsh` | every app starts at `ravand`. |

## Different (the few)

These are the product differences. Do not drop them to look more like dsh.

1. **No model loop.** Ravand does not register `ctx.llm` or `ctx.agentLoop`. Vendor CLIs own turns, tools, and prompts. dsh is a row in the registry, same as grok and claude.

2. **No provider keys.** Ravand config never holds API keys or vendor cookies. If a CLI needs a key, print the vendor login command and exit 2.

3. **Profile means a seat first.** Ravand profile = isolated credential HOME plus allowed agents. A Cordis plugin tree may live *inside* that HOME. Do not rename the seat away. If we need the dsh word "profile" for plugin composition, call that a **bundle set** or **preset** in Ravand docs.

4. **Policy fail closed is not optional.** A sandbox plugin you can unmount is not enough. If Policy or Permission Broker cannot decide, do not spawn. A patch must not disable that.

5. **ACP is the only agent I/O.** Do not wrap vendor HTTP. Do not scrape TUI output. MCP attaches at `session/new` only.

6. **Classification.** Customer repos never run on a personal HOME. dsh has no work/personal seat rule.

7. **License.** Ravand is BSL 1.1. dsh and Cordis are MIT. Do not vendor their code into our tree in a way that fights BSL. Depend on Cordis as a package. Do not fork dsh and rebrand it.

8. **v0 is still one process that spawns vendor ACP.** Creator mode, Code mode, and a web UI are not v0. Queue and workers stay v2.

## Word clash

| Word | dsh | Ravand |
|------|-----|--------|
| profile | plugin composition in Harness home | isolated seat HOME |
| harness | the agent runtime | we keep `harness.toml` as the repo policy file only |
| session | model-visible event log | run metadata + optional audit, not the vendor transcript by default |

When writing Ravand code against Cordis, say **preset** or **bundle set** for the plugin tree. Say **profile** only for the seat.

## Proposed shape

```
Human / IDE / CI
        │
        ▼
   ravand CLI          Cordis kernel
        │
  plugins (seams)
    policy · profile HOME · registry
    acp-runtime · permission · session · audit
        │  ACP stdio
        ▼
 vendor CLI (grok | claude | cursor | kimi | dsh --profile acp)
```

v0 plugin list matches today's packages: `policy`, `profile`, `registry`, `runtime`, `permissions`, `sessions`, `audit`, `cli`. There is no `llm` plugin and no `agent-loop` plugin.

`dsh --profile acp` remains one registry command. A user who wants DeepSeek's loop runs that backend under a Ravand profile HOME, same as Grok.

## What we will not copy

- `ctx.llm` and DeepSeek API keys
- Standard / Code / Minimal / Creator modes
- In-process tool registry that executes bash and writes files for the model
- Live patch reload of the ACP stdio profile while a run owns stdin
- MIT as the product license
- A web UI in v0

## Accept or reject

HLD stays as written until this list is accepted.

If accepted, the next doc change is HLD only: add Cordis as the kernel, add the word **preset** for plugin trees, keep profile as the seat, keep the eight differences. SCHEMA and slices do not grow a model loop.

Next: [Schema](SCHEMA.md) if you are still on the design path. Or say the differences are accepted and we patch [HLD.md](HLD.md).
