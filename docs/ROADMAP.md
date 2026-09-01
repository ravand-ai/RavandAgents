# Roadmap

## v0: dogfood (one machine)

- Policy + Profile + Registry
- ACP Runtime for grok / kimi / claude / cursor
- `ravand which` `ravand run` `ravand login`
- Session + Audit
- Overflow
- OTel no-op or OTLP if env set

Exit: you can run Ravand Agents on a real repo with Grok Build logged into the personal or work HOME.

## v1: first other humans

- `harness.toml` committed per repo
- ACP server mode so Zed / VS Code attach to `ravand`
- Login doctor (`ravand status`)
- Compare: `ravand run --all "review this diff"`
- Classification field enforced (customer repo ≠ personal profile)

## v2: distribution

- Postgres + PGMQ (`q.tasks`, `q.events`, `q.results`)
- Worker process + capability advertisement
- VT heartbeat, archive, poison after N crashes
- Task table + task_events
- Work vs personal queues

## v3: control plane completeness

- Fail-closed if Policy/DB down
- Inventory of adapters × profiles × workers
- `ravand pause --agent X --profile work` kill/freeze
- Human approval queue (not only local ask)
- Signed evidence record (task_id, actor, policy hash, decision)
- Judge plugin: tests must pass before status=ok
- Eval store: golden tasks, Claude vs Grok
- Utilization metrics (duration, tool_calls, rate_limits) as cost proxy
- Worker drain/cordon
- SLOs + page on queue age

## Explicitly later / partners

- InsForge MCP
- AgentField identity
- Slack / OpenACP channels
- Cordis custom loop as one registry row
- GRC mapping (NIST / EU) as export, not the product
- Infra AIOps (disks, kube)

## Positioning reminder

Ravand Agents is an **agent control plane** for subscription coding agents.

- AI governance = rulebook + court. Ravand Agents supplies runtime gates + evidence, not DPIAs.
- AIOps = NOC for infra. Ravand Agents supplies queue/worker health, not cluster healing.
- AgentOps = traces, evals, cost for agent runs. v3 overlaps here.
