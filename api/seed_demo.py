"""
api/seed_demo.py

Portable, create-only demo seeder for PermitFlow.

Produces the full demo dataset described in DEMO_SETUP.md:

  * 6 tenants  — City A..D populated (1 admin, 2 organizers, 3 reviewers each),
                 City E/F admin-only (1 admin, no agencies, no applications)
  * 26 users   — 6 City Admins, 8 Organizers, 12 Agency Reviewers,
                 all hashed with the project's own hash_password()
  * 12 agencies (Police/Health/Fire in the four populated tenants)
  * 32 routing rules (Police + Health for each of the four event types; Fire
                 is deliberately left out of the base matrix because
                 app/core/routing.py adds it automatically above 5,000
                 attendance — seeding it would mask that override)
  * 40 applications (10 per populated tenant) with review tasks and audit
                 history across Submitted / Under Review / Approved /
                 Rejected / Changes Requested scenarios
  * 0 application data in the admin-only tenants

Design rules, matching the phase requirements:

  CREATE-ONLY. This script never deletes, truncates, drops or alters
  anything — no tables, no schema, no constraints, no RLS policies, no
  migrations. Database *cleanup* is a separate one-time step that must never
  be embedded here.

  PORTABLE. Connection strings and the demo password come from the project's
  existing Settings (repo-root .env), exactly like api/seed.py. No
  machine-specific paths or credentials are hardcoded.

  IDEMPOTENT. Every row gets a deterministic uuid5 identifier derived from a
  fixed namespace plus a stable business key (tenant name, email,
  event slug, ...). A repeat run finds the existing rows and skips them, so
  nothing is duplicated and nothing previously seeded is rewritten.

  SINGLE TRANSACTION. Everything is flushed inside one session and committed
  once; any failure rolls the whole run back, so a partial dataset can never
  be left behind.

  REAL BUSINESS LOGIC. Review tasks come from the actual
  app.core.routing.required_agencies() (matrix + attendance override), status
  transitions go through app.core.lifecycle's guards and aggregation, audit
  actions reuse the constants defined by the API routes, and passwords are
  hashed by app.core.security.hash_password. Nothing is fabricated.

Runs on DATABASE_URL_ADMIN (the privileged connection) for the same reason
api/seed.py does: Row Level Security is forced on every table, so the
restricted application role cannot create tenants or write cross-tenant
rows by design. Seeding is an administrative action.

Usage (from the repository root):

    python api/seed_demo.py

Windows PowerShell (this project keeps its venv at the repo root):

    & ".\\.venv\\Scripts\\python.exe" ".\\api\\seed_demo.py"
"""

from __future__ import annotations

import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

import sqlalchemy as sa
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Audit action strings come from the route modules themselves so the seeder
# can never drift from what the API actually writes.
from app.api.applications import (  # noqa: E402
    _AUDIT_APPLICATION_STATUS_CHANGE as AUDIT_STATUS_CHANGED,
)
from app.api.reviews import (  # noqa: E402
    _AUDIT_DECISION_NAME as DECISION_AUDIT_NAME,
    _AUDIT_DECISION_PREFIX as DECISION_AUDIT_PREFIX,
)
from app.core.config import settings  # noqa: E402
from app.core.lifecycle import (  # noqa: E402
    aggregate_application_status,
    assert_application_reviewable,
    assert_review_transition_allowed,
)
from app.core.routing import required_agencies  # noqa: E402
from app.core.security import hash_password, verify_password  # noqa: E402
from app.models import (  # noqa: E402
    Agency,
    Application,
    ApplicationStatus,
    AuditEvent,
    EventType,
    EventTypeAgencyRule,
    ReviewStatus,
    ReviewTask,
    Tenant,
    User,
    UserRole,
)
from app.schemas.application import missing_submission_fields  # noqa: E402

# ---------------------------------------------------------------------------
# Stable identity
# ---------------------------------------------------------------------------

# Fixed namespace: every uuid5 below is a pure function of stable business
# keys, so re-running the seeder recomputes the same ids and recognises its
# own rows instead of inserting duplicates.
SEED_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://permitflow.demo/seed_demo")

