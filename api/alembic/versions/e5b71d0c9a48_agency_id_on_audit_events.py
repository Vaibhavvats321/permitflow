"""agency_id on audit_events

Revision ID: e5b71d0c9a48
Revises: c3d91a7f4e82
Create Date: 2026-10-03 09:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b71d0c9a48"
down_revision: Union[str, Sequence[str], None] = "c3d91a7f4e82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Record which agency produced an audit entry.

    The brief asks each audit row to name the reviewer identity *and* the agency.
    `user_id` already identifies the individual, but a user is only implicitly
    attached to an agency: the link lives on the user row, so "which department
    made this decision" cannot be answered from the audit trail alone. It is
    stored explicitly so the timeline stays meaningful if that user's agency
    assignment is ever changed.

    Nullable: the timeline is not only reviewer decisions. Submission records an
    event too, and those have no single agency behind them. Existing rows are not
    backfilled, since rows written before this column have no agency to infer.

    The FK uses ondelete="RESTRICT" — the default and what the other foreign keys
    on this table already do. Audit history outlives the agencies it refers to,
    so no cascade belongs here.

    RLS policies are untouched. This adds a column, which does not change what a
    tenant can read: the existing tenant_isolation_policy still governs every row,
    and `app.current_tenant_id` continues to be set from the verified token.
    """
    op.add_column(
        "audit_events",
        sa.Column("agency_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_events_agency_id",
        "audit_events",
        "agencies",
        ["agency_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_audit_events_agency_id_created_at",
        "audit_events",
        ["agency_id", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_audit_events_agency_id_created_at", table_name="audit_events")
    op.drop_constraint(
        "fk_audit_events_agency_id", "audit_events", type_="foreignkey"
    )
    op.drop_column("audit_events", "agency_id")