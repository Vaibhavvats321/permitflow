"""
app/core/security.py

Self-contained authentication utilities.
No database imports. No route imports.

Provides:
  - hash_password(plain: str) -> str
  - verify_password(plain: str, hashed: str) -> bool
  - create_access_token(sub, tenant_id, role) -> str
  - decode_access_token(token: str) -> dict   (raises on invalid/expired)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing — Argon2 via pwdlib
# ---------------------------------------------------------------------------

_pwd_hasher = PasswordHash([Argon2Hasher()])


def hash_password(plain: str) -> str:
    """Return an Argon2 hash of *plain*."""
    return _pwd_hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*; False otherwise."""
    return _pwd_hasher.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT — PyJWT
# ---------------------------------------------------------------------------

_ALGORITHM = settings.JWT_ALGORITHM
_SECRET = settings.JWT_SECRET
_EXPIRE_MINUTES = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES


def create_access_token(
    *,
    sub: uuid.UUID | str,
    tenant_id: uuid.UUID | str,
    role: str,
) -> str:
    """
    Create a signed JWT access token.

    Claims:
      sub        — user UUID (string)
      tenant_id  — tenant UUID (string)
      role       — UserRole value (string)
      exp        — expiry timestamp (UTC)
      iat        — issued-at timestamp (UTC)
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(sub),
        "tenant_id": str(tenant_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT access token.

    Raises:
      jwt.ExpiredSignatureError  — token has expired
      jwt.InvalidTokenError      — token is malformed or signature invalid
    """
    return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
