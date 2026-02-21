# Project Coding Rules (Non-Obvious Only)

## Path Management (MANDATORY)
All modules MUST import shared paths from [`config.py`](../config.py:1):
- `ROOT`, `DATA_DIR`, `LOG_DIR`, `SKILLS_DIR`, `JOBS_DB`, `TOKEN_LOG_DB`
- These directories are auto-created on first import

## Token Saving (PRD Rule: Cache > Rules > LLM)
Before calling [`inference.ask()`](../inference.py:98), ALWAYS call [`cache.check()`](../cache.py:130) first:
```python
from cache import Cache
c = Cache()
hit = c.check(prompt)
if hit:
    return hit  # 0 tokens consumed
response = await inference.ask(prompt)
c.store(prompt, response)
```

## Import Patterns
- Use `from __future__ import annotations` for async modules (daemon.py, monitor.py, telegram.py, cache.py)
- Use `from dotenv import load_dotenv` at module level for .env access
- Optional imports wrapped in try/except (e.g., sentence-transformers in cache.py)

## Database Access Patterns
- Jobs DB: Use [`JOBS_DB`](../config.py:18) constant for path
- Token Log DB: Use [`TOKEN_LOG_DB`](../config.py:19) constant for path
- Analytics: Use [`data.get_duck()`](../data.py:35) for DuckDB in-memory connection
- DuckDB SQLite attachment: Must call `INSTALL sqlite; LOAD sqlite;` and `ATTACH` before queries

## HexStrike Server Specifics
- The server file is 18k+ lines with embedded exploit templates
- API port configurable via `HEXSTRIKE_PORT` env var (default: 8888)
- Host configurable via `HEXSTRIKE_HOST` env var (default: 127.0.0.1)
- Health check endpoint: `GET /health`

## Async Module Patterns
- Async modules (daemon.py, monitor.py, telegram.py) use `from __future__ import annotations`
- Use `asyncio.create_task()` for background tasks
- Use `asyncio.Future` for approval gates in telegram.py

## Skill YAML Structure
Skills in [`skills/`](../skills/) must follow this exact structure:
```yaml
name: skill_name
steps:
  - tool: mcp_tool_name
    input: context_key      # optional
    output: context_key     # required
    on_fail: continue|abort  # default: continue
    notify: always|on_error|never  # default: always
    gate: none|approve    # default: none
```

## Provider Tier Selection
- Use `inference.ask()` with `complexity` parameter: "low", "med", "high"
- Low tier: ollama/llama3 (free)
- Med tier: openrouter/granite-3.1, zhipuai/glm-4
- High tier: gemini/gemini-2.0-flash-exp, openrouter/granite-3.1

## Cache Backend Fallback
- Primary: Redis (sentence-transformers for embeddings)
- Fallback: numpy n-gram embeddings (lightweight, always available)
- Last resort: No semantic cache (exact match only)
