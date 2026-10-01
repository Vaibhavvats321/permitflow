"""
Tests for organizer tracking and resubmission.

Covers:
- Organizer list and detail showing per-agency review progress
- Ownership and tenant isolation on tracking endpoints
- Editing a draft, and editing an application sent back for changes
- Refusing edits to Submitted, Under Review, Approved and Rejected
- Resubmission validity, completeness, and duplicate prevention
- Selective task reset: changes-requested resets, approvals preserved,
  rejections never reopened
- Audit history for edits, resets and resubmission
- Concurrent resubmission

Tests run against the real database through the restricted application role, so
the RLS path is exercised rather than mocked.
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Application,
    ApplicationStatus,
    AuditEvent,
    EventType,
    ReviewStatus,
    ReviewTask,
)
from tests.conftest import TenantFixture

APPLICATIONS = "/applications"

# Long enough that a request which *can* run to completion will have done so.
_LOCK_WAIT_SECONDS = 1.5

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


def _scoped_session(tenant_id: uuid.UUID) -> Session:
    """
    A session on the restricted application role with the tenant GUC pinned.

    Transaction-local, matching `get_tenant_db`: a session-scoped setting would
    survive commit on that pooled backend and leak the tenant into the next
    test that draws the connection.
    """
    session = SessionLocal()
    session.execute(
        sa.text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
    return session


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def tenant(make_tenant) -> TenantFixture:
    """A tenant with a Police reviewer and a Health reviewer."""
    fixture = make_tenant("ResubmitTenant", with_reviewer=True)
    fixture.health_reviewer = fixture.add_reviewer_for("Health")
    return fixture


def create_draft(client: TestClient, token: str, **overrides) -> uuid.UUID:
    payload = {**VALID_PAYLOAD, **overrides}
    response = client.post(APPLICATIONS, json=payload, headers=auth(token))
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def submit(client: TestClient, token: str, application_id) -> dict:
    response = client.post(
        f"{APPLICATIONS}/{application_id}/submit", headers=auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


def agency_id_for(db, fixture: TenantFixture, agency_name: str):
    return fixture.agencies[agency_name].id


def agency_task(
    client: TestClient, fixture: TenantFixture, application_id, agency_name
) -> str:
    """
    The review task id for one agency on one application.

    Found by scanning each reviewer's queue for the task whose `agency_id`
    matches. Avoids depending on the submit response, so the tests do not have to
    thread a second piece of state through every helper.
    """
    agency_id = str(fixture.agencies[agency_name].id)
    for reviewer in (fixture.reviewer, fixture.health_reviewer):
        response = client.get(
            "/review-tasks", headers=auth(fixture.token_for(reviewer))
        )
        assert response.status_code == 200, response.text
        for task in response.json():
            if (
                task["application_id"] == str(application_id)
                and task["agency_id"] == agency_id
            ):
                return task["id"]
    raise AssertionError(f"no review task for {agency_name}")


def decide(
    client: TestClient,
    fixture: TenantFixture,
    application_id,
    agency_name: str,
    action: str,
    comment: str = "Reviewed.",
):
    task_id = agency_task(client, fixture, application_id, agency_name)
    reviewer = fixture.reviewer if agency_name == "Police" else fixture.health_reviewer
    return client.post(
        f"/review-tasks/{task_id}/decision",
        json={"action": action, "comment": comment},
        headers=auth(fixture.token_for(reviewer)),
    )


def application_status(db, application_id) -> ApplicationStatus:
    return db.get(Application, uuid.UUID(str(application_id))).status


def task_status(db, application_id, agency_name: str, fixture: TenantFixture):
    """The review task status for one agency, read straight from the database."""
    return (
        db.query(ReviewTask)
        .filter(
            ReviewTask.application_id == uuid.UUID(str(application_id)),
            ReviewTask.agency_id == fixture.agencies[agency_name].id,
        )
        .one()
        .status
    )


# ---------------------------------------------------------------------------
# Helpers for setting up review states
# ---------------------------------------------------------------------------


def submitted_changes_requested(
    client: TestClient, fixture: TenantFixture, db=None, **overrides
) -> uuid.UUID:
    """An application where Police requested changes and Health approved."""
    token = fixture.token_for(fixture.organizer)
    application_id = create_draft(client, token, **overrides)
    submit(client, token, application_id)

    decide(client, fixture, application_id, "Police", "request_changes", "Add a site plan.")
    decide(client, fixture, application_id, "Health", "approve", "Health is fine.")

    if db is not None:
        assert application_status(db, application_id) == ApplicationStatus.CHANGES_REQUESTED
    return application_id


# ---------------------------------------------------------------------------
# 1. Organizer tracking
# ---------------------------------------------------------------------------


def test_detail_includes_agency_wise_review_status(
    client: TestClient, tenant
) -> None:
    """The organizer sees each agency's decision, comment and timestamps."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)
    submit(client, token, application_id)

    decide(client, tenant, application_id, "Police", "approve", "Route plan agreed.")
    decide(client, tenant, application_id, "Health", "request_changes", "Need a site plan.")

    response = client.get(f"{APPLICATIONS}/{application_id}", headers=auth(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ApplicationStatus.CHANGES_REQUESTED.value

    reviews = {r["agency_name"]: r for r in body["reviews"]}
    assert set(reviews) == {"Police", "Health"}
    # Sorted by agency name, so the tracking view has a stable order.
    assert [r["agency_name"] for r in body["reviews"]] == ["Health", "Police"]

    assert reviews["Police"]["review_status"] == ReviewStatus.APPROVED.value
    assert reviews["Police"]["comment"] == "Route plan agreed."
    assert reviews["Health"]["review_status"] == ReviewStatus.CHANGES_REQUESTED.value
    assert reviews["Health"]["comment"] == "Need a site plan."

    for review in body["reviews"]:
        assert review["created_at"] is not None
        assert review["updated_at"] is not None
        assert review["agency_id"] is not None


def test_draft_detail_has_empty_reviews(client: TestClient, tenant) -> None:
    """A draft has no reviewers, so the list is empty rather than absent."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)

    response = client.get(f"{APPLICATIONS}/{application_id}", headers=auth(token))

    assert response.status_code == 200
    assert response.json()["reviews"] == []


def test_pending_task_has_no_comment(client: TestClient, tenant) -> None:
    """A task nobody has decided on has no comment, not an empty string."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)
    submit(client, token, application_id)

    response = client.get(f"{APPLICATIONS}/{application_id}", headers=auth(token))

    assert all(r["review_status"] == ReviewStatus.PENDING.value for r in response.json()["reviews"])
    assert all(r["comment"] is None for r in response.json()["reviews"])


def test_list_includes_review_progress(client: TestClient, tenant) -> None:
    """The organizer's list carries the same per-agency detail as the detail view."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)
    submit(client, token, application_id)
    decide(client, tenant, application_id, "Police", "approve", "Police ok.")

    response = client.get(APPLICATIONS, headers=auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == ApplicationStatus.UNDER_REVIEW.value
    reviews = {r["agency_name"]: r for r in body[0]["reviews"]}
    assert reviews["Police"]["review_status"] == ReviewStatus.APPROVED.value
    assert reviews["Health"]["review_status"] == ReviewStatus.PENDING.value


def test_tracking_does_not_expose_another_organizers_application(
    client: TestClient, tenant
) -> None:
    """Two organizers in one tenant are kept apart by ownership, not by RLS."""
    other = tenant.add_organizer()
    token = tenant.token_for(other)
    application_id = create_draft(client, token)
    submit(client, token, application_id)

    mine = client.get(
        f"{APPLICATIONS}/{application_id}", headers=auth(tenant.token_for(tenant.organizer))
    )
    listed = client.get(APPLICATIONS, headers=auth(tenant.token_for(tenant.organizer)))

    assert mine.status_code == 404
    assert application_id not in [a["id"] for a in listed.json()]


def test_tracking_does_not_expose_another_tenants_application(
    client: TestClient, make_tenant
) -> None:
    home = make_tenant("HomeTenant", with_reviewer=True)
    away = make_tenant("AwayTenant", with_reviewer=True)
    away_token = away.token_for(away.organizer)
    application_id = create_draft(client, away_token)
    submit(client, away_token, application_id)

    response = client.get(
        f"{APPLICATIONS}/{application_id}",
        headers=auth(home.token_for(home.organizer)),
    )
    listed = client.get(APPLICATIONS, headers=auth(home.token_for(home.organizer)))

    assert response.status_code == 404
    assert listed.json() == []


def test_history_of_another_organizers_application_is_404(client: TestClient, tenant) -> None:
    other = tenant.add_organizer()
    token = tenant.token_for(other)
    application_id = create_draft(client, token)

    response = client.get(
        f"{APPLICATIONS}/{application_id}/history",
        headers=auth(tenant.token_for(tenant.organizer)),
    )

    assert response.status_code == 404


@pytest.mark.parametrize("role_field", ["reviewer", "health_reviewer", "admin"])
def test_non_organizers_cannot_track_applications(
    client: TestClient, tenant, role_field
) -> None:
    """Tracking is organizer-scoped; reviewers keep their own queue."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)

    other_token = tenant.token_for(getattr(tenant, role_field))
    assert client.get(APPLICATIONS, headers=auth(other_token)).status_code == 403
    assert (
        client.get(
            f"{APPLICATIONS}/{application_id}", headers=auth(other_token)
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"{APPLICATIONS}/{application_id}/history", headers=auth(other_token)
        ).status_code
        == 403
    )


def test_history_requires_authentication(client: TestClient, tenant) -> None:
    application_id = create_draft(client, tenant.token_for(tenant.organizer))

    assert client.get(APPLICATIONS).status_code == 401
    assert client.get(f"{APPLICATIONS}/{application_id}").status_code == 401
    assert client.get(f"{APPLICATIONS}/{application_id}/history").status_code == 401


def test_history_is_empty_for_a_draft(client: TestClient, tenant) -> None:
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)

    response = client.get(f"{APPLICATIONS}/{application_id}/history", headers=auth(token))

    assert response.status_code == 200
    assert response.json()["events"] == []


# ---------------------------------------------------------------------------
# 2. Editing after changes requested
# ---------------------------------------------------------------------------


def test_draft_can_still_be_edited(client: TestClient, db, tenant) -> None:
    """Normal Draft editing is unchanged."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)

    response = client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "location": "Different Park"},
        headers=auth(token),
    )

    assert response.status_code == 200
    assert response.json()["location"] == "Different Park"
    assert db.get(Application, application_id).location == "Different Park"


def test_changes_requested_application_can_be_edited(client: TestClient, db, tenant) -> None:
    """The state an agency sends it back in is exactly when editing is useful."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    response = client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "location": "Riverside Park (north entrance)", "expected_attendance": 4000},
        headers=auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["location"] == "Riverside Park (north entrance)"
    row = db.get(Application, application_id)
    assert row.location == "Riverside Park (north entrance)"
    assert row.expected_attendance == 4000
    # Editing does not itself resubmit: the application stays in Changes Requested
    # until the organizer asks for it.
    assert row.status == ApplicationStatus.CHANGES_REQUESTED


def test_edit_uses_existing_schema_validation(client: TestClient, tenant) -> None:
    """The same field rules apply as on a draft."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)

    bad_name = client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "event_name": "   "},
        headers=auth(token),
    )
    negative = client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "expected_attendance": -5},
        headers=auth(token),
    )
    reversed_dates = client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "start_date": END.isoformat(), "end_date": START.isoformat()},
        headers=auth(token),
    )

    assert bad_name.status_code == 422
    assert negative.status_code == 422
    assert reversed_dates.status_code == 422


def test_edit_cannot_set_server_owned_fields(client: TestClient, tenant) -> None:
    """`extra="forbid"` still protects status and ownership."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)

    response = client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "status": ApplicationStatus.APPROVED.value},
        headers=auth(token),
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "setup, expected",
    [
        ("submitted", ApplicationStatus.SUBMITTED),
        ("under_review", ApplicationStatus.UNDER_REVIEW),
        ("approved", ApplicationStatus.APPROVED),
        ("rejected", ApplicationStatus.REJECTED),
    ],
)
def test_edit_is_refused_outside_editable_states(
    client: TestClient, db, tenant, setup, expected
) -> None:
    """Submitted, Under Review, Approved and Rejected are all closed to edits."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)
    submit(client, token, application_id)

    if setup == "submitted":
        pass
    elif setup == "under_review":
        decide(client, tenant, application_id, "Police", "approve", "Police ok.")
    elif setup == "approved":
        decide(client, tenant, application_id, "Police", "approve", "Police ok.")
        decide(client, tenant, application_id, "Health", "approve", "Health ok.")
    elif setup == "rejected":
        decide(client, tenant, application_id, "Police", "reject", "No permit.")

    assert application_status(db, application_id) == expected

    response = client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "location": "Somewhere else"},
        headers=auth(token),
    )

    assert response.status_code == 409, response.text
    # The refused edit changed nothing.
    assert db.get(Application, application_id).location == VALID_PAYLOAD["location"]


def test_edit_of_another_organizers_application_is_404(client: TestClient, tenant) -> None:
    other = tenant.add_organizer()
    application_id = create_draft(client, tenant.token_for(other))

    response = client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "location": "Hijacked"},
        headers=auth(tenant.token_for(tenant.organizer)),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 3. Resubmission
# ---------------------------------------------------------------------------


def test_resubmission_resets_only_changes_requested_tasks(
    client: TestClient, db, tenant
) -> None:
    """The central rule: only the agencies that asked for changes go back."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "description": "Now with a site plan."},
        headers=auth(token),
    )
    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert [a["name"] for a in body["reset_agencies"]] == ["Police"]
    # Health had already approved; its approval stands.
    assert [a["name"] for a in body["preserved_agencies"]] == ["Health"]
    assert body["still_pending_agencies"] == []

    assert task_status(db, application_id, "Police", tenant) == ReviewStatus.PENDING
    assert task_status(db, application_id, "Health", tenant) == ReviewStatus.APPROVED


