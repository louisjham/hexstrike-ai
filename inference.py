"""
HexClaw — inference.py
======================
Thrifty LLM inference with provider tiering, rotation, and token logging.

PRD rules enforced here:
  • Rules/cache > LLM        — always check cache.check() first (callers do this;
                               ask() asserts it for dev discipline)
  • Free/low tier            — status/plan tasks use LOW or FREE providers
  • High tier = google_pro   — only for tasks that genuinely need it
  • Token log to SQLite      — every call (hit or miss) logged to data/token_log.db

Provider tiers:
  HIGH   → gemini/gemini-1.5-pro   (best reasoning, costs most)
  LOW    → openrouter/mistralai/mistral-7b-instruct  (cheap, good enough)
  FREE   → openrouter/mistralai/mistral-7b-instruct:free  (0 cost, rate limited)

Rotation:
  If the primary provider fails (rate limit, quota, network), the next
  provider in the tier's rotation list is tried automatically.
  All providers share the same LiteLLM interface.

Usage:
    from inference import ask, ask_sync

    # Async (preferred — use from daemon/skills)
    response = await ask("Summarise these findings: ...", tier="low")

    # Sync (use from CLI tools / scripts)
    response = ask_sync("What ports are risky?", tier="free")

    # Force high-quality reasoning
    response = await ask("Prioritise and explain these CVEs: ...", tier="high")

Token log:
    All calls are recorded to data/token_log.db:
      provider, model, tokens_in, tokens_out, cost_usd, cache_hit, created_at
    Read via /stats Telegram command (zero inference).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

import cache as cache_module

log = logging.getLogger("hexclaw.inference")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.resolve()
TOKEN_LOG_DB = ROOT / "data" / "token_log.db"

# Provider strings (LiteLLM format: "provider/model-name")
PROVIDER_HIGH: str  = os.getenv("LITELLM_PROVIDER_HIGH", "gemini/gemini-1.5-pro")
PROVIDER_LOW: str   = os.getenv("LITELLM_PROVIDER_LOW",  "openrouter/mistralai/mistral-7b-instruct")
PROVIDER_FREE: str  = os.getenv("LITELLM_PROVIDER_FREE", "openrouter/mistralai/mistral-7b-instruct:free")

# Rotation lists: if index 0 fails, try index 1, etc.
PROVIDERS: dict[str, list[str]] = {
    "high": [
        PROVIDER_HIGH,
        "openrouter/google/gemini-pro",                        # fallback
        PROVIDER_LOW,                                          # last resort
    ],
    "low": [
        PROVIDER_LOW,
        PROVIDER_FREE,
        "openrouter/meta-llama/llama-3-8b-instruct:free",     # free fallback
    ],
    "free": [
        PROVIDER_FREE,
        "openrouter/meta-llama/llama-3-8b-instruct:free",
        "openrouter/mistralai/mistral-7b-instruct",            # paid if free exhausted
    ],
}

# Cost estimates per 1M tokens (input / output) in USD
# Used when the LiteLLM response doesn't include cost info.
COST_PER_1M: dict[str, tuple[float, float]] = {
    "gemini/gemini-1.5-pro":                                  (3.50,  10.50),
    "openrouter/google/gemini-pro":                           (0.50,   1.50),
    "openrouter/mistralai/mistral-7b-instruct":               (0.07,   0.07),
    "openrouter/mistralai/mistral-7b-instruct:free":          (0.00,   0.00),
    "openrouter/meta-llama/llama-3-8b-instruct:free":         (0.00,   0.00),
}

# Max tokens per request per tier
MAX_TOKENS: dict[str, int] = {
    "high": 4096,
    "low":  2048,
    "free": 1024,
}

# Retry config
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.5  # seconds; exponential

# ─────────────────────────────────────────────────────────────────────────────
# LiteLLM availability
# ─────────────────────────────────────────────────────────────────────────────

try:
    import litellm as _litellm_lib  # type: ignore
    _litellm_lib.drop_params = True      # ignore unsupported params per provider
    _litellm_lib.set_verbose = False
    LITELLM_AVAILABLE = True

    # Inject API keys from env into litellm's config
    _google_key = os.getenv("GOOGLE_API_KEY", "")
    _openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if _google_key:
        _litellm_lib.api_key = _google_key          # Gemini default
    if _openrouter_key:
        os.environ.setdefault("OPENROUTER_API_KEY", _openrouter_key)

except ImportError:
    _litellm_lib = None  # type: ignore[assignment]
    LITELLM_AVAILABLE = False
    log.warning("litellm not installed — inference will return stub responses")


# ─────────────────────────────────────────────────────────────────────────────
# Token log (SQLite)
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_token_log() -> None:
    """Create the token_log table if it doesn't exist."""
    TOKEN_LOG_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(TOKEN_LOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            provider    TEXT,
            model       TEXT,
            tokens_in   INTEGER,
            tokens_out  INTEGER,
            cost_usd    REAL,
            cache_hit   INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


_ensure_token_log()


def _log_tokens(
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    cache_hit: bool = False,
) -> None:
    """Write one inference record to the SQLite token log."""
    try:
        conn = sqlite3.connect(TOKEN_LOG_DB)
        conn.execute(
            """
            INSERT INTO token_log (provider, model, tokens_in, tokens_out, cost_usd, cache_hit)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (provider, model, tokens_in, tokens_out, round(cost_usd, 8), int(cache_hit)),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        log.debug("Token log write failed: %s", exc)


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate cost in USD using the COST_PER_1M table."""
    for key, (cost_in, cost_out) in COST_PER_1M.items():
        if key in model:
            return (tokens_in * cost_in + tokens_out * cost_out) / 1_000_000
    # Unknown model — assume zero to avoid false accounting
    return 0.0


def get_usage_summary() -> dict[str, Any]:
    """
    Return aggregated token usage from SQLite.
    Used by /stats command (zero inference).
    """
    try:
        conn = sqlite3.connect(TOKEN_LOG_DB)
        rows = conn.execute("""
            SELECT
                provider, model,
                COUNT(*)        AS calls,
                SUM(tokens_in)  AS tok_in,
                SUM(tokens_out) AS tok_out,
                SUM(cost_usd)   AS cost,
                SUM(cache_hit)  AS cache_hits
            FROM token_log
            GROUP BY provider, model
            ORDER BY cost DESC
        """).fetchall()
        conn.close()
        return {
            "by_model": [
                {
                    "provider":    r[0],
                    "model":       r[1],
                    "calls":       r[2],
                    "tokens_in":   r[3] or 0,
                    "tokens_out":  r[4] or 0,
                    "cost_usd":    round(r[5] or 0, 6),
                    "cache_hits":  r[6] or 0,
                }
                for r in rows
            ]
        }
    except Exception as exc:
        log.debug("Usage summary error: %s", exc)
        return {"by_model": []}


# ─────────────────────────────────────────────────────────────────────────────
# Core inference logic
# ─────────────────────────────────────────────────────────────────────────────

def _call_litellm(
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> tuple[str, int, int, float]:
    """
    Synchronous LiteLLM call.
    Returns (response_text, tokens_in, tokens_out, cost_usd).
    """
    if not LITELLM_AVAILABLE or _litellm_lib is None:
        # Stub for dev without API keys
        stub = f"[STUB: {model} — litellm not available]"
        return stub, 0, 0, 0.0

    response = _litellm_lib.completion(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    text: str = response.choices[0].message.content or ""

    usage = response.usage or {}
    tokens_in  = getattr(usage, "prompt_tokens",     0) or 0
    tokens_out = getattr(usage, "completion_tokens", 0) or 0

    # LiteLLM sometimes includes cost in response
    raw_cost = getattr(response, "_hidden_params", {}).get("response_cost")
    cost = float(raw_cost) if raw_cost else _estimate_cost(model, tokens_in, tokens_out)

    return text, tokens_in, tokens_out, cost


def _ask_with_rotation(
    prompt: str,
    tier: str,
    system: str | None,
    max_tokens: int,
    temperature: float,
) -> tuple[str, str, int, int, float]:
    """
    Try each provider in the tier's rotation list.
    Returns (response_text, model_used, tokens_in, tokens_out, cost_usd).
    Raises RuntimeError if all providers fail.
    """
    rotation = PROVIDERS.get(tier, PROVIDERS["low"])
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_exc: Exception | None = None

    for model in rotation:
        for attempt in range(MAX_RETRIES):
            try:
                log.debug("Calling %s (tier=%s attempt=%d)", model, tier, attempt + 1)
                text, tok_in, tok_out, cost = _call_litellm(
                    model, messages, max_tokens, temperature
                )
                return text, model, tok_in, tok_out, cost

            except Exception as exc:
                last_exc = exc
                wait = RETRY_BACKOFF_BASE ** attempt
                log.warning(
                    "Provider %s attempt %d failed: %s — retrying in %.1fs",
                    model, attempt + 1, exc, wait,
                )
                time.sleep(wait)
                continue  # next attempt

        log.warning("Provider %s exhausted retries — trying next provider", model)

    raise RuntimeError(
        f"All providers in tier '{tier}' failed. Last error: {last_exc}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def ask(
    prompt: str,
    tier: str = "low",
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    skip_cache: bool = False,
) -> str:
    """
    Async inference entry-point.

    PRD rule enforcement:
      1. Check cache first (unless skip_cache=True)
      2. Use the cheapest provider tier that satisfies the request
      3. Log every call to token_log.db

    Args:
        prompt:      The user message to send
        tier:        "high" | "low" | "free"  (default "low")
        system:      Optional system message
        temperature: Sampling temperature (lower = more deterministic)
        max_tokens:  Override per-tier default
        skip_cache:  Force a live LLM call (use sparingly)

    Returns:
        Response text string
    """
    if tier not in PROVIDERS:
        raise ValueError(f"Unknown tier '{tier}'. Must be one of: {list(PROVIDERS)}")

    effective_max_tokens = max_tokens or MAX_TOKENS.get(tier, 1024)
    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    # ── Tier 1/2 cache check ──────────────────────────────────────────────
    if not skip_cache:
        cached = cache_module.check(full_prompt)
        if cached is not None:
            _log_tokens(
                provider="cache",
                model="cache",
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                cache_hit=True,
            )
            return cached

    # ── Live LLM call (thread pool — don't block event loop) ─────────────
    try:
        text, model, tok_in, tok_out, cost = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _ask_with_rotation(
                prompt, tier, system, effective_max_tokens, temperature
            ),
        )
    except RuntimeError as exc:
        log.error("Inference failed for tier '%s': %s", tier, exc)
        return f"[Inference error: {exc}]"

    # ── Store in cache ────────────────────────────────────────────────────
    if not skip_cache:
        cache_module.store(full_prompt, text)

    # ── Log tokens ────────────────────────────────────────────────────────
    provider_name = model.split("/")[0] if "/" in model else model
    _log_tokens(
        provider=provider_name,
        model=model,
        tokens_in=tok_in,
        tokens_out=tok_out,
        cost_usd=cost,
        cache_hit=False,
    )

    log.info(
        "Inference: tier=%s model=%s in=%d out=%d cost=$%.6f",
        tier, model, tok_in, tok_out, cost,
    )
    return text


def ask_sync(
    prompt: str,
    tier: str = "low",
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    skip_cache: bool = False,
) -> str:
    """
    Synchronous wrapper around ask() for use in non-async contexts
    (CLI scripts, install hooks, etc.).
    """
    return asyncio.run(
        ask(
            prompt=prompt,
            tier=tier,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            skip_cache=skip_cache,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Specialised helpers (semantic shortcuts used by skills)
# ─────────────────────────────────────────────────────────────────────────────

VULN_PRIORITISE_SYSTEM = """You are a senior penetration tester.
Given a list of vulnerabilities, output a JSON array ranked by exploitability and impact.
Each item: {"rank": 1, "title": "...", "severity": "critical|high|medium|low", "reason": "..."}
Be concise. No prose outside the JSON array."""

SUGGEST_NEXT_SYSTEM = """You are an autonomous red-team agent.
Given partial recon results, suggest the 3 most valuable next scanning steps.
Output JSON: {"next_steps": ["...", "...", "..."]}
Each step must be a specific tool name + target. No prose outside JSON."""


async def prioritise_vulns(findings: list[dict], tier: str = "high") -> list[dict]:
    """
    Rank a list of findings by severity/exploitability using LLM.
    Returns sorted list (may be from cache).
    """
    if not findings:
        return []

    import json as _json

    prompt = _json.dumps(findings[:30], indent=2)  # cap to avoid token explosion
    raw = await ask(prompt, tier=tier, system=VULN_PRIORITISE_SYSTEM, temperature=0.1)

    try:
        # Strip markdown code fences if present
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return _json.loads(cleaned)
    except Exception:
        log.warning("prioritise_vulns: failed to parse LLM JSON response")
        return findings  # return original order on parse failure


async def suggest_next_steps(
    target: str,
    findings_summary: str,
    tier: str = "low",
) -> list[str]:
    """
    Suggest next scanning steps from a text summary of findings.
    Returns list of step strings (may be from cache).
    """
    import json as _json

    prompt = f"Target: {target}\n\nFindings summary:\n{findings_summary}"
    raw = await ask(prompt, tier=tier, system=SUGGEST_NEXT_SYSTEM, temperature=0.2)

    try:
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = _json.loads(cleaned)
        return data.get("next_steps", [])
    except Exception:
        log.warning("suggest_next_steps: failed to parse LLM JSON response")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# CLI self-test / usage display
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json as _json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="HexClaw inference CLI")
    parser.add_argument("--prompt", type=str, default=None, help="Send a test prompt")
    parser.add_argument("--tier",   type=str, default="low", choices=["high","low","free"])
    parser.add_argument("--stats",  action="store_true", help="Print token usage stats")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache for this call")
    args = parser.parse_args()

    if args.stats:
        summary = get_usage_summary()
        print(_json.dumps(summary, indent=2))

    elif args.prompt:
        print(f"Calling tier={args.tier} ...")
        result = ask_sync(
            prompt=args.prompt,
            tier=args.tier,
            skip_cache=args.no_cache,
        )
        print("\n─── Response ───")
        print(result)

    else:
        print("HexClaw inference.py")
        print(f"  LiteLLM available : {LITELLM_AVAILABLE}")
        print(f"  HIGH provider     : {PROVIDERS['high'][0]}")
        print(f"  LOW  provider     : {PROVIDERS['low'][0]}")
        print(f"  FREE provider     : {PROVIDERS['free'][0]}")
        print(f"  Token log DB      : {TOKEN_LOG_DB}")
        print(f"  Cache stats       : {cache_module.get_cache().stats()}")
        print()
        print("Run with --prompt 'your question' [--tier high|low|free]")
        print("Run with --stats to see token usage")
