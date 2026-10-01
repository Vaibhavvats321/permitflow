"""
Tests for the agency reviewer workflow.

Covers:
- The reviewer's queue is scoped to their own agency and tenant
- Application details are reachable only through a task assigned to them
- Approve / Reject / Request Changes, each requiring a comment
- Invalid transitions (acting twice, acting on a closed application)
- Cross-agency, cross-tenant and wrong-role access
- The derived application status after each combination of decisions
- Audit events written for decisions and status changes
- Duplicate/concurrent action protection

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

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Application,
    ApplicationStatus,
    AuditEvent,
    EventType,
    ReviewStatus,
    ReviewTask,
    User,
    UserRole,
)
from tests.conftest import TEST_PASSWORD, TenantFixture

REVIEW_TASKS = "/review-tasks"

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


# Long enough that a request which *can* run to completion will have done so.
# Used by the lock test to distinguish "blocked on the row lock" from "finished".
_LOCK_WAIT_SECONDS = 1.5


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _scoped_session(tenant_id: uuid.UUID) -> Session:
    """
    A session on the restricted application role with the tenant GUC pinned.

    The blocker in the lock test has to behave like the real request session,
    including its RLS context, or the row lock it takes would be on a row the
    application role cannot even see.
    """
    session = SessionLocal()
    # Transaction-local (`true`), not session-scoped (`false`). A session-scoped
    # setting survives commit on that pooled backend, so the tenant id would
    # stay behind on a connection the next test gets from the pool — which is
    # exactly the leak `test_rls_isolation.py` asserts does not happen. The
    # after_begin hook in `get_tenant_db` uses the same transaction-local form.
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
    """
    A tenant with Police and Health reviewers.

    `with_reviewer=True` gives the Police reviewer (the fixture's default
    `agency`); Health is added explicitly because the aggregate-status tests
    need two agencies deciding independently.
    """
    fixture = make_tenant("ReviewTenant", with_reviewer=True)
    fixture.health_reviewer = fixture.add_reviewer_for("Health")
    return fixture


def create_and_submit(
    client: TestClient, fixture: TenantFixture, **overrides
) -> tuple[uuid.UUID, dict[str, str]]:
    """Create a draft and submit it, returning the application id and tasks."""
    token = fixture.token_for(fixture.organizer)
    payload = {**VALID_PAYLOAD, **overrides}

    created = client.post("/applications", json=payload, headers=auth(token))
    assert created.status_code == 201, created.text
    application_id = uuid.UUID(created.json()["id"])

    submitted = client.post(
        f"/applications/{application_id}/submit", headers=auth(token)
    )
    assert submitted.status_code == 200, submitted.text

    tasks_by_agency = {
        a["name"]: a["id"]
        for a in submitted.json()["required_agencies"]
    }
    return application_id, tasks_by_agency


def task_for(client: TestClient, fixture: TenantFixture, application_id) -> str:
    """The id of the reviewer's own (Police) task on this application."""
    token = fixture.token_for(fixture.reviewer)
    response = client.get(REVIEW_TASKS, headers=auth(token))
    assert response.status_code == 200, response.text
    matches = [
        t for t in response.json() if t["application_id"] == str(application_id)
    ]
    assert len(matches) == 1
    return matches[0]["id"]


def decide(
    client: TestClient, token: str, task_id: str, action: str, comment: str = "Looks fine."
):
    return client.post(
        f"{REVIEW_TASKS}/{task_id}/decision",
        json={"action": action, "comment": comment},
        headers=auth(token),
    )


def application_status(db, application_id: uuid.UUID) -> ApplicationStatus:
    return db.get(Application, application_id).status


# ---------------------------------------------------------------------------
# 1. Reviewer queue
# ---------------------------------------------------------------------------


