import sqlalchemy
from app.core.config import settings
engine = sqlalchemy.create_engine(settings.DATABASE_URL)
with engine.connect() as conn:
    result = conn.execute(sqlalchemy.text("SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public'")).fetchall()
    print('Tables RLS enabled:', result)
    policies = conn.execute(sqlalchemy.text("SELECT tablename, policyname, permissive, roles, cmd, qual, with_check FROM pg_policies WHERE schemaname = 'public'")).fetchall()
    for p in policies:
        print('Policy:', p)
    force = conn.execute(sqlalchemy.text("SELECT relname, relforcerowsecurity FROM pg_class WHERE relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public') AND relkind = 'r'")).fetchall()
    print('FORCE RLS:', force)
