"""Opaque access tokens for class-management magic links.

A manage token is 24 random bytes (~192 bits) from ``secrets``.  Only
its SHA-256 hash is stored, so a database leak cannot hand out
moderation rights.  Plain SHA-256 (no salt, no KDF) is correct here:
salting/stretching defend *low-entropy* secrets like passwords against
brute force; a 192-bit random token has no brute-force surface, and a
fast hash keeps per-request lookup cheap.  Comparison is constant-time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

TOKEN_BYTES = 24


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), stored_hash)
