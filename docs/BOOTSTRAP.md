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

Assign **one issue to one CLI**. Do not run three builders on the same files.

## Contracts to put on disk first (before Slice 0 code)

1. Root `harness.toml` (copy of examples, this repo as the first project).
2. `docs/SECURITY.md` (this stack).
3. This file.
4. GitHub issues with acceptance tests (this plan's issue list).
5. `AGENTS.md` slices unchanged in order.

Language lock for v0: **TypeScript, Node 22+, pnpm**. Do not start a second language.

## Phases

### Phase A: contracts (no product binary)

- Root `harness.toml`
- Security roles and subagent grants
- Issues on GitHub
- Humans still invoke `grok` / `kimi` / `cursor` directly, but they must follow SECURITY.md

Exit: an issue exists for every v0 slice. This repo has a policy file.

### Phase B: policy without ACP (Slice 0–1)

- `ravand` bin
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

## Issue prompt template

Paste into Grok, Kimi, or Cursor:

```
You are the builder for Ravand Agents. Read AGENTS.md, docs/SECURITY.md, docs/BOOTSTRAP.md, and the GitHub issue.

Implement only that issue. Write failing tests first for policy and permission.
Do not read ~/.ravand/profiles cookie files. Do not add secrets. Do not start the next slice.
Run the verify commands in AGENTS.md plus the issue's tests.
Do not commit unless the issue says to. Do not push.
```

## GitHub issues to open

Open these in order. Each body must list parent issue, assigned CLI, and tests.

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
