"""
api/seed.py

Create the demo dataset: two tenants (Springfield and Riverton), their
agencies, the event-type routing matrix, and one user per role per tenant.

Idempotent. Re-running converges on the same rows and the same UUIDs, so it is
safe to run repeatedly and safe to run against a partially seeded database.

Runs on DATABASE_URL_ADMIN, not the application connection. This is not a
shortcut: `permitflow_app` has Row Level Security forced on every table, so it
cannot insert a second tenant or write rows outside its own tenant by design.
Seeding is an administrative action and belongs on the privileged connection.

Usage:
    python api/seed.py
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Agency,
    EventType,
    EventTypeAgencyRule,
    Tenant,
    User,
    UserRole,
)


@dataclass(frozen=True)
class DemoUser:
    email: str
    role: UserRole
    agency: str | None = None  # agency name; None means no agency


# Fire is always required above 5,000 expected attendees, so the base matrix
# omits it and the routing service adds it dynamically.
BASE_REQUIRED = ("Police", "Health")

ALL_AGENCIES = ("Police", "Fire", "Health")

ALL_EVENT_TYPES = (
    EventType.MARATHON,
    EventType.CONCERT,
    EventType.STREET_FAIR,
    EventType.OTHER,
)

DEMO_TENANTS: dict[str, list[DemoUser]] = {
    "Springfield": [
        DemoUser("springfield-organizer@example.com", UserRole.ORGANIZER),
        DemoUser("springfield-reviewer@example.com", UserRole.AGENCY_REVIEWER, "Police"),
        DemoUser("springfield-admin@example.com", UserRole.CITY_ADMIN),
    ],
    "Riverton": [
        DemoUser("riverton-organizer@example.com", UserRole.ORGANIZER),
        DemoUser("riverton-reviewer@example.com", UserRole.AGENCY_REVIEWER, "Fire"),
        DemoUser("riverton-admin@example.com", UserRole.CITY_ADMIN),
    ],
}


def seed_tenant(db: Session, name: str, users: list[DemoUser]) -> Tenant:
    """Upsert one tenant with its agencies, routing rules and users."""
    tenant = db.execute(
        sa.select(Tenant).where(Tenant.name == name)
    ).scalar_one_or_none()

    created = tenant is None
    if created:
        tenant = Tenant(name=name)
        db.add(tenant)
        db.flush()
        print(f"  + tenant {name}")
    else:
        print(f"  = tenant {name} (already present)")

    # Agencies. There is no unique constraint on (tenant_id, name), so match
    # explicitly rather than relying on a constraint violation.
    agencies: dict[str, Agency] = {}
    for agency_name in ALL_AGENCIES:
        agency = db.execute(
            sa.select(Agency).where(
                Agency.tenant_id == tenant.id, Agency.name == agency_name
            )
        ).scalar_one_or_none()
        if agency is None:
            agency = Agency(name=agency_name, tenant_id=tenant.id)
            db.add(agency)
            db.flush()
            print(f"    + agency {agency_name}")
        agencies[agency_name] = agency

    # Routing rules: replace the set per (tenant, event_type) so a changed
    # matrix converges instead of accumulating stale rows.
    for event_type in ALL_EVENT_TYPES:
        existing = {
            rule.agency_id
            for rule in db.execute(
                sa.select(EventTypeAgencyRule).where(
                    EventTypeAgencyRule.tenant_id == tenant.id,
                    EventTypeAgencyRule.event_type == event_type,
                )
            ).scalars()
        }
        wanted = {agencies[a].id for a in BASE_REQUIRED}

        for agency_id in wanted - existing:
            db.add(
                EventTypeAgencyRule(
                    tenant_id=tenant.id,
                    event_type=event_type,
                    agency_id=agency_id,
                )
            )
        for agency_id in existing - wanted:
            db.execute(
                sa.delete(EventTypeAgencyRule).where(
                    EventTypeAgencyRule.tenant_id == tenant.id,
                    EventTypeAgencyRule.event_type == event_type,
                    EventTypeAgencyRule.agency_id == agency_id,
                )
            )

    # Users. Re-hash only when the row is new so repeat runs do not churn
    # existing hashes or invalidate a session mid-demonstration.
    for demo_user in users:
        user = db.execute(
            sa.select(User).where(User.email == demo_user.email)
        ).scalar_one_or_none()
        if user is not None:
            print(f"    = user {demo_user.email} (already present)")
            continue

        db.add(
            User(
                email=demo_user.email,
                password_hash=hash_password(settings.DEMO_USER_PASSWORD),
                role=demo_user.role,
                tenant_id=tenant.id,
                agency_id=agencies[demo_user.agency].id if demo_user.agency else None,
            )
        )
        print(f"    + user {demo_user.email}")

    db.flush()
    return tenant


def seed() -> None:
    # Deliberately NOT app.db.session.SessionLocal: that is bound to the
    # application role, which RLS prevents from creating tenants at all.
    admin_engine = sa.create_engine(settings.DATABASE_URL_ADMIN, future=True)
    factory = sa.orm.sessionmaker(bind=admin_engine, autoflush=False)
    db = factory()
    try:
        print("seeding demo data")
        for name, users in DEMO_TENANTS.items():
            seed_tenant(db, name, users)
        db.commit()
        print("\ncommitted")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        admin_engine.dispose()


def print_summary() -> None:
    """Report what a given connection can actually see.

    With the application connection this demonstrates RLS: the same query
    returns rows only for tenants the session is scoped to.
    """
    from app.db.session import engine

    print("\nrow counts as the application role (RLS applies):")
    with engine.connect() as conn:
        print(f"  current_user = {conn.execute(sa.text('select current_user')).scalar()}")
        for table in ("tenants", "users", "agencies", "event_type_agency_rules"):
            print(f"  {table}: {conn.execute(sa.text(f'select count(*) from {table}')).scalar()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print row counts visible to the application role afterwards",
    )
    args = parser.parse_args()

    seed()
    print(f"\ndemo password for all seeded accounts: {settings.DEMO_USER_PASSWORD}")
    for name, users in DEMO_TENANTS.items():
        print(f"\n{name}:")
        for demo_user in users:
            agency = f" ({demo_user.agency})" if demo_user.agency else ""
            print(f"  {demo_user.email:38} {demo_user.role.value}{agency}")

    if args.summary:
        print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
