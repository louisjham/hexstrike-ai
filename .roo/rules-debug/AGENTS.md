# Project Debug Rules (Non-Obvious Only)

## Debug Mode Flags
- `python3 hexstrike_server.py --debug` for verbose logging
- `python3 hexstrike_mcp.py --debug` for MCP client debugging
- `python3 monitor.py --test-alert` for monitor pipeline verification

## Log Locations
- Daemon logs: [`logs/daemon.log`](../logs/daemon.log)
- Monitor logs: [`logs/monitor.log`](../logs/monitor.log)
- Server logs: `hexstrike.log` (in project root)
- Extension Host output channel (for VSCode integration)

## Common Debugging Issues

### MCP Connection Failed
```bash
# Check if server is running
netstat -tlnp | grep 8888

# Verify health endpoint
curl http://127.0.0.1:8888/health
```

### Redis Connection Issues
- Check Redis is running: `redis-cli ping` (should return PONG)
- Verify REDIS_URL in .env (default: redis://localhost:6379/0)
- Semantic cache uses DB 1, exact match uses DB 0

### Database Issues
- Jobs DB: [`data/jobs.db`](../data/jobs.db) - check SQLite permissions
- Token Log DB: [`data/token_log.db`](../data/token_log.db) - check SQLite permissions
- DuckDB: In-memory only, no persistent file

### Telegram Bot Issues
- Verify TELEGRAM_BOT_TOKEN in .env
- Verify TELEGRAM_CHAT_ID (must be integer, not string)
- Check `logs/daemon.log` for Telegram connection errors

## Silent Failure Points
- IPC messages in telegram.py fail silently if not wrapped in try/catch
- Cache check() returns None on miss (not False) - check with `if hit:` not `if hit is not None:`
- inference.ask() returns empty dict on failure (check `if not response:`)

## Required Environment Variables for Debugging
- `TELEGRAM_BOT_TOKEN` - Required for daemon.py
- `TELEGRAM_CHAT_ID` - Required for daemon.py
- `REDIS_URL` - Optional but recommended
- `GOOGLE_API_KEY` - Required for LLM planner
- `HEXSTRIKE_PORT` - Default: 8888
- `HEXSTRIKE_HOST` - Default: 127.0.0.1

## Monitor Debug Modes
- `--once`: Single pass then exit (useful for cron)
- `--dry-run`: Log alerts but don't send Telegram or write DB
- `--test-alert`: Fire synthetic test alert to verify pipeline

## Daemon Job Queue Debugging
- Jobs stored in SQLite at [`data/jobs.db`](../data/jobs.db)
- Status values: 'pending', 'running', 'done', 'failed', 'cancelled'
- Query jobs: `sqlite3 data/jobs.db "SELECT * FROM jobs;"`
