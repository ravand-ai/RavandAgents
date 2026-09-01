# Compared with DeepSeek Harness and Cordis

Reading: [Docs map](README.md)

Previous: [HLD](HLD.md)
Next: [Schema](SCHEMA.md)

Status: proposal. This file does not replace [HLD.md](HLD.md) until we accept the differences below.

DeepSeek Harness (`dsh`) is DeepSeek's agent runtime. Cordis is the plugin kernel under it, and the architecture in the paper behind it.

Ravand does **not** use Cordis as a dependency and does **not** run the Cordis package as its kernel. We write our own kernel. We take the Cordis architecture, then change it to fit Ravand: seats, fail closed, ACP-only, no model loop, no provider keys.

We do not fork `cordiverse/cordis` or `deepseek-harness`. We do not rebrand dsh.

Sources:

- https://github.com/deepseek-ai/deepseek-harness
- https://github.com/cordiverse/cordis
- https://deepseek.com/harness/en/
- Paper: *A Programming Paradigm for Spatiotemporal Composability* (arXiv:2608.25512)

## What they are

**Cordis** is a meta-framework. It is not an agent. Plugins mount into a shared context. Each plugin registers services on `ctx.<key>`, typed events, and reversible effects. Unload undoes those effects. Load order comes from `inject` dependencies, not a hand-written boot list.

Five ideas we study, from the dsh Cordis primer. Our kernel keeps the ideas. It does not keep Cordis type names or package APIs unless they still fit after we change them:

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

## Kernel: take the architecture, write our own

The kernel is a Ravand package (working name: the Ravand kernel). It is based on the Cordis architecture, then cut to our needs.

**Take from Cordis architecture**

- Plugins mount into a shared context.
- Services are found by key, not by importing a concrete class.
- Dependencies declare wait-for-service, not a hard-coded boot order.
- Events intercept work (`waterfall` is how Permission Broker fail-closes: decide and do not continue).
- Registrations are reversible. Unload undoes them.

**Change for Ravand**

- No `llm` service and no agent-loop service in the kernel.
- Policy and Permission Broker cannot be unmounted. Fail closed is kernel law, not a plugin you patch out.
- Profile in this kernel means the seat HOME. Plugin composition is a **preset**, not a dsh "profile".
- The only child I/O the kernel allows toward an agent is ACP stdio.
- The kernel never reads vendor token files.

**Do not**

- Add `@deepseek-ai/cordis` or `cordiverse/cordis` as the runtime.
- Copy Cordis source into `packages/` and rename symbols.
- Implement dsh's `ctx.tools` execution pipeline.

## Same shape, different kernel

| Idea | In dsh | In Ravand |
|------|--------|-----------|
| Kernel | Cordis package | Our kernel, Cordis-shaped, Ravand rules |
| Composition | Profile + bundles + ordered patches | Preset + bundles. `ravand` boots a plugin tree. |
| ACP stdio | `dsh --profile acp` | Gateway still speaks ACP as client (and later as server named `ravand`). |
| Seams | Service definition, provider, consumer | Policy, profile HOME, registry, runtime, permission, session, audit each have a seam. |
| Interception | `waterfall` on tool/permission events | Permission Broker is a waterfall listener. Fail closed means return without continuing. |
| Session log | Append-only events | Session + audit stay append-only. Work bodies still off by default. |
| Isolate child HOME | `DSH_HOME` for nested dsh | Spawn vendor CLIs with `HOME=~/.ravand/profiles/<name>`. |
| One launcher | every app starts at `dsh` | every app starts at `ravand`. |

## Different (the few)

These are the product differences. Do not drop them to look more like dsh.

1. **No model loop.** The Ravand kernel does not grow an LLM adapter or an agent loop. Vendor CLIs own turns, tools, and prompts. dsh is a row in the registry, same as grok and claude.

2. **No provider keys.** Ravand config never holds API keys or vendor cookies. If a CLI needs a key, print the vendor login command and exit 2.

3. **Profile means a seat first.** Ravand profile = isolated credential HOME plus allowed agents. A plugin preset may live *inside* that HOME. Do not rename the seat away. Plugin composition is a **preset**, never a dsh "profile".

4. **Policy fail closed is not optional.** A sandbox plugin you can unmount is not enough. If Policy or Permission Broker cannot decide, do not spawn. A patch must not disable that.

5. **ACP is the only agent I/O.** Do not wrap vendor HTTP. Do not scrape TUI output. MCP attaches at `session/new` only.

6. **Classification.** Customer repos never run on a personal HOME. dsh has no work/personal seat rule.

7. **Own kernel, BSL.** Ravand is BSL 1.1. dsh and Cordis are MIT. Read their docs and the paper. Write the kernel ourselves. Do not depend on the Cordis package. Do not fork dsh.

8. **v0 is still one process that spawns vendor ACP.** Creator mode, Code mode, and a web UI are not v0. Queue and workers stay v2.

## Word clash

| Word | dsh | Ravand |
|------|-----|--------|
| profile | plugin composition in Harness home | isolated seat HOME |
| harness | the agent runtime | we keep `harness.toml` as the repo policy file only |
| session | model-visible event log | run metadata + optional audit, not the vendor transcript by default |

When writing Ravand kernel plugins, say **preset** for the plugin tree. Say **profile** only for the seat.

## Proposed shape

```
Human / IDE / CI
        │
        ▼
   ravand CLI          Ravand kernel (Cordis-shaped)
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

- The Cordis npm/git package as our runtime
- Cordis source copied into this repo
- `ctx.llm` and DeepSeek API keys
- Standard / Code / Minimal / Creator modes
- In-process tool registry that executes bash and writes files for the model
- Live patch reload of the ACP stdio profile while a run owns stdin
- MIT as the product license
- A web UI in v0

## Accept or reject

HLD stays as written until this list is accepted.

If accepted, the next doc change is HLD only: name our kernel, say it follows Cordis architecture after Ravand changes, add the word **preset** for plugin trees, keep profile as the seat, keep the eight differences. SCHEMA and slices do not grow a model loop. Do not add a Cordis dependency.

Next: [Schema](SCHEMA.md) if you are still on the design path. Or say the differences are accepted and we patch [HLD.md](HLD.md).
