"""
app/api/applications.py

Organizer-facing permit applications.

  POST /applications         create a draft
  GET  /applications         list my applications
  GET  /applications/{id}    fetch one of mine
  PUT  /applications/{id}    edit one of mine

Scope note: this module covers drafting, submission, organizer tracking, and
resubmission. Reviewer decisions and the aggregate status lifecycle live in
`app.api.reviews` and `app.core.lifecycle`.

Two independent layers keep a tenant's data private, and both are needed:

  1. RLS (the database). Every query here runs on the session from
     `get_tenant_db`, which pins `app.current_tenant_id` to the verified token
     before the first statement. A row belonging to another tenant is therefore
     invisible to PostgreSQL, not merely filtered out by Python. Guessing an id
     does not help.

  2. Ownership (this module). RLS is tenant-scoped, so it deliberately says
     nothing about one organizer seeing another organizer's applications inside
     the same city. That is enforced by always filtering on `submitter_id` and
     by returning 404 — never 403 — for someone else's row, so the API does not
     confirm that a given id exists.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

# Shared with the admin list so every search box escapes and matches the same
# way. admin.py does not import this module, so the import is not circular.
from app.api.admin import _contains_pattern
from app.core.lifecycle import (
    InvalidStatusTransition,
    assert_application_editable,
    assert_application_resubmittable,
    should_reset_on_resubmission,
    resubmission_application_status,
)
from app.core.routing import agencies_required_by_attendance, required_agencies
from app.deps import CurrentUser, get_tenant_db, require_role
from app.models import (
    Agency,
    Application,
    ApplicationStatus,
    AuditEvent,
    EventType,
    ReviewStatus,
    ReviewTask,
    UserRole,
)
from app.schemas.application import (
    ApplicationCreate,
    ApplicationHistoryResponse,
    ApplicationResponse,
    ApplicationUpdate,
    RequiredAgency,
    ResubmitApplicationResponse,
    SubmitApplicationResponse,
    missing_submission_fields,
    review_summaries,
)
from app.schemas.review import AuditEventResponse

router = APIRouter(prefix="/applications", tags=["applications"])

# Only organizers author applications. City Admins manage routing config and
# reviewers act on review tasks; neither creates permit applications.
OrganizerOnly = Annotated[CurrentUser, Depends(require_role(UserRole.ORGANIZER))]
TenantSession = Annotated[Session, Depends(get_tenant_db)]

# One detail for "no such application" and "not yours". Distinguishing them
# would let a caller probe which application ids exist in their tenant.
_APPLICATION_NOT_FOUND_DETAIL = "Application not found"

# Only reachable by creating a draft. `status` is never accepted from a request
# body; it moves to Submitted through the submit endpoint and later through the
# reviewer lifecycle.
_STATUS_ON_CREATE = ApplicationStatus.DRAFT

# A submitted application is Under Review only once an agency acts; at the moment
# of submission it is Submitted with every task Pending.
_STATUS_ON_SUBMIT = ApplicationStatus.SUBMITTED
_INITIAL_REVIEW_STATUS = ReviewStatus.PENDING

# Audit action names for organizer-driven changes. Distinct from the reviewer's
# `review.*` actions: a reader of the timeline needs to tell "an agency decided"
# from "the organizer acted", and the two can both be true in one resubmission
# cycle.
_AUDIT_APPLICATION_EDITED = "application.edited"
_AUDIT_APPLICATION_RESUBMITTED = "application.resubmitted"
_AUDIT_REVIEW_TASK_RESET = "review.task_reset"
_AUDIT_APPLICATION_STATUS_CHANGE = "application.status_changed"

# A generous upper bound. The point is to stop one request from pulling an
# unbounded result set; real deployments would page.
_MAX_PAGE_SIZE = 100


def _application_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_APPLICATION_NOT_FOUND_DETAIL,
    )


def _transition_conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _describe_changes(changes: dict[str, tuple[object, object]]) -> str:
    """
    Summarise which fields an edit changed, old -> new.

    Audit comments are free text, so the wording is for a human reading a
    timeline. Field names are included rather than a bare count, because "2 fields
    changed" does not tell a reviewer whether the attendance or the location
    moved. Values are truncated: an audit comment is not a place to store a whole
    event description.
    """
    parts = []
    for field, (before, after) in sorted(changes.items()):
        parts.append(f"{field}: {_abbreviate(before)} -> {_abbreviate(after)}")
    return "; ".join(parts)


def _abbreviate(value: object, limit: int = 60) -> str:
    if value is None:
        return "none"
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _application_response(application: Application) -> ApplicationResponse:
    """
    Build the organizer-facing response, including per-agency review progress.

    `selectinload` on review_tasks and agency is what keeps this to two queries
    regardless of how many agencies are reviewing; without it each task would
    trigger its own lazy load.
    """
    return ApplicationResponse.model_validate(
        application,
        from_attributes=True,
    ).model_copy(
        update={"reviews": review_summaries(application.review_tasks)}
    )


def _load_own_application(
    session: Session, current_user: CurrentUser, application_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Application:
    """
    Fetch an application that the caller both owns and can see.

    The `submitter_id` predicate is the ownership check. The tenant predicate is
    redundant under RLS and deliberately omitted: RLS is the authority on
    tenancy, and duplicating it in the query would let the two drift apart. If
    RLS were ever weakened, the ownership predicate would still hold.

    `for_update=True` takes a row lock on the application. Used by the write
    paths that read a status and then act on it, so two concurrent requests
    cannot both pass the same status check and then both act. All such paths lock
    the application first, which keeps the lock order consistent with the
    reviewer path in `app.api.reviews` and rules out a deadlock between the two.
    """
    query = select(Application).where(
        Application.id == application_id,
        Application.submitter_id == current_user.id,
    )

    if for_update:
        query = query.with_for_update()

    # Eager-load the review tasks the tracking response reads, and the agency
    # each belongs to so the summaries can be named.
    query = query.options(
        selectinload(Application.review_tasks).selectinload(ReviewTask.agency)
    )

    application = session.execute(query).scalar_one_or_none()

    if application is None:
        # Covers all three cases identically: unknown id, another organizer's
        # application, another tenant's application.
        raise _application_not_found()

    return application


@router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_application(
    payload: ApplicationCreate,
    session: TenantSession,
    current_user: OrganizerOnly,
) -> Application:
    """
    Create a draft permit application.

    `tenant_id` and `submitter_id` come from the verified token, never from the
    request body, so a client cannot file an application under another city or
    another organizer even by naming them explicitly.
    """
    application = Application(
        **payload.model_dump(),
        status=_STATUS_ON_CREATE,
        submitter_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    session.add(application)
    session.commit()
    session.refresh(application)
    return _application_response(application)


@router.get("", response_model=list[ApplicationResponse])
def list_applications(
    session: TenantSession,
    current_user: OrganizerOnly,
    status_filter: Annotated[
        ApplicationStatus | None,
        Query(alias="status", description="Filter by lifecycle status."),
    ] = None,
    event_type_filter: Annotated[
        EventType | None,
        Query(alias="event_type", description="Filter by event type."),
    ] = None,
    q: Annotated[
        str | None,
        Query(description="Free-text search over name, location and description."),
    ] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)] = 50,
) -> list[ApplicationResponse]:
    """
    List the caller's own applications, newest first.

    RLS restricts the result to the caller's tenant; `submitter_id` restricts it
    to the caller. Neither is redundant: a city may have several organizers, and
    one must not see another's drafts.

    `q` is matched in the database rather than in the browser, so it covers
    every application the caller owns instead of only the rows paged on screen.
    It sits under both predicates above: the search can never widen the result
    past the caller's own rows.
    """
    query = select(Application).where(Application.submitter_id == current_user.id)

    if status_filter is not None:
        query = query.where(Application.status == status_filter)
    if event_type_filter is not None:
        query = query.where(Application.event_type == event_type_filter)

    needle = (q or "").strip()
    if needle:
        pattern = _contains_pattern(needle)
        query = query.where(
            or_(
                Application.event_name.ilike(pattern),
                Application.location.ilike(pattern),
                Application.description.ilike(pattern),
            )
        )

    # created_at is not unique, so id breaks ties to keep paging deterministic.
    # Eager-load review tasks for the tracking view. Without this each returned
    # application would issue its own query per task.
    query = query.options(
        selectinload(Application.review_tasks).selectinload(ReviewTask.agency)
    )

    query = (
        query.order_by(Application.created_at.desc(), Application.id.desc())
        .offset(offset)
        .limit(limit)
    )

    return [_application_response(a) for a in session.execute(query).scalars()]


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: uuid.UUID,
    session: TenantSession,
    current_user: OrganizerOnly,
) -> ApplicationResponse:
    """Fetch one of the caller's own applications, with its review progress."""
    return _application_response(
        _load_own_application(session, current_user, application_id)
    )


