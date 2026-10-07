"""Add agencies.attendance_threshold for per-agency large-event routing.

Replaces the hardcoded "attendance over 5,000 always adds Fire" rule with a
per-agency threshold stored in the database: an agency is required whenever
expected_attendance exceeds its threshold. NULL means "no attendance rule",
so an agency stays matrix-only.

The backfill gives every existing Fire row 5,000 so installations keep the
exact behaviour they had before this migration; admins can change it (or set
thresholds for other agencies) from the agency management screen afterwards.

Revision ID: 7f2d9a4c1e83
Revises: e5b71d0c9a48
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "7f2d9a4c1e83"
down_revision = "e5b71d0c9a48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agencies ADD COLUMN attendance_threshold integer")
    # Existing behaviour preserved for existing rows: Fire keeps the 5,000 rule.
    op.execute("UPDATE agencies SET attendance_threshold = 5000 WHERE name = 'Fire'")


def downgrade() -> None:
    op.execute("ALTER TABLE agencies DROP COLUMN attendance_threshold")