def test_resubmission_clears_the_reset_task_comment_but_keeps_the_approval(
    client: TestClient, db, tenant
) -> None:
    """
    The comment described the previous submission.

    Leaving it on a Pending task would misattribute it as feedback about the
    corrected application, so it is cleared. The agency's words remain in the
    audit trail.
    """
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    client.post(f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token))

    police_id = tenant.agencies["Police"].id
    police_task = (
        db.query(ReviewTask)
        .filter(
            ReviewTask.application_id == application_id,
            ReviewTask.agency_id == police_id,
        )
        .one()
    )
    assert police_task.comment is None
    assert police_task.status == ReviewStatus.PENDING

    health_task = (
        db.query(ReviewTask)
        .filter(
            ReviewTask.application_id == application_id,
            ReviewTask.agency_id == tenant.agencies["Health"].id,
        )
        .one()
    )
    # The preserved approval keeps both its status and its comment.
    assert health_task.comment == "Health is fine."


def test_resubmission_preserves_the_previous_decision_in_the_audit_trail(
    client: TestClient, db, tenant
) -> None:
    """Resetting a task must not erase what the agency originally said."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    client.post(f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token))

    response = client.get(f"{APPLICATIONS}/{application_id}/history", headers=auth(token))
    actions = [e["action"] for e in response.json()["events"]]

    assert "review.changes_requested" in actions
    assert "review.task_reset" in actions
    assert "application.resubmitted" in actions


def test_resubmission_when_every_agency_requested_changes(
    client: TestClient, db, tenant
) -> None:
    """Both agencies asked, so both go back and the application restarts clean."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)
    submit(client, token, application_id)
    decide(client, tenant, application_id, "Police", "request_changes", "Site plan please.")
    decide(client, tenant, application_id, "Health", "request_changes", "Noise assessment.")

    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert sorted(a["name"] for a in body["reset_agencies"]) == ["Health", "Police"]
    assert body["preserved_agencies"] == []
    # Nothing has been decided since, so this is Submitted rather than Under
    # Review: a fresh submission, not a partially-reviewed one.
    assert body["application"]["status"] == ApplicationStatus.SUBMITTED.value
    assert application_status(db, application_id) == ApplicationStatus.SUBMITTED
    assert task_status(db, application_id, "Police", tenant) == ReviewStatus.PENDING
    assert task_status(db, application_id, "Health", tenant) == ReviewStatus.PENDING