def test_queue_lists_only_my_agencies_tasks(client: TestClient, db, tenant) -> None:
    """The reviewer sees their agency's task, not the other agency's."""
    application_id, agencies = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)

    response = client.get(REVIEW_TASKS, headers=auth(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    task = body[0]
    assert task["application_id"] == str(application_id)
    assert task["agency_id"] == agencies["Police"]
    assert task["review_status"] == ReviewStatus.PENDING.value
    # Application details travel with the task.
    assert task["application"]["event_name"] == VALID_PAYLOAD["event_name"]
    assert task["application"]["status"] == ApplicationStatus.SUBMITTED.value


def test_queue_excludes_another_agencies_task(client: TestClient, tenant) -> None:
    """Health's reviewer must not see Police's task on the same application."""
    application_id, _ = create_and_submit(client, tenant)

    response = client.get(
        REVIEW_TASKS, headers=auth(tenant.token_for(tenant.health_reviewer))
    )

    assert response.status_code == 200
    ids = [t["application_id"] for t in response.json()]
    # Health *does* have a task on this application, but it is Health's own.
    assert ids == [str(application_id)]
    health_task = response.json()[0]
    assert health_task["agency_id"] != _police_agency_id(tenant)


def _police_agency_id(tenant: TenantFixture) -> str:
    return str(tenant.agencies["Police"].id)


def test_queue_is_empty_for_agency_with_no_tasks(client: TestClient, make_tenant) -> None:
    """A reviewer whose agency has no assignments gets an empty queue, not an error."""
    fixture = make_tenant("QuietTenant", with_reviewer=True)
    response = client.get(
        REVIEW_TASKS, headers=auth(fixture.token_for(fixture.reviewer))
    )
    assert response.status_code == 200
    assert response.json() == []


def test_queue_filters_by_review_status(client: TestClient, tenant) -> None:
    """The status filter narrows to decisions already made."""
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    assert decide(client, token, task_id, "approve").status_code == 200

    approved = client.get(
        f"{REVIEW_TASKS}?status={ReviewStatus.APPROVED.value}", headers=auth(token)
    )
    pending = client.get(
        f"{REVIEW_TASKS}?status={ReviewStatus.PENDING.value}", headers=auth(token)
    )

    assert len(approved.json()) == 1
    assert pending.json() == []


def test_queue_filters_by_event_type(client: TestClient, tenant) -> None:
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)

    matching = client.get(
        f"{REVIEW_TASKS}?event_type={EventType.MARATHON.value}", headers=auth(token)
    )
    other = client.get(
        f"{REVIEW_TASKS}?event_type={EventType.CONCERT.value}", headers=auth(token)
    )

    assert len(matching.json()) == 1
    assert other.json() == []


# ---------------------------------------------------------------------------
# 2. Application detail access
# ---------------------------------------------------------------------------


def test_reviewer_can_read_task_detail(client: TestClient, tenant) -> None:
    application_id, agencies = create_and_submit(client, tenant)
    task_id = task_for(client, tenant, application_id)

    response = client.get(
        f"{REVIEW_TASKS}/{task_id}", headers=auth(tenant.token_for(tenant.reviewer))
    )

    assert response.status_code == 200
    assert response.json()["id"] == task_id
    assert response.json()["application"]["location"] == VALID_PAYLOAD["location"]


def test_reviewer_cannot_read_another_agencies_task(client: TestClient, tenant) -> None:
    """Different agency, same tenant: 404, not 403, and no application leak."""
    application_id, agencies = create_and_submit(client, tenant)

    # Police's task id, requested by Health's reviewer.
    police_task_id = next(
        t["id"]
        for t in client.get(
            REVIEW_TASKS, headers=auth(tenant.token_for(tenant.reviewer))
        ).json()
        if t["application_id"] == str(application_id)
    )

    response = client.get(
        f"{REVIEW_TASKS}/{police_task_id}",
        headers=auth(tenant.token_for(tenant.health_reviewer)),
    )

    assert response.status_code == 404
    assert "Riverside Park" not in response.text


def test_reviewer_cannot_read_another_tenants_task(client: TestClient, make_tenant) -> None:
    """Guessing a task id across tenants finds nothing."""
    home = make_tenant("HomeTenant", with_reviewer=True)
    away = make_tenant("AwayTenant", with_reviewer=True)
    application_id, _ = create_and_submit(client, away)

    away_task_id = next(
        t["id"]
        for t in client.get(
            REVIEW_TASKS, headers=auth(away.token_for(away.reviewer))
        ).json()
        if t["application_id"] == str(application_id)
    )

    response = client.get(
        f"{REVIEW_TASKS}/{away_task_id}", headers=auth(home.token_for(home.reviewer))
    )

    assert response.status_code == 404


def test_reviewer_has_no_route_into_organizer_applications(
    client: TestClient, tenant
) -> None:
    """Reviewers cannot read `/applications` at all, so no ownership bypass."""
    application_id, _ = create_and_submit(client, tenant)

    response = client.get(
        f"/applications/{application_id}", headers=auth(tenant.token_for(tenant.reviewer))
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 3. Review actions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "expected_task_status"),
    [
        ("approve", ReviewStatus.APPROVED),
        ("reject", ReviewStatus.REJECTED),
        ("request_changes", ReviewStatus.CHANGES_REQUESTED),
    ],
)
def test_each_action_records_its_decision(
    client: TestClient, db, tenant, action, expected_task_status
) -> None:
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    response = decide(client, token, task_id, action, "Reviewed on site.")

    assert response.status_code == 200, response.text
    assert response.json()["task"]["review_status"] == expected_task_status.value

    task = db.query(ReviewTask).get(task_id)
    assert task.status == expected_task_status
    assert task.comment == "Reviewed on site."


