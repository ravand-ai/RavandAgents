# How to use Ravand

Reading: [Docs map](README.md)

Previous: [Product README](../README.md)
Next: [examples/harness.toml](../examples/harness.toml), then [SCHEMA.md](SCHEMA.md) for keys

This file is the operator how-to for the live `ravand` CLI. It does not replace [SUCCESS.md](SUCCESS.md) or [HLD.md](HLD.md).

## Install

Use Python 3.12 or newer. Install `uv`.

```bash
uv sync
uv run ravand --help
```

From this repo, prefix every command with `uv run`. The rest of this file writes `ravand` for short.

## First hour

1. Run `ravand init` in the repo. This writes `./harness.toml`.
2. Copy `examples/policy.user.toml` to `~/.ravand/config.toml`.
3. Run `ravand login work`. This prints vendor login commands for that seat.
4. Run `ravand which`. This prints the resolved JSON.
5. Run `ravand status`. This probes login state.
6. Run `ravand run "your task"`. This spawns the selected ACP agent.

`ravand init` refuses to overwrite an existing `harness.toml`. That case exits 3.

## Policy files

A run requires `./harness.toml` in the current repo. If that file is missing, the CLI fails closed and tells you to run `ravand init`.

User seats live in `~/.ravand/config.toml`. Start from `examples/policy.user.toml`.

| Path | Role |
|------|------|
| `./harness.toml` | Repo policy. Required for a run. |
| `~/.ravand/config.toml` | User profiles and named accounts. |
| `~/.ravand/profiles/<name>` | Isolated seat HOME for vendor CLIs. |
| `~/.ravand/sessions/` | Session records. |
| `~/.ravand/audit.jsonl` | Append-only audit log. |

Set `RAVAND_HOME` to move the `~/.ravand` tree.

Do not put secrets in `harness.toml`.

## Commands

| Command | What it does |
|---------|----------------|
| `ravand init` | Write `./harness.toml`. Refuse if the file exists. |
| `ravand which` | Print JSON for profile, agent, overflow, permissions, home, and command. |
| `ravand login [profile]` | Print vendor login hints with `HOME` set to the profile seat. |
| `ravand run PROMPT` | Spawn the selected ACP agent. |
| `ravand status` | Login doctor. Probe seats. Do not read cookie contents. |
| `ravand serve` | Start HTTP, cron, and worker on one bus. |
| `ravand steer SESSION TEXT` | Continue a live ACP session. |
| `ravand pause --agent ID --profile NAME` | Fail-close new runs for that pair. |
| `ravand plugin add PATH` | Install a plugin from a path. |
| `ravand plugin list` | List installed plugins. |
| `ravand tui` | Operator screen on a TTY. Do not grow this command. |

`ravand which` also accepts `--profile`, `-a` / `--agent`, and `--account`.

## Agents

These ids and ACP commands come from the registry.

| Id | ACP command |
|----|-------------|
| `grok` | `grok agent stdio` |
| `kimi` | `kimi acp` |
| `claude` | `npx -y @agentclientprotocol/claude-agent-acp` |
| `cursor` | `cursor-agent acp` |
| `opencode` | `opencode acp` |
| `dsh` | `dsh --profile acp` |

An unknown id fails closed. The CLI does not spawn.

## Run flags

- `-a` / `--agent` picks the agent id.
- `--account` picks a named account from `~/.ravand/config.toml`.
- `--format jsonl` is the default. It prints SessionEvent JSONL.
- `--format text` prints text for a human TTY.
- `--yes` auto-decides permissions (`repo-only`). It never prompts.

A missing prompt exits 2.

## Overflow

The first agent can hit `rate_limit`, `quota`, `crash`, or an auth miss.

If policy sets `overflow` and that agent is not on the deny list, Ravand starts the overflow agent.

The overflow run keeps the same `task_id`. Audit type is `agent.overflow`. Overflow is a fallback. It is not collaboration.

## Serve

`ravand serve` with no subcommand starts HTTP, cron, and worker together.

Subcommands: `serve http`, `serve cron`, `serve worker`, `serve acp`.

`ravand serve http` binds `127.0.0.1:8765`. Change the port with `--port`.

`POST /run` accepts a JSON prompt and streams SSE.

Other POST paths are signed webhooks. Send `X-Ravand-Signature: sha256=<hex>`. Unsigned requests fail closed.

`ravand serve acp` is a stdio ACP server. The agent name is `ravand`.

## Fail closed

If Policy cannot decide, the CLI does not spawn.

A repo with `classification = "customer"` cannot use a personal profile or a personal account.

A missing vendor login prints the login command and exits 2.

Keep secrets out of `harness.toml`. Do not log vendor cookie files.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | ok |
| 2 | auth required |
| 3 | policy deny |
| 4 | spawn fail |
| 5 | agent error |
| 6 | capability miss (worker) |

## Not on the CLI yet

There is no `ravand workflow` command.

Harness `subagents` is a Policy check only. The runtime does not spawn a child for that key.

The native loop is a stub. It does not call a provider.

Do not grow TUI.

OpenCode is a backend. The command is `opencode acp`.

OpenHands is not in the product.