def test_resubmission_with_a_preserved_approval_is_under_review(
    client: TestClient, db, tenant
) -> None:
    """A retained approval means the application is not brand new."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
    )

    assert response.json()["application"]["status"] == ApplicationStatus.UNDER_REVIEW.value


def test_resubmission_leaves_untouched_agencies_pending(
    client: TestClient, db, tenant
) -> None:
    """
    An agency that never decided stays Pending.

    Large events route to Fire as well as Police and Health; if Police requests
    changes and Health has not yet acted, Fire must not be reset or dropped.
    """
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token, expected_attendance=6000)
    submit(client, token, application_id)
    decide(client, tenant, application_id, "Police", "request_changes", "Site plan.")

    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert [a["name"] for a in body["reset_agencies"]] == ["Police"]
    assert sorted(a["name"] for a in body["still_pending_agencies"]) == ["Fire", "Health"]
    assert task_status(db, application_id, "Health", tenant) == ReviewStatus.PENDING


def test_resubmission_preserves_the_agency_set(client: TestClient, db, tenant) -> None:
    """No new review tasks are created, so routing is not re-evaluated."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    before = len(client.get(APPLICATIONS, headers=auth(token)).json()[0]["reviews"])
    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
    )
    after = len(response.json()["application"]["reviews"])

    assert before == after == 2


