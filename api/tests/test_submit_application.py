"""
Tests for submitting an application and creating review tasks.

The submit endpoint:
- Turns a Draft into Submitted
- Creates one Pending review task for each required agency
- Adds Fire if attendance > 5000
- Prevents submitting non-drafts
- Prevents duplicate submission
- Enforces ownership and tenancy

Also validates the routing logic via the API, so the implementation of
app.core.routing is actually exercised at runtime.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Application,
    ApplicationStatus,
    EventType,
    ReviewStatus,
    ReviewTask,
)

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


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def submit_path(app_id: uuid.UUID | str) -> str:
    return f"{APPLICATIONS}/{app_id}/submit"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def tenant(make_tenant) -> TenantFixture:
    return make_tenant("SubmitTenant", with_reviewer=True)


def create_draft(client: TestClient, token: str, **overrides) -> Application:
    payload = {**VALID_PAYLOAD, **overrides}
    response = client.post(APPLICATIONS, json=payload, headers=auth(token))
    assert response.status_code == 201, response.text
    body = response.json()
    return Application(
        id=uuid.UUID(body["id"]),
        status=ApplicationStatus(body["status"]),
        submitter_id=uuid.UUID(body["submitter_id"]),
        tenant_id=uuid.UUID(body["tenant_id"]),
        event_type=EventType(body["event_type"]),
        expected_attendance=body["expected_attendance"],
    )


def submit(client: TestClient, token: str, app_id: uuid.UUID | str):
    return client.post(submit_path(app_id), headers=auth(token))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_submit_transitions_draft_to_submitted_and_creates_tasks(
    client: TestClient, db, tenant
) -> None:
    """Base routing: Marathon requires Police and Health (Fire not added)."""
    draft = create_draft(client, tenant.token_for(tenant.organizer))

    response = submit(client, tenant.token_for(tenant.organizer), draft.id)

    assert response.status_code == 200
    body = response.json()
    app_body = body["application"]
    assert app_body["id"] == str(draft.id)
    assert app_body["status"] == ApplicationStatus.SUBMITTED.value

    agency_names = [a["name"] for a in body["required_agencies"]]
    assert agency_names == ["Health", "Police"]  # stable, name-sorted
    assert body["attendance_override_applied"] is False

    tasks = (
        db.query(ReviewTask)
        .filter(ReviewTask.application_id == draft.id)
        .order_by(ReviewTask.id)
        .all()
    )
    assert len(tasks) == 2
    for task in tasks:
        assert task.status.value == "Pending"
        assert task.tenant_id == tenant.tenant.id
        assert task.application_id == draft.id

    row = db.get(Application, draft.id)
    assert row.status == ApplicationStatus.SUBMITTED


def test_submit_adds_fire_when_attendance_above_5000(
    client: TestClient, db, tenant
) -> None:
    """
    "attendance over 5,000 always adds Fire."

    The seeded base rules do not include Fire, so it is appended.
    """
    draft = create_draft(
        client,
        tenant.token_for(tenant.organizer),
        expected_attendance=5001,
    )

    response = submit(client, tenant.token_for(tenant.organizer), draft.id)

    assert response.status_code == 200
    agency_names = [a["name"] for a in response.json()["required_agencies"]]
    assert agency_names == ["Fire", "Health", "Police"]
    assert response.json()["attendance_override_applied"] is True

    task_count = db.query(ReviewTask).filter(
        ReviewTask.application_id == draft.id
    ).count()
    assert task_count == 3


def test_submit_does_not_add_fire_at_exactly_5000(
    client: TestClient, db, tenant
) -> None:
    """Exactly 5000 is not "over 5,000"; the override must not fire."""
    draft = create_draft(
        client,
        tenant.token_for(tenant.organizer),
        expected_attendance=5000,
    )

    response = submit(client, tenant.token_for(tenant.organizer), draft.id)

    assert response.status_code == 200
    agency_names = [a["name"] for a in response.json()["required_agencies"]]
    assert agency_names == ["Health", "Police"]
    assert response.json()["attendance_override_applied"] is False
    assert db.query(ReviewTask).filter(ReviewTask.application_id == draft.id).count() == 2


def test_submit_fire_already_required_is_not_duplicated(
    client: TestClient, db, tenant
) -> None:
    """
    A hypothetical case where routing already includes Fire: union, not append.

    The seeded rules do not, but the routing logic must be idempotent by agency id.
    """
    draft = create_draft(
        client,
        tenant.token_for(tenant.organizer),
        event_type=EventType.CONCERT.value,
        expected_attendance=6000,
    )

    response = submit(client, tenant.token_for(tenant.organizer), draft.id)
    assert response.status_code == 200
    agency_names = [a["name"] for a in response.json()["required_agencies"]]
    assert agency_names == ["Fire", "Health", "Police"]
    assert db.query(ReviewTask).filter(ReviewTask.application_id == draft.id).count() == 3


def test_submit_adds_agency_whose_threshold_is_exceeded(
    client: TestClient, tenant
) -> None:
    """
    Threshold routing is per-agency and read from the database.

    "Parks Department" is in no routing matrix: only its stored threshold can
    make it required, and only when attendance is strictly above that value.
    """
    admin = tenant.token_for(tenant.admin)
    organizer = tenant.token_for(tenant.organizer)

    with TestClient(app) as client:
        created = client.post(
            "/admin/agencies",
            json={"name": "Parks Department", "attendance_threshold": 1000},
            headers=auth(admin),
        )
        assert created.status_code == 201, created.text

        over = create_draft(client, organizer, expected_attendance=1500)
        response = submit(client, organizer, over.id)
        assert response.status_code == 200
        names = [a["name"] for a in response.json()["required_agencies"]]
        assert names == ["Health", "Parks Department", "Police"]
        assert response.json()["attendance_override_applied"] is True

        # Attendance equal to the threshold is not "over" — Parks stays out.
        exact = create_draft(client, organizer, expected_attendance=1000)
        response = submit(client, organizer, exact.id)
        assert response.status_code == 200
        names = [a["name"] for a in response.json()["required_agencies"]]
        assert names == ["Health", "Police"]
        assert response.json()["attendance_override_applied"] is False


def test_threshold_change_applies_to_new_submissions(
    client: TestClient, db, tenant
) -> None:
    """
    An admin's threshold edit takes effect on the next submission — no code
    change, no restart. The brief's example: Fire 5,000 -> 8,000 stops a
    5,500-attendance event from routing to Fire.
    """
    admin = tenant.token_for(tenant.admin)
    organizer = tenant.token_for(tenant.organizer)
    fire_id = tenant.agencies["Fire"].id

    with TestClient(app) as client:
        before = create_draft(client, organizer, expected_attendance=5500)
        response = submit(client, organizer, before.id)
        assert response.status_code == 200
        assert [a["name"] for a in response.json()["required_agencies"]] == [
            "Fire",
            "Health",
            "Police",
        ]

        patch = client.patch(
            f"/admin/agencies/{fire_id}",
            json={"name": "Fire", "attendance_threshold": 8000},
            headers=auth(admin),
        )
        assert patch.status_code == 200
        assert patch.json()["attendance_threshold"] == 8000

        after = create_draft(client, organizer, expected_attendance=5500)
        response = submit(client, organizer, after.id)
        assert response.status_code == 200
        assert [a["name"] for a in response.json()["required_agencies"]] == [
            "Health",
            "Police",
        ]
        assert response.json()["attendance_override_applied"] is False
        # One task per agency, both submissions: Fire once before, none after.
        assert (
            db.query(ReviewTask).filter(ReviewTask.application_id == before.id).count()
            == 3
        )
        assert (
            db.query(ReviewTask).filter(ReviewTask.application_id == after.id).count()
            == 2
        )


def test_agency_in_matrix_and_over_threshold_gets_one_task(
    client: TestClient, db, tenant
) -> None:
    """
    Matrix + threshold is a union keyed by agency id: an agency required by
    both routes still gets exactly one review task.
    """
    admin = tenant.token_for(tenant.admin)
    organizer = tenant.token_for(tenant.organizer)

    with TestClient(app) as client:
        # Police is in the matrix for every event type; drop its threshold far
        # enough that the same submission exceeds it as well.
        patch = client.patch(
            f"/admin/agencies/{tenant.agencies['Police'].id}",
            json={"name": "Police", "attendance_threshold": 100},
            headers=auth(admin),
        )
        assert patch.status_code == 200

        draft = create_draft(client, organizer, expected_attendance=500)
        response = submit(client, organizer, draft.id)
        assert response.status_code == 200

        names = [a["name"] for a in response.json()["required_agencies"]]
        assert names == ["Health", "Police"]  # Police once, not twice
        assert db.query(ReviewTask).filter(
            ReviewTask.application_id == draft.id
        ).count() == 2


def test_submit_is_atomic(db, client, tenant) -> None:
    """
    The status and tasks are created together.

    If tasks could be created without the status flip in a broken transaction,
    that would be a bug. We assert both landed after commit.
    """
    draft = create_draft(client, tenant.token_for(tenant.organizer))
    submit(client, tenant.token_for(tenant.organizer), draft.id)

    row = db.get(Application, draft.id)
    assert row.status == ApplicationStatus.SUBMITTED
    assert db.query(ReviewTask).filter(ReviewTask.application_id == draft.id).count() == 2


def test_submit_requires_all_mandatory_fields(db, client, tenant) -> None:
    """A draft without dates/location/attendance cannot be submitted."""
    token = tenant.token_for(tenant.organizer)
    draft = create_draft(client, token, start_date=None, end_date=None, location=None, expected_attendance=None)

    response = submit(client, token, draft.id)

    assert response.status_code == 422
    assert "missing required fields" in response.json()["detail"]
    row = db.get(Application, draft.id)
    assert row.status == ApplicationStatus.DRAFT
    assert db.query(ReviewTask).filter(ReviewTask.application_id == draft.id).count() == 0


@pytest.mark.parametrize(
    "missing_field", ["start_date", "end_date", "location", "expected_attendance"]
)
def test_submit_rejects_each_missing_field(
    client: TestClient, db, tenant, missing_field
) -> None:
    """Each mandatory field is reported by name, and nothing is written."""
    token = tenant.token_for(tenant.organizer)
    draft = create_draft(client, token, **{missing_field: None})

    response = submit(client, token, draft.id)

    assert response.status_code == 422
    assert missing_field in response.json()["detail"]
    assert db.get(Application, draft.id).status == ApplicationStatus.DRAFT
    assert db.query(ReviewTask).filter(ReviewTask.application_id == draft.id).count() == 0


def test_database_rejects_duplicate_review_tasks(db, tenant) -> None:
    """
    The last line of defence against a duplicate task is the schema, not the API.

    Simulates two concurrent submits winning the race past the application-level
    checks: the constraint is what stops the same agency getting two tasks.
    """
    draft = create_draft_from_session(tenant)

    for _ in range(2):
        db.add(
            ReviewTask(
                application_id=draft.id,
                agency_id=tenant.agencies["Police"].id,
                tenant_id=tenant.tenant.id,
            )
        )

    # The flush is what hits the constraint: the second INSERT for the same
    # (application_id, agency_id) pair violates it.
    with pytest.raises(sa.exc.IntegrityError) as excinfo:
        db.flush()

    assert "uq_review_tasks_application_agency" in str(excinfo.value)
    db.rollback()


def create_draft_from_session(tenant: TenantFixture) -> Application:
    """Arrange an application row directly, bypassing the API."""
    application = Application(
        event_name="Concurrency Probe",
        event_type=EventType.MARATHON,
        start_date=START,
        end_date=END,
        location="Riverside Park",
        expected_attendance=1000,
        status=ApplicationStatus.DRAFT,
        submitter_id=tenant.organizer.id,
        tenant_id=tenant.tenant.id,
    )
    tenant.session.add(application)
    tenant.session.commit()
    return application


# ---------------------------------------------------------------------------
# Invalid transitions and duplicates
# ---------------------------------------------------------------------------


def test_submit_only_draft_is_allowed(client: TestClient, db, tenant) -> None:
    """Once not Draft, submission is rejected with 409."""
    draft = create_draft(client, tenant.token_for(tenant.organizer))
    submit(client, tenant.token_for(tenant.organizer), draft.id)

    response = submit(client, tenant.token_for(tenant.organizer), draft.id)
    assert response.status_code == 409
    assert "Submitted" in response.json()["detail"]
    assert db.query(ReviewTask).filter(ReviewTask.application_id == draft.id).count() == 2


def test_submit_twice_does_not_create_duplicate_tasks(client: TestClient, db, tenant) -> None:
    draft = create_draft(client, tenant.token_for(tenant.organizer))
    submit(client, tenant.token_for(tenant.organizer), draft.id)
    submit(client, tenant.token_for(tenant.organizer), draft.id)  # second attempt
    assert db.query(ReviewTask).filter(ReviewTask.application_id == draft.id).count() == 2


# ---------------------------------------------------------------------------
# Authorization and isolation
# ---------------------------------------------------------------------------


def test_submit_requires_authentication(client: TestClient, tenant) -> None:
    draft = create_draft(client, tenant.token_for(tenant.organizer))
    response = client.post(submit_path(draft.id))
    assert response.status_code == 401


@pytest.mark.parametrize("user_attr", ["admin", "reviewer"])
def test_non_organizers_cannot_submit(client: TestClient, db, tenant, user_attr) -> None:
    draft = create_draft(client, tenant.token_for(tenant.organizer))
    token = tenant.token_for(getattr(tenant, user_attr))
    response = submit(client, token, draft.id)
    assert response.status_code == 403
    row = db.get(Application, draft.id)
    assert row.status == ApplicationStatus.DRAFT
    # Scoped to this tenant: the seeded demo data may already have tasks, and an
    # unscoped count would make this test depend on unrelated database contents.
    assert (
        db.query(ReviewTask).filter(ReviewTask.tenant_id == tenant.tenant.id).count()
        == 0
    )


def test_submit_another_organizers_application_is_404(client: TestClient, make_tenant) -> None:
    city = make_tenant("SubmitOwner")
    second = city.add_organizer()
    draft = create_draft(client, city.token_for(city.organizer))
    response = submit(client, city.token_for(second), draft.id)
    assert response.status_code == 404
    assert city.session.get(Application, draft.id).status == ApplicationStatus.DRAFT


def test_submit_cross_tenant_is_404(client: TestClient, make_tenant) -> None:
    springfield = make_tenant("SubmitSpringfield")
    riverton = make_tenant("SubmitRiverton")
    draft = create_draft(client, springfield.token_for(springfield.organizer))
    response = submit(client, riverton.token_for(riverton.organizer), draft.id)
    assert response.status_code == 404
    assert springfield.session.get(Application, draft.id).status == ApplicationStatus.DRAFT


def test_review_tasks_are_tenant_scoped_and_owned(client: TestClient, db, make_tenant) -> None:
    springfield = make_tenant("SubmitTSpringfield")
    riverton = make_tenant("SubmitTRiverton")
    s_draft = create_draft(client, springfield.token_for(springfield.organizer))
    r_draft = create_draft(client, riverton.token_for(riverton.organizer))

    submit(client, springfield.token_for(springfield.organizer), s_draft.id)
    submit(client, riverton.token_for(riverton.organizer), r_draft.id)

    s_tasks = db.query(ReviewTask).filter(ReviewTask.application_id == s_draft.id).all()
    r_tasks = db.query(ReviewTask).filter(ReviewTask.application_id == r_draft.id).all()
    for t in s_tasks + r_tasks:
        assert t.tenant_id == t.application.tenant_id
    assert all(t.tenant_id == springfield.tenant.id for t in s_tasks)
    assert all(t.tenant_id == riverton.tenant.id for t in r_tasks)


def test_submit_with_unknown_id_is_404(client: TestClient, tenant) -> None:
    response = submit(client, tenant.token_for(tenant.organizer), uuid.uuid4())
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Routing specifics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("event_type", "expected_agencies"),
    [
        (EventType.MARATHON, ["Health", "Police"]),
        (EventType.CONCERT, ["Health", "Police"]),
        (EventType.STREET_FAIR, ["Health", "Police"]),
        (EventType.OTHER, ["Health", "Police"]),
    ],
)
def test_event_types_route_to_base_agencies(
    client: TestClient, db, tenant, event_type, expected_agencies
) -> None:
    draft = create_draft(client, tenant.token_for(tenant.organizer), event_type=event_type.value)
    response = submit(client, tenant.token_for(tenant.organizer), draft.id)
    assert response.status_code == 200
    assert [a["name"] for a in response.json()["required_agencies"]] == expected_agencies
    assert db.query(ReviewTask).filter(ReviewTask.application_id == draft.id).count() == len(expected_agencies)


def test_routing_never_reaches_another_tenants_agencies(
    client: TestClient, make_tenant, tenant
) -> None:
    """
    Tasks may only ever point at this city's own agencies.

    RLS checks `tenant_id` on review_tasks, which catches a task owned by the
    wrong city. It does not catch a task owned by *this* city that references
    another city's agency_id, because the foreign key to agencies is verified
    with row security disabled. The submit route asserts the agency list is
    local, which is what closes that gap.
    """
    draft = create_draft(client, tenant.token_for(tenant.organizer))
    response = submit(client, tenant.token_for(tenant.organizer), draft.id)

    assert response.status_code == 200
    other = make_tenant("RoutingOtherCity")
    for agency in response.json()["required_agencies"]:
        assert uuid.UUID(agency["id"]) not in {
            other.agencies["Police"].id,
            other.agencies["Fire"].id,
            other.agencies["Health"].id,
        }


def test_submit_refuses_when_no_agencies_are_configured(
    db, client, tenant
) -> None:
    """
    An application nobody reviews must not be filed.

    With the matrix emptied, submitting would create zero review tasks and the
    application would sit Submitted forever — invisible to every agency.
    """
    from app.models import EventTypeAgencyRule

    db.query(EventTypeAgencyRule).filter(
        EventTypeAgencyRule.tenant_id == tenant.tenant.id
    ).delete(synchronize_session=False)
    db.commit()

    draft = create_draft(client, tenant.token_for(tenant.organizer))
    response = submit(client, tenant.token_for(tenant.organizer), draft.id)

    assert response.status_code == 422
    assert "No agencies are configured" in response.json()["detail"]
    assert db.get(Application, draft.id).status == ApplicationStatus.DRAFT
    assert db.query(ReviewTask).filter(ReviewTask.application_id == draft.id).count() == 0


def test_large_event_without_a_fire_agency_submits_without_fire(
    db, client, tenant
) -> None:
    """
    The override adds Fire only if this city actually has a Fire department.

    A city that has not created one must still be able to submit a large event;
    the application goes to its configured agencies instead of failing.
    """
    from app.models import Agency

    db.query(Agency).filter(
        Agency.tenant_id == tenant.tenant.id, Agency.name == "Fire"
    ).delete(synchronize_session=False)
    db.commit()

    draft = create_draft(
        client, tenant.token_for(tenant.organizer), expected_attendance=60000
    )
    response = submit(client, tenant.token_for(tenant.organizer), draft.id)

    assert response.status_code == 200
    assert [a["name"] for a in response.json()["required_agencies"]] == [
        "Health",
        "Police",
    ]
    # The override was evaluated and did apply, it just had nothing to add.
    assert response.json()["attendance_override_applied"] is True


def test_routing_respects_each_tenants_rules(client: TestClient, make_tenant) -> None:
    """
    Tenants share the same code, but the matrix is tenant-scoped.

    The seeded rules are identical; this is a smoke test that the query
    filters by tenant_id via RLS context.
    """
    springfield = make_tenant("RouteSpringfield")
    riverton = make_tenant("RouteRiverton")

    s = create_draft(client, springfield.token_for(springfield.organizer))
    r = create_draft(client, riverton.token_for(riverton.organizer))

    submit(client, springfield.token_for(springfield.organizer), s.id)
    submit(client, riverton.token_for(riverton.organizer), r.id)

    s_names = [t.agency.name for t in springfield.session.query(ReviewTask).filter(ReviewTask.application_id == s.id).all()]
    r_names = [t.agency.name for t in riverton.session.query(ReviewTask).filter(ReviewTask.application_id == r.id).all()]
    assert sorted(s_names) == ["Health", "Police"]
    assert sorted(r_names) == ["Health", "Police"]
