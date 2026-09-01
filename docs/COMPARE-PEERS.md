# Compared with OpenClaw, Hermes Agent, and Grok Build

Reading: [Docs map](README.md)

Previous: [Modular runtime](MODULAR.md)
Next: [Schema](SCHEMA.md)

This file is a gap list. It does not add services. HLD and MODULAR stay the product law.

"Grok bot" here means **Grok Build** (`grok`), xAI's coding agent, not the Grok chatbot on X. OpenClaw and Hermes are the other two runtimes people actually run.

## What each product is

| Product | Job | How you talk to it |
|---------|-----|--------------------|
| **OpenClaw** | Personal or small-team assistant gateway. Models + tools + **messaging channels** + optional coding harnesses | WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Control UI, CLI, ACP |
| **Hermes Agent** (Nous Research) | Full open-source **agent harness**: loop, tools, memory, cron, sandbox, ACP server | TUI, `hermes acp`, HTTP+SSE API, some chat adapters |
| **Grok Build** | Vendor **coding agent**: TUI, plan, subagents, skills, MCP, ACP | `grok`, `grok -p`, `grok agent stdio` |
| **Ravand Agents** | **Control plane** over those (and a native loop later). Seats, accounts, policy, bus, workflows | `ravand` CLI first. HTTP/webhooks later |

Ravand is not trying to replace Grok's TUI or become another WhatsApp bot. Gaps below are still real if we want a complete operator product.

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
| Skills + marketplace | **Y** (ClawHub) | Y | Y | N |
| Hooks on tool/file events | Y | Y | **Y** | N |
| Memory across sessions | Y | **Y** | Y | N (session files only) |
| Context compression / lineage | N | **Y** | some | N |
| Cron / scheduled agents | Y | **Y** | N | N (webhooks later, not cron) |
| Browser / computer-use | nodes | **Y** | web search | N |
| Plan mode (approve before write) | some | some | **Y** | N |
| Parallel subagents + git worktrees | workers | delegate | **Y** | P (subagents; no worktrees) |
| Live steer / cancel of a child harness | **Y** (`/acp steer`) | cancel | cancel | P (Cancel only) |
| Headless JSON for bots/CI | Y | Y | **Y** (`-p`) | P (`ravand run`) |
| OpenAI-compatible HTTP API | N | **Y** | API is xAI's, not ours | P (our API later, not OpenAI-shaped) |
| Signed webhooks in | some | some | N | P (v2) |
| Workflows / pipelines as graphs | weak | weak | N | P (v2) |
| Swappable bus (PGMQ/Kafka) | N | N | N | P |
| Cloud users + roles | team gateway | N | N | P (v2) |
| Evals / golden tasks | N | RL envs | N | P (v3) |
| Plugin kernel (hot compose) | plugins | plugins | plugins | P (our kernel) |

## What we are missing (by bucket)

### Missing and we should add to the design

These show up in all three, or they are how operators actually live with an agent. Not in MODULAR.md today.

1. **Skills.** Named, versioned playbooks (slash commands, `SKILL.md`). Grok, Hermes, and OpenClaw all have them. Workflows are not a substitute. A skill is a small reusable instruction pack the loop can load.

2. **Hooks.** Scripts that run on tool start/end or file edit, without being MCP. Grok Build ships this. Policy can call a hook; we have no hook seam.

3. **Session memory.** Durable notes the next run may read, under policy. We have session JSON and audit. We do not have agent-writable memory with retention and classification.

4. **Scheduler / cron.** Hermes and OpenClaw run agents on a clock. Webhooks cover "something happened". Cron covers "every weekday at 9". Different trigger.

5. **Plan mode.** Human verifies the plan before writes. Grok's core loop. We have permission ask per tool, not approve-the-plan.

6. **Live steer.** OpenClaw can push extra instruction into a running ACP child. We only cancel.

7. **ACP server in v1 is already planned.** Keep it. Without it, Zed/VS Code cannot attach to `ravand` the way they attach to `grok` or `hermes acp`.

8. **Headless machine-readable stream** (`streaming-json` / SSE). Grok and Hermes use this for bots. `ravand run` must define the event schema, not only stdout text.

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

## Suggested doc follow-ups (not done in this file)

If we accept the "should add" list, next HLD/MODULAR patches are only:

- Skill seam
- Hook seam
- Memory seam (classified)
- Cron trigger next to webhook
- Plan mode as a permission flavor
- Steer on the ACP runtime
- Streaming event schema for `ravand run`

Do not add channels or a TUI in that pass.

Next: [Schema](SCHEMA.md)
