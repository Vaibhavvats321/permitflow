"""
app/api/auth.py

Authentication routes.

  POST /auth/login  email + password -> JWT
  GET  /auth/me     the authenticated principal

Login is the only place in the application that reads a user row outside its
tenant's RLS context. That is necessary because the tenant is not yet known
before authentication, and is done through the `get_user_by_email` SECURITY
DEFINER function, which is owned by the schema owner, returns only the four
fields required to verify a credential, and is not executable by PUBLIC.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.models import UserRole
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# Shared with the authentication dependencies so that "unknown account" and
# "wrong password" are indistinguishable to a caller.
_INVALID_CREDENTIALS_DETAIL = "Could not validate credentials"


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_INVALID_CREDENTIALS_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """
    Exchange email and password for an access token.

    Runs on a plain session with no tenant context: the tenant is unknown until
    a credential is verified. Row lookup therefore goes through the
    get_user_by_email function rather than the users table, which RLS would
    otherwise hide.
    """
    # Emails are stored lowercase (see api/seed.py), so normalise on the way in.
    # Otherwise a user typing "User@Example.com" would be told their account is
    # unknown even though it exists.
    email = str(payload.email).strip().lower()

    row = db.execute(
        text("SELECT id, password_hash, tenant_id, role FROM public.get_user_by_email(:email)"),
        {"email": email},
    ).mappings().first()

    # Verify the password even when the account is unknown, so the response
    # time does not reveal whether the email exists.
    stored_hash = row["password_hash"] if row is not None else _DUMMY_HASH

    if not verify_password(payload.password, stored_hash) or row is None:
        raise _unauthorized()

    try:
        role = UserRole.parse(row["role"])
    except ValueError:
        # A role value that cannot be mapped is unusable; do not fail open.
        raise _unauthorized() from None

    token = create_access_token(
        sub=row["id"],
        tenant_id=row["tenant_id"],
        role=role.value,
    )

    return LoginResponse(access_token=token, role=role, tenant_id=row["tenant_id"])


@router.get("/me", response_model=UserResponse)
def read_current_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> UserResponse:
    """
    Return the authenticated user.

    Deliberately has no role check: every authenticated role may inspect its
    own identity. Role gating belongs on the routes that need it via
    require_role.
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        tenant_id=current_user.tenant_id,
        agency_id=current_user.agency_id,
    )


# A real Argon2 hash of an unguessable value, computed once at import. Verifying
# against it costs roughly the same as verifying a genuine account, which keeps
# the unknown-email path from being measurably faster than the wrong-password
# path and leaking which addresses are registered.
_DUMMY_HASH = hash_password("permitflow-timing-equaliser-not-a-real-account")
