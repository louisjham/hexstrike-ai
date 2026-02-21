# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Core Architecture

This is a dual-system project:
1. **HexStrike AI Server** ([`hexstrike_server.py`](hexstrike_server.py:1)) - Flask-based MCP server with 150+ security tools
2. **HexClaw Daemon** ([`daemon.py`](daemon.py:1)) - Asyncio orchestrator for autonomous agent workflows

Both systems share common configuration via [`config.py`](config.py:1) - always import paths from there.

## Essential Commands

```bash
# Start MCP server (required for AI agent communication)
python3 hexstrike_server.py

# Start MCP client (connects to server)
python3 hexstrike_mcp.py --server http://127.0.0.1:8888

# Run HexClaw autonomous daemon
python3 daemon.py

# Run threat intelligence monitor
python3 monitor.py              # continuous
python3 monitor.py --once       # single pass
python3 monitor.py --dry-run    # log without sending
python3 monitor.py --test-alert  # fire test alert

# Interactive setup wizard
python install.py
```

## Critical Non-Obvious Patterns

### Path Management (MANDATORY)
All modules MUST import shared paths from [`config.py`](config.py:1):
- `ROOT`, `DATA_DIR`, `LOG_DIR`, `SKILLS_DIR`, `JOBS_DB`, `TOKEN_LOG_DB`
- These directories are auto-created on first import

### Token Saving (PRD Rule: Cache > Rules > LLM)
Before calling [`inference.ask()`](inference.py:98), ALWAYS call [`cache.check()`](cache.py:130) first:
```python
from cache import Cache
c = Cache()
hit = c.check(prompt)
if hit:
    return hit  # 0 tokens consumed
response = await inference.ask(prompt)
c.store(prompt, response)
```

### Environment Variables Required
- `TELEGRAM_BOT_TOKEN` - Required for Telegram bot (daemon.py)
- `TELEGRAM_CHAT_ID` - Required for Telegram whitelist
- `REDIS_URL` - Optional but recommended for semantic caching (default: redis://localhost:6379/0)
- `POSTGRES_DSN` - Optional for persistent storage
- `GOOGLE_API_KEY` - Required for LLM planner

### Skill Workflow Format
Skills are YAML files in [`skills/`](skills/) with this structure:
```yaml
name: skill_name
steps:
  - tool: mcp_tool_name
    input: context_key
    output: context_key
    on_fail: continue|abort
    notify: always|on_error|never
    gate: none|approve
```

### Database Architecture
- **Jobs**: SQLite at [`data/jobs.db`](data/jobs.db) - job queue and status
- **Token Log**: SQLite at [`data/token_log.db`](data/token_log.db) - LLM usage tracking
- **Analytics**: DuckDB in-memory via [`data.get_duck()`](data.py:35) - fast queries on Parquet files
- **Cache**: Redis (DB 0 for exact match, DB 1 for semantic) with embedding fallback

### Import Patterns
- Use `from __future__ import annotations` for async modules (daemon.py, monitor.py, telegram.py, cache.py)
- Use `from dotenv import load_dotenv` at module level for .env access
- Optional imports wrapped in try/except (e.g., sentence-transformers in cache.py)

### HexStrike Server Specifics
- The server file is 18k+ lines with embedded exploit templates
- API port configurable via `HEXSTRIKE_PORT` env var (default: 8888)
- Host configurable via `HEXSTRIKE_HOST` env var (default: 127.0.0.1)
- Health check endpoint: `GET /health`

## Testing & Linting

No standard test framework or linting configured. Manual testing via:
- `python3 hexstrike_server.py --debug` for verbose logging
- `python3 hexstrike_mcp.py --debug` for MCP client debugging
- `python3 monitor.py --test-alert` for monitor pipeline verification

## HexClaw Orchestration Rules

From [`.agent/hexclaw-prd.md`](.agent/hexclaw-prd.md:1):
- Use rules/cached responses where possible (0-token gating)
- Telegram buttons for multi-choice (no inference needed)
- Use cheap models (Flash/Haiku) for planning, Pro/High-tier only for complex exploit/dev logic
- Target: Plan-to-Execution latency < 5s, /orchestrate success rate > 80%

## External Dependencies

150+ security tools must be installed separately (see INSTALL.md or run `python install.py`):
- Core: nmap, nuclei, amass, subfinder, gobuster, sqlmap
- Browser: Chrome/Chromium + ChromeDriver for selenium automation
- Optional: Redis server for caching, PostgreSQL for persistence
