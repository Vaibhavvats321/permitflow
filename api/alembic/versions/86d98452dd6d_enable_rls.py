"""enable_rls

Revision ID: 86d98452dd6d
Revises: 9a53f1d86113
Create Date: 2026-10-01 09:22:27.227986

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86d98452dd6d'
down_revision: Union[str, Sequence[str], None] = '9a53f1d86113'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    tables = [
        'users',
        'agencies',
        'event_type_agency_rules',
        'applications',
        'review_tasks',
        'audit_events'
    ]
    
    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"CREATE POLICY tenant_isolation_policy ON {table} AS PERMISSIVE FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);")
    
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY;")
    op.execute("CREATE POLICY tenant_isolation_policy ON tenants AS PERMISSIVE FOR ALL USING (id = current_setting('app.current_tenant_id', true)::uuid);")


def downgrade() -> None:
    """Downgrade schema."""
    tables = [
        'users',
        'agencies',
        'event_type_agency_rules',
        'applications',
        'review_tasks',
        'audit_events',
        'tenants'
    ]
    
    for table in tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

