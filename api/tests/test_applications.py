"""
Tests for the Organizer application draft endpoints.

Three separate guarantees are asserted here:

  1. Authorization  — only an authenticated Organizer may use these routes.
  2. Tenancy        — a token from another city sees nothing, even by id.
  3. Ownership      — a second organizer in the same city sees nothing either.

Point 3 is the one RLS does not cover for us. The policy is tenant-scoped, so
within a city every organizer passes it; ownership is enforced by the query
itself. These tests exist so that a later refactor cannot quietly drop the
`submitter_id` predicate and leak one organizer's drafts to another.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models import Application, ApplicationStatus, EventType, UserRole

from tests.conftest import TenantFixture

APPLICATIONS = "/applications"

START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
END = START + timedelta(hours=6)

VALID_PAYLOAD = {
    "event_name": "River City Marathon",
    "event_type": EventType.MARATHON.value,
    "start_date": START.isoformat(),
    "end_date": END.isoformat(),
    "location": "Riverside Park",
    "expected_attendance": 3500,
    "description": "Annual marathon along the river path.",
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def tenant(make_tenant) -> TenantFixture:
    return make_tenant("AppTenant", with_reviewer=True)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create(client: TestClient, token: str, **overrides):
    body = {**VALID_PAYLOAD, **overrides}
    return client.post(APPLICATIONS, json=body, headers=auth(token))


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_returns_201_with_a_draft(client: TestClient, tenant) -> None:
    response = create(client, tenant.token_for(tenant.organizer))

    assert response.status_code == 201
    body = response.json()
    assert body["event_name"] == VALID_PAYLOAD["event_name"]
    assert body["event_type"] == EventType.MARATHON.value
    assert body["location"] == "Riverside Park"
    assert body["expected_attendance"] == 3500
    assert body["status"] == ApplicationStatus.DRAFT.value
    assert body["submitter_id"] == str(tenant.organizer.id)
    assert body["tenant_id"] == str(tenant.tenant.id)
    assert uuid.UUID(body["id"])


def test_created_row_is_persisted_with_server_owned_fields(client: TestClient, db, tenant) -> None:
    """Verify against the database, not just the response body."""
    token = tenant.token_for(tenant.organizer)
    created = create(client, token).json()

    row = db.get(Application, uuid.UUID(created["id"]))

    assert row is not None
    assert row.submitter_id == tenant.organizer.id
    assert row.tenant_id == tenant.tenant.id
    assert row.status == ApplicationStatus.DRAFT
    assert row.created_at.tzinfo is not None
    assert row.updated_at.tzinfo is not None


def test_client_cannot_choose_submitter_or_tenant(client: TestClient, tenant) -> None:
    """
    Server-owned fields are not accepted from the request.

    A client that names another organizer or another city must be rejected
    outright rather than silently ignored, so the attempt is visible in the
    response instead of looking like success.
    """
    token = tenant.token_for(tenant.organizer)

    for field, value in (
        ("submitter_id", str(uuid.uuid4())),
        ("tenant_id", str(uuid.uuid4())),
        ("status", ApplicationStatus.APPROVED.value),
    ):
        response = create(client, token, **{field: value})
        assert response.status_code == 422, field


def test_minimal_draft_is_allowed(client: TestClient, tenant) -> None:
    """A draft may be incomplete; submission is what will demand the rest."""
    response = client.post(
        APPLICATIONS,
        json={"event_name": "Notebook", "event_type": EventType.OTHER.value},
        headers=auth(tenant.token_for(tenant.organizer)),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["start_date"] is None
    assert body["expected_attendance"] is None
    assert body["status"] == ApplicationStatus.DRAFT.value


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"event_name": ""}, "blank event name"),
        ({"event_name": "   "}, "whitespace-only event name"),
        ({"event_name": "x" * 256}, "event name too long"),
        ({"event_type": "Nightclub"}, "unknown event type"),
        ({"event_type": None}, "missing event type"),
        ({"expected_attendance": -1}, "negative attendance"),
        ({"expected_attendance": 0.5}, "non-integer attendance"),
        ({"location": "y" * 256}, "location too long"),
        (
            {
                "start_date": END.isoformat(),
                "end_date": START.isoformat(),
            },
            "end before start",
        ),
    ],
)
def test_invalid_payloads_are_rejected(
    client: TestClient, tenant, overrides, reason
) -> None:
    response = create(client, tenant.token_for(tenant.organizer), **overrides)

    assert response.status_code == 422, reason


def test_same_day_start_and_end_is_allowed(client: TestClient, tenant) -> None:
    """Equal timestamps are a legitimate single-day event, not a reversal."""
    response = create(
        client,
        tenant.token_for(tenant.organizer),
        start_date=START.isoformat(),
        end_date=START.isoformat(),
    )

    assert response.status_code == 201


def test_naive_timestamps_are_treated_as_utc(client: TestClient, tenant) -> None:
    """
    A timestamp without an offset must not be silently reinterpreted.

    The columns are `timestamptz`; an unzoned value would otherwise be read in
    the database server's timezone and shift the event date.
    """
    response = create(
        client,
        tenant.token_for(tenant.organizer),
        start_date="2026-11-07T14:00:00",
        end_date=None,
    )

    assert response.status_code == 201
    assert response.json()["start_date"].startswith("2026-11-07T14:00:00")


def test_offset_timestamps_are_converted_to_utc(client: TestClient, tenant) -> None:
    """14:00 at UTC-05:00 is 19:00 UTC; the stored value must agree."""
    response = create(
        client,
        tenant.token_for(tenant.organizer),
        start_date="2026-11-07T14:00:00-05:00",
        end_date=None,
    )

    assert response.status_code == 201
    stored = datetime.fromisoformat(response.json()["start_date"])
    assert stored.astimezone(UTC) == datetime(2026, 11, 7, 19, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [APPLICATIONS, f"{APPLICATIONS}/{uuid.uuid4()}"],
)
def test_endpoints_require_authentication(client: TestClient, path) -> None:
    assert client.get(path).status_code == 401


def test_create_requires_authentication(client: TestClient) -> None:
    response = client.post(APPLICATIONS, json=VALID_PAYLOAD)

    assert response.status_code == 401
    assert "submitter_id" not in response.text


def test_create_rejects_a_garbage_token(client: TestClient, tenant) -> None:
    response = client.post(
        APPLICATIONS,
        json=VALID_PAYLOAD,
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == 401


def test_create_rejects_an_expired_token(client: TestClient, tenant) -> None:
    expired = jwt.encode(
        {
            "sub": str(tenant.organizer.id),
            "tenant_id": str(tenant.tenant.id),
            "role": UserRole.ORGANIZER.value,
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.post(
        APPLICATIONS, json=VALID_PAYLOAD, headers=auth(expired)
    )

    assert response.status_code == 401


@pytest.mark.parametrize("user_attr", ["admin", "reviewer"])
def test_non_organizers_get_403(client: TestClient, tenant, user_attr) -> None:
    """Authenticated but not permitted is 403, distinct from 401."""
    token = tenant.token_for(getattr(tenant, user_attr))

    create_response = create(client, token)
    list_response = client.get(APPLICATIONS, headers=auth(token))

    assert create_response.status_code == 403
    assert create_response.json()["detail"] == "Insufficient permissions"
    assert list_response.status_code == 403


def test_non_organizers_cannot_create_rows(client: TestClient, db, tenant) -> None:
    """A 403 must leave the database untouched, not half-write."""
    token = tenant.token_for(tenant.admin)

    assert create(client, token).status_code == 403
    assert db.query(Application).filter(Application.tenant_id == tenant.tenant.id).count() == 0


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_returns_only_my_applications(client: TestClient, make_tenant) -> None:
    alice = make_tenant("ListAlice")
    bob = make_tenant("ListBob")

    create(client, alice.token_for(alice.organizer), event_name="Alice One")
    create(client, alice.token_for(alice.organizer), event_name="Alice Two")
    create(client, bob.token_for(bob.organizer), event_name="Bob One")

    mine = client.get(
        APPLICATIONS, headers=auth(alice.token_for(alice.organizer))
    ).json()

    assert [a["event_name"] for a in mine] == ["Alice Two", "Alice One"]


def test_list_is_empty_for_a_new_organizer(client: TestClient, tenant) -> None:
    response = client.get(APPLICATIONS, headers=auth(tenant.token_for(tenant.organizer)))

    assert response.status_code == 200
    assert response.json() == []


def test_list_filters_by_status_and_event_type(client: TestClient, tenant) -> None:
    token = tenant.token_for(tenant.organizer)
    create(client, token, event_name="Marathon", event_type=EventType.MARATHON.value)
    create(client, token, event_name="Concert", event_type=EventType.CONCERT.value)

    by_type = client.get(
        f"{APPLICATIONS}?event_type={EventType.CONCERT.value}", headers=auth(token)
    ).json()
    by_status = client.get(
        f"{APPLICATIONS}?status={ApplicationStatus.DRAFT.value}", headers=auth(token)
    ).json()

    assert [a["event_name"] for a in by_type] == ["Concert"]
    assert len(by_status) == 2


def test_list_rejects_an_unknown_filter_value(client: TestClient, tenant) -> None:
    response = client.get(
        f"{APPLICATIONS}?status=Nonsense", headers=auth(tenant.token_for(tenant.organizer))
    )

    assert response.status_code == 422


def test_list_paginates(client: TestClient, tenant) -> None:
    token = tenant.token_for(tenant.organizer)
    for index in range(5):
        create(client, token, event_name=f"Event {index}")

    page = client.get(f"{APPLICATIONS}?limit=2&offset=1", headers=auth(token)).json()
    every = client.get(f"{APPLICATIONS}?limit=100", headers=auth(token)).json()

    assert len(page) == 2
    assert len(every) == 5
    # Paging must not repeat or drop rows.
    assert {a["id"] for a in page}.issubset({a["id"] for a in every})
    assert page == every[1:3]


def test_list_limit_is_capped(client: TestClient, tenant) -> None:
    response = client.get(
        f"{APPLICATIONS}?limit=10000", headers=auth(tenant.token_for(tenant.organizer))
    )

    assert response.status_code == 422


def test_organizers_in_the_same_tenant_cannot_see_each_other(client: TestClient, db, make_tenant) -> None:
    """
    RLS is tenant-scoped, so this check belongs to the application.

    Two organizers in one city both pass the policy; only the `submitter_id`
    predicate keeps their applications apart.
    """
    city = make_tenant("SameCityTenant")
    second = city.add_organizer()

    first_id = create(
        client, city.token_for(city.organizer), event_name="First Organizer Draft"
    ).json()["id"]
    create(client, city.token_for(second), event_name="Second Organizer Draft")

    seen = client.get(
        APPLICATIONS, headers=auth(city.token_for(second))
    ).json()

    assert [a["event_name"] for a in seen] == ["Second Organizer Draft"]
    assert first_id not in [a["id"] for a in seen]


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


def test_get_returns_my_application(client: TestClient, tenant) -> None:
    token = tenant.token_for(tenant.organizer)
    created = create(client, token).json()

    response = client.get(f"{APPLICATIONS}/{created['id']}", headers=auth(token))

    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_id_is_404(client: TestClient, tenant) -> None:
    response = client.get(
        f"{APPLICATIONS}/{uuid.uuid4()}", headers=auth(tenant.token_for(tenant.organizer))
    )

    assert response.status_code == 404


def test_get_malformed_id_is_422(client: TestClient, tenant) -> None:
    response = client.get(
        f"{APPLICATIONS}/not-a-uuid", headers=auth(tenant.token_for(tenant.organizer))
    )

    assert response.status_code == 422


def test_get_another_organizers_application_is_404_not_403(client: TestClient, make_tenant) -> None:
    """
    404 rather than 403, so the API never confirms that an id exists.
    """
    city = make_tenant("GetOwnerTenant")
    second = city.add_organizer()
    target = create(client, city.token_for(city.organizer)).json()

    response = client.get(
        f"{APPLICATIONS}/{target['id']}", headers=auth(city.token_for(second))
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"


def test_get_other_tenants_application_is_404(client: TestClient, make_tenant) -> None:
    """Cross-tenant read is blocked, even holding the exact id."""
    springfield = make_tenant("GetSpringfield")
    riverton = make_tenant("GetRiverton")
    target = create(client, springfield.token_for(springfield.organizer)).json()

    response = client.get(
        f"{APPLICATIONS}/{target['id']}",
        headers=auth(riverton.token_for(riverton.organizer)),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_replaces_fields(client: TestClient, tenant) -> None:
    token = tenant.token_for(tenant.organizer)
    created = create(client, token).json()

    response = client.put(
        f"{APPLICATIONS}/{created['id']}",
        json={**VALID_PAYLOAD, "event_name": "Renamed Event"},
        headers=auth(token),
    )

    assert response.status_code == 200
    assert response.json()["event_name"] == "Renamed Event"
    assert response.json()["id"] == created["id"]


def test_update_cannot_change_ownership_or_status(client: TestClient, tenant) -> None:
    token = tenant.token_for(tenant.organizer)
    created = create(client, token).json()

    for field, value in (
        ("status", ApplicationStatus.APPROVED.value),
        ("submitter_id", str(tenant.admin.id)),
        ("tenant_id", str(uuid.uuid4())),
    ):
        response = client.put(
            f"{APPLICATIONS}/{created['id']}",
            json={**VALID_PAYLOAD, field: value},
            headers=auth(token),
        )
        assert response.status_code == 422, field


def test_update_bumps_updated_at(client: TestClient, tenant) -> None:
    token = tenant.token_for(tenant.organizer)
    created = create(client, token).json()

    updated = client.put(
        f"{APPLICATIONS}/{created['id']}",
        json={**VALID_PAYLOAD, "event_name": "Touched"},
        headers=auth(token),
    ).json()

    assert datetime.fromisoformat(updated["updated_at"]) > datetime.fromisoformat(
        created["updated_at"]
    )
    # Identity and creation time are not the application's to change.
    assert updated["created_at"] == created["created_at"]


def test_update_of_another_organizers_application_is_404(client: TestClient, make_tenant) -> None:
    city = make_tenant("PutOwnerTenant")
    second = city.add_organizer()
    target = create(client, city.token_for(city.organizer)).json()

    response = client.put(
        f"{APPLICATIONS}/{target['id']}",
        json={**VALID_PAYLOAD, "event_name": "Hijacked"},
        headers=auth(city.token_for(second)),
    )

    assert response.status_code == 404


def test_update_across_tenants_is_404_and_changes_nothing(
    client: TestClient, db, make_tenant
) -> None:
    springfield = make_tenant("PutSpringfield")
    riverton = make_tenant("PutRiverton")
    target = create(client, springfield.token_for(springfield.organizer)).json()

    response = client.put(
        f"{APPLICATIONS}/{target['id']}",
        json={**VALID_PAYLOAD, "event_name": "Cross Tenant Edit"},
        headers=auth(riverton.token_for(riverton.organizer)),
    )

    assert response.status_code == 404
    row = db.get(Application, uuid.UUID(target["id"]))
    assert row.event_name == VALID_PAYLOAD["event_name"]


def test_update_rejects_invalid_payload(client: TestClient, tenant) -> None:
    token = tenant.token_for(tenant.organizer)
    created = create(client, token).json()

    response = client.put(
        f"{APPLICATIONS}/{created['id']}",
        json={**VALID_PAYLOAD, "end_date": (START - timedelta(days=1)).isoformat()},
        headers=auth(token),
    )

    assert response.status_code == 422


def test_update_of_a_non_draft_is_conflict(client: TestClient, db, tenant) -> None:
    """
    A submitted application must not be quietly editable.

    Marked Submitted directly in the database: submission itself is not built
    yet, but the guard has to hold for whatever eventually sets that status.
    """
    token = tenant.token_for(tenant.organizer)
    created = create(client, token).json()

    row = db.get(Application, uuid.UUID(created["id"]))
    row.status = ApplicationStatus.SUBMITTED
    db.commit()

    response = client.put(
        f"{APPLICATIONS}/{created['id']}",
        json={**VALID_PAYLOAD, "event_name": "Sneaky Edit"},
        headers=auth(token),
    )

    assert response.status_code == 409
    assert "Submitted" in response.json()["detail"]
    db.refresh(row)
    assert row.event_name == VALID_PAYLOAD["event_name"]


# ---------------------------------------------------------------------------
# Runtime isolation
# ---------------------------------------------------------------------------


def test_application_routes_use_the_restricted_role(client: TestClient, tenant) -> None:
    """
    Confirm these endpoints are not accidentally running privileged.

    The tenant GUC is set per request from the token, so a write must still be
    attributed to the tenant in the token, never one supplied by the caller.
    """
    token = tenant.token_for(tenant.organizer)

    created = create(client, token).json()

    with sa.create_engine(settings.DATABASE_URL).connect() as conn:
        current_user = conn.execute(sa.text("select current_user")).scalar()
    assert current_user == "permitflow_app"

    row = tenant.session.get(Application, uuid.UUID(created["id"]))
    assert row.tenant_id == tenant.tenant.id


def test_forged_tenant_claim_cannot_file_into_another_city(
    client: TestClient, make_tenant
) -> None:
    """
    A token naming another city must not be able to write there.

    The tenant is taken from the verified claim, but RLS independently scopes
    the write, so a mismatch finds nothing and returns 401 rather than filing
    the application under the wrong city.
    """
    springfield = make_tenant("ForgedSpringfield")
    riverton = make_tenant("ForgedRiverton")

    forged = jwt.encode(
        {
            "sub": str(springfield.organizer.id),
            "tenant_id": str(riverton.tenant.id),
            "role": UserRole.ORGANIZER.value,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.post(APPLICATIONS, json=VALID_PAYLOAD, headers=auth(forged))

    assert response.status_code == 401
    assert springfield.session.query(Application).filter(Application.tenant_id == springfield.tenant.id).count() == 0
    assert riverton.session.query(Application).filter(Application.tenant_id == riverton.tenant.id).count() == 0


def test_organizer_role_claim_cannot_be_forged_to_pass_the_role_gate(
    client: TestClient, tenant
) -> None:
    """
    The gate reads the role from the database, not from the token.

    A reviewer cannot mint a token claiming ORGANIZER and create applications.
    """
    forged = jwt.encode(
        {
            "sub": str(tenant.reviewer.id),
            "tenant_id": str(tenant.tenant.id),
            "role": UserRole.ORGANIZER.value,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.post(APPLICATIONS, json=VALID_PAYLOAD, headers=auth(forged))

    assert response.status_code == 403
    assert tenant.session.query(Application).filter(Application.tenant_id == tenant.tenant.id).count() == 0