# Review and merge

Reading: [Docs map](README.md)

Previous: [Bootstrap plan](BOOTSTRAP.md)
Next: GitHub Project

Grok reviews. Kimi 2.7 and Cursor Composer open PRs. Safe PRs merge without waiting for a human ping. Unsafe PRs stay open.

Board: [Ravand v0](https://github.com/orgs/ravand-ai/projects/1)

## Open a PR

From the issue branch:

```bash
git push -u origin N-short-description
gh pr create --base main --head N-short-description \
  --title "type: what changed (#N)" \
  --body "Closes #N"
```

One issue, one branch, one PR. If you found extra work, open a new issue instead of stuffing the PR.

## Grok review checklist

Run on the PR ref:

1. `uv run pytest` green (or the PR is TDD-only and the failures are the point, and the body says so).
2. No hatchling. Build backend is `uv_build`.
3. No new PyPI dep unless the issue named it, or a benchmark + second reviewer exists.
4. No secrets, cookie paths, `sk-`, `xai-`, `Bearer` in the diff.
5. Files match the wave ownership table in BOOTSTRAP.md.
6. CodeQL on the PR is not failing for a new real bug. A new CodeQL finding → new issue, not a silent extra commit on this PR unless it is this issue.

If all of those hold, the PR is **safe**. Merge it.

```bash
gh pr checkout N
uv run pytest
gh pr merge N --squash --delete-branch
```

If it is not safe: comment what failed, do not merge. Author (or overflow CLI) fixes on the same branch.

## After merge

Update the GitHub Project card to Done. Unblock the next wave. Next Ready cards may run in parallel (Kimi + Cursor). Grok reviews those PRs.

Once `ravand run` works (Slice 2 on `main`):

```bash
uv run ravand run -a kimi --format jsonl "implement issue #N. SECURITY.md. One branch."
uv run ravand run -a cursor --format jsonl "..."
uv run ravand run -a grok --format jsonl "review PR #N using docs/REVIEW.md"
```

Do not call `kimi` / `cursor-agent` / `grok` naked on this repo after that, except overflow if `ravand run` itself is broken.

## Stacked slices

Merge Slice 0 before Slice 1, Slice 1 before Slice 2. GitHub **blocked by** already encodes that. Do not merge a blocked PR.