@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.DRAFT,
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.APPROVED,
        ApplicationStatus.REJECTED,
    ],
)
def test_resubmission_is_refused_outside_changes_requested(
    client: TestClient, db, tenant, status
) -> None:
    """Only Changes Requested may be resubmitted."""
    token = tenant.token_for(tenant.organizer)

    if status is ApplicationStatus.DRAFT:
        application_id = create_draft(client, token)
    else:
        application_id = create_draft(client, token)
        submit(client, token, application_id)
        if status is ApplicationStatus.UNDER_REVIEW:
            decide(client, tenant, application_id, "Police", "approve", "Police ok.")
        elif status is ApplicationStatus.APPROVED:
            decide(client, tenant, application_id, "Police", "approve", "Police ok.")
            decide(client, tenant, application_id, "Health", "approve", "Health ok.")
        elif status is ApplicationStatus.REJECTED:
            decide(client, tenant, application_id, "Police", "reject", "No.")

    assert application_status(db, application_id) == status

    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
    )

    assert response.status_code == 409, response.text
    assert application_status(db, application_id) == status


def test_resubmission_validates_required_fields(client: TestClient, db, tenant) -> None:
    """Resubmitting an application that is still incomplete is refused."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    # An agency can request changes while the application is incomplete only if
    # it slipped past submission validation, so clear a required field directly.
    db.get(Application, application_id).location = None
    db.commit()

    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
    )

    assert response.status_code == 422, response.text
    assert "location" in response.json()["detail"]
    # No task was reset.
    assert task_status(db, application_id, "Police", tenant) == ReviewStatus.CHANGES_REQUESTED


def test_duplicate_resubmission_is_refused(client: TestClient, db, tenant) -> None:
    """The second resubmit finds no changes-requested task left to reset."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    first = client.post(f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token))
    assert first.status_code == 200

    second = client.post(f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token))
    assert second.status_code == 409

    # The application's own status also refuses it, which is the first check hit.
    assert application_status(db, application_id) in (
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
    )


