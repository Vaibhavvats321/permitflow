"""
app/deps.py

FastAPI dependencies for authentication and tenant-scoped database access.

Layering:
  - core/security.py  owns JWT + password primitives (no DB, no HTTP)
  - db/session.py     owns connections and the RLS setting
  - deps.py           composes the two for route handlers

Tenant isolation relies on PostgreSQL Row Level Security. RLS policies read
`current_setting('app.current_tenant_id')`, so every database session used by an
authenticated request must establish that setting from the *verified* JWT
before any RLS-protected query runs. Nothing here trusts a client-supplied
tenant id, and there is no module-level tenant state.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models import User, UserRole

# auto_error=False so a missing header produces our own 401 message rather than
# FastAPI's generic one, keeping error responses consistent.
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TokenClaims:
    """Validated contents of an access token. Never contains secrets."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: UserRole


@dataclass(frozen=True)
class CurrentUser:
    """
    Authenticated principal exposed to routes.

    Deliberately a separate type from the ORM User so that `password_hash`
    cannot leak into a response by accident.
    """

    id: uuid.UUID
    email: str
    role: UserRole
    tenant_id: uuid.UUID
    agency_id: uuid.UUID | None


def _unauthorized() -> HTTPException:
    # Built per call so the exception instance is never shared across requests.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_token_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenClaims:
    """
    Extract, verify and structurally validate the bearer token.

    Raises 401 for a missing header, an undecodable or expired token, or a
    token missing any claim we require. Deliberately does not touch the
    database and does not distinguish "user does not exist" from "wrong
    password" — that check happens in get_current_user.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized()

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized() from None
    except jwt.InvalidTokenError:
        raise _unauthorized() from None

    sub = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role = payload.get("role")

    if not sub or not tenant_id or not role:
        raise _unauthorized()

    try:
        user_id = uuid.UUID(str(sub))
        parsed_tenant_id = uuid.UUID(str(tenant_id))
        parsed_role = UserRole(role)
    except (ValueError, TypeError):
        raise _unauthorized() from None

    return TokenClaims(user_id=user_id, tenant_id=parsed_tenant_id, role=parsed_role)


def _bind_tenant_to_transactions(session: Session, tenant_id: uuid.UUID) -> None:
    """
    Re-apply the tenant setting at the start of every transaction on `session`.

    SET LOCAL is discarded on COMMIT. A session that commits and then runs
    another query would silently see zero rows from RLS-protected tables, so we
    hook SQLAlchemy's after_begin event and set the value on each new
    transaction. The tenant id is captured in this closure, which is scoped to
    the request's own session — there is no shared or global tenant state.
    """

    @event.listens_for(session, "after_begin")
    def _set_tenant_on_begin(sess: Session, transaction, connection) -> None:
        connection.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )


def get_tenant_db(claims: TokenClaims = Depends(get_token_claims)) -> Iterator[Session]:
    """
    Yield a Session whose every transaction is scoped to the caller's tenant.

    Depends on get_token_claims, so a missing or invalid token fails with 401
    before any connection work happens. The session is rolled back and closed
    on exit; handlers own commit boundaries, and the after_begin hook means a
    commit cannot drop tenant isolation for subsequent reads.
    """
    session = SessionLocal()
    _bind_tenant_to_transactions(session, claims.tenant_id)
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(
    session: Session = Depends(get_tenant_db),
    claims: TokenClaims = Depends(get_token_claims),
) -> CurrentUser:
    """
    Load the authenticated user for the verified token.

    The lookup runs under the caller's tenant RLS context, so a token whose
    `tenant_id` claim does not match the user's real tenant finds no row and
    fails with 401. This makes a forged or stale tenant claim unusable rather
    than merely unlikely.

    Returns a CurrentUser, never the ORM User, so password_hash stays out of
    route responses.
    """
    user = session.get(User, claims.user_id)

    if user is None or user.tenant_id != claims.tenant_id:
        raise _unauthorized()

    return CurrentUser(
        id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
        agency_id=user.agency_id,
    )


def require_role(*roles: UserRole) -> Callable[..., CurrentUser]:
    """
    Build a dependency that admits only the given roles.

    Returns 403 rather than 401: the caller is authenticated but not permitted.
    Keeps future ORGANIZER / REVIEWER / ADMIN routes free of inline role checks.
    """

    def _dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _dependency
