"""
Shared fixtures for the test suite.

Tests run against the real local PostgreSQL database. Fixtures arrange data on
the privileged admin connection (DATABASE_URL_ADMIN), because the application
role cannot create a tenant: RLS is forced on every table. The code under test
still connects as the restricted application role, so assertions exercise the
real runtime isolation path.

Each test cleans up the tenants it created, so the suite leaves no rows behind.
"""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.session import engine
from app.models import (
    Agency,
    Application,
    ApplicationStatus,
    AuditEvent,
    EventType,
    EventTypeAgencyRule,
    ReviewTask,
    Tenant,
    User,
    UserRole,
)

TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(scope="session")
def admin_engine() -> sa.Engine:
    """Privileged engine used only to arrange and tear down test data."""
    eng = sa.create_engine(settings.DATABASE_URL_ADMIN, future=True)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture(scope="session", autouse=True)
def _schema_present(admin_engine: sa.Engine):
    """Fail fast with a clear message if migrations have not been run."""
    with admin_engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                sa.text(
                    "select tablename from pg_tables where schemaname = 'public'"
                )
            ).fetchall()
        }
    missing = {"tenants", "users", "agencies"} - names
    if missing:
        pytest.fail(
            f"missing tables {sorted(missing)} — run `alembic upgrade head` first"
        )


@pytest.fixture
def db(admin_engine: sa.Engine) -> Session:
    """Privileged session for arranging test data and reading assertions."""
    factory = sa.orm.sessionmaker(bind=admin_engine, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


class TenantFixture:
    """A tenant plus its users/agencies, created and tracked for cleanup."""

    def __init__(
        self,
        session: Session,
        name: str,
        *,
        with_reviewer: bool = False,
    ) -> None:
        self.session = session
        self.name = name
        self.tenant = Tenant(name=name)
        session.add(self.tenant)
        session.flush()

        # Agencies and routing rules mirror api/seed.py so tests exercise the
        # same shape as the demo data. Fire is left out of the base matrix: the
        # attendance override in app/core/routing.py is what adds it, so a
        # fixture that included it would make the threshold untestable.
        self.agencies = {
            agency_name: Agency(name=agency_name, tenant_id=self.tenant.id)
            for agency_name in ("Police", "Fire", "Health")
        }
        session.add_all(self.agencies.values())
        session.flush()

        # `agency` stays the Police department: it is what a reviewer is attached to.
        self.agency = self.agencies["Police"]

        for event_type in EventType:
            for agency_name in ("Police", "Health"):
                session.add(
                    EventTypeAgencyRule(
                        tenant_id=self.tenant.id,
                        event_type=event_type,
                        agency_id=self.agencies[agency_name].id,
                    )
                )
        session.flush()

        password_hash = hash_password(TEST_PASSWORD)
        self.organizer = self._user(
            f"{name.lower()}-organizer@example.com",
            UserRole.ORGANIZER,
            password_hash,
        )
        self.admin = self._user(
            f"{name.lower()}-admin@example.com", UserRole.CITY_ADMIN, password_hash
        )
        self.reviewer = (
            self._user(
                f"{name.lower()}-reviewer@example.com",
                UserRole.AGENCY_REVIEWER,
                password_hash,
                agency_id=self.agency.id,
            )
            if with_reviewer
            else None
        )

    def add_reviewer_for(
        self,
        agency_name: str,
        suffix: str | None = None,
    ) -> User:
        """
        Add a reviewer attached to a specific agency in this tenant.

        Needed to test agency isolation within a city: RLS isolates tenants, so
        two agencies in one tenant both pass the policy, and the reviewer's
        queue has to be scoped by `agency_id` in the application.
        """
        agency = self.agencies[agency_name]
        user = self._user(
            f"{self.name.lower()}-{agency_name.lower()}"
            f"{f'-{suffix}' if suffix else ''}-reviewer@example.com",
            UserRole.AGENCY_REVIEWER,
            hash_password(TEST_PASSWORD),
            agency_id=agency.id,
        )
        self.session.commit()
        return user

    def add_organizer(self, suffix: str = "second") -> User:
        """
        Add a second organizer to this tenant.

        Needed to test ownership within a city: RLS isolates tenants, so two
        organizers in one tenant both pass the policy and the application has to
        keep their rows apart on its own.
        """
        user = self._user(
            f"{self.name.lower()}-{suffix}-organizer@example.com",
            UserRole.ORGANIZER,
            hash_password(TEST_PASSWORD),
        )
        self.session.commit()
        return user

    def _user(
        self,
        email: str,
        role: UserRole,
        password_hash: str,
        agency_id: uuid.UUID | None = None,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            tenant_id=self.tenant.id,
            agency_id=agency_id,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def token_for(self, user: User) -> str:
        return create_access_token(
            sub=user.id, tenant_id=user.tenant_id, role=user.role.value
        )

    def cleanup(self) -> None:
        """Delete this tenant's rows. Order respects foreign keys."""
        session = self.session
        if self.tenant.id is None:
            return
        tenant_ids = [self.tenant.id]
        for model in (ReviewTask, AuditEvent, Application, EventTypeAgencyRule):
            session.query(model).filter(model.tenant_id.in_(tenant_ids)).delete(
                synchronize_session=False
            )
        session.query(User).filter(User.tenant_id.in_(tenant_ids)).delete(
            synchronize_session=False
        )
        session.query(Agency).filter(Agency.tenant_id.in_(tenant_ids)).delete(
            synchronize_session=False
        )
        session.query(Tenant).filter(Tenant.id.in_(tenant_ids)).delete(
            synchronize_session=False
        )
        session.commit()


@pytest.fixture
def make_tenant(db: Session):
    """Factory creating isolated tenants that are removed after the test."""
    created: list[TenantFixture] = []

    def _make(name: str, *, with_reviewer: bool = False) -> TenantFixture:
        fixture = TenantFixture(db, name, with_reviewer=with_reviewer)
        db.commit()
        created.append(fixture)
        return fixture

    yield _make

    db.rollback()
    for fixture in created:
        fixture.cleanup()


__all__ = ["TEST_PASSWORD", "TenantFixture"]