DEMO_EMAIL_DOMAIN = "permitflow.demo"


def seed_id(kind: str, *parts: str) -> uuid.UUID:
    """Deterministic id for one seeded row, keyed by kind + business key."""
    return uuid.uuid5(SEED_NAMESPACE, "/".join((kind, *parts)))


# ---------------------------------------------------------------------------
# Tenant structure (exact counts mandated by the demo spec)
# ---------------------------------------------------------------------------

POPULATED_CITIES = ("City A", "City B", "City C", "City D")
ADMIN_ONLY_CITIES = ("City E", "City F")

# Agencies created in each populated tenant.
AGENCY_NAMES = ("Police", "Health", "Fire")

# Base matrix: Police + Health on every event type. Fire is intentionally
# absent — app/core/routing.py adds Fire automatically when expected
# attendance is strictly greater than 5,000, and a matrix that already
# contained Fire would make that override invisible in the demo.
BASE_ROUTING_AGENCIES = ("Police", "Health")

DEMO_PASSWORD = settings.DEMO_USER_PASSWORD  # documented as Demo1234!


def city_slug(city: str) -> str:
    """'City A' -> 'citya' (email slug, deterministic)."""
    return city.lower().replace(" ", "")


def tenant_users(city: str) -> tuple[tuple[str, UserRole, str | None], ...]:
    """(email, role, agency_name) for one populated tenant — exactly 6 users."""
    slug = city_slug(city)
    return (
        (f"admin.{slug}@{DEMO_EMAIL_DOMAIN}", UserRole.CITY_ADMIN, None),
        (f"organizer1.{slug}@{DEMO_EMAIL_DOMAIN}", UserRole.ORGANIZER, None),
        (f"organizer2.{slug}@{DEMO_EMAIL_DOMAIN}", UserRole.ORGANIZER, None),
        (f"police.{slug}@{DEMO_EMAIL_DOMAIN}", UserRole.AGENCY_REVIEWER, "Police"),
        (f"health.{slug}@{DEMO_EMAIL_DOMAIN}", UserRole.AGENCY_REVIEWER, "Health"),
        (f"fire.{slug}@{DEMO_EMAIL_DOMAIN}", UserRole.AGENCY_REVIEWER, "Fire"),
    )


# ---------------------------------------------------------------------------
# Application template: 10 events per populated tenant
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    """One reviewer decision, in chronological order within the application."""

    agency: str
    status: ReviewStatus
    comment: str


@dataclass(frozen=True)
class EventSpec:
    slug: str  # stable identity inside the tenant
    title: str
    event_type: EventType
    attendance: int
    location: str
    description: str
    organizer: int  # 1 or 2 — distributes the 10 events 5/5 across organizers
    decisions: tuple[Decision, ...] = field(default_factory=tuple)

    @property
    def is_large(self) -> bool:
        return self.attendance > 5000


