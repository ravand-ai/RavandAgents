# Roadmap

Reading: [Docs map](README.md)

Previous: [Product README](../README.md)
Next: [HLD](HLD.md)

## v0: dogfood (one machine)

- Ravand kernel (Cordis-shaped, our code)
- Policy + Profile + Registry
- ACP Runtime for grok / kimi / claude / cursor / dsh
- `ravand which` `ravand run` `ravand login`
- Session + Audit
- Overflow
- Local human ask
- OTel no-op or OTLP if env set

Exit: you can run Ravand Agents on a real repo with Grok Build logged into the personal or work HOME.

## v1: modular local runtime

- Named accounts: several Claude/Grok/other logins and API keys per profile
- Project policy picks accounts, MCP servers, functions
- Native loop plugin (optional; ACP path still works)
- Sandbox seam
- `harness.toml` committed per repo
- ACP server mode so Zed / VS Code attach to `ravand`
- Classification field enforced (customer repo ≠ personal profile or personal account)

## v2: workflows, distribution, cloud users

- Workflows and pipelines; both bind tools, functions, subagents
- Human verification queue (named approver, timeout deny)
- HTTP API and signed webhooks to start a run or workflow
- Bus seam: Postgres + PGMQ default (`q.tasks`, `q.events`, `q.results`). Kafka as an alternate provider
- Worker process + capability advertisement
- Cloud: multiple users, roles, per-project access
- Org vault for API keys. Still no CLI cookies in SaaS

## v3: evals and control plane completeness

- Fail-closed if Policy/DB down
- Inventory of adapters × profiles × workers × accounts
- `ravand pause --agent X --profile work` kill/freeze
- Signed evidence record (task_id, actor, policy hash, decision)
- Judge plugin: tests must pass before status=ok
- Eval store: golden tasks, account vs account
- Utilization and provider usage as cost proxy
- Worker drain/cordon
- SLOs + page on queue age

## Explicitly later / partners

- InsForge MCP as one MCP row
- AgentField identity
- Slack / OpenACP channels
- GRC mapping (NIST / EU) as export, not the product
- Infra AIOps (disks, kube)

## Positioning reminder

Ravand Agents is a **modular agent control plane**. Subscription CLIs, native loops, and cloud users all sit behind the same policy.

- AI governance = rulebook + court. Ravand Agents supplies runtime gates + evidence, not DPIAs.
- AIOps = NOC for infra. Ravand Agents supplies queue/worker health, not cluster healing.
- AgentOps = traces, evals, cost for agent runs. v3 overlaps here.

Next: [HLD](HLD.md)