def test_resubmission_of_another_organizers_application_is_404(
    client: TestClient, tenant
) -> None:
    other = tenant.add_organizer()
    other_token = tenant.token_for(other)
    application_id = create_draft(client, other_token)
    submit(client, other_token, application_id)
    decide(client, tenant, application_id, "Police", "request_changes", "Site plan.")

    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit",
        headers=auth(tenant.token_for(tenant.organizer)),
    )

    assert response.status_code == 404


def test_resubmission_of_another_tenants_application_is_404(
    client: TestClient, make_tenant
) -> None:
    home = make_tenant("HomeTenant", with_reviewer=True)
    away = make_tenant("AwayTenant", with_reviewer=True)
    away_token = away.token_for(away.organizer)
    application_id = create_draft(client, away_token)
    submit(client, away_token, application_id)

    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit",
        headers=auth(home.token_for(home.organizer)),
    )

    assert response.status_code == 404


@pytest.mark.parametrize("role_field", ["reviewer", "health_reviewer", "admin"])
def test_non_organizers_cannot_resubmit(client: TestClient, tenant, role_field) -> None:
    """Resubmission is an organizer action."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, None)

    other_token = tenant.token_for(getattr(tenant, role_field))
    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(other_token)
    )

    assert response.status_code == 403


def test_resubmission_requires_authentication(client: TestClient, tenant) -> None:
    application_id = submitted_changes_requested(client, tenant, None)

    response = client.post(f"{APPLICATIONS}/{application_id}/resubmit")

    assert response.status_code == 401


def test_resubmitted_application_can_be_reviewed_again(client: TestClient, db, tenant) -> None:
    """The reset task is genuinely re-reviewable, not just relabelled."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "description": "Site plan attached."},
        headers=auth(token),
    )
    client.post(f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token))

    response = decide(
        client, tenant, application_id, "Police", "approve", "Site plan is fine now."
    )

    assert response.status_code == 200, response.text
    assert response.json()["application_status"] == ApplicationStatus.APPROVED.value
    assert application_status(db, application_id) == ApplicationStatus.APPROVED


def test_rejected_agency_is_never_reopened_by_resubmission(
    client: TestClient, db, tenant
) -> None:
    """
    A rejection has no reversal.

    In practice this is unreachable: a rejected task makes the application
    Rejected, which cannot be resubmitted at all. The test asserts the guard
    directly by forcing the inconsistent state, so the refusal is a deliberate
    check rather than an accident of the ordering.
    """
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)
    submit(client, token, application_id)

    police_id = tenant.agencies["Police"].id
    police_task = (
        db.query(ReviewTask)
        .filter(
            ReviewTask.application_id == application_id, ReviewTask.agency_id == police_id
        )
        .one()
    )
    police_task.status = ReviewStatus.CHANGES_REQUESTED
    police_task.comment = "Site plan please."
    health_task = (
        db.query(ReviewTask)
        .filter(
            ReviewTask.application_id == application_id,
            ReviewTask.agency_id == tenant.agencies["Health"].id,
        )
        .one()
    )
    health_task.status = ReviewStatus.REJECTED
    health_task.comment = "No."
    db.get(Application, application_id).status = ApplicationStatus.CHANGES_REQUESTED
    db.commit()

    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
    )

    assert response.status_code == 409
    assert "rejected" in response.json()["detail"].lower()
    db.expire_all()
    assert db.query(ReviewTask).filter_by(id=police_task.id).one().status == ReviewStatus.CHANGES_REQUESTED
    assert db.query(ReviewTask).filter_by(id=health_task.id).one().status == ReviewStatus.REJECTED


def test_resubmission_refused_when_no_agency_requests_changes(
    client: TestClient, db, tenant
) -> None:
    """
    The application says Changes Requested but no task does.

    Rather than resetting nothing and moving the application back to Submitted,
    the endpoint refuses. The state is inconsistent and silently "fixing" it would
    misreport what the agencies actually did.
    """
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)
    submit(client, token, application_id)

    db.get(Application, application_id).status = ApplicationStatus.CHANGES_REQUESTED
    db.commit()

    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
    )

    assert response.status_code == 409
    assert "requesting changes" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 4. Audit trail
# ---------------------------------------------------------------------------


