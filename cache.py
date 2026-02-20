"""
HexClaw — cache.py
==================
Two-tier inference cache sitting in front of every LLM call.

Tier 1 — Exact match (Redis, DB 0)
  Key   : "exact:{sha256(prompt)}"
  Value : JSON-serialised LLM response string
  TTL   : CACHE_EXACT_TTL seconds (default 86400 — 1 day)

Tier 2 — Semantic match (Redis, DB 1)
  Stores prompt embeddings as Redis hash fields.
  On lookup, computes cosine similarity against all stored embeddings
  and returns the cached response if similarity ≥ CACHE_SEMANTIC_THRESHOLD.
  Embedding generation: uses numpy only (dot-product on character n-gram
  frequency vector) when sentence-transformers not available, so the cache
  works without heavy ML deps.

PRD constraint: Rules/cache > LLM
  Always call check() before inference.ask(). If a hit is returned, skip
  the LLM entirely.

Usage:
    from cache import Cache

    c = Cache()
    hit = c.check(prompt)
    if hit:
        return hit          # 0 tokens consumed

    response = await llm_call(prompt)
    c.store(prompt, response)
    return response
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("hexclaw.cache")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_SEMANTIC_DB: int = int(os.getenv("REDIS_SEMANTIC_DB", "1"))

CACHE_EXACT_TTL: int = int(os.getenv("CACHE_EXACT_TTL", str(86_400)))       # 1 day
CACHE_SEMANTIC_TTL: int = int(os.getenv("CACHE_SEMANTIC_TTL", str(604_800))) # 7 days
CACHE_SEMANTIC_THRESHOLD: float = float(os.getenv("CACHE_SEMANTIC_THRESHOLD", "0.92"))
CACHE_SEMANTIC_MAX_ENTRIES: int = int(os.getenv("CACHE_SEMANTIC_MAX_ENTRIES", "2000"))

# Embedding dimension when using the lightweight built-in encoder
_EMBED_DIM = 256

# ─────────────────────────────────────────────────────────────────────────────
# Embedding backends (in priority order)
# ─────────────────────────────────────────────────────────────────────────────

_EMBED_BACKEND: str = "none"  # set during _init_embedder()
_embed_model: Any = None


def _init_embedder() -> None:
    """Detect best available embedding backend at import time."""
    global _EMBED_BACKEND, _embed_model

    # Option A — sentence-transformers (best quality, heavy)
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        _EMBED_BACKEND = "sentence_transformers"
        log.debug("Embedding backend: sentence-transformers (all-MiniLM-L6-v2)")
        return
    except ImportError:
        pass

    # Option B — numpy char n-gram (lightweight, always available after pip install numpy)
    try:
        import numpy  # noqa: F401
        _EMBED_BACKEND = "ngram_numpy"
        log.debug("Embedding backend: n-gram/numpy (lightweight)")
        return
    except ImportError:
        pass

    # Option C — pure Python fallback (no cosine similarity, semantic cache disabled)
    _EMBED_BACKEND = "none"
    log.warning("No embedding backend available — semantic cache disabled")


_init_embedder()


def _embed(text: str) -> list[float] | None:
    """
    Produce a fixed-length embedding vector for *text*.
    Returns None when no backend is available (semantic cache disabled).
    """
    if _EMBED_BACKEND == "sentence_transformers":
        vec = _embed_model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    if _EMBED_BACKEND == "ngram_numpy":
        return _ngram_embed(text)

    return None


def _ngram_embed(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """
    Lightweight character trigram frequency vector, L2-normalised.
    No external ML deps — only numpy required.
    """
    import numpy as np

    text = text.lower()[:2048]  # cap for speed
    vec = np.zeros(dim, dtype=np.float32)

    # Hash each trigram into one of the dim buckets
    for i in range(len(text) - 2):
        trigram = text[i:i+3]
        bucket = int(hashlib.md5(trigram.encode()).hexdigest(), 16) % dim
        vec[bucket] += 1.0

    # L2 norm
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec.tolist()


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    import numpy as np
    va, vb = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


# ─────────────────────────────────────────────────────────────────────────────
# Redis connection pool
# ─────────────────────────────────────────────────────────────────────────────

def _make_redis(db_override: int | None = None):
    """Return a Redis client, or None if Redis is unavailable."""
    try:
        import redis as redis_lib
        from urllib.parse import urlparse

        parsed = urlparse(REDIS_URL)
        db = db_override if db_override is not None else (int(parsed.path.lstrip("/")) if parsed.path.lstrip("/") else 0)

        client = redis_lib.Redis(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            db=db,
            password=parsed.password or None,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()  # fail fast
        return client
    except Exception as exc:
        log.debug("Redis unavailable (%s) — cache operating in no-op mode", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Cache class
# ─────────────────────────────────────────────────────────────────────────────

class Cache:
    """
    Two-tier inference cache.

    All public methods are synchronous for simplicity — Redis calls are
    fast enough (<1 ms local) that async overhead is not warranted here.
    Wrap in asyncio.to_thread() if needed from async contexts.

    Methods:
        check(prompt)           → str | None   (hit = 0 tokens spent)
        store(prompt, response) → None
        stats()                 → dict
        flush_exact()           → int           (number of keys deleted)
        flush_semantic()        → int
    """

    def __init__(self) -> None:
        self._r_exact = _make_redis(db_override=None)           # DB 0 (exact)
        self._r_sem   = _make_redis(db_override=REDIS_SEMANTIC_DB)  # DB 1 (semantic)
        self._hits_exact = 0
        self._hits_semantic = 0
        self._misses = 0

    # ── Public API ────────────────────────────────────────────────────────

    def check(self, prompt: str) -> str | None:
        """
        Check both cache tiers for *prompt*.

        Returns the cached response string on hit, None on miss.
        PRD rule: always call this before inference.ask().
        """
        # Tier 1 — exact
        result = self._check_exact(prompt)
        if result is not None:
            self._hits_exact += 1
            log.debug("Cache HIT (exact): %.60s...", prompt)
            return result

        # Tier 2 — semantic
        result = self._check_semantic(prompt)
        if result is not None:
            self._hits_semantic += 1
            log.debug("Cache HIT (semantic): %.60s...", prompt)
            # Promote to exact cache for future identical calls
            self._store_exact(prompt, result)
            return result

        self._misses += 1
        log.debug("Cache MISS: %.60s...", prompt)
        return None

    def store(self, prompt: str, response: str) -> None:
        """
        Store a (prompt, response) pair in both tiers.
        Call this after every successful LLM response.
        """
        self._store_exact(prompt, response)
        self._store_semantic(prompt, response)

    def stats(self) -> dict[str, Any]:
        """Return runtime statistics (no Redis calls)."""
        total = self._hits_exact + self._hits_semantic + self._misses
        hit_rate = round((self._hits_exact + self._hits_semantic) / total, 3) if total else 0.0
        return {
            "hits_exact":    self._hits_exact,
            "hits_semantic": self._hits_semantic,
            "misses":        self._misses,
            "total":         total,
            "hit_rate":      hit_rate,
            "embed_backend": _EMBED_BACKEND,
            "redis_exact":   self._r_exact is not None,
            "redis_semantic": self._r_sem is not None,
        }

    def flush_exact(self) -> int:
        """Delete all exact-cache keys. Returns count deleted."""
        if self._r_exact is None:
            return 0
        keys = self._r_exact.keys("exact:*")
        if keys:
            return self._r_exact.delete(*keys)
        return 0

    def flush_semantic(self) -> int:
        """Delete all semantic-cache keys. Returns count deleted."""
        if self._r_sem is None:
            return 0
        count = 0
        for key in self._r_sem.scan_iter("sem:embed:*"):
            self._r_sem.delete(key)
            count += 1
        self._r_sem.delete("sem:index")
        return count

    # ── Exact tier ────────────────────────────────────────────────────────

    def _exact_key(self, prompt: str) -> str:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return f"exact:{digest}"

    def _check_exact(self, prompt: str) -> str | None:
        if self._r_exact is None:
            return None
        try:
            val = self._r_exact.get(self._exact_key(prompt))
            return val  # str | None (decode_responses=True)
        except Exception as exc:
            log.debug("Exact cache get error: %s", exc)
            return None

    def _store_exact(self, prompt: str, response: str) -> None:
        if self._r_exact is None:
            return
        try:
            self._r_exact.setex(self._exact_key(prompt), CACHE_EXACT_TTL, response)
        except Exception as exc:
            log.debug("Exact cache set error: %s", exc)

    # ── Semantic tier ─────────────────────────────────────────────────────

    def _check_semantic(self, prompt: str) -> str | None:
        if self._r_sem is None or _EMBED_BACKEND == "none":
            return None

        query_vec = _embed(prompt)
        if query_vec is None:
            return None

        try:
            # Load index: list of (entry_id, stored_prompt_hash→response)
            index_ids: list[str] = self._r_sem.lrange("sem:index", 0, -1)
            if not index_ids:
                return None

            best_sim = 0.0
            best_entry_id: str | None = None

            for entry_id in index_ids:
                embed_raw = self._r_sem.hget(f"sem:embed:{entry_id}", "vec")
                if embed_raw is None:
                    continue
                stored_vec: list[float] = json.loads(embed_raw)
                sim = _cosine(query_vec, stored_vec)
                if sim > best_sim:
                    best_sim = sim
                    best_entry_id = entry_id

            if best_sim >= CACHE_SEMANTIC_THRESHOLD and best_entry_id:
                response = self._r_sem.hget(f"sem:embed:{best_entry_id}", "response")
                log.debug(
                    "Semantic hit (sim=%.3f, threshold=%.3f): %.50s...",
                    best_sim, CACHE_SEMANTIC_THRESHOLD, prompt,
                )
                return response

        except Exception as exc:
            log.debug("Semantic cache check error: %s", exc)

        return None

    def _store_semantic(self, prompt: str, response: str) -> None:
        if self._r_sem is None or _EMBED_BACKEND == "none":
            return

        vec = _embed(prompt)
        if vec is None:
            return

        try:
            # Enforce max entries (evict oldest = leftmost in index list)
            index_len = self._r_sem.llen("sem:index")
            if index_len >= CACHE_SEMANTIC_MAX_ENTRIES:
                old_id = self._r_sem.lpop("sem:index")
                if old_id:
                    self._r_sem.delete(f"sem:embed:{old_id}")

            entry_id = hashlib.sha256(f"{prompt}{time.time()}".encode()).hexdigest()[:16]
            self._r_sem.hset(f"sem:embed:{entry_id}", mapping={
                "vec":      json.dumps(vec),
                "response": response,
                "prompt":   prompt[:200],
            })
            self._r_sem.expire(f"sem:embed:{entry_id}", CACHE_SEMANTIC_TTL)
            self._r_sem.rpush("sem:index", entry_id)

        except Exception as exc:
            log.debug("Semantic cache store error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton (shared across all callers in the process)
# ─────────────────────────────────────────────────────────────────────────────

_cache_instance: Cache | None = None


def get_cache() -> Cache:
    """Return the process-wide Cache singleton."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = Cache()
    return _cache_instance


