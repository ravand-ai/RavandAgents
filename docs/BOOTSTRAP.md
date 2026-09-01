# Bootstrap: Ravand builds Ravand

Reading: [Docs map](README.md)

Previous: [Security contract](SECURITY.md)
Next: GitHub issues, then [AGENTS.md](../AGENTS.md) Slice 0

We use Grok Build, Kimi, and Cursor **now** to implement Ravand. Then we use Ravand to run those same CLIs under policy. Until `ravand run` works, the contracts in this repo are the stand-in control plane: `harness.toml`, `AGENTS.md`, `docs/SECURITY.md`.

[SUCCESS.md](SUCCESS.md) still wins on ship order. This file is the work plan.

## Goal

A loop we can run every day:

```
human writes a GitHub issue
    → builder (grok | kimi | cursor) implements one issue
    → tester + secret-scan subagents
    → security-gate reviews
    → human merges
when ravand exists:
    ravand run -a grok "implement #N"
    same policy, same audit
```

Do not wait for the native loop. The first dogfood is ACP spawn of tools we already have.

## Tools we have

| CLI | Role on this repo | Why |
|-----|-------------------|-----|
| Grok Build (`grok`) | default builder, kernel, ACP runtime | default in `harness.toml` |
| Kimi (`kimi`) | overflow builder, tests, policy tables | overflow agent |
| Cursor (`cursor-agent`) | CLI UX, `ravand status`, editor-shaped diffs | third backend |
| Human | orchestrator, merge, security-gate when no second model | never skip |

Assign **one issue to one CLI**. Grok, Kimi, and Cursor run **at the same time** when their issues do not share files. Do not run two builders on the same path.

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

## Phases

### Phase A: contracts (no product binary)

- Root `harness.toml`
- Security roles and subagent grants
- Issues on GitHub
- Humans still invoke `grok` / `kimi` / `cursor` directly, but they must follow SECURITY.md

Exit: an issue exists for every v0 slice. This repo has a policy file.

### Phase B: policy without ACP (Slice 0–1)

- `ravand` bin (`uv run ravand`)
- `ravand which` JSON
- Profile dirs created, never filled with copied cookies
- Tests: profile mismatch, deny list, unknown agent

Exit: `ravand which` in this repo prints work + grok + kimi overflow.

### Phase C: one real child (Slice 2–3)

- Spawn `grok agent stdio` with isolated HOME
- Permission broker repo-only
- JSONL SessionEvent
- Session + audit files
- secret-scan on the stream

Exit: `ravand run --format jsonl "print the repo name"` works with Grok logged into the work HOME.

### Phase D: dogfood (Slice 4 + status + other CLIs)

- Overflow to Kimi
- `ravand status`
- Cursor and Kimi as registered backends
- Implement the next GitHub issue **through** `ravand run -a grok`

Exit: SUCCESS.md four checks. We stop opening Grok outside Ravand for this repo.

### Phase E: stop

No bus, no native loop, no plugin registry, no cloud. Open those issues only after Phase D.

## Agent graph (security first)

```
human (orchestrator)
  ├── security-gate     (read-only review, every PR)
  ├── builder           (exactly one of grok | kimi | cursor)
  │     ├── secret-scan (read-only subagent, every builder run)
  │     └── tester      (writes tests only)
  └── docs              (docs/ only, optional)
```

Rules:

- Builder never merges.
- Security-gate never writes product code.
- If secret-scan fails, builder output is discarded.
- Subagent grant ≤ parent grant.
- Prompt for an issue must include: issue URL, SECURITY.md, AGENTS.md slice, "do not implement the next slice."
- Concurrent builders: only issues in the same wave, and only disjoint file sets.
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

Start the next wave when the previous wave's PRs are merged (or the issue is not blocked).

| Wave | Parallel issues | CLI | Owns (do not touch others) |
|------|-----------------|-----|----------------------------|
| 1 | #2 skeleton | Grok | `pyproject.toml`, `uv.lock`, `packages/cli`, `packages/*/pyproject.toml` stubs |
| 1 | #1 security tests | Kimi | `tests/security/` only |
| 1 | docs already done | Cursor idle, or review #2 | no product files |
| 2 | #3 `ravand which` | Kimi | `packages/policy`, `packages/profile`, `packages/registry` |
| 2 | #7 status (tests first) | Cursor | `tests/status/` until #3 lands, then `packages/cli` status command only |
| 3 | #4 grok ACP | Grok | `packages/runtime`, `packages/permissions` |
| 3 | #7 finish status | Cursor | `packages/cli` status only |
| 4 | #5 session + audit | Cursor | `packages/sessions`, `packages/audit` |
| 4 | #8 kimi + cursor backends | Grok | `packages/registry` agent commands only |
| 5 | #6 overflow | Kimi | `packages/runtime` overflow only |
| 6 | #9 dogfood | Grok via `ravand run` | one tiny docs file |

If two waves would edit `packages/cli` or `packages/runtime` at once, wait. Open a new issue for leftover work instead of stretching a wave.

## Issue prompt template

Paste into Grok, Kimi, or Cursor:

```
You are the builder for Ravand Agents. Read AGENTS.md, docs/SECURITY.md, docs/BOOTSTRAP.md, and the GitHub issue.

Implement only that issue. Branch name: N-short-description from the issue number.
TDD: write a failing pytest first, run it, then write code. Use Python 3.12+ and uv. Do not add Node or TypeScript.
Add a dependency only if the failing test cannot pass with the stdlib, or a benchmark plus a reviewer justify a performance package (own GitHub issue). Slice 0 may add pytest. ACP SDK only in Slice 2.
Work only the files this issue owns (BOOTSTRAP concurrent waves). Grok, Kimi, and Cursor may run other issues in the same wave on disjoint paths.
If you find extra work, open a new GitHub issue. Do not grow this branch.
Do not read ~/.ravand/profiles cookie files. Do not add secrets. Do not start the next slice.
Run: uv run pytest, plus AGENTS.md verify, plus CodeQL locally if available.
Do not commit unless the issue says to. Do not push.
```

## GitHub issues to open

Issues exist: https://github.com/ravand-ai/RavandAgents/issues  
Run them by **wave**, not as a single file. Each body must list parent issue, assigned CLI, and tests.

1. Security contract in CI mindset (this file + SECURITY.md already). Remaining: test fixtures for deny.
2. Slice 0 skeleton
3. Slice 1 policy + which
4. Slice 2 grok ACP + JSONL + permissions
5. Slice 3 session + audit
6. Slice 4 overflow kimi
7. `ravand status`
8. Cursor + Kimi backends wired in registry
9. Dogfood: implement a tiny docs nit **using** `ravand run`

Do not open workflow, Kafka, or native-loop issues in this batch.
