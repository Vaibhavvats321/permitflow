from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models import ApplicationStatus, EventType, ReviewStatus, ReviewTask
from app.schemas.review import AuditEventResponse


def _as_utc(value: datetime | None) -> datetime | None:
    """
    Normalise a datetime to timezone-aware UTC.

    The columns are `timestamp with time zone`. A naive datetime sent by a
    browser without a timezone would otherwise be interpreted in whatever
    timezone the *database server* happens to be set to, silently shifting the
    event date. Treating it as UTC is the least surprising choice for a
    city-calendar field and is what the browser sends anyway.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ApplicationWrite(BaseModel):
    """
    Editable fields of a permit application.

    Deliberately excludes `status`, `submitter_id` and `tenant_id`: those are
    server-owned. An organizer chooses *what* the application says; the API
    decides whose it is and where it lives.

    `extra="forbid"` makes a request that tries to set one of those fail loudly
    with a 422. Silently dropping them would let a client believe it had
    submitted an application, or filed one under a different city, when it had
    done neither.
    """

    model_config = ConfigDict(extra="forbid")

    event_name: str = Field(max_length=255)
    event_type: EventType
    start_date: datetime | None = None
    end_date: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    expected_attendance: int | None = Field(default=None, ge=0)
    description: str | None = None

    @field_validator("event_name", "location", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        """Trim surrounding whitespace so '   ' is not a valid event name."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("event_name")
    @classmethod
    def _require_event_name(cls, value: str) -> str:
        if not value:
            raise ValueError("event_name must not be blank")
        return value

    @field_validator("start_date", "end_date")
    @classmethod
    def _normalise_timestamps(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)

    @model_validator(mode="after")
    def _end_after_start(self) -> "ApplicationWrite":
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must be on or after start_date")
        return self


class ApplicationCreate(ApplicationWrite):
    """Payload for `POST /applications`. Creates a draft."""


class ApplicationUpdate(ApplicationWrite):
    """
    Payload for `PUT /applications/{id}`.

    Full replacement of the editable fields rather than a sparse patch: a draft
    has no concurrent editor, so there is no merge ambiguity to resolve, and
    the client cannot accidentally leave a stale field behind.
    """


class ApplicationResponse(ApplicationWrite):
    """
    An application as the organizer sees it, with per-agency review progress.

    `reviews` is the tracking view: one entry per agency that was asked to
    review, carrying that agency's decision and comment. It is an empty list for a
    draft, which has not been submitted and therefore has no reviewers.

    Included on create and submit responses too, where it is `[]`, so the shape
    does not change between "just made it" and "fetched it" — a client can read
    one response shape and never have to special-case a draft.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ApplicationStatus
    submitter_id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Populated by the routes from `review_summaries(application.review_tasks)`.
    # Declared as a plain field with an empty default rather than read off the
    # ORM object, because the schema layer must not depend on the model layer.
    reviews: list[AgencyReviewStatus] = Field(default_factory=list)


class AgencyReviewStatus(BaseModel):
    """
    One agency's decision on an application, as the organizer sees it.

    This is the per-agency progress view that makes tracking useful: the
    organizer can see which agency has decided, which has not, and why, without
    inferring any of it from the aggregate status.

    Deliberately no reviewer identity. The brief asks for the agency's status,
    its comment and timestamps; naming the individual who pressed the button is
    not needed to act on the feedback and is a small privacy cost. The
    application-level history carries `user_id` for anyone who genuinely needs
    to audit a specific decision.
    """

    model_config = ConfigDict(from_attributes=True)

    agency_id: uuid.UUID
    agency_name: str
    review_status: ReviewStatus
    # The agency's own words. Null while the task is still Pending.
    comment: str | None = None
    created_at: datetime
    # Moves on every decision and on every resubmission reset, so a task that was
    # sent back to an agency is visibly newer than the ones that were not.
    updated_at: datetime


def review_summaries(
    tasks: Iterable[ReviewTask],
) -> list[AgencyReviewStatus]:
    """
    Build the per-agency tracking entries for an application.

    A function rather than a model property: the model layer should not import
    the schema layer, and this needs the `agency` relationship eager-loaded to
    name the agencies. Sorted by agency name so the tracking view has a stable
    order across requests.

    A task whose agency relationship is missing gets an empty name rather than
    raising. That cannot happen through the API — the FK guarantees an agency
    exists — but a tracking view that 500s on unexpected data would hide the rest
    of the application.
    """
    summaries = [
        AgencyReviewStatus(
            agency_id=task.agency_id,
            agency_name=task.agency.name if task.agency is not None else "",
            review_status=task.status,
            comment=task.comment,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        for task in tasks
    ]
    return sorted(summaries, key=lambda s: (s.agency_name, str(s.agency_id)))


class RequiredAgency(BaseModel):
    """One agency that must review the submitted application."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class SubmitApplicationResponse(BaseModel):
    """
    The submitted application together with the review tasks it created.

    Returning the agency list (rather than only a 200) means the organizer can
    see who was asked to review without a second call, and it makes the
    attendance thresholds visible: an agency whose threshold the attendance
    exceeds appears here and not on a smaller event.
    """

    application: ApplicationResponse
    required_agencies: list[RequiredAgency]
    # Whether the expected attendance exceeded at least one agency's configured
    # threshold. Reported so the extra review is explainable rather than
    # mysterious — the agencies themselves are in `required_agencies`.
    attendance_override_applied: bool = False


class ResubmitApplicationResponse(BaseModel):
    """
    The result of resubmitting a corrected application.

    Returns which agencies were asked to look again. That is the whole point of
    the operation, so it is explicit rather than something the organizer has to
    diff against the previous state to discover: an agency that had already
    approved is absent from `reset_agencies`, and the organizer should be able to
    see that without asking.
    """

    application: ApplicationResponse
    # Agencies whose changes-requested task went back to Pending.
    reset_agencies: list[RequiredAgency]
    # Agencies whose approval was preserved and were not asked again.
    preserved_agencies: list[RequiredAgency]
    # Agencies that had not yet decided when the organizer resubmitted. Their
    # task was already Pending and stays Pending; they are listed so the organizer
    # knows the full audience, not just the part that moved.
    still_pending_agencies: list[RequiredAgency]


class ApplicationHistoryResponse(BaseModel):
    """
    An application's audit timeline for its organizer.

    Separate from the reviewer-scoped history in `app.schemas.review`: that one
    is gated on a review assignment, this one on ownership. Same table, same
    rows, different question.
    """

    application_id: uuid.UUID
    application_status: ApplicationStatus
    events: list[AuditEventResponse]


class SubmissionRequirementError(ValueError):
    """
    The application cannot sensibly be submitted yet.

    Raised when required fields are still missing. Surfaced as a 422 by the
    route: this is a problem with the payload, not with authorization.
    """


def missing_submission_fields(application: ApplicationWrite) -> list[str]:
    """
    Names of the fields that must be present before submission.

    A draft may be incomplete, but submitting one would create review tasks for
    agencies that cannot assess it. Which fields those are is a product decision,
    so it lives here rather than being scattered across the route.
    """
    missing = [
        name
        for name in ("start_date", "end_date", "location", "expected_attendance")
        if getattr(application, name) in (None, "")
    ]
    return missing