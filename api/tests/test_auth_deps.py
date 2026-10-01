"""
Tests for the authentication dependency layer.

Covers token extraction and validation, the 401 contract, tenant-context
establishment across commit boundaries, and the 403 role contract.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import sqlalchemy as sa
from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.deps import (
    CurrentUser,
    get_current_user,
    get_tenant_db,
    get_token_claims,
    require_role,
)
from app.main import app
from app.models import UserRole

ME_PATH = "/_test/me"


def make_token(
    sub: uuid.UUID | str,
    tenant_id: uuid.UUID | str,
    role: str,
    *,
    secret: str | None = None,
    expires_in: timedelta = timedelta(minutes=5),
) -> str:
    """Build a token directly, bypassing create_access_token defaults."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(sub),
            "tenant_id": str(tenant_id),
            "role": role,
            "iat": now,
            "exp": now + expires_in,
        },
        secret or settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def mount_me(probe: FastAPI, path: str = ME_PATH) -> None:
    @probe.get(path)
    def me(user: CurrentUser = Depends(get_current_user)) -> dict:
        return {
            "id": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "tenant_id": str(user.tenant_id),
        }


def session_for(token: str):
    """Resolve a token to claims, then open a tenant-scoped session."""
    claims = get_token_claims(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    )
    generator = get_tenant_db(claims)
    return claims, generator, next(generator)


def current_tenant_setting(session) -> str | None:
    return session.execute(
        sa.text("SELECT current_setting('app.current_tenant_id', true)")
    ).scalar()


@pytest.fixture
def probe_app() -> FastAPI:
    """
    A fresh app per test for mounting probe routes.

    Registering routes on the shared global `app` would leak paths between
    tests and make assertions depend on execution order.
    """
    return FastAPI()


# ---------------------------------------------------------------------------
# Public behaviour: routes that do not require authentication
# ---------------------------------------------------------------------------


def test_health_is_public() -> None:
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Token extraction and validation -> 401
# ---------------------------------------------------------------------------


def test_missing_header_returns_401(probe_app: FastAPI, make_tenant) -> None:
    make_tenant("NoHeaderTenant")
    mount_me(probe_app)

    with TestClient(probe_app) as client:
        assert client.get(ME_PATH).status_code == 401


@pytest.mark.parametrize(
    "header",
    [
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "not-a-scheme"},
    ],
)
def test_unusable_authorization_headers_return_401(
    probe_app: FastAPI, make_tenant, header: dict[str, str]
) -> None:
    make_tenant("BadHeaderTenant")
    mount_me(probe_app)

    with TestClient(probe_app) as client:
        assert client.get(ME_PATH, headers=header).status_code == 401


def test_token_signed_with_wrong_secret_returns_401(
    probe_app: FastAPI, make_tenant
) -> None:
    tenant = make_tenant("WrongSecretTenant")
    forged = make_token(
        tenant.organizer.id,
        tenant.tenant.id,
        UserRole.ORGANIZER.value,
        secret="an-attacker-controlled-secret-value-here",
    )
    mount_me(probe_app)

    with TestClient(probe_app) as client:
        assert client.get(ME_PATH, headers={"Authorization": f"Bearer {forged}"}
                           ).status_code == 401


def test_expired_token_returns_401(probe_app: FastAPI, make_tenant) -> None:
    tenant = make_tenant("ExpiredTenant")
    expired = make_token(
        tenant.organizer.id,
        tenant.tenant.id,
        UserRole.ORGANIZER.value,
        expires_in=timedelta(hours=-1),
    )
    mount_me(probe_app)

    with TestClient(probe_app) as client:
        assert client.get(
            ME_PATH, headers={"Authorization": f"Bearer {expired}"}
        ).status_code == 401