# The template covers every lifecycle state the demo must show:
# Approved (1, 2, 9), Rejected (3, 10), Changes Requested (4),
# Submitted/pending (5, 7), Under Review (6, 8). Three events exceed 5,000
# attendance (1, 5, 8) so the automatic Fire routing is exercised, and the
# decision order keeps every step inside the reviewable states enforced by
# app.core.lifecycle (the decisive rejection is always applied last).
EVENT_TEMPLATE: tuple[EventSpec, ...] = (
    EventSpec(
        slug="riverfront-marathon",
        title="Riverfront Marathon",
        event_type=EventType.MARATHON,
        attendance=12000,
        location="Riverside Drive",
        description="Annual city marathon along the river with road closures.",
        organizer=1,
        decisions=(
            Decision("Police", ReviewStatus.APPROVED,
                     "Road-closure and traffic-control plan verified. Approved."),
            Decision("Health", ReviewStatus.APPROVED,
                     "First-aid stations and water points meet the health code. Approved."),
            Decision("Fire", ReviewStatus.APPROVED,
                     "Large-event attendance override: egress and hydrant access reviewed. Approved."),
        ),
    ),
    EventSpec(
        slug="summer-concert-series",
        title="Summer Concert Series",
        event_type=EventType.CONCERT,
        attendance=800,
        location="Central Park Bandshell",
        description="Three-evening outdoor concert series in the park.",
        organizer=1,
        decisions=(
            Decision("Police", ReviewStatus.APPROVED,
                     "Crowd management and parking plan approved."),
            Decision("Health", ReviewStatus.APPROVED,
                     "Sanitation facilities confirmed for the expected attendance. Approved."),
        ),
    ),
    EventSpec(
        slug="downtown-street-fair",
        title="Downtown Street Fair",
        event_type=EventType.STREET_FAIR,
        attendance=4500,
        location="Main Street",
        description="Vendor market and stage on the closed-off main street.",
        organizer=1,
        decisions=(
            # Approvals are applied before the decisive rejection so every
            # step satisfies assert_application_reviewable.
            Decision("Health", ReviewStatus.APPROVED,
                     "Food-handler permits and hand-wash stations checked. Approved."),
            Decision("Police", ReviewStatus.REJECTED,
                     "No viable traffic-control plan for the requested closure. Rejected."),
        ),
    ),
    EventSpec(
        slug="jazz-nights",
        title="Jazz Nights",
        event_type=EventType.CONCERT,
        attendance=2500,
        location="Old Town Amphitheater",
        description="Ticketed evening jazz programme at the amphitheater.",
        organizer=1,
        decisions=(
            Decision("Police", ReviewStatus.APPROVED,
                     "Egress routes and parking marshalling approved."),
            Decision("Health", ReviewStatus.CHANGES_REQUESTED,
                     "Please add the sanitation plan and revise the load-in window."),
        ),
    ),
    EventSpec(
        slug="charity-fun-run",
        title="Charity Fun Run",
        event_type=EventType.MARATHON,
        attendance=6000,
        location="Lakeside Trail",
        description="Charity run around the lake, awaiting its first decision.",
        organizer=1,
        decisions=(),  # stays Submitted: all tasks (incl. Fire) pending
    ),
    EventSpec(
        slug="neighborhood-block-party",
        title="Neighborhood Block Party",
        event_type=EventType.OTHER,
        attendance=300,
        location="Elm Street",
        description="Community block party with one agency decision recorded.",
        organizer=2,
        decisions=(
            Decision("Police", ReviewStatus.APPROVED,
                     "Street barricades and staffing approved."),
        ),
    ),
    EventSpec(
        slug="artisan-market",
        title="Artisan Market",
        event_type=EventType.STREET_FAIR,
        attendance=1200,
        location="Convention Center Plaza",
        description="Weekend craft market on the convention center plaza.",
        organizer=2,
        decisions=(),  # stays Submitted: both tasks pending
    ),
    EventSpec(
        slug="harbor-music-festival",
        title="Harbor Music Festival",
        event_type=EventType.CONCERT,
        attendance=5200,
        location="Harbor Pavilion",
        description="Waterfront music festival above the Fire attendance threshold.",
        organizer=2,
        decisions=(
            Decision("Fire", ReviewStatus.APPROVED,
                     "Large-event attendance override: temporary structures and exits reviewed. Approved."),
        ),
    ),
    EventSpec(
        slug="community-picnic",
        title="Community Picnic",
        event_type=EventType.OTHER,
        attendance=150,
        location="Greenwood Park",
        description="City departments' family picnic in Greenwood Park.",
        organizer=2,
        decisions=(
            Decision("Police", ReviewStatus.APPROVED,
                     "No road closures needed; patrol presence noted. Approved."),
            Decision("Health", ReviewStatus.APPROVED,
                     "Food safety and shade provisions confirmed. Approved."),
        ),
    ),
    EventSpec(
        slug="food-truck-rally",
        title="Food Truck Rally",
        event_type=EventType.STREET_FAIR,
        attendance=4200,
        location="Union Square",
        description="Food-truck gathering in Union Square.",
        organizer=2,
        decisions=(
            Decision("Police", ReviewStatus.APPROVED,
                     "Vehicle staging and crowd barriers approved."),
            Decision("Health", ReviewStatus.REJECTED,
                     "Grease-disposal and cold-chain plan does not meet the health code. Rejected."),
        ),
    ),
)

