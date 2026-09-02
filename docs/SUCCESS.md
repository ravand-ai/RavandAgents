# How Ravand can succeed

Reading: [Docs map](README.md)

Previous: [Product README](../README.md)
Next: [Roadmap](ROADMAP.md)

This file is product strategy. It does not add services.

If this file fights [HLD.md](HLD.md) or [MODULAR.md](MODULAR.md), this file wins on **what we ship first**. HLD wins on **how a service works**. MODULAR wins on **what the product is**.

Do not read the first-ship wedge as the end of the product. The destination is the full control plane. The wedge is the first vertical slice that must work this week.

## The product (destination)

Ravand is the next-generation agent control plane. One kernel runs agents from different providers, with different toolkits and plugins, on different tasks.

It combines:

- A **Hermes-class harness**: own loop, tools, memory, cron, sandbox, ACP server, HTTP.
- **Grok Build** (and other subscription CLIs) as coding backends we spawn over ACP. We do not rebuild Grok's TUI.
- An **OpenClaw-class gateway**: always-on process, HTTP, signed webhooks, chat channels as trigger plugins.
- **AgentField-class identity**: who may run, under which seat, with which grants.
- **Full orchestration**: workflows, pipelines, subagents, plugins, mixed personal and work seats.

Some agents are personal. Some are work. Some start from `ravand run`. Some start from a webhook, cron, or the HTTP API. Policy still fail-closes. Secrets stay out of git and out of the bus.

The unit of value stays: **which account, under which profile, with which tools and sandbox, may touch this repo.** The rest of the map (loop, gateway, memory, cron, workflow, identity) plugs into that.

HLD and MODULAR are that product. ROADMAP is the order we build it.

## Why we study DeepSeek Harness and Cordis

We need a kernel where loop, tools, MCP, sandbox, bus, memory, trigger, workflow, and identity are plugins. Cordis is the published architecture for that: plugins mount into a shared context, `inject` waits for services, events intercept work, unload reverses effects.

We take those ideas. We write our own kernel. We do not add the Cordis package. We do not fork `deepseek-harness`. DeepSeek Harness stays one ACP backend in the registry.

Read [DSH-CORDIS.md](DSH-CORDIS.md).

## Why we compare OpenClaw, Hermes, and Grok Build

Those products are the feature list of the destination. We compare so we do not forget gateway, harness, coding backends, identity, and orchestration.

[COMPARE-PEERS.md](COMPARE-PEERS.md) is the gap list we intend to close, in ROADMAP order. It is not a blog. A row marked P is designed product law. A row marked N is out unless HLD names it.

Do not beat Grok on fullscreen coding UX. Spawn Grok (and Cursor, Kimi, Claude, dsh) under policy instead. Do not beat OpenClaw by copying WhatsApp first. Ship the gateway and channels as trigger plugins after the kernel runs.

## The first job we ship (wedge)

Mixed seats. Company Cursor, personal Kimi, work Claude, Grok on another laptop. Sharing one login is a ToS and employment problem. API-key routers do not fit people who already pay for CLIs.

One sentence you should be able to demo in two minutes:

> This customer repo cannot run on my personal profile. `ravand run` picks the work Grok seat, records the decision, and refuses the override.

If that demo is slow, flaky, or needs a native loop, **v0 is not ready**. Do not skip the rest of the map. Sequence it. Native loop, gateway, cron, webhooks, workflows, memory, identity, and cloud users stay on the product. They ship after the demo works as a daily driver.

## Ship the wedge first, keep the map

Keep MODULAR as the product shape. Do not implement a later seam to look busy while the wedge is unusable. Do not delete a later seam from the product because v0 is not loved yet.

| First ship (v0) | Product, sequenced after v0 is usable |
|-----------------|----------------------------------------|
| Kernel skeleton | Native loop, plugin host |
| Policy + profile HOME | Workflows, pipelines, subagents |
| `ravand which` / `run` / `login` | Cron, HTTP, webhooks, gateway |
| ACP spawn of grok, then more CLIs | Named API accounts, AgentField identity |
| Fail closed + audit line | Graph memory, org memory |
| JSONL SessionEvent | Cloud users, vault, evals |

A plugin host in v1 is **load a disk package**. It is not a marketplace. Marketplace stays out.

## Five product improvements (first ship)

**1. One default preset.** Modularity that starts empty feels like a kit, not a product. Ship `preset = "work-acp"` that already has grok, repo-only, file memory, jsonl stream. Power users change seams. New users never see Kafka.

**2. `ravand status` as the login doctor.** "Grok is logged into work HOME. Personal Kimi is logged in. This repo is customer so personal is denied." That screen sells the product. The probe must be a real login marker, not `npx --version`.

**3. Overflow you can feel.** Rate-limit on work Claude, fall over to Grok, same `task_id`, audit `agent.overflow`. That is a story no TUI has.

**4. Speak files people already have.** Load the target repo `AGENTS.md`. Honor MCP lists they already wrote. Do not invent a second skill format if `SKILL.md` is enough. Compatibility is distribution.

**5. Config must stay small.** v0 `harness.toml` stays the eight keys in `examples/harness.toml`. Extra keys are later and optional. If the example file needs a comment to explain every line, it is too big.

## How we know the first ship is working

Dogfood on this repo and two real work repos. The first-ship gate is not a complete HLD. It is:

- We refuse to run `grok` without `ravand` on a classified repo.
- `ravand which` is right 100% of the time in those repos.
- One other human can install, login a profile, and run a task without a call.
- Audit can answer "which account touched this tree yesterday."

[#56](https://github.com/ravand-ai/RavandAgents/issues/56) closed those checks on paper. Daily-driver on this repo is still the gate. Leftover CLI is [`ravand init`](https://github.com/ravand-ai/RavandAgents/issues/162). Do not grow TUI ([#51](https://github.com/ravand-ai/RavandAgents/issues/51)).

After that gate, follow [ROADMAP.md](ROADMAP.md) through v1 (named accounts, harness seams), v2 (gateway triggers, bus, orchestration), v3 (evidence, evals), v4 (channels and identity). Do not stop at v0.

## What would kill it

- Treating this file as the destination and dropping gateway, harness, identity, or orchestration.
- Building a coding agent that is a worse Grok Build.
- Shipping twenty plugins and no reliable `ravand run`.
- Putting keys in git or cookies in a SaaS "just for the demo."
- Soft policy (warn and continue). That is not Ravand.
- Renaming profile/preset/harness every month. Pick the words in DSH-CORDIS and stop.

## License and money

BSL with a $250k grant is enough to talk to a company. Do not spend time on contributor-compete licenses until someone is paying. The commercial motion is: you grew past the grant or you want to offer a rival control plane. Until then, dogfood the wedge and keep building the map.

## Next

Follow [ROADMAP.md](ROADMAP.md). First-ship gate: [SECURITY.md](SECURITY.md) then [BOOTSTRAP.md](BOOTSTRAP.md). Destination: [HLD.md](HLD.md) and [MODULAR.md](MODULAR.md).

Next: [Roadmap](ROADMAP.md)