@router.put("/{application_id}", response_model=ApplicationResponse)
def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    session: TenantSession,
    current_user: OrganizerOnly,
) -> Application:
    """
    Replace the editable fields of a draft, or of an application sent back for
    corrections.

    Two states are editable, and the difference matters:

      * **Draft** — never submitted, so nothing depends on it yet.
      * **Changes Requested** — an agency asked for corrections, so this is
        exactly what the organizer should be doing.

    Submitted and Under Review are refused: an edit there would change what the
    agencies are reviewing without triggering a new review, and would leave their
    recorded decision a statement about a document that no longer exists.
    Approved and Rejected are settled.

    The application row is locked before the status is checked, so two
    concurrent edits cannot both pass that check against the same state.

    Only fields that actually changed are written to the audit trail. An edit
    that resubmits identical values is not a meaningful change and saying so
    would pad the timeline with noise.
    """
    application = _load_own_application(
        session, current_user, application_id, for_update=True
    )

    try:
        assert_application_editable(application.status)
    except InvalidStatusTransition as exc:
        raise _transition_conflict(str(exc)) from exc

    changes = {
        field: (getattr(application, field), value)
        for field, value in payload.model_dump().items()
        if getattr(application, field) != value
    }

    for field, value in payload.model_dump().items():
        setattr(application, field, value)

    if changes:
        session.add(
            AuditEvent(
                application_id=application.id,
                tenant_id=application.tenant_id,
                user_id=current_user.id,
                # No agency: this is the organizer acting, not an agency.
                agency_id=None,
                action=_AUDIT_APPLICATION_EDITED,
                old_status=ApplicationStatus(application.status).value,
                new_status=ApplicationStatus(application.status).value,
                comment=_describe_changes(changes),
            )
        )

    # Single commit: the field changes and the audit row land together, so an
    # edit can never go unrecorded.
    session.commit()
    session.refresh(application)
    return _application_response(application)


