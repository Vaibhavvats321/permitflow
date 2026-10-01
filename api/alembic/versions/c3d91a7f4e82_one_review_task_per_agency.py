"""one review task per agency per application

Revision ID: c3d91a7f4e82
Revises: 1f888b2cf36d
Create Date: 2026-10-02 10:15:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d91a7f4e82"
down_revision: Union[str, Sequence[str], None] = "1f888b2cf36d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Guarantee one review task per agency per application.

    A submitted application gets exactly one Pending task per required agency.
    Without this constraint, a double-clicked submit or a retried request could
    create a second task for the same agency, which would show up as the
    application being reviewed twice and could let a single agency cast two
    votes once reviewer decisions are implemented.

    This is a data invariant, so it belongs in the schema rather than in an
    application-level check that a race could bypass. RLS policies are
    untouched; only a constraint is added.
    """
    op.create_unique_constraint(
        "uq_review_tasks_application_agency",
        "review_tasks",
        ["application_id", "agency_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_review_tasks_application_agency", "review_tasks", type_="unique"
    )