def test_comment_is_stored_trimmed(client: TestClient, db, tenant) -> None:
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    response = decide(client, token, task_id, "approve", "   Fine by me.   ")

    assert response.status_code == 200
    assert db.query(ReviewTask).get(task_id).comment == "Fine by me."


@pytest.mark.parametrize("comment", ["", "   ", "\n\t "])
def test_blank_comment_is_rejected(client: TestClient, db, tenant, comment) -> None:
    """Every action needs a real comment; whitespace is not a comment."""
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    response = decide(client, token, task_id, "approve", comment)

    assert response.status_code == 422, response.text
    task = db.query(ReviewTask).get(task_id)
    assert task.status == ReviewStatus.PENDING
    assert task.comment is None


def test_missing_comment_field_is_rejected(client: TestClient, tenant) -> None:
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    response = client.post(
        f"{REVIEW_TASKS}/{task_id}/decision",
        json={"action": "approve"},
        headers=auth(token),
    )

    assert response.status_code == 422


def test_unknown_action_is_rejected(client: TestClient, tenant) -> None:
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    response = decide(client, token, task_id, "shrug", "Not a real action.")

    assert response.status_code == 422


def test_reviewer_cannot_send_application_fields(client: TestClient, tenant) -> None:
    """`extra="forbid"` stops a reviewer editing what they are reviewing."""
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    response = client.post(
        f"{REVIEW_TASKS}/{task_id}/decision",
        json={
            "action": "approve",
            "comment": "Fine.",
            "expected_attendance": 10,
            "location": "Elsewhere",
        },
        headers=auth(token),
    )

    assert response.status_code == 422


