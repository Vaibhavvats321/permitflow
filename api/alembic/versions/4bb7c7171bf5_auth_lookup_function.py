"""auth_lookup_function

Revision ID: 4bb7c7171bf5
Revises: 86d98452dd6d
Create Date: 2026-10-01 10:01:39.319437

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4bb7c7171bf5'
down_revision: Union[str, Sequence[str], None] = '86d98452dd6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Creates get_user_by_email(TEXT) as a SECURITY DEFINER function owned by
    the postgres superuser. This allows it to bypass FORCE ROW LEVEL SECURITY
    on the users table for the single, narrowly-scoped purpose of credential
    lookup during login. The function:
      - uses an explicit SET search_path = public to prevent search-path attacks
      - is REVOKED from PUBLIC immediately after creation
      - is GRANTED only to permitflow_app
      - returns only the four fields required for authentication
    """
    # The function must be owned by a superuser to bypass FORCE RLS.
    # Alembic migrations run as the connecting user (postgres superuser via DATABASE_URL),
    # so the function is automatically owned by postgres — no role switch needed.
    op.execute("""
        CREATE FUNCTION public.get_user_by_email(p_email TEXT)
        RETURNS TABLE (
            id          uuid,
            password_hash varchar(255),
            tenant_id   uuid,
            role        userrole
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        BEGIN
            RETURN QUERY
            SELECT
                u.id,
                u.password_hash,
                u.tenant_id,
                u.role
            FROM public.users u
            WHERE u.email = p_email;
        END;
        $$;
    """)

    # Harden: revoke public execute, grant only to the application role
    op.execute("REVOKE EXECUTE ON FUNCTION public.get_user_by_email(TEXT) FROM PUBLIC;")
    op.execute("GRANT  EXECUTE ON FUNCTION public.get_user_by_email(TEXT) TO permitflow_app;")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP FUNCTION IF EXISTS public.get_user_by_email(TEXT);")