@router.post("/{application_id}/submit", response_model=SubmitApplicationResponse)
def submit_application(
    application_id: uuid.UUID,
    session: TenantSession,
    current_user: OrganizerOnly,
) -> SubmitApplicationResponse:
    """
    Submit a draft and open a review task for each required agency.

    The status change and the review tasks are written in one transaction, so
    an application can never end up Submitted with no reviewers assigned. Either
    both land or neither does.

    Duplicates are prevented three ways, cheapest first:
      - the ownership-aware load plus the Draft check, which is what a plain
        double-click hits;
      - re-reading existing tasks before inserting, which closes the window
        between the check and the insert;
      - the uq_review_tasks_application_agency constraint, which is what
        actually survives a genuine race.
    """
    application = _load_own_application(session, current_user, application_id)

    if application.status is not ApplicationStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only draft applications can be submitted; this one is "
                f"{ApplicationStatus(application.status).value}"
            ),
        )

    # Refuse to file an application the agencies cannot assess. A draft is
    # allowed to be incomplete; a submission is not.
    missing = missing_submission_fields(application)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot submit: missing required fields {', '.join(missing)}",
        )

    agencies = required_agencies(session, application)

    # Defence in depth, and the one place here that RLS cannot cover.
    # The policy checks `tenant_id` on review_tasks, so it refuses a task
    # belonging to another city -- but a row owned by *this* city that points at
    # another city's agency_id would pass it, because the FK to agencies is
    # checked with row security disabled. Today that is unreachable: the agency
    # list comes from an RLS-scoped join, so every id is already this city's.
    # Asserting it anyway means a future change that accepts an agency id from
    # the request body fails here rather than silently cross-wiring a review.
    foreign = [a.name for a in agencies if a.tenant_id != application.tenant_id]
    if foreign:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Routing produced agencies outside this city: {foreign}",
        )

    if not agencies:
        # No matrix rows for this event type. Submitting would create an
        # application that no agency can see, which looks approved by absence.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"No agencies are configured to review "
                f"{application.event_type.value} applications in this city. "
                f"Ask a City Admin to set the routing rules."
            ),
        )

    already_assigned = {
        row[0]
        for row in session.execute(
            select(ReviewTask.agency_id).where(
                ReviewTask.application_id == application.id
            )
        )
    }
    if already_assigned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application has already been submitted for review",
        )

    application.status = _STATUS_ON_SUBMIT

    for agency in agencies:
        session.add(
            ReviewTask(
                application_id=application.id,
                agency_id=agency.id,
                tenant_id=application.tenant_id,
                status=_INITIAL_REVIEW_STATUS,
            )
        )

    session.add(
        AuditEvent(
            application_id=application.id,
            tenant_id=application.tenant_id,
            user_id=current_user.id,
            agency_id=None,
            action=_AUDIT_APPLICATION_STATUS_CHANGE,
            old_status=ApplicationStatus.DRAFT.value,
            new_status=_STATUS_ON_SUBMIT.value,
            comment=f"Submitted for review by {len(agencies)} agency(ies)",
        )
    )

    # Single commit: the status change and every task land together or not at all.
    # tenant_id is copied from the application, never from the request, so a
    # task cannot be created outside the submitting city's tenant.
    session.commit()
    session.refresh(application)

    return SubmitApplicationResponse(
        application=_application_response(application),
        required_agencies=[RequiredAgency.model_validate(a) for a in agencies],
        attendance_override_applied=bool(
            agencies_required_by_attendance(session, application)
        ),
    )


