"""
cache.py

WHY THIS FILE EXISTS:
Every call to generate_sql() currently hits the Gemini API, even if someone
asks the exact same question twice in a row. That's slower than necessary
and burns through your free-tier quota for no reason. This file adds a
Redis-backed cache: if we've already generated SQL for this exact
(question, database) pair, return the cached result instantly instead of
calling Gemini again.

WHY WE HASH THE CACHE KEY (instead of using the raw question + connection
string as the key):
The connection string contains a plaintext DB password. Using it directly
as a Redis key would mean that password sits in Redis in a readable key
name, visible to anyone who can inspect Redis (e.g. via the `KEYS *` command
or Kafka UI-style tools). Hashing collapses it into a fixed-length,
non-reversible string, which functions perfectly as a cache key without
ever exposing the original secret.

WHY REDIS SPECIFICALLY (not just an in-memory Python dict):
An in-memory dict would reset every time the service restarts (which
happens constantly during development, since we run with --reload), and
wouldn't be shared if we ever ran multiple instances of this service. Redis
persists independently of this process and is designed exactly for this
"fast key-value cache" use case -- which is also why it's already sitting in
our docker-compose.yml from Phase 1.
"""

import hashlib
import json
import os

import redis

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
CACHE_TTL_SECONDS = 60 * 60 * 24  # 24 hours -- schemas/data can change, so we don't cache forever

# WHY decode_responses=True: without it, Redis returns raw bytes (b"...")
# instead of normal Python strings, which is annoying to work with everywhere
# else in this file. This makes get/set behave like a normal string-based dict.
_redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def _build_cache_key(question: str, connection_string: str) -> str:
    """
    Builds a stable, non-reversible cache key from the question + which
    database it's asked against. SHA-256 gives us a fixed-length hex string
    regardless of input length, and the same input always produces the same
    hash -- which is exactly the property a cache key needs.
    """
    raw = f"{question.strip().lower()}::{connection_string}"
    return "nlsql:" + hashlib.sha256(raw.encode()).hexdigest()


def get_cached_result(question: str, connection_string: str) -> dict | None:
    """
    Looks up a cached result. Returns the cached dict if found, or None if
    this question hasn't been asked before (a real "cache miss").
    """
    key = _build_cache_key(question, connection_string)
    cached_value = _redis_client.get(key)

    if cached_value is None:
        return None

    return json.loads(cached_value)


def store_result(question: str, connection_string: str, result: dict) -> None:
    """
    Stores a result in the cache with an expiry (TTL). We use setex (SET with
    EXpiry) rather than a plain set, specifically so stale data can't live
    forever if the underlying database schema or data changes later.
    """
    key = _build_cache_key(question, connection_string)
    _redis_client.setex(key, CACHE_TTL_SECONDS, json.dumps(result))