"""
app/schemas/review.py

Wire formats for the reviewer queue and reviewer actions.

Reviewers never accept application fields. The only body a reviewer can send is
a decision (`approve` / `reject` / `request_changes`) plus a comment. There is no
schema in this module that would let a reviewer edit an event's dates, location
or attendance, which is what stops a reviewer from rewriting the thing under
review.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ApplicationStatus, EventType, ReviewStatus


class ReviewTaskApplication(BaseModel):
    """
    The application a review task points at, as a reviewer needs to see it.

    A flattened copy rather than the full `ApplicationResponse`: the reviewer
    view deliberately omits `submitter_id` and `tenant_id`, which are internal
    bookkeeping the agency has no use for, and exposes only what the agency is
    being asked to assess.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_name: str
    event_type: EventType
    start_date: datetime | None = None
    end_date: datetime | None = None
    location: str | None = None
    expected_attendance: int | None = None
    description: str | None = None
    status: ApplicationStatus


class ReviewTaskResponse(BaseModel):
    """
    One queued review task, with the application it refers to.

    `review_status` is the agency's own decision. The embedded `application.status`
    is the aggregate across every agency, so a reviewer can see that their
    colleagues have already rejected without having to open each application.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    agency_id: uuid.UUID
    review_status: ReviewStatus = Field(validation_alias="status")
    comment: str | None = None
    created_at: datetime
    updated_at: datetime
    application: ReviewTaskApplication


class ReviewActionRequest(BaseModel):
    """
    A reviewer's decision on one task.

    `extra="forbid"` so a request that tries to smuggle in application fields —
    or a `status` — fails with a 422 instead of being silently dropped. A
    reviewer who believes they can set `expected_attendance` here has been
    misinformed either way, but a loud failure is better than a silent one.

    The comment is required and must contain something other than whitespace. A
    bare approve with no reasoning leaves the organizer nothing to act on, so the
    requirement is enforced at the schema rather than left to each route.
    """

    model_config = ConfigDict(extra="forbid")

    action: str = Field(max_length=64)
    comment: str = Field(max_length=2000)

    @field_validator("action")
    @classmethod
    def _normalise_action(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("comment")
    @classmethod
    def _require_comment(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("a comment is required for every review action")
        return stripped


class ReviewActionResponse(BaseModel):
    """
    The result of a reviewer action.

    Returns the updated task and the application status it produced, so the
    caller can see the aggregate without a follow-up request and without
    guessing whether their decision was the last one needed.
    """

    task: ReviewTaskResponse
    # The application status immediately after this action. It only moves on
    # some decisions: one agency approving out of two leaves it Under Review.
    application_status: ApplicationStatus


class AuditEventResponse(BaseModel):
    """
    One entry from an application's history.

    Append-only: there is no update or delete path for these rows, in the API or
    in the schema. `old_status` and `new_status` are stored as strings because
    the same column carries both the review task status and the application
    status depending on the event.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    user_id: uuid.UUID | None = None
    agency_id: uuid.UUID | None = None
    action: str
    old_status: str | None = None
    new_status: str | None = None
    comment: str | None = None
    created_at: datetime


class ApplicationHistoryResponse(BaseModel):
    """The full audit timeline for an application, oldest first."""

    application_id: uuid.UUID
    application_status: ApplicationStatus
    events: list[AuditEventResponse]