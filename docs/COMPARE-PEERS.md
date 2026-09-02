# Compared with OpenClaw, Hermes Agent, and Grok Build

Reading: [Docs map](README.md)

Previous: [Modular runtime](MODULAR.md)
Next: [Schema](SCHEMA.md)

This file is a gap list. It does not add services. HLD and MODULAR stay the product law. SUCCESS wins on ship order.

## Why we compare

Ravand's destination is the next generation of these products on one kernel, not a smaller v0 CLI.

| We take from | As |
|--------------|----|
| **Hermes Agent** | Open harness: loop, tools, memory, cron, sandbox, ACP server, HTTP |
| **Grok Build** | Coding agent we spawn over ACP (plan, skills, MCP, subagents). We do not rebuild its TUI |
| **OpenClaw** | Always-on gateway, channels as trigger plugins, control surface |
| **AgentField** | Identity: who may run, under which seat |

We compare so those rows stay on the product. A P in the matrix is designed work, sequenced by [ROADMAP.md](ROADMAP.md). An N stays out unless HLD names it.

"Grok bot" here means **Grok Build** (`grok`), xAI's coding agent, not the Grok chatbot on X. OpenClaw and Hermes are the other two runtimes people actually run. AgentField is identity, not a fourth coding TUI.

## What each product is

| Product | Job | How you talk to it |
|---------|-----|--------------------|
| **OpenClaw** | Personal or small-team assistant gateway. Models + tools + **messaging channels** + optional coding harnesses | WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Control UI, CLI, ACP |
| **Hermes Agent** (Nous Research) | Full open-source **agent harness**: loop, tools, memory, cron, sandbox, ACP server | TUI, `hermes acp`, HTTP+SSE API, some chat adapters |
| **Grok Build** | Vendor **coding agent**: TUI, plan, subagents, skills, MCP, ACP | `grok`, `grok -p`, `grok agent stdio` |
| **AgentField** | Agent **identity** (who may run, grants) | partner identity, not a coding TUI |
| **Ravand Agents** | **Control plane + harness + gateway**: seats, accounts, policy, loops, tools, plugins, bus, workflows, identity | `ravand` CLI first. HTTP, webhooks, channels later |

Ravand does not replace Grok's TUI and does not start as a WhatsApp bot. The gaps below are the destination. Close them in ROADMAP order.

## Feature matrix

Y = they ship it now. P = we designed it (often later than v0). N = we have not designed it.

| Feature | OpenClaw | Hermes | Grok Build | Ravand |
|---------|----------|--------|------------|--------|
| Own agent loop + tools | Y | Y | Y | P (native loop later; v0 is ACP child) |
| ACP **client** (spawn grok/claude/dsh) | Y (`acpx`) | Y (some providers) | Y | P (v0 core) |
| ACP **server** (IDE talks to us) | Y | Y | Y | P (v1) |
| Isolated seats / HOMEs | weak | some profiles | one login HOME | P (core) |
| Many accounts per vendor + project deny | N | N | N | P |
| Fail-closed project policy | plugin add-on | approvals | plan approve | P (kernel law) |
| Work vs personal / classification | N | N | N | P |
| Overflow on rate_limit | N | N | N | P |
| Messaging channels (Slack, Telegram, …) | **Y** | some | N | N (roadmap: later/partners) |
| Always-on gateway daemon | **Y** | Y | N (session CLI) | N |
| Control UI / dashboard | **Y** | dashboard/PTY | TUI | N |
| Skills + marketplace | **Y** (ClawHub) | Y | Y | P (skills, no marketplace) |
| Hooks on tool/file events | Y | Y | **Y** | P |
| Memory across sessions | Y | **Y** | Y | P (scoped + swappable store) |
| Context compression / lineage | N | **Y** | some | N |
| Cron / scheduled agents | Y | **Y** | N | P |
| Plan mode (approve before write) | some | some | **Y** | P |
| Browser / computer-use | nodes | **Y** | web search | N |
| Parallel subagents + git worktrees | workers | delegate | **Y** | P (subagents; no worktrees) |
| Live steer / cancel of a child harness | **Y** (`/acp steer`) | cancel | cancel | P (Cancel + Steer) |
| Headless JSON for bots/CI | Y | Y | **Y** (`-p`) | P (SessionEvent JSONL/SSE) |
| OpenAI-compatible HTTP API | N | **Y** | API is xAI's, not ours | P (our API later, not OpenAI-shaped) |
| Signed webhooks in | some | some | N | P (v2) |
| Workflows / pipelines as graphs | weak | weak | N | P (v2) |
| Swappable bus (PGMQ/Kafka) | N | N | N | P |
| Cloud users + roles | team gateway | N | N | P (v2) |
| Evals / golden tasks | N | RL envs | N | P (v3) |
| Plugin kernel (hot compose) | plugins | plugins | plugins | P (our kernel) |

## What we are missing (by bucket)

### Designed now (was a gap)

Skills, hooks, classified memory, cron, plan mode, steer, SessionEvent JSONL/SSE, ACP server (v1), gateway, and AgentField identity are in HLD, MODULAR, and SCHEMA. Still not all implemented in code. Close them in ROADMAP order.

### Missing on purpose unless we change the product

Do not add these just because OpenClaw has them. Add them only if Ravand becomes a messenger assistant.

- WhatsApp / Telegram / Discord / Signal / iMessage as first-class channels
- ClawHub-style public skill store
- Companion device nodes / phone apps
- Nous-style self-evolution of the agent
- Grok's fullscreen TUI (we spawn `grok` instead)
- Training / RL environments (Hermes)

Slack is already "later/partners" in the roadmap. That is a channel plugin, not v0.

### Missing vs Grok Build as a coding agent

If someone compares `ravand` to `grok` as a daily driver, they will ask for:

- Plan → diff → approve
- Parallel subagents in **git worktrees**
- `AGENTS.md` pickup from the repo (we write AGENTS.md for ourselves; we do not say we load the target repo's)
- Built-in code search / grep / git
- `/goal` style plan-run-verify

Those belong on the **native loop** seam or we keep telling people to spawn Grok Build. Do not reimplement Grok's TUI.

### Missing vs OpenClaw as a control plane

OpenClaw already spawns Codex/Claude via ACP and owns sessions, channels, and permissions. What they lack (and we claim): named multi-account policy, classification, overflow, fail-closed kernel, bus workers, evals.

What they have that we still lack for "control plane": always-on Gateway process, Control UI, `/acp status|steer|set-mode`, owner-aware sessions (`work` owner vs `claude` harness).

### Missing vs Hermes as a harness

Hermes is the closest "open loop + ACP + API" stack. Gaps if our native loop is real:

- Provider adapters (Anthropic, Codex, Bedrock, …) as a catalog
- Tool registration vs tool **exposure** (not every registered tool is visible this turn)
- Lineage-preserving context compression
- Browser tool
- Cron
- OpenAI-compatible HTTP for existing frontends (Open WebUI)

## Follow-ups (now in HLD / MODULAR / SCHEMA)

Skills, hooks, classified memory, cron, plan mode, steer, and SessionEvent JSONL/SSE are product law. ACP server stays v1. Channels and identity ship in v4. A coding TUI stays out.

Update the matrix: those rows are **P** (designed), not N.

Next: [Schema](SCHEMA.md)
