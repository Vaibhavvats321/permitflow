"""agency reviewers and lookup indexes

Revision ID: 1f888b2cf36d
Revises: 4bb7c7171bf5
Create Date: 2026-10-01 12:05:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1f888b2cf36d'
down_revision: Union[str, Sequence[str], None] = '4bb7c7171bf5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # An Agency Reviewer belongs to exactly one agency within their tenant.
    # Nullable because Organizers and City Admins have no agency.
    op.execute("ALTER TABLE users ADD COLUMN agency_id uuid")
    op.create_foreign_key(
        'fk_users_agency_id',
        'users',
        'agencies',
        ['agency_id'],
        ['id'],
    )

    # Tenant scoping and lifecycle filtering for the organizer tracking view.
    op.create_index('ix_applications_tenant_id', 'applications', ['tenant_id'])
    op.create_index('ix_applications_tenant_id_status', 'applications', ['tenant_id', 'status'])

    # Reviewer queue: list applications assigned to my agency, filterable by status.
    op.create_index('ix_review_tasks_agency_id_status', 'review_tasks', ['agency_id', 'status'])
    op.create_index('ix_review_tasks_application_id', 'review_tasks', ['application_id'])

    # Application lookup by submitter for the organizer's own list.
    op.create_index('ix_applications_submitter_id', 'applications', ['submitter_id'])

    # Audit timeline is read per application, newest first.
    op.create_index(
        'ix_audit_events_application_id_created_at',
        'audit_events',
        ['application_id', 'created_at'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_audit_events_application_id_created_at', table_name='audit_events')
    op.drop_index('ix_applications_submitter_id', table_name='applications')
    op.drop_index('ix_review_tasks_application_id', table_name='review_tasks')
    op.drop_index('ix_review_tasks_agency_id_status', table_name='review_tasks')
    op.drop_index('ix_applications_tenant_id_status', table_name='applications')
    op.drop_index('ix_applications_tenant_id', table_name='applications')

    op.drop_constraint('fk_users_agency_id', 'users', type_='foreignkey')
    op.execute("ALTER TABLE users DROP COLUMN agency_id")