# ── Convenience wrappers ──────────────────────────────────────────────────────

def check(prompt: str) -> str | None:
    """Module-level shortcut: get_cache().check(prompt)."""
    return get_cache().check(prompt)


def get(prompt: str, thresh: float = 0.95) -> str | None:
    """PRD compliant alias for check()."""
    # Note: Threshold override logic could be added to Cache.check if needed.
    return get_cache().check(prompt)


def store(prompt: str, response: str) -> None:
    """Module-level shortcut: get_cache().store(prompt, response)."""
    get_cache().store(prompt, response)


def set(prompt: str, response: str) -> None:
    """PRD compliant alias for store()."""
    get_cache().store(prompt, response)


# ─────────────────────────────────────────────────────────────────────────────
# CLI self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    c = Cache()
    print(f"Embed backend : {_EMBED_BACKEND}")
    print(f"Redis exact   : {c._r_exact is not None}")
    print(f"Redis semantic: {c._r_sem is not None}")

    if c._r_exact is None:
        print("[INFO] Redis not available -- skipping round-trip test (install Redis to enable caching)")
        print("\nStats:", c.stats())
        raise SystemExit(0)

    # Exact round-trip
    p1 = "What is the capital of France?"
    r1 = "Paris."
    c.store(p1, r1)
    result = c.check(p1)
    if result == r1:
        print("[OK] Exact cache round-trip OK")
    else:
        print(f"[FAIL] Exact cache miss after store! Got: {result!r}")

    # Semantic round-trip (similar but not identical prompt)
    p2 = "Tell me the capital city of France?"
    hit = c.check(p2)
    if _EMBED_BACKEND != "none":
        if hit:
            print(f"[OK] Semantic cache hit for similar prompt: '{hit}'")
        else:
            print("[INFO] Semantic miss (similarity below threshold -- expected for short prompts)")
    else:
        print("[INFO] Semantic cache skipped (no embedding backend)")

    print("\nStats:", c.stats())
