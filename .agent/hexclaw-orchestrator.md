Reposition HexClaw as "Agent Orchestration Engine": Modular workflows (cyber + general), Telegram-first interactivity, customizable YAML. Wow factor: /orchestrate "find+exploit Struts vuln" → Auto-chain → Inline approve → Report.

Updated PRD Addendum (.agent/rules/hexclaw-orchestrator.md)
text
# HexClaw: Agent Orchestrator Engine
**Not pentest-only**: End-to-end workflows (cyber/OSINT/dev/automation). YAML configs, Telegram hub.

## Positioning
- "Orchestrate agents/tools like Zapier + AutoGPT"
- Demo: /orchestrate "scan US → vulns → exploit lab" → 1 chat

## New Workflows (YAML)
orchestrate:
cyber: recon→suggest→nuclei→report
dev: git clone→lint→test→deploy
osint: breach→social→darkweb
custom: user YAML drop-in

text

## Interactivity (Telegram Superpowers)
- **Buttons**: [Run Full/Ports Only/Custom YAML/Abort]
- **Multi-choice**: /target? [US/Google/Domain/Custom]
- **Voice**: /plan "breach hunt" → "Approve steps?"
- **Files**: Upload targets.csv → Auto-scan

## Universal Engine
- **MCP Plugins**: HexStrike + user tools (git/docker/any CLI)
- **YAML Editor**: /edit workflow → Inline changes
- **Agent Planner**: Low-token "Plan: {goal}" → Workflow graph → Telegram confirm

## Wow Demos
1. `/orchestrate "US RDP vulns"` → Masscan→DuckDB→ExploitDB→Lab PoC
2. `/dev "fix lint errors"` → Git+black+pytest+PR
3. `/osint "company X breach"` → HIBP+TG scrape+report

## Agent Prompt Sequence
1. `@workspace Read hexclaw-orchestrator.md; PRD v2`
2. `Extend daemon: YAML loader /orchestrate <goal>`
3. `Telegram: voice→plan→inline graph approve`
4. `Plugins: git/dev/osint YAML templates`
5. `Test: /orchestrate "scan→vulns" → full Telegram flow`
Paste One-by-One
text
@workspace Update PRD: Orchestrator engine, YAML workflows, /orchestrate goal→Telegram plan/approve.
Universal appeal: Cyber pros + devs → One engine.