# ---------------------------------------------------------------------------
# Timeline. All demo history sits in the past; event dates in the future.
# ---------------------------------------------------------------------------

NOW = datetime.now(UTC).replace(microsecond=0)
TENANT_AT = NOW - timedelta(days=60)
AGENCY_AT = NOW - timedelta(days=59)
USER_AT = NOW - timedelta(days=58)
RULE_AT = NOW - timedelta(days=58)


def application_created_at(index: int) -> datetime:
    """45 days ago down to 9 days ago, four days apart."""
    return NOW - timedelta(days=45 - 4 * index)


# ---------------------------------------------------------------------------
# Idempotent create helpers
# ---------------------------------------------------------------------------


class Ledger:
    """Counts of rows this run created vs. found already present."""

    def __init__(self) -> None:
        self.created: Counter[str] = Counter()
        self.existing: Counter[str] = Counter()

    def note(self, kind: str, created: bool) -> None:
        (self.created if created else self.existing)[kind] += 1


def _get_or_create(
    db: Session,
    model: type,
    obj_id: uuid.UUID,
    kind: str,
    ledger: Ledger,
    fallback: Callable[[Session], object | None] | None = None,
    **values,
):
    """
    Return (row, created) for a deterministically-identified row.

    `fallback` handles the one case a uuid cannot: a natural key that the
    database already holds (tenant name, unique email, routing-rule
    uniqueness) under an id this seeder did not write. Existing rows are used
    as-is — create-only means never rewriting what is already there.
    """
    db.flush()
    obj = db.get(model, obj_id)
    if obj is None and fallback is not None:
        obj = fallback(db)
    if obj is not None:
        ledger.note(kind, created=False)
        return obj, False

    obj = model(id=obj_id, **values)
    db.add(obj)
    db.flush()
    ledger.note(kind, created=True)
    return obj, True


# ---------------------------------------------------------------------------
# Per-tenant seeding
# ---------------------------------------------------------------------------


def seed_populated_tenant(db: Session, city: str, ledger: Ledger, password_hash: str) -> None:
    slug = city_slug(city)

    tenant, _ = _get_or_create(
        db, Tenant, seed_id("tenant", city), "tenant", ledger,
        fallback=lambda s: s.execute(
            sa.select(Tenant).where(Tenant.name == city)
        ).scalar_one_or_none(),
        name=city,
        created_at=TENANT_AT,
    )

    agencies: dict[str, Agency] = {}
    for name in AGENCY_NAMES:
        agency, _ = _get_or_create(
            db, Agency, seed_id("agency", city, name), "agency", ledger,
            fallback=lambda s, t=tenant, n=name: s.execute(
                sa.select(Agency).where(Agency.tenant_id == t.id, Agency.name == n)
            ).scalar_one_or_none(),
            name=name,
            tenant_id=tenant.id,
            created_at=AGENCY_AT,
        )
        agencies[name] = agency  # type: ignore[assignment]

    # Routing rules: Police + Health for all four event types (see
    # BASE_ROUTING_AGENCIES for why Fire is not written here).
    for event_type in EventType:
        for agency_name in BASE_ROUTING_AGENCIES:
            _get_or_create(
                db,
                EventTypeAgencyRule,
                seed_id("rule", city, event_type.value, agency_name),
                "rule",
                ledger,
                fallback=lambda s, t=tenant, e=event_type, a=agencies[agency_name]: s.execute(
                    sa.select(EventTypeAgencyRule).where(
                        EventTypeAgencyRule.tenant_id == t.id,
                        EventTypeAgencyRule.event_type == e,
                        EventTypeAgencyRule.agency_id == a.id,
                    )
                ).scalar_one_or_none(),
                event_type=event_type,
                agency_id=agencies[agency_name].id,
                tenant_id=tenant.id,
            )

    # Users: exactly 6 — 1 admin, 2 organizers, 3 reviewers.
    users: dict[str, User] = {}
    for email, role, agency_name in tenant_users(city):
        user, _ = _get_or_create(
            db, User, seed_id("user", email), "user", ledger,
            fallback=lambda s, e=email: s.execute(
                sa.select(User).where(User.email == e)
            ).scalar_one_or_none(),
            email=email,
            password_hash=password_hash,
            role=role,
            tenant_id=tenant.id,
            agency_id=agencies[agency_name].id if agency_name else None,
            created_at=USER_AT,
        )
        users[email] = user  # type: ignore[assignment]

    organizers = [users[f"organizer{i}.{slug}@{DEMO_EMAIL_DOMAIN}"] for i in (1, 2)]
    reviewers = {
        name: users[f"{name.lower()}.{slug}@{DEMO_EMAIL_DOMAIN}"]
        for name in ("Police", "Health", "Fire")
    }

    # Applications: exactly 10, five per organizer.
    for index, spec in enumerate(EVENT_TEMPLATE):
        application_id = seed_id("application", city, spec.slug)
        if db.get(Application, application_id) is not None:
            ledger.note("application", created=False)
            continue

        organizer = organizers[spec.organizer - 1]
        created_at = application_created_at(index)
        start_date = (NOW + timedelta(days=21 + index * 7)).replace(microsecond=0)

        application = Application(
            id=application_id,
            event_name=f"{city} {spec.title}",
            event_type=spec.event_type,
            start_date=start_date,
            end_date=start_date + timedelta(days=1),
            location=spec.location,
            expected_attendance=spec.attendance,
            description=spec.description,
            status=ApplicationStatus.DRAFT,
            submitter_id=organizer.id,
            tenant_id=tenant.id,
            created_at=created_at,
            updated_at=created_at,
        )
        db.add(application)
        db.flush()
        ledger.note("application", created=True)

        tasks = _simulate_submit(db, application, organizer, ledger, city)
        _simulate_decisions(db, application, tasks, reviewers, spec, ledger, city)