def test_reviewer_cannot_force_application_status(client: TestClient, tenant) -> None:
    """Nor can a reviewer set the application status directly."""
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    response = client.post(
        f"{REVIEW_TASKS}/{task_id}/decision",
        json={
            "action": "approve",
            "comment": "Fine.",
            "application_status": ApplicationStatus.APPROVED.value,
        },
        headers=auth(token),
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. Wrong role
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role_field", ["organizer", "admin"])
def test_non_reviewers_are_refused(client: TestClient, tenant, role_field) -> None:
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(getattr(tenant, role_field))

    queue = client.get(REVIEW_TASKS, headers=auth(token))
    detail = client.get(
        f"{REVIEW_TASKS}/{uuid.uuid4()}", headers=auth(token)
    )
    task_id = task_for(client, tenant, application_id)
    action = decide(client, token, task_id, "approve")

    assert queue.status_code == 403
    assert detail.status_code == 403
    assert action.status_code == 403


def test_unauthenticated_is_rejected(client: TestClient, tenant) -> None:
    application_id, _ = create_and_submit(client, tenant)
    task_id = task_for(client, tenant, application_id)

    assert client.get(REVIEW_TASKS).status_code == 401
    assert client.get(f"{REVIEW_TASKS}/{task_id}").status_code == 401
    assert (
        client.post(
            f"{REVIEW_TASKS}/{task_id}/decision",
            json={"action": "approve", "comment": "hi"},
        ).status_code
        == 401
    )


def test_reviewer_without_an_agency_is_refused(client: TestClient, db, tenant) -> None:
    """A reviewer with no agency is a data error, reported as such."""
    orphan = User(
        email="orphan-reviewer@example.com",
        password_hash=hash_password(TEST_PASSWORD),
        role=UserRole.AGENCY_REVIEWER,
        tenant_id=tenant.tenant.id,
        agency_id=None,
    )
    db.add(orphan)
    db.commit()

    from app.core.security import create_access_token

    token = create_access_token(
        sub=orphan.id, tenant_id=tenant.tenant.id, role=orphan.role.value
    )
    response = client.get(REVIEW_TASKS, headers=auth(token))

    assert response.status_code == 403
    assert "agency" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 5. Central application status
# ---------------------------------------------------------------------------


def test_first_approval_moves_application_under_review(
    client: TestClient, db, tenant
) -> None:
    """One of two agencies approving is not approval of the permit."""
    application_id, agencies = create_and_submit(client, tenant)

    response = decide(
        client, tenant.token_for(tenant.reviewer), task_for(client, tenant, application_id), "approve"
    )

    assert response.status_code == 200
    assert response.json()["application_status"] == ApplicationStatus.UNDER_REVIEW.value
    assert application_status(db, application_id) == ApplicationStatus.UNDER_REVIEW


def test_all_approvals_approve_the_application(client: TestClient, db, tenant) -> None:
    """Approved only when every required agency has approved."""
    application_id, agencies = create_and_submit(client, tenant)

    decide(
        client,
        tenant.token_for(tenant.reviewer),
        task_for(client, tenant, application_id),
        "approve",
        "Police ok.",
    )
    health_task = _health_task_id(client, tenant, application_id)
    response = decide(
        client, tenant.token_for(tenant.health_reviewer), health_task, "approve", "Health ok."
    )

    assert response.status_code == 200
    assert response.json()["application_status"] == ApplicationStatus.APPROVED.value
    assert application_status(db, application_id) == ApplicationStatus.APPROVED


def test_any_rejection_rejects_the_application(client: TestClient, db, tenant) -> None:
    """One rejection is decisive, even if the other agency approves afterwards."""
    application_id, _ = create_and_submit(client, tenant)

    decide(
        client,
        tenant.token_for(tenant.reviewer),
        task_for(client, tenant, application_id),
        "reject",
        "Road closure not approved.",
    )
    health_task = _health_task_id(client, tenant, application_id)
    decide(
        client,
        tenant.token_for(tenant.health_reviewer),
        health_task,
        "approve",
        "Health is fine with it.",
    )

    assert application_status(db, application_id) == ApplicationStatus.REJECTED


def test_changes_requested_sets_application_status(client: TestClient, db, tenant) -> None:
    """Changes Requested goes back to the organizer, even over an approval."""
    application_id, _ = create_and_submit(client, tenant)

    decide(
        client,
        tenant.token_for(tenant.reviewer),
        task_for(client, tenant, application_id),
        "request_changes",
        "Missing a site plan.",
    )
    health_task = _health_task_id(client, tenant, application_id)
    decide(
        client,
        tenant.token_for(tenant.health_reviewer),
        health_task,
        "approve",
        "Health ok.",
    )

    # Changes-requested outranks approval: the organizer still has work to do.
    assert application_status(db, application_id) == ApplicationStatus.CHANGES_REQUESTED


def test_changes_requested_before_approval_then_approved_by_all_stays_requested(
    client: TestClient, db, tenant
) -> None:
    """
    Ordering does not matter: a changes-requested decision is not undone by a
    later approval, because the organizer has to resubmit.
    """
    application_id, _ = create_and_submit(client, tenant)

    decide(
        client,
        tenant.token_for(tenant.health_reviewer),
        _health_task_id(client, tenant, application_id),
        "request_changes",
        "Need a noise assessment.",
    )
    decide(
        client,
        tenant.token_for(tenant.reviewer),
        task_for(client, tenant, application_id),
        "approve",
        "Police ok.",
    )

    assert application_status(db, application_id) == ApplicationStatus.CHANGES_REQUESTED


def _health_task_id(client: TestClient, tenant: TenantFixture, application_id) -> str:
    tasks = client.get(
        REVIEW_TASKS, headers=auth(tenant.token_for(tenant.health_reviewer))
    ).json()
    matches = [t for t in tasks if t["application_id"] == str(application_id)]
    assert len(matches) == 1
    return matches[0]["id"]


# ---------------------------------------------------------------------------
# 6. Invalid transitions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "first", ["approve", "reject", "request_changes"]
)
def test_cannot_act_twice_on_the_same_task(client: TestClient, db, tenant, first) -> None:
    """A decided task is closed to further reviewer action."""
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    expected = {
        "approve": ReviewStatus.APPROVED,
        "reject": ReviewStatus.REJECTED,
        "request_changes": ReviewStatus.CHANGES_REQUESTED,
    }[first]

    assert decide(client, token, task_id, first, "First decision.").status_code == 200
    second = decide(client, token, task_id, "approve", "Changed my mind.")

    assert second.status_code == 409, second.text
    # The first decision and its comment are untouched.
    task = db.get(ReviewTask, uuid.UUID(task_id))
    assert task.status == expected
    assert task.comment == "First decision."


def test_original_decision_survives_a_rejected_second_action(
    client: TestClient, db, tenant
) -> None:
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    decide(client, token, task_id, "request_changes", "Need more detail.")
    decide(client, token, task_id, "approve", "Actually fine.")

    task = db.query(ReviewTask).get(task_id)
    assert task.status == ReviewStatus.CHANGES_REQUESTED
    assert task.comment == "Need more detail."