@router.post("/{application_id}/resubmit", response_model=ResubmitApplicationResponse)
def resubmit_application(
    application_id: uuid.UUID,
    session: TenantSession,
    current_user: OrganizerOnly,
) -> ResubmitApplicationResponse:
    """
    Resubmit a corrected application and put the requesting agencies back to Pending.

    The central rule is selectivity. Only tasks whose status is Changes Requested
    go back to Pending:

      * **Changes Requested -> Pending.** This is the whole point. The agency asked
        for something and has not seen the fix yet.
      * **Approved is preserved.** The agency already said yes. Making the
        organizer earn that a second time is wasteful, and resetting it would
        lose the fact that it had been given.
      * **Rejected is never reopened.** A rejection has no reversal in this
        lifecycle, and the application cannot be in Changes Requested with a
        rejected task anyway. Asserted rather than assumed, so a future change
        that makes that reachable fails here instead of silently reviving it.
      * **Pending stays Pending.** It has not been asked anything, so there is
        nothing to reset.

    Each agency's *previous* decision is preserved. The comment is cleared only on
    the tasks being reset, and even then the agency's words remain in the audit
    trail: the `review.changes_requested` row is appended to, never replaced.

    Concurrency. Locks are taken in one fixed order — this application's review
    tasks, then the application — because that is the order the reviewer decision
    path already uses. Resubmission locks several tasks *and* the application, so
    taking them the other way round would let a reviewer and an organizer deadlock
    against each other: the reviewer holds its own task and waits for the
    application, while the organizer holds the application and waits for the task.

    The task query goes first, before the ownership check, because the lock order
    is what keeps that safe to do. RLS scopes it to the caller's own tenant, so it
    cannot block another city, and if the organizer turns out not to own this
    application the request 404s and the transaction rolls back, releasing the
    locks it took.

    A second resubmission arriving while the first is in flight blocks on those
    locks, then re-reads the status — by which point the application is no longer
    Changes Requested, so it is refused rather than resetting the tasks a second
    time. The retry guard below covers the ordinary double-click, where the
    requests do not actually overlap.
    """
    tasks = list(
        session.execute(
            select(ReviewTask)
            .where(ReviewTask.application_id == application_id)
            .with_for_update()
            .options(selectinload(ReviewTask.agency))
        )
        .scalars()
        .unique()
    )

    application = _load_own_application(
        session, current_user, application_id, for_update=True
    )

    try:
        assert_application_resubmittable(application.status)
    except InvalidStatusTransition as exc:
        raise _transition_conflict(str(exc)) from exc

    # Same completeness check as the first submission: resubmitting an
    # application that is still missing its dates or location would send the
    # agencies back to work they cannot do.
    missing = missing_submission_fields(application)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Cannot resubmit: missing required fields {', '.join(missing)}"
            ),
        )

    previous_application_status = ApplicationStatus(application.status)

    if not tasks:
        # Cannot happen: submission creates tasks in the same transaction that set
        # the status. Guarded because resetting nothing while claiming to have
        # resubmitted would be worse than an error.
        raise _transition_conflict(
            "This application has no review tasks to resubmit"
        )

    if not any(should_reset_on_resubmission(t.status) for t in tasks):
        # The application says Changes Requested but no task does. Either a
        # reviewer decision is still in flight, or the state is inconsistent.
        # Refusing is the safe answer: acting would reset nothing and silently
        # move the application back to Submitted.
        raise _transition_conflict(
            "No agency is currently requesting changes on this application"
        )

    reset: list[ReviewTask] = []
    preserved: list[ReviewTask] = []
    still_pending: list[ReviewTask] = []

    for task in tasks:
        if should_reset_on_resubmission(task.status):
            reset.append(task)
        elif ReviewStatus(task.status) is ReviewStatus.APPROVED:
            preserved.append(task)
        elif ReviewStatus(task.status) is ReviewStatus.PENDING:
            still_pending.append(task)
        else:
            # A rejected task cannot coexist with Changes Requested, but if it ever
            # does, refusing beats reopening a rejection.
            raise _transition_conflict(
                "This application has a rejected review and cannot be resubmitted"
            )

    for task in reset:
        task.status = _INITIAL_REVIEW_STATUS
        # The comment goes with the reset: it described the *previous* submission,
        # and leaving it on a Pending task would misattribute it as feedback about
        # the corrected one. The agency's actual words remain in the audit trail.
        task.comment = None

        session.add(
            AuditEvent(
                application_id=application.id,
                tenant_id=application.tenant_id,
                user_id=current_user.id,
                agency_id=task.agency_id,
                action=_AUDIT_REVIEW_TASK_RESET,
                old_status=ReviewStatus.CHANGES_REQUESTED.value,
                new_status=ReviewStatus.PENDING.value,
                comment=f"Reset to Pending for resubmission of {task.agency.name}",
            )
        )

    # Flush before recomputing: the session uses autoflush=False, so the status
    # read below would otherwise see the pre-reset values and derive the wrong
    # aggregate.
    session.flush()

    new_application_status = resubmission_application_status(
        [ReviewStatus(t.status) for t in tasks]
    )
    application.status = new_application_status

    session.add(
        AuditEvent(
            application_id=application.id,
            tenant_id=application.tenant_id,
            user_id=current_user.id,
            agency_id=None,
            action=_AUDIT_APPLICATION_RESUBMITTED,
            old_status=previous_application_status.value,
            new_status=new_application_status.value,
            comment=(
                f"Resubmitted; {len(reset)} agency review(s) reset to Pending"
                + (f", {len(preserved)} approval(s) preserved" if preserved else "")
            ),
        )
    )

    if new_application_status is not previous_application_status:
        session.add(
            AuditEvent(
                application_id=application.id,
                tenant_id=application.tenant_id,
                user_id=current_user.id,
                agency_id=None,
                action=_AUDIT_APPLICATION_STATUS_CHANGE,
                old_status=previous_application_status.value,
                new_status=new_application_status.value,
                comment="Derived from the review tasks after resubmission",
            )
        )

    # Single commit: task resets, status change and every audit row land
    # together. A resubmission that failed halfway would leave the agencies in a
    # state the organizer had not asked for.
    session.commit()
    session.refresh(application)

    def agencies_of(group: list[ReviewTask]) -> list[RequiredAgency]:
        return [
            RequiredAgency(id=t.agency_id, name=t.agency.name if t.agency else "")
            for t in sorted(group, key=lambda t: t.agency.name if t.agency else "")
        ]

    return ResubmitApplicationResponse(
        application=_application_response(application),
        reset_agencies=agencies_of(reset),
        preserved_agencies=agencies_of(preserved),
        still_pending_agencies=agencies_of(still_pending),
    )


@router.get("/{application_id}/history", response_model=ApplicationHistoryResponse)
def get_application_history(
    application_id: uuid.UUID,
    session: TenantSession,
    current_user: OrganizerOnly,
) -> ApplicationHistoryResponse:
    """
    The audit timeline for one of the caller's own applications.

    Ordered oldest first, so it reads as a sequence. Same rows the reviewer
    history endpoint exposes, but gated on ownership rather than on a review
    assignment — the organizer is entitled to the history of their own permit
    whether or not they are a reviewer.
    """
    application = _load_own_application(session, current_user, application_id)

    events = session.execute(
        select(AuditEvent)
        .where(AuditEvent.application_id == application.id)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
    ).scalars()

    return ApplicationHistoryResponse(
        application_id=application.id,
        application_status=ApplicationStatus(application.status),
        events=[AuditEventResponse.model_validate(e) for e in events],
    )