def seed_admin_only_tenant(db: Session, city: str, ledger: Ledger, password_hash: str) -> None:
    """City E/F: one City Admin, no agencies, no routing, no applications."""
    slug = city_slug(city)

    tenant, _ = _get_or_create(
        db, Tenant, seed_id("tenant", city), "tenant", ledger,
        fallback=lambda s: s.execute(
            sa.select(Tenant).where(Tenant.name == city)
        ).scalar_one_or_none(),
        name=city,
        created_at=TENANT_AT,
    )

    email = f"admin.{slug}@{DEMO_EMAIL_DOMAIN}"
    _get_or_create(
        db, User, seed_id("user", email), "user", ledger,
        fallback=lambda s, e=email: s.execute(
            sa.select(User).where(User.email == e)
        ).scalar_one_or_none(),
        email=email,
        password_hash=password_hash,
        role=UserRole.CITY_ADMIN,
        tenant_id=tenant.id,
        agency_id=None,
        created_at=USER_AT,
    )


# ---------------------------------------------------------------------------
# Submission and decisions — mirrors the API routes' writes exactly
# ---------------------------------------------------------------------------


def _simulate_submit(
    db: Session,
    application: Application,
    organizer: User,
    ledger: Ledger,
    city: str,
) -> dict[str, ReviewTask]:
    """
    Apply the same writes as POST /applications/{id}/submit.

    Task set comes from the real routing logic (matrix plus the >5,000 Fire
    override), guarded by the same completeness and non-empty checks the
    route performs.
    """
    missing = missing_submission_fields(application)
    if missing:
        raise RuntimeError(
            f"{application.event_name}: cannot seed a submission missing {missing}"
        )

    agencies = required_agencies(db, application)
    if not agencies:
        raise RuntimeError(
            f"{application.event_name}: routing matrix produced no agencies"
        )
    foreign = [a.name for a in agencies if a.tenant_id != application.tenant_id]
    if foreign:
        raise RuntimeError(f"{application.event_name}: cross-tenant routing {foreign}")

    submit_at = application.created_at + timedelta(hours=2)

    tasks: dict[str, ReviewTask] = {}
    for agency in agencies:
        task = ReviewTask(
            id=seed_id("task", str(application.id), str(agency.id)),
            application_id=application.id,
            agency_id=agency.id,
            tenant_id=application.tenant_id,
            status=ReviewStatus.PENDING,
            created_at=submit_at,
            updated_at=submit_at,
        )
        db.add(task)
        tasks[agency.name] = task
        ledger.note("task", created=True)
    db.flush()

    application.status = ApplicationStatus.SUBMITTED
    application.updated_at = submit_at
    db.add(
        AuditEvent(
            id=seed_id("audit", str(application.id), "submit"),
            application_id=application.id,
            tenant_id=application.tenant_id,
            user_id=organizer.id,
            agency_id=None,
            action=AUDIT_STATUS_CHANGED,
            old_status=ApplicationStatus.DRAFT.value,
            new_status=ApplicationStatus.SUBMITTED.value,
            comment=f"Submitted for review by {len(agencies)} agency(ies)",
            created_at=submit_at,
        )
    )
    ledger.note("audit", created=True)
    db.flush()
    return tasks