def test_cannot_act_on_a_rejected_application(client: TestClient, db, tenant) -> None:
    """A settled application is closed, even for the agency that has not voted."""
    application_id, _ = create_and_submit(client, tenant)

    decide(
        client,
        tenant.token_for(tenant.reviewer),
        task_for(client, tenant, application_id),
        "reject",
        "No permit for this route.",
    )

    health_response = decide(
        client,
        tenant.token_for(tenant.health_reviewer),
        _health_task_id(client, tenant, application_id),
        "approve",
        "Health had no objections.",
    )

    assert health_response.status_code == 409, health_response.text
    health_task = db.query(ReviewTask).filter(
        ReviewTask.application_id == application_id,
        ReviewTask.agency_id == tenant.agencies["Health"].id,
    ).one()
    assert health_task.status == ReviewStatus.PENDING


def test_cannot_review_a_draft_application(client: TestClient, db, tenant) -> None:
    """
    The assignment's example of an invalid transition: approving a draft.

    A draft has no review tasks, so the API rejects it earlier, as 404. The
    lifecycle rule that would apply is unit-tested below.
    """
    token = tenant.token_for(tenant.organizer)
    created = client.post("/applications", json=VALID_PAYLOAD, headers=auth(token))
    assert created.status_code == 201
    application_id = uuid.UUID(created.json()["id"])

    # No task exists, so no reviewer can address it.
    response = decide(
        client, tenant.token_for(tenant.reviewer), uuid.uuid4(), "approve", "x"
    )
    assert response.status_code == 404
    assert application_status(db, application_id) == ApplicationStatus.DRAFT


def test_cannot_act_on_another_agencies_task(client: TestClient, db, tenant) -> None:
    """Health's reviewer cannot decide Police's task, and it stays Pending."""
    application_id, _ = create_and_submit(client, tenant)
    police_task_id = task_for(client, tenant, application_id)

    response = decide(
        client,
        tenant.token_for(tenant.health_reviewer),
        police_task_id,
        "reject",
        "Not my department.",
    )

    assert response.status_code == 404
    task = db.query(ReviewTask).get(police_task_id)
    assert task.status == ReviewStatus.PENDING
    assert task.comment is None


def test_cannot_act_on_another_tenants_task(client: TestClient, db, make_tenant) -> None:
    home = make_tenant("HomeTenant", with_reviewer=True)
    away = make_tenant("AwayTenant", with_reviewer=True)
    application_id, _ = create_and_submit(client, away)
    away_task_id = next(
        t["id"]
        for t in client.get(
            REVIEW_TASKS, headers=auth(away.token_for(away.reviewer))
        ).json()
        if t["application_id"] == str(application_id)
    )

    response = decide(
        client, home.token_for(home.reviewer), away_task_id, "approve", "Looks ok."
    )

    assert response.status_code == 404
    task = db.query(ReviewTask).get(away_task_id)
    assert task.status == ReviewStatus.PENDING


def test_organizer_cannot_edit_a_submitted_application_while_under_review(
    client: TestClient, tenant
) -> None:
    """Reviewing an application that is silently edited would be pointless."""
    application_id, _ = create_and_submit(client, tenant)
    organizer = tenant.token_for(tenant.organizer)

    decide(
        client,
        tenant.token_for(tenant.reviewer),
        task_for(client, tenant, application_id),
        "approve",
        "Police ok.",
    )

    response = client.put(
        f"/applications/{application_id}",
        json={**VALID_PAYLOAD, "location": "Somewhere else"},
        headers=auth(organizer),
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# 7. Audit trail
# ---------------------------------------------------------------------------


def test_decision_writes_an_audit_event(client: TestClient, db, tenant) -> None:
    """Reviewer identity, agency, application, action, comment and time."""
    application_id, _ = create_and_submit(client, tenant)
    task = tenant.agencies["Police"]
    task_id = task_for(client, tenant, application_id)

    decide(
        client,
        tenant.token_for(tenant.reviewer),
        task_id,
        "approve",
        "Traffic plan agreed.",
    )

    event = (
        db.query(AuditEvent)
        .filter(AuditEvent.action == "review.approved")
        .order_by(AuditEvent.created_at.desc())
        .first()
    )
    assert event is not None
    assert event.application_id == application_id
    assert event.user_id == tenant.reviewer.id
    assert event.agency_id == task.id
    assert event.tenant_id == tenant.tenant.id
    assert event.old_status == ReviewStatus.PENDING.value
    assert event.new_status == ReviewStatus.APPROVED.value
    assert event.comment == "Traffic plan agreed."
    assert event.created_at is not None


def test_application_status_change_writes_a_second_audit_event(
    client: TestClient, db, tenant
) -> None:
    """The decision and the status change it caused are distinct facts."""
    application_id, _ = create_and_submit(client, tenant)
    task_id = task_for(client, tenant, application_id)

    decide(
        client,
        tenant.token_for(tenant.reviewer),
        task_id,
        "approve",
        "Police ok.",
    )

    events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.application_id == application_id,
            AuditEvent.action == "application.status_changed",
        )
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        .all()
    )
    # Two: the Draft -> Submitted change on submit, then the one the approval
    # caused.
    assert len(events) == 2
    assert events[0].old_status == ApplicationStatus.DRAFT.value
    assert events[0].new_status == ApplicationStatus.SUBMITTED.value
    assert events[1].old_status == ApplicationStatus.SUBMITTED.value
    assert events[1].new_status == ApplicationStatus.UNDER_REVIEW.value


