"""Temporary inspection script — deleted after the seeder is verified."""
import sqlalchemy as sa

from app.core.config import settings

e = sa.create_engine(settings.DATABASE_URL_ADMIN)
conn = e.connect()

tables = [
    "tenants", "users", "agencies", "event_type_agency_rules",
    "applications", "review_tasks", "audit_events",
]
print("--- row counts ---")
for t in tables:
    print(f"{t}: {conn.execute(sa.text(f'select count(1) from {t}')).scalar()}")

print("--- RLS state ---")
rows = conn.execute(sa.text(
    "select relname, relrowsecurity, relforcerowsecurity from pg_class "
    "where relname in ('tenants','users','agencies','event_type_agency_rules',"
    "'applications','review_tasks','audit_events') order by relname"
)).all()
for r in rows:
    print(f"{r[0]}: enabled={r[1]}, forced={r[2]}")

print("--- policies ---")
pol = conn.execute(sa.text(
    "select tablename, policyname from pg_policies "
    "where schemaname='public' order by tablename"
)).all()
for p in pol:
    print(f"{p[0]}: {p[1]}")

print("--- alembic ---")
print(conn.execute(sa.text("select version_num from alembic_version")).scalar())

print("--- tables in public schema ---")
tt = conn.execute(sa.text(
    "select table_name from information_schema.tables "
    "where table_schema='public' order by table_name"
)).all()
print([r[0] for r in tt])

print("--- app role ---")
role = conn.execute(sa.text(
    "select rolname, rolsuper, rolcanlogin from pg_roles "
    "where rolname='permitflow_app'"
)).first()
print(role)

print("--- table grants for app role ---")
g = conn.execute(sa.text(
    "select table_name, privilege_type from information_schema.role_table_grants "
    "where grantee='permitflow_app' and table_schema='public' order by table_name, privilege_type"
)).all()
for row in g:
    print(row)

conn.close()
e.dispose()
