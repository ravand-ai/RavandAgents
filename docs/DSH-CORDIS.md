# Compared with DeepSeek Harness and Cordis

Reading: [Docs map](README.md)

Previous: [HLD](HLD.md)
Next: [Modular runtime](MODULAR.md)

Status: accepted direction. Kernel is ours. Product seams are in [HLD.md](HLD.md) and [MODULAR.md](MODULAR.md). Destination is in [SUCCESS.md](SUCCESS.md).

## Why we adopt this architecture

Ravand must run many providers, many toolkits, and many plugins on one policy. Loop, tools, MCP, sandbox, bus, memory, trigger, workflow, and identity have to be swappable. A hard-wired coding agent cannot do that.

Cordis is the published architecture for a plugin kernel: plugins mount into a shared context, `inject` waits for services, events intercept work, unload reverses effects. DeepSeek Harness is that kernel applied to a coding agent. We need the kernel shape. We do not need to become dsh.

We write our own kernel. We do not add the Cordis package. We do not fork `deepseek-harness`. dsh stays one ACP backend in the registry.

DeepSeek Harness (`dsh`) is DeepSeek's agent runtime. Cordis is the plugin kernel under it, and the architecture in the paper behind it.

Ravand does **not** use Cordis as a dependency and does **not** run the Cordis package as its kernel. We take the Cordis architecture, then change it to fit Ravand: seats, named accounts, fail closed, modular loops and tools.

Loops, LLM keys, sandboxes, workflows, and MCP are product seams. They are not copied from the Cordis package. See [MODULAR.md](MODULAR.md).

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

## What Ravand is

[HLD.md](HLD.md) and [MODULAR.md](MODULAR.md) say Ravand is a modular control plane: seats, named accounts, optional native loop, workflows, sandboxes, gateway, identity. v0 still runs the ACP + seat path. That is the first ship, not the architecture. dsh remains one ACP backend.

## Kernel: take the architecture, write our own

The kernel is a Ravand package (working name: the Ravand kernel). It is based on the Cordis architecture, then cut to our needs.

**Take from Cordis architecture**

- Plugins mount into a shared context.
- Services are found by key, not by importing a concrete class.
- Dependencies declare wait-for-service, not a hard-coded boot order.
- Events intercept work (`waterfall` is how Permission Broker fail-closes: decide and do not continue).
- Registrations are reversible. Unload undoes them.

**Change for Ravand**

- LLM and agent-loop are optional seams, not the heart of the kernel. A project may use ACP children only.
- Policy and Permission Broker cannot be unmounted. Fail closed is kernel law, not a plugin you patch out.
- Profile in this kernel means the seat HOME. Plugin composition is a **preset**, not a dsh "profile".
- Child I/O is ACP stdio and/or the native loop plugin. Do not wrap vendor CLI HTTP. Do not scrape TUI output.
- The kernel never reads vendor cookie files. It may use named API keys from the secret store. It never logs them.

**Do not**

- Add `@deepseek-ai/cordis` or `cordiverse/cordis` as the runtime.
- Copy Cordis source into `packages/` and rename symbols.
- Copy dsh's tool pipeline as our default. Tools are our seam, per project.

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

1. **Loop is a seam, not the product identity.** dsh is a coding agent. Ravand is a control plane that may run a native loop. dsh stays a registry row for the ACP path.

2. **Keys are named accounts, never git.** `harness.toml` names accounts. Secrets live in the profile store or cloud vault. Vendor CLI cookies stay unread.

3. **Profile means a seat first.** Isolated HOME plus allowed accounts. Plugin composition is a **preset**.

4. **Policy fail closed is not optional.** If Policy, Permission Broker, or account resolution cannot decide, do not run.

5. **No vendor-CLI HTTP wrap.** ACP for CLIs. Native API only through the account plugin. No TUI scrape. MCP is selective per project.

6. **Classification.** Customer repos never use a personal HOME or a personal account.

7. **Own kernel, BSL.** Do not depend on the Cordis package. Do not fork dsh.

8. **v0 is ACP + seats.** Native loop, workflows, cloud users, eval store, and a web UI are later. Queue and workers stay v2.

## Word clash

| Word | dsh | Ravand |
|------|-----|--------|
| profile | plugin composition in Harness home | isolated seat HOME |
| harness | the agent runtime | we keep `harness.toml` as the repo policy file only |
| session | model-visible event log | run metadata + optional audit, not the vendor transcript by default |

When writing Ravand kernel plugins, say **preset** for the plugin tree. Say **profile** only for the seat.

## Proposed shape

```
Human / IDE / CI / webhook / cron
        │
        ▼
   ravand Gateway      Ravand kernel (Cordis-shaped)
        │
  plugins (seams)
    policy · profile HOME · accounts · registry · identity
    loop (ACP and/or native) · tools · MCP · sandbox
    permission · workflow · pipeline · session · audit
    memory · cron · trigger · bus
        │
        ▼
 vendor CLI and/or native provider API (named accounts)
```

v0 plugins: `policy`, `profile`, `registry`, `runtime`, `permissions`, `sessions`, `audit`, `cli`. Later plugins: accounts, loop, sandbox, workflow, pipeline, memory, trigger, identity, eval.

`dsh --profile acp` remains one registry command for the ACP path.

## What we will not copy

- The Cordis npm/git package as our runtime
- Cordis source copied into this repo
- dsh Standard / Code / Minimal / Creator modes as our product names
- Live patch reload of the ACP stdio profile while a run owns stdin
- MIT as the product license
- A web UI in v0

HLD and [MODULAR.md](MODULAR.md) already hold this direction.

Next: [Modular runtime](MODULAR.md)