def _simulate_decisions(
    db: Session,
    application: Application,
    tasks: dict[str, ReviewTask],
    reviewers: dict[str, User],
    spec: EventSpec,
    ledger: Ledger,
    city: str,
) -> None:
    """
    Apply the template's decisions the way POST /review-tasks/{id}/decision
    does: lifecycle guards first, then derived status, then one audit row per
    decision plus one for any aggregate status movement.
    """
    decision_at = application.created_at + timedelta(hours=2)

    for step, decision in enumerate(spec.decisions, start=1):
        if decision.agency not in tasks:
            raise RuntimeError(
                f"{city}/{spec.slug}: decision for {decision.agency} but routing "
                f"created tasks for {sorted(tasks)}"
            )

        decision_at += timedelta(days=1)
        task = tasks[decision.agency]
        reviewer = reviewers[decision.agency]
        target = decision.status

        old_task_status = ReviewStatus(task.status)
        try:
            assert_review_transition_allowed(old_task_status, target)
            assert_application_reviewable(ApplicationStatus(application.status))
        except Exception as exc:  # pragma: no cover - template bug, rolls back
            raise RuntimeError(
                f"{city}/{spec.slug}: illegal transition {old_task_status} -> {target} "
                f"on application status {application.status}"
            ) from exc

        task.status = target
        task.comment = decision.comment
        task.updated_at = decision_at
        db.flush()

        statuses = [
            ReviewStatus(row[0])
            for row in db.execute(
                sa.select(ReviewTask.status).where(
                    ReviewTask.application_id == application.id
                )
            )
        ]
        previous_status = ApplicationStatus(application.status)
        new_status = aggregate_application_status(statuses, current=previous_status)
        application.status = new_status
        application.updated_at = decision_at

        db.add(
            AuditEvent(
                id=seed_id("audit", str(application.id), f"decision-{step}"),
                application_id=application.id,
                tenant_id=application.tenant_id,
                user_id=reviewer.id,
                agency_id=task.agency_id,
                action=f"{DECISION_AUDIT_PREFIX}{DECISION_AUDIT_NAME[target]}",
                old_status=old_task_status.value,
                new_status=target.value,
                comment=decision.comment,
                created_at=decision_at,
            )
        )
        ledger.note("audit", created=True)

        if new_status is not previous_status:
            db.add(
                AuditEvent(
                    id=seed_id("audit", str(application.id), f"status-{step}"),
                    application_id=application.id,
                    tenant_id=application.tenant_id,
                    user_id=reviewer.id,
                    agency_id=task.agency_id,
                    action=AUDIT_STATUS_CHANGED,
                    old_status=previous_status.value,
                    new_status=new_status.value,
                    comment=decision.comment,
                    created_at=decision_at,
                )
            )
            ledger.note("audit", created=True)

    db.flush()


# ---------------------------------------------------------------------------
# Seeding run
# ---------------------------------------------------------------------------


