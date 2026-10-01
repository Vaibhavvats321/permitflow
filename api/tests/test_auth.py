"""
Tests for the login and /auth/me endpoints.

Covers the successful login contract, the response shape, the fact that a
password is never returned, and — most importantly — that every way of failing
to authenticate produces the same 401 body, so the endpoint cannot be used to
enumerate registered email addresses.

Users are arranged on the privileged connection; login itself runs on the
restricted application role, so these tests exercise the real runtime path
including the cross-tenant SECURITY DEFINER lookup.
"""

from __future__ import annotations

import uuid

import jwt
import pytest
import sqlalchemy as sa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import hash_password
from app.deps import require_role
from app.main import app
from app.models import UserRole

from tests.conftest import TenantFixture

LOGIN_PATH = "/auth/login"
ME_PATH = "/auth/me"

# The single detail string every authentication failure must produce. Asserted
# literally so a future change that leaks account existence is caught here.
GENERIC_401_DETAIL = "Could not validate credentials"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def login(client: TestClient, email: str, password: str):
    return client.post(LOGIN_PATH, json={"email": email, "password": password})


@pytest.fixture
def account(make_tenant) -> TenantFixture:
    return make_tenant("AuthTenant", with_reviewer=True)


# ---------------------------------------------------------------------------
# Successful login
# ---------------------------------------------------------------------------


def test_login_returns_a_usable_token(client: TestClient, account) -> None:
    response = login(client, account.organizer.email, "correct-horse-battery-staple")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == UserRole.ORGANIZER.value
    assert body["tenant_id"] == str(account.tenant.id)

    claims = jwt.decode(
        body["access_token"],
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )
    assert claims["sub"] == str(account.organizer.id)
    assert claims["tenant_id"] == str(account.tenant.id)
    assert claims["role"] == UserRole.ORGANIZER.value


def test_login_token_authenticates_against_me(client: TestClient, account) -> None:
    """The end-to-end round trip: login, then use the token."""
    token = login(
        client, account.organizer.email, "correct-horse-battery-staple"
    ).json()["access_token"]

    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "id": str(account.organizer.id),
        "email": account.organizer.email,
        "role": UserRole.ORGANIZER.value,
        "tenant_id": str(account.tenant.id),
        "agency_id": None,
    }


def test_login_never_returns_password_material(client: TestClient, account) -> None:
    raw = login(
        client, account.organizer.email, "correct-horse-battery-staple"
    ).text

    assert "password" not in raw
    assert account.organizer.password_hash not in raw


@pytest.mark.parametrize(
    ("user_attr", "expected_agency"),
    [
        ("organizer", None),
        ("reviewer", "agency"),
        ("admin", None),
    ],
)
def test_login_and_me_agree_on_role_and_agency(
    client: TestClient, account, user_attr, expected_agency
) -> None:
    user = getattr(account, user_attr)
    token = login(client, user.email, "correct-horse-battery-staple").json()[
        "access_token"
    ]

    me = client.get(ME_PATH, headers={"Authorization": f"Bearer {token}"}).json()

    assert me["role"] == user.role.value
    assert me["agency_id"] == (
        str(account.agency.id) if expected_agency else None
    )


def test_login_is_case_insensitive_on_email(client: TestClient, account) -> None:
    """Emails are stored lowercase; a differently-cased address still works."""
    response = login(
        client, account.organizer.email.upper(), "correct-horse-battery-staple"
    )

    assert response.status_code == 200


def test_password_change_invalidates_the_old_one(client: TestClient, db, account) -> None:
    """Changing the hash must actually revoke the previous credential."""
    assert login(
        client, account.organizer.email, "correct-horse-battery-staple"
    ).status_code == 200

    account.organizer.password_hash = hash_password("a-brand-new-password")
    db.commit()

    assert login(
        client, account.organizer.email, "correct-horse-battery-staple"
    ).status_code == 401
    assert login(
        client, account.organizer.email, "a-brand-new-password"
    ).status_code == 200


# ---------------------------------------------------------------------------
# Failure modes: all indistinguishable
# ---------------------------------------------------------------------------


def test_wrong_password_is_401(client: TestClient, account) -> None:
    response = login(client, account.organizer.email, "not-the-password")

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_401_DETAIL


def test_unknown_email_is_401(client: TestClient, account) -> None:
    response = login(client, "nobody@example.com", "correct-horse-battery-staple")

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_401_DETAIL


def test_existing_and_nonexistent_accounts_are_indistinguishable(
    client: TestClient, account
) -> None:
    """
    The core anti-enumeration assertion.

    An attacker must not be able to tell a registered address from an
    unregistered one by comparing responses.
    """
    unknown = login(client, "definitely-not-registered@example.com", "some-password")
    wrong_password = login(client, account.organizer.email, "some-password")

    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json() == wrong_password.json()
    assert unknown.headers.get("www-authenticate") == "Bearer"


def test_other_tenants_users_can_log_in_independently(client: TestClient, make_tenant) -> None:
    """Authentication is not scoped to a tenant that has not been chosen yet."""
    springfield = make_tenant("AuthSpringfield")
    riverton = make_tenant("AuthRiverton")

    first = login(
        client, springfield.organizer.email, "correct-horse-battery-staple"
    ).json()
    second = login(
        client, riverton.organizer.email, "correct-horse-battery-staple"
    ).json()

    assert first["tenant_id"] == str(springfield.tenant.id)
    assert second["tenant_id"] == str(riverton.tenant.id)
    assert first["tenant_id"] != second["tenant_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "whatever"},
        {"email": "someone@example.com"},
        {"password": "whatever"},
        {},
    ],
)
def test_malformed_credentials_are_rejected(client: TestClient, payload) -> None:
    """A 422 is fine for structurally invalid input; a 500 would not be."""
    response = client.post(LOGIN_PATH, json=payload)

    assert response.status_code == 422
    assert GENERIC_401_DETAIL not in response.text


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


