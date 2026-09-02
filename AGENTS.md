# Project rules

Reading: [docs map](docs/README.md)

Previous: [Governance](docs/GOVERNANCE.md) and the example tomls
Next: leftover CLI is [`ravand init`](https://github.com/ravand-ai/RavandAgents/issues/162). SUCCESS [#56](https://github.com/ravand-ai/RavandAgents/issues/56) is closed. Four SUCCESS checks hold. Do not grow TUI ([#51](https://github.com/ravand-ai/RavandAgents/issues/51)). Current feature milestone is [v2-s1-bus](https://github.com/ravand-ai/RavanAgents/milestone/6). Sprints are **milestones**, not labels.

This file has two parts. Stack, verify, and branches are for the task protocol. "Adopted product rules" is the implement contract. Skip to that heading if you are reading the design.

The task protocol lives in the installed task-protocol skill.

## Stack

- Language: Python 3.12+
- Package manager: uv
- Framework: none yet
- Test runner: pytest

## Verify commands

Run these commands in the Verify step. Report the result of each one. Show the output.

Search README.md, this file, docs, and examples for leftover old product names, the old env prefix, and the old home path. The search must print no lines.

Search the same paths for the old CLI word in lowercase. The search must print no lines.

Confirm the nested design-pack directory is absent.

Confirm these files exist:

```
test -f docs/README.md && test -f docs/HLD.md && test -f AGENTS.md && test -f examples/harness.toml && echo 'core files present'
```

When `pyproject.toml` exists, also run:

```
uv run pytest
```

Pass: leftover-name searches empty, nested design-pack directory absent, core files present, pytest green when the suite exists.

CodeQL: GitHub code scanning on every push and pull request to `main` (`.github/workflows/codeql.yml`). A new CodeQL finding is a new GitHub issue. Do not expand the current branch to “fix everything.”

## Integration branches

Do not push directly to a branch in this table.

| Branch | Note |
|--------|------|
| main | Integration branch |

## Ticket and branch

- Ticket key format: GitHub issue number (`#12`)
- Branch name format: `N-short-description` (example: `2-slice-0-skeleton`)
- Commit message format: `type: description (#N)`
- One GitHub issue → one branch → one PR. If you find extra work, open a new issue. Do not pile it onto the current branch.

## Task protocol

Follow the `task-protocol` skill for a feature, a bug fix, and a ticket.

Use the plan mode of the current harness. Wait for the user to accept the plan. Do not write product code before that.

Use the `coder` agent for Build and Verify when the harness has that agent.

Use the `reviewer` agent for Review and the pull request draft when the harness has that agent.

## Plan ahead, blockers, review, delivery

Read this section before you open a ticket or start a builder. Chat memory is not the plan. A compacted session must re-read this file, not invent process.

### Plan ahead

The sprint is a GitHub **milestone** (`v1-s1-named-seats`, `v1-s2-policy-seams`, …). Do not add `sprint-N` labels.

Version is a label (`v0` or `v1`). A v1 title must not wear `v0`.

Board: [Ravand v0](https://github.com/orgs/ravand-ai/projects/1) and [Ravand v1](https://github.com/orgs/ravand-ai/projects/2).

Before a sprint starts, write three things on the milestone (or a pinned issue):

1. The sprint deliverable in one sentence.
2. The issue list that serves that sentence.
3. GitHub **blocked by** links for every dependent card.

Do not start coding until those blockers are set.

While builders code the current sprint, fill later-sprint backlog on the board. Set `blocked by` on those cards too. Do not dispatch a later-sprint card until the current milestone retro is done.

### Sorted by blockers

Ready means all of these hold:

- The issue is open.
- The issue is on the **current** milestone.
- Every GitHub `blocked by` parent is closed (or there is no parent).

Check parents with:

```
gh api repos/ravand-ai/RavandAgents/issues/N/dependencies/blocked_by
```

Sort the board by that graph, not by issue number and not by who shouted last.

Do not start a blocked card. Do not merge a PR whose issue still has an open `blocked by` parent.

If you find extra work, open a new issue and set `blocked by` / `blocking`. Do not grow the current branch.

### How to review

Follow [docs/REVIEW.md](docs/REVIEW.md). The builder never merges.

Grok runs the six-point checklist on the PR ref and pastes the command output. Safe means squash-merge and delete the branch. Unsafe means comment and stay on the same branch. Retarget stacked children before you delete a base.

### Why we check

A green pytest is not a merge. Review exists because these faults still pass tests:

- Policy or account resolution fails **open** (the product rule is fail closed).
- A secret, cookie path, `sk-`, `xai-`, or `Bearer` lands in the diff.
- The build backend becomes hatchling.
- A new PyPI dep arrives without an issue that named it.
- The PR is still blocked by an open parent.
- TUI (#51) gets closed by accident. SUCCESS (#56) is already closed.

The six-point checklist is the merge gate so a human does not re-read every diff. If a point is not green, the PR is not safe. Do not merge on vibe.

### Escape the improvement loop

You are in the loop when the only change is restating work that already shipped (README build path, AGENTS slice order, "leftover is SUCCESS" said a fifth time).

Stop. Close that ticket. Do not open another one like it.

A docs-only ticket is allowed only when a builder would take a **wrong action** without it (wrong command, wrong slice, wrong merge rule).

If you are idle, take the next Ready **feature** on the **current** milestone. Do not invent a docs-accuracy card to look busy.

Cap: at most one docs-accuracy issue per sprint, and only if a builder is actually lost.

### Delivery first

Ship as many current-sprint features as the blocker DAG allows. Prefer a failing pytest plus product code over prose.

Dispatch every Ready current-sprint card that has **disjoint files**. Grok, Kimi, and Cursor may run at the same time. One builder per issue. Do not serialize Ready disjoint work.

Do not pull a later-sprint card forward to look busy while the current milestone still has Ready features. Do not idle on docs while a Ready feature exists.

v1 sprint 1 deliverable: named CLI account under policy (`ravand which` / `run --account`, fail closed), plus hooks and file memory as unblocked seats.

v1 exit (later sprints): one project can say this job is work-grok ACP, that job is company-claude API, both under the same deny list.

### Sprint retro and next plan

A sprint finishes when the current milestone has **zero** open issues. Then do this, in order. Do not skip.

1. Retro. Comment on the milestone: what shipped, what stayed blocked, which improvement loop we fell into (if any). Name the PRs.
2. Plan the next milestone. Keep only cards that serve the v1 exit. Drop the rest. Set `blocked by` before anyone codes.
3. Dispatch Ready disjoint **feature** cards for that next sprint. Fill further-sprint backlog after that, not instead of it.

Do not start the next sprint's builders before the retro comment exists. Do not treat a finished sprint as a reason to rewrite docs. The next action is the next feature.
## Adopted product rules

You are implementing Ravand Agents, a modular agent control plane. v0 is local ACP over subscription CLIs. Later slices add named LLM accounts, a native loop, sandboxes, workflows, and cloud users.

Read this file before writing code. Follow it over conversational memory.

### Goal

Ship a CLI `ravand` that:

1. Reads `harness.toml` in the current repo (else `~/.ravand/config.toml`)
2. Picks `profile` + `agent`
3. Sets `HOME` (or vendor-specific config dir) to `~/.ravand/profiles/<profile>`
4. Spawns the vendor ACP command
5. Speaks ACP v1 over stdio (initialize → session/new → session/prompt)
6. Answers `session/request_permission` from policy
7. Writes session + audit records
8. Streams text to stdout

v0 is **one process**. Do not stand up a bus or Postgres until v2 flags exist.

### Hard constraints

- Do not put secrets in `harness.toml`, the bus, or work audit (unless `RAVAND_AUDIT_BODIES=1`).
- Never copy or log vendor CLI cookie files from profile HOMEs. API keys live in the profile secret store or cloud vault. Use them. Do not log them.
- If a subscription CLI needs a login, refuse and print the vendor login command.
- Work profile MUST NOT run on a repo whose policy says `profile = "personal"` and the reverse. Customer classification never uses a personal account.
- If Policy, Permission Broker, or account resolution cannot decide: **fail closed**. Do not spawn.
- Do not invent an ACP dialect. Use the official Python ACP SDK.
- Do not wrap vendor CLI HTTP APIs. Native loop (later) talks to the provider only through the named account plugin.
- Do not scrape TUI output. Structured ACP or the native loop plugin only.
- Do not add the Cordis package as the kernel. Do not fork dsh.
- Do not add a second plugin runtime. The kernel is the plugin host.
- Do not read memory across a denied isolation scope.
- Do not add a dependency for convenience. Stdlib first. Slice 0 may add pytest (dev). The ACP SDK is allowed only in Slice 2.
- A performance dependency is allowed only when: (1) a checked-in benchmark shows a real win on a Ravand path, (2) a reviewer other than the builder accepts the benchmark and the new risk (supply chain, size, license), (3) a GitHub issue named the dependency. Open that issue if it did not exist. Do not sneak the package onto an unrelated branch.

### Implementation order (do not skip)

Leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162). SUCCESS [#56](https://github.com/ravand-ai/RavandAgents/issues/56) is closed. Current feature milestone is v2-s1-bus. One GitHub issue per branch. TDD: write the failing pytest first, then the code. Do not grow TUI. Do not implement issue 51.

#### Slice 0: skeleton

Read first: [README.md](README.md), HLD services list.

- Python 3.12+, uv, `pyproject.toml` at the repo root.
- uv workspace. Packages match HLD service names under `packages/`.
- Build backend: `uv_build` only. Do not add hatchling.
- `packages/cli` console script: `ravand`
- pytest. First test: `ravand --help` or missing command exits non-zero with `not implemented`.
- Commands that print “not implemented” except `ravand which` after slice 1.
- No Node, pnpm, or TypeScript app code.
- Dependencies: pytest (dev) only. Nothing else.

Next: Slice 1.

#### Slice 1: Policy + Profile + Registry (no ACP yet)

Read first: [docs/SCHEMA.md](docs/SCHEMA.md), [examples/harness.toml](examples/harness.toml), [examples/policy.user.toml](examples/policy.user.toml), HLD Policy / Profile / Registry.

- Parse `examples/harness.toml` schema in `docs/SCHEMA.md`
- `ravand which` prints JSON: `{ profile, agent, overflow, permissions, home, command }`
- `ravand login <profile>` prints login hints per agent in that profile
- Isolated dirs: create `~/.ravand/profiles/<name>` if missing
- pytest first: deny list, profile mismatch, missing harness.toml fallback, unknown agent id

Next: Slice 2.

#### Slice 2: ACP Runtime for ONE agent

Read first: HLD ACP Runtime, HLD Permission Broker, SCHEMA SessionEvent and CLI exit codes.

Start with Grok Build if `grok` is on PATH: `grok agent stdio`.
Fallback order: `kimi acp` → `npx -y @agentclientprotocol/claude-agent-acp` → `cursor-agent acp`.

Handshake:

1. spawn with `HOME` + `cwd` = repo root
2. `initialize` (protocolVersion 1)
3. if agent requires `authenticate`, try advertised method `cached_token` / existing session; else print vendor login and exit 2
4. `session/new` with absolute cwd
5. `session/prompt`
6. emit `SessionEvent` JSONL (`run.started`, `text.delta`, `run.ended`). Do not print secrets.
7. `session/close` on SIGINT / completion

Permission mode v0: `repo-only` (allow read/write under cwd, deny else; shell = ask or deny in `--yes` CI).
`--format jsonl` is the default for scripts. A human TTY may still show text. The machine stream must exist.

Next: Slice 3.

#### Slice 3: Session + Audit

Read first: SCHEMA SessionRecord, SCHEMA Audit event, HLD Session Store, HLD Audit Log.

- `~/.ravand/sessions/<id>.json` as in SCHEMA.md
- append-only `~/.ravand/audit.jsonl`
- events: `run.started`, `run.ended`, `agent.selected`, `agent.denied`, `permission.allow`, `permission.deny`, `auth.missing`

Next: Slice 4.

#### Slice 4: Overflow

Read first: HLD run path step 8, SCHEMA `overflowOf`, audit type `agent.overflow`.

If Runtime ends with rate_limit / quota / crash AND policy.overflow is set AND overflow not in deny: start a second run. Audit `agent.overflow`. Same task_id, field `overflowOf`.

Next: Slice 5.

#### Slice 5: Observability hooks (no vendor backend required)

Read first: SCHEMA OTel.

- Emit OTel spans if `OTEL_EXPORTER_OTLP_ENDPOINT` is set; else no-op.
- Root span: `invoke_agent` with attributes in SCHEMA.md
- Child: `execute_tool` per tool call
- Metrics counters in-process even without OTLP: duration, result enum

Next: Slice 6, only after `ravand run` works on one machine.

#### Slice 6: Bus (feature-flagged)

Read first: HLD Dispatcher, Worker, Bus. SCHEMA TaskMessage, WorkerInfo. MODULAR bus seam.

Only if a bus is configured. Default driver is PGMQ.

- Talk to the Bus seam, not to `pgmq` from Policy or Runtime
- Dispatcher `send` to `q.tasks`
- Worker loop `read` + heartbeat + archive/ack
- Payload exactly as SCHEMA.md (no secrets)
- Worker skips job if local profile cannot run that agent (`capability_miss`, nack fast)
- Do not add Kafka in this slice. Postgres + PGMQ is the first provider.

### Code style

- Small packages matching `docs/HLD.md` service names
- No catch-all `utils.py` for policy
- Failures: typed errors `PolicyDenied`, `AuthRequired`, `CapabilityMiss`, `FailClosed`
- Exit codes: 0 ok, 2 auth, 3 policy deny, 4 spawn fail, 5 agent error

### Tests to write first (TDD)

For every GitHub issue: add or change a pytest that fails, run it, then write the code. Do not write production code before the failing test.

1. Policy: personal repo + work override flag → denied
2. Permission: write `/etc/passwd` → deny
3. Registry: unknown agent id → error
4. Runtime mock: fake ACP server that answers initialize/session/prompt
5. Overflow: mock rate_limit then second agent called

### Do not

- Implement Slack, InsForge, AgentField, or a desktop app in v0
- Add Kubernetes
- Store prompts in audit for `profile = work` unless `RAVAND_AUDIT_BODIES=1`
- Reformat this document’s product rules

### When stuck

Prefer the official Python ACP SDK and acpx’s spawn/session shape over writing JSON-RPC by hand.
Reference: https://github.com/openclaw/acpx (MIT), https://agentclientprotocol.com

Reading order lives in [docs/README.md](docs/README.md).
