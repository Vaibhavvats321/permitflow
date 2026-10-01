"""
api/bootstrap_role.py

Idempotently prepare the restricted `permitflow_app` database role so the
application can connect without inheriting superuser privileges.

The application must NOT connect as a superuser: PostgreSQL Row Level Security
is enforced per table, and a role with SUPERUSER or BYPASSRLS silently ignores
every policy. Connecting privileged would therefore disable tenant isolation at
runtime while still appearing to work.

What this script guarantees:
  - permitflow_app is NOSUPERUSER and NOBYPASSRLS
  - it may log in with the password from APP_DB_PASSWORD
  - it has USAGE on schema public, DML on the PermitFlow tables, and EXECUTE on
    the get_user_by_email login function
  - tables created by future migrations are granted automatically

It does NOT alter any RLS policy, and never grants EXECUTE on
get_user_by_email to PUBLIC.

Usage:
    python api/bootstrap_role.py
    python api/bootstrap_role.py --check   # verify only, change nothing

Safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import settings  # noqa: E402

APP_ROLE = "permitflow_app"

# Order matters for readability only; each statement is independent.
GRANTS = [
    "GRANT USAGE ON SCHEMA public TO permitflow_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO permitflow_app",
    "GRANT EXECUTE ON FUNCTION public.get_user_by_email(TEXT) TO permitflow_app",
    # Cover tables added by migrations that run after this bootstrap.
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO permitflow_app",
]


def _role_exists(conn) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT count(*) FROM pg_roles WHERE rolname = :role"),
            {"role": APP_ROLE},
        ).scalar()
    )


def _role_state(conn) -> dict:
    row = conn.execute(
        sa.text(
            "SELECT rolsuper, rolbypassrls, rolcanlogin, "
            "rolpassword IS NOT NULL AS has_password "
            "FROM pg_roles WHERE rolname = :role"
        ),
        {"role": APP_ROLE},
    ).one_or_none()
    if row is None:
        return {}
    return {
        "rolsuper": row.rolsuper,
        "rolbypassrls": row.rolbypassrls,
        "rolcanlogin": row.rolcanlogin,
        "has_password": row.has_password,
    }


def _admin_engine() -> sa.Engine:
    url = make_url(settings.DATABASE_URL_ADMIN)
    if url.drivername.startswith("postgresql"):
        return sa.create_engine(settings.DATABASE_URL_ADMIN, future=True)
    raise SystemExit(f"unexpected admin driver: {url.drivername}")


def _check(conn) -> int:
    """Report whether the role is correctly configured. Returns a failure count."""
    problems: list[str] = []

    state = _role_state(conn)
    if not state:
        print(f"  {APP_ROLE}: MISSING")
        return 1

    print(f"  {APP_ROLE}: rolsuper={state['rolsuper']} "
          f"rolbypassrls={state['rolbypassrls']} "
          f"rolcanlogin={state['rolcanlogin']} "
          f"password_set={state['has_password']}")

    if state["rolsuper"]:
        problems.append("role is SUPERUSER — RLS would be bypassed")
    if state["rolbypassrls"]:
        problems.append("role has BYPASSRLS — RLS would be bypassed")
    if not state["rolcanlogin"]:
        problems.append("role cannot log in")
    if not state["has_password"]:
        problems.append("no password set")

    schema_ok = conn.execute(
        sa.text(
            "SELECT has_schema_privilege(:r, 'public', 'USAGE')"
        ),
        {"r": APP_ROLE},
    ).scalar()
    if not schema_ok:
        problems.append("missing USAGE on schema public")

    fn_ok = conn.execute(
        sa.text(
            "SELECT has_function_privilege(:r, 'public.get_user_by_email(text)', 'EXECUTE')"
        ),
        {"r": APP_ROLE},
    ).scalar()
    if not fn_ok:
        problems.append("missing EXECUTE on get_user_by_email")

    public_exec = conn.execute(
        sa.text(
            "SELECT has_function_privilege('public', 'public.get_user_by_email(text)', 'EXECUTE')"
        )
    ).scalar()
    if public_exec:
        problems.append("get_user_by_email is executable by PUBLIC — must be revoked")

    missing = conn.execute(
        sa.text(
            "SELECT coalesce(array_agg(c.relname), '{}') "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' "
            "AND NOT has_table_privilege(:r, c.oid, 'SELECT,INSERT,UPDATE,DELETE')"
        ),
        {"r": APP_ROLE},
    ).scalar()
    if missing:
        problems.append(f"tables missing DML grants: {sorted(missing)}")

    for problem in problems:
        print(f"  PROBLEM: {problem}")
    return len(problems)


def bootstrap() -> int:
    engine = _admin_engine()
    try:
        with engine.begin() as conn:
            admin_url = make_url(settings.DATABASE_URL_ADMIN)
            print(f"admin connection: {admin_url.username}@{admin_url.host}/{admin_url.database}")

            if not _role_exists(conn):
                print(f"  creating {APP_ROLE} (NOSUPERUSER NOBYPASSRLS)")
                conn.execute(sa.text(f"CREATE ROLE {APP_ROLE} NOSUPERUSER NOBYPASSRLS"))

            # ALTER ROLE ... PASSWORD does not accept a bind parameter, so the
            # value is inlined as a properly escaped SQL literal. literal_execute
            # makes SQLAlchemy quote and escape it rather than trusting us.
            conn.execute(
                sa.text(
                    f"ALTER ROLE {APP_ROLE} WITH LOGIN NOSUPERUSER NOBYPASSRLS "
                    "PASSWORD :password"
                ).bindparams(
                    sa.bindparam(
                        "password",
                        value=settings.APP_DB_PASSWORD,
                        literal_execute=True,
                    )
                )
            )
            print(f"  set LOGIN + password for {APP_ROLE}")

            for statement in GRANTS:
                conn.execute(sa.text(statement))
                print(f"  ok: {statement.split(' TO ')[0].split(' IN SCHEMA')[0]} ...")
    finally:
        engine.dispose()

    print("\nverifying:")
    with _admin_engine().connect() as conn:
        failures = _check(conn)
    return failures


def check_only() -> int:
    with _admin_engine().connect() as conn:
        print(f"checking {APP_ROLE}:")
        return _check(conn)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the role without changing anything",
    )
    args = parser.parse_args()

    failures = check_only() if args.check else bootstrap()
    if failures:
        print(f"\n{failures} problem(s) found")
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
