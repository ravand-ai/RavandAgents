# Bootstrap: Ravand builds Ravand

Reading: [Docs map](README.md)

Previous: [Security contract](SECURITY.md)
Next: leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162). SUCCESS [#56](https://github.com/ravand-ai/RavandAgents/issues/56) is closed. Current feature milestone is v2-s1-bus. Do not grow TUI. Do not implement issue 51.

We use Grok Build, Kimi, and Cursor to implement Ravand. `ravand run` already works on this repo. Prefer `uv run ravand run -a grok|kimi|cursor --yes` over naked CLIs here ([REVIEW.md](REVIEW.md)). The contracts still bind every run: `harness.toml`, `AGENTS.md`, `docs/SECURITY.md`.

[SUCCESS.md](SUCCESS.md) still wins on ship order. This file is the work plan.

## Goal

A loop we can run every day:

```
human writes a GitHub issue
    → builder (grok | kimi | cursor) implements one issue
    → tester + secret-scan subagents
    → security-gate reviews
    → human merges
```

Prefer `uv run ravand run -a grok|kimi|cursor --yes` over naked `kimi` / `cursor-agent` / `grok` on this repo ([REVIEW.md](REVIEW.md)):

```
uv run ravand run -a kimi --yes "implement #N"
uv run ravand run -a cursor --yes "..."
uv run ravand run -a grok --yes "review PR"
```

Same policy, same audit. Do not wait for the native loop. The first dogfood is ACP spawn of tools we already have.

## Tools we have

| CLI | Default job | Also may |
|-----|-------------|---------|
| Kimi 2.7 (`kimi`) | **Coding** (policy, tests, slices) | Review if Grok is down |
| Cursor Composer (`cursor-agent`) | **Coding** (CLI, runtime, diffs) | Review if Grok is down |
| Grok Build (`grok`) | **Review, board, issue management**, and coding when needed | Take any Ready coding issue if Kimi or Cursor hit a limit |
| Human | Merge, orchestrator, security-gate if no reviewer | never skip |

All three can code. Prefer Kimi 2.7 and Cursor Composer for implementation. Prefer Grok for review, GitHub Project status, blocked-by, and splitting new issues.

Assign **one active builder per issue**. Kimi and Cursor run **at the same time** on disjoint files. Grok reviews their PRs in parallel and may code a third Ready card if the files do not overlap.

**Overflow (process):** product overflow (`agent.overflow`) exists. If the assigned CLI is rate-limited, logged out, or gone, do not stall the wave. Comment on the issue `overflow: kimi → cursor` (or grok), then the other CLI continues **that same branch** or the next Ready issue. Same `task` / issue number. Do not duplicate the work on a second branch. Prefer `uv run ravand run` for the overflow CLI. Keep this human overflow comment when `ravand run` itself is broken.

## Contracts to put on disk first (before Slice 0 code)

1. Root `harness.toml` (copy of examples, this repo as the first project).
2. `docs/SECURITY.md` (this stack).
3. This file.
4. GitHub issues with acceptance tests (this plan's issue list).
5. `AGENTS.md` slices unchanged in order.

Language lock for v0: **Python 3.12+ and uv**. Do not start a second language.

Process lock:

- TDD. Failing pytest first, then code.
- One GitHub issue → one branch `N-short-description` → one PR.
- If you discover extra work, open a new GitHub issue. Do not grow the current branch.
- CodeQL on push and PR. A CodeQL alert becomes a new issue, not a silent extra commit on the wrong branch.
- Safe work (SECURITY.md holds, TDD, no extra deps, disjoint files) does not wait for human approval to implement or commit. Human still merges to `main`.
- Builder never merges. Merge uses the six-point checklist in [REVIEW.md](REVIEW.md). Leftover CLI is #162. Current feature milestone is v2-s1-bus. Do not grow TUI. Do not implement issue 51.

## Phases

### Phase A: contracts (no product binary) — done

- Root `harness.toml`
- Security roles and subagent grants
- Issues on GitHub
- Humans still invoke `grok` / `kimi` / `cursor` directly, but they must follow SECURITY.md

Exit: an issue exists for every v0 slice. This repo has a policy file.

### Phase B: policy without ACP (Slice 0–1) — done

- `ravand` bin (`uv run ravand`)
- `ravand which` JSON
- Profile dirs created, never filled with copied cookies
- Tests: profile mismatch, deny list, unknown agent

Exit: `ravand which` in this repo prints work + grok + kimi overflow.

### Phase C: one real child (Slice 2–3) — done

- Spawn `grok agent stdio` with isolated HOME
- Permission broker repo-only
- JSONL SessionEvent
- Session + audit files
- secret-scan on the stream

Exit: `ravand run --format jsonl "print the repo name"` works with Grok logged into the work HOME.

### Phase D: dogfood (Slice 4 + status + other CLIs) — in progress

- Overflow to Kimi
- `ravand status`
- Cursor and Kimi as registered backends
- Implement the next GitHub issue **through** `ravand run` (kimi or cursor to code; grok to review; overflow CLI if one is limited)

Those bullets shipped. SUCCESS [#56](https://github.com/ravand-ai/RavandAgents/issues/56) is closed. Leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162).

Exit: SUCCESS.md four checks. We stop opening Grok outside Ravand for this repo.

### Phase E: stop

v1 shipped (including optional native loop). Current feature milestone is v2-s1-bus. Do not grow TUI. Do not implement issue 51.

## Agent graph (security first)

```
human (orchestrator, merge)
  ├── grok            review + management (and code if needed)
  ├── builder         kimi 2.7 and/or cursor composer (coding)
  │     ├── secret-scan
  │     └── tester
  └── overflow        if kimi or cursor is limited, grok or the other coder continues
```

Rules:

- Builder never merges. Grok-as-reviewer never merges either. Human merges. Merge uses the six-point checklist in [REVIEW.md](REVIEW.md). Leftover CLI is #162. Current feature milestone is v2-s1-bus. Do not grow TUI. Do not implement issue 51.
- Prefer Grok as security-gate / reviewer. If Grok is limited, Kimi or Cursor may review a PR they did **not** author.
- If secret-scan fails, builder output is discarded.
- Subagent grant ≤ parent grant.
- Prompt for an issue must include: issue URL, SECURITY.md, AGENTS.md slice, "do not implement the next slice."
- Concurrent builders: only issues in the same wave, and only disjoint file sets.
- If a CLI hits a limit: comment overflow on the issue, another CLI continues. Do not wait.
- No new PyPI package for convenience. Stdlib first. pytest is the Slice 0 exception. ACP SDK is Slice 2.
- Performance-only packages need a checked-in benchmark, a reviewer besides the builder, and their own GitHub issue. See below.

## GitHub Project

Track v0 on a GitHub Project so blocked work is visible. Status follows the waves. An issue that cannot start stays **Blocked** with the parent issue linked (GitHub "blocked by").

Do not start a builder on a Blocked card. Grok, Kimi, and Cursor take **Ready** cards in the same wave, disjoint files.

Project: [Ravand v0](https://github.com/orgs/ravand-ai/projects/1). Add every new issue to it. If a slice is blocked by another, set **blocked by** on the GitHub issue (already set for #1–#9). Do not encode the graph only in chat.

## Dependencies (performance)

Default: stdlib. pytest (dev) in Slice 0. Official Python ACP SDK in Slice 2.

You may add a package **for speed** when all of these hold:

1. A failing or slow benchmark lives in `benchmarks/` (or the issue) and names the Ravand path (for example JSONL encode, TOML parse, ACP frame read).
2. The PR shows before/after numbers on the same machine command.
3. A reviewer who is not the builder accepts the number and the license/supply-chain cost.
4. The dependency is the subject of its own GitHub issue (or the current issue said "add X for performance"). CodeQL and secret-scan still run.

Reject: pydantic because models look nicer, httpx before we have HTTP, a CLI framework before `argparse` hurts. Those are convenience, not performance.

## Concurrent waves

Waves 1–6 (through dogfood issue 9) are shipped / historical. SUCCESS [#56](https://github.com/ravand-ai/RavandAgents/issues/56) is closed. Leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162). Current feature milestone is v2-s1-bus. Do not grow TUI. Do not implement issue 51.

The table is historical file ownership. REVIEW.md still uses it. It is not a current work plan.

| Wave | Status | Parallel issues | Default coder | Grok | Owns (do not touch others) |
|------|--------|-----------------|---------------|------|----------------------------|
| 1 | shipped | #2 skeleton | Kimi 2.7 or Cursor Composer | review PR | `pyproject.toml`, `uv.lock`, `packages/cli`, package stubs |
| 1 | shipped | #1 security tests | the other coder | review PR | `tests/security/` only |
| 2 | shipped | #3 `ravand which` | Kimi 2.7 | review | `packages/policy`, `packages/profile`, `packages/registry` |
| 2 | shipped | #7 status (tests first) | Cursor Composer | review | `tests/status/` then `packages/cli` status only |
| 3 | shipped | #4 grok ACP | Cursor Composer or Kimi | review; code if they are limited | `packages/runtime`, `packages/permissions` |
| 3 | shipped | #7 finish status | Cursor Composer | review | `packages/cli` status only |
| 4 | shipped | #5 session + audit | Cursor Composer | review | `packages/sessions`, `packages/audit` |
| 4 | shipped | #8 kimi + cursor backends | Kimi 2.7 | review | `packages/registry` agent commands only |
| 5 | shipped | #6 overflow | Kimi 2.7 | review | `packages/runtime` overflow only |
| 6 | shipped | #9 dogfood | via `ravand run -a grok` or overflow CLI | manage the run | one tiny docs file |

If two waves would edit `packages/cli` or `packages/runtime` at once, wait. Open a new issue for leftover work instead of stretching a wave.

## Issue prompt template

Paste into Grok, Kimi, or Cursor:

```
You are a Ravand builder (Kimi 2.7 or Cursor Composer for code; Grok for review/management and code if needed). Read AGENTS.md, docs/SECURITY.md, docs/BOOTSTRAP.md, and the GitHub issue.

Implement only that issue. Branch name: N-short-description from the issue number.
TDD: write a failing pytest first, run it, then write code. Use Python 3.12+ and uv. Do not add Node or TypeScript.
Add a dependency only if the failing test cannot pass with the stdlib, or a benchmark plus a reviewer justify a performance package (own GitHub issue). Slice 0 may add pytest. ACP SDK only in Slice 2.
Work only the files this issue owns (BOOTSTRAP concurrent waves). Grok, Kimi, and Cursor may run other issues in the same wave on disjoint paths.
If you find extra work, open a new GitHub issue. Do not grow this branch.
Do not read ~/.ravand/profiles cookie files. Do not add secrets. Do not start the next slice.
Run: uv run pytest, plus AGENTS.md verify, plus CodeQL locally if available.
Do not commit unless the issue says to. Do not push.
```

## GitHub issues 1–9 (shipped / historical)

Issues 1–9 are already opened and shipped: https://github.com/ravand-ai/RavandAgents/issues  
The list is historical. SUCCESS [#56](https://github.com/ravand-ai/RavandAgents/issues/56) is closed. Leftover CLI is [#162](https://github.com/ravand-ai/RavandAgents/issues/162). Current feature milestone is v2-s1-bus. Do not grow TUI. Do not implement issue 51.

1. shipped — Security contract in CI mindset (this file + SECURITY.md already). Remaining: test fixtures for deny.
2. shipped — Slice 0 skeleton
3. shipped — Slice 1 policy + which
4. shipped — Slice 2 grok ACP + JSONL + permissions
5. shipped — Slice 3 session + audit
6. shipped — Slice 4 overflow kimi
7. shipped — `ravand status`
8. shipped — Cursor + Kimi backends wired in registry
9. shipped — Dogfood: implement a tiny docs nit **using** `ravand run`

Do not open workflow, Kafka, or native-loop issues in this batch.
