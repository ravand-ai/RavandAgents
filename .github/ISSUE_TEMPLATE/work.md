---
name: Work item
about: One issue, one branch, TDD
labels: v0
---

## Why

## Branch

`N-short-description` after this issue gets a number.

## Builder

Grok / Kimi / Cursor (pick one).

Subagents: tester, secret-scan.

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

## Exit

- `uv run pytest` green
- CodeQL on the PR
- SECURITY.md still holds