def test_no_status_change_audit_event_when_status_holds(client: TestClient, db, tenant) -> None:
    """One of two approving moves nothing, so no status-change event is written."""
    application_id, _ = create_and_submit(client, tenant)

    decide(
        client,
        tenant.token_for(tenant.reviewer),
        task_for(client, tenant, application_id),
        "approve",
        "Police ok.",
    )

    count = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.application_id == application_id,
            AuditEvent.action == "application.status_changed",
        )
        .count()
    )
    # Draft -> Submitted on submit, then Submitted -> Under Review. Health
    # approving changed nothing, so it added no third.
    assert count == 2


def test_rejected_action_writes_no_audit_event(client: TestClient, db, tenant) -> None:
    """A refused decision leaves no trace in the timeline."""
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    decide(client, token, task_id, "approve", "Fine.")
    before = db.query(AuditEvent).filter(
        AuditEvent.application_id == application_id
    ).count()

    assert decide(client, token, task_id, "reject", "Actually no.").status_code == 409

    after = db.query(AuditEvent).filter(
        AuditEvent.application_id == application_id
    ).count()
    assert after == before


def test_audit_timeline_is_readable_by_the_reviewer(client: TestClient, tenant) -> None:
    """The history endpoint returns the application's decisions, oldest first."""
    application_id, _ = create_and_submit(client, tenant)
    police_task = task_for(client, tenant, application_id)
    token = tenant.token_for(tenant.reviewer)

    decide(client, token, police_task, "approve", "Police ok.")
    decide(
        client,
        tenant.token_for(tenant.health_reviewer),
        _health_task_id(client, tenant, application_id),
        "reject",
        "Sanitation inadequate.",
    )

    response = client.get(f"{REVIEW_TASKS}/{police_task}/history", headers=auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["application_id"] == str(application_id)
    assert body["application_status"] == ApplicationStatus.REJECTED.value
    actions = [e["action"] for e in body["events"]]
    assert actions == [
        "application.status_changed",
        "review.approved",
        "application.status_changed",
        "review.rejected",
        "application.status_changed",
    ]
    # The comments travel with the history.
    assert body["events"][1]["comment"] == "Police ok."
    assert body["events"][3]["comment"] == "Sanitation inadequate."


def test_history_is_scoped_to_the_reviewers_agency(client: TestClient, tenant) -> None:
    """No history for a task this agency does not own."""
    application_id, _ = create_and_submit(client, tenant)
    police_task = task_for(client, tenant, application_id)

    response = client.get(
        f"{REVIEW_TASKS}/{police_task}/history",
        headers=auth(tenant.token_for(tenant.health_reviewer)),
    )

    assert response.status_code == 404


def test_audit_rows_are_never_overwritten_by_later_actions(
    client: TestClient, db, tenant
) -> None:
    """Both agencies' decisions coexist in the timeline."""
    application_id, _ = create_and_submit(client, tenant)

    decide(
        client,
        tenant.token_for(tenant.reviewer),
        task_for(client, tenant, application_id),
        "approve",
        "Police ok.",
    )
    decide(
        client,
        tenant.token_for(tenant.health_reviewer),
        _health_task_id(client, tenant, application_id),
        "approve",
        "Health ok.",
    )

    comments = [
        e.comment
        for e in db.query(AuditEvent)
        .filter(
            AuditEvent.application_id == application_id,
            AuditEvent.action == "review.approved",
        )
        .all()
    ]
    assert sorted(comments) == ["Health ok.", "Police ok."]


# ---------------------------------------------------------------------------
# 8. Concurrency / duplicate protection
# ---------------------------------------------------------------------------


def test_duplicate_action_on_one_task_is_protected_by_the_status_check(
    client: TestClient, tenant
) -> None:
    """
    The retried-request case, which the task status check catches.

    Two sequential decisions are not a race, so this asserts the ordinary
    duplicate path: the second is refused with 409.
    """
    application_id, _ = create_and_submit(client, tenant)
    token = tenant.token_for(tenant.reviewer)
    task_id = task_for(client, tenant, application_id)

    assert decide(client, token, task_id, "approve", "First.").status_code == 200
    assert decide(client, token, task_id, "reject", "Second.").status_code == 409


def test_concurrent_approvals_from_two_agencies_produce_one_approved_application(
    client: TestClient, db, tenant
) -> None:
    """
    Both agencies decide at the same instant, and the result stays consistent.

    This asserts the outcome, not the interleaving: whichever order the two
    transactions happen to take, both requests succeed and the application ends
    Approved rather than stranded part-way. The mechanism that guarantees it is
    covered deterministically by
    `test_decision_waits_for_the_application_lock`.
    """
    application_id, _ = create_and_submit(client, tenant)
    police_task = task_for(client, tenant, application_id)
    health_task = _health_task_id(client, tenant, application_id)
    police_token = tenant.token_for(tenant.reviewer)
    health_token = tenant.token_for(tenant.health_reviewer)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                lambda t, task: client.post(
                    f"{REVIEW_TASKS}/{task}/decision",
                    json={"action": "approve", "comment": "ok"},
                    headers=auth(t),
                ),
                token,
                task,
            )
            for token, task in ((police_token, police_task), (health_token, health_task))
        ]
        responses = [f.result() for f in futures]

    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert {r.json()["task"]["review_status"] for r in responses} == {
        ReviewStatus.APPROVED.value
    }

    # Whatever the interleaving, the aggregate reflects both decisions.
    assert application_status(db, application_id) == ApplicationStatus.APPROVED


