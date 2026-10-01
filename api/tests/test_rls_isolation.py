"""
Functional Row Level Security tests.

These run as `permitflow_app` (the unprivileged, non-superuser application role)
using SET LOCAL ROLE inside a transaction. That role has neither SUPERUSER nor
BYPASSRLS, and every table has FORCE ROW LEVEL SECURITY, so the policies in
migration 86d98452dd6d are genuinely enforced here.

No policy is modified, relaxed, or disabled to make these pass.

The application's own DATABASE_URL connects as `permitflow_app`, so the tests
below run as the same unprivileged role the application uses at runtime.
"""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.session import engine

from tests.conftest import TenantFixture


APP_ROLE = "permitflow_app"


def _pristine_engine():
    """An engine whose connections never carry prior GUC state."""
    return sa.create_engine(settings.DATABASE_URL, poolclass=NullPool)


def _app_role_available() -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(
                sa.text("select count(*) from pg_roles where rolname = :role"),
                {"role": APP_ROLE},
            ).scalar()
        )


requires_app_role = pytest.mark.skipif(
    not _app_role_available(),
    reason=f"database role {APP_ROLE} does not exist",
)


def _settings_query(session) -> str | None:
    """
    Read the tenant GUC. When unset, PostgreSQL 18 returns an empty string
    rather than NULL, so normalise both to None.
    """
    value = session.execute(
        sa.text("SELECT current_setting('app.current_tenant_id', true)")
    ).scalar()
    return value or None


@requires_app_role
def test_app_role_is_not_superuser_and_does_not_bypass_rls() -> None:
    """Precondition: this suite would be meaningless against a privileged role."""
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(sa.text(f"SET LOCAL ROLE {APP_ROLE}"))
            assert conn.execute(sa.text("select current_user")).scalar() == APP_ROLE
            row = conn.execute(
                sa.text("select rolsuper, rolbypassrls from pg_roles where rolname = current_user")
            ).one()
            assert row.rolsuper is False
            assert row.rolbypassrls is False
        finally:
            transaction.rollback()


@requires_app_role
def test_tenant_a_cannot_read_tenant_b_rows(make_tenant) -> None:
    """
    The assignment's central requirement: a Riverton user must get nothing
    from Springfield, even by guessing IDs.
    """
    springfield = make_tenant("RLSSpringfield")
    riverton = make_tenant("RLSRiverton")

    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(sa.text(f"SET LOCAL ROLE {APP_ROLE}"))
            conn.execute(
                sa.text(
                    "SELECT set_config('app.current_tenant_id', :tid, true)"
                ),
                {"tid": str(springfield.tenant.id)},
            )

            visible = {
                row[0]
                for row in conn.execute(sa.text("SELECT id FROM tenants")).fetchall()
            }
            assert springfield.tenant.id in visible
            assert riverton.tenant.id not in visible

            # Guessing the exact other-tenant UUID still returns nothing.
            guessed = conn.execute(
                sa.text("SELECT id FROM tenants WHERE id = :id"),
                {"id": str(riverton.tenant.id)},
            ).fetchall()
            assert guessed == []
        finally:
            transaction.rollback()


@requires_app_role
def test_cross_tenant_insert_is_rejected(make_tenant) -> None:
    """A row carrying another tenant's id cannot be written."""
    riverton = make_tenant("RLSInsertRiverton")
    other_id = uuid.uuid4()

    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(sa.text(f"SET LOCAL ROLE {APP_ROLE}"))
            conn.execute(
                sa.text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                {"tid": str(riverton.tenant.id)},
            )
            # PostgreSQL raises InsufficientPrivilege (42501) here, which the
            # psycopg driver surfaces as ProgrammingError rather than
            # IntegrityError, so match on the SQLSTATE via the DBAPI error.
            with pytest.raises(sa.exc.ProgrammingError) as excinfo:
                conn.execute(
                    sa.text(
                        "INSERT INTO tenants (id, name, created_at) "
                        "VALUES (:id, :name, now())"
                    ),
                    {"id": str(other_id), "name": "ForgedTenant"},
                )
            assert "row-level security" in str(excinfo.value)
        finally:
            transaction.rollback()


@requires_app_role
def test_no_tenant_context_yields_no_rows(make_tenant) -> None:
    """
    Without the tenant GUC the policies see NULL and fail closed.

    Uses a dedicated NullPool engine so the connection is guaranteed never to
    have had the GUC set. See
    test_missing_context_on_recycled_connection_errors_for_documented
    behaviour on a pooled connection that previously set it.
    """
    make_tenant("RLSNoContextTenant")
    pristine = _pristine_engine()

    try:
        with pristine.connect() as conn:
            transaction = conn.begin()
            try:
                conn.execute(sa.text(f"SET LOCAL ROLE {APP_ROLE}"))
                assert _settings_query(conn) is None
                assert conn.execute(sa.text("SELECT count(*) FROM tenants")).scalar() == 0
                assert conn.execute(sa.text("SELECT count(*) FROM users")).scalar() == 0
            finally:
                transaction.rollback()
    finally:
        pristine.dispose()


