# HexClaw PRD v2.0
**Universal Agent Orchestration Engine**
Not pentest-only: End-to-end workflows (cyber/OSINT/dev/automation). YAML configs, Telegram hub.

## Tech Stack & Architecture
- **Backend**: Python asyncio daemon, MCP server wrapper.
- **Orchestration**: YAML-based workflow loader, dynamic "Agent Planner" (low-token).
- **Data**: DuckDB (analytics/Parquet), Postgres (storage/job state).
- **Inference**: LiteLLM (Google Pro/OpenRouter/free); Redis semantic cache.
- **Interface**: Telegram bot (v2: voice, inline graphs, interactive buttons, file uploads).
- **Plugins**: MCP-compatible tools (Git, Docker, HexStrike, any CLI).

## Core Modules (Updated)
1.  **install.py**: Dependency & environment management.
2.  **daemon.py**: (Extended) YAML workflow engine, heartbeat pool, `/orchestrate` goal handler.
3.  **planner.py**: (New) LLM-powered goal-to-workflow translator. Generates execution graphs.
4.  **telegram_ui.py**: (Enhanced) Rich interactivity: /plan, /orchestrate, /edit workflow, voice commands.
5.  **skills/**: YAML templates for Cyber, Dev, OSINT, and Custom automation.
6.  **monitor.py**: Threat Intel / CVE alerts with proactive "Suggest & Orchestrate" triggers.

## Orchestration Workflows
### 1. Cyber (Default)
`recon → suggest → nuclei → exploit → report`
### 2. Dev-Ops
`git clone → lint → test → deploy`
### 3. OSINT
`breach hunt → social mapping → darkweb scan → report`
### 4. Custom
`User-defined YAML drop-in`

## Telegram Command Set (v2)
- `/orchestrate "<goal>"`: Generate and confirm a multi-step plan.
- `/plan`: View current/pending workflow graph.
- `/edit <workflow>`: Inline YAML editing.
- `/recon <target>`: Legacy single-skill shortcut.
- `/status`: Real-time job dashboard.

## Efficiency Constraints
- **0-Token Gating**: Use rules and cached responses where possible.
- **Telegram Buttons**: No inference for standard multi-choices.
- **Low-Token Planner**: Use cheap models (Flash/Haiku) for planning; Pro/High-tier only for complex exploit/dev logic.

## Success Metrics
- Plan-to-Execution latency < 5s.
- /orchestrate success rate > 80% without manual YAML correction.
- Telegram-only management (zero SSH required for daily Ops).

---
*PRD v2.0 finalized. Proceed to implementation of Orchestrator Engine.*