def test_decision_waits_for_the_application_lock(
    client: TestClient, db, tenant
) -> None:
    """
    Two agencies decide at once, forced into the worst-case ordering.

    A thread test alone cannot prove the application lock is doing anything: the
    window is wide enough that the requests simply do not collide, and the test
    passes whether or not the lock exists. (It did.) So the collision is
    manufactured instead.

    A separate session holds `FOR UPDATE` on the application row, records one
    agency's approval without committing, and the second decision is fired from
    a thread. The thread must stay blocked, because the route takes the same
    lock before recomputing the aggregate. Without `with_for_update()` on the
    application the request would read a task list missing the pending approval
    and write Under Review, and the request would not have waited at all.

    Releasing the lock lets the request proceed, and it then sees the committed
    approval — which is exactly the read the lock exists to guarantee.
    """
    application_id, _ = create_and_submit(client, tenant)
    health_task = _health_task_id(client, tenant, application_id)
    police_task = task_for(client, tenant, application_id)
    health_token = tenant.token_for(tenant.health_reviewer)

    # A transaction that has approved the Police task but not yet committed.
    blocker = _scoped_session(tenant.tenant.id)
    try:
        # No explicit begin(): pinning the GUC in _scoped_session already opened
        # a transaction, and this one has to span the whole test.
        blocker.execute(
            sa.text("SELECT 1 FROM applications WHERE id = :id FOR UPDATE"),
            {"id": str(application_id)},
        )
        blocker.execute(
            sa.text(
                "UPDATE review_tasks SET status = 'APPROVED', comment = 'Police ok.' "
                "WHERE id = :id"
            ),
            {"id": police_task},
        )

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                lambda: client.post(
                    f"{REVIEW_TASKS}/{health_task}/decision",
                    json={"action": "approve", "comment": "Health ok."},
                    headers=auth(health_token),
                )
            )

            # Give the request ample time to run to completion if it can.
            # It must not, because it needs the lock this transaction holds.
            time.sleep(_LOCK_WAIT_SECONDS)
            assert not pending.done(), (
                "decision returned while the application row was locked by another "
                "transaction — the application lock is not being taken"
            )

            blocker.commit()

            response = pending.result(timeout=30)

        assert response.status_code == 200, response.text
        # The committed approval was visible to the second transaction, so the
        # aggregate was computed from both decisions.
        assert (
            response.json()["application_status"] == ApplicationStatus.APPROVED.value
        )
        assert application_status(db, application_id) == ApplicationStatus.APPROVED
    finally:
        blocker.rollback()
        blocker.close()


