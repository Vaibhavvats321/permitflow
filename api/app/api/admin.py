"""
app/api/admin.py

City Admin endpoints.

Scope: tenant-scoped management of agencies, users, and routing rules.
All endpoints require the CITY_ADMIN role and are automatically scoped to the
admin's own tenant via the RLS-enabled database session.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, UTC
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.deps import CurrentUser, get_tenant_db, require_role
from app.models import (
    Agency,
    Application,
    ApplicationStatus,
    AuditEvent,
    EventType,
    EventTypeAgencyRule,
    ReviewStatus,
    ReviewTask,
    User,
    UserRole,
)
from app.schemas.admin import (
    AdminApplicationHistoryResponse,
    AdminAuditEventResponse,
    AgencyCreate,
    AgencyResponse,
    AgencyUpdate,
    DashboardSummary,
    RoutingRuleCreate,
    RoutingRuleResponse,
    RoutingRuleUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.schemas.application import (
    ApplicationResponse,
    ApplicationStatus as AppStatus,
    review_summaries,
)

router = APIRouter(prefix="/admin", tags=["admin"])

AdminOnly = Annotated[CurrentUser, Depends(require_role(UserRole.CITY_ADMIN))]
TenantSession = Annotated[Session, Depends(get_tenant_db)]

_MAX_PAGE_SIZE = 100


def _not_found(detail: str = "Resource not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=DashboardSummary)
def get_dashboard(
    session: TenantSession,
    current_user: AdminOnly,
) -> DashboardSummary:
    """
    Summary counts for the City Admin's landing page.

    All counts are scoped to the admin's tenant via the RLS session.
    Average days to decision is computed over completed applications
    (Approved or Rejected) that have at least one review task.
    """
    # Total and per-status counts
    total_apps = session.scalar(
        select(func.count(Application.id))
    ) or 0

    draft_apps = session.scalar(
        select(func.count(Application.id)).where(Application.status == ApplicationStatus.DRAFT)
    ) or 0

    submitted_apps = session.scalar(
        select(func.count(Application.id)).where(Application.status == ApplicationStatus.SUBMITTED)
    ) or 0

    under_review_apps = session.scalar(
        select(func.count(Application.id)).where(Application.status == ApplicationStatus.UNDER_REVIEW)
    ) or 0

    approved_apps = session.scalar(
        select(func.count(Application.id)).where(Application.status == ApplicationStatus.APPROVED)
    ) or 0

    rejected_apps = session.scalar(
        select(func.count(Application.id)).where(Application.status == ApplicationStatus.REJECTED)
    ) or 0

    changes_requested_apps = session.scalar(
        select(func.count(Application.id)).where(Application.status == ApplicationStatus.CHANGES_REQUESTED)
    ) or 0

    # Average days to decision: for completed applications (Approved/Rejected)
    # that have at least one review task. Measure from application creation
    # to the first decision that moved it out of Submitted/Under Review.
    avg_days_result = session.execute(
        select(
            func.avg(
                func.extract("epoch", ReviewTask.updated_at - Application.created_at) / 86400.0
            )
        )
        .select_from(ReviewTask)
        .join(Application, Application.id == ReviewTask.application_id)
        .where(
            Application.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REJECTED]),
            ReviewTask.status != ReviewStatus.PENDING,
        )
    ).scalar()

    average_days = float(avg_days_result) if avg_days_result is not None else None

    return DashboardSummary(
        total_applications=total_apps,
        draft_applications=draft_apps,
        submitted_applications=submitted_apps,
        under_review_applications=under_review_apps,
        approved_applications=approved_apps,
        rejected_applications=rejected_apps,
        changes_requested_applications=changes_requested_apps,
        average_days_to_decision=average_days,
    )


# ---------------------------------------------------------------------------
# Agency Management
# ---------------------------------------------------------------------------


@router.get("/agencies", response_model=List[AgencyResponse])
def list_agencies(
    session: TenantSession,
    current_user: AdminOnly,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> List[AgencyResponse]:
    """
    List all agencies in the admin's tenant, ordered by name.
    """
    agencies = session.execute(
        select(Agency)
        .order_by(Agency.name)
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    return [AgencyResponse.model_validate(a, from_attributes=True) for a in agencies]


@router.post(
    "/agencies",
    response_model=AgencyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agency(
    payload: AgencyCreate,
    session: TenantSession,
    current_user: AdminOnly,
) -> AgencyResponse:
    """
    Create a new agency in the admin's tenant.

    Agency names must be unique within the tenant.
    """
    # Check for duplicate name within tenant
    existing = session.execute(
        select(Agency).where(
            Agency.tenant_id == current_user.tenant_id,
            Agency.name == payload.name,
        )
    ).scalar_one_or_none()

    if existing:
        raise _conflict(f"An agency named '{payload.name}' already exists in this city")

    agency = Agency(
        name=payload.name,
        tenant_id=current_user.tenant_id,
    )
    session.add(agency)
    session.commit()
    session.refresh(agency)

    return AgencyResponse.model_validate(agency, from_attributes=True)


@router.get("/agencies/{agency_id}", response_model=AgencyResponse)
def get_agency(
    agency_id: uuid.UUID,
    session: TenantSession,
    current_user: AdminOnly,
) -> AgencyResponse:
    """Fetch one agency in the admin's tenant."""
    agency = session.execute(
        select(Agency).where(
            Agency.id == agency_id,
            Agency.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()

    if agency is None:
        raise _not_found("Agency not found")

    return AgencyResponse.model_validate(agency, from_attributes=True)


@router.patch("/agencies/{agency_id}", response_model=AgencyResponse)
def update_agency(
    agency_id: uuid.UUID,
    payload: AgencyUpdate,
    session: TenantSession,
    current_user: AdminOnly,
) -> AgencyResponse:
    """
    Update an agency's name.

    Name must remain unique within the tenant.
    """
    agency = session.execute(
        select(Agency).where(
            Agency.id == agency_id,
            Agency.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()

    if agency is None:
        raise _not_found("Agency not found")

    # Check for duplicate name (excluding self)
    existing = session.execute(
        select(Agency).where(
            Agency.tenant_id == current_user.tenant_id,
            Agency.name == payload.name,
            Agency.id != agency_id,
        )
    ).scalar_one_or_none()

    if existing:
        raise _conflict(f"An agency named '{payload.name}' already exists in this city")

    agency.name = payload.name
    session.commit()
    session.refresh(agency)

    return AgencyResponse.model_validate(agency, from_attributes=True)


@router.delete("/agencies/{agency_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agency(
    agency_id: uuid.UUID,
    session: TenantSession,
    current_user: AdminOnly,
) -> None:
    """
    Delete an agency.

    Fails with 409 if the agency is referenced by routing rules or review tasks.
    """
    agency = session.execute(
        select(Agency).where(
            Agency.id == agency_id,
            Agency.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()

    if agency is None:
        raise _not_found("Agency not found")

    # Check for references in routing rules
    routing_ref = session.execute(
        select(EventTypeAgencyRule).where(
            EventTypeAgencyRule.agency_id == agency_id,
        )
    ).first()

    if routing_ref:
        raise _conflict(
            "Cannot delete agency: it is referenced by routing rules. "
            "Remove or reassign the routing rules first."
        )

    # Check for references in review tasks
    review_ref = session.execute(
        select(ReviewTask).where(
            ReviewTask.agency_id == agency_id,
        )
    ).first()

    if review_ref:
        raise _conflict(
            "Cannot delete agency: it has existing review tasks. "
            "Reassign or complete those tasks first."
        )

    session.delete(agency)
    session.commit()


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------


def _user_response(user: User, agency_name: Optional[str] = None) -> UserResponse:
    """Build a UserResponse with agency name if available."""
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        agency_id=user.agency_id,
        agency_name=agency_name,
        created_at=user.created_at,
    )


@router.get("/users", response_model=List[UserResponse])
def list_users(
    session: TenantSession,
    current_user: AdminOnly,
    role_filter: Annotated[
        Optional[UserRole],
        Query(alias="role", description="Filter by role."),
    ] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> List[UserResponse]:
    """
    List all users in the admin's tenant, with optional role filter.
    """
    query = select(User).where(User.tenant_id == current_user.tenant_id)

    if role_filter is not None:
        query = query.where(User.role == role_filter)

    query = query.order_by(User.created_at.desc()).offset(offset).limit(limit)

    users = session.execute(query).scalars().all()

    # Fetch agency names in a single query
    agency_ids = [u.agency_id for u in users if u.agency_id]
    agency_names = {}
    if agency_ids:
        agencies = session.execute(
            select(Agency).where(Agency.id.in_(agency_ids))
        ).scalars().all()
        agency_names = {a.id: a.name for a in agencies}

    return [
        _user_response(u, agency_names.get(u.agency_id))
        for u in users
    ]


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    session: TenantSession,
    current_user: AdminOnly,
) -> UserResponse:
    """
    Create a new user in the admin's tenant.

    - Email must be unique globally (enforced by DB unique constraint).
    - Password is hashed with Argon2.
    - Role must be one of the three supported roles.
    - Agency Reviewer requires an agency_id that belongs to this tenant.
    - Organizer and City Admin must not have an agency_id.
    """
    # Validate role-specific agency requirements
    if payload.role == UserRole.AGENCY_REVIEWER:
        if payload.agency_id is None:
            raise _unprocessable("Agency Reviewer requires an agency_id")

        # Verify agency exists and belongs to this tenant
        agency = session.execute(
            select(Agency).where(
                Agency.id == payload.agency_id,
                Agency.tenant_id == current_user.tenant_id,
            )
        ).scalar_one_or_none()

        if agency is None:
            raise _not_found("Agency not found or does not belong to this city")

    else:
        # Organizer and City Admin must not have an agency
        if payload.agency_id is not None:
            raise _unprocessable(
                f"{payload.role.value} users cannot be assigned to an agency"
            )

    # Check email uniqueness
    existing = session.execute(
        select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()

    if existing:
        raise _conflict("A user with this email already exists")

    # Hash password
    from app.core.security import hash_password

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        tenant_id=current_user.tenant_id,
        agency_id=payload.agency_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    agency_name = None
    if user.agency_id:
        agency = session.get(Agency, user.agency_id)
        agency_name = agency.name if agency else None

    return _user_response(user, agency_name)


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: uuid.UUID,
    session: TenantSession,
    current_user: AdminOnly,
) -> UserResponse:
    """Fetch one user in the admin's tenant."""
    user = session.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()

    if user is None:
        raise _not_found("User not found")

    agency_name = None
    if user.agency_id:
        agency = session.get(Agency, user.agency_id)
        agency_name = agency.name if agency else None

    return _user_response(user, agency_name)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    session: TenantSession,
    current_user: AdminOnly,
) -> UserResponse:
    """
    Update a user.

    - Cannot change tenant_id (implicitly enforced by tenant-scoped session).
    - Cannot change role (not in payload).
    - Email must remain unique if changed.
    - Password is re-hashed if provided.
    - Agency assignment can be changed for Agency Reviewers.
    """
    user = session.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()

    if user is None:
        raise _not_found("User not found")

    # Email uniqueness check
    if payload.email is not None and payload.email.lower() != user.email:
        existing = session.execute(
            select(User).where(User.email == payload.email.lower())
        ).scalar_one_or_none()

        if existing:
            raise _conflict("A user with this email already exists")

        user.email = payload.email.lower()

    # Password update
    if payload.password is not None:
        from app.core.security import hash_password
        user.password_hash = hash_password(payload.password)

    # Agency assignment change (only for Agency Reviewers)
    if payload.agency_id is not None:
        if user.role != UserRole.AGENCY_REVIEWER:
            raise _unprocessable(
                "Only Agency Reviewer users can be assigned to an agency"
            )

        # Verify agency exists and belongs to this tenant
        agency = session.execute(
            select(Agency).where(
                Agency.id == payload.agency_id,
                Agency.tenant_id == current_user.tenant_id,
            )
        ).scalar_one_or_none()

        if agency is None:
            raise _not_found("Agency not found or does not belong to this city")

        user.agency_id = payload.agency_id

    session.commit()
    session.refresh(user)

    agency_name = None
    if user.agency_id:
        agency = session.get(Agency, user.agency_id)
        agency_name = agency.name if agency else None

    return _user_response(user, agency_name)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    session: TenantSession,
    current_user: AdminOnly,
) -> None:
    """
    Delete a user.

    Fails with 409 if the user has authored audit events (to preserve audit trail).
    """
    if user_id == current_user.id:
        raise _forbidden("Cannot delete your own account")

    user = session.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()

    if user is None:
        raise _not_found("User not found")

    # Check for audit events referencing this user
    audit_ref = session.execute(
        select(AuditEvent.id).where(AuditEvent.user_id == user_id).limit(1)
    ).first()

    if audit_ref:
        raise _conflict(
            "Cannot delete user: they have authored audit events. "
            "Audit trail must be preserved."
        )

    session.delete(user)
    session.commit()


# ---------------------------------------------------------------------------
# Routing Configuration
# ---------------------------------------------------------------------------


@router.get("/routing", response_model=List[RoutingRuleResponse])
def list_routing_rules(
    session: TenantSession,
    current_user: AdminOnly,
) -> List[RoutingRuleResponse]:
    """
    List all routing rules for the admin's tenant.

    Returns one row per (event_type, agency) pair with agency name.
    """
    rules = session.execute(
        select(EventTypeAgencyRule, Agency.name)
        .join(Agency, Agency.id == EventTypeAgencyRule.agency_id)
        .where(EventTypeAgencyRule.tenant_id == current_user.tenant_id)
        .order_by(EventTypeAgencyRule.event_type, Agency.name)
    ).all()

    return [
        RoutingRuleResponse(
            event_type=rule.event_type.value,
            agency_id=rule.agency_id,
            agency_name=agency_name,
        )
        for rule, agency_name in rules
    ]


@router.post(
    "/routing",
    response_model=RoutingRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_routing_rule(
    payload: RoutingRuleCreate,
    session: TenantSession,
    current_user: AdminOnly,
) -> RoutingRuleResponse:
    """
    Create a routing rule for the admin's tenant.

    Validates that:
    - event_type is a valid EventType enum value
    - agency belongs to this tenant
    - no duplicate rule exists for the same (event_type, agency) pair
    """
    # Validate event_type
    try:
        event_type = EventType(payload.event_type)
    except ValueError:
        raise _unprocessable(
            f"Invalid event_type '{payload.event_type}'. "
            f"Expected one of: {', '.join(e.value for e in EventType)}"
        )

    # Verify agency belongs to this tenant
    agency = session.execute(
        select(Agency).where(
            Agency.id == payload.agency_id,
            Agency.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()

    if agency is None:
        raise _not_found("Agency not found or does not belong to this city")

    # Check for duplicate
    existing = session.execute(
        select(EventTypeAgencyRule).where(
            EventTypeAgencyRule.tenant_id == current_user.tenant_id,
            EventTypeAgencyRule.event_type == event_type,
            EventTypeAgencyRule.agency_id == payload.agency_id,
        )
    ).scalar_one_or_none()

    if existing:
        raise _conflict(
            f"Routing rule for {event_type.value} with agency {agency.name} already exists"
        )

    rule = EventTypeAgencyRule(
        tenant_id=current_user.tenant_id,
        event_type=event_type,
        agency_id=payload.agency_id,
    )
    session.add(rule)
    session.commit()

    return RoutingRuleResponse(
        event_type=event_type.value,
        agency_id=agency.id,
        agency_name=agency.name,
    )


@router.delete("/routing/{event_type}/{agency_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_routing_rule(
    event_type: str,
    agency_id: uuid.UUID,
    session: TenantSession,
    current_user: AdminOnly,
) -> None:
    """
    Delete a routing rule.

    Does not affect existing review tasks. New submissions will follow the
    updated routing matrix.
    """
    try:
        event_type_enum = EventType(event_type)
    except ValueError:
        raise _unprocessable(
            f"Invalid event_type '{event_type}'. "
            f"Expected one of: {', '.join(e.value for e in EventType)}"
        )

    rule = session.execute(
        select(EventTypeAgencyRule).where(
            EventTypeAgencyRule.tenant_id == current_user.tenant_id,
            EventTypeAgencyRule.event_type == event_type_enum,
            EventTypeAgencyRule.agency_id == agency_id,
        )
    ).scalar_one_or_none()

    if rule is None:
        raise _not_found("Routing rule not found")

    session.delete(rule)
    session.commit()


# ---------------------------------------------------------------------------
# Additional routing helpers
# ---------------------------------------------------------------------------


@router.get("/routing/matrix", response_model=dict)
def get_routing_matrix(
    session: TenantSession,
    current_user: AdminOnly,
) -> dict:
    """
    Get the full routing matrix as a map of event_type -> list of agency names.

    Useful for UI display and validation.
    """
    rules = session.execute(
        select(EventTypeAgencyRule, Agency.name)
        .join(Agency, Agency.id == EventTypeAgencyRule.agency_id)
        .where(EventTypeAgencyRule.tenant_id == current_user.tenant_id)
        .order_by(EventTypeAgencyRule.event_type, Agency.name)
    ).all()

    matrix: dict[str, List[str]] = {}
    for rule, agency_name in rules:
        matrix.setdefault(rule.event_type.value, []).append(agency_name)

    # Ensure all event types appear in the matrix
    for event_type in EventType:
        matrix.setdefault(event_type.value, [])

    return matrix


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


def _application_response(application: Application) -> ApplicationResponse:
    """
    Build the admin's application response, including per-agency review progress.

    Same contract as the organizer path in `app.api.applications`: the schema
    cannot read `review_tasks` (it does not know about the model layer), so the
    summaries are attached explicitly. `selectinload` on the endpoints below
    keeps this to a fixed number of queries regardless of how many agencies are
    reviewing.
    """
    return ApplicationResponse.model_validate(
        application, from_attributes=True
    ).model_copy(
        update={"reviews": review_summaries(application.review_tasks)}
    )


def _with_review_summaries(query):
    """Eager-load review tasks and their agencies for the summary builder."""
    return query.options(
        selectinload(Application.review_tasks).selectinload(ReviewTask.agency)
    )


@router.get("/applications", response_model=list[ApplicationResponse])
def list_applications(
    session: TenantSession,
    current_user: AdminOnly,
    offset: int = 0,
    limit: int = 100,
    status: str = None,
    event_type: str = None,
) -> list[ApplicationResponse]:
    """
    List all applications in the admin's tenant, with optional filtering.

    Each entry carries its per-agency review summaries: agency name, decision
    status, comment and timestamps. RLS plus the explicit tenant predicate keep
    other cities' rows out of the result.
    """
    from app.models import Application, ApplicationStatus, EventType
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from fastapi import Query
    from typing import Optional, List
    import uuid

    query = select(Application).where(Application.tenant_id == current_user.tenant_id)

    if status is not None:
        query = query.where(Application.status == status)
    if event_type is not None:
        query = query.where(Application.event_type == event_type)

    # Order by most recently updated first
    query = query.order_by(Application.updated_at.desc()).offset(offset).limit(limit)
    query = _with_review_summaries(query)

    applications = session.execute(query).scalars().all()
    return [_application_response(app) for app in applications]


@router.get("/applications/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: str,
    session: TenantSession,
    current_user: AdminOnly,
) -> ApplicationResponse:
    """
    Fetch a single application by ID (admin view), with its review summaries.

    Cross-tenant ids return 404, matching the rest of this router: distinguishing
    "wrong city" from "no such row" would confirm that an id exists.
    """
    from app.models import Application
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from fastapi import Query, Depends
    from typing import Optional, List
    import uuid

    query = select(Application).where(
        Application.id == application_id,
        Application.tenant_id == current_user.tenant_id,
    )
    application = session.execute(_with_review_summaries(query)).scalar_one_or_none()

    if application is None:
        raise _not_found("Application not found")

    return _application_response(application)


@router.get(
    "/applications/{application_id}/history",
    response_model=AdminApplicationHistoryResponse,
)
def get_application_history(
    application_id: str,
    session: TenantSession,
    current_user: AdminOnly,
) -> AdminApplicationHistoryResponse:
    """
    The full audit timeline for an application in the admin's tenant.

    Same rows, ordering (oldest first) and event data as the organizer and
    reviewer history endpoints, plus two display-only additions per entry:
    the actor's email and the acting agency's name, resolved with a pair of
    outer joins so the whole timeline costs one query regardless of length.

    Isolation: the application fetch carries the tenant predicate (and RLS
    backs it), so another city's id — or no id at all — is a 404, never a 403
    and never a partial leak. An event whose actor or agency is absent
    (system-generated, or a row the session cannot see) yields None for that
    field rather than failing the request.
    """
    application = session.execute(
        select(Application).where(
            Application.id == application_id,
            Application.tenant_id == current_user.tenant_id,
        )
    ).scalar_one_or_none()

    if application is None:
        raise _not_found("Application not found")

    rows = session.execute(
        select(AuditEvent, User.email, Agency.name)
        .outerjoin(User, AuditEvent.user_id == User.id)
        .outerjoin(Agency, AuditEvent.agency_id == Agency.id)
        .where(AuditEvent.application_id == application.id)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
    ).all()

    events = [
        AdminAuditEventResponse.model_validate(event, from_attributes=True).model_copy(
            update={"actor_email": email, "agency_name": agency_name}
        )
        for event, email, agency_name in rows
    ]

    return AdminApplicationHistoryResponse(
        application_id=application.id,
        application_status=ApplicationStatus(application.status),
        events=events,
    )

