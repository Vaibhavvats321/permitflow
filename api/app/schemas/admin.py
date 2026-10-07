"""
app/schemas/admin.py

Wire formats for the City Admin workspace.

City Admins manage their city's configuration: agencies, users, and routing rules.
All endpoints are tenant-scoped; the admin's tenant_id comes from the verified JWT,
never from the request body.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ApplicationStatus, EventType, UserRole
from app.schemas.review import AuditEventResponse


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class DashboardSummary(BaseModel):
    """Aggregate counts for the City Admin's landing page."""

    total_applications: int
    draft_applications: int
    submitted_applications: int
    under_review_applications: int
    approved_applications: int
    rejected_applications: int
    changes_requested_applications: int
    average_days_to_decision: Optional[float] = None


# ---------------------------------------------------------------------------
# Agency Management
# ---------------------------------------------------------------------------


class AgencyResponse(BaseModel):
    """An agency as the City Admin sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    # Expected attendance strictly above this makes the agency a required
    # reviewer; None means the agency is only ever required by the matrix.
    attendance_threshold: Optional[int] = None


class AgencyCreate(BaseModel):
    """Payload for creating a new agency."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=255)
    attendance_threshold: Optional[int] = Field(default=None, ge=0, le=2_000_000_000)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("agency name must not be blank")
        return stripped


class AgencyUpdate(BaseModel):
    """
    Payload for updating an agency's name and/or attendance threshold.

    `attendance_threshold` is only applied when present in the request body:
    omitting it leaves the current value alone, while an explicit JSON `null`
    clears it (the agency becomes matrix-only).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=255)
    attendance_threshold: Optional[int] = Field(default=None, ge=0, le=2_000_000_000)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("agency name must not be blank")
        return stripped


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """A user as the City Admin sees it. Never includes password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    agency_id: Optional[uuid.UUID] = None
    agency_name: Optional[str] = None
    created_at: datetime


class UserCreate(BaseModel):
    """Payload for creating a new user."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=255)
    role: UserRole
    agency_id: Optional[uuid.UUID] = None

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def _require_password(cls, value: str) -> str:
        if len(value.strip()) < 8:
            raise ValueError("password must be at least 8 characters")
        return value

    @field_validator("agency_id")
    @classmethod
    def _validate_agency_id(cls, value: Optional[uuid.UUID]) -> Optional[uuid.UUID]:
        if value is None:
            return None
        # The route will validate that the agency belongs to the admin's tenant
        # and that the role is AGENCY_REVIEWER. This validator only checks format.
        return value


class UserUpdate(BaseModel):
    """Payload for updating a user. Cannot change tenant_id or role."""

    model_config = ConfigDict(extra="forbid")

    email: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, min_length=8, max_length=255)
    agency_id: Optional[uuid.UUID] = None

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def _require_password(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if len(value.strip()) < 8:
            raise ValueError("password must be at least 8 characters")
        return value


# ---------------------------------------------------------------------------
# Routing Configuration
# ---------------------------------------------------------------------------


class RoutingRuleResponse(BaseModel):
    """One routing rule: which agency reviews which event type."""

    model_config = ConfigDict(from_attributes=True)

    event_type: str
    agency_id: uuid.UUID
    agency_name: str


class RoutingRuleCreate(BaseModel):
    """Payload for creating a routing rule."""

    model_config = ConfigDict(extra="forbid")

    event_type: str
    agency_id: uuid.UUID


class RoutingRuleUpdate(BaseModel):
    """Payload for updating a routing rule (change the agency)."""

    model_config = ConfigDict(extra="forbid")

    agency_id: uuid.UUID


# ---------------------------------------------------------------------------
# Application History
# ---------------------------------------------------------------------------


class AdminAuditEventResponse(AuditEventResponse):
    """
    One audit timeline entry, enriched with readable actor information.

    Extends the shared `AuditEventResponse` so every audit field stays
    identical to what the organizer and reviewer views see; only the two
    display fields are added. They are populated by outer joins on the query
    side: a system-generated event (no actor) or an event whose actor row is
    unavailable degrades to `None` instead of failing the request. No other
    user field is exposed — never `password_hash`.
    """

    actor_email: Optional[str] = None
    agency_name: Optional[str] = None


class AdminApplicationHistoryResponse(BaseModel):
    """The audit timeline for one application, as the City Admin sees it."""

    application_id: uuid.UUID
    application_status: ApplicationStatus
    events: list[AdminAuditEventResponse]