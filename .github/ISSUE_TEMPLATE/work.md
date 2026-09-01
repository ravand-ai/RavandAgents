---
name: Work item
about: One issue, one branch, TDD
labels: v0
---

## Why

## Branch

`N-short-description` after this issue gets a number.

## Builder

Default coder: Kimi 2.7 or Cursor Composer. Grok: review and management; code if the others are limited or the files are free.

Subagents: tester, secret-scan.

If the assigned CLI is rate-limited or unavailable, comment `overflow: <from> → <to>` and continue. Do not wait.

## TDD

1. Write a failing pytest.
2. Run `uv run pytest` and show the failure.
3. Write the minimum code.
4. Run pytest green.

## Do

-

## Do not

- Grow this branch with extra work. Open a new issue instead.
- Secrets, cookie files, vendor HTTP wrap.
- Add a PyPI dependency for convenience. Performance deps need a benchmark, a second reviewer, and an issue that names the package.
- Start work while this issue is **Blocked** on the Ravand v0 GitHub Project.
- Edit files another open wave already owns (see `docs/BOOTSTRAP.md` concurrent waves).

## Exit

- `uv run pytest` green
- CodeQL on the PR
- SECURITY.md still holds
