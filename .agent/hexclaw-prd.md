# HexClaw PRD v1.0
**Autonomous cybersecurity agent** (HexStrike MCP + OpenClaw daemon). Thrifty inference, Telegram hub.

## Tech Stack
- Backend: Python asyncio daemon, MCP server wrapper
- Data: DuckDB(analytics/Parquet), Postgres(storage)
- Comms: Telegram bot (inline buttons/approvals)
- Inference: LiteLLM (Google Pro/Z.AI/OpenRouter/free); Redis cache (exact/semantic)
- Email: SMTP app + temp-mails throwaways
- Monitor: RSS/CVE alerts → Telegram

## Core Modules (Implement order)
1. **install.py**: pip deps/redis/postgres/temp-mails/.env/service
2. **daemon.py**: Heartbeat poll queue, MCP chains, notify Telegram
3. **inference.py**: Provider rotate/tier (high=google_pro); token log sqlite
4. **cache.py**: Redis exact+semantic (embeddings); check before LLM
5. **telegram.py**: Hub bot (/recon/status); inline approve/multi-choice
6. **data.py**: DuckDB query/store Parquet; Postgres aggregate; text-to-sql suggest_next
7. **skills/**: recon_osint.yaml (amass/rustscan/nuclei); vuln_prioritize.py
8. **monitor.py**: RSS CVE/Shodan → Telegram alert + suggest

## Workflows (MCP YAML)
us-recon:

amass → subs.parquet

rustscan → ports.parquet

nuclei → vulns.parquet

suggest_next → Telegram buttons

text

## Constraints (0 tokens where possible)
- Rules/cache > LLM
- Telegram buttons = 0 inference
- SQL cache hits for analytics
- Free/low tier for status/plans

## Success
- /recon target → Full chain → Telegram report (under 100 tokens total)
- Alerts → Approve → Execute
- Usage dashboard /stats

PRD complete. Generate code modularly: install→daemon→etc.