def seed() -> Ledger:
    # Deliberately not app.db.session.SessionLocal: that connection belongs to
    # the restricted application role, which RLS prevents from creating
    # tenants at all. Seeding runs on the privileged connection, exactly like
    # api/seed.py and the test fixtures.
    admin_engine = sa.create_engine(settings.DATABASE_URL_ADMIN, future=True)
    factory = sa.orm.sessionmaker(bind=admin_engine, autoflush=False)
    db = factory()
    ledger = Ledger()
    try:
        print("seeding demo data (create-only, idempotent)")
        # Hash once: every account shares the one documented demo password.
        password_hash = hash_password(DEMO_PASSWORD)
        for city in POPULATED_CITIES:
            print(f"\n{city} (populated)")
            seed_populated_tenant(db, city, ledger, password_hash)
        for city in ADMIN_ONLY_CITIES:
            print(f"\n{city} (admin-only)")
            seed_admin_only_tenant(db, city, ledger, password_hash)
        db.commit()
        print("\ncommitted")
    except Exception:
        db.rollback()
        print("\nerror: rolled back — no partial data was written")
        raise
    finally:
        db.close()
        admin_engine.dispose()
    return ledger


# ---------------------------------------------------------------------------
# Verification and summary
# ---------------------------------------------------------------------------


def _scoped_ids(engine: sa.Engine) -> list[uuid.UUID]:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.select(Tenant.id).where(
                Tenant.name.in_([*POPULATED_CITIES, *ADMIN_ONLY_CITIES])
            )
        ).scalars()
        return list(rows)


