from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.routing import LARGE_EVENT_REQUIRED_AGENCY
from app.models import ApplicationStatus, EventType


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
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ApplicationStatus
    submitter_id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


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
    attendance override visible: Fire appears on a large event and not on a
    small one.
    """

    application: ApplicationResponse
    required_agencies: list[RequiredAgency]
    # Whether the "over 5,000 attendees" threshold was exceeded. Reported so the
    # extra Fire review is explainable to the organizer rather than mysterious.
    attendance_override_applied: bool = False


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