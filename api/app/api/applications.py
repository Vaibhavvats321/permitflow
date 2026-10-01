"""
app/api/applications.py

Organizer-facing permit applications.

  POST /applications         create a draft
  GET  /applications         list my applications
  GET  /applications/{id}    fetch one of mine
  PUT  /applications/{id}    edit one of mine

Scope note: this module covers drafting and submission. Submission resolves the
reviewing agencies and creates one Pending review task each. Reviewer decisions,
the aggregate status lifecycle, and resubmission are not implemented yet.

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
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.routing import is_large_event, required_agencies
from app.deps import CurrentUser, get_tenant_db, require_role
from app.models import Application, ApplicationStatus, EventType, ReviewStatus, ReviewTask, UserRole
from app.schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    RequiredAgency,
    SubmitApplicationResponse,
    missing_submission_fields,
)

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

# A generous upper bound. The point is to stop one request from pulling an
# unbounded result set; real deployments would page.
_MAX_PAGE_SIZE = 100


def _application_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_APPLICATION_NOT_FOUND_DETAIL,
    )


def _load_own_application(
    session: Session, current_user: CurrentUser, application_id: uuid.UUID
) -> Application:
    """
    Fetch an application that the caller both owns and can see.

    The `submitter_id` predicate is the ownership check. The tenant predicate is
    redundant under RLS and deliberately omitted: RLS is the authority on
    tenancy, and duplicating it in the query would let the two drift apart. If
    RLS were ever weakened, the ownership predicate would still hold.
    """
    application = session.execute(
        select(Application).where(
            Application.id == application_id,
            Application.submitter_id == current_user.id,
        )
    ).scalar_one_or_none()

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
    return application


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
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)] = 50,
) -> list[Application]:
    """
    List the caller's own applications, newest first.

    RLS restricts the result to the caller's tenant; `submitter_id` restricts it
    to the caller. Neither is redundant: a city may have several organizers, and
    one must not see another's drafts.
    """
    query = select(Application).where(Application.submitter_id == current_user.id)

    if status_filter is not None:
        query = query.where(Application.status == status_filter)
    if event_type_filter is not None:
        query = query.where(Application.event_type == event_type_filter)

    # created_at is not unique, so id breaks ties to keep paging deterministic.
    query = (
        query.order_by(Application.created_at.desc(), Application.id.desc())
        .offset(offset)
        .limit(limit)
    )

    return list(session.execute(query).scalars())


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: uuid.UUID,
    session: TenantSession,
    current_user: OrganizerOnly,
) -> Application:
    """Fetch one of the caller's own applications."""
    return _load_own_application(session, current_user, application_id)


@router.put("/{application_id}", response_model=ApplicationResponse)
def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    session: TenantSession,
    current_user: OrganizerOnly,
) -> Application:
    """
    Replace the editable fields of a draft.

    Ownership is re-checked before the write. Only drafts are editable here;
    once an application has been submitted the lifecycle rules take over, and
    allowing silent edits to a submitted application would let an organizer
    change what agencies are reviewing without triggering a new review.
    """
    application = _load_own_application(session, current_user, application_id)

    if application.status is not ApplicationStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only draft applications can be edited; this one is "
                f"{ApplicationStatus(application.status).value}"
            ),
        )

    for field, value in payload.model_dump().items():
        setattr(application, field, value)

    # onupdate only fires if SQLAlchemy sees a change, and the flush below
    # guarantees that the dirty row is written.
    session.commit()
    session.refresh(application)
    return application


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

    # Single commit: the status change and every task land together or not at all.
    # tenant_id is copied from the application, never from the request, so a
    # task cannot be created outside the submitting city's tenant.
    session.commit()
    session.refresh(application)

    return SubmitApplicationResponse(
        application=ApplicationResponse.model_validate(application),
        required_agencies=[RequiredAgency.model_validate(a) for a in agencies],
        attendance_override_applied=is_large_event(application),
    )