def verify_and_summarize() -> bool:
    """
    Count only this seeder's tenants and verify every mandated invariant.

    Returns True only if all mandatory counts and password checks pass, so a
    broken run exits non-zero instead of claiming success.
    """
    engine = sa.create_engine(settings.DATABASE_URL_ADMIN, future=True)
    ok = True
    try:
        with engine.connect() as conn:
            tenant_ids = list(
                conn.execute(
                    sa.select(Tenant.id).where(
                        Tenant.name.in_([*POPULATED_CITIES, *ADMIN_ONLY_CITIES])
                    )
                ).scalars()
            )
            if len(tenant_ids) != 6:
                print(f"FAIL: expected 6 demo tenants, found {len(tenant_ids)}")
                return False

            def count(model, extra=None) -> int:
                stmt = sa.select(sa.func.count()).select_from(model).where(
                    model.tenant_id.in_(tenant_ids)
                )
                if extra is not None:
                    stmt = stmt.where(extra)
                return conn.execute(stmt).scalar()

            users = conn.execute(
                sa.select(User.email, User.role, User.password_hash, User.tenant_id)
                .join(Tenant, Tenant.id == User.tenant_id)
                .where(User.tenant_id.in_(tenant_ids))
                .order_by(Tenant.name, User.email)
            ).all()

            role_counts = Counter(UserRole.parse(row[1]).value for row in users)
            per_tenant_users = Counter(row[3] for row in users)

            app_rows = conn.execute(
                sa.select(Application.tenant_id, Application.status)
                .where(Application.tenant_id.in_(tenant_ids))
            ).all()
            apps_per_tenant = Counter(row[0] for row in app_rows)
            status_counts = Counter(ApplicationStatus(row[1]).value for row in app_rows)

            agencies = count(Agency)
            rules = count(EventTypeAgencyRule)
            tasks = count(ReviewTask)
            audits = count(AuditEvent)
            applications = len(app_rows)

            # Orphan checks: every child row must reference a parent that exists.
            orphans = conn.execute(
                sa.text(
                    """
                    select
                      (select count(*) from review_tasks rt
                         left join applications a on a.id = rt.application_id
                        where a.id is null)
                    + (select count(*) from review_tasks rt
                         left join agencies g on g.id = rt.agency_id
                        where g.id is null)
                    + (select count(*) from audit_events ae
                         left join applications a on a.id = ae.application_id
                        where a.id is null)
                    + (select count(*) from audit_events ae
                         left join users u on u.id = ae.user_id
                        where ae.user_id is not null and u.id is null)
                    + (select count(*) from users u
                         left join tenants t on t.id = u.tenant_id
                        where t.id is null)
                    """
                )
            ).scalar()

            # Passwords: every demo account must authenticate with the common
            # demo password, checked with the project's own verifier.
            password_ok = sum(
                1 for row in users if verify_password(DEMO_PASSWORD, row[2])
            )

            # RLS must still be enforced on all seven application tables.
            rls = conn.execute(
                sa.text(
                    "select count(*) from pg_class c "
                    "join pg_namespace n on n.oid = c.relnamespace "
                    "where n.nspname = 'public' and c.relkind = 'r' "
                    "and c.relname <> 'alembic_version' "
                    "and c.relrowsecurity and c.relforcerowsecurity"
                )
            ).scalar()
            policies = conn.execute(
                sa.text(
                    "select count(*) from pg_policies where schemaname = 'public'"
                )
            ).scalar()

        # ---- report -------------------------------------------------------
        print("\n" + "=" * 66)
        print("seed verification (scoped to the 6 demo tenants)")
        print("=" * 66)

        def check(label: str, actual, expected) -> None:
            nonlocal ok
            passed = actual == expected
            ok = ok and passed
            mark = "ok  " if passed else "FAIL"
            print(f"  [{mark}] {label}: {actual} (expected {expected})")

        check("tenants", len(tenant_ids), 6)
        check("users", len(users), 26)
        check("  City Admin", role_counts.get("City Admin", 0), 6)
        check("  Organizer", role_counts.get("Organizer", 0), 8)
        check("  Agency Reviewer", role_counts.get("Agency Reviewer", 0), 12)
        check("applications", applications, 40)

        for city in POPULATED_CITIES:
            tid = None
            with engine.connect() as conn:
                tid = conn.execute(
                    sa.select(Tenant.id).where(Tenant.name == city)
                ).scalar_one()
            check(f"{city}: users", per_tenant_users[tid], 6)
            check(f"{city}: applications", apps_per_tenant[tid], 10)
        for city in ADMIN_ONLY_CITIES:
            tid = None
            with engine.connect() as conn:
                tid = conn.execute(
                    sa.select(Tenant.id).where(Tenant.name == city)
                ).scalar_one()
            check(f"{city}: users", per_tenant_users[tid], 1)
            check(f"{city}: applications", apps_per_tenant[tid], 0)

        print("\n  totals:")
        print(f"    agencies={agencies}  routing_rules={rules}  "
              f"review_tasks={tasks}  audit_events={audits}")
        print(f"    application statuses: {dict(sorted(status_counts.items()))}")
        print(f"  [ {'ok  ' if password_ok == 26 else 'FAIL'} ] "
              f"password check: {password_ok}/26 accounts accept the demo password")
        print(f"  [ {'ok  ' if orphans == 0 else 'FAIL'} ] "
              f"orphaned child rows: {orphans}")
        print(f"  [ {'ok  ' if rls == 7 and policies == 7 else 'FAIL'} ] "
              f"RLS enabled+forced: {rls}/7 tables, policies: {policies}/7")
        ok = ok and password_ok == 26 and orphans == 0 and rls == 7 and policies == 7

        # ---- credentials ---------------------------------------------------
        print("\ndemo accounts (password for ALL: "
              f"{DEMO_PASSWORD}):")
        with engine.connect() as conn:
            rows = conn.execute(
                sa.select(Tenant.name, User.email, User.role)
                .join(User, User.tenant_id == Tenant.id)
                .where(Tenant.name.in_([*POPULATED_CITIES, *ADMIN_ONLY_CITIES]))
                .order_by(
                    sa.case(
                        {c: i for i, c in enumerate([*POPULATED_CITIES, *ADMIN_ONLY_CITIES])},
                        value=Tenant.name,
                    ),
                    User.email,
                )
            ).all()
        current = None
        for tenant_name, email, role in rows:
            if tenant_name != current:
                current = tenant_name
                print(f"\n  {tenant_name}:")
            print(f"    {email:38} {UserRole.parse(role).value}")

        print("\nverification:", "PASSED" if ok else "FAILED")
    finally:
        engine.dispose()
    return ok


def main() -> int:
    ledger = seed()

    print("\nthis run:")
    for kind in sorted(set(ledger.created) | set(ledger.existing)):
        print(f"  {kind:13} created={ledger.created[kind]:3d}  "
              f"already present={ledger.existing[kind]:3d}")

    return 0 if verify_and_summarize() else 1


if __name__ == "__main__":
    raise SystemExit(main())
