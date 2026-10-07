"""
app/core/routing.py

Decides which agencies must review an application.

Two rules, in this order:

  1. The tenant's routing matrix (`event_type_agency_rules`), which a City Admin
     configures: this event type always needs these agencies.
  2. The attendance thresholds: any agency whose `attendance_threshold` the
     expected attendance exceeds is required as well. Each agency carries its
     own value (Fire 5,000, Police 6,000, ...), stored in the database and
     editable from the agency management screen, so changing a threshold takes
     effect on the next submission without a code change.

Rule 2 is additive: the union is keyed by agency id, so an agency that both
appears in the matrix and exceeds its threshold still gets exactly one review
task.

The comparison is strictly greater than, never >=: attendance equal to an
agency's threshold does not make the event large enough for that agency.

This module is pure logic over a session. It performs no writes and raises no
HTTP errors, so it can be reused by the resubmission path without dragging
route concerns along.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agency, Application, EventTypeAgencyRule


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


def _threshold_agencies(
    session: Session, tenant_id, attendance: int | None
) -> list[Agency]:
    """
    Agencies whose attendance threshold the given attendance exceeds.

    A missing attendance never matches: an application without a count cannot
    make any threshold fire, and NULL thresholds mean "matrix only".
    """
    if attendance is None:
        return []
    return list(
        session.execute(
            select(Agency)
            .where(
                Agency.tenant_id == tenant_id,
                Agency.attendance_threshold.is_not(None),
                Agency.attendance_threshold < attendance,
            )
            .order_by(Agency.name)
        )
        .scalars()
    )


def agencies_required_by_attendance(
    session: Session, application: Application
) -> list[Agency]:
    """
    Agencies required because the expected attendance exceeds their threshold.

    Read from the database on every call, so an admin lowering (or raising) a
    threshold immediately changes which agencies the next submission routes to.
    """
    return _threshold_agencies(
        session, application.tenant_id, application.expected_attendance
    )


def required_agencies(session: Session, application: Application) -> list[Agency]:
    """
    Agencies that must review this application, in a stable order.

    A set union keyed by agency id, so an agency required by both the matrix
    and its attendance threshold does not get two tasks: the threshold rule is
    additive, not duplicative. Ordered by name for a predictable response and
    deterministic tests.
    """
    agencies = {
        agency.id: agency
        for agency in _agencies_for_event_type(
            session, application.tenant_id, application.event_type
        )
    }

    agencies.update(
        (agency.id, agency)
        for agency in agencies_required_by_attendance(session, application)
    )

    return sorted(agencies.values(), key=lambda agency: agency.name)
