# Security contract

Reading: [Docs map](README.md)

Previous: [How Ravand can succeed](SUCCESS.md)
Next: [Bootstrap plan](BOOTSTRAP.md)

Security is the first product. A feature that cannot fail closed does not ship.

This file is law for humans and for Grok, Kimi, and Cursor working on this repo. If it fights a convenience in a slice, this file wins.

## Must never happen

- Secrets in git, in `harness.toml`, in JSONL streams, in audit (unless `RAVAND_AUDIT_BODIES=1` and the profile is not `work`).
- Read or copy vendor CLI cookie files from a profile HOME.
- Work profile on a `personal` repo, or the reverse.
- Customer classification on a personal profile or personal account.
- Spawn when Policy, Permission Broker, or account resolution cannot decide.
- Soft deny (warn and continue).
- Wrap vendor CLI HTTP or scrape a TUI.
- A subagent that inherits write/shell when the parent was repo-read or ask.

## Isolation

| Boundary | Rule |
|----------|------|
| Profile HOME | One seat. `HOME=~/.ravand/profiles/<name>` for CLI children. |
| Repo cwd | Writes only under cwd unless policy says otherwise. |
| Subagent | Fresh process. Same cwd. Own HOME or sandbox. No extra tools. |
| Memory | Scope in every key. No cross-scope merge. |
| Stream | `SessionEvent` only. No paths to cookies. No keys. |

## Permission matrix for development agents

These are roles that work **on Ravand**, using Grok, Kimi, or Cursor. They are not all product plugins yet. The product must enforce the same idea later.

| Role | May read | May write | Shell | Secrets | Spawn child |
|------|----------|-----------|-------|---------|-------------|
| orchestrator (human) | yes | yes | yes | never commit | yes |
| builder | repo | repo (not `.env`, not profile HOME) | ask | no | tests only |
| security-gate | repo | no (except review notes) | no | scan only | no |
| tester | repo + fixtures | `packages/**/test*` | limited to test runner | fixtures fake only | no |
| docs | `docs/`, README, AGENTS, examples | those paths only | no | no | no |

Default for a child of builder: **tester**. A builder must not spawn a second builder with shell.

## Subagents (product and dogfood)

A subagent is a child run with a narrower grant. Parent grant is a ceiling, never a floor.

| Subagent | Job | Grant |
|----------|-----|-------|
| secret-scan | grep tokens, `.env`, cookie paths | read-only |
| policy-test | fail-closed cases | test runner |
| audit-check | last run has `agent.selected` or `agent.denied` | read `~/.ravand/audit.jsonl` metadata only |
| acp-mock | fake ACP server for unit tests | no network |

If a subagent needs more grant than the parent, fail closed. Do not prompt-up.

## Checks that must pass on every change

1. No files under `~/.ravand/profiles/` are read by product code except existence/stat for login doctor.
2. Tests: personal repo + work override → denied.
3. Tests: write `/etc/passwd` → denied.
4. Tests: unknown agent id → error, no spawn.
5. `ravand run --format jsonl` output contains no `sk-`, `xai-`, `Bearer`, or `HOME=.*\.claude`.

Until those tests exist, every PR description must say which of them the change does not yet cover.

Write the failing pytest first. A PR with production code and no new or updated test is not ready.

If review or CodeQL finds a new problem that is not this issue, open a new GitHub issue. Do not expand the branch.

## Reporting

A security miss is a blocking issue. Do not fold it into a feature issue. Label `security`.