def test_me_requires_a_token(client: TestClient) -> None:
    assert client.get(ME_PATH).status_code == 401


def test_me_rejects_a_garbage_token(client: TestClient) -> None:
    response = client.get(ME_PATH, headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_401_DETAIL


def test_me_rejects_a_token_signed_with_another_secret(
    client: TestClient, account
) -> None:
    forged = jwt.encode(
        {
            "sub": str(account.organizer.id),
            "tenant_id": str(account.tenant.id),
            "role": UserRole.ORGANIZER.value,
            "exp": 9999999999,
        },
        "a-different-secret",
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


def test_me_rejects_a_token_for_a_deleted_user(client: TestClient, db, account) -> None:
    token = account.token_for(account.organizer)
    db.query(type(account.organizer)).filter(
        type(account.organizer).id == account.organizer.id
    ).delete(synchronize_session=False)
    db.commit()

    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_me_rejects_a_token_claiming_another_tenant(client: TestClient, make_tenant) -> None:
    """A token pointing at tenant B but naming tenant A's user finds nothing."""
    springfield = make_tenant("AuthMTSpringfield")
    riverton = make_tenant("AuthMTRiverton")

    forged = jwt.encode(
        {
            "sub": str(springfield.organizer.id),
            "tenant_id": str(riverton.tenant.id),
            "role": UserRole.ORGANIZER.value,
            "exp": 9999999999,
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


@pytest.mark.parametrize(
    "user_attr", ["organizer", "reviewer", "admin"]
)
def test_me_admits_every_role(client: TestClient, account, user_attr) -> None:
    """All three roles can read their own identity; only role-gated routes 403."""
    user = getattr(account, user_attr)
    token = login(client, user.email, "correct-horse-battery-staple").json()[
        "access_token"
    ]

    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["role"] == user.role.value


def test_role_gate_returns_403_not_401(client: TestClient, account) -> None:
    """403 lives on role-gated routes, not on /auth/me."""
    probe = FastAPI()

    @probe.get("/_test/admin-only")
    def admin_only(_=Depends(require_role(UserRole.CITY_ADMIN))):
        return {"ok": True}

    probe_client = TestClient(probe)
    organizer = account.token_for(account.organizer)

    response = probe_client.get(
        "/_test/admin-only", headers={"Authorization": f"Bearer {organizer}"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"

    admin = account.token_for(account.admin)
    assert probe_client.get(
        "/_test/admin-only", headers={"Authorization": f"Bearer {admin}"}
    ).status_code == 200

    # Unauthenticated is still 401, proving the two are distinct.
    assert probe_client.get("/_test/admin-only").status_code == 401


# ---------------------------------------------------------------------------
# Runtime isolation, not just schema isolation
# ---------------------------------------------------------------------------


def test_login_runs_on_the_restricted_application_role(client: TestClient, account) -> None:
    """
    The login lookup must not depend on a superuser.

    get_user_by_email is SECURITY DEFINER, so it returns the row even though the
    calling role has no tenant context and RLS would otherwise hide it.
    """
    assert login(
        client, account.organizer.email, "correct-horse-battery-staple"
    ).status_code == 200

    with sa.create_engine(settings.DATABASE_URL).connect() as conn:
        current_user = conn.execute(sa.text("select current_user")).scalar()
    assert current_user != "postgres"
    assert current_user != "superuser"


def test_login_function_is_not_executable_by_public(db) -> None:
    """
    SECURITY DEFINER is only safe while PUBLIC lacks EXECUTE.

    If PUBLIC could call get_user_by_email, any role could harvest every user's
    password hash regardless of RLS.
    """
    with sa.create_engine(settings.DATABASE_URL_ADMIN).connect() as conn:
        can_call = conn.execute(
            sa.text(
                "select has_function_privilege("
                "'public', 'public.get_user_by_email(text)', 'EXECUTE')"
            )
        ).scalar()

    assert can_call is False


def test_unknown_user_does_not_consult_the_users_table_directly(
    client: TestClient, account
) -> None:
    """
    Reading users without a tenant context must yield nothing, yet login works.

    Together these prove login goes through the SECURITY DEFINER function
    rather than an unguarded SELECT on a table RLS would have emptied.
    """
    # A NullPool connection is guaranteed never to have had the tenant GUC set,
    # which is the only way this query can run at all: see the documented
    # empty-string placeholder behaviour in test_rls_isolation.
    from sqlalchemy.pool import NullPool

    pristine = sa.create_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        with pristine.connect() as conn:
            assert conn.execute(sa.text("select count(*) from users")).scalar() == 0
    finally:
        pristine.dispose()

    assert login(
        client, account.organizer.email, "correct-horse-battery-staple"
    ).status_code == 200


def test_unknown_uuid_in_token_is_401(client: TestClient) -> None:
    orphan = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "role": UserRole.ORGANIZER.value,
            "exp": 9999999999,
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {orphan}"})

    assert response.status_code == 401