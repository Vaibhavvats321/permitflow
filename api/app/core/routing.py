"""
app/core/routing.py

Decides which agencies must review an application.

Two rules, in this order:

  1. The tenant's routing matrix (`event_type_agency_rules`), which a City Admin
     configures: this event type always needs these agencies.
  2. The attendance override: an event expected to draw more than 5,000 people
     always needs Fire as well.

Rule 2 is an override rather than a seed convenience. The seeded routing matrix
deliberately leaves Fire out of the base set, so if rule 2 were dropped the
threshold would silently stop firing and nothing would look wrong in the demo.

The threshold is `> 5000`, not `>= 5000`: the brief says "attendance over 5,000
always adds Fire", so exactly 5,000 does not trigger it.

This module is pure logic over a session. It performs no writes and raises no
HTTP errors, so it can be reused by the eventual resubmission path without
dragging route concerns along.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agency, Application, EventTypeAgencyRule

# "Rule: attendance over 5,000 always adds Fire." Strictly greater than.
LARGE_EVENT_ATTENDANCE_THRESHOLD = 5000

# Matched by name within the tenant. Agencies are tenant-scoped, so this can
# only ever resolve to the requesting city's own Fire department.
LARGE_EVENT_REQUIRED_AGENCY = "Fire"


class RoutingError(RuntimeError):
    """The event type has no routing rules configured for this tenant."""


def _agencies_for_event_type(
    session: Session, tenant_id, event_type
) -> list[Agency]:
    """
    Agencies the routing matrix requires for this event type.

    Joins through the rule table rather than filtering agencies by name, so a
    City Admin can add or remove any agency per event type and the result
    follows.
    """
    return list(
        session.execute(
            select(Agency)
            .join(
                EventTypeAgencyRule,
                EventTypeAgencyRule.agency_id == Agency.id,
            )
            .where(
                EventTypeAgencyRule.tenant_id == tenant_id,
                EventTypeAgencyRule.event_type == event_type,
            )
            .order_by(Agency.name)
        )
        .scalars()
        .unique()
    )


def _large_event_agencies(session: Session, tenant_id) -> list[Agency]:
    return list(
        session.execute(
            select(Agency)
            .where(
                Agency.tenant_id == tenant_id,
                Agency.name == LARGE_EVENT_REQUIRED_AGENCY,
            )
            .order_by(Agency.name)
        )
        .scalars()
    )


def is_large_event(application: Application) -> bool:
    """Whether the attendance override applies. A missing count is not large."""
    attendance = application.expected_attendance
    return attendance is not None and attendance > LARGE_EVENT_ATTENDANCE_THRESHOLD


def required_agencies(session: Session, application: Application) -> list[Agency]:
    """
    Agencies that must review this application, in a stable order.

    A set union, so an event type that already lists Fire explicitly does not
    get two Fire tasks: the attendance override is additive, not duplicative.
    Ordered by name for a predictable response and deterministic tests.
    """
    agencies = {
        agency.id: agency
        for agency in _agencies_for_event_type(
            session, application.tenant_id, application.event_type
        )
    }

    if is_large_event(application):
        agencies.update(
            (agency.id, agency) for agency in _large_event_agencies(session, application.tenant_id)
        )

    return sorted(agencies.values(), key=lambda agency: agency.name)