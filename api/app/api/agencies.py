"""
app/api/agencies.py

Read-only agency list shared by every signed-in role.

Organizers and reviewers need the same attendance thresholds that submit
routing uses — to explain which agencies a given attendance will pull in —
but the admin agency endpoints require the City Admin role. This router
exposes the tenant-scoped list (RLS guarantees it is only the caller's own
city) to any authenticated user, read-only: creating and editing agencies
stays an admin concern.
"""

from __future__ import annotations

from typing import Annotated, List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, get_current_user, get_tenant_db
from app.models import Agency
from app.schemas.admin import AgencyResponse

router = APIRouter(prefix="/agencies", tags=["agencies"])

TenantSession = Annotated[Session, Depends(get_tenant_db)]
AnyUser = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("", response_model=List[AgencyResponse])
def list_agencies(
    session: TenantSession,
    current_user: AnyUser,
) -> List[AgencyResponse]:
    """
    Every agency in the caller's city, ordered by name.

    Includes `attendance_threshold` so the application flow can show which
    agencies a given expected attendance requires without hardcoding any
    agency name or limit.
    """
    agencies = session.execute(
        select(Agency).order_by(Agency.name)
    ).scalars().all()
    return [AgencyResponse.model_validate(a, from_attributes=True) for a in agencies]