@pytest.mark.parametrize("missing_claim", ["sub", "tenant_id", "role"])
def test_token_missing_required_claim_returns_401(
    probe_app: FastAPI, make_tenant, missing_claim: str
) -> None:
    tenant = make_tenant(f"Missing{missing_claim.title()}ClaimTenant")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(tenant.organizer.id),
        "tenant_id": str(tenant.tenant.id),
        "role": UserRole.ORGANIZER.value,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    payload.pop(missing_claim)
    token = jwt.encode(
        payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    mount_me(probe_app)

    with TestClient(probe_app) as client:
        assert client.get(
            ME_PATH, headers={"Authorization": f"Bearer {token}"}
        ).status_code == 401


@pytest.mark.parametrize(
    "sub,tenant_id,role",
    [
        ("not-a-uuid", None, None),
        (None, "not-a-uuid", None),
        (None, None, "SUPERUSER"),
        (None, None, ""),
    ],
)
def test_malformed_claim_values_return_401(
    probe_app: FastAPI,
    make_tenant,
    sub: str | None,
    tenant_id: str | None,
    role: str | None,
) -> None:
    tenant = make_tenant(f"Malformed{sub}{tenant_id}{role}"[:60])
    user = tenant.organizer

    def resolve(value, fallback):
        return fallback if value is None else value

    token = make_token(
        resolve(sub, user.id),
        resolve(tenant_id, tenant.tenant.id),
        resolve(role, UserRole.ORGANIZER.value),
    )
    mount_me(probe_app)

    with TestClient(probe_app) as client:
        assert client.get(
            ME_PATH, headers={"Authorization": f"Bearer {token}"}
        ).status_code == 401


def test_token_for_nonexistent_user_returns_401(
    probe_app: FastAPI, make_tenant
) -> None:
    tenant = make_tenant("GhostUserTenant")
    ghost = create_access_token(
        sub=uuid.uuid4(), tenant_id=tenant.tenant.id, role=UserRole.ORGANIZER.value
    )
    mount_me(probe_app)

    with TestClient(probe_app) as client:
        assert client.get(
            ME_PATH, headers={"Authorization": f"Bearer {ghost}"}
        ).status_code == 401


# ---------------------------------------------------------------------------
# Current user representation
# ---------------------------------------------------------------------------


def test_valid_token_resolves_user(probe_app: FastAPI, make_tenant) -> None:
    tenant = make_tenant("ValidTokenTenant")
    mount_me(probe_app)

    with TestClient(probe_app) as client:
        response = client.get(
            ME_PATH,
            headers={"Authorization": f"Bearer {tenant.token_for(tenant.organizer)}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(tenant.organizer.id)
    assert body["email"] == tenant.organizer.email
    assert body["tenant_id"] == str(tenant.tenant.id)
    assert body["role"] == UserRole.ORGANIZER.value


def test_current_user_exposes_no_secret_fields(
    probe_app: FastAPI, make_tenant
) -> None:
    tenant = make_tenant("NoHashLeakTenant")

    @probe_app.get("/_test/me-fields")
    def me_fields(user: CurrentUser = Depends(get_current_user)) -> dict:
        return {"fields": sorted(user.__dataclass_fields__)}

    with TestClient(probe_app) as client:
        response = client.get(
            "/_test/me-fields",
            headers={"Authorization": f"Bearer {tenant.token_for(tenant.organizer)}"},
        )

    assert response.status_code == 200
    fields = response.json()["fields"]
    assert "password_hash" not in fields
    assert "password" not in fields
    assert set(fields) == {"id", "email", "role", "tenant_id", "agency_id"}


def test_reviewer_carries_agency_id(make_tenant) -> None:
    tenant = make_tenant("ReviewerAgencyTenant", with_reviewer=True)
    claims, generator, session = session_for(tenant.token_for(tenant.reviewer))
    try:
        user = get_current_user(session, claims)
        assert user.agency_id == tenant.agency.id
    finally:
        generator.close()


def test_organizer_has_no_agency(make_tenant) -> None:
    tenant = make_tenant("OrganizerNoAgencyTenant")
    claims, generator, session = session_for(tenant.token_for(tenant.organizer))
    try:
        user = get_current_user(session, claims)
        assert user.agency_id is None
    finally:
        generator.close()


# ---------------------------------------------------------------------------
# Tenant context
# ---------------------------------------------------------------------------


def test_tenant_setting_matches_verified_claim(make_tenant) -> None:
    """The core guarantee: RLS sees the authenticated caller's tenant id."""
    tenant = make_tenant("TenantSettingTenant", with_reviewer=True)
    claims, generator, session = session_for(tenant.token_for(tenant.reviewer))
    try:
        assert current_tenant_setting(session) == str(claims.tenant_id)
    finally:
        generator.close()


def test_tenant_setting_survives_commit(make_tenant) -> None:
    """
    SET LOCAL is discarded on COMMIT, so the session must re-establish it.

    This is the regression guard for the silent-zero-rows failure mode: without
    the after_begin hook, this assert sees an empty string instead of the id.
    """
    tenant = make_tenant("CommitSurvivalTenant", with_reviewer=True)
    claims, generator, session = session_for(tenant.token_for(tenant.reviewer))
    try:
        assert current_tenant_setting(session) == str(claims.tenant_id)

        session.commit()

        assert current_tenant_setting(session) == str(claims.tenant_id)
    finally:
        generator.close()


def test_tenant_setting_survives_rollback(make_tenant) -> None:
    tenant = make_tenant("RollbackSurvivalTenant", with_reviewer=True)
    claims, generator, session = session_for(tenant.token_for(tenant.reviewer))
    try:
        session.rollback()
        assert current_tenant_setting(session) == str(claims.tenant_id)
    finally:
        generator.close()


def test_tenant_setting_survives_repeated_commits(make_tenant) -> None:
    tenant = make_tenant("RepeatCommitTenant", with_reviewer=True)
    claims, generator, session = session_for(tenant.token_for(tenant.reviewer))
    try:
        for _ in range(3):
            session.commit()
            assert current_tenant_setting(session) == str(claims.tenant_id)
    finally:
        generator.close()


def test_concurrent_tenants_do_not_share_tenant_state(make_tenant) -> None:
    """Two tenants on the same engine must never observe each other's id."""
    tenant_a = make_tenant("IsolationA", with_reviewer=True)
    tenant_b = make_tenant("IsolationB", with_reviewer=True)

    claims_a, gen_a, sess_a = session_for(tenant_a.token_for(tenant_a.reviewer))
    claims_b, gen_b, sess_b = session_for(tenant_b.token_for(tenant_b.reviewer))
    try:
        value_a = current_tenant_setting(sess_a)
        value_b = current_tenant_setting(sess_b)
        assert value_a == str(tenant_a.tenant.id)
        assert value_b == str(tenant_b.tenant.id)
        assert value_a != value_b

        # Re-reading each session still yields its own tenant, not the last one used.
        assert current_tenant_setting(sess_a) == str(tenant_a.tenant.id)
        assert current_tenant_setting(sess_b) == str(tenant_b.tenant.id)
    finally:
        gen_a.close()
        gen_b.close()


def test_token_with_mismatched_tenant_claim_is_rejected(
    probe_app: FastAPI, make_tenant
) -> None:
    """
    A validly signed token whose tenant claim does not match the user's real
    tenant must not resolve, because the RLS-scoped lookup returns no row.
    """
    tenant_a = make_tenant("MismatchA", with_reviewer=True)
    tenant_b = make_tenant("MismatchB", with_reviewer=True)

    mismatched = create_access_token(
        sub=tenant_a.reviewer.id,
        tenant_id=tenant_b.tenant.id,
        role=UserRole.AGENCY_REVIEWER.value,
    )
    mount_me(probe_app)

    with TestClient(probe_app) as client:
        assert client.get(
            ME_PATH, headers={"Authorization": f"Bearer {mismatched}"}
        ).status_code == 401


def test_token_claiming_admin_role_cannot_escalate(
    probe_app: FastAPI, make_tenant
) -> None:
    """
    Authorization must come from the database row, not the token's role claim.

    The token below is validly signed and claims CITY_ADMIN for a user the
    database records as an ORGANIZER. It must be rejected rather than trusted.
    """
    tenant = make_tenant("EscalationTenant")
    escalating = create_access_token(
        sub=tenant.organizer.id,
        tenant_id=tenant.tenant.id,
        role=UserRole.CITY_ADMIN.value,
    )

    @probe_app.get("/_test/admin-only")
    def admin_only(
        user: CurrentUser = Depends(require_role(UserRole.CITY_ADMIN)),
    ) -> dict:
        return {"role": user.role.value}

    with TestClient(probe_app) as client:
        response = client.get(
            "/_test/admin-only",
            headers={"Authorization": f"Bearer {escalating}"},
        )

    assert response.status_code == 403


def test_get_token_claims_rejects_missing_credentials() -> None:
    """A direct call with no credentials fails fast rather than yielding None."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        get_token_claims(None)

    assert excinfo.value.status_code == 401


# ---------------------------------------------------------------------------
# Role authorization -> 403
# ---------------------------------------------------------------------------


def test_require_role_returns_403_for_wrong_role(
    probe_app: FastAPI, make_tenant
) -> None:
    tenant = make_tenant("RoleDenyTenant")

    @probe_app.get("/_test/admin-only")
    def admin_only(
        user: CurrentUser = Depends(require_role(UserRole.CITY_ADMIN)),
    ) -> dict:
        return {"role": user.role.value}

    with TestClient(probe_app) as client:
        response = client.get(
            "/_test/admin-only",
            headers={"Authorization": f"Bearer {tenant.token_for(tenant.organizer)}"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


def test_require_role_allows_matching_role(probe_app: FastAPI, make_tenant) -> None:
    tenant = make_tenant("RoleAllowTenant")

    @probe_app.get("/_test/admin-only")
    def admin_only(
        user: CurrentUser = Depends(require_role(UserRole.CITY_ADMIN)),
    ) -> dict:
        return {"role": user.role.value}

    with TestClient(probe_app) as client:
        response = client.get(
            "/_test/admin-only",
            headers={"Authorization": f"Bearer {tenant.token_for(tenant.admin)}"},
        )

    assert response.status_code == 200
    assert response.json()["role"] == UserRole.CITY_ADMIN.value


def test_require_role_accepts_any_of_several_roles(
    probe_app: FastAPI, make_tenant
) -> None:
    tenant = make_tenant("RoleMultiTenant", with_reviewer=True)

    @probe_app.get("/_test/staff")
    def staff(
        user: CurrentUser = Depends(
            require_role(UserRole.AGENCY_REVIEWER, UserRole.CITY_ADMIN)
        ),
    ) -> dict:
        return {"role": user.role.value}

    with TestClient(probe_app) as client:
        reviewer_response = client.get(
            "/_test/staff",
            headers={"Authorization": f"Bearer {tenant.token_for(tenant.reviewer)}"},
        )
        admin_response = client.get(
            "/_test/staff",
            headers={"Authorization": f"Bearer {tenant.token_for(tenant.admin)}"},
        )

    assert reviewer_response.status_code == 200
    assert reviewer_response.json()["role"] == UserRole.AGENCY_REVIEWER.value
    assert admin_response.status_code == 200
    assert admin_response.json()["role"] == UserRole.CITY_ADMIN.value


def test_require_role_returns_401_when_unauthenticated(probe_app: FastAPI) -> None:
    @probe_app.get("/_test/staff-anon")
    def staff(
        user: CurrentUser = Depends(require_role(UserRole.CITY_ADMIN)),
    ) -> dict:
        return {"role": user.role.value}

    with TestClient(probe_app) as client:
        assert client.get("/_test/staff-anon").status_code == 401


def test_401_responses_advertise_bearer_scheme(probe_app: FastAPI, make_tenant) -> None:
    make_tenant("WwwAuthenticateTenant")
    mount_me(probe_app)

    with TestClient(probe_app) as client:
        response = client.get(ME_PATH)

    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


# ---------------------------------------------------------------------------
# Error message hygiene
# ---------------------------------------------------------------------------


def test_auth_failures_are_indistinguishable(probe_app: FastAPI, make_tenant) -> None:
    """
    Unknown user, wrong-tenant claim, bad signature and garbage token must all
    produce byte-identical responses so the API cannot be used to enumerate
    accounts.
    """
    tenant = make_tenant("HygieneTenant")
    other = make_tenant("HygieneOtherTenant")

    unknown_user = create_access_token(
        sub=uuid.uuid4(), tenant_id=tenant.tenant.id, role=UserRole.ORGANIZER.value
    )
    wrong_tenant = create_access_token(
        sub=other.organizer.id, tenant_id=tenant.tenant.id, role=UserRole.ORGANIZER.value
    )
    wrong_secret = make_token(
        tenant.organizer.id,
        tenant.tenant.id,
        UserRole.ORGANIZER.value,
        secret="an-attacker-controlled-secret-value-here",
    )

    mount_me(probe_app)

    with TestClient(probe_app) as client:
        responses = [
            client.get(ME_PATH),
            client.get(ME_PATH, headers={"Authorization": "Bearer garbage"}),
            client.get(ME_PATH, headers={"Authorization": f"Bearer {unknown_user}"}),
            client.get(ME_PATH, headers={"Authorization": f"Bearer {wrong_tenant}"}),
            client.get(ME_PATH, headers={"Authorization": f"Bearer {wrong_secret}"}),
        ]

    assert {r.status_code for r in responses} == {401}
    details = {r.json()["detail"] for r in responses}
    assert details == {"Could not validate credentials"}