@requires_app_role
def test_missing_context_on_recycled_connection_errors_for_documented(
    make_tenant,
) -> None:
    """
    Documents a latent sharp edge in the existing policies.

    Once any transaction on a pooled connection has set
    `app.current_tenant_id`, PostgreSQL keeps the placeholder and resets it to
    the EMPTY STRING (not NULL) after commit. The current policy expression is
    `current_setting('app.current_tenant_id', true)::uuid`, so on such a
    connection a query issued without tenant context raises
    "invalid input syntax for type uuid" instead of quietly matching zero rows.

    This still leaks nothing — it fails closed with an error — but it turns a
    missing-tenant bug into a 500 rather than an empty result. The application
    path avoids it entirely because get_tenant_db sets the value in an
    after_begin hook on every transaction.

    Fixing it properly means redefining the policies with
    `nullif(current_setting(...), '')::uuid` in a new forward migration. Not
    done here: this step must not touch the existing RLS configuration.
    """
    make_tenant("RLSRecycledTenant")

    # One connection throughout: the placeholder only survives on the same
    # backend, so a second connect() could hand back a different session.
    with engine.connect() as conn:
        transaction = conn.begin()
        conn.execute(sa.text(f"SET LOCAL ROLE {APP_ROLE}"))
        conn.execute(
            sa.text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": str(uuid.uuid4())},
        )
        transaction.commit()

        transaction = conn.begin()
        try:
            conn.execute(sa.text(f"SET LOCAL ROLE {APP_ROLE}"))
            # Read raw: _settings_query normalises the empty string to None.
            raw = conn.execute(
                sa.text("SELECT current_setting('app.current_tenant_id', true)")
            ).scalar()
            assert raw == "", f"expected empty-string placeholder, got {raw!r}"
            # psycopg reports SQLSTATE 22P02 as DataError; SQLAlchemy may wrap
            # it as ProgrammingError depending on the statement, so accept both.
            with pytest.raises((sa.exc.DataError, sa.exc.ProgrammingError)) as excinfo:
                conn.execute(sa.text("SELECT count(*) FROM tenants"))
            assert "invalid input syntax for type uuid" in str(excinfo.value)
        finally:
            transaction.rollback()


@requires_app_role
def test_each_protected_table_is_isolated(make_tenant) -> None:
    """Every tenant-scoped table must hide the other tenant's rows."""
    springfield = make_tenant("RLSAllSpringfield", with_reviewer=True)
    riverton = make_tenant("RLSAllRiverton", with_reviewer=True)

    tables = [
        "tenants",
        "users",
        "agencies",
        "event_type_agency_rules",
        "applications",
        "review_tasks",
        "audit_events",
    ]

    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(sa.text(f"SET LOCAL ROLE {APP_ROLE}"))
            conn.execute(
                sa.text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                {"tid": str(springfield.tenant.id)},
            )
            for table in tables:
                if table == "tenants":
                    ids = {r[0] for r in conn.execute(sa.text("SELECT id FROM tenants")).fetchall()}
                    assert riverton.tenant.id not in ids, table
                else:
                    rows = conn.execute(sa.text(f"SELECT tenant_id FROM {table}")).fetchall()
                    assert all(r[0] == springfield.tenant.id for r in rows), table
        finally:
            transaction.rollback()


def test_rls_is_enabled_and_forced_on_every_table() -> None:
    """Schema-level guard: if someone disables RLS, this fails."""
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "select relname, relrowsecurity, relforcerowsecurity "
                "from pg_class where relnamespace = "
                "(select oid from pg_namespace where nspname = 'public') "
                "and relkind = 'r' and relname <> 'alembic_version'"
            )
        ).fetchall()
    assert rows, "no tables found"
    for name, enabled, forced in rows:
        assert enabled, f"RLS disabled on {name}"
        assert forced, f"RLS not FORCED on {name}"


def test_tenant_isolation_policy_present_on_every_table() -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "select tablename from pg_policies "
                "where schemaname = 'public' and policyname = 'tenant_isolation_policy'"
            )
        ).fetchall()
    protected = {r[0] for r in rows}
    expected = {
        "tenants",
        "users",
        "agencies",
        "event_type_agency_rules",
        "applications",
        "review_tasks",
        "audit_events",
    }
    assert expected <= protected


def test_application_connection_does_not_bypass_rls() -> None:
    """
    The live connection must not be able to opt out of RLS.

    Every other test in this file proves the policies work. This one proves they
    are actually reached: the application's DATABASE_URL has to connect as a
    role that is neither SUPERUSER nor BYPASSRLS, otherwise RLS is inert at
    runtime no matter how correct the policies are.
    """
    with engine.connect() as conn:
        current_user = conn.execute(sa.text("select current_user")).scalar()
        row = conn.execute(
            sa.text(
                "select rolsuper, rolbypassrls from pg_roles where rolname = :u"
            ),
            {"u": current_user},
        ).one()

    assert current_user == APP_ROLE, (
        f"DATABASE_URL connects as {current_user!r}, expected {APP_ROLE!r}"
    )
    assert row.rolsuper is False
    assert row.rolbypassrls is False


def test_app_role_cannot_see_rows_without_tenant_context(make_tenant) -> None:
    """
    The connection the application actually uses must fail closed.

    Complements the tests above, which set an explicit tenant: even with no
    GUC set at all, the runtime role sees nothing.
    """
    springfield = make_tenant("RLSFailClosedSpringfield")
    make_tenant("RLSFailClosedRiverton")

    pristine = _pristine_engine()
    try:
        with pristine.connect() as conn:
            assert conn.execute(sa.text("select current_user")).scalar() == APP_ROLE
            assert _settings_query(conn) is None
            assert conn.execute(sa.text("select count(*) from tenants")).scalar() == 0
            assert conn.execute(sa.text("select count(*) from users")).scalar() == 0
            # Even a directly addressed row id yields nothing.
            assert conn.execute(
                sa.text("select id from tenants where id = :id"),
                {"id": str(springfield.tenant.id)},
            ).fetchall() == []
    finally:
        pristine.dispose()