def test_concurrent_actions_on_one_task_produce_one_decision(
    client: TestClient, db, tenant
) -> None:
    """
    Two reviewers of the same agency decide simultaneously.

    The unique constraint and the task lock mean one wins and the other is
    refused. Whichever it is, exactly one comment is recorded: the loser's
    rationale is not written over the winner's.
    """
    application_id, _ = create_and_submit(client, tenant)
    task_id = task_for(client, tenant, application_id)
    token = tenant.token_for(tenant.reviewer)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                lambda c: client.post(
                    f"{REVIEW_TASKS}/{task_id}/decision",
                    json={"action": "approve", "comment": c},
                    headers=auth(token),
                ),
                comment,
            )
            for comment in ("first voice", "second voice")
        ]
        responses = [f.result() for f in futures]

    statuses = sorted(r.status_code for r in responses)
    assert statuses in ([200, 200], [200, 409]), [r.text for r in responses]

    task = db.query(ReviewTask).get(task_id)
    assert task.status == ReviewStatus.APPROVED
    assert task.comment in ("first voice", "second voice")

    # At most one decision was recorded for this task, whatever the interleaving.
    decisions = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.application_id == application_id,
            AuditEvent.action == "review.approved",
        )
        .count()
    )
    assert decisions <= 1


# ---------------------------------------------------------------------------
# 9. Lifecycle unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("task_statuses", "current", "expected"),
    [
        # Nothing decided: the application stays where it is.
        ([ReviewStatus.PENDING, ReviewStatus.PENDING], ApplicationStatus.SUBMITTED, ApplicationStatus.SUBMITTED),
        # One of two: open, and explicitly Under Review.
        ([ReviewStatus.APPROVED, ReviewStatus.PENDING], ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW),
        ([ReviewStatus.CHANGES_REQUESTED, ReviewStatus.PENDING], ApplicationStatus.SUBMITTED, ApplicationStatus.CHANGES_REQUESTED),
        # All approved: approved.
        ([ReviewStatus.APPROVED, ReviewStatus.APPROVED], ApplicationStatus.UNDER_REVIEW, ApplicationStatus.APPROVED),
        # Any rejection is decisive.
        ([ReviewStatus.APPROVED, ReviewStatus.REJECTED], ApplicationStatus.UNDER_REVIEW, ApplicationStatus.REJECTED),
        ([ReviewStatus.PENDING, ReviewStatus.REJECTED], ApplicationStatus.UNDER_REVIEW, ApplicationStatus.REJECTED),
        # Changes requested outranks approval.
        ([ReviewStatus.APPROVED, ReviewStatus.CHANGES_REQUESTED], ApplicationStatus.UNDER_REVIEW, ApplicationStatus.CHANGES_REQUESTED),
        ([ReviewStatus.CHANGES_REQUESTED, ReviewStatus.CHANGES_REQUESTED], ApplicationStatus.UNDER_REVIEW, ApplicationStatus.CHANGES_REQUESTED),
        # A lone task is still a complete set.
        ([ReviewStatus.APPROVED], ApplicationStatus.SUBMITTED, ApplicationStatus.APPROVED),
        ([ReviewStatus.REJECTED], ApplicationStatus.SUBMITTED, ApplicationStatus.REJECTED),
    ],
)
def test_aggregate_application_status(task_statuses, current, expected) -> None:
    from app.core.lifecycle import aggregate_application_status

    assert aggregate_application_status(task_statuses, current=current) == expected


def test_draft_cannot_be_reviewed() -> None:
    from app.core.lifecycle import InvalidStatusTransition, assert_application_reviewable

    with pytest.raises(InvalidStatusTransition):
        assert_application_reviewable(ApplicationStatus.DRAFT)


@pytest.mark.parametrize(
    "status", [ApplicationStatus.APPROVED, ApplicationStatus.REJECTED]
)
def test_settled_applications_cannot_be_reviewed(status) -> None:
    from app.core.lifecycle import InvalidStatusTransition, assert_application_reviewable

    with pytest.raises(InvalidStatusTransition):
        assert_application_reviewable(status)


@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.CHANGES_REQUESTED,
    ],
)
def test_reviewable_application_statuses_are_allowed(status) -> None:
    from app.core.lifecycle import assert_application_reviewable

    assert_application_reviewable(status)


@pytest.mark.parametrize(
    "current",
    [ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.CHANGES_REQUESTED],
)
def test_a_decided_task_cannot_transition_again(current) -> None:
    """Every target is refused once a task has a decision."""
    from app.core.lifecycle import (
        InvalidStatusTransition,
        assert_review_transition_allowed,
    )

    for target in (
        ReviewStatus.APPROVED,
        ReviewStatus.REJECTED,
        ReviewStatus.CHANGES_REQUESTED,
    ):
        with pytest.raises(InvalidStatusTransition):
            assert_review_transition_allowed(current, target)


@pytest.mark.parametrize(
    "target",
    [
        ReviewStatus.APPROVED,
        ReviewStatus.REJECTED,
        ReviewStatus.CHANGES_REQUESTED,
    ],
)
def test_pending_task_accepts_each_decision(target) -> None:
    from app.core.lifecycle import assert_review_transition_allowed

    assert_review_transition_allowed(ReviewStatus.PENDING, target)