def test_edit_writes_an_audit_event_describing_the_change(
    client: TestClient, db, tenant
) -> None:
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    response = client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "location": "Riverside Park North", "expected_attendance": 4200},
        headers=auth(token),
    )
    assert response.status_code == 200

    event = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.application_id == application_id,
            AuditEvent.action == "application.edited",
        )
        .one()
    )
    assert event.user_id == tenant.organizer.id
    assert event.tenant_id == tenant.tenant.id
    # No agency: the organizer acted.
    assert event.agency_id is None
    assert event.old_status == ApplicationStatus.CHANGES_REQUESTED.value
    assert event.new_status == ApplicationStatus.CHANGES_REQUESTED.value
    assert "location" in event.comment
    assert "expected_attendance" in event.comment
    assert event.created_at is not None


def test_edit_that_changes_nothing_writes_no_audit_event(
    client: TestClient, db, tenant
) -> None:
    """Resubmitting identical values is not a meaningful change."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    response = client.put(
        f"{APPLICATIONS}/{application_id}", json=VALID_PAYLOAD, headers=auth(token)
    )

    assert response.status_code == 200
    count = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.application_id == application_id,
            AuditEvent.action == "application.edited",
        )
        .count()
    )
    assert count == 0


def test_resubmission_writes_audit_events(client: TestClient, db, tenant) -> None:
    """Reset, resubmission and the derived status change are all recorded."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    response = client.post(
        f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
    )
    assert response.status_code == 200

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.application_id == application_id)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        .all()
    )
    actions = [e.action for e in events]

    assert "application.edited" not in actions  # no edit in this test
    assert "application.resubmitted" in actions
    assert "review.task_reset" in actions
    assert "application.status_changed" in actions

    reset = next(e for e in events if e.action == "review.task_reset")
    assert reset.agency_id == tenant.agencies["Police"].id
    assert reset.old_status == ReviewStatus.CHANGES_REQUESTED.value
    assert reset.new_status == ReviewStatus.PENDING.value

    resubmitted = next(e for e in events if e.action == "application.resubmitted")
    assert resubmitted.old_status == ApplicationStatus.CHANGES_REQUESTED.value
    assert resubmitted.new_status == ApplicationStatus.UNDER_REVIEW.value
    assert "1 agency review" in resubmitted.comment
    assert "1 approval" in resubmitted.comment

    # Three status changes in this application's life: Draft -> Submitted on
    # submit, Submitted -> Changes Requested when Police asked, then the one
    # resubmission caused.
    status_changes = [e for e in events if e.action == "application.status_changed"]
    assert len(status_changes) == 3
    resubmission_change = status_changes[-1]
    assert resubmission_change.old_status == ApplicationStatus.CHANGES_REQUESTED.value
    assert resubmission_change.new_status == ApplicationStatus.UNDER_REVIEW.value


def test_history_is_chronological_across_resubmission_cycles(
    client: TestClient, db, tenant
) -> None:
    """A full cycle reads as one ordered sequence."""
    token = tenant.token_for(tenant.organizer)
    application_id = create_draft(client, token)
    submit(client, token, application_id)
    decide(client, tenant, application_id, "Police", "request_changes", "Site plan.")
    client.put(
        f"{APPLICATIONS}/{application_id}",
        json={**VALID_PAYLOAD, "description": "Site plan attached."},
        headers=auth(token),
    )
    client.post(f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token))
    decide(client, tenant, application_id, "Police", "approve", "Accepted.")
    decide(client, tenant, application_id, "Health", "approve", "Accepted.")

    response = client.get(f"{APPLICATIONS}/{application_id}/history", headers=auth(token))

    assert response.status_code == 200
    body = response.json()
    actions = [e["action"] for e in body["events"]]
    assert actions == [
        "application.status_changed",
        "review.changes_requested",
        "application.status_changed",
        "application.edited",
        "review.task_reset",
        "application.resubmitted",
        "application.status_changed",
        "review.approved",
        "application.status_changed",
        "review.approved",
        "application.status_changed",
    ]
    assert body["application_status"] == ApplicationStatus.APPROVED.value
    # Timestamps never go backwards.
    timestamps = [e["created_at"] for e in body["events"]]
    assert timestamps == sorted(timestamps)


