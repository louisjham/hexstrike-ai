# Project Documentation Rules (Non-Obvious Only)

## Dual-System Architecture
This is NOT a single monolithic application:
- **HexStrike Server** ([`hexstrike_server.py`](../hexstrike_server.py:1)): Flask-based MCP API server with 150+ security tools
- **HexClaw Daemon** ([`daemon.py`](../daemon.py:1)): Asyncio orchestrator for autonomous agent workflows
- Both share configuration via [`config.py`](../config.py:1)

## Counterintuitive Code Organization
- `src/` does NOT exist - main code is in project root
- `skills/` contains YAML workflow definitions, not Python code
- `data/` contains SQLite databases and Parquet files (not source code)
- `logs/` contains daemon.log and monitor.log (not server logs)

## Misleading Directory Names
- `email/` contains Gmail and M365 API modules, not email sending utilities
- `.agent/` contains PRD and rules documents, not agent code
- `assets/` contains images for README, not runtime assets

## Important Context Not Evident from File Structure
- Skills are YAML files that define multi-step workflows, not single tool calls
- MCP tools are defined in hexstrike_server.py (18k+ lines), not separate files
- The "daemon" is a job queue processor, not a background service manager
- Monitor.py is a threat intelligence feed poller, not system monitoring

## Documentation Locations
- PRD (Product Requirements Document): [`.agent/hexclaw-prd.md`](../.agent/hexclaw-prd.md:1)
- Orchestrator design: [`.agent/hexclaw-orchestrator.md`](../.agent/hexclaw-orchestrator.md:1)
- Install guide: [`INSTALL.md`](../INSTALL.md:1) (Kali Linux WSL specific)
- README: [`README.md`](../README.md:1) (comprehensive but 750+ lines)

## Key Configuration Files
- `.env`: Environment variables (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, REDIS_URL, etc.)
- `requirements.txt`: Python dependencies (150+ external tools must be installed separately)
- `hexstrike-ai-mcp.json`: MCP client configuration for AI agents

## Hidden Dependencies
- Redis server is optional but required for semantic caching
- PostgreSQL is optional for persistent storage
- Chrome/Chromium + ChromeDriver required for selenium automation
- 150+ external security tools (nmap, nuclei, amass, etc.) must be installed separately

## Workflow Execution Flow
1. User sends goal to Telegram bot or daemon
2. [`planner.py`](../planner.py:1) translates goal to skill selection
3. [`daemon.py`](../daemon.py:1) enqueues job to SQLite queue
4. Daemon runs skill steps from YAML in [`skills/`](../skills/)
5. Each step calls MCP tools via HTTP to hexstrike_server.py
6. Results stored as Parquet files in [`data/`](../data/)
7. Telegram notifications sent on completion/error

## Data Persistence Patterns
- Jobs: SQLite at [`data/jobs.db`](../data/jobs.db)
- Token usage: SQLite at [`data/token_log.db`](../data/token_log.db)
- Findings: Parquet files in [`data/`](../data/) (e.g., `test_job_001/vulns.parquet`)
- Analytics: DuckDB in-memory (no persistence)
- Cache: Redis (DB 0 for exact, DB 1 for semantic)
