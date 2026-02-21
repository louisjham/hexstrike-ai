# Project Architecture Rules (Non-Obvious Only)

## Hidden Coupling Between Components

### Daemon-Specific Coupling
- [`daemon.py`](../daemon.py:1) requires `telegram.py` to register callbacks at startup
- [`telegram.py`](../telegram.py:1) imports from `config` but depends on daemon to register enqueue/status/orchestrate callbacks
- This circular dependency is resolved by callback registration pattern in daemon.py

### Cache-Inference Coupling
- [`cache.py`](../cache.py:1) must be called before [`inference.ask()`](../inference.py:98) for token efficiency
- This is a PRD requirement (Cache > Rules > LLM) - not optional

### Data-Daemon Coupling
- [`data.py`](../data.py:1) DuckDB connection is in-memory only
- Parquet files must be stored via `data.store_parquet()` before analytics can query them
- DuckDB attaches SQLite databases dynamically via `ATTACH` commands

## Undocumented Architectural Decisions

### Two-Tier Cache System
- Tier 1: Exact match (Redis DB 0) - SHA256 hash of prompt
- Tier 2: Semantic match (Redis DB 1) - Embeddings with cosine similarity
- Fallback: numpy n-gram embeddings if sentence-transformers unavailable
- This design enables 0-token responses for similar prompts

### Provider Tiering Strategy
- Low tier: Free models (ollama/llama3) for planning
- Med tier: Mid-cost models (openrouter/granite-3.1, zhipuai/glm-4)
- High tier: Premium models (gemini/gemini-2.0-flash-exp) for complex logic
- Token logging happens at all tiers in SQLite

### Job Queue Design
- SQLite-based queue in [`data/jobs.db`](../data/jobs.db)
- Heartbeat poll pattern (daemon.py) rather than push notifications
- Status transitions: pending → running → done/failed/cancelled
- No rollback capability (forward-only by design)

## Non-Standard Patterns That Must Be Followed

### YAML Skill Structure
Skills in [`skills/`](../skills/) must follow exact structure:
- `tool`: MCP tool name (maps to daemon.py TOOL_ENDPOINT_MAP)
- `input`: Context key to read from (optional)
- `output`: Parquet filename or context key to write to
- `on_fail`: "continue" or "abort" (default: continue)
- `notify`: "always", "on_error", or "never" (default: always)
- `gate`: "none" or "approve" (default: none)

### Telegram Approval Gates
- Approval gates use asyncio.Future objects in [`telegram.py`](../telegram.py:1)
- `_pending_approvals` dict maps approval_id to Future
- Daemon awaits Future for operator confirmation
- This enables 0-inference human-in-the-loop

### Path Centralization
- All paths MUST come from [`config.py`](../config.py:1)
- Direct path references in code will break on different environments
- Directories auto-created on first import: DATA_DIR, LOG_DIR, SKILLS_DIR

## Performance Bottlenecks Discovered Through Investigation

### HexStrike Server Size
- 18k+ lines in single file ([`hexstrike_server.py`](../hexstrike_server.py:1))
- Embedded exploit templates increase memory footprint
- Consider splitting into modules for maintainability

### DuckDB SQLite Attachment
- Every query requires `INSTALL sqlite; LOAD sqlite; ATTACH ...`
- This overhead is significant for frequent queries
- Consider materializing frequently accessed tables

### Redis Dependency
- Without Redis, semantic cache is disabled (fallback to exact match only)
- This increases token consumption significantly
- Redis is optional but strongly recommended

## Architecture Constraints

### Async Module Requirements
- Use `from __future__ import annotations` for type hints
- All async functions must be awaitable
- Use asyncio.create_task() for concurrent operations

### Database Schema Constraints
- Jobs table: fixed schema (id, skill, params, status, target, timestamps, result, error)
- Token log table: fixed schema (id, provider, model, tier, tokens_in, tokens_out, cost, created_at)
- No migrations, no schema versioning (forward-only)

### MCP Tool Registration
- Tools defined in hexstrike_server.py as Flask routes
- Mapped in daemon.py TOOL_ENDPOINT_MAP
- New tools require both server endpoint and daemon mapping

## Communication Protocols

### Daemon → Server
- HTTP POST to MCP server endpoints
- JSON payload with params
- Response contains tool output

### Telegram ↔ Daemon
- Callback registration pattern (not direct imports)
- Asyncio.Future for approval gates
- Inline keyboard buttons for 0-inference choices

### Monitor → Daemon
- Monitor runs as asyncio task within daemon
- Notifier pattern for Telegram delivery
- Best-effort Postgres write-back (optional)