def test_history_is_tenant_scoped(client: TestClient, make_tenant) -> None:
    """Audit rows carry the tenant, and no tenant sees another's."""
    home = make_tenant("HomeTenant", with_reviewer=True)
    away = make_tenant("AwayTenant", with_reviewer=True)

    away_token = away.token_for(away.organizer)
    away_application = create_draft(client, away_token)
    submit(client, away_token, away_application)

    home_token = home.token_for(home.organizer)
    home_application = create_draft(client, home_token)
    submit(client, home_token, home_application)

    # Another tenant's application is simply not there.
    response = client.get(
        f"{APPLICATIONS}/{away_application}/history", headers=auth(home_token)
    )
    assert response.status_code == 404

    # And the home organizer's own history contains no foreign audit rows.
    response = client.get(
        f"{APPLICATIONS}/{home_application}/history", headers=auth(home_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["application_id"] == str(home_application)
    assert [e["action"] for e in body["events"]]


def test_refused_resubmission_writes_no_audit_event(client: TestClient, db, tenant) -> None:
    """A refused action leaves no trace."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    before = db.query(AuditEvent).filter(
        AuditEvent.application_id == application_id
    ).count()

    assert (
        client.post(f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)).status_code
        == 200
    )
    client.post(f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token))

    after_first = db.query(AuditEvent).filter(
        AuditEvent.application_id == application_id
    ).count()
    client.post(f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token))
    after_second = db.query(AuditEvent).filter(
        AuditEvent.application_id == application_id
    ).count()

    assert after_first > before
    assert after_second == after_first


# ---------------------------------------------------------------------------
# 5. Concurrency
# ---------------------------------------------------------------------------


def test_concurrent_resubmissions_produce_one_reset(client: TestClient, db, tenant) -> None:
    """
    Two resubmissions at once, forced into the worst-case ordering.

    A thread test alone cannot prove the lock works — the requests may not
    collide at all, in which case the test passes whether or not the lock is
    there. So the collision is manufactured: a separate session holds
    `FOR UPDATE` on the application row, and a resubmission fired from a thread
    must block until it is released.

    Whichever way it interleaves, the tasks are reset exactly once: the second
    request re-reads the status after the first commits and is refused.
    """
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    blocker = _scoped_session(tenant.tenant.id)
    try:
        blocker.execute(
            sa.text("SELECT 1 FROM applications WHERE id = :id FOR UPDATE"),
            {"id": str(application_id)},
        )

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                lambda: client.post(
                    f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
                )
            )
            time.sleep(_LOCK_WAIT_SECONDS)
            assert not pending.done(), (
                "resubmission returned while the application row was locked by "
                "another transaction — the lock is not being taken"
            )
            blocker.commit()
            first = pending.result(timeout=30)

        assert first.status_code == 200, first.text

        second = client.post(
            f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
        )
        assert second.status_code == 409

        # Exactly one round of reset events, from one resubmission.
        resets = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.application_id == application_id,
                AuditEvent.action == "review.task_reset",
            )
            .count()
        )
        assert resets == 1
        assert task_status(db, application_id, "Police", tenant) == ReviewStatus.PENDING
        assert task_status(db, application_id, "Health", tenant) == ReviewStatus.APPROVED
    finally:
        blocker.rollback()
        blocker.close()


def test_resubmission_is_idempotent_under_true_parallel_fire(
    client: TestClient, db, tenant
) -> None:
    """Two genuinely simultaneous resubmissions: one succeeds, one is refused."""
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                lambda: client.post(
                    f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
                )
            )
            for _ in range(2)
        ]
        responses = [f.result(timeout=30) for f in futures]

    statuses = sorted(r.status_code for r in responses)
    assert statuses in ([200, 409], [409, 200]), [r.text for r in responses]

    resets = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.application_id == application_id,
            AuditEvent.action == "review.task_reset",
        )
        .count()
    )
    assert resets == 1


def test_concurrent_edits_do_not_both_apply(client: TestClient, db, tenant) -> None:
    """
    Two edits at once: the application lock serialises them.

    The application row is locked before the editable-status check, so the second
    request re-reads the state the first one left rather than acting on a stale
    read.
    """
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)

    blocker = _scoped_session(tenant.tenant.id)
    try:
        blocker.execute(
            sa.text("SELECT 1 FROM applications WHERE id = :id FOR UPDATE"),
            {"id": str(application_id)},
        )

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                lambda: client.put(
                    f"{APPLICATIONS}/{application_id}",
                    json={**VALID_PAYLOAD, "location": "Second Park"},
                    headers=auth(token),
                )
            )
            time.sleep(_LOCK_WAIT_SECONDS)
            assert not pending.done(), (
                "edit returned while the application row was locked — the lock "
                "is not being taken"
            )
            blocker.commit()
            first = pending.result(timeout=30)

        assert first.status_code == 200
        assert db.get(Application, application_id).location == "Second Park"
        edits = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.application_id == application_id,
                AuditEvent.action == "application.edited",
            )
            .count()
        )
        assert edits == 1
    finally:
        blocker.rollback()
        blocker.close()


def test_resubmission_locks_the_tasks_before_the_application(
    client: TestClient, db, tenant
) -> None:
    """
    The lock order that keeps organizer and reviewer from deadlocking.

    The reviewer decision path takes two locks: its own review task, then the
    application. Resubmission needs both of them too, so it has to take them in
    the same order. If it took the application first, an organizer resubmitting
    while a reviewer was deciding would leave each transaction holding what the
    other one was waiting for, and Postgres would abort one of them with a
    deadlock error — a 500 to the organizer.

    Lock order is awkward to test through a race, because a deadlock test either
    flakes or passes for the wrong reason. So this asserts the property directly:
    while a resubmission is blocked on a review task, the application row must
    still be unlocked.

    A third session takes the task lock, a resubmission is fired at it and parks
    on that task, and a probe then goes after the application row. Probe wins
    means the resubmission had not taken the application yet — which is exactly
    the ordering that makes the two paths safe. Had it taken the application
    first, the probe would block and the test would fail.
    """
    token = tenant.token_for(tenant.organizer)
    application_id = submitted_changes_requested(client, tenant, db)
    police_task = agency_task(client, tenant, application_id, "Police")

    blocker = _scoped_session(tenant.tenant.id)
    probe = _scoped_session(tenant.tenant.id)
    probe_error: Exception | None = None
    try:
        blocker.execute(
            sa.text("SELECT 1 FROM review_tasks WHERE id = :id FOR UPDATE"),
            {"id": police_task},
        )

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                lambda: client.post(
                    f"{APPLICATIONS}/{application_id}/resubmit", headers=auth(token)
                )
            )
            try:
                time.sleep(_LOCK_WAIT_SECONDS)
                assert not pending.done(), (
                    "resubmission returned while a review task was locked by "
                    "another transaction — the task lock is not being taken"
                )

                # The probe must get the application row. A short lock timeout
                # turns "the resubmission is holding it" into a timeout instead of
                # a second hang.
                try:
                    probe.execute(sa.text("SET LOCAL lock_timeout = '750ms'"))
                    probe.execute(
                        sa.text(
                            "SELECT 1 FROM applications WHERE id = :id FOR UPDATE"
                        ),
                        {"id": str(application_id)},
                    )
                except sa.exc.OperationalError as exc:
                    probe_error = exc
                finally:
                    # The probe now holds the application row it just locked, so
                    # it has to let go of it here. Leaving it locked would park
                    # the resubmission on that row, and the `with` block below
                    # would then wait on a request that can never finish.
                    probe.rollback()

            finally:
                # Always release the task lock before waiting on the request, for
                # the same reason.
                blocker.commit()

            response = pending.result(timeout=30)

        assert probe_error is None, (
            "the application row was already locked while the resubmission was "
            "still waiting on a review task, so resubmission takes its locks in "
            "the opposite order to the reviewer decision path, and the two can "
            f"deadlock: {probe_error}"
        )
        assert response.status_code == 200, response.text
        assert task_status(db, application_id, "Police", tenant) == ReviewStatus.PENDING
        assert task_status(db, application_id, "Health", tenant) == ReviewStatus.APPROVED
    finally:
        probe.rollback()
        probe.close()
        blocker.rollback()
        blocker.close()


# ---------------------------------------------------------------------------
# 6. Lifecycle unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [ApplicationStatus.DRAFT, ApplicationStatus.CHANGES_REQUESTED],
)
def test_editable_application_statuses(status) -> None:
    from app.core.lifecycle import assert_application_editable

    assert_application_editable(status)


@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.APPROVED,
        ApplicationStatus.REJECTED,
    ],
)
def test_non_editable_application_statuses_are_refused(status) -> None:
    from app.core.lifecycle import InvalidStatusTransition, assert_application_editable

    with pytest.raises(InvalidStatusTransition):
        assert_application_editable(status)


@pytest.mark.parametrize(
    "status",
    [ApplicationStatus.DRAFT, ApplicationStatus.SUBMITTED, ApplicationStatus.APPROVED],
)
def test_only_changes_requested_can_be_resubmitted(status) -> None:
    from app.core.lifecycle import (
        InvalidStatusTransition,
        assert_application_resubmittable,
    )

    with pytest.raises(InvalidStatusTransition):
        assert_application_resubmittable(status)


@pytest.mark.parametrize(
    ("task_statuses", "expected"),
    [
        # Every agency asked: a clean restart.
        ([ReviewStatus.PENDING, ReviewStatus.PENDING], ApplicationStatus.SUBMITTED),
        # An approval survived, so the application is not brand new.
        ([ReviewStatus.APPROVED, ReviewStatus.PENDING], ApplicationStatus.UNDER_REVIEW),
        # A rejection still wins, so a rejected task is never revived.
        ([ReviewStatus.APPROVED, ReviewStatus.REJECTED], ApplicationStatus.REJECTED),
    ],
)
def test_resubmission_application_status(task_statuses, expected) -> None:
    from app.core.lifecycle import resubmission_application_status

    assert resubmission_application_status(task_statuses) == expected


@pytest.mark.parametrize(
    ("status", "resets"),
    [
        (ReviewStatus.CHANGES_REQUESTED, True),
        (ReviewStatus.PENDING, False),
        (ReviewStatus.APPROVED, False),
        (ReviewStatus.REJECTED, False),
    ],
)
def test_should_reset_on_resubmission(status, resets) -> None:
    from app.core.lifecycle import should_reset_on_resubmission

    assert should_reset_on_resubmission(status) is resets