"""
app/api/reviews.py

Reviewer-facing queue and review actions.

  GET  /review-tasks                my agency's queue
  GET  /review-tasks/{id}           one task, with the application
  POST /review-tasks/{id}/decision  approve / reject / request changes

Scope note: this module covers reviewing. Resubmission after a changes-requested
decision is a later phase.

Three independent layers keep reviewers inside their agency's lane, and all three
are needed:

  1. Role (`require_role(AGENCY_REVIEWER)`). An organizer or City Admin is
     refused at the door with 403, before any query runs. Only agency staff
     review.

  2. RLS (the database). Every query here runs on the `get_tenant_db` session,
     so another city's tasks and applications are invisible to PostgreSQL. A
     guessed id finds nothing.

  3. Agency scope (this module). RLS is tenant-scoped and says nothing about one
     agency seeing another's queue inside the same city. That is enforced by
     always filtering on the reviewer's own `agency_id`, and by returning 404 —
     never 403 — for a task belonging to a different agency, so the API does not
     confirm that the id exists.

The application status is never set here directly. This module records a
decision and then calls `app.core.lifecycle` to derive the aggregate, so the
lifecycle rules live in exactly one module. Two agencies acting at the same
instant cannot disagree about the result, because both serialise on a row lock
on the application and both recompute from the full set of task statuses.

Reviewers cannot modify application fields. The only body this router accepts is
a decision and a comment, enforced by the schema in `app.schemas.review`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.lifecycle import (
    InvalidStatusTransition,
    aggregate_application_status,
    assert_application_reviewable,
    assert_review_transition_allowed,
)
from app.deps import CurrentUser, get_tenant_db, require_role
from app.models import (
    Application,
    ApplicationStatus,
    AuditEvent,
    EventType,
    ReviewStatus,
    ReviewTask,
    UserRole,
)
from app.schemas.review import (
    ApplicationHistoryResponse,
    AuditEventResponse,
    ReviewActionRequest,
    ReviewActionResponse,
    ReviewTaskResponse,
)

router = APIRouter(prefix="/review-tasks", tags=["reviews"])

ReviewerOnly = Annotated[CurrentUser, Depends(require_role(UserRole.AGENCY_REVIEWER))]
TenantSession = Annotated[Session, Depends(get_tenant_db)]

# One detail for "no such task" and "not your agency's". Distinguishing them
# would let a reviewer enumerate which review task ids exist in their city.
_TASK_NOT_FOUND_DETAIL = "Review task not found"

_MAX_PAGE_SIZE = 100

# The three reviewer decisions, mapped to the review task status each one
# produces. Kept as data so the route cannot drift from the lifecycle module:
# `assert_review_transition_allowed` still decides whether the move is legal,
# this only says which target each name means.
_ACTION_TARGETS: dict[str, ReviewStatus] = {
    "approve": ReviewStatus.APPROVED,
    "reject": ReviewStatus.REJECTED,
    "request_changes": ReviewStatus.CHANGES_REQUESTED,
}

# Audit action names. The reviewer decision is recorded separately from the
# application status change it caused, so the timeline distinguishes "an agency
# approved" from "the permit is now approved" — different facts that happen to
# coincide on the last vote.
_AUDIT_DECISION_PREFIX = "review."
_AUDIT_APPLICATION_STATUS_CHANGE = "application.status_changed"


def _task_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_TASK_NOT_FOUND_DETAIL,
    )


def _require_reviewer_agency(current_user: CurrentUser) -> uuid.UUID:
    """
    The reviewer's agency id, or a clear 403 if they do not have one.

    `users.agency_id` is nullable because organizers and City Admins do not
    belong to an agency. A reviewer with no agency is a data error rather than a
    valid configuration, and returning an empty queue would hide it.
    """
    if current_user.agency_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer account is not attached to an agency",
        )
    return current_user.agency_id


def _task_query(current_user: CurrentUser):
    """
    Base query for a reviewer's own tasks, with the application eager-loaded.

    The `agency_id` predicate is the agency isolation check. It is redundant with
    RLS only in the sense that RLS checks the other axis (tenant); it is what
    keeps one agency from reading another's work inside the same city.
    """
    return (
        select(ReviewTask)
        .join(Application, Application.id == ReviewTask.application_id)
        .where(
            ReviewTask.agency_id == current_user.agency_id,
            # The task's own tenant must match the application it points at.
            # RLS already guarantees both rows are in the caller's tenant; this
            # asserts the two agree with each other, which RLS does not.
            Application.tenant_id == ReviewTask.tenant_id,
        )
        .options(selectinload(ReviewTask.application))
    )


def _to_response(task: ReviewTask) -> ReviewTaskResponse:
    return ReviewTaskResponse.model_validate(
        {
            "id": task.id,
            "application_id": task.application_id,
            "agency_id": task.agency_id,
            "status": task.status,
            "comment": task.comment,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "application": task.application,
        }
    )


@router.get("", response_model=list[ReviewTaskResponse])
def list_review_tasks(
    session: TenantSession,
    current_user: ReviewerOnly,
    status_filter: Annotated[
        ReviewStatus | None,
        Query(alias="status", description="Filter by this agency's review status."),
    ] = None,
    event_type_filter: Annotated[
        EventType | None,
        Query(alias="event_type", description="Filter by event type."),
    ] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)] = 50,
) -> list[ReviewTaskResponse]:
    """
    List the review tasks assigned to the caller's agency, newest first.

    Scoped to the reviewer's own agency and, via the session, to the reviewer's
    own tenant. Every row in this response is a task this agency is actually
    being asked to decide on; there is no cross-agency visibility.
    """
    _require_reviewer_agency(current_user)
    query = _task_query(current_user)

    if status_filter is not None:
        query = query.where(ReviewTask.status == status_filter)
    if event_type_filter is not None:
        query = query.where(Application.event_type == event_type_filter)

    # created_at is not unique, so id breaks ties to keep paging deterministic.
    query = (
        query.order_by(ReviewTask.created_at.desc(), ReviewTask.id.desc())
        .offset(offset)
        .limit(limit)
    )

    return [_to_response(task) for task in session.execute(query).scalars().unique()]


@router.get("/{task_id}", response_model=ReviewTaskResponse)
def get_review_task(
    task_id: uuid.UUID,
    session: TenantSession,
    current_user: ReviewerOnly,
) -> ReviewTaskResponse:
    """
    Fetch one review task for the caller's agency.

    Application details are reachable here only because a task exists for this
    agency on it. Reviewers have no route into `/applications` at all — those
    are organizer-scoped — so this is the only way to read an application, and
    it is gated on an assignment to review it.
    """
    agency_id = _require_reviewer_agency(current_user)

    task = session.execute(
        _task_query(current_user).where(ReviewTask.id == task_id)
    ).scalar_one_or_none()

    if task is None:
        # Covers an unknown id, another agency's task, and another tenant's task
        # identically.
        raise _task_not_found()

    return _to_response(task)


@router.post("/{task_id}/decision", response_model=ReviewActionResponse)
def decide_review_task(
    task_id: uuid.UUID,
    payload: ReviewActionRequest,
    session: TenantSession,
    current_user: ReviewerOnly,
) -> ReviewActionResponse:
    """
    Record a reviewer's decision and recompute the application status.

    Concurrency. Two agencies can finish at the same moment, and the naive
    version of this — read every task, count approvals, write the result — races:
    both read "one of two approved", both write Under Review, and the second
    approval is lost. So the decision is taken under two row locks, always in
    this order:

        1. the review task  (`FOR UPDATE` on this reviewer's own task)
        2. the application (`FOR UPDATE`)

    Every writer takes the same order, so the locks cannot deadlock. Holding the
    application lock means the other agency is blocked before it writes its own
    task status, which is what makes the read-all-tasks-and-recompute below see a
    consistent snapshot: no task status can change between the read and the
    write, because changing one requires the same lock.

    The application status is then derived by `app.core.lifecycle` rather than
    set here, so "approved only when every agency approved" is enforced in one
    module instead of at each call site.
    """
    agency_id = _require_reviewer_agency(current_user)

    target = _ACTION_TARGETS.get(payload.action)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown review action {payload.action!r}; expected one of "
                f"{', '.join(sorted(_ACTION_TARGETS))}"
            ),
        )

    # Lock 1: this reviewer's own task. Scoped by agency so a task belonging to
    # another agency is a 404 here rather than a lock it could never act on.
    task = session.execute(
        select(ReviewTask)
        .where(ReviewTask.id == task_id, ReviewTask.agency_id == agency_id)
        .with_for_update()
    ).scalar_one_or_none()

    if task is None:
        raise _task_not_found()

    # Lock 2: the application. Every status decision serialises on this row.
    application = session.execute(
        select(Application).where(Application.id == task.application_id).with_for_update()
    ).scalar_one_or_none()

    if application is None:
        # Would mean a task pointing at no application. The FK prevents it, so
        # this is a guard rather than an expected path.
        raise _task_not_found()

    old_review_status = ReviewStatus(task.status)

    # Both checks are refused with 409: the caller is allowed to review, but
    # this particular state has already been decided or is not yet reviewable.
    try:
        assert_review_transition_allowed(old_review_status, target)
        assert_application_reviewable(application.status)
    except InvalidStatusTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    # The reviewer's comment lands on the task. It is written once, on the
    # transition out of Pending: there is no path back to Pending, so a decision
    # is never silently overwritten by a second one.
    task.status = target
    task.comment = payload.comment

    # Recompute from the full set of decisions, now that the application lock is
    # held.
    #
    # The explicit flush matters: the session is built with autoflush=False, so
    # without it the SELECT below would run against the database while this
    # task's new status was still only in the identity map. The aggregate would
    # then be computed from the pre-decision task list and would disagree with
    # the row that gets written — a reviewer approving the last outstanding task
    # would leave the application Under Review instead of Approved.
    session.flush()

    all_statuses = [
        ReviewStatus(row[0])
        for row in session.execute(
            select(ReviewTask.status).where(ReviewTask.application_id == application.id)
        )
    ]

    previous_application_status = ApplicationStatus(application.status)
    new_application_status = aggregate_application_status(
        all_statuses, current=previous_application_status
    )
    application.status = new_application_status

    # Audit trail. Two rows are written for a decision that moves the application,
    # one for the decision itself and one for the aggregate it caused. They are
    # different facts: the last agency to approve both approves and finalises,
    # and a reader of the timeline should be able to tell those apart.
    session.add(
        AuditEvent(
            application_id=application.id,
            tenant_id=application.tenant_id,
            user_id=current_user.id,
            agency_id=task.agency_id,
            action=f"{_AUDIT_DECISION_PREFIX}{target.value.lower()}",
            old_status=old_review_status.value,
            new_status=target.value,
            comment=payload.comment,
        )
    )

    if new_application_status is not previous_application_status:
        session.add(
            AuditEvent(
                application_id=application.id,
                tenant_id=application.tenant_id,
                user_id=current_user.id,
                agency_id=task.agency_id,
                action=_AUDIT_APPLICATION_STATUS_CHANGE,
                old_status=previous_application_status.value,
                new_status=new_application_status.value,
                comment=payload.comment,
            )
        )

    # Single commit: decision, aggregate status and audit rows land together. A
    # reviewer cannot leave a decision recorded with no audit trail, and the
    # application status cannot move without the decision that moved it.
    session.commit()

    session.refresh(task)
    session.refresh(application)

    return ReviewActionResponse(
        task=_to_response(task),
        application_status=new_application_status,
    )


@router.get("/{task_id}/history", response_model=ApplicationHistoryResponse)
def get_review_history(
    task_id: uuid.UUID,
    session: TenantSession,
    current_user: ReviewerOnly,
) -> ApplicationHistoryResponse:
    """
    The audit timeline for the application this task refers to.

    Gated on the same assignment check as the task itself, so a reviewer sees
    the history of applications they were asked to review and nothing else.
    """
    agency_id = _require_reviewer_agency(current_user)

    task = session.execute(
        _task_query(current_user).where(ReviewTask.id == task_id)
    ).scalar_one_or_none()

    if task is None:
        raise _task_not_found()

    events = session.execute(
        select(AuditEvent)
        .where(AuditEvent.application_id == task.application_id)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
    ).scalars()

    return ApplicationHistoryResponse(
        application_id=task.application_id,
        application_status=ApplicationStatus(task.application.status),
        events=[AuditEventResponse.model_validate(e) for e in events],
    )