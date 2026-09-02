# How Ravand can succeed

Reading: [Docs map](README.md)

Previous: [Product README](../README.md)
Next: [Roadmap](ROADMAP.md)

The HLD and MODULAR files describe a large platform. That is a map, not a launch. Products like OpenClaw, Hermes, and Grok Build won by being something you run this week. Ravand wins only if one painful job is obviously better, then the rest of the map stays behind a seam.

This file is product strategy. It does not add services. If it fights HLD, this file wins on **what we ship first**. HLD still wins on **how a service works**.

## The job that is ours

Mixed seats. Company Cursor, personal Kimi, work Claude, Grok on another laptop. Sharing one login is a ToS and employment problem. API-key routers do not fit people who already pay for CLIs.

One sentence you should be able to demo in two minutes:

> This customer repo cannot run on my personal profile. `ravand run` picks the work Grok seat, records the decision, and refuses the override.

If that demo is slow, flaky, or needs a native loop, the product is not ready. Everything else (workflows, Kafka, graph memory, cloud users) is later.

Grok Build wins at coding in a TUI. Hermes wins at an open harness. OpenClaw wins at chat channels. Do not beat them there first. Beat them at **policy over seats they already have**.

## Freeze the map, ship the wedge

Keep MODULAR as the long-term shape. Do not implement a seam until the wedge is daily-driver for us.

| Ship now (v0) | Design only until v0 is loved |
|---------------|-------------------------------|
| Kernel skeleton | Native loop |
| Policy + profile HOME | Workflows and pipelines |
| `ravand which` / `run` / `login` | Cron, HTTP, webhooks |
| ACP spawn of grok (then one more CLI) | Kafka |
| Fail closed + audit line | Graph memory, org memory |
| JSONL SessionEvent | Cloud users, vault |
| | Plugin marketplace, integrations |

A plugin host in v1 is fine as **load a disk package**. It is not fine as "we are a platform, please write plugins" before anyone uses `ravand run`.

## Five product improvements

**1. One default preset.** Modularity that starts empty feels like a kit, not a product. Ship `preset = "work-acp"` that already has grok, repo-only, file memory, jsonl stream. Power users change seams. New users never see Kafka.

**2. `ravand status` as the login doctor.** "Grok is logged into work HOME. Personal Kimi is logged in. This repo is customer so personal is denied." That screen sells the product. Build it right after `which`.

**3. Overflow you can feel.** Rate-limit on work Claude, fall over to Grok, same `task_id`, audit `agent.overflow`. That is a story no TUI has.

**4. Speak files people already have.** Load the target repo `AGENTS.md`. Honor MCP lists they already wrote. Do not invent a second skill format if `SKILL.md` is enough. Compatibility is distribution.

**5. Config must stay small.** Today a full project can grow `harness.toml` plus accounts plus plugins plus memory plus cron plus bus. v0 `harness.toml` stays the eight keys in `examples/harness.toml`. Extra keys are later and optional. If the example file needs a comment to explain every line, it is too big.

## How we know it is working

Dogfood on this repo and two real work repos. Success is not a complete HLD. Success is:

- We refuse to run `grok` without `ravand` on a classified repo.
- `ravand which` is right 100% of the time in those repos.
- One other human can install, login a profile, and run a task without a call.
- Audit can answer "which account touched this tree yesterday."

Those four hold ([#56](https://github.com/ravand-ai/RavandAgents/issues/56) closed). Leftover CLI is [`ravand init`](https://github.com/ravand-ai/RavandAgents/issues/162). Current feature milestone is v2-s1-bus. Do not grow TUI.

## What would kill it

- Building a coding agent that is a worse Grok Build.
- Shipping twenty plugins and no reliable `ravand run`.
- Putting keys in git or cookies in a SaaS "just for the demo."
- Soft policy (warn and continue). That is not Ravand.
- Renaming profile/preset/harness every month. Pick the words in DSH-CORDIS and stop.

## License and money

BSL with a $250k grant is enough to talk to a company. Do not spend time on contributor-compete licenses until someone is paying. The commercial motion is: you grew past the grant or you want to offer a rival control plane. Until then, dogfood.

## Next

Follow [ROADMAP.md](ROADMAP.md). Four SUCCESS checks hold ([#56](https://github.com/ravand-ai/RavandAgents/issues/56) closed). Leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162). Current feature milestone is v2-s1-bus. Do not grow TUI.

Dogfood plan: [SECURITY.md](SECURITY.md) then [BOOTSTRAP.md](BOOTSTRAP.md).

Next: [Roadmap](ROADMAP.md)
