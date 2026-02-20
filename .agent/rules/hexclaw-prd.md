# HexClaw PRD v1.0
**Agent Orchestrator**: HexStrike MCP + OpenClaw daemon. Thrifty, Telegram hub.

**Stack**: Python asyncio, DuckDB/Parquet/Postgres, Telegram bot, LiteLLM(Google Pro/Z.AI/OR/free), Redis cache.

**Modules**:
1.install.py: pip(litellm redis python-telegram-bot temp-mails psycopg2 duckdb msgraph google-api-python-client), .env(email/pass), postgres/redis, systemd
2.daemon.py: Heartbeat queue→MCP YAML→Telegram notify
3.inference.py: Tier rotate, sqlite tokens
4.cache.py: Redis exact+semantic embeddings
5.telegram.py: /orchestrate/status, inline approve
6.data.py: DuckDB analytics, text-to-sql suggest_next
7.skills/recon_osint.yaml: amass/rustscan/nuclei
8.email/: M365 Graph + Gmail API sort/reply/new_inbox

**Rules**: Cache>rules>LLM. Telegram buttons=0t.
